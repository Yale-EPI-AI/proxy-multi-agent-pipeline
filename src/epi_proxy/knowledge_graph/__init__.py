"""EPI Proxy Discovery Knowledge Graph — public API."""

from .builder import GraphBuilder
from .export import to_cytoscape_elements, to_graphml, to_json, to_summary_report
from .visualize import generate_html
from .graph import EpiKnowledgeGraph
from .queries import (
    get_confounder_warnings,
    get_direction_mismatches,
    get_verdict_conflicts,
    get_coverage_gaps,
    get_cross_indicator_candidates,
    get_graph_stats,
    get_indicator_coverage_summary,
    get_proxies_for_indicator,
    get_shared_data_sources,
)
from .reasoning import run_reasoning
from .schema import (
    DataSourceNode,
    EdgeData,
    EdgeType,
    IndicatorNode,
    Inference,
    InferredCandidateEdge,
    NodeData,
    NodeType,
    ProxyForEdge,
    ProxyNode,
)

__all__ = [
    "EpiKnowledgeGraph",
    "GraphBuilder",
    "run_reasoning",
    # Schema
    "NodeType",
    "NodeData",
    "IndicatorNode",
    "ProxyNode",
    "DataSourceNode",
    "EdgeType",
    "EdgeData",
    "ProxyForEdge",
    "InferredCandidateEdge",
    "Inference",
    # Queries
    "get_proxies_for_indicator",
    "get_cross_indicator_candidates",
    "get_direction_mismatches",
    "get_verdict_conflicts",
    "get_confounder_warnings",
    "get_coverage_gaps",
    "get_indicator_coverage_summary",
    "get_shared_data_sources",
    "get_graph_stats",
    # Export
    "to_json",
    "to_graphml",
    "to_summary_report",
    "to_cytoscape_elements",
    "generate_html",
]
