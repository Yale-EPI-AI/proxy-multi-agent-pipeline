# EPI Proxy Discovery Pipeline — System Design

**Status:** Living document · **Last updated:** 2026-08-29 · **Audience:** developers joining the project, and reviewers who need the full system picture.

This document describes the architecture of the EPI Proxy Discovery Pipeline: what it does, how data flows through it, how the components fit together, and how a new developer should get oriented. It is meant to be read top to bottom on day one, then used as a reference.

For domain context on the EPI itself, see `CLAUDE.md` and `src/epi_proxy/domain_knowledge.py`.

---

---

# Part I: Overview & Architecture

## 1. What the System Does

The Yale **Environmental Performance Index (EPI)** ranks 180 countries across 58+ environmental indicators. Many of those indicators are weak: poor country coverage, infrequent updates, or values that are *modeled/imputed* rather than directly measured. (Example: the Waste Recovery Rate indicator, WRR, has 56 countries imputed.)

The pipeline's job is to **discover and statistically validate "data proxies"** — alternative, more readily available datasets that correlate with a hard-to-measure EPI indicator and could supplement or validate it.

> **Worked example.** Anti-diarrheal medication sales correlate with water-quality problems, so pharmaceutical trade data could serve as a proxy for the "Unsafe Drinking Water" (UWD) indicator.

The system is a **two-stage multi-agent pipeline**:

- **Stage 1 — Discovery (hypothesis generation).** A tool-using LLM discovery agent explores real data APIs (World Bank, WHO, NASA POWER, etc.), fetches candidate proxy datasets into a local DuckDB, and emits structured *proxy hypotheses*.
- **Stage 2 — Verification & Validation (hypothesis testing).** For each hypothesis, the system runs a statistical protocol (bivariate + partial correlation, functional-form fitting) and assigns a verdict: `confirmed`, `partially_confirmed`, `inconclusive`, or `rejected`. A lightweight LLM validation agent then audits each result against 10 inclusion criteria.

Outputs are aggregated into a JSON result and an HTML dashboard, and (optionally) compiled into a knowledge graph for cross-indicator reasoning or cross-model comparison matrices.

---

---

## 2. Component Diagram

