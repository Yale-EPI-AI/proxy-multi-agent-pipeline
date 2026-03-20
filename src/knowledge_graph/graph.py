"""Core EpiKnowledgeGraph class wrapping a NetworkX DiGraph with typed nodes/edges."""

from __future__ import annotations

from typing import Optional

import networkx as nx

from .schema import (
    EdgeData,
    EdgeType,
    NodeData,
    NodeType,
    deserialize_edge,
    deserialize_node,
)


class EpiKnowledgeGraph:
    """Thin typed wrapper around nx.DiGraph for EPI proxy discovery."""

    def __init__(self) -> None:
        self._graph = nx.DiGraph()

    # ── Node operations ───────────────────────────────────────────────────

    def add_node(self, node_id: str, data: NodeData) -> None:
        self._graph.add_node(node_id, **data.model_dump())

    def get_node(self, node_id: str) -> Optional[NodeData]:
        if node_id not in self._graph:
            return None
        return deserialize_node(dict(self._graph.nodes[node_id]))

    def get_nodes_by_type(self, node_type: NodeType) -> list[tuple[str, NodeData]]:
        results = []
        for nid, attrs in self._graph.nodes(data=True):
            if attrs.get("node_type") == node_type:
                results.append((nid, deserialize_node(dict(attrs))))
        return results

    # ── Edge operations ───────────────────────────────────────────────────

    def add_edge(self, source: str, target: str, data: EdgeData) -> None:
        self._graph.add_edge(source, target, **data.model_dump())

    def get_edge(self, source: str, target: str) -> Optional[EdgeData]:
        if not self._graph.has_edge(source, target):
            return None
        return deserialize_edge(dict(self._graph.edges[source, target]))

    def get_edges_by_type(self, edge_type: EdgeType) -> list[tuple[str, str, EdgeData]]:
        results = []
        for u, v, attrs in self._graph.edges(data=True):
            if attrs.get("edge_type") == edge_type:
                results.append((u, v, deserialize_edge(dict(attrs))))
        return results

    # ── Traversal ─────────────────────────────────────────────────────────

    def neighbors(self, node_id: str, edge_type: Optional[EdgeType] = None) -> list[str]:
        if node_id not in self._graph:
            return []
        if edge_type is None:
            return list(self._graph.successors(node_id))
        return [
            v for v in self._graph.successors(node_id)
            if self._graph.edges[node_id, v].get("edge_type") == edge_type
        ]

    def predecessors(self, node_id: str, edge_type: Optional[EdgeType] = None) -> list[str]:
        if node_id not in self._graph:
            return []
        if edge_type is None:
            return list(self._graph.predecessors(node_id))
        return [
            u for u in self._graph.predecessors(node_id)
            if self._graph.edges[u, node_id].get("edge_type") == edge_type
        ]

    # ── Summary ───────────────────────────────────────────────────────────

    def summary(self) -> dict[str, int]:
        """Counts by node type and edge type."""
        counts: dict[str, int] = {"total_nodes": self._graph.number_of_nodes(), "total_edges": self._graph.number_of_edges()}
        for nt in NodeType:
            counts[f"node:{nt.value}"] = sum(
                1 for _, d in self._graph.nodes(data=True) if d.get("node_type") == nt
            )
        for et in EdgeType:
            counts[f"edge:{et.value}"] = sum(
                1 for _, _, d in self._graph.edges(data=True) if d.get("edge_type") == et
            )
        return counts

    @property
    def nx_graph(self) -> nx.DiGraph:
        """Escape hatch for direct NetworkX access."""
        return self._graph
