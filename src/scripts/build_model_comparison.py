#!/usr/bin/env python3
"""Build a self-contained HTML dashboard comparing multiple model runs.

Scans a parent directory whose subdirectories are model output dirs (each
holding ``{TLA}/pipeline_result.json`` files), loads every pipeline result,
and writes one consolidated ``model_comparison.html`` with:
  • per-model summary cards
  • an indicator x model verdict matrix
  • shared-proxy agreement (hypotheses matched by db_variable_id)
  • an expandable per-indicator deep-dive

Usage:
    uv run python src/scripts/build_model_comparison.py
    uv run python src/scripts/build_model_comparison.py --root new-outputs
    uv run python src/scripts/build_model_comparison.py --root new-outputs/ \
        --output new-outputs/model_comparison.html
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from epi_proxy.report_compare import build_comparison_html, load_model_runs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("new-outputs"),
        help="Parent directory containing model output directories (default: new-outputs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output HTML path (default: <root>/model_comparison.html)",
    )
    args = parser.parse_args()

    root: Path = args.root.resolve()
    if not root.is_dir():
        parser.error(f"Root directory does not exist: {root}")

    runs = load_model_runs(root)
    if not runs:
        parser.error(f"No model output directories (containing pipeline_result.json) found under {root}")

    output = (args.output or root / "model_comparison.html").resolve()
    html = build_comparison_html(runs, root_name=root.name)
    output.write_text(html, encoding="utf-8")

    print(f"Compared {len(runs)} model runs under {root}:")
    for run in runs:
        n_hyps = len(run.all_hypotheses)
        n_verified = len(run.all_verifications)
        print(f"  {run.name}: {len(run.results)} indicators, {n_hyps} hypotheses, {n_verified} verified")
    print(f"\nWrote: {output}")


if __name__ == "__main__":
    main()
