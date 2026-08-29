"""Compile the knowledge graph from all pipeline outputs.

Scans outputs/ for directories matching EPI indicator TLAs,
loads their pipeline_result.json files, builds the graph,
runs clingo reasoning, and exports results.

Usage: uv run python src/scripts/compile_knowledge_graph.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from epi_proxy.config import OUTPUTS_DIR
from epi_proxy.knowledge_graph import (
    GraphBuilder,
    run_reasoning,
    get_coverage_gaps,
    get_graph_stats,
    get_indicator_coverage_summary,
    to_json,
    to_graphml,
    to_summary_report,
    generate_html,
)


def main() -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # 1. Build the graph
    console.print("\n[bold]Building EPI knowledge graph...[/bold]")
    builder = GraphBuilder()
    kg = builder.build()

    stats = get_graph_stats(kg)
    console.print(f"  Nodes: {stats['total_nodes']}, Edges: {stats['total_edges']}")

    # 2. Run reasoning
    console.print("\n[bold]Running clingo reasoning...[/bold]")
    inferences = run_reasoning(kg)
    console.print(f"  {len(inferences)} inferences generated")

    # Summarize inference types
    inf_types: dict[str, int] = {}
    for inf in inferences:
        inf_types[inf.inference_type] = inf_types.get(inf.inference_type, 0) + 1
    for itype, count in sorted(inf_types.items()):
        console.print(f"    {itype}: {count}")

    # 3. Summary table (recompute after reasoning adds inferred edges)
    stats = get_graph_stats(kg)
    console.print("\n[bold]Node/Edge Summary[/bold]")
    summary_table = Table(show_header=True)
    summary_table.add_column("Type", style="cyan")
    summary_table.add_column("Count", justify="right")
    for key, val in sorted(stats.items()):
        if key.startswith("node:") or key.startswith("edge:"):
            summary_table.add_row(key, str(val))
    summary_table.add_row("indicators_with_proxies", str(stats.get("indicators_with_proxies", 0)))
    summary_table.add_row("indicators_without_proxies", str(stats.get("indicators_without_proxies", 0)))
    console.print(summary_table)

    # 4. Indicator coverage
    console.print("\n[bold]Indicator Coverage[/bold]")
    df = get_indicator_coverage_summary(kg)
    has_proxies = df[df["total_proxies"] > 0]
    if not has_proxies.empty:
        cov_table = Table(show_header=True)
        cov_table.add_column("TLA", style="cyan")
        cov_table.add_column("Indicator")
        cov_table.add_column("Proxies", justify="right")
        cov_table.add_column("Confirmed", justify="right", style="green")
        cov_table.add_column("Partial", justify="right", style="yellow")
        cov_table.add_column("Inconclusive", justify="right")
        cov_table.add_column("Rejected", justify="right", style="red")
        cov_table.add_column("Inferred", justify="right", style="blue")
        for _, row in has_proxies.iterrows():
            cov_table.add_row(
                row["tla"],
                str(row["label"])[:40],
                str(row["total_proxies"]),
                str(row["confirmed"]),
                str(row["partially_confirmed"]),
                str(row["inconclusive"]),
                str(row["rejected"]),
                str(row["inferred_candidates"]),
            )
        console.print(cov_table)

    # Coverage gaps
    gaps = get_coverage_gaps(kg)
    console.print(f"\n[bold]Coverage gaps:[/bold] {len(gaps)} indicators with no proxies")

    # 5. Export
    out_dir = OUTPUTS_DIR / "knowledge_graph"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out_dir / "graph.json"
    with open(json_path, "w") as f:
        json.dump(to_json(kg), f, indent=2, default=str)
    console.print(f"\n[green]Saved:[/green] {json_path}")

    # GraphML
    graphml_path = out_dir / "graph.graphml"
    to_graphml(kg, graphml_path)
    console.print(f"[green]Saved:[/green] {graphml_path}")

    # Summary report
    report_path = out_dir / "summary.md"
    report = to_summary_report(kg, inferences)
    with open(report_path, "w") as f:
        f.write(report)
    console.print(f"[green]Saved:[/green] {report_path}")

    # Interactive HTML visualization
    html_path = out_dir / "graph.html"
    generate_html(kg, inferences, output_path=html_path)
    console.print(f"[green]Saved:[/green] {html_path}")

    console.print("\n[bold green]Done![/bold green]")
    console.print(f"Open the interactive graph: [bold]open {html_path}[/bold]")


if __name__ == "__main__":
    main()