```
                                  ┌──────────────────────────────────────────────┐
                                  │                 ENTRY POINTS                 │
                                  │                                              │
                                  │   CLI: uv run epi-proxy -i WRR               │
                                  │   Web: src/web/app.py  (Gradio, HF Spaces)   │
                                  └───────────────────────┬──────────────────────┘
                                                          │
                                                          v
                               ┌────────────────────────────────────────────────────┐
                               │            src/epi_proxy/orchestrator.py           │
                               │   run_pipeline() / run_pipeline_headless()         │
                               │   • local_inference_context (vLLM / SGLang)        │
                               │   • load metadata   • seed DB   • route stages     │
                               │   • aggregate → PipelineResult   • build dashboard │
                               └───────┬───────────────────────────────┬────────────┘
                                       │                               │
               ┌───────────────────────┘                               └───────────────────────┐
               v                                                                               v
┌──────────────────────────────────────┐                         ┌──────────────────────────────────────────────────┐
│         STAGE 1 — DISCOVERY          │                         │            STAGE 2 — VERIFICATION                │
│  src/epi_proxy/stage1/discovery.py   │                         │  src/epi_proxy/stage2/verifier.py                │
│                                      │                         │                                                  │
│  Tool-calling agent loop:            │                         │  Partition hypotheses by evidence_type:          │
│    search → preview → fetch → corr   │                         │   ┌─ programmatic_verify                         │
│    (≤ DISCOVERY_MAX_TOOL_CALLS=80)   │                         │   │    • DB-backed (deterministic)               │
│                                      │                         │   │      run_full_verification()                 │
│  Tools (30):                         │                         │   │                                              │
    src/epi_proxy/stage1/tools.py      │                         │   │    • else LLM Script Generator               │
│   3 per source × 9 sources + 3 DB    │                         │   │      writes & runs verify.py                 │
│        │                             │                         │   ├─ manual_data_needed → exploratory            │
│        v                             │                         │   └─ literature_attested → corroboration         │
│  src/epi_proxy/utils/data_fetch.py   │                         │            │                                     │
│   World Bank · WHO GHO · NASA POWER  │                         │            v                                     │
│   Comtrade · Wikipedia · OpenAQ      │                         │  src/epi_proxy/utils/stats.py + db_stats.py      │
│   GEE · GDELT(BQ) · FAOSTAT(offline) │                         │   bivariate · partial · functional form          │
│        │                             │                         │   → determine_verdict()                          │
│        v   parse + enum-repair       │                         │            │                                     │
│  ResearchOutput{ ProxyHypothesis[] } │ ── hypotheses (JSON) ─> │            v                                     │
└──────────────┬───────────────────────┘                         │  src/epi_proxy/stage2/validator.py (LLM Auditor) │
               │                                                 │   10 inclusion criteria → ValidationAnnotation   │
               │                                                 │   inclusion gate (advisory/soft/hard)            │
               │                                                 └──────────────────┬───────────────────────────────┘
               │                                                                    │
               v                                                                    v
        ┌──────────────────────────────────────────────────────────────────────────────────┐
        │                          CENTRAL DATA LAYER (src/epi_proxy/utils/db.py)          │
        │   DuckDB @ outputs/epi_data.duckdb                                               │
        │   variables · observations(country,year,value) · fetch_log                       │
        │   register_variable · upsert_observations · align_variables · get_observations   │
        └──────────────────────────────────────────────────────────────────────────────────┘
               │                                                                   │
               v                                                                   v
   ┌───────────────────────────┐                                   ┌───────────────────────────────────────────┐
   │  EPI reference data       │                                   │            OUTPUTS                        │
   │  docs/EPI2024_Work/       │                                   │  outputs/{TLA}/                           │
   │   Inputs/  Raw/{TLA}_raw  │                                   │   pipeline_result.json · dashboard.html   │
   │   (loaded via data_utils) │                                   │   pipeline.log · llm_traces.jsonl         │
   │                           │                                   │   stage1/{discovery_output,hypotheses}    │
   │                           │                                   │   stage2/{HYP-ID}/{verify.py,result.json} │
   └───────────────────────────┘                                   └───────────────────────────────────────────┘
                                                                                   │
                                                                                   v
                               ┌───────────────────────────────────────────────────────────────────────────┐
                               │   POST-HOC: KNOWLEDGE GRAPH & COMPARISONS                                 │
                               │   src/scripts/compile_knowledge_graph.py  (NetworkX + clingo ASP)         │
                               │   src/scripts/build_model_comparison.py   (Cross-model matrix dashboard)  │
                               │   src/scripts/render_llm_traces.py        (Trace HTML visualizer)         │
                               └───────────────────────────────────────────────────────────────────────────┘
```

---

---

## 3. Workflow in Plain Language

A run targets **one or more EPI indicators**, identified by three-letter abbreviations (TLAs), e.g. `WRR` or `-I WRR UWD WPC`.

1. **Kickoff & Inference Setup.** The operator runs the CLI (`uv run epi-proxy -i WRR`) or clicks "Run Pipeline" in the web UI. If local inference is enabled (`USE_LOCAL_INFERENCE=true`), the orchestrator automatically starts and health-checks a local vLLM or SGLang server process. The orchestrator then loads indicator metadata (description, units, source, polarity) from the EPI master variable list.

2. **Seed the database.** Before discovery starts, the orchestrator loads the *target* indicator's raw data and the standard *control variables* (GDP per capita, population, urbanization) into a central DuckDB (`outputs/epi_data.duckdb`). This guarantees the agent always has the target and controls available for correlation.

3. **Discovery agent explores (Stage 1).** The discovery agent (`src/epi_proxy/stage1/discovery.py`) is given the indicator, its domain context (from `src/epi_proxy/domain_knowledge.py`), and a toolbox of ~30 data tools. It loops: *search* a source for relevant series → *preview* candidates → *fetch and store* promising ones into the DB → optionally *pre-correlate* against the target. The agent runs until it is satisfied or hits its tool-call budget (default 80). It then emits a JSON block of **proxy hypotheses** — each one a structured claim: "proxy variable X relates to target Y in direction D with functional form F, sourced from dataset Z."

4. **Parse & repair.** The agent's JSON is parsed into `ProxyHypothesis` objects. Because LLMs occasionally invent enum values ("high" confidence, "monthly" frequency), an enum-repair table coerces known-bad values to valid ones *before* validation, preventing dropped hypotheses.

5. **(Optional) human review.** With `--review`, the operator sees a table of hypotheses and interactively selects which to verify.

