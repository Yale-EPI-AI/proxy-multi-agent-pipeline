# EPI Proxy Discovery Pipeline — System Design

**Status:** Living document · **Last updated:** 2026-08-29 · **Audience:** developers joining the project, and reviewers who need the full system picture.

This document describes the architecture of the EPI Proxy Discovery Pipeline: what it does, how data flows through it, how the components fit together, and how a new developer should get oriented. It is meant to be read top to bottom on day one, then used as a reference.

For domain context on the EPI itself, see `CLAUDE.md` and `src/domain_knowledge.py`.

---

## 1. What the System Does

The Yale **Environmental Performance Index (EPI)** ranks 180 countries across 58+ environmental indicators. Many of those indicators are weak: poor country coverage, infrequent updates, or values that are *modeled/imputed* rather than directly measured. (Example: the Waste Recovery Rate indicator, WRR, has 56 countries imputed.)

The pipeline's job is to **discover and statistically validate "data proxies"** — alternative, more readily available datasets that correlate with a hard-to-measure EPI indicator and could supplement or validate it.

> **Worked example.** Anti-diarrheal medication sales correlate with water-quality problems, so pharmaceutical trade data could serve as a proxy for the "Unsafe Drinking Water" (UWD) indicator.

The system is a **two-stage multi-agent pipeline**:

- **Stage 1 — Discovery (hypothesis generation).** A tool-using LLM discovery agent explores real data APIs (World Bank, WHO, NASA POWER, etc.), fetches candidate proxy datasets into a local DuckDB, and emits structured *proxy hypotheses*.
- **Stage 2 — Verification & Validation (hypothesis testing).** For each hypothesis, the system runs a statistical protocol (bivariate + partial correlation, functional-form fitting) and assigns a verdict: `confirmed`, `partially_confirmed`, `inconclusive`, or `rejected`. A lightweight LLM validation agent then audits each result against 10 inclusion criteria.

Outputs are aggregated into a JSON result and an HTML dashboard, and (optionally) compiled into a knowledge graph for cross-indicator reasoning or cross-model comparison matrices.

---

## 2. Workflow in Plain Language

A run targets **one or more EPI indicators**, identified by three-letter abbreviations (TLAs), e.g. `WRR` or `-I WRR UWD WPC`.

1. **Kickoff & Inference Setup.** The operator runs the CLI (`uv run python -m src -i WRR`) or clicks "Run Pipeline" in the web UI. If local inference is enabled (`USE_LOCAL_INFERENCE=true`), the orchestrator automatically starts and health-checks a local vLLM or SGLang server process. The orchestrator then loads indicator metadata (description, units, source, polarity) from the EPI master variable list.

2. **Seed the database.** Before discovery starts, the orchestrator loads the *target* indicator's raw data and the standard *control variables* (GDP per capita, population, urbanization) into a central DuckDB (`outputs/epi_data.duckdb`). This guarantees the agent always has the target and controls available for correlation.

3. **Discovery agent explores (Stage 1).** The discovery agent (`src/stage1/discovery.py`) is given the indicator, its domain context (from `src/domain_knowledge.py`), and a toolbox of ~30 data tools. It loops: *search* a source for relevant series → *preview* candidates → *fetch and store* promising ones into the DB → optionally *pre-correlate* against the target. The agent runs until it is satisfied or hits its tool-call budget (default 80). It then emits a JSON block of **proxy hypotheses** — each one a structured claim: "proxy variable X relates to target Y in direction D with functional form F, sourced from dataset Z."

4. **Parse & repair.** The agent's JSON is parsed into `ProxyHypothesis` objects. Because LLMs occasionally invent enum values ("high" confidence, "monthly" frequency), an enum-repair table coerces known-bad values to valid ones *before* validation, preventing dropped hypotheses.

5. **(Optional) human review.** With `--review`, the operator sees a table of hypotheses and interactively selects which to verify.

