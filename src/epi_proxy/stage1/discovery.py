"""Stage 1 Discovery Agent: tool-using Claude agent that explores data APIs.

Replaces the Gemini deep research + Claude parser pipeline with a single
Claude Sonnet agent that can directly search, preview, fetch, and correlate
data from multiple APIs (World Bank, WHO, NASA POWER, FAOSTAT).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from epi_proxy.config import (
    CLAUDE_DISCOVERY_MODEL,
    DB_PATH,
    DISCOVERY_MAX_TOOL_CALLS,
    OUTPUTS_DIR,
)
from epi_proxy.schemas import ProxyHypothesis, ResearchOutput
from epi_proxy.stage1.prompts import DISCOVERY_SYSTEM_PROMPT, DISCOVERY_USER_PROMPT_TEMPLATE
from epi_proxy.stage1.tools import DISCOVERY_TOOLS, execute_tool
from epi_proxy.utils.llm import LLMClient

logger = logging.getLogger(__name__)


def _build_domain_knowledge_section(tla: str) -> str:
    """Build domain knowledge section if available."""
    try:
        from epi_proxy.domain_knowledge import DOMAIN_KNOWLEDGE
        if tla in DOMAIN_KNOWLEDGE:
            return f"## Domain Context\n{DOMAIN_KNOWLEDGE[tla]}\n\n"
    except ImportError:
        pass
    return ""


async def run_discovery(
    tla: str,
    metadata: dict,
    *,
    max_tool_calls: int = None,
    db_path: Path = None,
) -> ResearchOutput:
    """Run the tool-using discovery agent for a given EPI indicator.

    Args:
        tla: EPI indicator three-letter abbreviation.
        metadata: Indicator metadata from load_variable_metadata().
        max_tool_calls: Max tool calls before forcing finalization.
        db_path: Override DB path (defaults to config.DB_PATH).

    Returns:
        ResearchOutput with discovered hypotheses.
    """
    if max_tool_calls is None:
        max_tool_calls = DISCOVERY_MAX_TOOL_CALLS
    if db_path is None:
        db_path = DB_PATH

    # Ensure target indicator is loaded in DB
    from epi_proxy.utils.db import get_connection
    from epi_proxy.utils.data_utils import load_raw_indicator
    from epi_proxy.utils.db import register_variable, upsert_observations, variable_exists

    conn = get_connection(db_path)

    target_variable_id = f"epi:{tla}"
    if not variable_exists(conn, target_variable_id):
        logger.info("Loading target indicator %s into DB", tla)
        df = load_raw_indicator(tla)
        register_variable(
            conn, target_variable_id,
            name=metadata.get("Description", tla),
            source_type="epi",
            source_org=metadata.get("Source", "EPI"),
            polarity=metadata.get("Polarity", None),
        )
        upsert_observations(conn, target_variable_id, df, triggered_by="discovery_init")

    # Also ensure control variables are loaded
    from epi_proxy.config import CONTROL_VARIABLE_TLAS
    for ctrl_tla in CONTROL_VARIABLE_TLAS:
        ctrl_id = f"epi:{ctrl_tla}"
        if not variable_exists(conn, ctrl_id):
            try:
                ctrl_df = load_raw_indicator(ctrl_tla)
                register_variable(conn, ctrl_id, name=ctrl_tla, source_type="epi")
                upsert_observations(conn, ctrl_id, ctrl_df, triggered_by="discovery_init")
            except Exception:
                logger.debug("Could not load control variable %s", ctrl_tla)

    # Build prompts
    domain_section = _build_domain_knowledge_section(tla)
    user_prompt = DISCOVERY_USER_PROMPT_TEMPLATE.format(
        tla=tla,
        indicator_name=metadata.get("Description", tla),
        units=metadata.get("Units", ""),
        source_org=metadata.get("Source", ""),
        issue_category=metadata.get("IssueCategory", ""),
        polarity=metadata.get("Polarity", ""),
        domain_knowledge_section=domain_section,
    )

    # Initialize LLM client
    client = LLMClient(trace_dir=OUTPUTS_DIR / tla)
    messages = [{"role": "user", "content": user_prompt}]

    tool_call_count = 0
    tool_log: list[dict] = []

    logger.info("Starting discovery agent for %s (max %d tool calls)", tla, max_tool_calls)

    # Agent loop
    while True:
        response = await client.chat_with_tools(
            model=CLAUDE_DISCOVERY_MODEL,
            max_tokens=8192,
            system=DISCOVERY_SYSTEM_PROMPT,
            tools=DISCOVERY_TOOLS,
            messages=messages,
        )

        logger.info(
            "Agent response: stop_reason=%s, tool_uses=%d, text_len=%d",
            response.stop_reason, len(response.tool_uses), len(response.text or ""),
        )

        # If no tool use, we're done
        if response.stop_reason == "end_turn" or not response.tool_uses:
            logger.info("Discovery agent finished after %d tool calls", tool_call_count)
            final_text = response.text or ""
            break

        # Execute tool calls
        messages.append(client.build_assistant_message(response))
        tool_results_raw: list[tuple[str, str, str]] = []

        for tu in response.tool_uses:
            tool_call_count += 1
            logger.info(
                "Tool call %d/%d: %s(%s)",
                tool_call_count, max_tool_calls,
                tu.name, json.dumps(tu.input)[:100],
            )

            result_str = execute_tool(tu.name, tu.input, conn)
            tool_log.append({
                "call_number": tool_call_count,
                "tool": tu.name,
                "input": tu.input,
                "result_preview": result_str[:200],
            })

            tool_results_raw.append((tu.id, tu.name, result_str))

        messages.extend(client.build_tool_result_messages(tool_results_raw))

        # Check budget
        if tool_call_count >= max_tool_calls:
            logger.info("Tool call budget exhausted (%d), requesting finalization", tool_call_count)
            messages.append({
                "role": "user",
                "content": (
                    "You have used all your tool call budget. "
                    "Please finalize your hypotheses now based on what you've found so far. "
                    "Output your final JSON with the hypotheses array."
                ),
            })
            # One more turn to get the final output
            response = await client.chat_with_tools(
                model=CLAUDE_DISCOVERY_MODEL,
                max_tokens=8192,
                system=DISCOVERY_SYSTEM_PROMPT,
                tools=DISCOVERY_TOOLS,
                messages=messages,
            )
            final_text = response.text or ""
            break

    # Parse final output
    research_output = _parse_discovery_output(tla, final_text)

    # Save artifacts
    output_dir = OUTPUTS_DIR / tla / "stage1"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "discovery_output.json").write_text(
        json.dumps({"final_text": final_text, "tool_log": tool_log}, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "hypotheses.json").write_text(
        research_output.model_dump_json(indent=2),
        encoding="utf-8",
    )

    logger.info(
        "Discovery complete for %s: %d hypotheses, %d tool calls",
        tla, len(research_output.hypotheses), tool_call_count,
    )

    return research_output


# Enum value repair table for discovery-agent outputs.
#
# The agent frequently invents natural-language enum values (e.g. "high"
# confidence, "administrative" methodology, "monthly" update frequency). A
# single bad enum used to kill the entire hypothesis at Pydantic validation;
# this table coerces known-bad values to sensible defaults before validation.
#
# Keys are LOWERCASED and stripped; values are valid enum strings from
# src/schemas.py. Any value not in the table falls through to "unknown" for
# that field (if the enum has one) or is left alone.
_ENUM_REPAIRS: dict[str, dict[str, str]] = {
    "confidence": {
        "high": "speculative",
        "medium": "speculative",
        "low": "speculative",
        "strong": "speculative",
        "moderate": "speculative",
        "weak": "speculative",
        "certain": "literature_backed",
        "verified": "literature_backed",
        "expert": "expert_opinion",
    },
    "evidence_type": {
        "programmatic": "programmatic_verify",
        "literature": "literature_attested",
        "manual": "manual_data_needed",
    },
    "accessibility": {
        "free": "open",
        "public": "open",
        "account": "free_account",
        "registration": "free_account",
        "api": "open",
    },
    "update_frequency": {
        "monthly": "annual",
        "monthly (aggregated annually)": "annual",
        "weekly": "annual",
        "daily": "annual",
        "quarterly": "annual",
        "continuous": "annual",
        "near-real-time": "annual",
        "real-time": "annual",
        "static": "one_time",
        "single": "one_time",
        "periodic": "irregular",
        "sporadic": "irregular",
    },
    "methodology_status": {
        "administrative": "government_official",
        "administrative data": "government_official",
        "modeled": "international_org",
        "model": "international_org",
        "model-based": "international_org",
        "reanalysis": "international_org",
        "satellite": "satellite_derived",
        "remote sensing": "satellite_derived",
        "sensor": "sensor_network",
        "crowdsourced": "sensor_network",
        "digital": "digital_behavioral",
        "trade data": "trade_statistics",
        "customs": "trade_statistics",
        "grey literature": "grey_literature",
        "survey": "international_org",
    },
    "direction": {
        "inverse": "negative",
        "proportional": "positive",
        "u-shaped": "nonlinear",
        "complex": "nonlinear",
    },
    "functional_form": {
        "log": "log-linear",
        "log linear": "log-linear",
        "loglinear": "log-linear",
        "polynomial": "quadratic",
        "exponential": "nonlinear",
        "sigmoid": "nonlinear",
    },
}

# Valid enum values per field — used to avoid coercing a value that's
# already valid. Populated lazily on first use.
_ENUM_VALID: dict[str, set[str]] = {}


def _load_valid_enums() -> None:
    """Populate _ENUM_VALID from schema enums (called once)."""
    if _ENUM_VALID:
        return
    from epi_proxy.schemas import (
        Confidence, EvidenceType, Accessibility, UpdateFrequency,
        MethodologyStatus, Direction, FunctionalForm,
    )
    _ENUM_VALID["confidence"] = {e.value for e in Confidence}
    _ENUM_VALID["evidence_type"] = {e.value for e in EvidenceType}
    _ENUM_VALID["accessibility"] = {e.value for e in Accessibility}
    _ENUM_VALID["update_frequency"] = {e.value for e in UpdateFrequency}
    _ENUM_VALID["methodology_status"] = {e.value for e in MethodologyStatus}
    _ENUM_VALID["direction"] = {e.value for e in Direction}
    _ENUM_VALID["functional_form"] = {e.value for e in FunctionalForm}


def _repair_enum(field: str, value) -> tuple[object, bool]:
    """Coerce a value for an enum field. Returns (repaired_value, was_repaired).

    - If value is None or already valid, returns it unchanged.
    - If value is in the per-field repair table, maps to the target.
    - Otherwise falls back to 'unknown' (or keeps as-is if the enum has no
      'unknown' variant).
    """
    _load_valid_enums()
    if value is None or not isinstance(value, str):
        return value, False
    clean = value.strip().lower()
    if clean in _ENUM_VALID.get(field, set()):
        return clean if clean != value else value, clean != value
    mapping = _ENUM_REPAIRS.get(field, {})
    if clean in mapping:
        return mapping[clean], True
    # Try loose substring match against the repair table
    for bad, good in mapping.items():
        if bad in clean or clean in bad:
            return good, True
    # Last resort: 'unknown' if the enum supports it
    valid = _ENUM_VALID.get(field, set())
    if "unknown" in valid:
        return "unknown", True
    return value, False


def _repair_hypothesis_enums(h_data: dict, hyp_id: str) -> list[str]:
    """Walk a hypothesis dict and repair enum-typed fields in place.

    Returns a list of repair notes (one per field that was coerced), for
    logging. Does NOT raise on unexpected structure — missing sub-dicts
    are skipped.
    """
    notes: list[str] = []

    # Top-level: confidence, evidence_type
    for field in ("confidence", "evidence_type"):
        if field in h_data:
            repaired, changed = _repair_enum(field, h_data[field])
            if changed:
                notes.append(f"{field}={h_data[field]!r}->{repaired!r}")
                h_data[field] = repaired

    # Relationship: direction, functional_form
    rel = h_data.get("relationship")
    if isinstance(rel, dict):
        for field in ("direction", "functional_form"):
            if field in rel:
                repaired, changed = _repair_enum(field, rel[field])
                if changed:
                    notes.append(f"relationship.{field}={rel[field]!r}->{repaired!r}")
                    rel[field] = repaired

    # Data source: accessibility, update_frequency, methodology_status
    ds = h_data.get("data_source")
    if isinstance(ds, dict):
        for field in ("accessibility", "update_frequency", "methodology_status"):
            if field in ds:
                repaired, changed = _repair_enum(field, ds[field])
                if changed:
                    notes.append(f"data_source.{field}={ds[field]!r}->{repaired!r}")
                    ds[field] = repaired

    if notes:
        logger.info(
            "Repaired enums in hypothesis %s: %s", hyp_id, "; ".join(notes),
        )
    return notes


def _parse_discovery_output(tla: str, text: str) -> ResearchOutput:
    """Parse the agent's final JSON output into a ResearchOutput.

    Invalid enum values (e.g. confidence='high', methodology_status=
    'administrative') are repaired in place via _repair_hypothesis_enums
    BEFORE Pydantic validation, so one bad field doesn't drop the whole
    hypothesis. Repairs are logged at INFO level.
    """
    # Try to extract JSON from the text
    # Look for ```json ... ``` block first
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try to find raw JSON object with "hypotheses"
        json_match = re.search(r"\{[\s\S]*\"hypotheses\"[\s\S]*\}", text)
        if json_match:
            json_str = json_match.group(0)
        else:
            # Also try to find raw JSON array of hypotheses
            json_match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", text)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning("Could not find JSON in discovery output")
                return ResearchOutput(indicator_tla=tla, hypotheses=[])

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse discovery JSON: %s", exc)
        return ResearchOutput(indicator_tla=tla, hypotheses=[])

    # If the LLM returned a JSON list directly: [ { "id": ... }, ... ]
    if isinstance(data, list):
        data = {"hypotheses": data}
    elif not isinstance(data, dict):
        logger.warning("Unexpected JSON type in discovery output: %s", type(data))
        return ResearchOutput(indicator_tla=tla, hypotheses=[])

    raw_hypotheses = data.get("hypotheses", [])
    if not isinstance(raw_hypotheses, list):
        logger.warning("Expected 'hypotheses' to be a list, got %s", type(raw_hypotheses))
        raw_hypotheses = []

    hypotheses = []
    for h_data in raw_hypotheses:
        if not isinstance(h_data, dict):
            continue
        # Skip mock tool calls output as text (e.g. {"type": "function", ...})
        if "type" in h_data and "function" in h_data:
            continue
        if "id" not in h_data and "proxy_variable" not in h_data:
            continue
        hyp_id = h_data.get("id", "?")
        _repair_hypothesis_enums(h_data, hyp_id)
        try:
            hyp = ProxyHypothesis.model_validate(h_data)
            hypotheses.append(hyp)
        except Exception as exc:
            logger.warning(
                "Failed to parse hypothesis %s after repair: %s", hyp_id, exc,
            )
            continue

    return ResearchOutput(
        indicator_tla=tla,
        hypotheses=hypotheses,
        causal_map_summary=data.get("causal_map_summary", "") if isinstance(data, dict) else "",
    )
