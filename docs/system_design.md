# EPI Proxy Discovery Pipeline — System Design

**Status:** Living document · **Last updated:** 2026-06-09 · **Audience:** developers joining the project, and reviewers who need the full system picture.

This document describes the architecture of the EPI Proxy Discovery Pipeline: what it does, how data flows through it, how the components fit together, and how a new developer should get oriented. It is meant to be read top to bottom on day one, then used as a reference.

For the *why* behind specific design choices (verdict thresholds, control variables, the partial-correlation logic), see `docs/pipeline_walkthrough.md`. For domain context on the EPI itself, see `CLAUDE.md`.

---

## 1. What the System Does

The Yale **Environmental Performance Index (EPI)** ranks 180 countries across 58+ environmental indicators. Many of those indicators are weak: poor country coverage, infrequent updates, or values that are *modeled/imputed* rather than directly measured. (Example: the Waste Recovery Rate indicator, WRR, has 56 countries imputed.)

The pipeline's job is to **discover and statistically validate "data proxies"** — alternative, more readily available datasets that correlate with a hard-to-measure EPI indicator and could supplement or validate it.

> **Worked example.** Anti-diarrheal medication sales correlate with water-quality problems, so pharmaceutical trade data could serve as a proxy for the "Unsafe Drinking Water" (UWD) indicator.

The system is a **two-stage multi-agent pipeline**:

- **Stage 1 — Discovery (hypothesis generation).** A tool-using Claude agent explores real data APIs (World Bank, WHO, NASA POWER, etc.), fetches candidate proxy datasets into a local database, and emits structured *proxy hypotheses*.
- **Stage 2 — Verification (hypothesis testing).** For each hypothesis, the system runs a statistical protocol (bivariate + partial correlation, functional-form fitting) and assigns a verdict: `confirmed`, `partially_confirmed`, `inconclusive`, or `rejected`. A lightweight validation agent then audits each result against inclusion criteria.

Outputs are aggregated into a JSON result and an HTML dashboard, and (optionally) compiled into a knowledge graph for cross-indicator reasoning.

---

## 2. Workflow in Plain Language

A run targets **one EPI indicator** at a time, identified by its three-letter abbreviation (TLA), e.g. `WRR`.

1. **Kickoff.** The operator runs the CLI (`python -m src -i WRR`) or clicks "Run Pipeline" in the web UI. The orchestrator loads the indicator's metadata (description, units, source, polarity) from the EPI master variable list.

2. **Seed the database.** Before discovery starts, the orchestrator loads the *target* indicator's raw data and the standard *control variables* (GDP per capita, population, urbanization) into a local DuckDB. This guarantees the agent always has the target and controls available for correlation.

3. **Discovery agent explores (Stage 1).** A Claude agent is given the indicator, its domain context (for Tier-1 indicators), and a toolbox of ~30 data tools. It loops: *search* a source for relevant series → *preview* candidates → *fetch and store* promising ones into the DB → optionally *pre-correlate* against the target. The agent runs until it is satisfied or hits its tool-call budget (default 80). It then emits a JSON block of **proxy hypotheses** — each one a structured claim: "proxy variable X relates to target Y in direction D with functional form F, sourced from dataset Z."

4. **Parse & repair.** The agent's JSON is parsed into `ProxyHypothesis` objects. Because LLMs invent enum values ("high" confidence, "monthly" frequency), an enum-repair table coerces known-bad values to valid ones *before* validation, so one bad field doesn't drop an otherwise-good hypothesis.

5. **(Optional) human review.** With `--review`, the operator sees a table of hypotheses and picks which to verify.

6. **Verification (Stage 2).** Hypotheses are partitioned by `evidence_type` and processed sequentially:
   - **`programmatic_verify`** — data is fetchable/already-fetched. If the proxy data was already stored in the DB during discovery, a **deterministic statistics pipeline** runs directly against the DB (no agent). Otherwise a **Claude Code agent** writes and runs a `verify.py` that downloads the data and runs the shared statistics library.
   - **`manual_data_needed`** — an *exploratory* agent attempts to locate the data.
   - **`literature_attested`** — a *corroboration* agent assesses the literature claim without requiring fresh data.

7. **Statistical protocol.** For each verifiable hypothesis the system computes Pearson + Spearman correlation, partial correlation controlling for GDP/pop/urbanization (does the proxy add signal beyond what the existing imputation model already captures?), and fits linear/log-linear/quadratic forms (best by AIC). A decision tree maps these to a verdict.