6. **Verification (Stage 2).** Hypotheses are partitioned by `evidence_type` and processed sequentially:
   - **`programmatic_verify`** — data is fetchable or already fetched. If the proxy data was already stored in the DB during discovery, a **deterministic statistics pipeline** runs directly against DuckDB (`verify_hypothesis_from_db` via `src/epi_proxy/utils/db_stats.py`, fast and free of LLM tokens). Otherwise, an **LLM code-generation agent** (`verify_hypothesis` in `src/epi_proxy/stage2/verifier.py`) writes a `verify.py` script that downloads the data and runs the shared statistics library, executed via `subprocess.run` with a 3-attempt retry loop on errors.
   - **`manual_data_needed`** — an *exploratory* agent attempts to locate the data and outlines acquisition steps.
   - **`literature_attested`** — a *corroboration* agent assesses the literature claim and reported effect size without requiring fresh data.

7. **Statistical protocol.** For each verifiable hypothesis, the system computes Pearson + Spearman correlation, partial correlation controlling for GDP/pop/urbanization (does the proxy add signal beyond existing imputation models?), and fits linear/log-linear/quadratic forms (best by AIC). A decision tree maps these to a verdict.

8. **Validation gate.** A lightweight LLM validator (`src/epi_proxy/stage2/validator.py`) scores each result against 10 inclusion criteria (spatial completeness, open access, recency, methodology provenance, signal independence, etc.). Depending on the binding mode (`advisory` / `soft_gate` / `hard_gate`), failing a *critical* criterion can downgrade the verdict.

9. **Aggregate & report.** All results roll up into `pipeline_result.json` and a self-contained HTML `dashboard.html`. Everything is written under `outputs/{TLA}/`.

10. **(Post-hoc) knowledge graph & model comparison.** Standalone scripts compile indicator outputs into a NetworkX graph for clingo ASP reasoning (`src/scripts/compile_knowledge_graph.py`) or generate cross-model comparison matrix dashboards (`src/scripts/build_model_comparison.py`).

---

---

# Part II: Subsystem Deep Dives

## 4. Stage 1 Deep Dive — Discovery Agent & API Exploration

Stage 1 is responsible for **autonomous hypothesis generation grounded in real-world data**. Rather than performing unconstrained open-ended brainstorming, the Discovery Agent acts as an active data scientist: searching real APIs, previewing metadata, fetching actual time-series observations into DuckDB, and testing preliminary correlations before formalizing hypotheses.

### 4.1 Pre-Seeding Ground Truth and Confounders
Before the discovery agent starts its loop, the orchestrator seeds two critical baselines into the central DuckDB (`outputs/epi_data.duckdb`):
1. **Target Indicator Time Series (`epi:{TLA}`)**: The historical values of the target EPI indicator across all 180 countries and available years (e.g. 1990–2021).
2. **Standard Control Variables (`epi:GPC`, `epi:POP`, `epi:URB`)**:
   - `GPC`: GDP per capita (constant USD).
   - `POP`: Total population.
   - `URB`: Urban population percentage.

Pre-loading these ensures that any candidate proxy dataset fetched by the agent can be immediately joined and statistically compared against both the target and the key socioeconomic confounders.

### 4.2 Domain Knowledge Injection
The agent is primed with structured domain context from `src/epi_proxy/domain_knowledge.py` covering all 58 EPI indicators:
- Official indicator definition, mathematical formula, units, and transformation (e.g., $\ln(x)$).
- Imputation methodology and known limitations (e.g., whether the official score relies on regression models).
- Known physical, economic, or geographic confounders.
- Sibling indicator relationships across issue categories.

This prevents the agent from re-discovering trivial facts and focuses its reasoning on novel proxy mechanisms.

### 4.3 The Tool-Use Exploration Loop
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

### 4.4 Structured Hypothesis Output & Enum Coercion
Upon exhausting its tool budget or satisfying its exploration goals, the agent emits a structured JSON block containing a list of `ProxyHypothesis` objects ($h = \psi(c, v, r)$).

Because LLMs frequently invent natural-language enum variations (e.g., `"high"` for confidence, `"administrative"` for methodology), the parser runs an automated coercion routine (`_repair_hypothesis_enums`) before Pydantic schema validation. This ensures minor string variations are mapped to canonical schema values without discarding high-quality hypotheses.

---

---