6. **Verification (Stage 2).** Hypotheses are partitioned by `evidence_type` and processed sequentially:
   - **`programmatic_verify`** — data is fetchable or already fetched. If the proxy data was already stored in the DB during discovery, a **deterministic statistics pipeline** runs directly against DuckDB (`verify_hypothesis_from_db` via `src/utils/db_stats.py`, fast and free of LLM tokens). Otherwise, an **LLM code-generation agent** (`verify_hypothesis` in `src/stage2/verifier.py`) writes a `verify.py` script that downloads the data and runs the shared statistics library, executed via `subprocess.run` with a 3-attempt retry loop on errors.
   - **`manual_data_needed`** — an *exploratory* agent attempts to locate the data and outlines acquisition steps.
   - **`literature_attested`** — a *corroboration* agent assesses the literature claim and reported effect size without requiring fresh data.

7. **Statistical protocol.** For each verifiable hypothesis, the system computes Pearson + Spearman correlation, partial correlation controlling for GDP/pop/urbanization (does the proxy add signal beyond existing imputation models?), and fits linear/log-linear/quadratic forms (best by AIC). A decision tree maps these to a verdict.

8. **Validation gate.** A lightweight LLM validator (`src/stage2/validator.py`) scores each result against 10 inclusion criteria (spatial completeness, open access, recency, methodology provenance, signal independence, etc.). Depending on the binding mode (`advisory` / `soft_gate` / `hard_gate`), failing a *critical* criterion can downgrade the verdict.

9. **Aggregate & report.** All results roll up into `pipeline_result.json` and a self-contained HTML `dashboard.html`. Everything is written under `outputs/{TLA}/`.

10. **(Post-hoc) knowledge graph & model comparison.** Standalone scripts compile indicator outputs into a NetworkX graph for clingo ASP reasoning (`scripts/compile_knowledge_graph.py`) or generate cross-model comparison matrix dashboards (`scripts/build_model_comparison.py`).

---

## 3. Stage 1 Deep Dive — Discovery Agent & API Exploration

Stage 1 is responsible for **autonomous hypothesis generation grounded in real-world data**. Rather than performing unconstrained open-ended brainstorming, the Discovery Agent acts as an active data scientist: searching real APIs, previewing metadata, fetching actual time-series observations into DuckDB, and testing preliminary correlations before formalizing hypotheses.

### 3.1 Pre-Seeding Ground Truth and Confounders
Before the discovery agent starts its loop, the orchestrator seeds two critical baselines into the central DuckDB (`outputs/epi_data.duckdb`):
1. **Target Indicator Time Series (`epi:{TLA}`)**: The historical values of the target EPI indicator across all 180 countries and available years (e.g. 1990–2021).
2. **Standard Control Variables (`epi:GPC`, `epi:POP`, `epi:URB`)**:
   - `GPC`: GDP per capita (constant USD).
   - `POP`: Total population.
   - `URB`: Urban population percentage.

Pre-loading these ensures that any candidate proxy dataset fetched by the agent can be immediately joined and statistically compared against both the target and the key socioeconomic confounders.

### 3.2 Domain Knowledge Injection
The agent is primed with structured domain context from `src/domain_knowledge.py` covering all 58 EPI indicators:
- Official indicator definition, mathematical formula, units, and transformation (e.g., $\ln(x)$).
- Imputation methodology and known limitations (e.g., whether the official score relies on regression models).
- Known physical, economic, or geographic confounders.
- Sibling indicator relationships across issue categories.

This prevents the agent from re-discovering trivial facts and focuses its reasoning on novel proxy mechanisms.

### 3.3 The Tool-Use Exploration Loop
The discovery agent operates in an autonomous tool-calling loop (capped by `DISCOVERY_MAX_TOOL_CALLS`, default 80), supported by ~30 tools across **9 data source families**:
- **World Bank Development Indicators**: Global economic, infrastructure, and demographic indicators.
- **WHO Global Health Observatory (GHO)**: Disease burden, mortality rates, and health system metrics.
- **NASA POWER**: Global agro-climatology, precipitation, surface temperature, solar irradiance.
- **UN Comtrade**: International bilateral trade statistics (HS-coded imports/exports).
- **Wikipedia Pageviews**: Public attention and behavioral digital traces per country.
- **OpenAQ v3**: Air quality ground-monitoring sensor measurements.
- **Google Earth Engine (GEE)**: Satellite-derived remote sensing products (Sentinel-5P NO2, Landsat, MODIS).
- **GDELT BigQuery**: Global database of events, language, and tone news coverage metrics.
- **FAOSTAT (Offline fallback)**: Agricultural statistics (short-circuits gracefully when service is offline).

