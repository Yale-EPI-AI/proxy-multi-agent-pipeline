"""Build an EpiKnowledgeGraph from pipeline results, CSV hierarchy, and domain knowledge."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from src.config import MASTER_VARIABLE_LIST, OUTPUTS_DIR
from src.domain_knowledge import DOMAIN_KNOWLEDGE
from src.schemas import PipelineResult
from src.utils.data_utils import get_available_indicators

from .graph import EpiKnowledgeGraph
from .schema import (
    DataSourceNode,
    EdgeData,
    EdgeType,
    IndicatorNode,
    NodeData,
    NodeType,
    ProxyForEdge,
    ProxyNode,
)

# Map CSV PolicyObjective values to friendly names
_POLICY_OBJECTIVE_LABELS = {
    "Health": "Environmental Health",
    "Ecosystem": "Ecosystem Vitality",
    "Climate": "Climate Change",
}

# Map CSV IssueCategory codes to friendly names
_ISSUE_CATEGORY_LABELS = {
    "AirQuality": "Air Quality",
    "WaterQuality": "Sanitation & Drinking Water",
    "HeavyMetals": "Heavy Metals",
    "WasteManagement": "Waste Management",
    "AirPollution": "Air Pollution",
    "Agriculture": "Agriculture",
    "Biodiversity": "Biodiversity & Habitat",
    "EcoSvcs": "Forests",
    "Fisheries": "Fisheries",
    "WaterResources": "Water Resources",
    "Climate": "Climate Change Mitigation",
}


class GraphBuilder:
    """Construct an EpiKnowledgeGraph from all available data sources."""

    def __init__(self, outputs_dir: Path | None = None) -> None:
        self.outputs_dir = outputs_dir or OUTPUTS_DIR
        self.kg = EpiKnowledgeGraph()
        self._source_nodes: dict[str, str] = {}  # normalized org name → node_id

    def build(self) -> EpiKnowledgeGraph:
        """Run the full build sequence and return the graph."""
        self._load_epi_hierarchy()
        self._load_domain_knowledge()
        self._load_sibling_edges()
        self._load_pipeline_results()
        return self.kg

    # ── 3a. EPI hierarchy from master_variable_list.csv ───────────────────

    def _load_epi_hierarchy(self) -> None:
        df = pd.read_csv(MASTER_VARIABLE_LIST)
        indicators = df[df["Type"] == "Indicator"]

        # Create policy objective nodes
        for po_code, po_label in _POLICY_OBJECTIVE_LABELS.items():
            node_id = f"objective:{po_code}"
            self.kg.add_node(node_id, NodeData(
                node_type=NodeType.POLICY_OBJECTIVE,
                label=po_label,
                description=f"EPI policy objective: {po_label}",
            ))

        # Create issue category nodes + CONTAINS edges from objectives
        seen_categories: set[str] = set()
        for _, row in indicators.iterrows():
            ic_code = str(row["IssueCategory"])
            po_code = str(row["PolicyObjective"])
            if ic_code in seen_categories:
                continue
            seen_categories.add(ic_code)

            ic_label = _ISSUE_CATEGORY_LABELS.get(ic_code, ic_code)
            ic_id = f"category:{ic_code}"
            self.kg.add_node(ic_id, NodeData(
                node_type=NodeType.ISSUE_CATEGORY,
                label=ic_label,
                description=f"EPI issue category: {ic_label}",
            ))
            self.kg.add_edge(
                f"objective:{po_code}", ic_id,
                EdgeData(edge_type=EdgeType.CONTAINS),
            )

        # Create indicator nodes + CONTAINS edges from categories
        for _, row in indicators.iterrows():
            tla = str(row["Abbreviation"])
            ic_code = str(row["IssueCategory"])
            po_code = str(row["PolicyObjective"])

            ind_id = f"indicator:{tla}"
            self.kg.add_node(ind_id, IndicatorNode(
                label=str(row["Variable"]),
                description=str(row.get("Description", "")),
                tla=tla,
                policy_objective=po_code,
                issue_category=ic_code,
                units=str(row.get("Units", "")),
                raw_polarity=str(row.get("RawPolarity", "")),
                source_org=str(row.get("Source", "")),
            ))
            self.kg.add_edge(
                f"category:{ic_code}", ind_id,
                EdgeData(edge_type=EdgeType.CONTAINS),
            )

        # SAME_ISSUE_CATEGORY edges between all indicators in each category
        cat_indicators: dict[str, list[str]] = {}
        for _, row in indicators.iterrows():
            ic = str(row["IssueCategory"])
            tla = str(row["Abbreviation"])
            cat_indicators.setdefault(ic, []).append(tla)

        for tlas in cat_indicators.values():
            for i, a in enumerate(tlas):
                for b in tlas[i + 1:]:
                    self.kg.add_edge(
                        f"indicator:{a}", f"indicator:{b}",
                        EdgeData(edge_type=EdgeType.SAME_ISSUE_CATEGORY),
                    )
                    self.kg.add_edge(
                        f"indicator:{b}", f"indicator:{a}",
                        EdgeData(edge_type=EdgeType.SAME_ISSUE_CATEGORY),
                    )

    # ── 3b. Domain knowledge attachment ───────────────────────────────────

    def _load_domain_knowledge(self) -> None:
        for tla, text in DOMAIN_KNOWLEDGE.items():
            node_id = f"indicator:{tla}"
            node = self.kg.get_node(node_id)
            if node is None:
                continue
            # Update the node's domain_knowledge field
            attrs = dict(self.kg.nx_graph.nodes[node_id])
            attrs["domain_knowledge"] = text
            self.kg.nx_graph.nodes[node_id].update(attrs)

    # ── 3c. Sibling edges from domain knowledge text ─────────────────────

    def _load_sibling_edges(self) -> None:
        for tla, text in DOMAIN_KNOWLEDGE.items():
            match = re.search(r"Sibling indicators:\s*(.+?)(?:Weight:|$)", text)
            if not match:
                continue
            sibling_tlas = re.findall(r"[A-Z]{3}", match.group(1))
            for sib in sibling_tlas:
                src = f"indicator:{tla}"
                dst = f"indicator:{sib}"
                # Only add if both nodes exist and edge doesn't already exist
                if self.kg.get_node(src) and self.kg.get_node(dst):
                    if not self.kg.get_edge(src, dst) or self.kg.get_edge(src, dst).edge_type != EdgeType.SIBLING_INDICATOR:
                        self.kg.add_edge(src, dst, EdgeData(edge_type=EdgeType.SIBLING_INDICATOR))
                    if not self.kg.get_edge(dst, src) or self.kg.get_edge(dst, src).edge_type != EdgeType.SIBLING_INDICATOR:
                        self.kg.add_edge(dst, src, EdgeData(edge_type=EdgeType.SIBLING_INDICATOR))

    # ── 3d. Pipeline results ──────────────────────────────────────────────

    def _load_pipeline_results(self) -> None:
        # Get known indicator TLAs
        known_tlas = {ind["Abbreviation"] for ind in get_available_indicators()}

        for result_path in sorted(self.outputs_dir.glob("*/pipeline_result.json")):
            dir_name = result_path.parent.name
            if dir_name not in known_tlas:
                continue

            with open(result_path) as f:
                raw = json.load(f)
            pipeline = PipelineResult.model_validate(raw)

            if not pipeline.research_output:
                continue

            # Build lookup for verification results
            verif_map = {vr.hypothesis_id: vr for vr in pipeline.verification_results}

            for hyp in pipeline.research_output.hypotheses:
                # Create proxy node
                proxy_id = f"proxy:{hyp.id}"
                self.kg.add_node(proxy_id, ProxyNode(
                    label=hyp.proxy_variable,
                    description=hyp.proxy_description,
                    hypothesis_id=hyp.id,
                    proxy_variable=hyp.proxy_variable,
                    proxy_description=hyp.proxy_description,
                    confidence=hyp.confidence.value if hyp.confidence else "",
                    evidence_type=hyp.evidence_type.value if hyp.evidence_type else "",
                ))

                # Build proxy_for edge with full statistical evidence
                vr = verif_map.get(hyp.id)
                edge_kwargs: dict = {
                    "hypothesis_id": hyp.id,
                    "direction": hyp.relationship.direction.value if hyp.relationship.direction else "",
                    "functional_form": hyp.relationship.functional_form.value if hyp.relationship.functional_form else "",
                    "strength_estimate": hyp.relationship.strength_estimate or "",
                    "mechanism": hyp.mechanism,
                }

                if vr:
                    edge_kwargs["verdict"] = vr.verdict.value if vr.verdict else ""
                    if vr.raw_correlation:
                        edge_kwargs["pearson_r"] = vr.raw_correlation.pearson_r
                        edge_kwargs["pearson_p"] = vr.raw_correlation.pearson_p
                        edge_kwargs["spearman_rho"] = vr.raw_correlation.spearman_rho
                        edge_kwargs["n_observations"] = vr.raw_correlation.n_observations
                    if vr.partial_correlation:
                        edge_kwargs["partial_r"] = vr.partial_correlation.partial_r
                    if vr.functional_form:
                        edge_kwargs["best_functional_form"] = vr.functional_form.best_form.value if vr.functional_form.best_form else ""
                    if vr.validation:
                        edge_kwargs["validation_issues"] = vr.validation.issues
                        if vr.validation.inclusion_score:
                            edge_kwargs["inclusion_score"] = vr.validation.inclusion_score.criteria_met

                self.kg.add_edge(
                    proxy_id, f"indicator:{hyp.target_variable}",
                    ProxyForEdge(**edge_kwargs),
                )

                # Create / deduplicate data source node
                ds = hyp.data_source
                if ds and ds.organization:
                    source_key = ds.organization.lower().strip()
                    if source_key not in self._source_nodes:
                        source_id = f"source:{source_key.replace(' ', '_')}"
                        self._source_nodes[source_key] = source_id
                        self.kg.add_node(source_id, DataSourceNode(
                            label=ds.name,
                            description=f"Data from {ds.organization}",
                            organization=ds.organization,
                            url=ds.url or "",
                            accessibility=ds.accessibility.value if ds.accessibility else "",
                            coverage=ds.coverage or "",
                            country_count_estimate=ds.country_count_estimate,
                            methodology_status=ds.methodology_status.value if ds.methodology_status else "",
                        ))

                    self.kg.add_edge(
                        proxy_id, self._source_nodes[source_key],
                        EdgeData(edge_type=EdgeType.MEASURED_BY),
                    )
