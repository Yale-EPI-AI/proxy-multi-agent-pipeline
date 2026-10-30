"""Build an EpiKnowledgeGraph from pipeline results, CSV hierarchy, and domain knowledge."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from epi_proxy.config import MASTER_VARIABLE_LIST, OUTPUTS_DIR
from epi_proxy.domain_knowledge import DOMAIN_KNOWLEDGE
from epi_proxy.schemas import PipelineResult
from epi_proxy.utils.data_utils import get_available_indicators

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

    def __init__(
        self,
        outputs_dir: Path | None = None,
        root_dir: Path | None = None,
        multi_model: bool = False,
    ) -> None:
        self.outputs_dir = outputs_dir or OUTPUTS_DIR
        self.root_dir = root_dir
        self.multi_model = multi_model or (root_dir is not None)
        self.kg = EpiKnowledgeGraph()
        self._source_nodes: dict[str, str] = {}  # normalized org name → node_id
        self.model_names: list[str] = []

    def build(self) -> EpiKnowledgeGraph:
        """Run the full build sequence and return the graph."""
        self._load_epi_hierarchy()
        self._load_domain_knowledge()
        self._load_sibling_edges()
        if self.multi_model:
            self._load_multi_model_pipeline_results()
        else:
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

                clean_target = hyp.target_variable.replace("epi:", "").strip().upper()
                if clean_target not in known_tlas:
                    clean_target = dir_name

                self.kg.add_edge(
                    proxy_id, f"indicator:{clean_target}",
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

    # ── 3e. Multi-model pipeline results ──────────────────────────────────

    def _load_multi_model_pipeline_results(self) -> None:
        from epi_proxy.report_compare import load_model_runs, _proxy_key

        root = self.root_dir or self.outputs_dir
        runs = load_model_runs(root)
        self.model_names = [run.name for run in runs]
        known_tlas = {ind["Abbreviation"] for ind in get_available_indicators()}

        for run in runs:
            model_name = run.name
            for tla, pipeline in run.results.items():
                if tla not in known_tlas or not pipeline.research_output:
                    continue

                verif_map = {vr.hypothesis_id: vr for vr in pipeline.verification_results}

                for hyp in pipeline.research_output.hypotheses:
                    canonical_key = _proxy_key(hyp)
                    proxy_id = f"proxy:{canonical_key}"
                    vr = verif_map.get(hyp.id)
                    verdict = vr.verdict.value if (vr and vr.verdict) else "inconclusive"

                    eval_entry = {
                        "model": model_name,
                        "hypothesis_id": hyp.id,
                        "direction": hyp.relationship.direction.value if hyp.relationship.direction else "",
                        "functional_form": hyp.relationship.functional_form.value if hyp.relationship.functional_form else "",
                        "strength_estimate": hyp.relationship.strength_estimate or "",
                        "mechanism": hyp.mechanism,
                        "verdict": verdict,
                        "confidence": hyp.confidence.value if hyp.confidence else "",
                        "pearson_r": vr.raw_correlation.pearson_r if (vr and vr.raw_correlation) else None,
                        "pearson_p": vr.raw_correlation.pearson_p if (vr and vr.raw_correlation) else None,
                        "spearman_rho": vr.raw_correlation.spearman_rho if (vr and vr.raw_correlation) else None,
                        "n_observations": vr.raw_correlation.n_observations if (vr and vr.raw_correlation) else None,
                        "partial_r": vr.partial_correlation.partial_r if (vr and vr.partial_correlation) else None,
                        "best_functional_form": vr.functional_form.best_form.value if (vr and vr.functional_form and vr.functional_form.best_form) else "",
                        "validation_issues": vr.validation.issues if (vr and vr.validation) else [],
                        "inclusion_score": vr.validation.inclusion_score.criteria_met if (vr and vr.validation and vr.validation.inclusion_score) else None,
                    }

                    # 1. Update / create ProxyNode
                    existing_node = self.kg.get_node(proxy_id)
                    if existing_node is None:
                        self.kg.add_node(proxy_id, ProxyNode(
                            label=hyp.proxy_variable,
                            description=hyp.proxy_description,
                            hypothesis_id=hyp.id,
                            proxy_variable=hyp.proxy_variable,
                            proxy_description=hyp.proxy_description,
                            confidence=hyp.confidence.value if hyp.confidence else "",
                            evidence_type=hyp.evidence_type.value if hyp.evidence_type else "",
                            canonical_id=canonical_key,
                            models=[model_name],
                            model_count=1,
                            verdict_breakdown={verdict: 1},
                        ))
                    else:
                        attrs = dict(self.kg.nx_graph.nodes[proxy_id])
                        models = list(attrs.get("models", []))
                        if model_name not in models:
                            models.append(model_name)
                        attrs["models"] = models
                        attrs["model_count"] = len(models)
                        vb = dict(attrs.get("verdict_breakdown", {}))
                        vb[verdict] = vb.get(verdict, 0) + 1
                        attrs["verdict_breakdown"] = vb
                        self.kg.nx_graph.nodes[proxy_id].update(attrs)

                    # 2. Update / create ProxyForEdge
                    clean_target = hyp.target_variable.replace("epi:", "").strip().upper()
                    if clean_target not in known_tlas:
                        clean_target = tla
                    target_id = f"indicator:{clean_target}"
                    existing_edge = self.kg.get_edge(proxy_id, target_id)
                    if existing_edge is None or existing_edge.edge_type != EdgeType.PROXY_FOR:
                        self.kg.add_edge(
                            proxy_id, target_id,
                            ProxyForEdge(
                                hypothesis_id=hyp.id,
                                direction=eval_entry["direction"],
                                functional_form=eval_entry["functional_form"],
                                strength_estimate=eval_entry["strength_estimate"],
                                mechanism=eval_entry["mechanism"],
                                verdict=verdict,
                                pearson_r=eval_entry["pearson_r"],
                                pearson_p=eval_entry["pearson_p"],
                                spearman_rho=eval_entry["spearman_rho"],
                                n_observations=eval_entry["n_observations"],
                                partial_r=eval_entry["partial_r"],
                                best_functional_form=eval_entry["best_functional_form"],
                                inclusion_score=eval_entry["inclusion_score"],
                                validation_issues=eval_entry["validation_issues"],
                                models=[model_name],
                                model_count=1,
                                model_evaluations={model_name: eval_entry},
                                consensus_verdict=verdict,
                                agreement_score=1.0,
                                has_directional_conflict=False,
                            ),
                        )
                    else:
                        eattrs = dict(self.kg.nx_graph.edges[proxy_id, target_id])
                        emodels = list(eattrs.get("models", []))
                        if model_name not in emodels:
                            emodels.append(model_name)
                        eattrs["models"] = emodels
                        eattrs["model_count"] = len(emodels)

                        evals = dict(eattrs.get("model_evaluations", {}))
                        evals[model_name] = eval_entry
                        eattrs["model_evaluations"] = evals

                        # Check directional conflict
                        directions = {ev.get("direction") for ev in evals.values() if ev.get("direction")}
                        if len(directions) > 1:
                            eattrs["has_directional_conflict"] = True

                        # Dominant consensus verdict
                        v_counts: dict[str, int] = {}
                        for ev in evals.values():
                            v = ev.get("verdict", "")
                            if v:
                                v_counts[v] = v_counts.get(v, 0) + 1
                        dominant_v = None
                        dominant_c = -1
                        for v_opt in ["confirmed", "partially_confirmed", "inconclusive", "rejected"]:
                            c = v_counts.get(v_opt, 0)
                            if c > dominant_c and c > 0:
                                dominant_v = v_opt
                                dominant_c = c

                        eattrs["consensus_verdict"] = dominant_v or verdict
                        eattrs["verdict"] = eattrs["consensus_verdict"]
                        eattrs["agreement_score"] = dominant_c / len(evals) if evals else 1.0

                        # Average correlation metrics across models
                        r_vals = [ev["pearson_r"] for ev in evals.values() if ev.get("pearson_r") is not None]
                        if r_vals:
                            eattrs["pearson_r"] = sum(r_vals) / len(r_vals)
                        par_vals = [ev["partial_r"] for ev in evals.values() if ev.get("partial_r") is not None]
                        if par_vals:
                            eattrs["partial_r"] = sum(par_vals) / len(par_vals)

                        self.kg.nx_graph.edges[proxy_id, target_id].update(eattrs)

                    # 3. Create / deduplicate data source node
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

                        if not self.kg.get_edge(proxy_id, self._source_nodes[source_key]):
                            self.kg.add_edge(
                                proxy_id, self._source_nodes[source_key],
                                EdgeData(edge_type=EdgeType.MEASURED_BY),
                            )

        # Post-process all ProxyNode consensus_status
        for nid, attrs in list(self.kg.nx_graph.nodes(data=True)):
            if attrs.get("node_type") == NodeType.PROXY_VARIABLE.value:
                m_count = attrs.get("model_count", 1)
                vb = attrs.get("verdict_breakdown", {})
                n_evals = sum(vb.values())
                c_count = vb.get("confirmed", 0)
                r_count = vb.get("rejected", 0)
                if m_count <= 1:
                    c_status = "single_model"
                elif c_count == n_evals and c_count > 0:
                    c_status = "unanimous_confirmed"
                elif c_count >= 2 and c_count >= r_count:
                    c_status = "majority_confirmed"
                elif c_count > 0 and r_count > 0:
                    c_status = "contested"
                else:
                    c_status = "multi_model_mixed"
                self.kg.nx_graph.nodes[nid]["consensus_status"] = c_status


class MultiModelGraphBuilder(GraphBuilder):
    """Convenience builder specifically for cross-model hyper-directories."""

    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, multi_model=True)