The agent follows an iterative exploration pattern:
1. `search_*`: Query source catalogs for candidate variables matching the causal map.
2. `preview_*`: Inspect temporal coverage, country coverage, and sample values without full download.
3. `fetch_and_store_*`: Download full global time series and register them into DuckDB (`outputs/epi_data.duckdb`).
4. `correlate_variables`: Test in-memory bivariate and partial correlations against the target indicator directly in DuckDB.

### 3.4 Structured Hypothesis Output & Enum Coercion
Upon exhausting its tool budget or satisfying its exploration goals, the agent emits a structured JSON block containing a list of `ProxyHypothesis` objects ($h = \psi(c, v, r)$).

Because LLMs frequently invent natural-language enum variations (e.g., `"high"` for confidence, `"administrative"` for methodology), the parser runs an automated coercion routine (`_repair_hypothesis_enums`) before Pydantic schema validation. This ensures minor string variations are mapped to canonical schema values without discarding high-quality hypotheses.

---

## 4. Stage 2 Deep Dive — Verification vs. Validation

Stage 2 tests and audits candidate hypotheses. A foundational design principle of this pipeline is the **strict architectural separation between Verification and Validation**:

```
                              ┌──────────────────────────────────────────────────┐
                              │            ProxyHypothesis from Stage 1          │
                              └────────────────────────┬─────────────────────────┘
                                                       │
                                                       v
                   ┌────────────────────────────────────────────────────────────────────────┐
                   │                     STEP 1: VERIFICATION (The Math)                    │
                   │  "Does the empirical data support the hypothesized relationship?"       │
                   │                                                                        │
                   │  • Bivariate Pearson (r) & Spearman (ρ) correlation                     │
                   │  • Pingouin partial correlation controlling for log(GDP), Pop, Urban    │
                   │  • Functional form fitting (Linear vs. Log-Linear vs. Quadratic by AIC) │
                   │  • Deterministic Decision Tree Verdict Assignment                      │
                   └───────────────────────────────────┬────────────────────────────────────┘
                                                       │
                                                       │  VerificationResult (Initial Verdict)
                                                       v
                   ┌────────────────────────────────────────────────────────────────────────┐
                   │                     STEP 2: VALIDATION (The Audit)                     │
                   │  "Is this dataset legitimate, independent, robust, and EPI-compliant?" │
                   │                                                                        │
                   │  • 10 Inclusion Criteria Scoring (Spatial, Temporal, Recency, etc.)    │
                   │  • Signal Independence & Imputation-Leakage Audit                      │
                   │  • Binding Inclusion Gate (Advisory / Soft Gate / Hard Gate)           │
                   │  • Verdict Adjustment / Downgrade if Critical Criteria Fail            │
                   └───────────────────────────────────┬────────────────────────────────────┘
                                                       │
                                                       v
                              ┌──────────────────────────────────────────────────┐
                              │      Final VerificationResult + Validation        │
                              └──────────────────────────────────────────────────┘
```

### 4.1 Verification: Quantitative Empirical Testing

**Verification** asks: *"Is the hypothesized statistical relationship empirically true in the observed data?"*

Verification is purely statistical and mathematical. It executes via one of two paths based on the hypothesis `evidence_type`:

#### A. Deterministic DuckDB Path (`verify_hypothesis_from_db`)
- **When used**: Whenever candidate proxy data was already fetched and stored in DuckDB during Stage 1 (`db_variable_id` is set).
- **Why it matters**: Runs instantaneously via `src/utils/db_stats.py`, produces fully deterministic outputs, and consumes zero LLM tokens.
- **Execution**: Aligns `(iso, year)` pairs across proxy, target, and controls directly in SQL, then runs the core statistical battery.

