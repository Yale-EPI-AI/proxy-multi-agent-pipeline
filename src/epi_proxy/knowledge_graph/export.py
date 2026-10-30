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
        has_proxies = df[df["total_proxies"] > 0]
        if not has_proxies.empty:
            lines.append("### Indicators with Proxy Hypotheses\n")
            lines.append("| TLA | Indicator | Category | Total | Confirmed | Partial | Inconclusive | Rejected | Inferred |")
            lines.append("|-----|-----------|----------|-------|-----------|---------|--------------|----------|----------|")
            for _, row in has_proxies.iterrows():
                lines.append(
                    f"| {row['tla']} | {row['label']} | {row['issue_category']} | "
                    f"{row['total_proxies']} | {row['confirmed']} | {row['partially_confirmed']} | "
                    f"{row['inconclusive']} | {row['rejected']} | {row['inferred_candidates']} |"
                )
            lines.append("")

    # Coverage gaps
    gaps = get_coverage_gaps(graph)
    if gaps:
        lines.append(f"### Coverage Gaps ({len(gaps)} indicators with no proxies)\n")
        gap_cats: dict[str, list[str]] = {}
        for tla in gaps:
            node = graph.get_node(f"indicator:{tla}")
            cat = getattr(node, "issue_category", "unknown") if node else "unknown"
            gap_cats.setdefault(cat, []).append(tla)
        for cat, tlas in sorted(gap_cats.items()):
            lines.append(f"- **{cat}**: {', '.join(tlas)}")
        lines.append("")

    # Detailed inventory of all proxies grouped by indicator
    lines.append("## Detailed Proxy Inventory by Indicator\n")
    tla_nodes = sorted([
        nid for nid, attrs in graph.nx_graph.nodes(data=True)
        if attrs.get("node_type") == NodeType.INDICATOR.value
    ])
    for ind_id in tla_nodes:
        ind_node = graph.get_node(ind_id)
        tla = ind_id.split(":", 1)[1]
        label = getattr(ind_node, "label", tla) if ind_node else tla

        proxies_data = []
        for u, v, edge in graph.get_edges_by_type(EdgeType.PROXY_FOR):
            if v == ind_id:
                p_node = graph.get_node(u)
                proxies_data.append((u, p_node, edge))

        if not proxies_data:
            continue

        lines.append(f"### {tla} — {label}\n")
        lines.append("| Proxy ID | Variable Name | Verdict | Models | Pearson r | Partial r | Best Form |")
        lines.append("|----------|---------------|---------|--------|-----------|-----------|-----------|")
        for p_id, p_node, edge in proxies_data:
            var_name = getattr(p_node, "proxy_variable", "") if p_node else ""
            v = getattr(edge, "consensus_verdict", getattr(edge, "verdict", ""))
            models = getattr(edge, "models", [])
            m_str = ", ".join(models) if models else "default"
            pr = getattr(edge, "pearson_r", None)
            pr_str = f"{pr:.3f}" if pr is not None else "-"
            par = getattr(edge, "partial_r", None)
            par_str = f"{par:.3f}" if par is not None else "-"
            form = getattr(edge, "best_functional_form", getattr(edge, "functional_form", "-")) or "-"
            lines.append(f"| `{p_id}` | {var_name} | {v} | {m_str} | {pr_str} | {par_str} | {form} |")
        lines.append("")

    # Reasoning results
    if inferences:
        lines.append("## Reasoning Results\n")

        # 1. Multi-Model Consensus
        consensus = [i for i in inferences if i.inference_type == "multi_model_consensus"]
        if consensus:
            lines.append(f"### Multi-Model Consensus ({len(consensus)})\n")
            lines.append("Proxies independently confirmed by >= 2 distinct models:\n")
            lines.append("| Target TLA | Proxy ID |")
            lines.append("|------------|----------|")
            for inf in consensus:
                pid = inf.details.get("proxy_id", "")
                tla = inf.details.get("target_tla", "")
                lines.append(f"| **{tla}** | `{pid}` |")
            lines.append("")

        # 2. Inter-Model Verdict Contradictions
        mconflicts = [i for i in inferences if i.inference_type == "inter_model_conflict"]
        if mconflicts:
            lines.append(f"### Inter-Model Verdict Contradictions ({len(mconflicts)})\n")
            lines.append("Same proxy confirmed by one model but rejected by another:\n")
            lines.append("| Target TLA | Proxy ID | Confirming Model | Rejecting Model |")
            lines.append("|------------|----------|------------------|-----------------|")
            for inf in mconflicts:
                d = inf.details
                lines.append(f"| **{d.get('target_tla', '')}** | `{d.get('proxy_id', '')}` | {d.get('confirming_model', '')} | {d.get('rejecting_model', '')} |")
            lines.append("")

        # 3. Inter-Model Directional Conflicts
        dirconflicts = [i for i in inferences if i.inference_type == "directional_conflict"]
        if dirconflicts:
            lines.append(f"### Inter-Model Directional Conflicts ({len(dirconflicts)})\n")
            lines.append("Models posited opposing physical/causal directions:\n")
            lines.append("| Target TLA | Proxy ID | Model 1 (Direction) | Model 2 (Direction) |")
            lines.append("|------------|----------|---------------------|---------------------|")
            for inf in dirconflicts:
                d = inf.details
                lines.append(
                    f"| **{d.get('target_tla', '')}** | `{d.get('proxy_id', '')}` | {d.get('model1', '')} ({d.get('direction1', '')}) | {d.get('model2', '')} ({d.get('direction2', '')}) |"
                )
            lines.append("")

        # 4. Unique Model Discoveries
        uniques = [i for i in inferences if i.inference_type == "unique_model_discovery"]
        if uniques:
            lines.append(f"### Unique Model Discoveries ({len(uniques)})\n")
            lines.append("Confirmed proxies discovered exclusively by a single model:\n")
            lines.append("| Target TLA | Proxy ID | Exclusive Model |")
            lines.append("|------------|----------|-----------------|")
            for inf in uniques:
                d = inf.details
                lines.append(f"| **{d.get('target_tla', '')}** | `{d.get('proxy_id', '')}` | {d.get('model', '')} |")
            lines.append("")

        # 5. Cross-Indicator Candidates
        cross = [i for i in inferences if i.inference_type == "cross_candidate"]
        if cross:
            lines.append(f"### Cross-Indicator Candidates ({len(cross)})\n")
            lines.append("| Source Proxy | Target TLA | Transfer Reason | Confidence |")
            lines.append("|--------------|------------|-----------------|------------|")
            for inf in cross:
                proxy_id = inf.source.split(":", 1)[1] if inf.source else ""
                target = inf.target.split(":", 1)[1] if inf.target else ""
                reason = inf.details.get("reason", "")
                conf = inf.edge.confidence if inf.edge else 0
                lines.append(f"| `{proxy_id}` | **{target}** | {reason} | {conf:.2f} |")
            lines.append("")

        # 6. Direction-Observation Mismatches
        mismatches = [i for i in inferences if i.inference_type == "direction_mismatch"]
        if mismatches:
            lines.append(f"### Direction-Observation Mismatches ({len(mismatches)})\n")
            lines.append("| Indicator | Proxy ID | Hypothesized Direction | Observed Pearson r |")
            lines.append("|-----------|----------|------------------------|--------------------|")
            for inf in mismatches:
                d = inf.details
                lines.append(
                    f"| **{d.get('indicator', '')}** | `{d.get('proxy', '')}` | {d.get('hypothesized_direction', '')} | {d.get('observed_r', 0):.3f} |"
                )
            lines.append("")

        # 7. Same-Direction Verdict Conflicts
        vconflicts = [i for i in inferences if i.inference_type == "verdict_conflict"]
        if vconflicts:
            lines.append(f"### Same-Direction Verdict Conflicts ({len(vconflicts)})\n")
            lines.append("| Indicator | Confirmed Proxy | Rejected Proxy | Hypothesized Direction |")
            lines.append("|-----------|-----------------|----------------|------------------------|")
            for inf in vconflicts:
                d = inf.details
                lines.append(
                    f"| **{d.get('indicator', '')}** | `{d.get('proxy1', '')}` | `{d.get('proxy2', '')}` | {d.get('direction', '')} |"
                )
            lines.append("")

        # 8. Confounder Warnings
        warnings = [i for i in inferences if i.inference_type == "confounder_warning"]
        if warnings:
            lines.append(f"### Confounder Warnings ({len(warnings)})\n")
            lines.append("Proxies where mechanisms mention GDP/population but partial correlation collapses or is missing:\n")
            lines.append("| Proxy ID |")
            lines.append("|----------|")
            for inf in warnings:
                pid = inf.details.get("proxy_id", "")
                lines.append(f"| `{pid}` |")
            lines.append("")

        # 9. Shared Source Opportunities
        shared = [i for i in inferences if i.inference_type == "shared_source"]
        if shared:
            lines.append(f"### Shared Source Opportunities ({len(shared)})\n")
            lines.append("| Data Source | Target TLA |")
            lines.append("|-------------|------------|")
            for inf in shared:
                src = inf.details.get("source", "")
                tgt = inf.details.get("target_tla", "")
                lines.append(f"| `{src}` | **{tgt}** |")
            lines.append("")

    return "\n".join(lines)


def to_cytoscape_elements(graph: EpiKnowledgeGraph) -> list[dict]:
    """Convert graph to Cytoscape.js element format for web visualization."""
    elements = []

    for nid, attrs in graph.nx_graph.nodes(data=True):
        node_data = {
            "id": nid,
            "label": attrs.get("label", nid),
            **{k: v for k, v in attrs.items() if isinstance(v, (str, int, float, bool))},
        }
        if "models" in attrs and isinstance(attrs["models"], list):
            node_data["models"] = attrs["models"]
            node_data["models_str"] = ", ".join(attrs["models"])
        elements.append({
            "group": "nodes",
            "data": node_data,
        })

    for u, v, attrs in graph.nx_graph.edges(data=True):
        edge_data = {
            "source": u,
            "target": v,
            **{k: v_val for k, v_val in attrs.items() if isinstance(v_val, (str, int, float, bool))},
        }
        if "models" in attrs and isinstance(attrs["models"], list):
            edge_data["models"] = attrs["models"]
            edge_data["models_str"] = ", ".join(attrs["models"])
        elements.append({
            "group": "edges",
            "data": edge_data,
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