## 5. Stage 2 Deep Dive — Verification vs. Validation

Stage 2 tests and audits candidate hypotheses. A foundational design principle of this pipeline is the **strict architectural separation between Verification and Validation**:

```
                              ┌──────────────────────────────────────────────────┐
                              │            ProxyHypothesis from Stage 1          │
                              └────────────────────────┬─────────────────────────┘
                                                       │
                                                       v
                   ┌─────────────────────────────────────────────────────────────────────────┐
                   │                     STEP 1: VERIFICATION (The Math)                     │
                   │  "Does the empirical data support the hypothesized relationship?"       │
                   │                                                                         │
                   │  • Bivariate Pearson (r) & Spearman (ρ) correlation                     │
                   │  • Pingouin partial correlation controlling for log(GDP), Pop, Urban    │
                   │  • Functional form fitting (Linear vs. Log-Linear vs. Quadratic by AIC) │
                   │  • Deterministic Decision Tree Verdict Assignment                       │
                   └───────────────────────────────────┬─────────────────────────────────────┘
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
                              │      Final VerificationResult + Validation       │
                              └──────────────────────────────────────────────────┘
```

### 5.1 Verification: Quantitative Empirical Testing

**Verification** asks: *"Is the hypothesized statistical relationship empirically true in the observed data?"*

Verification is purely statistical and mathematical. It executes via one of two paths based on the hypothesis `evidence_type`:

#### A. Deterministic DuckDB Path (`verify_hypothesis_from_db`)
- **When used**: Whenever candidate proxy data was already fetched and stored in DuckDB during Stage 1 (`db_variable_id` is set).
- **Why it matters**: Runs instantaneously via `src/epi_proxy/utils/db_stats.py`, produces fully deterministic outputs, and consumes zero LLM tokens.
- **Execution**: Aligns `(iso, year)` pairs across proxy, target, and controls directly in SQL, then runs the core statistical battery.

#### B. LLM Script Generation & Execution Path (`verify_hypothesis`)
- **When used**: For hypotheses requiring bespoke transformations, external data downloads, or exploratory routing (`manual_data_needed` / `literature_attested`).
- **Execution**: The LLM writes a standalone `verify.py` script utilizing shared stats utilities (`epi_proxy.utils.stats`). The script is executed in an isolated subprocess (`subprocess.run`). If errors or timeouts occur, stderr/stdout is fed back to the LLM in a **3-attempt self-correction loop**.

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

### 5.2 Validation: Methodological Audit & Inclusion Gating

**Validation** asks: *"Even if the correlation is statistically significant, is this proxy credible, open, methodologically sound, and suitable for the Yale EPI?"*

A proxy might show high correlation ($r = 0.85$) simply because both variables track GDP per capita, or because the dataset is restricted, unmaintained, or has poor global coverage. The Validation Agent (`src/epi_proxy/stage2/validator.py`) audits the verification artifacts against **10 EPI Inclusion Criteria**:

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

---

## 6. Knowledge Graph Post-Processing & Logical Reasoning

The Knowledge Graph (`src/epi_proxy/knowledge_graph/`) is a **post-hoc semantic and symbolic reasoning system** that operates over the aggregated outputs of the multi-agent pipeline. It decouples individual indicator discoveries from global systemic analysis, enabling cross-indicator hypothesis transfer, mechanism anomaly detection, and data opportunity discovery across all 58 EPI indicators.

### 6.1 What It Is & Why It Exists

While Stage 1 and Stage 2 discover and test proxies for one indicator at a time (e.g. `UWD` or `WRR`), environmental systems exhibit deep causal coupling:
- **Shared Drivers:** Indicators within the same Issue Category (e.g., `WWR` Wastewater Reused and `WWT` Wastewater Treated) share underlying socioeconomic, regulatory, and industrial infrastructure.
- **Cross-Indicator Signal Transfer:** A data proxy confirmed for indicator $A$ (e.g. pharmaceutical trade data for `UWD`) may serve as a powerful candidate proxy for an untested sibling indicator $B$ (e.g. `HPE` Household Solid Fuels / Household Pathogen Exposure).
- **Global Inconsistency Detection:** Hypothesized causal mechanisms across independent runs might contradict each other (e.g., claiming a positive vs negative link) or rely on confounding variables like GDP per capita without surviving partial correlation controls.