#### B. LLM Script Generation & Execution Path (`verify_hypothesis`)
- **When used**: For hypotheses requiring bespoke transformations, external data downloads, or exploratory routing (`manual_data_needed` / `literature_attested`).
- **Execution**: The LLM writes a standalone `verify.py` script utilizing shared stats utilities (`src.utils.stats`). The script is executed in an isolated subprocess (`subprocess.run`). If errors or timeouts occur, stderr/stdout is fed back to the LLM in a **3-attempt self-correction loop**.

#### C. Statistical Testing Protocol & Verdict Decision Tree
The verification protocol computes:
1. **Bivariate Correlation**: Pearson $r$ (linear) and Spearman $\rho$ (monotonic rank) with $p$-values. Minimum sample size threshold: $n \ge 20$.
2. **Partial Correlation**: Controls for $\log(\text{GDP per capita})$, population, and urbanization using `pingouin.partial_corr`. Minimum sample size: $n \ge 30$. Tests whether the proxy provides signal beyond general economic development.
3. **Functional Form Selection**: Fits Linear ($y = a + bx$), Log-Linear ($y = a + b \ln x$), and Quadratic ($y = a + bx + cx^2$) models; selects the best model minimizing Akaike Information Criterion (AIC).
4. **Deterministic Decision Tree**:
   - $n < 20 \implies$ `inconclusive`
   - Empirical direction opposes hypothesized direction $\implies$ `rejected`
   - $p > 0.10 \implies$ `rejected`
   - $0.05 < p \le 0.10 \implies$ `inconclusive`
   - $|r| > 0.3 \land p < 0.05 \land \text{partial } p < 0.05 \implies$ `confirmed`
   - $|r| > 0.3 \land p < 0.05 \land (\text{partial } p \ge 0.05 \lor \text{unavailable}) \implies$ `partially_confirmed`

---

### 4.2 Validation: Methodological Audit & Inclusion Gating

**Validation** asks: *"Even if the correlation is statistically significant, is this proxy credible, open, methodologically sound, and suitable for the Yale EPI?"*

A proxy might show high correlation ($r = 0.85$) simply because both variables track GDP per capita, or because the dataset is restricted, unmaintained, or has poor global coverage. The Validation Agent (`src/stage2/validator.py`) audits the verification artifacts against **10 EPI Inclusion Criteria**:

| Criterion | Type | Description / Threshold |
|---|---|---|
| `relevance` | Methodological | Does the proxy have a sound, mechanistic causal link to the target indicator? |
| `performance_orientation` | Methodological | Does it measure tangible environmental states or outcomes rather than intentions? |
| `outcome_focus` | Methodological | Measures direct impacts rather than intermediate policy declarations. |
| `documented_methodology` | Provenance | Source has transparent, documented methodology (peer-reviewed, official, or documented sensor/satellite). |
| `verified_results` | Quality | Verification results and data transformations are authentic and free of synthetic data artifacts. |
| `spatial_completeness` | **Critical** | Proxy covers at least **80 countries** globally. |
| `temporal_completeness` | Metric | Proxy contains at least **3 distinct years** of observation. |
| `recency` | Metric | Proxy includes observations from **2018 or newer**. |
| `open_access` | **Critical** | Dataset is publicly and freely accessible for reproducible scientific research. |
| `signal_independence` | Advisory | Proxy correlation remains significant after controlling for log(GDP), population, and urbanization. |

#### Inclusion Binding Modes (`config.INCLUSION_BINDING_MODE`)
The validator can enforce criteria at three configurable levels:
1. **`advisory` (Default)**: Validation issues and inclusion scores ($X/10$) are recorded in `pipeline_result.json` and highlighted on the dashboard, but statistical verdicts remain untouched.
2. **`soft_gate`**: If a hypothesis achieves $< 6/10$ criteria, a `confirmed` verdict is downgraded to `partially_confirmed`.
3. **`hard_gate`**: If a hypothesis fails any **critical criterion** (`spatial_completeness` or `open_access`), the verdict is immediately downgraded to `rejected`.