8. **Validation gate.** A cheap Claude (Haiku) validator scores each result against 10 inclusion criteria (spatial completeness, open access, recency, methodology provenance, signal independence, …). Depending on the binding mode (`advisory` / `soft_gate` / `hard_gate`), failing a *critical* criterion can downgrade the verdict.

9. **Aggregate & report.** All results roll up into `pipeline_result.json` and an HTML dashboard. Everything is written under `outputs/{TLA}/`.

10. **(Post-hoc) knowledge graph.** A standalone script compiles all indicator outputs into a NetworkX graph and runs clingo ASP reasoning over it (e.g. transitive proxy relationships, shared-driver detection). This never modifies the pipeline — it's an analysis layer.

---

## 3. Component Diagram

```
                                  ┌──────────────────────────────────────────────┐
                                  │                 ENTRY POINTS                   │
                                  │                                                │
                                  │   CLI: python -m src -i WRR                    │
                                  │   Web: web/app.py  (Gradio, HF Spaces)         │
                                  └───────────────────────┬────────────────────────┘
                                                          │
                                                          v
                              ┌────────────────────────────────────────────────────┐
                              │            src/orchestrator.py                       │
                              │   run_pipeline() / run_pipeline_headless()           │
                              │   • load metadata   • seed DB   • route stages       │
                              │   • aggregate → PipelineResult   • build dashboard    │
                              └───────┬───────────────────────────────┬──────────────┘
                                      │                               │
              ┌───────────────────────┘                               └───────────────────────┐
              v                                                                                 v
┌─────────────────────────────────────┐                       ┌──────────────────────────────────────────┐
│         STAGE 1 — DISCOVERY          │                        │            STAGE 2 — VERIFICATION          │
│  src/stage1/discovery.py             │                        │  src/stage2/verifier.py                    │
│                                      │                        │                                            │
│  Claude agent loop (Sonnet 4.6):     │                        │  Partition hypotheses by evidence_type:    │
│    search → preview → fetch → corr   │                        │   ┌─ programmatic_verify                   │
│    (≤ DISCOVERY_MAX_TOOL_CALLS=80)   │                        │   │    • DB-backed (deterministic) ──┐      │
│                                      │                        │   │      run_full_verification()      │     │
│  Tools (src/stage1/tools.py, 30):    │                        │   │    • else Claude Code agent       │     │
│   3 per source × 9 sources + 3 DB    │                        │   │      writes & runs verify.py      │     │
│        │                             │                        │   ├─ manual_data_needed → exploratory     │
│        v                             │                        │   └─ literature_attested → corroboration   │
│  src/utils/data_fetch.py             │                        │            │                               │
│   World Bank · WHO GHO · NASA POWER  │                        │            v                               │
│   Comtrade · Wikipedia · OpenAQ      │                        │  src/utils/stats.py + db_stats.py          │
│   GEE · GDELT(BQ) · FAOSTAT(offline) │                        │   bivariate · partial · functional form    │
│        │                             │                        │   → determine_verdict()                    │
│        v   parse + enum-repair       │                        │            │                               │
│  ResearchOutput{ ProxyHypothesis[] } │ ── hypotheses (JSON) ─> │            v                               │
└──────────────┬───────────────────────┘                       │  src/stage2/validator.py (Haiku 4.5)       │
               │                                                │   10 inclusion criteria → ValidationAnnotation
               │                                                │   inclusion gate (advisory/soft/hard)      │
               │                                                └──────────────────┬─────────────────────────┘
               │                                                                   │
               v                                                                   v
        ┌──────────────────────────────────────────────────────────────────────────────────┐
        │                          CENTRAL DATA LAYER (src/utils/db.py)                       │
        │   DuckDB @ outputs/epi_data.duckdb                                                   │
        │   variables · observations(country,year,value) · fetch_log                          │
        │   register_variable · upsert_observations · align_variables · get_observations       │
        └──────────────────────────────────────────────────────────────────────────────────┘
               │                                                                   │
               v                                                                   v
   ┌─────────────────────────┐                                  ┌──────────────────────────────────────┐
   │  EPI reference data      │                                   │            OUTPUTS                      │
   │  docs/EPI2024_Work/      │                                   │  outputs/{TLA}/                         │
   │   Inputs/  Raw/{TLA}_raw │                                   │   pipeline_result.json · dashboard.html │
   │   POutputs/ ...          │                                   │   pipeline.log                          │
   │  (loaded via data_utils) │                                   │   stage1/{discovery_output,hypotheses}  │
   └─────────────────────────┘                                   │   stage2/{HYP-ID}/{verify.py,result.json}
                                                                  └──────────────────────────────────────┘
                                                                                   │
                                                                                   v
                              ┌────────────────────────────────────────────────────────────────────┐
                              │   POST-HOC: KNOWLEDGE GRAPH (src/knowledge_graph/)                    │
                              │   scripts/compile_knowledge_graph.py                                  │
                              │   NetworkX graph  ──>  clingo ASP reasoning  ──>  outputs/knowledge_graph/
                              │   (does NOT modify the pipeline — read-only analysis)                 │
                              └────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Reference

### Orchestration
| File | Responsibility |
|---|---|
| `src/orchestrator.py` | CLI entry (`main`), `run_pipeline()` (interactive), `run_pipeline_headless()` (Gradio generator). Loads metadata, seeds DB, routes stages, aggregates, triggers dashboard. |
| `src/__main__.py` | Makes `python -m src` work. |
| `src/config.py` | All paths, model names, thresholds, and tunables. **Start here when changing behavior.** |
| `web/app.py` | Gradio UI: tabs for Reports, Knowledge Graph, Presentations, Pipeline Runner, Indicator Reference. Wraps `run_pipeline_headless()`. |

### Stage 1 — Discovery
| File | Responsibility |
|---|---|
| `src/stage1/discovery.py` | The agent loop. Seeds target + control variables into DB, runs the tool-use loop, parses + enum-repairs the final JSON into `ResearchOutput`. |
| `src/stage1/tools.py` | 30 tool definitions handed to the agent: `search_/preview_/fetch_and_store_` × 9 sources, plus 3 DB tools. `execute_tool()` dispatches. |
| `src/stage1/prompts.py` | `DISCOVERY_SYSTEM_PROMPT` + user template. |
| `src/utils/data_fetch.py` | The 9 source families. Each exposes `search_*` / `preview_*` / `fetch_*` / `fetch_and_store_*`. This is where external-API quirks live. |
| `src/domain_knowledge.py` | TLA → domain-context strings (definition, imputation model, confounders, data-quality issues) for Tier-1 indicators. Injected into the discovery prompt. |

### Stage 2 — Verification
| File | Responsibility |
|---|---|
| `src/stage2/verifier.py` | `verify_hypothesis()` (Claude Code agent path) and `verify_hypothesis_from_db()` (deterministic path via `db_stats.run_full_verification`). Parses `result.json` into `VerificationResult`. |
| `src/stage2/data_loader.py` | `prepare_verification_context()` — coverage stats + file paths formatted for the agent prompt. |
| `src/stage2/prompts.py` | Verification / corroboration / exploratory prompt builders + the validator prompt. |
| `src/stage2/validator.py` | Post-verification validation; 10 inclusion criteria; inclusion-gate logic (incl. GDP-imputation-dependent escalation for WRR). |
| `src/utils/stats.py` | `run_bivariate_correlation`, `run_partial_correlation` (pingouin), `test_functional_form` (AIC), `determine_verdict`, `build_result_json`. |
| `src/utils/db_stats.py` | `run_full_verification()` — the deterministic, DB-backed equivalent of the agent's `verify.py`. |

### Shared data layer
| File | Responsibility |
|---|---|
| `src/utils/db.py` | DuckDB: `variables`, `observations`, `fetch_log`. Connection mgmt, `register_variable`, `upsert_observations`, `align_variables`, `get_observations`. |
| `src/utils/data_utils.py` | `load_raw_indicator()` (wide→long, sentinel→NaN), `load_variable_metadata()`, `get_available_indicators()`. |
| `src/utils/country_align.py`, `country_codes.py` | Country-name/ISO reconciliation across sources. |
| `src/schemas.py` | All Pydantic v2 models (see §5). |

### Knowledge graph (post-hoc)
| File | Responsibility |
|---|---|
| `src/knowledge_graph/builder.py` | `GraphBuilder` — pipeline outputs → NetworkX graph. |
| `src/knowledge_graph/reasoning.py` | `ReasoningEngine` + `run_reasoning()` — clingo ASP inference. |
| `src/knowledge_graph/{export,visualize,queries,graph,schema}.py` | Export (json/graphml/html), Cytoscape viz, queries, graph model. |
| `scripts/compile_knowledge_graph.py` | Standalone driver → `outputs/knowledge_graph/`. |

---

## 5. Core Data Contracts (`src/schemas.py`)

The hypothesis schema is the **contract between Stage 1 and Stage 2**. Stage 1 produces it; Stage 2 consumes it.

```
ProxyHypothesis            ← Stage 1 output / Stage 2 input
  ├── context: Context           (geographic_scope, time_period)
  ├── relationship: Relationship (direction, functional_form, strength_estimate)
  ├── data_source: DataSource    (name, url, accessibility, methodology_status, update_frequency, coverage)
  ├── evidence_type              (programmatic_verify | literature_attested | manual_data_needed)  → routes Stage 2
  ├── confidence                 (speculative | literature_backed | expert_opinion)
  └── db_variable_id             (set if data was fetched during discovery → enables DB-backed verification)

