"""Generate an interactive HTML visualization of the EPI knowledge graph."""

from __future__ import annotations

import json
from pathlib import Path

from .graph import EpiKnowledgeGraph
from .schema import EdgeType, Inference, NodeType


def _build_viz_elements(graph: EpiKnowledgeGraph) -> list[dict]:
    """Build Cytoscape.js elements with visualization-specific fields."""
    elements = []

    # Assign concentric ring levels and angular ordering
    # Ring 0: policy_objective, Ring 1: issue_category, Ring 2: indicator, Ring 3: proxy, Ring 4: data_source
    ring_map = {
        NodeType.POLICY_OBJECTIVE.value: 0,
        NodeType.ISSUE_CATEGORY.value: 1,
        NodeType.INDICATOR.value: 2,
        NodeType.PROXY_VARIABLE.value: 3,
        NodeType.DATA_SOURCE.value: 4,
    }

    for nid, attrs in graph.nx_graph.nodes(data=True):
        node_type = attrs.get("node_type", "")
        ring = ring_map.get(node_type, 3)

        data = {
            "id": nid,
            "label": attrs.get("label", nid),
            "node_type": node_type,
            "ring": ring,
        }

        # Extra fields per type
        if node_type == NodeType.INDICATOR.value:
            data["tla"] = attrs.get("tla", "")
            data["issue_category"] = attrs.get("issue_category", "")
            data["policy_objective"] = attrs.get("policy_objective", "")
            data["units"] = attrs.get("units", "")
            data["raw_polarity"] = attrs.get("raw_polarity", "")
            data["source_org"] = attrs.get("source_org", "")
            dk = attrs.get("domain_knowledge", "")
            if dk:
                data["domain_knowledge"] = dk[:500] + ("..." if len(dk) > 500 else "")

        elif node_type == NodeType.PROXY_VARIABLE.value:
            data["hypothesis_id"] = attrs.get("hypothesis_id", "")
            data["proxy_variable"] = attrs.get("proxy_variable", "")
            data["proxy_description"] = attrs.get("proxy_description", "")
            data["confidence"] = attrs.get("confidence", "")
            data["evidence_type"] = attrs.get("evidence_type", "")
            # Find the verdict from proxy_for edge
            for _, target, eattrs in graph.nx_graph.out_edges(nid, data=True):
                if eattrs.get("edge_type") == EdgeType.PROXY_FOR.value:
                    data["verdict"] = eattrs.get("verdict", "")
                    data["target_tla"] = target.split(":", 1)[1] if ":" in target else target
                    break

        elif node_type == NodeType.DATA_SOURCE.value:
            data["organization"] = attrs.get("organization", "")
            data["url"] = attrs.get("url", "")
            data["accessibility"] = attrs.get("accessibility", "")
            data["coverage"] = attrs.get("coverage", "")

        elif node_type == NodeType.ISSUE_CATEGORY.value:
            data["description"] = attrs.get("description", "")

        elif node_type == NodeType.POLICY_OBJECTIVE.value:
            data["description"] = attrs.get("description", "")

        elements.append({"group": "nodes", "data": data})

    for u, v, attrs in graph.nx_graph.edges(data=True):
        edge_type = attrs.get("edge_type", "")
        data = {
            "id": f"{u}|{v}",
            "source": u,
            "target": v,
            "edge_type": edge_type,
        }

        if edge_type == EdgeType.PROXY_FOR.value:
            data["verdict"] = attrs.get("verdict", "")
            data["direction"] = attrs.get("direction", "")
            data["functional_form"] = attrs.get("functional_form", "")
            data["strength_estimate"] = attrs.get("strength_estimate", "")
            data["mechanism"] = (attrs.get("mechanism", "") or "")[:300]
            pr = attrs.get("pearson_r")
            if pr is not None:
                data["pearson_r"] = round(pr, 3)
            pp = attrs.get("pearson_p")
            if pp is not None:
                data["pearson_p"] = round(pp, 4)
            data["n_observations"] = attrs.get("n_observations", "")
            par = attrs.get("partial_r")
            if par is not None:
                data["partial_r"] = round(par, 3)

        elif edge_type == EdgeType.INFERRED_CANDIDATE.value:
            data["rule_name"] = attrs.get("rule_name", "")
            data["confidence"] = attrs.get("confidence", "")
            data["explanation"] = attrs.get("explanation", "")

        elements.append({"group": "edges", "data": data})

    return elements


