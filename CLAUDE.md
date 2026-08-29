# EPI Data Proxy Discovery Pipeline

## Notes on code execution & environment

Always use `uv` for environment management and code execution (e.g. `uv run python ...` or `uv sync`).

Before running the pipeline for the first time, ensure the raw EPI dataset archive is unzipped:
```bash
unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/
```

When pushing to Hugging Face Spaces, always push to the `main` branch: `git push hf master:main` or `git push hf main`. HF Spaces reads from `main`, not `master`.

## Project Overview

This project builds a **multi-agent system for discovering data proxies** for the Yale Environmental Performance Index (EPI). The EPI ranks 180 countries across 58+ indicators spanning environmental health and ecosystem vitality, but many indicators suffer from poor country coverage, infrequent updates, or reliance on modeled (rather than directly measured) data. The goal is to find alternative data sources ("proxies") that correlate with hard-to-measure EPI indicators and could supplement or validate official statistics.

**Example:** Anti-diarrheal medication sales correlate with water quality problems, so pharmaceutical sales data could serve as a proxy for the "Unsafe Drinking Water" (UWD) indicator.

## Architecture: Two-Stage Pipeline

### Stage 1: Discovery Agent (Hypothesis Generation)
A tool-using reasoning agent (`src/stage1/discovery.py`) explores real-world data APIs, fetches candidate proxy datasets into a centralized DuckDB (`outputs/epi_data.duckdb`), and emits structured *proxy hypotheses*:
- **API Exploration**: Searches, previews, and fetches candidate time series across 9 source families (~30 tools in `src/stage1/tools.py`).
- **Target & Control Seeding**: Target indicator data and standard control variables (`GPC`, `POP`, `URB`) are automatically pre-loaded into the DuckDB.
- **In-Memory Pre-correlation**: Optionally tests correlation against the target before finalizing hypotheses.
- **Structured Hypothesis Output**: Emits structured JSON adhering to the `ProxyHypothesis` schema, parsed and repaired via enum coercion (`_repair_hypothesis_enums`).

### Stage 2: Verification & Validation
Stage 2 validates candidate hypotheses using statistical testing and multi-criteria audit:
- **Routing by Evidence Type**:
  - `programmatic_verify`: Data is fetchable or already fetched in DuckDB.
    - **DB-backed deterministic path** (`verify_hypothesis_from_db` via `src/utils/db_stats.py`): Runs the full statistical protocol directly from DuckDB (fast, deterministic, zero LLM tokens).
    - **Agent code-generation path** (`verify_hypothesis` in `src/stage2/verifier.py`): The LLM generates `verify.py`, executed via `subprocess.run` with a 3-attempt retry loop on errors/timeouts.
  - `manual_data_needed`: Exploratory prompt assessing data acquisition steps.
  - `literature_attested`: Corroboration prompt validating literature citations and reported metrics.
- **Statistical Protocol**:
  - Pearson ($r$) & Spearman ($\rho$) correlation with significance ($p$-values) and sample size checks ($n \ge 20$).
  - Partial correlation controlling for log(GDP per capita), population, and urbanization via `pingouin`.
  - Functional form fitting: linear, log-linear, and quadratic models compared via AIC (`test_functional_form()`).
  - Decision tree verdict assignment: `confirmed`, `partially_confirmed`, `inconclusive`, or `rejected`.
- **Validation & Inclusion Gate**:
  - An LLM validator (`src/stage2/validator.py`) evaluates 10 inclusion criteria (`spatial_completeness`, `open_access`, `recency`, `documented_methodology`, `signal_independence`, etc.).
  - Configurable binding mode (`advisory`, `soft_gate`, `hard_gate`).
  - Special escalation for GDP-imputed indicators (`GDP_IMPUTATION_DEPENDENT`, e.g. WRR): flags proxies lacking signal independence.

## Hypothesis Formalization (DiscoveryBench-inspired)

Each proxy hypothesis follows the structured formalism $h = \psi(c, v, r)$:
- **Context ($c$)**: Boundary conditions — e.g., "across countries with GDP > $5000, 2010-2020"
- **Variables ($v$)**: Target EPI indicator + candidate proxy variable(s)
- **Relationship ($r$)**: The nature of the statistical link — e.g., "positive linear correlation (r=0.72)", "log-linear"

Hypotheses form a **semantic tree** where:
- **Root**: The target EPI indicator (e.g., UWD — unsafe drinking water)
- **Internal nodes**: Intermediate causal/mechanistic variables
- **Leaves**: Observable, accessible proxy data sources