VerificationResult         ← Stage 2 output (one per hypothesis)
  ├── verdict                    (confirmed | partially_confirmed | inconclusive | rejected)
  ├── verification_method        (statistical_test | literature_accepted | pending_data | ...)
  ├── raw_correlation: CorrelationResult           (pearson_r/p, spearman_rho/p, n_obs, n_countries)
  ├── partial_correlation: PartialCorrelationResult (partial_r/p, control_variables)
  ├── functional_form: FunctionalFormResult         (best_form + R²/AIC per form)
  └── validation: ValidationAnnotation              (issues[], inclusion_score: InclusionCriteriaScore)

PipelineResult             ← final aggregated artifact
  ├── research_output: ResearchOutput  (hypotheses[] + causal_map_summary)
  └── verification_results: VerificationResult[]
```

**The verdict decision tree** (`determine_verdict` in `stats.py`, thresholds in `config.py`):
`n < 20` → inconclusive · direction mismatch → rejected · `p > 0.10` → rejected · `0.05 < p < 0.10` → inconclusive · `|r| > 0.3 ∧ p < 0.05 ∧ partial significant` → confirmed · bivariate significant but partial not → partially_confirmed.

---

## 6. Developer Onboarding

This section gets a new developer from zero to a working run and a mental model of where to make changes.

### 6.1 Prerequisites & environment

- **Always use the `epi` conda environment** for any code execution or package installs. This is a hard project rule:
  ```bash
  conda activate epi          # or prefix commands with: conda run -n epi <cmd>
  pip install -e .            # installs the package + deps from pyproject.toml
  ```
- **API keys** live in `.env` (copy from `.env.example`). The only *required* key is `ANTHROPIC_API_KEY`. Optional keys unlock specific discovery sources:
  | Var | Source | Notes |
  |---|---|---|
  | `ANTHROPIC_API_KEY` | All agents | **Required.** |
  | `COMTRADE_API_KEY` | UN Comtrade | Free, 500 req/day. |
  | `OPENAQ_API_KEY` | OpenAQ v3 | Free, 2000 req/day; a full backfill exceeds it. |
  | `GEE_PROJECT` | Google Earth Engine | Needs `earthengine authenticate` first (not an API key). |
  | `GOOGLE_APPLICATION_CREDENTIALS` | GDELT (BigQuery) | Service-account JSON; billing must be enabled. |
  | *(none)* | World Bank, WHO GHO, NASA POWER, Wikipedia | No auth. |
  - FAOSTAT is currently **offline** — its tools short-circuit with a clear error by design.

### 6.2 First runs (in order)

```bash
# 1. See the universe of indicators you can target
python -m src --list-indicators