The Knowledge Graph connects the formal EPI 2024 indicator hierarchy with empirical pipeline results and executes **Answer Set Programming (ASP)** rules via `clingo` to synthesize higher-order systemic insights.

```
       EPI 2024 Taxonomy                               Discovered Evidence Layer
┌───────────────────────────────┐                  ┌───────────────────────────────┐
│ PolicyObjective: Ecosystem    │                  │ ProxyNode: WHO Cholera Rate   │
│       │ contains              │                  │   (confidence, evidence_type) │
│       v                       │                  └───────────────┬───────────────┘
│ IssueCategory: Water Quality  │                                  │
│       │ contains              │                                  │ measured_by
│       v                       │                                  v
│ IndicatorNode: UWD            │ <─── proxy_for ───────────────── DataSourceNode: WHO GHO
│   (domain context, units)     │     (r=0.72, p=0.001,            (org, url, accessibility)
└───────────────┬───────────────┘      partial_r=0.45,
                │                      verdict: confirmed)
                │ sibling_indicator
                v
┌───────────────────────────────┐
│ IndicatorNode: HPE            │ < - - inferred_candidate - - - - [ASP Reasoner]
│   (untested for cholera data) │       (confidence: 0.80)
└───────────────────────────────┘
```

---

### 6.2 How the Knowledge Graph is Created (`GraphBuilder`)

The graph is constructed by `GraphBuilder` (`src/epi_proxy/knowledge_graph/builder.py`) by layering four heterogeneous data sources into a typed `EpiKnowledgeGraph` (built on NetworkX MultiDiGraph):

1. **EPI Hierarchy Ingestion (`_load_epi_hierarchy`)**:
   - Parses `docs/EPI2024_Work/Inputs/master_variable_list.csv`.
   - Creates 3 `PolicyObjective` nodes (`Health`, `Ecosystem`, `Climate`), 11 `IssueCategory` nodes (`AirQuality`, `WaterQuality`, `WasteManagement`, etc.), and 58 `IndicatorNode`s.
   - Instantiates `contains` edges from Objectives → Categories → Indicators, as well as pairwise bidirectional `same_issue_category` edges between co-located indicators.

2. **Domain Knowledge & Sibling Ingestion (`_load_domain_knowledge`, `_load_sibling_edges`)**:
   - Ingests indicator metadata and domain context from `src/epi_proxy/domain_knowledge.py`.
   - Extracts explicit domain sibling mappings (e.g., `WRR` ↔ `WPC` / `SMW`, `WWR` ↔ `WWT` / `WWC` / `WWG`) and adds `sibling_indicator` edges.

3. **Pipeline Results Ingestion (`_load_pipeline_results`)**:
   - Traverses `outputs/{TLA}/pipeline_result.json` across all available indicator runs.
   - For each hypothesis, instantiates:
     - `ProxyNode`: node ID `proxy:{HYP_ID}`, storing proxy variable name, confidence level, evidence type, and description.
     - `DataSourceNode`: node ID `source:{org_slug}`, storing data source organization, URL, accessibility, and country coverage.
     - `measured_by` edge: directed from `ProxyNode` → `DataSourceNode`.

4. **Statistical & Audit Edge Attribution**:
   - Constructs directed `proxy_for` edges from `ProxyNode` → `IndicatorNode`.
   - Enriches the edge with full statistical metrics from Stage 2 verification: Pearson $r$, $p$-value, Spearman $\rho$, $N$ observations, partial correlation $r_{\text{partial}}$ controlling for log(GDP), best functional form (AIC selected), Stage 2 verdict (`confirmed`, `partially_confirmed`, `inconclusive`, `rejected`), validation inclusion score (0–10), and validation audit flags.

---

### 6.3 Symbolic Reasoning via Answer Set Programming (ASP)

The graph integrates declarative First-Order Logic reasoning via `clingo` (`src/epi_proxy/knowledge_graph/reasoning.py`). The `ReasoningEngine` translates graph structures into ASP relational facts (`indicator/3`, `proxy/4`, `correlation/2`, `partial_r/2`, `source/2`, `sibling/2`, `same_category/2`, `mechanism_mentions_confounder/1`) and executes declarative rules:

