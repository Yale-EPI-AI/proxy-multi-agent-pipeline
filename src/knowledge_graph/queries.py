"""High-level query functions for the EPI knowledge graph."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .graph import EpiKnowledgeGraph
from .schema import EdgeType, Inference, NodeType


def get_proxies_for_indicator(
    graph: EpiKnowledgeGraph,
    tla: str,
    verdict_filter: Optional[str] = None,
    include_inferred: bool = False,
) -> list[dict]:
    """Get all proxies targeting a given indicator, with optional verdict filter."""
    indicator_id = f"indicator:{tla}"
    results = []

    edge_types = [EdgeType.PROXY_FOR]
    if include_inferred:
        edge_types.append(EdgeType.INFERRED_CANDIDATE)

    for et in edge_types:
        for proxy_id in graph.predecessors(indicator_id, edge_type=et):
            edge = graph.get_edge(proxy_id, indicator_id)
            proxy_node = graph.get_node(proxy_id)
            if edge is None:
                continue

            edge_dict = edge.model_dump()
            if verdict_filter and edge_dict.get("verdict") != verdict_filter:
                continue

            result = {"proxy_id": proxy_id, "edge_type": et.value}
            if proxy_node:
                result["proxy_variable"] = getattr(proxy_node, "proxy_variable", "")
                result["confidence"] = getattr(proxy_node, "confidence", "")
            result.update(edge_dict)
            results.append(result)

    return results


def get_cross_indicator_candidates(graph: EpiKnowledgeGraph, tla: str) -> list[dict]:
    """Get inferred candidate proxies for an indicator from reasoning."""
    indicator_id = f"indicator:{tla}"
    results = []
    for proxy_id in graph.predecessors(indicator_id, edge_type=EdgeType.INFERRED_CANDIDATE):
        edge = graph.get_edge(proxy_id, indicator_id)
        proxy_node = graph.get_node(proxy_id)
        if edge is None:
            continue
        result = {"proxy_id": proxy_id}
        if proxy_node:
            result["proxy_variable"] = getattr(proxy_node, "proxy_variable", "")
        result.update(edge.model_dump())
        results.append(result)
    return results


def get_contradictions(
    graph: EpiKnowledgeGraph,
    tla: Optional[str] = None,
    inferences: Optional[list[Inference]] = None,
) -> list[dict]:
    """Get direction conflicts, optionally filtered by indicator TLA."""
    if inferences is None:
        return []
    results = []
    for inf in inferences:
        if inf.inference_type != "direction_conflict":
            continue
        if tla and inf.details.get("indicator") != tla:
            continue
        results.append(inf.details)
    return results


def get_confounder_warnings(
    graph: EpiKnowledgeGraph,
    tla: Optional[str] = None,
    inferences: Optional[list[Inference]] = None,
) -> list[dict]:
    """Get confounder warnings, optionally filtered by indicator TLA."""
    if inferences is None:
        return []
    results = []
    for inf in inferences:
        if inf.inference_type != "confounder_warning":
            continue
        proxy_id = inf.details.get("proxy_id", "")
        # If filtering by TLA, check which indicator this proxy targets
        if tla:
            target_edges = graph.neighbors(f"proxy:{proxy_id}", edge_type=EdgeType.PROXY_FOR)
            if not any(t == f"indicator:{tla}" for t in target_edges):
                continue
        results.append(inf.details)
    return results


def get_coverage_gaps(
    graph: EpiKnowledgeGraph,
    inferences: Optional[list[Inference]] = None,
) -> list[str]:
    """Get TLAs of indicators with no proxy hypotheses."""
    if inferences is None:
        # Compute directly from graph
        gaps = []
        for nid, _ in graph.get_nodes_by_type(NodeType.INDICATOR):
            tla = nid.split(":", 1)[1]
            proxies = graph.predecessors(nid, edge_type=EdgeType.PROXY_FOR)
            if not proxies:
                gaps.append(tla)
        return sorted(gaps)

    return sorted([
        inf.details["tla"]
        for inf in inferences
        if inf.inference_type == "coverage_gap"
    ])


def get_indicator_coverage_summary(graph: EpiKnowledgeGraph) -> pd.DataFrame:
    """Per-indicator summary: # proxies, # confirmed, # rejected, etc."""
    rows = []
    for nid, node in graph.get_nodes_by_type(NodeType.INDICATOR):
        tla = nid.split(":", 1)[1]
        proxies = graph.predecessors(nid, edge_type=EdgeType.PROXY_FOR)
        inferred = graph.predecessors(nid, edge_type=EdgeType.INFERRED_CANDIDATE)

        verdicts: dict[str, int] = {}
        for pid in proxies:
            edge = graph.get_edge(pid, nid)
            if edge:
                v = getattr(edge, "verdict", "unknown") or "unknown"
                verdicts[v] = verdicts.get(v, 0) + 1

        rows.append({
            "tla": tla,
            "label": getattr(node, "label", ""),
            "issue_category": getattr(node, "issue_category", ""),
            "total_proxies": len(proxies),
            "confirmed": verdicts.get("confirmed", 0),
            "partially_confirmed": verdicts.get("partially_confirmed", 0),
            "inconclusive": verdicts.get("inconclusive", 0),
            "rejected": verdicts.get("rejected", 0),
            "inferred_candidates": len(inferred),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("total_proxies", ascending=False).reset_index(drop=True)
    return df


def get_shared_data_sources(
    graph: EpiKnowledgeGraph, tla1: str, tla2: str
) -> list[dict]:
    """Find data sources shared between proxies of two indicators."""
    sources1: set[str] = set()
    sources2: set[str] = set()

    for pid in graph.predecessors(f"indicator:{tla1}", edge_type=EdgeType.PROXY_FOR):
        for sid in graph.neighbors(pid, edge_type=EdgeType.MEASURED_BY):
            sources1.add(sid)

    for pid in graph.predecessors(f"indicator:{tla2}", edge_type=EdgeType.PROXY_FOR):
        for sid in graph.neighbors(pid, edge_type=EdgeType.MEASURED_BY):
            sources2.add(sid)

    shared = sources1 & sources2
    results = []
    for sid in shared:
        node = graph.get_node(sid)
        results.append({
            "source_id": sid,
            "organization": getattr(node, "organization", "") if node else "",
            "label": getattr(node, "label", "") if node else "",
        })
    return results


def get_graph_stats(graph: EpiKnowledgeGraph) -> dict:
    """Overall graph statistics."""
    summary = graph.summary()

    # Count unique indicators with at least one proxy
    indicators_with_proxies = set()
    for _, v, _ in graph.get_edges_by_type(EdgeType.PROXY_FOR):
        indicators_with_proxies.add(v)

    summary["indicators_with_proxies"] = len(indicators_with_proxies)
    summary["indicators_without_proxies"] = summary.get(f"node:{NodeType.INDICATOR.value}", 0) - len(indicators_with_proxies)

    return summary
