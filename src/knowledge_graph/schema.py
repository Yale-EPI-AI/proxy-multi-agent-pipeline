"""Node and edge type definitions for the EPI knowledge graph."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Node Types ────────────────────────────────────────────────────────────────


class NodeType(str, Enum):
    POLICY_OBJECTIVE = "policy_objective"
    ISSUE_CATEGORY = "issue_category"
    INDICATOR = "indicator"
    PROXY_VARIABLE = "proxy_variable"
    DATA_SOURCE = "data_source"


class NodeData(BaseModel):
    node_type: NodeType
    label: str
    description: str = ""
    metadata: dict = Field(default_factory=dict)


class IndicatorNode(NodeData):
    node_type: NodeType = NodeType.INDICATOR
    tla: str
    policy_objective: str
    issue_category: str
    units: str = ""
    raw_polarity: str = ""
    source_org: str = ""
    domain_knowledge: Optional[str] = None


class ProxyNode(NodeData):
    node_type: NodeType = NodeType.PROXY_VARIABLE
    hypothesis_id: str
    proxy_variable: str
    proxy_description: str = ""
    confidence: str = ""
    evidence_type: str = ""


class DataSourceNode(NodeData):
    node_type: NodeType = NodeType.DATA_SOURCE
    organization: str = ""
    url: str = ""
    accessibility: str = ""
    coverage: str = ""
    country_count_estimate: Optional[int] = None
    methodology_status: str = ""


# ── Edge Types ────────────────────────────────────────────────────────────────


class EdgeType(str, Enum):
    CONTAINS = "contains"
    PROXY_FOR = "proxy_for"
    MEASURED_BY = "measured_by"
    SAME_ISSUE_CATEGORY = "same_issue_category"
    SIBLING_INDICATOR = "sibling_indicator"
    INFERRED_CANDIDATE = "inferred_candidate"


class EdgeData(BaseModel):
    edge_type: EdgeType
    metadata: dict = Field(default_factory=dict)


class ProxyForEdge(EdgeData):
    edge_type: EdgeType = EdgeType.PROXY_FOR
    hypothesis_id: str = ""
    direction: str = ""
    functional_form: str = ""
    strength_estimate: str = ""
    mechanism: str = ""
    verdict: str = ""
    pearson_r: Optional[float] = None
    pearson_p: Optional[float] = None
    spearman_rho: Optional[float] = None
    n_observations: Optional[int] = None
    partial_r: Optional[float] = None
    best_functional_form: str = ""
    inclusion_score: Optional[int] = None
    validation_issues: list[str] = Field(default_factory=list)


class InferredCandidateEdge(EdgeData):
    edge_type: EdgeType = EdgeType.INFERRED_CANDIDATE
    rule_name: str = ""
    confidence: float = 0.0
    explanation: str = ""
    source_evidence: list[str] = Field(default_factory=list)


# ── Inference result container ────────────────────────────────────────────────


class Inference(BaseModel):
    """Result from the reasoning engine — an inferred edge or warning."""
    inference_type: str  # "cross_candidate", "direction_mismatch", "verdict_conflict", etc.
    source: str = ""
    target: str = ""
    edge: Optional[InferredCandidateEdge] = None
    details: dict = Field(default_factory=dict)


# ── Deserialization helpers ───────────────────────────────────────────────────

NODE_TYPE_MAP: dict[str, type[NodeData]] = {
    NodeType.POLICY_OBJECTIVE: NodeData,
    NodeType.ISSUE_CATEGORY: NodeData,
    NodeType.INDICATOR: IndicatorNode,
    NodeType.PROXY_VARIABLE: ProxyNode,
    NodeType.DATA_SOURCE: DataSourceNode,
}

EDGE_TYPE_MAP: dict[str, type[EdgeData]] = {
    EdgeType.CONTAINS: EdgeData,
    EdgeType.PROXY_FOR: ProxyForEdge,
    EdgeType.MEASURED_BY: EdgeData,
    EdgeType.SAME_ISSUE_CATEGORY: EdgeData,
    EdgeType.SIBLING_INDICATOR: EdgeData,
    EdgeType.INFERRED_CANDIDATE: InferredCandidateEdge,
}


def deserialize_node(attrs: dict) -> NodeData:
    """Reconstruct a typed NodeData from a NetworkX attrs dict."""
    nt = attrs.get("node_type", "")
    cls = NODE_TYPE_MAP.get(nt, NodeData)
    return cls.model_validate(attrs)


def deserialize_edge(attrs: dict) -> EdgeData:
    """Reconstruct a typed EdgeData from a NetworkX attrs dict."""
    et = attrs.get("edge_type", "")
    cls = EDGE_TYPE_MAP.get(et, EdgeData)
    return cls.model_validate(attrs)