# 2. Cheapest end-to-end smoke test: skip Stage 1, verify hand-made hypotheses
python -m src -i WRR --stage 2 --hypotheses-file outputs/WRR/test_hypotheses.json

# 3. Full pipeline on one indicator (this calls the LLM agents — costs money, ~20 min)
python -m src -i WRR

# 4. With a human-in-the-loop hypothesis review gate
python -m src -i WRR --review

# 5. The web UI (what HF Spaces serves)
python web/app.py        # → http://localhost:7860
```

Useful flags: `--stage {1,2,both}`, `--max-hypotheses N`, `--max-tool-calls N`, `--inclusion-mode {advisory,soft_gate,hard_gate}`, `--verbose`.

### 6.3 Where things land

Everything for a run is under `outputs/{TLA}/`:
```
outputs/WRR/
├── pipeline.log              # timestamped log (NOTE: appends across runs, no rotation)
├── pipeline_result.json      # the aggregated PipelineResult
├── dashboard.html            # human-facing report
├── stage1/
│   ├── discovery_output.json # raw agent final text + full tool-call log (great for debugging)
│   └── hypotheses.json       # parsed ResearchOutput
└── stage2/{HYP-ID}/
    ├── verify.py             # agent-written analysis (agent path only)
    ├── result.json           # structured stats + verdict
    └── agent_output.txt       # raw agent transcript