def generate_html(
    graph: EpiKnowledgeGraph,
    inferences: list[Inference] | None = None,
    output_path: Path | None = None,
) -> str:
    """Generate a self-contained HTML file with interactive graph visualization."""
    elements = _build_viz_elements(graph)

    # Collect inference summaries for the info panel
    inference_summary = {}
    if inferences:
        for inf in inferences:
            t = inf.inference_type
            inference_summary[t] = inference_summary.get(t, 0) + 1

    # Collect TLA list for search
    tlas = sorted([
        nid.split(":", 1)[1]
        for nid, attrs in graph.nx_graph.nodes(data=True)
        if attrs.get("node_type") == NodeType.INDICATOR.value
    ])

    html = _HTML_TEMPLATE.replace("__ELEMENTS__", json.dumps(elements, default=str))
    html = html.replace("__TLA_LIST__", json.dumps(tlas))
    html = html.replace("__INFERENCE_SUMMARY__", json.dumps(inference_summary))

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

    return html


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EPI Proxy Discovery — Knowledge Graph</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.4/cytoscape.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  @font-face { font-family: 'YaleNew'; src: url('https://yaleux.github.io/yaleui/assets/fonts/YaleNew-Roman.woff2') format('woff2'); font-weight: 400; }
  @font-face { font-family: 'YaleNew'; src: url('https://yaleux.github.io/yaleui/assets/fonts/YaleNew-Bold.woff2') format('woff2'); font-weight: 700; }

  :root {
    --yale-blue: #00356B;
    --yale-blue-light: #2b5f9e;
    --yale-blue-faint: rgba(0, 53, 107, 0.06);
    --epi-green: #2e7d32;
    --green-light: #4caf50;
    --accent-amber: #bf6900;
    --accent-red: #c62828;
    --bg-primary: #ffffff;
    --bg-secondary: #f7f7f5;
    --border: #d4d2cb;
    --border-light: #e8e6e1;
    --text-primary: #2c2c2c;
    --text-secondary: #5a5a5a;
    --text-muted: #8a8a8a;
    --font-body: 'Source Sans 3', 'Segoe UI', sans-serif;
    --font-display: 'YaleNew', Georgia, serif;
    --font-mono: 'JetBrains Mono', monospace;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: var(--font-body); background: var(--bg-secondary); color: var(--text-primary); display: flex; height: 100vh; overflow: hidden; }

  /* ── Left sidebar ─────────────────────────────────────── */
  #sidebar {
    width: 280px; background: var(--bg-primary); border-right: 1px solid var(--border);
    padding: 20px; overflow-y: auto; flex-shrink: 0;
    display: flex; flex-direction: column; gap: 20px;
  }

  .sidebar-header {
    border-bottom: 2px solid var(--yale-blue); padding-bottom: 14px;
  }
  .sidebar-header h1 {
    font-family: var(--font-display); font-size: 17px; color: var(--yale-blue);
    font-weight: 700; line-height: 1.3;
  }
  .sidebar-header .subtitle {
    font-size: 12px; color: var(--text-muted); margin-top: 2px;
  }

  .section-label {
    font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 8px; font-weight: 500;
  }

  .search-box {
    width: 100%; padding: 9px 12px; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: 6px;
    color: var(--text-primary); font-family: var(--font-mono); font-size: 13px; outline: none;
    transition: border-color 0.2s;
  }
  .search-box:focus { border-color: var(--yale-blue); box-shadow: 0 0 0 3px var(--yale-blue-faint); }
  .search-box::placeholder { color: var(--text-muted); font-family: var(--font-body); }

  .toggle-group { display: flex; flex-direction: column; gap: 2px; }
  .toggle-item {
    display: flex; align-items: center; gap: 8px; padding: 5px 8px;
    cursor: pointer; font-size: 13px; color: var(--text-secondary);
    border-radius: 4px; transition: background 0.15s;
  }
  .toggle-item:hover { background: var(--yale-blue-faint); }
  .toggle-item input { accent-color: var(--yale-blue); width: 14px; height: 14px; }
  .toggle-item .swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
  .toggle-item .count { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin-left: auto; }

  .legend-section { display: flex; flex-direction: column; gap: 10px; }
  .legend-group-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 2px; }
  .legend-row { display: flex; flex-wrap: wrap; gap: 10px; }
  .legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary); }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .legend-line { width: 16px; height: 2px; flex-shrink: 0; border-radius: 1px; }
  .legend-line.dashed { background: repeating-linear-gradient(90deg, var(--accent-amber) 0, var(--accent-amber) 4px, transparent 4px, transparent 7px); }

  .stats-bar {
    font-size: 12px; color: var(--text-muted); line-height: 1.6;
    padding-top: 12px; border-top: 1px solid var(--border-light);
    margin-top: auto;
  }
  .stats-bar strong { color: var(--text-secondary); }

  /* ── Graph area ───────────────────────────────────────── */
  #cy-container { flex: 1; position: relative; background: var(--bg-secondary); }
  #cy { width: 100%; height: 100%; }

  /* ── Popover detail panel ───────────────────────────────── */
  #popover {
    display: none; position: absolute; z-index: 1000;
    background: var(--bg-primary); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px 18px; width: 340px; max-height: 420px;
    overflow-y: auto; box-shadow: 0 8px 30px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06);
    pointer-events: auto;
  }
  #popover.visible { display: block; }

  #popover-title {
    font-family: var(--font-display); font-size: 15px; color: var(--yale-blue);
    font-weight: 700; margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 2px solid var(--yale-blue); line-height: 1.3;
  }
  #popover .field { margin-bottom: 10px; }
  #popover .field-label {
    font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 2px;
  }
  #popover .field-value {
    font-size: 13px; color: var(--text-primary); line-height: 1.5; word-wrap: break-word;
  }
  #popover .field-value a { color: var(--yale-blue-light); text-decoration: none; }
  #popover .field-value a:hover { text-decoration: underline; }

  .verdict-badge {
    display: inline-block; padding: 2px 10px; border-radius: 4px;
    font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  }
  .verdict-confirmed { background: #e8f5e9; color: var(--epi-green); }
  .verdict-partially_confirmed { background: #fff8e1; color: var(--accent-amber); }
  .verdict-inconclusive { background: #f5f5f5; color: var(--text-muted); }
  .verdict-rejected { background: #fbe9e7; color: var(--accent-red); }

  .stat-chip {
    display: inline-block; padding: 1px 6px; border-radius: 3px;
    font-family: var(--font-mono); font-size: 12px;
    background: var(--bg-secondary); color: var(--text-primary);
    border: 1px solid var(--border-light);
  }

  #popover-close {
    position: absolute; top: 10px; right: 12px; background: none; border: none;
    font-size: 18px; color: var(--text-muted); cursor: pointer; line-height: 1;
    padding: 2px 6px; border-radius: 4px;
  }
  #popover-close:hover { background: var(--bg-secondary); color: var(--text-primary); }
</style>
</head>
<body>

<div id="sidebar">
  <div class="sidebar-header">
    <h1>EPI Proxy Discovery<br>Knowledge Graph</h1>
    <div class="subtitle">Yale Center for Environmental Law & Policy</div>
  </div>

  <div>
    <div class="section-label">Search Indicator</div>
    <input type="text" id="search" class="search-box" placeholder="Type TLA (e.g. UWD, WRR)..." list="tla-list">
    <datalist id="tla-list"></datalist>
  </div>

  <div>
    <div class="section-label">Graph Layers</div>
    <div class="toggle-group" id="layer-toggles"></div>
  </div>

  <div>
    <div class="section-label">Relationships</div>
    <div class="toggle-group" id="edge-toggles"></div>
  </div>

  <div>
    <div class="section-label">Verification Status</div>
    <div class="toggle-group" id="verdict-toggles"></div>
  </div>

  <div class="legend-section">
    <div class="section-label">Legend</div>
    <div>
      <div class="legend-group-label">Node types (by size)</div>
      <div class="legend-row" id="legend-nodes"></div>
    </div>
    <div>
      <div class="legend-group-label">Verification verdict</div>
      <div class="legend-row" id="legend-verdicts"></div>
    </div>
    <div>
      <div class="legend-group-label">Relationships</div>
      <div class="legend-row" id="legend-edges"></div>
    </div>
  </div>

  <div class="stats-bar" id="stats"></div>
</div>

<div id="cy-container">
  <div id="cy"></div>
  <div id="popover">
    <button id="popover-close">&times;</button>
    <div id="popover-title"></div>
    <div id="popover-body"></div>
  </div>
</div>

<script>
const allElements = __ELEMENTS__;
const tlaList = __TLA_LIST__;
const inferenceSummary = __INFERENCE_SUMMARY__;

// ── Semantic labels ────────────────────────────────────────────
const nodeLabels = {
  policy_objective: 'EPI Policy Objectives',
  issue_category:   'Issue Categories',
  indicator:        'EPI Indicators',
  proxy_variable:   'Proxy Hypotheses',
  data_source:      'Data Sources',
};
const nodeDescriptions = {
  policy_objective: 'Health, Ecosystem Vitality, Climate Change',
  issue_category:   'e.g. Air Quality, Biodiversity, Waste',
  indicator:        '67 measurable metrics (3-letter TLAs)',
  proxy_variable:   'Candidate proxy data sources',
  data_source:      'Organizations providing proxy data',
};
const nodeColors = {
  policy_objective: '#00356B',
  issue_category:   '#2b5f9e',
  indicator:        '#4a90d9',
  proxy_variable:   '#2e7d32',
  data_source:      '#8a8a8a',
};
const verdictColors = {
  confirmed:            '#2e7d32',
  partially_confirmed:  '#bf6900',
  inconclusive:         '#8a8a8a',
  rejected:             '#c62828',
};
const verdictLabels = {
  confirmed:            'Confirmed',
  partially_confirmed:  'Partially confirmed',
  inconclusive:         'Inconclusive',
  rejected:             'Rejected',
};
const edgeLabels = {
  contains:             'Hierarchy (contains)',
  proxy_for:            'Proxy relationship',
  measured_by:          'Data source link',
  same_issue_category:  'Same issue category',
  sibling_indicator:    'Sibling indicators',
  inferred_candidate:   'Inferred candidate (reasoning)',
};
const edgeColors = {
  contains:             '#b0ada6',
  proxy_for:            '#2e7d32',
  measured_by:          '#8a8a8a',
  same_issue_category:  '#d4d2cb',
  sibling_indicator:    '#6a1b9a',
  inferred_candidate:   '#bf6900',
};

// ── Default visibility ─────────────────────────────────────────
const defaultNodeVis = {
  policy_objective: true, issue_category: true,
  indicator: true, proxy_variable: true, data_source: false,
};
const defaultEdgeVis = {
  contains: true, proxy_for: true, measured_by: false,
  same_issue_category: false, sibling_indicator: false, inferred_candidate: true,
};
const defaultVerdictVis = {
  confirmed: true, partially_confirmed: true, inconclusive: true, rejected: true,
};

let nodeVis = {...defaultNodeVis};
let edgeVis = {...defaultEdgeVis};
let verdictVis = {...defaultVerdictVis};
let searchTLA = '';

// ── Setup controls ─────────────────────────────────────────────
function setupControls() {
  // Layer (node type) toggles
  const lt = document.getElementById('layer-toggles');
  for (const [type, label] of Object.entries(nodeLabels)) {
    const count = allElements.filter(e => e.group === 'nodes' && e.data.node_type === type).length;
    lt.innerHTML += `<label class="toggle-item">
      <input type="checkbox" data-node-type="${type}" ${defaultNodeVis[type] ? 'checked' : ''}>
      <span class="swatch" style="background:${nodeColors[type]}"></span>
      ${label}
      <span class="count">${count}</span>
    </label>`;
  }
  lt.querySelectorAll('input').forEach(cb => cb.addEventListener('change', e => {
    nodeVis[e.target.dataset.nodeType] = e.target.checked;
    if (e.target.dataset.nodeType === 'data_source') {
      edgeVis.measured_by = e.target.checked;
      const mb = document.querySelector('[data-edge-type="measured_by"]');
      if (mb) mb.checked = e.target.checked;
    }
    applyFilters();
  }));

  // Edge toggles
  const et = document.getElementById('edge-toggles');
  for (const [type, label] of Object.entries(edgeLabels)) {
    const count = allElements.filter(e => e.group === 'edges' && e.data.edge_type === type).length;
    et.innerHTML += `<label class="toggle-item">
      <input type="checkbox" data-edge-type="${type}" ${defaultEdgeVis[type] ? 'checked' : ''}>
      <span class="swatch" style="background:${edgeColors[type]}; border-radius:1px; height:3px; width:12px;"></span>
      ${label}
      <span class="count">${count}</span>
    </label>`;
  }
  et.querySelectorAll('input').forEach(cb => cb.addEventListener('change', e => {
    edgeVis[e.target.dataset.edgeType] = e.target.checked;
    applyFilters();
  }));

  // Verdict toggles
  const vt = document.getElementById('verdict-toggles');
  for (const [verdict, label] of Object.entries(verdictLabels)) {
    const count = allElements.filter(e => e.group === 'nodes' && e.data.verdict === verdict).length;
    vt.innerHTML += `<label class="toggle-item">
      <input type="checkbox" data-verdict="${verdict}" checked>
      <span class="swatch" style="background:${verdictColors[verdict]}"></span>
      ${label}
      <span class="count">${count}</span>
    </label>`;
  }
  vt.querySelectorAll('input').forEach(cb => cb.addEventListener('change', e => {
    verdictVis[e.target.dataset.verdict] = e.target.checked;
    applyFilters();
  }));

  // Legends
  const ln = document.getElementById('legend-nodes');
  const ringLabels = ['policy_objective', 'issue_category', 'indicator', 'proxy_variable', 'data_source'];
  ringLabels.forEach(t => {
    ln.innerHTML += `<span class="legend-item"><span class="legend-dot" style="background:${nodeColors[t]}"></span>${nodeLabels[t].replace('EPI ', '')}</span>`;
  });

  const lv = document.getElementById('legend-verdicts');
  for (const [v, label] of Object.entries(verdictLabels)) {
    lv.innerHTML += `<span class="legend-item"><span class="legend-dot" style="background:${verdictColors[v]}"></span>${label}</span>`;
  }

  const le = document.getElementById('legend-edges');
  le.innerHTML += `<span class="legend-item"><span class="legend-line" style="background:${edgeColors.proxy_for}"></span>Proxy link</span>`;
  le.innerHTML += `<span class="legend-item"><span class="legend-line dashed"></span>Inferred</span>`;
  le.innerHTML += `<span class="legend-item"><span class="legend-line" style="background:${edgeColors.contains}"></span>Hierarchy</span>`;

  // TLA datalist
  const dl = document.getElementById('tla-list');
  tlaList.forEach(tla => { const o = document.createElement('option'); o.value = tla; dl.appendChild(o); });
}

// ── Cytoscape init ─────────────────────────────────────────────
const cy = cytoscape({
  container: document.getElementById('cy'),
  elements: [],
  style: [
    // Base node
    { selector: 'node', style: {
      'label': 'data(label)', 'font-family': '"Source Sans 3", sans-serif',
      'font-size': 9, 'color': '#5a5a5a',
      'text-valign': 'bottom', 'text-margin-y': 5,
      'text-max-width': 85, 'text-wrap': 'ellipsis',
      'background-color': '#999', 'width': 18, 'height': 18, 'border-width': 0,
      'transition-property': 'opacity, background-color, border-width, border-color, width, height',
      'transition-duration': '0.25s',
    }},
    // Policy objectives — center
    { selector: 'node[node_type="policy_objective"]', style: {
      'background-color': '#00356B', 'width': 44, 'height': 44,
      'font-family': '"YaleNew", Georgia, serif',
      'font-size': 13, 'font-weight': 'bold', 'color': '#00356B',
      'text-margin-y': 7,
    }},
    // Issue categories — ring 1
    { selector: 'node[node_type="issue_category"]', style: {
      'background-color': '#2b5f9e', 'width': 28, 'height': 28,
      'font-size': 10, 'color': '#2b5f9e', 'font-weight': '600',
    }},
    // Indicators — ring 2
    { selector: 'node[node_type="indicator"]', style: {
      'background-color': '#4a90d9', 'width': 20, 'height': 20,
      'font-size': 9, 'color': '#5a5a5a',
      'font-family': '"JetBrains Mono", monospace',
    }},
    // Proxies — ring 3
    { selector: 'node[node_type="proxy_variable"]', style: {
      'background-color': '#2e7d32', 'width': 12, 'height': 12,
      'font-size': 7, 'color': '#8a8a8a',
    }},
    // Data sources — ring 4
    { selector: 'node[node_type="data_source"]', style: {
      'background-color': '#8a8a8a', 'width': 10, 'height': 10,
      'font-size': 7, 'shape': 'diamond', 'color': '#8a8a8a',
    }},
    // Verdict overrides for proxy nodes
    { selector: 'node[verdict="confirmed"]', style: { 'background-color': '#2e7d32' }},
    { selector: 'node[verdict="partially_confirmed"]', style: { 'background-color': '#bf6900' }},
    { selector: 'node[verdict="inconclusive"]', style: { 'background-color': '#8a8a8a' }},
    { selector: 'node[verdict="rejected"]', style: { 'background-color': '#c62828' }},
    // Base edge
    { selector: 'edge', style: {
      'width': 1, 'line-color': '#d4d2cb', 'curve-style': 'bezier',
      'target-arrow-shape': 'triangle', 'target-arrow-color': '#d4d2cb',
      'arrow-scale': 0.5, 'opacity': 0.4,
      'transition-property': 'opacity, line-color, width',
      'transition-duration': '0.25s',
    }},
    // Edge type styles
    { selector: 'edge[edge_type="contains"]', style: {
      'line-color': '#b0ada6', 'target-arrow-color': '#b0ada6', 'width': 1.5, 'opacity': 0.5,
    }},
    { selector: 'edge[edge_type="proxy_for"]', style: {
      'line-color': '#2e7d32', 'target-arrow-color': '#2e7d32', 'width': 2, 'opacity': 0.6,
    }},
    { selector: 'edge[edge_type="inferred_candidate"]', style: {
      'line-color': '#bf6900', 'target-arrow-color': '#bf6900',
      'width': 1.5, 'line-style': 'dashed', 'opacity': 0.5,
    }},
    { selector: 'edge[edge_type="measured_by"]', style: {
      'line-color': '#8a8a8a', 'target-arrow-color': '#8a8a8a', 'opacity': 0.3,
    }},
    { selector: 'edge[edge_type="same_issue_category"]', style: {
      'line-color': '#e8e6e1', 'target-arrow-shape': 'none', 'opacity': 0.2,
    }},
    { selector: 'edge[edge_type="sibling_indicator"]', style: {
      'line-color': '#6a1b9a', 'target-arrow-shape': 'none', 'opacity': 0.25,
    }},
    // Highlight / dim
    { selector: '.highlighted', style: {
      'border-width': 3, 'border-color': '#00356B', 'z-index': 999,
    }},
    { selector: '.dimmed', style: { 'opacity': 0.08 }},
    { selector: 'edge.dimmed', style: { 'opacity': 0.03 }},
    { selector: '.highlighted-edge', style: { 'opacity': 0.9, 'width': 2.5, 'z-index': 999 }},
  ],
  layout: { name: 'preset' },
  wheelSensitivity: 0.3,
});

// ── Filtering ──────────────────────────────────────────────────
function getFilteredElements() {
  return allElements.filter(el => {
    if (el.group === 'nodes') {
      if (!nodeVis[el.data.node_type]) return false;
      if (el.data.node_type === 'proxy_variable' && el.data.verdict && !verdictVis[el.data.verdict]) return false;
      return true;
    }
    if (el.group === 'edges') {
      return edgeVis[el.data.edge_type] !== false;
    }
    return true;
  });
}

function applyFilters() {
  const filtered = getFilteredElements();
  cy.elements().remove();
  cy.add(filtered);
  // Prune orphan edges
  cy.edges().forEach(e => {
    if (!cy.getElementById(e.data('source')).length || !cy.getElementById(e.data('target')).length) {
      e.remove();
    }
  });
  runLayout();
  applySearch();
  updateStats();
}

function applySearch() {
  cy.elements().removeClass('highlighted dimmed highlighted-edge');
  if (!searchTLA) return;
  const center = cy.getElementById('indicator:' + searchTLA);
  if (!center.length) return;

  const connected = center.neighborhood().add(center);
  const parent = center.incomers('edge[edge_type="contains"]').sources();
  const grandparent = parent.incomers('edge[edge_type="contains"]').sources();
  const highlight = connected.add(parent).add(grandparent);

  cy.elements().addClass('dimmed');
  highlight.removeClass('dimmed');
  center.addClass('highlighted');
  highlight.edges().addClass('highlighted-edge');
}

// ── Layout (concentric only) ───────────────────────────────────
function runLayout() {
  cy.layout({
    name: 'cose',
    idealEdgeLength: 100,
    nodeOverlap: 20,
    nodeRepulsion: 12000,
    edgeElasticity: 80,
    gravity: 0.3,
    numIter: 800,
    animate: true,
    animationDuration: 800,
    animationEasing: 'ease-out',
  }).run();
}

// ── Popover ────────────────────────────────────────────────────
const popover = document.getElementById('popover');
const popoverTitle = document.getElementById('popover-title');
const popoverBody = document.getElementById('popover-body');

function showPopover(data, type, renderedPos) {
  let html = '';

  if (type === 'node') {
    popoverTitle.textContent = data.label || data.id;
    const nt = data.node_type || '';

    if (nt === 'indicator') {
      html += field('TLA', `<span class="stat-chip">${data.tla}</span>`);
      html += field('Issue Category', data.issue_category);
      html += field('Policy Objective', data.policy_objective);
      html += field('Units', data.units);
      html += field('Polarity', data.raw_polarity);
      html += field('Data Source', data.source_org);
      if (data.domain_knowledge) html += field('Domain Knowledge', data.domain_knowledge);
    } else if (nt === 'proxy_variable') {
      html += field('Hypothesis', `<span class="stat-chip">${data.hypothesis_id}</span>`);
      if (data.target_tla) html += field('Target Indicator', `<span class="stat-chip">${data.target_tla}</span>`);
      if (data.verdict) html += field('Verdict', `<span class="verdict-badge verdict-${data.verdict}">${(data.verdict || '').replace(/_/g, ' ')}</span>`);
      html += field('Confidence', data.confidence ? data.confidence.replace(/_/g, ' ') : '');
      html += field('Evidence Type', data.evidence_type ? data.evidence_type.replace(/_/g, ' ') : '');
      if (data.proxy_description) html += field('Description', data.proxy_description);
    } else if (nt === 'data_source') {
      html += field('Organization', data.organization);
      if (data.url) html += field('URL', `<a href="${data.url}" target="_blank">${data.url}</a>`);
      html += field('Accessibility', data.accessibility);
      html += field('Coverage', data.coverage);
    } else if (nt === 'policy_objective') {
      popoverTitle.textContent = data.label;
      html += field('Role', 'Top-level EPI policy objective');
      html += field('Description', data.description);
    } else if (nt === 'issue_category') {
      popoverTitle.textContent = data.label;
      html += field('Role', 'EPI issue category grouping related indicators');
      html += field('Description', data.description);
    }
  } else if (type === 'edge') {
    const et = data.edge_type || '';
    popoverTitle.textContent = edgeLabels[et] || et;

    html += field('From', data.source);
    html += field('To', data.target);

    if (et === 'proxy_for') {
      if (data.verdict) html += field('Verdict', `<span class="verdict-badge verdict-${data.verdict}">${(data.verdict || '').replace(/_/g, ' ')}</span>`);
      html += field('Direction', data.direction);
      html += field('Functional Form', data.functional_form);
      html += field('Expected Strength', data.strength_estimate);
      if (data.pearson_r !== undefined && data.pearson_r !== '') html += field('Pearson r', `<span class="stat-chip">${data.pearson_r}</span>`);
      if (data.pearson_p !== undefined && data.pearson_p !== '') html += field('Pearson p', `<span class="stat-chip">${data.pearson_p}</span>`);
      if (data.partial_r !== undefined && data.partial_r !== '') html += field('Partial r (GDP controlled)', `<span class="stat-chip">${data.partial_r}</span>`);
      if (data.n_observations) html += field('N observations', `<span class="stat-chip">${data.n_observations}</span>`);
      if (data.mechanism) html += field('Mechanism', data.mechanism);
    } else if (et === 'inferred_candidate') {
      html += field('Rule', data.rule_name);
      if (data.confidence) html += field('Confidence', `<span class="stat-chip">${data.confidence}</span>`);
      html += field('Explanation', data.explanation);
    }
  }

  popoverBody.innerHTML = html || 'No details';

  // Position near the node/edge within the cy-container
  const container = document.getElementById('cy-container');
  const rect = container.getBoundingClientRect();
  let left = renderedPos.x + 20;
  let top = renderedPos.y - 20;

  // Keep popover within container bounds
  const pw = 340, ph = 420;
  if (left + pw > rect.width) left = renderedPos.x - pw - 20;
  if (top + ph > rect.height) top = rect.height - ph - 10;
  if (top < 10) top = 10;
  if (left < 10) left = 10;

  popover.style.left = left + 'px';
  popover.style.top = top + 'px';
  popover.classList.add('visible');
}

function hidePopover() {
  popover.classList.remove('visible');
}

function field(label, value) {
  if (value === undefined || value === null || value === '') return '';
  return `<div class="field"><div class="field-label">${label}</div><div class="field-value">${value}</div></div>`;
}

// ── Stats bar ──────────────────────────────────────────────────
function updateStats() {
  const s = document.getElementById('stats');
  const nn = cy.nodes().length;
  const ne = cy.edges().length;
  const tn = allElements.filter(e => e.group === 'nodes').length;
  const te = allElements.filter(e => e.group === 'edges').length;
  s.innerHTML = `<strong>Showing</strong> ${nn} nodes, ${ne} edges<br><strong>Total</strong> ${tn} nodes, ${te} edges`;
}

// ── Events ─────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', e => {
  searchTLA = e.target.value.toUpperCase().trim();
  applySearch();
});

// Close popover
document.getElementById('popover-close').addEventListener('click', hidePopover);

// Click on node
cy.on('click', 'node', function(e) {
  const node = e.target;
  showPopover(node.data(), 'node', node.renderedPosition());
});

// Click on edge
cy.on('click', 'edge', function(e) {
  const edge = e.target;
  const mid = edge.renderedMidpoint();
  showPopover(edge.data(), 'edge', mid);
});

// Click on background — close popover
cy.on('click', function(e) {
  if (e.target === cy) hidePopover();
});

// Cursor feedback on hover
cy.on('mouseover', 'node, edge', function() { document.getElementById('cy').style.cursor = 'pointer'; });
cy.on('mouseout', 'node, edge', function() { document.getElementById('cy').style.cursor = 'default'; });

// ── Init ───────────────────────────────────────────────────────
setupControls();
applyFilters();
</script>
</body>
</html>"""
