"""Post-verification validation agent: reviews verification outputs for quality issues."""

import json
import logging
from pathlib import Path
from typing import Optional

import anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_VALIDATION_MODEL,
    INCLUSION_BINDING_MODE,
    INCLUSION_CRITICAL_CRITERIA,
    INCLUSION_SOFT_GATE_MIN_SCORE,
    VALIDATION_MAX_TOKENS,
)
from src.schemas import InclusionCriteriaScore, ProxyHypothesis, ValidationAnnotation, Verdict, VerificationResult
from src.stage2.prompts import VALIDATOR_SYSTEM_PROMPT, build_validation_prompt

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
) -> tuple[Verdict, list[str]]:
    """Apply inclusion criteria gating to adjust the verdict.

    Args:
        annotation: The validation annotation (must have inclusion_score).
        current_verdict: The verdict from statistical verification.
        binding_mode: Override for INCLUSION_BINDING_MODE.

    Returns:
        (adjusted_verdict, gate_notes) — verdict may be unchanged.
    """
    mode = binding_mode or INCLUSION_BINDING_MODE
    gate_notes: list[str] = []

    if mode == "advisory" or annotation.inclusion_score is None:
        return current_verdict, gate_notes

    score = annotation.inclusion_score

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
        logger.warning("No verify.py or result.json found in %s — skipping validation", output_dir)
        return None

    # Build prompt
    hypothesis_json = hypothesis.model_dump_json(indent=2)
    user_prompt = build_validation_prompt(
        hypothesis_json=hypothesis_json,
        verify_py_contents=verify_py,
        result_json_contents=result_json,
        agent_output_contents=agent_output,
    )

    # Call Anthropic API (async)
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    logger.info("Validating %s with %s...", hypothesis.id, CLAUDE_VALIDATION_MODEL)

    response = await client.messages.create(
        model=CLAUDE_VALIDATION_MODEL,
        max_tokens=VALIDATION_MAX_TOKENS,
        system=VALIDATOR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text
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

    # Apply inclusion criteria gating
    adjusted_verdict, gate_notes = apply_inclusion_gate(
        annotation, verification_result.verdict, inclusion_binding_mode
    )
    if gate_notes:
        annotation.issues.extend(gate_notes)

    return annotation, adjusted_verdict