#### Special Escalation for GDP-Imputed Indicators (`GDP_IMPUTATION_DEPENDENT`)
Several official EPI indicators (notably `WRR` — Waste Recovery Rate) are themselves imputed in the official EPI dataset via cross-sectional regression on $\log(\text{GDP})$. For these indicators, any proxy that fails `signal_independence` is merely re-deriving the imputation model. The validator automatically escalates this failure to a prominent yellow-flag warning in the report.

---

## 5. Component Diagram

```
                                  ┌──────────────────────────────────────────────┐
                                  │                 ENTRY POINTS                   │
                                  │                                                │
                                  │   CLI: uv run python -m src -i WRR             │
                                  │   Web: web/app.py  (Gradio, HF Spaces)         │
                                  └───────────────────────┬────────────────────────┘
                                                          │
                                                          v
                               ┌────────────────────────────────────────────────────┐
                               │            src/orchestrator.py                       │
                               │   run_pipeline() / run_pipeline_headless()           │
                               │   • local_inference_context (vLLM / SGLang)          │
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
│  Tool-calling agent loop:            │                        │  Partition hypotheses by evidence_type:    │
│    search → preview → fetch → corr   │                        │   ┌─ programmatic_verify                   │
│    (≤ DISCOVERY_MAX_TOOL_CALLS=80)   │                        │   │    • DB-backed (deterministic) ──┐      │
│                                      │                        │   │      run_full_verification()      │     │
│  Tools (src/stage1/tools.py, 30):    │                        │   │    • else LLM Script Generator    │     │
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
└──────────────┬───────────────────────┘                       │  src/stage2/validator.py (LLM Auditor)    │
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
   │   (loaded via data_utils)│                                   │   pipeline.log · llm_traces.jsonl       │
   │                          │                                   │   stage1/{discovery_output,hypotheses}  │
   │                          │                                   │   stage2/{HYP-ID}/{verify.py,result.json}
   └─────────────────────────┘                                   └──────────────────────────────────────┘
                                                                                   │
                                                                                   v
                               ┌────────────────────────────────────────────────────────────────────┐
                               │   POST-HOC: KNOWLEDGE GRAPH & COMPARISONS                             │
                               │   scripts/compile_knowledge_graph.py  (NetworkX + clingo ASP)         │
                               │   scripts/build_model_comparison.py   (Cross-model matrix dashboard)  │
                               │   scripts/render_llm_traces.py        (Trace HTML visualizer)         │
                               └────────────────────────────────────────────────────────────────────┘
```

---

## 6. Component Reference

### Orchestration & Local Inference
| File | Responsibility |
|---|---|
| `src/orchestrator.py` | CLI entry (`main`), `run_pipeline()` (interactive/batch), `run_pipeline_headless()` (Gradio generator). Manages engine lifecycle, DB seeding, stage routing, and dashboard export. |
| `src/__main__.py` | Makes `python -m src` work. |
| `src/config.py` | All paths, model names, thresholds, and tunables. **Start here when changing behavior.** |
| `src/utils/inference.py` | `VLLMEngine` and `SGLangEngine` lifecycle managers: background process spawning, port discovery, health-check polling, and shutdown. |
| `src/utils/llm.py` | Unified `LLMClient` supporting Anthropic, OpenAI, and local endpoints with complete trace logging to `llm_traces.jsonl`. |
| `web/app.py` | Gradio UI: tabs for Reports, Knowledge Graph, Presentation [EPI], Presentation [Technical], Pipeline Runner, and Indicator Reference. |

