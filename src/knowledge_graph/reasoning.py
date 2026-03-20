"""clingo-based Answer Set Programming reasoning over the EPI knowledge graph."""

from __future__ import annotations

from typing import Optional

import clingo

from .graph import EpiKnowledgeGraph
from .schema import (
    EdgeType,
    Inference,
    InferredCandidateEdge,
    NodeType,
)

# Confounder keywords derived from control variable TLAs
_CONFOUNDER_KEYWORDS = ["gdp", "urbanization", "urban", "population", "income", "wealth"]

ASP_RULES = r"""
#program rules.

% ══════════════════════════════════════════════════════════════════
% Rule 1: Cross-indicator candidate transfer
% If proxy P is confirmed for indicator A, and B is a sibling/same-category
% indicator without P tested, then P is a candidate for B.
% ══════════════════════════════════════════════════════════════════
cross_candidate(P, B, "sibling", 800) :-
    proxy(P, A, _, "confirmed"), sibling(A, B),
    not has_proxy_for(P, B).
cross_candidate(P, B, "sibling", 800) :-
    proxy(P, A, _, "partially_confirmed"), sibling(A, B),
    not has_proxy_for(P, B).
cross_candidate(P, B, "same_category", 600) :-
    proxy(P, A, _, "confirmed"), same_category(A, B), A != B,
    not sibling(A, B), not has_proxy_for(P, B).

has_proxy_for(P, I) :- proxy(P, I, _, _).

% ══════════════════════════════════════════════════════════════════
% Rule 2: Directional consistency check
% Flag when two non-rejected proxies for the same indicator disagree on direction
% ══════════════════════════════════════════════════════════════════
direction_conflict(I, P1, P2, D1, D2) :-
    proxy(P1, I, D1, V1), proxy(P2, I, D2, V2),
    P1 < P2, D1 != D2,
    V1 != "rejected", V2 != "rejected",
    V1 != "inconclusive", V2 != "inconclusive".

% ══════════════════════════════════════════════════════════════════
% Rule 3: Confounder path detection
% Flag proxies whose mechanism mentions confounders AND partial corr is weak
% ══════════════════════════════════════════════════════════════════
confounder_warning(P) :-
    mechanism_mentions_confounder(P),
    partial_r(P, PR), PR < 300, PR > -300.
confounder_warning(P) :-
    mechanism_mentions_confounder(P),
    not partial_r(P, _).

% ══════════════════════════════════════════════════════════════════
% Rule 4: Coverage gap detection
% Find indicators with no proxy hypotheses at all
% ══════════════════════════════════════════════════════════════════
has_any_proxy(I) :- proxy(_, I, _, _).
coverage_gap(I) :- indicator(I, _, _), not has_any_proxy(I).

% ══════════════════════════════════════════════════════════════════
% Rule 5: Shared data source opportunities
% If source S confirmed for indicator A, suggest S for sibling B
% ══════════════════════════════════════════════════════════════════
shared_source_candidate(S, B) :-
    source(P, S), proxy(P, A, _, "confirmed"),
    sibling(A, B), not source_used_for(S, B).
source_used_for(S, I) :- source(P, S), proxy(P, I, _, _).

% Show directives
#show cross_candidate/4.
#show direction_conflict/5.
#show confounder_warning/1.
#show coverage_gap/1.
#show shared_source_candidate/2.
"""