## Priority Indicators for Proxy Discovery

Based on analysis of the EPI 2024 Technical Appendix (country coverage, imputation rates, temporal sparsity):

### Tier 1 — Most Critical (massive imputation, poor coverage, stale data)
| TLA | Indicator | Issue |
|-----|-----------|-------|
| WRR | Waste Recovery Rate | 56 countries imputed (R²=0.42), highly variable temporal coverage |
| SMW | Controlled Solid Waste | Same underlying waste data quality challenges |
| WPC | Waste per capita | Same waste data ecosystem issues |
| WWR | Wastewater reused | Single year (2015) only, most countries lack data |
| WWT | Wastewater treated | Highly variable coverage, 2015-2021 |
| WWC | Wastewater collected | Highly variable coverage, 2015-2021 |
| WWG | Wastewater generated | Highly variable coverage, 2015-2021 |

### Tier 2 — Important (significant imputation, sparse temporal coverage)
| TLA | Indicator | Issue |
|-----|-----------|-------|
| RCY | Relative Crop Yield | 50 countries imputed (R²=0.51) |
| PRS | Pesticide Pollution Risk | Only 2 time points (2015, 2018) |
| BER | Bioclimatic Ecosystem Resilience | Only 5 data points spanning 2000-2020 |
| MPE | Marine Protection Effectiveness | Limited to 2012-2020 via satellite fishing data |

### Tier 3 — Moderate (single-snapshot indicators)
| TLA | Indicator | Issue |
|-----|-----------|-------|
| FLI | Forest Landscape Integrity | Single year (2020) |
| TCG | Net forest cover gain | Single year (2020) |
| PAR | Protected Areas Representativeness | Single year (2024) |

## Pipeline Implementation Details

### Statistical Verification (Stage 2)
- **Bivariate correlation**: Pearson + Spearman, with direction and significance checks
- **Partial correlation**: Controls for log(GDP per capita), population, urbanization via `pingouin`
- **Functional form testing**: Fits linear, log-linear, and quadratic models; selects best via AIC comparison (`test_functional_form()` in `src/utils/stats.py`)
- **Verdict thresholds**: Confirmed (|r|>0.3, p<0.05, partial significant), Partially Confirmed, Inconclusive (n<20 or borderline p), Rejected (p>0.10 or wrong direction)

### Domain Knowledge Injection (Stage 1)
- `src/domain_knowledge.py` maps **all 58 indicator TLAs** → domain context strings (indicator definition, imputation model, known confounders, data quality issues, sibling relationships)
- Injected into the Discovery agent prompt as "Domain Context" section
- `GDP_IMPUTATION_DEPENDENT` set identifies indicators (like `WRR`) whose official EPI score is derived from GDP regressions

### Key Source Files
- `src/schemas.py` — Pydantic v2 models: `ProxyHypothesis`, `VerificationResult`, `FunctionalFormResult`, `InclusionCriteriaScore` (10 criteria)
- `src/config.py` — Paths, API keys, model names, thresholds (`INCLUSION_CRITICAL_CRITERIA=[spatial_completeness, open_access]`, `DISCOVERY_MAX_TOOL_CALLS=80`)
- `src/orchestrator.py` — CLI (`python -m src`) and programmatic runner (`run_pipeline`, `run_pipeline_multi`, `run_pipeline_headless`)
- `src/stage1/discovery.py` — Stage 1 tool-calling discovery agent loop and enum-repair parser
- `src/stage1/tools.py` — 30 discovery-agent tools (3 per source × 9 sources + 3 DB tools)
- `src/stage1/prompts.py` — Discovery agent system prompt and indicator template
- `src/stage2/verifier.py` — Stage 2 verification runner: DB deterministic path + LLM subprocess execution retry loop
- `src/stage2/validator.py` — Post-verification validation + inclusion-gate logic
- `src/stage2/prompts.py` — Verification, exploratory, corroboration, and validation prompt templates
- `src/stage2/data_loader.py` — Target coverage summary for verification prompts
- `src/utils/db.py` — DuckDB manager (`variables`, `observations`, `fetch_log`, variable alignment)
- `src/utils/db_stats.py` — Deterministic DB-backed statistical verification runner (`run_full_verification`)
- `src/utils/stats.py` — Core statistical tests: bivariate, partial correlation, AIC functional form, verdict logic
- `src/utils/data_fetch.py` — 9 external source families (World Bank, WHO GHO, NASA POWER, Comtrade, Wikipedia, OpenAQ, GEE, GDELT BQ, FAOSTAT-offline)
- `src/utils/llm.py` — Unified LLM client supporting Anthropic, OpenAI, and local endpoints with trace logging (`llm_traces.jsonl`)
- `src/utils/inference.py` — Local inference engine lifecycle management (vLLM and SGLang)
- `src/report.py` — Self-contained HTML dashboard generator
- `src/report_compare.py` — Multi-model comparison matrix dashboard generator

