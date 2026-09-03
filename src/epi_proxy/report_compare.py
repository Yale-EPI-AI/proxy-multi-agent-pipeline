"""HTML dashboard generator comparing multiple model runs of the pipeline.

Scans a parent directory whose subdirectories are model output dirs (each
holding ``{TLA}/pipeline_result.json`` files), loads every ``PipelineResult``,
and renders a single self-contained HTML file with:

  1. Summary cards — per-model coverage, hypothesis counts, verdict distribution
  2. Indicator x Model matrix — hypothesis counts + dominant verdict per cell
  3. Shared-proxy agreement — hypotheses matched by ``db_variable_id`` across models
  4. Per-indicator deep-dive — expandable per-model hypothesis tables

Reuses the styling/helpers from :mod:`epi_proxy.report` so the look stays consistent
with the existing per-indicator dashboards.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from epi_proxy.report import _build_css, _build_js, _escape, _fmt, _verdict_color
from epi_proxy.schemas import PipelineResult, ProxyHypothesis, VerificationResult

VERDICT_ORDER = ["confirmed", "partially_confirmed", "inconclusive", "rejected"]
VERDICT_SHORT = {
    "confirmed": "C",
    "partially_confirmed": "P",
    "inconclusive": "I",
    "rejected": "R",
}

_INDICATOR_NAMES: dict[str, str] | None = None


# ── Data loading ──────────────────────────────────────────────────────────────


@dataclass
class ModelRun:
    """One model's output directory + its loaded per-indicator results."""

    name: str
    dir_path: Path
    results: dict[str, PipelineResult] = field(default_factory=dict)

    @property
    def all_hypotheses(self) -> list[ProxyHypothesis]:
        hyps: list[ProxyHypothesis] = []
        for pr in self.results.values():
            if pr.research_output:
                hyps.extend(pr.research_output.hypotheses)
        return hyps

    @property
    def all_verifications(self) -> list[VerificationResult]:
        vrs: list[VerificationResult] = []
        for pr in self.results.values():
            vrs.extend(pr.verification_results)
        return vrs


def resolve_model_name(model_dir: Path) -> str:
    """Best-effort model name from llm_traces.jsonl; falls back to dir name."""
    # Traces are written per-indicator, so search the model root and one level down.
    trace = model_dir / "llm_traces.jsonl"
    if not trace.exists():
        for sub in sorted(model_dir.iterdir()):
            if sub.is_dir() and (sub / "llm_traces.jsonl").exists():
                trace = sub / "llm_traces.jsonl"
                break
    if trace.exists():
        for line in trace.read_text(encoding="utf-8").splitlines()[:20]:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            model = entry.get("model")
            if model:
                return str(model)
    return model_dir.name