### Stage 1 — Discovery
| File | Responsibility |
|---|---|
| `src/stage1/discovery.py` | Tool-calling agent loop. Seeds target + control variables into DuckDB, runs the tool loop, parses and enum-repairs the final JSON into `ResearchOutput`. |
| `src/stage1/tools.py` | 30 tool definitions handed to the agent: `search_/preview_/fetch_and_store_` × 9 sources, plus 3 DB tools. `execute_tool()` dispatches. |
| `src/stage1/prompts.py` | `DISCOVERY_SYSTEM_PROMPT` + indicator prompt template. |
| `src/utils/data_fetch.py` | The 9 external source families: World Bank, WHO GHO, NASA POWER, Comtrade, Wikipedia, OpenAQ, GEE, GDELT BQ, FAOSTAT. |
| `src/domain_knowledge.py` | Complete domain context for **all 58 EPI indicators** (definition, imputation model, known confounders, data quality issues). Injected into discovery prompt. |

### Stage 2 — Verification & Validation
| File | Responsibility |
|---|---|
| `src/stage2/verifier.py` | `verify_hypothesis_from_db()` (deterministic path via `db_stats.run_full_verification`) and `verify_hypothesis()` (LLM script generation + `subprocess.run` loop). |
| `src/stage2/data_loader.py` | `prepare_verification_context()` — coverage stats + file paths formatted for verification prompts. |
| `src/stage2/prompts.py` | Prompt templates for verification, corroboration, exploratory search, and validation. |
| `src/stage2/validator.py` | Post-verification audit: scores 10 inclusion criteria; applies inclusion gating (`advisory`, `soft_gate`, `hard_gate`) and flags GDP-imputed proxies. |
| `src/utils/stats.py` | Pure computation: `run_bivariate_correlation`, `run_partial_correlation` (pingouin), `test_functional_form` (AIC), `determine_verdict`, `build_result_json`. |
| `src/utils/db_stats.py` | `run_full_verification()` — deterministic DB-backed equivalent of `verify.py`. |

### Reporting & Analysis
| File | Responsibility |
|---|---|
| `src/report.py` | Generates self-contained per-indicator HTML dashboards (`dashboard.html`). |
| `src/report_compare.py` | Generates cross-model comparison dashboards comparing multiple pipeline runs across models and indicators. |
| `scripts/render_llm_traces.py` | Renders `llm_traces.jsonl` into an interactive, readable HTML trace viewer. |
| `scripts/build_model_comparison.py` | Standalone CLI to scan model output folders and produce a comparison dashboard. |

### Shared Data Layer
| File | Responsibility |
|---|---|
| `src/utils/db.py` | Central DuckDB (`outputs/epi_data.duckdb`): tables `variables`, `observations`, `fetch_log`. Connection management, `upsert_observations`, `align_variables`. |
| `src/utils/data_utils.py` | `load_raw_indicator()` (wide→long format, sentinel→NaN), `load_variable_metadata()`, `get_available_indicators()`. |
| `src/utils/country_align.py`, `country_codes.py` | Country name/ISO3 reconciliation across data sources. |
| `src/schemas.py` | All Pydantic v2 data models. |

### Knowledge Graph (Post-Hoc)
| File | Responsibility |
|---|---|
| `src/knowledge_graph/builder.py` | `GraphBuilder` — pipeline outputs → NetworkX graph. |
| `src/knowledge_graph/reasoning.py` | `ReasoningEngine` + `run_reasoning()` — clingo ASP inference. |
| `src/knowledge_graph/{export,visualize,queries,graph,schema}.py` | Export (JSON/GraphML/HTML), Cytoscape.js interactive visualization, graph model. |
| `scripts/compile_knowledge_graph.py` | Standalone driver → `outputs/knowledge_graph/`. |

---

## 7. Core Data Contracts (`src/schemas.py`)