class ReasoningEngine:
    """Bridge between EpiKnowledgeGraph and clingo ASP solver."""

    def __init__(self, graph: EpiKnowledgeGraph) -> None:
        self.graph = graph

    def run(self) -> list[Inference]:
        """Generate facts from graph, run ASP rules, extract inferences."""
        ctl = clingo.Control(["0"])  # enumerate all answer sets

        # Add facts as a base program
        facts = self._generate_facts()
        ctl.add("base", [], facts)

        # Add rules
        ctl.add("rules", [], ASP_RULES)

        ctl.ground([("base", []), ("rules", [])])
        return self._extract_inferences(ctl)

    def _generate_facts(self) -> str:
        """Translate the knowledge graph into ASP fact strings."""
        lines: list[str] = []

        # Indicator facts
        for nid, node in self.graph.get_nodes_by_type(NodeType.INDICATOR):
            tla = nid.split(":", 1)[1]
            ic = getattr(node, "issue_category", "")
            po = getattr(node, "policy_objective", "")
            lines.append(f'indicator("{tla}", "{ic}", "{po}").')

        # Same-category edges
        for u, v, _ in self.graph.get_edges_by_type(EdgeType.SAME_ISSUE_CATEGORY):
            a = u.split(":", 1)[1]
            b = v.split(":", 1)[1]
            lines.append(f'same_category("{a}", "{b}").')

        # Sibling edges
        for u, v, _ in self.graph.get_edges_by_type(EdgeType.SIBLING_INDICATOR):
            a = u.split(":", 1)[1]
            b = v.split(":", 1)[1]
            lines.append(f'sibling("{a}", "{b}").')

        # Proxy facts from proxy_for edges
        for u, v, edge in self.graph.get_edges_by_type(EdgeType.PROXY_FOR):
            proxy_id = u.split(":", 1)[1]  # e.g. "UWD-H01"
            target_tla = v.split(":", 1)[1]
            direction = getattr(edge, "direction", "unknown")
            verdict = getattr(edge, "verdict", "inconclusive")
            lines.append(f'proxy("{proxy_id}", "{target_tla}", "{direction}", "{verdict}").')

            # Correlation (scaled to int * 1000)
            pearson_r = getattr(edge, "pearson_r", None)
            if pearson_r is not None:
                lines.append(f'correlation("{proxy_id}", {int(pearson_r * 1000)}).')

            # Partial correlation
            partial_r = getattr(edge, "partial_r", None)
            if partial_r is not None:
                lines.append(f'partial_r("{proxy_id}", {int(partial_r * 1000)}).')

            # N observations
            n_obs = getattr(edge, "n_observations", None)
            if n_obs is not None:
                lines.append(f'n_obs("{proxy_id}", {n_obs}).')

            # Proxy name for transitive matching
            proxy_node = self.graph.get_node(u)
            if proxy_node:
                pname = getattr(proxy_node, "proxy_variable", "")
                if pname:
                    safe_name = pname.replace('"', '\\"')[:80]
                    lines.append(f'proxy_name("{proxy_id}", "{safe_name}").')

        # Source facts
        for u, v, _ in self.graph.get_edges_by_type(EdgeType.MEASURED_BY):
            proxy_id = u.split(":", 1)[1]
            source_id = v.split(":", 1)[1]
            lines.append(f'source("{proxy_id}", "{source_id}").')

        # Mechanism confounder scanning (done in Python)
        for u, v, edge in self.graph.get_edges_by_type(EdgeType.PROXY_FOR):
            proxy_id = u.split(":", 1)[1]
            mechanism = getattr(edge, "mechanism", "").lower()
            if any(kw in mechanism for kw in _CONFOUNDER_KEYWORDS):
                lines.append(f'mechanism_mentions_confounder("{proxy_id}").')

        return "\n".join(lines)

    def _extract_inferences(self, ctl: clingo.Control) -> list[Inference]:
        """Parse clingo answer set atoms into Inference objects."""
        inferences: list[Inference] = []

        with ctl.solve(yield_=True) as handle:
            for model in handle:
                for atom in model.symbols(shown=True):
                    inf = self._atom_to_inference(atom)
                    if inf:
                        inferences.append(inf)

        return inferences

    def _atom_to_inference(self, atom: clingo.Symbol) -> Optional[Inference]:
        """Convert a single clingo atom to an Inference."""
        name = atom.name
        args = atom.arguments

        if name == "cross_candidate":
            proxy_id = args[0].string
            target_tla = args[1].string
            reason = args[2].string
            confidence = args[3].number / 1000
            return Inference(
                inference_type="cross_candidate",
                source=f"proxy:{proxy_id}",
                target=f"indicator:{target_tla}",
                edge=InferredCandidateEdge(
                    rule_name="cross_indicator_transfer",
                    confidence=confidence,
                    explanation=f"Proxy {proxy_id} confirmed/partially confirmed for {reason} indicator; untested for {target_tla}",
                    source_evidence=[proxy_id],
                ),
                details={"reason": reason},
            )

        elif name == "direction_conflict":
            indicator = args[0].string
            p1 = args[1].string
            p2 = args[2].string
            d1 = args[3].string
            d2 = args[4].string
            return Inference(
                inference_type="direction_conflict",
                source=f"proxy:{p1}",
                target=f"proxy:{p2}",
                details={
                    "indicator": indicator,
                    "proxy1": p1, "direction1": d1,
                    "proxy2": p2, "direction2": d2,
                },
            )

        elif name == "confounder_warning":
            proxy_id = args[0].string
            return Inference(
                inference_type="confounder_warning",
                source=f"proxy:{proxy_id}",
                details={"proxy_id": proxy_id},
            )

        elif name == "coverage_gap":
            tla = args[0].string
            return Inference(
                inference_type="coverage_gap",
                target=f"indicator:{tla}",
                details={"tla": tla},
            )

        elif name == "shared_source_candidate":
            source_id = args[0].string
            target_tla = args[1].string
            return Inference(
                inference_type="shared_source",
                source=f"source:{source_id}",
                target=f"indicator:{target_tla}",
                details={"source": source_id, "target_tla": target_tla},
            )

        return None


def run_reasoning(graph: EpiKnowledgeGraph) -> list[Inference]:
    """Run the reasoning engine and add inferred edges to the graph."""
    engine = ReasoningEngine(graph)
    inferences = engine.run()

    # Add inferred candidate edges to the graph
    for inf in inferences:
        if inf.edge and inf.source and inf.target:
            graph.add_edge(inf.source, inf.target, inf.edge)

    return inferences