```prolog
#program rules.

% Rule 1: Cross-Indicator Candidate Transfer
cross_candidate(P, B, "sibling", 800) :-
    proxy(P, A, _, "confirmed"), sibling(A, B), not has_proxy_for(P, B).
cross_candidate(P, B, "same_category", 600) :-
    proxy(P, A, _, "confirmed"), same_category(A, B), A != B,
    not sibling(A, B), not has_proxy_for(P, B).

% Rule 2a: Direction-Observation Mismatch (Mechanistic Conflict)
direction_mismatch(P, I, D, R) :-
    proxy(P, I, D, V), correlation(P, R),
    V != "rejected", V != "inconclusive",
    D = "positive", R < -50.
direction_mismatch(P, I, D, R) :-
    proxy(P, I, D, V), correlation(P, R),
    V != "rejected", V != "inconclusive",
    D = "negative", R > 50.

% Rule 2b: Same-Direction Verdict Conflict
verdict_conflict(I, P1, P2, D) :-
    proxy(P1, I, D, "confirmed"), proxy(P2, I, D, "rejected"), P1 != P2.

% Rule 3: Confounder Path Detection
confounder_warning(P) :-
    mechanism_mentions_confounder(P),
    partial_r(P, PR), PR < 300, PR > -300.

% Rule 4: Coverage Gap Detection
coverage_gap(I) :- indicator(I, _, _), not has_any_proxy(I).

% Rule 5: Shared Data Source Opportunities
shared_source_candidate(S, B) :-
    source(P, S), proxy(P, A, _, "confirmed"),
    sibling(A, B), not source_used_for(S, B).
```

Each inference generated by `clingo` is parsed into an `Inference` object and reflected back into the graph as an `inferred_candidate` edge with explanatory provenance metadata.

---

### 6.4 What Can Be Analyzed Through the Graph

The programmatic query API (`src/epi_proxy/knowledge_graph/queries.py`) supports deep systemic queries:

| Analytical Query | Function | Systemic Purpose |
|---|---|---|
| **Cross-Indicator Candidates** | `get_cross_indicator_candidates()` | Recommends verified proxies from sibling indicators to bootstrap discovery for hard-to-measure indicators without running blind web search. |
| **Mechanistic Direction Mismatches** | `get_direction_mismatches()` | Identifies hypotheses where theoretical domain mechanisms (e.g. positive association) fail in reality ($r < -0.05$), pinpointing flawed causal assumptions. |
| **Contradictory Verdicts** | `get_verdict_conflicts()` | Detects instances where two proxies claiming the same mechanism yielded opposite verification results (`confirmed` vs `rejected`), uncovering dataset bias or non-linear effects. |
| **Confounder Warnings** | `get_confounder_warnings()` | Flags proxies that cite economic wealth or population growth in their causal story but whose statistical link vanishes ($|r_{\text{partial}}| < 0.30$) once log(GDP per capita) is controlled. |
| **EPI Coverage Gaps** | `get_coverage_gaps()` | Lists orphaned EPI indicators across the 58 indicators that have zero discovered hypotheses, guiding subsequent discovery batch allocations. |
| **Data Source Overlap & Expansion** | `get_shared_data_sources()` | Discovers high-utility data providers (e.g., UN Comtrade, WHO GHO, NASA POWER) capable of feeding multiple indicators simultaneously. |
| **Indicator Discovery Matrix** | `get_indicator_coverage_summary()` | Generates a complete coverage DataFrame summarizing total proxies, verdict distributions, and inferred candidate counts across all indicators. |

---

### 6.5 Usage & Multi-Format Exports

The Knowledge Graph post-processor is executed via the CLI or programmatic API:

```bash
# Compile graph from outputs, run clingo reasoning, and export artifacts
uv run epi-kg
```

#### Generated Artifacts (`outputs/knowledge_graph/`):
1. **`graph.json`**: Complete typed serialization of all nodes, edges, edge weights, and inference attributes.
2. **`graph.html`**: Standalone interactive Cytoscape.js visualizer featuring:
   - Force-directed animation with responsive physics.
   - Interactive search, node categorization, and verdict-based edge coloring (green = confirmed, yellow = partial, red = rejected, dashed purple = inferred).
   - Sidebar inspector revealing full verification statistics and ASP inference explanations upon node/edge selection.
3. **`graph.graphml`**: XML-based GraphML export compatible with desktop network analysis tools like Gephi, Cytoscape Desktop, and standard NetworkX workflows.
4. **`summary.md`**: Markdown report detailing graph summary statistics, indicator coverage matrices, identified coverage gaps, and reasoning inferences.
5. **Gradio UI Integration**: Rendered natively under the **"Knowledge Graph"** tab in `uv run epi-web`.

