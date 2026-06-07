"""Export the EPI knowledge graph to JSON, GraphML, and Markdown."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from .graph import EpiKnowledgeGraph
from .queries import (
    get_coverage_gaps,
    get_graph_stats,
    get_indicator_coverage_summary,
)
from .schema import EdgeType, Inference, NodeType


def to_json(graph: EpiKnowledgeGraph) -> dict:
    """Full graph as node-link JSON (serializable dict)."""
    data = nx.node_link_data(graph.nx_graph)
    return data


def to_graphml(graph: EpiKnowledgeGraph, path: Path) -> None:
    """Export to GraphML for Gephi/Cytoscape. Flattens complex attributes."""
    g = graph.nx_graph.copy()

    # GraphML only supports scalar attributes — flatten lists/dicts
    for _, attrs in g.nodes(data=True):
        _flatten_attrs(attrs)
    for _, _, attrs in g.edges(data=True):
        _flatten_attrs(attrs)

    nx.write_graphml(g, str(path))


def to_summary_report(
    graph: EpiKnowledgeGraph,
    inferences: list[Inference] | None = None,
) -> str:
    """Human-readable Markdown summary of the knowledge graph."""
    lines: list[str] = []
    lines.append("# EPI Proxy Discovery Knowledge Graph — Summary Report\n")

    # Overall stats
    stats = get_graph_stats(graph)
    lines.append("## Graph Overview\n")
    lines.append(f"- **Total nodes**: {stats['total_nodes']}")
    lines.append(f"- **Total edges**: {stats['total_edges']}")
    lines.append(f"- **Indicators**: {stats.get(f'node:{NodeType.INDICATOR.value}', 0)}")
    lines.append(f"- **Proxy hypotheses**: {stats.get(f'node:{NodeType.PROXY_VARIABLE.value}', 0)}")
    lines.append(f"- **Data sources**: {stats.get(f'node:{NodeType.DATA_SOURCE.value}', 0)}")
    lines.append(f"- **Indicators with proxies**: {stats.get('indicators_with_proxies', 0)}")
    lines.append(f"- **Indicators without proxies**: {stats.get('indicators_without_proxies', 0)}")
    lines.append("")

    # Indicator coverage table
    lines.append("## Indicator Coverage\n")
    df = get_indicator_coverage_summary(graph)
    if not df.empty:
        # Only show indicators that have at least one proxy
        has_proxies = df[df["total_proxies"] > 0]
        if not has_proxies.empty:
            lines.append("### Indicators with Proxy Hypotheses\n")
            lines.append("| TLA | Indicator | Category | Total | Confirmed | Partial | Inconclusive | Rejected | Inferred |")
            lines.append("|-----|-----------|----------|-------|-----------|---------|--------------|----------|----------|")
            for _, row in has_proxies.iterrows():
                lines.append(
                    f"| {row['tla']} | {row['label'][:40]} | {row['issue_category']} | "
                    f"{row['total_proxies']} | {row['confirmed']} | {row['partially_confirmed']} | "
                    f"{row['inconclusive']} | {row['rejected']} | {row['inferred_candidates']} |"
                )
            lines.append("")

    # Coverage gaps
    gaps = get_coverage_gaps(graph)
    if gaps:
        lines.append(f"### Coverage Gaps ({len(gaps)} indicators with no proxies)\n")
        # Group by issue category
        gap_cats: dict[str, list[str]] = {}
        for tla in gaps:
            node = graph.get_node(f"indicator:{tla}")
            cat = getattr(node, "issue_category", "unknown") if node else "unknown"
            gap_cats.setdefault(cat, []).append(tla)
        for cat, tlas in sorted(gap_cats.items()):
            lines.append(f"- **{cat}**: {', '.join(tlas)}")
        lines.append("")

    # Reasoning results
    if inferences:
        lines.append("## Reasoning Results\n")

        cross = [i for i in inferences if i.inference_type == "cross_candidate"]
        if cross:
            lines.append(f"### Cross-Indicator Candidates ({len(cross)})\n")
            for inf in cross[:20]:  # cap for readability
                proxy_id = inf.source.split(":", 1)[1] if inf.source else ""
                target = inf.target.split(":", 1)[1] if inf.target else ""
                reason = inf.details.get("reason", "")
                conf = inf.edge.confidence if inf.edge else 0
                lines.append(f"- {proxy_id} → {target} ({reason}, confidence={conf:.2f})")
            if len(cross) > 20:
                lines.append(f"- ... and {len(cross) - 20} more")
            lines.append("")

        mismatches = [i for i in inferences if i.inference_type == "direction_mismatch"]
        if mismatches:
            lines.append(f"### Direction-Observation Mismatches ({len(mismatches)})\n")
            for inf in mismatches:
                d = inf.details
                lines.append(
                    f"- **{d.get('indicator', '')}**: {d.get('proxy', '')} — "
                    f"hypothesized {d.get('hypothesized_direction', '')} but observed r={d.get('observed_r', 0):.3f}"
                )
            lines.append("")

        vconflicts = [i for i in inferences if i.inference_type == "verdict_conflict"]
        if vconflicts:
            lines.append(f"### Same-Direction Verdict Conflicts ({len(vconflicts)})\n")
            for inf in vconflicts:
                d = inf.details
                lines.append(
                    f"- **{d.get('indicator', '')}**: {d.get('proxy1', '')} vs {d.get('proxy2', '')} "
                    f"(both {d.get('direction', '')}, but conflicting verdicts)"
                )
            lines.append("")

        warnings = [i for i in inferences if i.inference_type == "confounder_warning"]
        if warnings:
            lines.append(f"### Confounder Warnings ({len(warnings)})\n")
            for inf in warnings:
                pid = inf.details.get("proxy_id", "")
                lines.append(f"- {pid}: mechanism mentions confounder keywords, weak/missing partial correlation")
            lines.append("")

        shared = [i for i in inferences if i.inference_type == "shared_source"]
        if shared:
            lines.append(f"### Shared Source Opportunities ({len(shared)})\n")
            for inf in shared[:20]:
                src = inf.details.get("source", "")
                tgt = inf.details.get("target_tla", "")
                lines.append(f"- Source `{src}` → indicator {tgt}")
            if len(shared) > 20:
                lines.append(f"- ... and {len(shared) - 20} more")
            lines.append("")

    return "\n".join(lines)


def to_cytoscape_elements(graph: EpiKnowledgeGraph) -> list[dict]:
    """Convert graph to Cytoscape.js element format for web visualization."""
    elements = []

    for nid, attrs in graph.nx_graph.nodes(data=True):
        elements.append({
            "group": "nodes",
            "data": {"id": nid, "label": attrs.get("label", nid), **{k: v for k, v in attrs.items() if isinstance(v, (str, int, float, bool))}},
        })

    for u, v, attrs in graph.nx_graph.edges(data=True):
        elements.append({
            "group": "edges",
            "data": {"source": u, "target": v, **{k: v_val for k, v_val in attrs.items() if isinstance(v_val, (str, int, float, bool))}},
        })

    return elements


def _flatten_attrs(attrs: dict) -> None:
    """Flatten non-scalar attributes in-place for GraphML compatibility."""
    from enum import Enum
    for k in list(attrs.keys()):
        v = attrs[k]
        if v is None:
            attrs[k] = ""
        elif isinstance(v, Enum):
            attrs[k] = v.value
        elif isinstance(v, (list, dict)):
            attrs[k] = json.dumps(v)