```
ProxyHypothesis            ← Stage 1 output / Stage 2 input
  ├── context: Context           (geographic_scope, time_period, subpopulations)
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

## 8. Developer Onboarding

### 8.1 Prerequisites & Environment

- **Use `uv`** for dependency management and running commands:
  ```bash
  uv sync                     # installs dependencies from pyproject.toml / uv.lock
  ```
- **Unzip reference EPI data** before running the pipeline:
  ```bash
  unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/
  ```
- **API keys** live in `.env` (copy from `.env.example`). `ANTHROPIC_API_KEY` is required for cloud agent runs. Optional keys:
  | Var | Source | Notes |
  |---|---|---|
  | `ANTHROPIC_API_KEY` | Claude models | Required for cloud mode. |
  | `COMTRADE_API_KEY` | UN Comtrade | Free, 500 req/day. |
  | `OPENAQ_API_KEY` | OpenAQ v3 | Free, 2000 req/day. |
  | `GEE_PROJECT` | Google Earth Engine | Needs `earthengine authenticate` first. |
  | `GOOGLE_APPLICATION_CREDENTIALS` | GDELT (BigQuery) | Service account JSON with BigQuery access. |
  | `USE_LOCAL_INFERENCE` | Local models | Set `true` to run local open weights via vLLM/SGLang. |
  | `LOCAL_ENGINE_TYPE` | Local engine | `vllm` or `sglang`. |

### 8.2 Common CLI Commands

```bash
# 0. First-time setup: unzip reference dataset
unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/

# 1. See all available indicators
uv run python -m src --list-indicators

# 2. Run single indicator end-to-end
uv run python -m src -i WRR

# 3. Run multiple indicators in batch
uv run python -m src -I WRR UWD WPC

# 4. Skip Stage 1, verify pre-existing hypotheses
uv run python -m src -i WRR --stage 2 --hypotheses-file outputs/WRR/stage1/hypotheses.json

# 5. Interactive review mode before verification
uv run python -m src -i WRR --review

# 6. Launch the Gradio web dashboard
uv run python web/app.py        # → http://localhost:7860

# 7. Compile the knowledge graph across completed outputs
uv run python scripts/compile_knowledge_graph.py
```

### 8.3 Where Outputs Land

Everything for a run is stored under `outputs/{TLA}/`:
```
outputs/WRR/
├── pipeline.log              # timestamped run log
├── llm_traces.jsonl          # raw prompt/completion traces with token counts
├── pipeline_result.json      # aggregated PipelineResult
├── dashboard.html            # self-contained interactive dashboard
├── stage1/
│   ├── discovery_output.json # agent final text + tool call log
│   └── hypotheses.json       # parsed ResearchOutput
└── stage2/{HYP-ID}/
    ├── verify.py             # generated analysis script (agent path only)
    ├── result.json           # structured statistics and verdict
    ├── validation.json       # 10 inclusion criteria evaluation
    └── agent_output.txt      # agent execution transcript
```
The central DuckDB persists across runs at `outputs/epi_data.duckdb`.

### 8.4 How to Read the Codebase

1. `src/config.py` — configuration, thresholds, model settings.
2. `src/schemas.py` — Pydantic models and data contracts.
3. `src/orchestrator.py` — pipeline spine; trace `run_pipeline()`.
4. `src/stage1/discovery.py` & `src/stage1/tools.py` — tool-use discovery agent loop.
5. `src/stage2/verifier.py`, `src/stage2/validator.py`, & `src/utils/stats.py` — verification and validation logic.
6. `src/utils/db.py` & `src/utils/db_stats.py` — DuckDB data layer and deterministic verification.
7. `src/domain_knowledge.py` — indicator definitions and domain context.

---

## 9. Cross-Cutting Notes

- **Cost & Latency:** Stage 1 uses a tool-calling reasoning agent (bounded by `DISCOVERY_MAX_TOOL_CALLS`). Stage 2's DB-backed deterministic path is instantaneous and consumes zero LLM tokens. The agent script-generation fallback runs with a 3-attempt self-correction loop.
- **Model Agnosticism & Local Inference:** Fully supported via `src/utils/llm.py` and `src/utils/inference.py` — run cloud models (Anthropic, OpenAI) or local open-weights models (DeepSeek, Qwen, GPT-OSS) via vLLM/SGLang with automated process management.
- **Data Conventions:** Missing sentinels `{-9999, -8888, -7777}` are converted to `NaN` on load. 180 countries tracked.