---

---

# Part III: Data Contracts & Codebase Map

## 7. Core Data Contracts (`src/epi_proxy/schemas.py`)

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

---

## 8. Component Reference

### Orchestration & Local Inference
| File | Responsibility |
|---|---|
| `src/epi_proxy/orchestrator.py` | CLI entry (`main`), `run_pipeline()` (interactive/batch), `run_pipeline_headless()` (Gradio generator). Manages engine lifecycle, DB seeding, stage routing, and dashboard export. |
| `src/epi_proxy/config.py` | All paths, model names, thresholds, and tunables. **Start here when changing behavior.** |
| `src/epi_proxy/utils/inference.py` | `VLLMEngine` and `SGLangEngine` lifecycle managers: background process spawning, port discovery, health-check polling, and shutdown. |
| `src/epi_proxy/utils/llm.py` | Unified `LLMClient` supporting Anthropic, OpenAI, and local endpoints with complete trace logging to `llm_traces.jsonl`. |
| `src/web/app.py` | Gradio UI: tabs for Reports, Knowledge Graph, Presentation [EPI], Presentation [Technical], Pipeline Runner, and Indicator Reference. |

### Stage 1 — Discovery
| File | Responsibility |
|---|---|
| `src/epi_proxy/stage1/discovery.py` | Tool-calling agent loop. Seeds target + control variables into DuckDB, runs the tool loop, parses and enum-repairs the final JSON into `ResearchOutput`. |
| `src/epi_proxy/stage1/tools.py` | 30 tool definitions handed to the agent: `search_/preview_/fetch_and_store_` × 9 sources, plus 3 DB tools. `execute_tool()` dispatches. |
| `src/epi_proxy/stage1/prompts.py` | `DISCOVERY_SYSTEM_PROMPT` + indicator prompt template. |
| `src/epi_proxy/utils/data_fetch.py` | The 9 external source families: World Bank, WHO GHO, NASA POWER, Comtrade, Wikipedia, OpenAQ, GEE, GDELT BQ, FAOSTAT. |
| `src/epi_proxy/domain_knowledge.py` | Complete domain context for **all 58 EPI indicators** (definition, imputation model, known confounders, data quality issues). Injected into discovery prompt. |

### Stage 2 — Verification & Validation
| File | Responsibility |
|---|---|
| `src/epi_proxy/stage2/verifier.py` | `verify_hypothesis_from_db()` (deterministic path via `db_stats.run_full_verification`) and `verify_hypothesis()` (LLM script generation + `subprocess.run` loop). |
| `src/epi_proxy/stage2/data_loader.py` | `prepare_verification_context()` — coverage stats + file paths formatted for verification prompts. |
| `src/epi_proxy/stage2/prompts.py` | Prompt templates for verification, corroboration, exploratory search, and validation. |
| `src/epi_proxy/stage2/validator.py` | Post-verification audit: scores 10 inclusion criteria; applies inclusion gating (`advisory`, `soft_gate`, `hard_gate`) and flags GDP-imputed proxies. |
| `src/epi_proxy/utils/stats.py` | Pure computation: `run_bivariate_correlation`, `run_partial_correlation` (pingouin), `test_functional_form` (AIC), `determine_verdict`, `build_result_json`. |
| `src/epi_proxy/utils/db_stats.py` | `run_full_verification()` — deterministic DB-backed equivalent of `verify.py`. |

### Reporting & Analysis
| File | Responsibility |
|---|---|
| `src/epi_proxy/report.py` | Generates self-contained per-indicator HTML dashboards (`dashboard.html`). |
| `src/epi_proxy/report_compare.py` | Generates cross-model comparison dashboards comparing multiple pipeline runs across models and indicators. |
| `src/scripts/render_llm_traces.py` | Renders `llm_traces.jsonl` into an interactive, readable HTML trace viewer. |
| `src/scripts/build_model_comparison.py` | Standalone CLI to scan model output folders and produce a comparison dashboard. |