```
The shared DuckDB lives at `outputs/epi_data.duckdb` and persists *across* runs — discovery accumulates variables there.

### 6.4 How to read the codebase (suggested order)

1. `src/config.py` — every knob in one place.
2. `src/schemas.py` — the data contracts; everything else moves these objects around.
3. `src/orchestrator.py` — the spine; trace `run_pipeline()` top to bottom.
4. `src/stage1/discovery.py` then `src/stage1/tools.py` — the agent loop and its toolbox.
5. `src/stage2/verifier.py` + `src/utils/stats.py` — the two verification paths and the math.
6. `src/utils/db.py` — the data layer the two stages share.
7. `docs/pipeline_walkthrough.md` — a concrete WRR trace with real numbers and rationale.

### 6.5 Making common changes

- **Tune verdict behavior** → thresholds in `config.py` (`VERDICT_*`) and the tree in `stats.determine_verdict()`.
- **Add a discovery data source** → add `search_/preview_/fetch_and_store_` functions in `data_fetch.py`, register the 3 tool schemas in `stage1/tools.py`, and wire dispatch in `execute_tool()`.
- **Add domain context for a new indicator** → add a TLA entry in `domain_knowledge.py` (process documented in `docs/domain_knowledge_process.txt`).
- **Change inclusion gating** → `config.INCLUSION_*` and `stage2/validator.py`. `INCLUSION_CRITICAL_CRITERIA` is currently `[spatial_completeness, open_access]`; methodology is advisory as of 2026-04-13.
- **Add a UI surface** → a `gr.Tab` in `web/app.py` `build_app()`.

### 6.6 Gotchas (learned the hard way — see `CLAUDE.md`)

- **HF Spaces deploy pushes to `main`, not `master`:** `git push hf master:main`. HF reads from `main`.
- **Claude Code verification agent `cwd` must be `PROJECT_ROOT`** (not the output dir) or `from src.utils.stats import ...` fails and agents reimplement the stats badly. (Root cause of an early class of failures.)
- **LLM enum drift is expected:** the discovery parser repairs invalid enum values before Pydantic validation; don't "fix" it by tightening the prompt alone.
- **`test_functional_form()` only logs X, not Y** — so log-of-Y imputation models (like WRR's) can read as "quadratic." Known limitation.
- **NetworkX `write_graphml` fails on Pydantic enums** — flatten to `.value` strings before export.
- **Cytoscape `tap` events conflict with COSE layout animation** — use `click` events.
- **Gemini Deep Research (legacy Stage 1) cost ~$4/call.** The current Stage 1 is the tool-using Claude agent, which is cheaper; `pipeline_walkthrough.md` predates the migration and still references Perplexity/Gemini — treat `discovery.py` as the source of truth.

### 6.7 Running the knowledge graph

```bash
conda run -n epi python scripts/compile_knowledge_graph.py
# → outputs/knowledge_graph/{graph.json, graph.html, graph.graphml, summary.md}
```
It reads existing `outputs/{TLA}/pipeline_result.json` files; run the pipeline on a few indicators first. It is strictly read-only w.r.t. the pipeline.

---

## 7. Cross-Cutting Notes

- **Cost & latency.** Stage 1 is the tool-using agent (bounded by `DISCOVERY_MAX_TOOL_CALLS`). Stage 2's deterministic DB path is free; the agent fallback path costs LLM tokens. A full run is ~20 min wall time.
- **Determinism.** Wherever data is already in the DB, verification is deterministic (`db_stats.run_full_verification`). The LLM agent is only a fallback for data that wasn't fetched during discovery or for literature/manual hypotheses.
- **Idempotency.** `upsert_observations` makes re-loading a variable safe; the DB is a persistent cache across runs.
- **EPI data conventions.** Raw CSVs are wide (one column per year, e.g. `WRR.raw.2015`); missing-value sentinels `{-9999, -8888, -7777}` are replaced with `NaN` on load. 180 countries are tracked.
```