def load_model_runs(root_dir: Path) -> list[ModelRun]:
    """Load every model subdirectory under *root_dir*.

    A subdirectory is treated as a model run if it contains at least one
    ``{TLA}/pipeline_result.json``. Unparseable files are skipped.
    """
    if not root_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_dir}")

    runs: list[ModelRun] = []
    for entry in sorted(root_dir.iterdir()):
        if not entry.is_dir():
            continue
        run = ModelRun(name=resolve_model_name(entry), dir_path=entry)
        for pr_path in sorted(entry.glob("*/pipeline_result.json")):
            tla = pr_path.parent.name
            try:
                run.results[tla] = PipelineResult.model_validate_json(
                    pr_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
        if run.results:
            runs.append(run)
    return runs


def _verdict_counts(vrs: list[VerificationResult]) -> dict[str, int]:
    counts = {v: 0 for v in VERDICT_ORDER}
    for vr in vrs:
        v = vr.verdict.value
        counts[v] = counts.get(v, 0) + 1
    return counts


def _dominant_verdict(counts: dict[str, int]) -> str | None:
    """Most frequent verdict (confirmed > partial > inconclusive > rejected ties)."""
    best, best_count = None, -1
    for v in VERDICT_ORDER:
        if counts.get(v, 0) > best_count:
            best, best_count = v, counts[v]
    return best


def _indicator_name(tla: str) -> str:
    """Human-readable indicator name from the zipped master variable list."""
    global _INDICATOR_NAMES
    if _INDICATOR_NAMES is None:
        _INDICATOR_NAMES = _load_indicator_names()
    return _INDICATOR_NAMES.get(tla, tla)


def _load_indicator_names() -> dict[str, str]:
    """Read Abbreviation → Description from the (read-only) EPI data zip."""
    zip_path = (
        Path(__file__).resolve().parent.parent.parent / "docs" / "EPI2024_Work" / "EPI2024_Work.zip"
    )
    if not zip_path.exists():
        return {}
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = [n for n in z.namelist() if n.endswith("master_variable_list.csv")]
            if not names:
                return {}
            # Prefer the non-backup path.
            name = next((n for n in names if "old files" not in n), names[0])
            with z.open(name) as f:
                raw = io.StringIO(f.read().decode("utf-8", errors="replace"))
                rows = csv.DictReader(raw)
                return {
                    row["Abbreviation"]: row["Description"]
                    for row in rows
                    if row.get("Abbreviation") and row.get("Description")
                }
    except (KeyError, csv.Error, OSError):
        return {}


def _proxy_key(hyp: ProxyHypothesis) -> str:
    """Normalized join key for matching hypotheses across models."""
    if hyp.db_variable_id:
        return f"db:{hyp.db_variable_id}"
    return f"name:{hyp.proxy_variable.strip().lower()}"


def _slug(text: str) -> str:
    """Sanitize a string for use as an HTML element id."""
    out = []
    for ch in text:
        if ch.isalnum() or ch in "-._":
            out.append(ch)
        else:
            out.append("-")
    slug = "".join(out).strip("-")
    return slug or "x"


# ── HTML building ─────────────────────────────────────────────────────────────


def build_comparison_html(runs: list[ModelRun], root_name: str = "") -> str:
    """Render the full comparison dashboard as a self-contained HTML string."""
    all_tlas = sorted({tla for run in runs for tla in run.results})
    model_names = [run.name for run in runs]

    sections = []
    sections.append(_build_summary_section(runs))
    sections.append(_build_matrix_section(runs, all_tlas, model_names))
    sections.append(_build_shared_section(runs, all_tlas, model_names))
    sections.append(_build_deepdive_section(runs, all_tlas, model_names))

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model Comparison — Proxy Discovery Pipeline</title>
<style>
{_build_css()}
{_comparison_css()}
</style>
</head>
<body>
{_build_compare_header(runs, root_name)}
<div class="container">
{"".join(sections)}
</div>
<script>
{_build_js()}
{_comparison_js()}
</script>
</body>
</html>"""
    return page


def _comparison_css() -> str:
    return """
.section{margin:34px 0 14px;}
.section-title{
  color:#00356B;font-size:18px;font-weight:700;letter-spacing:.5px;
  border-bottom:2px solid #00356B;padding-bottom:8px;margin-bottom:16px;
}
table.summary{width:100%;border-collapse:collapse;min-width:900px;}
table.summary th,table.summary td{padding:8px 12px;border-bottom:1px solid #e8e6e1;font-size:12px;}
table.summary thead th{
  text-align:right;color:#00356B;font-size:10px;text-transform:uppercase;letter-spacing:1px;
  border-bottom:2px solid #00356B;font-weight:600;white-space:nowrap;
}
table.summary thead th.sortable{cursor:pointer;user-select:none;}
table.summary thead th.sortable:hover{color:#2b5f9e;}
table.summary thead th.sorted-asc::after{content:" \25B2";font-size:9px;}
table.summary thead th.sorted-desc::after{content:" \25BC";font-size:9px;}
table.summary th:first-child,table.summary td:first-child{text-align:left;}
table.summary td{text-align:right;font-variant-numeric:tabular-nums;}
table.summary td.name-col{font-weight:700;color:#00356B;word-break:break-word;max-width:280px;}
table.summary td.dir-col{font-family:monospace;font-size:10px;color:#8a8a8a;}
table.summary tr:hover td{background:rgba(0,53,107,0.04);}
.matrix-wrap{overflow-x:auto;}
table.matrix{width:100%;border-collapse:collapse;min-width:640px;}
table.matrix th,table.matrix td{
  text-align:center;padding:8px 10px;border-bottom:1px solid #e8e6e1;font-size:12px;
}
table.matrix thead th{
  color:#00356B;font-size:11px;text-transform:uppercase;letter-spacing:1px;
  border-bottom:2px solid #00356B;font-weight:600;white-space:nowrap;
}
table.matrix th:first-child,table.matrix td:first-child{text-align:left;}
.cell-count{font-size:15px;font-weight:700;color:#2c2c2c;display:block;}
.cell-verdicts{font-size:10px;color:#5a5a5a;letter-spacing:.3px;white-space:nowrap;}
.cell-empty{color:#c9c7c0;font-style:italic;font-size:11px;}
.cell-zero{color:#8a8a8a;font-size:11px;}
.agree-badge,.disagree-badge{
  display:inline-block;font-size:9px;font-weight:700;letter-spacing:.5px;
  padding:2px 7px;border-radius:3px;text-transform:uppercase;margin-left:6px;
}
.agree-badge{background:#e8f5e9;color:#2e7d32;border:1px solid #2e7d3230;}
.disagree-badge{background:#fff3e0;color:#bf6900;border:1px solid #bf690040;}
.dive-row{cursor:pointer;transition:background .15s;}
.dive-row:hover{background:rgba(0,53,107,0.04);}
.dive-row td{padding:10px 12px;border-bottom:1px solid #e8e6e1;font-size:13px;}
.dive-body{display:none;}
.dive-body.open{display:table-row;}
.dive-body td{padding:0;border-bottom:1px solid #e8e6e1;}
.dive-panel{background:#f7f7f5;padding:16px 20px;border-left:3px solid #00356B;}
.dive-panel h4{
  color:#00356B;font-size:11px;text-transform:uppercase;letter-spacing:1px;
  margin:16px 0 6px;font-weight:600;
}
.dive-panel h4:first-child{margin-top:0;}
.dive-panel p,.dive-panel li{color:#2c2c2c;font-size:13px;line-height:1.65;}
.dive-panel ul{list-style:none;padding:0;}
.dive-panel ul li::before{content:"\203A ";color:#8a8a8a;}
.run-block{margin-bottom:22px;}
.run-block:last-child{margin-bottom:0;}
.run-heading{
  font-size:12px;font-weight:700;color:#00356B;letter-spacing:.5px;
  text-transform:uppercase;margin-bottom:8px;
}
table.dive-table{width:100%;border-collapse:collapse;}
table.dive-table th{
  text-align:left;padding:7px 10px;color:#00356B;font-size:10px;
  text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #00356B;font-weight:600;
}
table.dive-table td{padding:8px 10px;border-bottom:1px solid #e8e6e1;font-size:12px;white-space:nowrap;}
table.dive-table td.proxy-col{white-space:normal;max-width:260px;}
.no-shared{color:#8a8a8a;font-style:italic;font-size:13px;}
"""


def _comparison_js() -> str:
    return r"""
function parseCell(th,text){
  if(th.getAttribute('data-type')==='str')return text.toLowerCase();
  var m=text.match(/[\d\.]+/);
  return m?parseFloat(m[0]):0;
}
function sortSummary(th){
  var idx=Array.prototype.indexOf.call(th.parentNode.children,th);
  var tbody=th.closest('table').querySelector('tbody');
  var rows=Array.prototype.slice.call(tbody.querySelectorAll('tr'));
  var asc=th.classList.contains('sorted-asc');
  th.closest('thead').querySelectorAll('th').forEach(function(h){
    h.classList.remove('sorted-asc','sorted-desc');
  });
  th.classList.add(asc?'sorted-desc':'sorted-asc');
  rows.sort(function(a,b){
    var av=parseCell(th,a.children[idx].textContent);
    var bv=parseCell(th,b.children[idx].textContent);
    var cmp=av<bv?-1:(av>bv?1:0);
    return asc?-cmp:cmp;
  });
  rows.forEach(function(r){tbody.appendChild(r);});
}
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('table.summary thead th.sortable').forEach(function(th){
    th.addEventListener('click',function(){sortSummary(th);});
  });
  document.querySelectorAll('.dive-row').forEach(function(row){
    row.addEventListener('click',function(){
      var id=row.getAttribute('data-dive');
      var body=document.getElementById('dive-'+id);
      if(!body)return;
      var open=body.classList.contains('open');
      document.querySelectorAll('.dive-body.open').forEach(function(r){r.classList.remove('open');});
      document.querySelectorAll('.dive-row').forEach(function(r){r.style.background='';});
      if(!open){
        body.classList.add('open');
        row.style.background='rgba(0,53,107,0.06)';
      }
    });
  });
});
"""


def _build_compare_header(runs: list[ModelRun], root_name: str) -> str:
    subtitle = f"{len(runs)} model runs compared"
    if root_name:
        subtitle += f" · {root_name}"
    subtitle += f" · {sum(len(run.results) for run in runs)} indicator runs total"
    chips = "".join(
        f'<span class="chip" style="background:#e8eaf6;color:#3949ab;border-color:#3949ab30">'
        f"{_escape(run.name)}</span>"
        for run in runs
    )
    return f"""<div class="header">
<div class="tla-badge">MODEL COMPARISON</div>
<div class="subtitle">{_escape(subtitle)}</div>
<div class="chips">{chips}</div>
</div>"""


def _build_summary_section(runs: list[ModelRun]) -> str:
    def confirmed_count(run: ModelRun) -> int:
        return _verdict_counts(run.all_verifications).get("confirmed", 0)

    ordered = sorted(runs, key=confirmed_count, reverse=True)

    head = (
        "<tr>"
        '<th class="sortable" data-type="str">Model</th>'
        '<th class="sortable" data-type="str">Dir</th>'
        '<th class="sortable" data-type="num">Indicators</th>'
        '<th class="sortable" data-type="num">Hypotheses</th>'
        '<th class="sortable" data-type="num">Verified</th>'
        '<th class="sortable" data-type="num">Confirmed</th>'
        '<th class="sortable" data-type="num">Partial</th>'
        '<th class="sortable" data-type="num">Inconcl.</th>'
        '<th class="sortable" data-type="num">Rejected</th>'
        '<th class="sortable" data-type="num">0-hyp inds</th>'
        '<th class="sortable" data-type="num">Conf. rate</th>'
        "</tr>"
    )

    rows = []
    for run in ordered:
        hyps = run.all_hypotheses
        vrs = run.all_verifications
        counts = _verdict_counts(vrs)
        zero_hyp_tlas = [
            t for t, pr in run.results.items()
            if not (pr.research_output and pr.research_output.hypotheses)
        ]
        conf_rate = f"{counts['confirmed'] / len(vrs):.0%}" if vrs else "—"

        verdict_cells = ""
        for v in VERDICT_ORDER:
            _, fg, _ = _verdict_color(v)
            verdict_cells += (
                f'<td style="color:{fg};font-weight:600">{counts[v]}</td>'
            )

        rows.append(
            f"<tr>"
            f'<td class="name-col">{_escape(run.name)}</td>'
            f'<td class="dir-col">{_escape(run.dir_path.name)}</td>'
            f"<td>{len(run.results)}</td>"
            f"<td>{len(hyps)}</td>"
            f"<td>{len(vrs)}</td>"
            f"{verdict_cells}"
            f"<td>{len(zero_hyp_tlas)}</td>"
            f"<td>{conf_rate}</td>"
            f"</tr>"
        )

    return f"""<div class="section">
<h2 class="section-title">Summary</h2>
<div class="matrix-wrap">
<table class="summary"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>
</div>
</div>"""


def _build_matrix_section(runs: list[ModelRun], all_tlas: list[str], model_names: list[str]) -> str:
    head = "<tr><th>Indicator</th>" + "".join(f"<th>{_escape(n)}</th>" for n in model_names) + "</tr>"
    rows = []
    for tla in all_tlas:
        cells = []
        for run in runs:
            pr = run.results.get(tla)
            if pr is None:
                cells.append('<td><span class="cell-empty">—</span></td>')
                continue
            hyps = pr.research_output.hypotheses if pr.research_output else []
            vrs = {vr.hypothesis_id: vr for vr in pr.verification_results}
            counts = _verdict_counts(list(vrs.values()))
            n_hyps = len(hyps)
            if n_hyps == 0:
                cells.append('<td><span class="cell-zero">0 hyps</span></td>')
                continue
            dom = _dominant_verdict(counts)
            bg, fg, bd = _verdict_color(dom or "inconclusive")
            short = " ".join(
                f"{VERDICT_SHORT[v]}{counts[v]}" for v in VERDICT_ORDER if counts.get(v)
            )
            cells.append(
                f'<td style="background:{bg}22">'
                f'<span class="cell-count" style="color:{fg}">{n_hyps}</span>'
                f'<span class="cell-verdicts">{short}</span>'
                f"</td>"
            )
        name = _indicator_name(tla)
        label = f'<span style="font-weight:700;color:#00356B">{tla}</span>'
        if name and name != tla:
            label += f'<br><span style="font-size:10px;color:#8a8a8a">{_escape(name)}</span>'
        rows.append(f"<tr><td>{label}</td>{''.join(cells)}</tr>")

    return f"""<div class="section">
<h2 class="section-title">Indicator x Model Matrix</h2>
<div class="matrix-wrap">
<table class="matrix"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>
</div>
</div>"""


def _build_shared_section(runs: list[ModelRun], all_tlas: list[str], model_names: list[str]) -> str:
    """Show hypotheses that multiple models proposed for the same indicator."""
    blocks = []
    for tla in all_tlas:
        # key → list of (run_index, hyp, vr)
        groups: dict[str, list[tuple[int, ProxyHypothesis, VerificationResult | None]]] = {}
        for i, run in enumerate(runs):
            pr = run.results.get(tla)
            if not pr or not pr.research_output:
                continue
            vr_map = {vr.hypothesis_id: vr for vr in pr.verification_results}
            for hyp in pr.research_output.hypotheses:
                groups.setdefault(_proxy_key(hyp), []).append((i, hyp, vr_map.get(hyp.id)))

        shared = {k: v for k, v in groups.items() if len({i for i, _, _ in v}) > 1}
        if not shared:
            continue

        rows = []
        for key, items in sorted(shared.items(), key=lambda kv: (len(kv[1]), kv[0])):
            proxy_name = items[0][1].proxy_variable
            if items[0][1].db_variable_id:
                proxy_name += f" <span style='color:#8a8a8a;font-size:10px'>({_escape(items[0][1].db_variable_id)})</span>"
            verdict_cells = []
            verdicts = []
            for i, run in enumerate(runs):
                found = next((it for it in items if it[0] == i), None)
                if found is None:
                    verdict_cells.append('<td style="color:#c9c7c0">—</td>')
                    continue
                hyp, vr = found[1], found[2]
                if vr is None:
                    verdict_cells.append('<td><span class="cell-zero">not verified</span></td>')
                    continue
                bg, fg, bd = _verdict_color(vr.verdict.value)
                verdict_cells.append(
                    f'<td><span class="verdict-badge" style="background:{bg};color:{fg};border-color:{bd}">'
                    f"{_escape(vr.verdict.value.replace('_', ' '))}</span></td>"
                )
                verdicts.append(vr.verdict.value)
            n_models = len({i for i, _, _ in items})
            badge = ""
            if len(set(verdicts)) == 1:
                badge = '<span class="agree-badge">agree</span>'
            elif verdicts:
                badge = '<span class="disagree-badge">disagree</span>'
            rows.append(
                f"<tr><td class='proxy-col'>{proxy_name} "
                f"<span style='color:#8a8a8a;font-size:10px'>({n_models} models)</span>{badge}</td>"
                + "".join(verdict_cells)
                + "</tr>"
            )

        name = _indicator_name(tla)
        blocks.append(f"""<h4 style="margin:16px 0 8px;color:#00356B;font-size:13px">
{tla} — {_escape(name if name != tla else '')}</h4>
<table class="dive-table">
<thead><tr><th>Proxy</th>{"".join(f"<th>{_escape(n)}</th>" for n in model_names)}</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>""")

    if not blocks:
        return """<div class="section">
<h2 class="section-title">Shared-Proxy Agreement</h2>
<p class="no-shared">No hypotheses were proposed by more than one model.</p>
</div>"""
    return f"""<div class="section">
<h2 class="section-title">Shared-Proxy Agreement</h2>
{''.join(blocks)}
</div>"""


def _build_deepdive_section(runs: list[ModelRun], all_tlas: list[str], model_names: list[str]) -> str:
    rows = []
    for tla in all_tlas:
        name = _indicator_name(tla)
        label = f"{tla}"
        if name and name != tla:
            label += f" — {_escape(name)}"
        covered = [run.name for run in runs if tla in run.results]
        rows.append(
            f'<tr class="dive-row" data-dive="{tla}"><td style="font-weight:700;color:#00356B">{label}</td>'
            f'<td style="color:#8a8a8a;font-size:12px">{_escape(", ".join(covered))}</td></tr>'
        )
        rows.append(f'<tr class="dive-body" id="dive-{tla}"><td colspan="2"><div class="dive-panel">')
        rows.append(_build_tla_detail(runs, tla, model_names))
        rows.append("</div></td></tr>")

    return f"""<div class="section">
<h2 class="section-title">Per-Indicator Detail</h2>
<table class="dive-table">
<thead><tr><th>Indicator</th><th>Models</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
</div>"""


def _build_tla_detail(runs: list[ModelRun], tla: str, model_names: list[str]) -> str:
    blocks = []
    for run in runs:
        pr = run.results.get(tla)
        if pr is None:
            continue
        hyps = pr.research_output.hypotheses if pr.research_output else []
        vr_map = {vr.hypothesis_id: vr for vr in pr.verification_results}
        if not hyps:
            blocks.append(
                f'<div class="run-block"><div class="run-heading">{_escape(run.name)}</div>'
                f'<p class="no-shared">No hypotheses generated.</p></div>'
            )
            continue
        body_rows = []
        for hyp in hyps:
            vr = vr_map.get(hyp.id)
            body_rows.append(_build_detail_row(run.name, hyp, vr))
        blocks.append(
            f'<div class="run-block"><div class="run-heading">{_escape(run.name)}</div>'
            f'<table class="dive-table">'
            f"<thead><tr><th>ID</th><th>Proxy</th><th>Verdict</th><th>r</th><th>p</th><th>n</th></tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table></div>"
        )
    return "".join(blocks)


def _build_detail_row(model_name: str, hyp: ProxyHypothesis, vr: VerificationResult | None) -> str:
    from epi_proxy.report import _build_detail_panel

    row_id = f"{_slug(model_name)}-{_escape(hyp.id)}"

    if vr is None:
        return (
            f'<tr class="summary-row not-verified" data-id="{row_id}">'
            f"<td>{_escape(hyp.id)}</td>"
            f'<td class="proxy-col">{_escape(hyp.proxy_variable)}</td>'
            f'<td><span class="verdict-badge" style="background:#f5f5f5;color:#8a8a8a;border-color:#8a8a8a40">not verified</span></td>'
            f"<td>—</td><td>—</td><td>—</td>"
            f"</tr>"
            f'<tr class="detail-row" id="detail-{row_id}"><td colspan="6">{_build_detail_panel(hyp, None)}</td></tr>'
        )

    bg, fg, bd = _verdict_color(vr.verdict.value)
    verdict_html = (
        f'<span class="verdict-badge" style="background:{bg};color:{fg};border-color:{bd}">'
        f"{_escape(vr.verdict.value.replace('_', ' '))}</span>"
    )
    r_val = _fmt(vr.raw_correlation.pearson_r) if vr.raw_correlation else "—"
    p_val = _fmt(vr.raw_correlation.pearson_p, ".2e") if vr.raw_correlation else "—"
    n_val = str(vr.raw_correlation.n_observations) if vr.raw_correlation and vr.raw_correlation.n_observations else "—"
    return (
        f'<tr class="summary-row" data-id="{row_id}">'
        f"<td>{_escape(hyp.id)}</td>"
        f'<td class="proxy-col">{_escape(hyp.proxy_variable)}</td>'
        f"<td>{verdict_html}</td><td>{r_val}</td><td>{p_val}</td><td>{n_val}</td>"
        f"</tr>"
        f'<tr class="detail-row" id="detail-{row_id}"><td colspan="6">{_build_detail_panel(hyp, vr)}</td></tr>'
    )
