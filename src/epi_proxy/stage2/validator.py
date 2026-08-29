"""Post-verification validation agent: reviews verification outputs for quality issues."""

import json
import logging
from pathlib import Path
from typing import Optional

from epi_proxy.config import (
    CLAUDE_VALIDATION_MODEL,
    INCLUSION_BINDING_MODE,
    INCLUSION_CRITICAL_CRITERIA,
    INCLUSION_SOFT_GATE_MIN_SCORE,
    OUTPUTS_DIR,
    VALIDATION_MAX_TOKENS,
)
from epi_proxy.schemas import (
    ProxyHypothesis,
    ValidationAnnotation,
    Verdict,
    VerificationResult,
)
from epi_proxy.stage2.prompts import (
    VALIDATOR_SYSTEM_PROMPT,
    VALIDATOR_SYSTEM_PROMPT_DB,
    build_validation_prompt,
    build_validation_prompt_from_db,
)
from epi_proxy.utils.llm import LLMClient

logger = logging.getLogger(__name__)


def _read_file_safe(path: Path) -> str:
    """Read a file, returning empty string if missing or unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        logger.debug("Could not read %s: %s", path, e)
        return ""


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences if present (```json ... ```)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # remove closing fence
        text = "\n".join(lines)
    return text


def apply_inclusion_gate(
    annotation: ValidationAnnotation,
    current_verdict: Verdict,
    binding_mode: str | None = None,
    target_tla: str | None = None,
) -> tuple[Verdict, list[str]]:
    """Apply inclusion criteria gating to adjust the verdict.

    Args:
        annotation: The validation annotation (must have inclusion_score).
        current_verdict: The verdict from statistical verification.
        binding_mode: Override for INCLUSION_BINDING_MODE.
        target_tla: Indicator TLA. Used to escalate signal_independence from
            advisory to yellow-flag warning for indicators in
            domain_knowledge.GDP_IMPUTATION_DEPENDENT.

    Returns:
        (adjusted_verdict, gate_notes) — verdict may be unchanged.
    """
    mode = binding_mode or INCLUSION_BINDING_MODE
    gate_notes: list[str] = []

    if annotation.inclusion_score is None:
        return current_verdict, gate_notes

    score = annotation.inclusion_score

    # Per-indicator escalation: for indicators whose EPI imputation model is
    # f(GDP, region), a proxy failing signal_independence is essentially
    # re-deriving the imputation. Surface as a yellow-flag warning (even in
    # advisory mode) — NOT a verdict downgrade, just prominent in the output.
    if target_tla:
        try:
            from epi_proxy.domain_knowledge import is_gdp_imputation_dependent

            if (
                is_gdp_imputation_dependent(target_tla)
                and score.signal_independence is False
            ):
                gate_notes.append(
                    f"signal_independence warning ({target_tla} is GDP-imputation-"
                    "dependent): the proxy's correlation is explained by GDP per "
                    "capita, re-deriving the imputation rather than adding "
                    "independent information. Not a rejection — review mechanism."
                )
        except Exception as exc:  # pragma: no cover — defensive import
            logger.debug("GDP-imputation check failed: %s", exc)

    if mode == "advisory":
        return current_verdict, gate_notes

    # Hard gate: reject if any critical criterion is explicitly False
    if mode == "hard_gate":
        for criterion in INCLUSION_CRITICAL_CRITERIA:
            value = getattr(score, criterion, None)
            if value is False:
                gate_notes.append(
                    f"Inclusion hard gate: '{criterion}' is False → rejected"
                )
                return Verdict.rejected, gate_notes

    # Soft gate (and hard gate fallthrough): downgrade confirmed → partially_confirmed
    if mode in ("soft_gate", "hard_gate"):
        if (
            score.criteria_met is not None
            and score.criteria_met < INCLUSION_SOFT_GATE_MIN_SCORE
            and current_verdict == Verdict.confirmed
        ):
            gate_notes.append(
                f"Inclusion soft gate: criteria_met={score.criteria_met} < "
                f"{INCLUSION_SOFT_GATE_MIN_SCORE} → downgraded to partially_confirmed"
            )
            return Verdict.partially_confirmed, gate_notes

    return current_verdict, gate_notes


async def _call_validation_llm(
    hypothesis: ProxyHypothesis,
    verification_result: VerificationResult,
    output_dir: Path,
    user_prompt: str,
    inclusion_binding_mode: str | None = None,
    log_label: str = "",
    system_prompt: str = VALIDATOR_SYSTEM_PROMPT,
) -> Optional[tuple[ValidationAnnotation, Verdict]]:
    """Shared tail: LLM call, parse, save validation.json, apply inclusion gate."""
    trace_dir = OUTPUTS_DIR / hypothesis.target_variable
    client = LLMClient(trace_dir=trace_dir)

    logger.info("Validating%s %s...", log_label, hypothesis.id)

    raw_text = await client.chat_completion(
        model=CLAUDE_VALIDATION_MODEL,
        max_tokens=VALIDATION_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = _strip_markdown_fences(raw_text)

    # Parse and validate
    parsed = json.loads(raw_text)
    annotation = ValidationAnnotation.model_validate(parsed)

    # Save standalone validation.json
    validation_path = output_dir / "validation.json"
    validation_path.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved validation to %s", validation_path)

    # Apply inclusion criteria gating (passes TLA so GDP-imputation-dependent
    # indicators can surface signal_independence as a yellow-flag warning).
    adjusted_verdict, gate_notes = apply_inclusion_gate(
        annotation,
        verification_result.verdict,
        inclusion_binding_mode,
        target_tla=hypothesis.target_variable,
    )
    if gate_notes:
        annotation.issues.extend(gate_notes)

    return annotation, adjusted_verdict


async def validate_result(
    hypothesis: ProxyHypothesis,
    verification_result: VerificationResult,
    output_dir: Path,
    inclusion_binding_mode: str | None = None,
) -> Optional[tuple[ValidationAnnotation, Verdict]]:
    """Validate a verification result by reviewing the agent's outputs.

    Args:
        hypothesis: The proxy hypothesis that was verified.
        verification_result: The structured result from verification.
        output_dir: Directory containing verify.py, result.json, agent_output.txt.
        inclusion_binding_mode: Override for inclusion criteria binding mode.

    Returns:
        (ValidationAnnotation, adjusted_verdict) if successful, None on failure.
    """
    # Read verification artifacts
    verify_py = _read_file_safe(output_dir / "verify.py")
    result_json = _read_file_safe(output_dir / "result.json")
    # Fall back to in-memory result if file not on disk
    if not result_json:
        result_json = verification_result.model_dump_json(indent=2)
    agent_output = _read_file_safe(output_dir / "agent_output.txt")

    if not verify_py and not result_json:
        logger.warning(
            "No verify.py or result.json found in %s — skipping validation", output_dir
        )
        return None

    # Build prompt
    hypothesis_json = hypothesis.model_dump_json(indent=2)
    user_prompt = build_validation_prompt(
        hypothesis_json=hypothesis_json,
        verify_py_contents=verify_py,
        result_json_contents=result_json,
        agent_output_contents=agent_output,
    )

    return await _call_validation_llm(
        hypothesis, verification_result, output_dir, user_prompt,
        inclusion_binding_mode,
    )


async def validate_result_from_db(
    hypothesis: ProxyHypothesis,
    verification_result: VerificationResult,
    output_dir: Path,
    inclusion_binding_mode: str | None = None,
) -> Optional[tuple[ValidationAnnotation, Verdict]]:
    """Validate a DB-verified hypothesis (no verify.py / agent_output.txt artifacts).

    Args:
        hypothesis: The proxy hypothesis that was verified.
        verification_result: The structured result from DB verification.
        output_dir: Directory containing result.json.
        inclusion_binding_mode: Override for inclusion criteria binding mode.

    Returns:
        (ValidationAnnotation, adjusted_verdict) if successful, None on failure.
    """
    # Read result.json (the only artifact the DB path produces)
    result_json = _read_file_safe(output_dir / "result.json")
    if not result_json:
        result_json = verification_result.model_dump_json(indent=2)

    if not result_json:
        logger.warning("No result.json found in %s — skipping validation", output_dir)
        return None

    # Build prompt (DB-specific — no verify.py / agent_output.txt context)
    hypothesis_json = hypothesis.model_dump_json(indent=2)
    user_prompt = build_validation_prompt_from_db(
        hypothesis_json=hypothesis_json,
        result_json_contents=result_json,
    )

    return await _call_validation_llm(
        hypothesis, verification_result, output_dir, user_prompt,
        inclusion_binding_mode,
        log_label=" (DB path)",
        system_prompt=VALIDATOR_SYSTEM_PROMPT_DB,
    )