### Shared Data Layer
| File | Responsibility |
|---|---|
| `src/epi_proxy/utils/db.py` | Central DuckDB (`outputs/epi_data.duckdb`): tables `variables`, `observations`, `fetch_log`. Connection management, `upsert_observations`, `align_variables`. |
| `src/epi_proxy/utils/data_utils.py` | `load_raw_indicator()` (wide→long format, sentinel→NaN), `load_variable_metadata()`, `get_available_indicators()`. |
| `src/epi_proxy/utils/country_align.py`, `src/epi_proxy/utils/country_codes.py` | Country name/ISO3 reconciliation across data sources. |
| `src/epi_proxy/schemas.py` | All Pydantic v2 data models. |

### Knowledge Graph (Post-Hoc)
| File | Responsibility |
|---|---|
| `src/epi_proxy/knowledge_graph/builder.py` | `GraphBuilder` — pipeline outputs → NetworkX graph. |
| `src/epi_proxy/knowledge_graph/reasoning.py` | `ReasoningEngine` + `run_reasoning()` — clingo ASP inference. |
| `src/epi_proxy/knowledge_graph/{export,visualize,queries,graph,schema}.py` | Export (JSON/GraphML/HTML), Cytoscape.js interactive visualization, graph model. |
| `src/scripts/compile_knowledge_graph.py` | Standalone driver → `outputs/knowledge_graph/`. |

---

---

# Part IV: Operations & Engineering

## 9. Developer Onboarding

### 9.1 Prerequisites & First-Time Setup

1. **Install dependencies with `uv`**:
   ```bash
   uv sync                     # installs dependencies from pyproject.toml / uv.lock
   ```
2. **Unzip reference EPI dataset** (required before first run):
   ```bash
   unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/
   ```

### 9.2 Environment Configuration (`.env`)

Copy the template `.env.example` to `.env` and populate your API keys and settings:
```bash
cp .env.example .env
```
Open `.env` and configure your LLM provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`), local inference options if running open-weights models (`USE_LOCAL_INFERENCE`), and optional external data source credentials.

### 9.3 Common CLI Commands

```bash
# 0. First-time setup: unzip reference dataset
unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/

# 1. See all available indicators
uv run epi-proxy --list-indicators

# 2. Run single indicator end-to-end
uv run epi-proxy -i WRR

# 3. Run multiple indicators in batch
uv run epi-proxy -I WRR UWD WPC

# 4. Skip Stage 1, verify pre-existing hypotheses
uv run epi-proxy -i WRR --stage 2 --hypotheses-file outputs/WRR/stage1/hypotheses.json

# 5. Interactive review mode before verification
uv run epi-proxy -i WRR --review

# 6. Launch the Gradio web dashboard
uv run epi-web

# 7. Compile the knowledge graph across completed outputs
uv run epi-kg
```

### 9.4 Where Outputs Land

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

### 9.5 How to Read the Codebase

1. `src/epi_proxy/config.py` — configuration, thresholds, model settings.
2. `src/epi_proxy/schemas.py` — Pydantic models and data contracts.
3. `src/epi_proxy/orchestrator.py` — pipeline spine; trace `run_pipeline()`.
4. `src/epi_proxy/stage1/discovery.py` & `src/epi_proxy/stage1/tools.py` — tool-use discovery agent loop.
5. `src/epi_proxy/stage2/verifier.py`, `src/epi_proxy/stage2/validator.py`, & `src/epi_proxy/utils/stats.py` — verification and validation logic.
6. `src/epi_proxy/utils/db.py` & `src/epi_proxy/utils/db_stats.py` — DuckDB data layer and deterministic verification.
7. `src/epi_proxy/domain_knowledge.py` — indicator definitions and domain context.
8. `src/epi_proxy/knowledge_graph/` — post-hoc graph construction, queries, and clingo ASP reasoning.

---

## 10. Cross-Cutting Notes

- **Cost & Latency:** Stage 1 uses a tool-calling reasoning agent (bounded by `DISCOVERY_MAX_TOOL_CALLS`). Stage 2's DB-backed deterministic path is instantaneous and consumes zero LLM tokens. The agent script-generation fallback runs with a 3-attempt self-correction loop.
- **Model Agnosticism & Local Inference:** Fully supported via `src/epi_proxy/utils/llm.py` and `src/epi_proxy/utils/inference.py` — run cloud models (Anthropic, OpenAI) or local open-weights models (DeepSeek, Qwen, GPT-OSS) via vLLM/SGLang with automated process management.
- **Data Conventions:** Missing sentinels `{-9999, -8888, -7777}` are converted to `NaN` on load. 180 countries tracked.