### External API Setup
- **Wikipedia Pageviews** — no auth required; Wikimedia pageviews REST API.
- **UN Comtrade** — free key at <https://comtradedeveloper.un.org/>; stored as `COMTRADE_API_KEY` in `.env` (500 requests/day). HS catalog cached at `src/utils/comtrade_hs_catalog.json`.
- **OpenAQ v3** — free key at <https://explore.openaq.org/>; stored as `OPENAQ_API_KEY` (2000 requests/day).
- **Google Earth Engine** — authenticate via `earthengine authenticate`; credentials at `~/.config/earthengine/credentials`; project ID in `GEE_PROJECT`. Scale floor is 50 km.
- **GDELT GKG (BigQuery)** — service account JSON on disk, path in `GOOGLE_APPLICATION_CREDENTIALS`. First 1 TB/month free.
- **FAOSTAT** — API host currently offline; short-circuits gracefully with an informative error.

### Local Inference Support
Run fully local open-weights models (e.g. `openai/gpt-oss-120b`, `deepseek-ai/DeepSeek-V3`) using vLLM or SGLang:
- Set `USE_LOCAL_INFERENCE=true` and `LOCAL_ENGINE_TYPE=vllm` (or `sglang`) in `.env`
- The orchestrator automatically launches the engine, finds an open port, waits for health check responsiveness, and shuts down on completion.

### Knowledge Graph
- `src/knowledge_graph/` — NetworkX graph + clingo ASP reasoning over pipeline outputs
- `scripts/compile_knowledge_graph.py` — Standalone script: builds graph, runs reasoning, exports to `outputs/knowledge_graph/`
- Run via: `uv run python scripts/compile_knowledge_graph.py`
- Read-only analysis tool — does NOT modify the pipeline or orchestrator.

## Key Directories

- `docs/` — Reference documents (EPI technical appendix, system design)
- `outputs/` — Run outputs per indicator (`outputs/{TLA}/pipeline_result.json`, `dashboard.html`, `stage1/`, `stage2/`)
- `outputs/epi_data.duckdb` — Persistent central DuckDB caching fetched time series across runs
- `outputs/knowledge_graph/` — Graph exports (graph.json, graph.html, graph.graphml, summary.md)
- `scripts/` — Standalone utility scripts (`compile_knowledge_graph.py`, `render_llm_traces.py`, `build_model_comparison.py`, `test_data_sources.py`)
- `docs/EPI2024_Work/` — Full EPI 2024 data pipeline and raw data
  - `Inputs/master_variable_list.csv` — All 58+ EPI indicators with metadata (source, units, processing)
  - `Inputs/MasterFile.csv` — Authoritative list of 180 countries with ISO codes
  - `Raw/` — Cleaned data files ready for the EPI pipeline (`{TLA}_raw.csv`)
- `web/` — Gradio web application (`web/app.py`)

## Common Commands

```bash
# Install dependencies
uv sync

# Unzip EPI reference data (first-time setup)
unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/

# List available indicators
uv run python -m src --list-indicators

# Run full pipeline on an indicator
uv run python -m src -i WRR

# Run multiple indicators in batch
uv run python -m src -I WRR UWD WPC

# Run Stage 2 only with pre-existing hypotheses
uv run python -m src -i WRR --stage 2 --hypotheses-file outputs/WRR/stage1/hypotheses.json

# Launch Gradio Web UI
uv run python web/app.py

# Render LLM traces to HTML
uv run python scripts/render_llm_traces.py outputs/WRR/llm_traces.jsonl

# Build cross-model comparison dashboard
uv run python scripts/build_model_comparison.py
```

## Gotchas
- NetworkX `write_graphml` fails on Pydantic enum values — flatten to `.value` strings before export
- Cytoscape.js `tap` events conflict with COSE layout animation — use `click` events instead
- `verify.py` subprocess execution runs with `cwd=PROJECT_ROOT` so Python imports `from src.utils...` work reliably
- LLM enum drift is normal: the discovery parser coerces natural-language values before Pydantic validation via `_repair_hypothesis_enums`
