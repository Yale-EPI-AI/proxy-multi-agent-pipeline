"""Smoke test for the discovery agent.

Run: uv run python src/scripts/test_discovery.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from epi_proxy.stage1.discovery import run_discovery
from epi_proxy.stage1.tools import execute_tool, DISCOVERY_TOOLS
from epi_proxy.utils.data_utils import load_variable_metadata
from epi_proxy.utils.db import get_connection, variable_coverage


async def test_tool_dispatch():
    """Test individual tool execution."""
    print("\n=== Tool Dispatch Tests ===")
    conn = get_connection()

    # Test search_world_bank
    result = execute_tool("search_world_bank", {"query": "water access"}, conn)
    data = json.loads(result)
    print(f"search_world_bank('water access'): {len(data)} results")
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    print("  PASS")

    # Test list_db_variables
    result = execute_tool("list_db_variables", {}, conn)
    data = json.loads(result)
    print(f"list_db_variables(): {len(data)} variables in DB")
    print("  PASS")

    # Test search_nasa_power
    result = execute_tool("search_nasa_power", {"query": "temperature"}, conn)
    data = json.loads(result)
    print(f"search_nasa_power('temperature'): {len(data)} results")
    print("  PASS")


async def test_discovery_agent():
    """Smoke test the full discovery agent with limited tool calls."""
    print("\n=== Discovery Agent Smoke Test ===")

    tla = "UWD"
    metadata = load_variable_metadata(tla)
    print(f"Running discovery for {tla}: {metadata.get('Description', '')}")

    research_output = await run_discovery(
        tla, metadata, max_tool_calls=15,
    )

    print(f"Hypotheses found: {len(research_output.hypotheses)}")
    assert len(research_output.hypotheses) >= 1, "Expected at least 1 hypothesis"

    # Check for db_variable_id
    db_linked = [h for h in research_output.hypotheses if h.db_variable_id]
    print(f"Hypotheses with db_variable_id: {len(db_linked)}")

    for h in research_output.hypotheses:
        print(f"  {h.id}: {h.proxy_variable} (db_id={h.db_variable_id})")
        print(f"    direction={h.relationship.direction.value}, "
              f"strength={h.relationship.strength_estimate}")

    print("  PASS")


if __name__ == "__main__":
    asyncio.run(test_tool_dispatch())
    asyncio.run(test_discovery_agent())
    print("\n=== ALL TESTS PASSED ===")
