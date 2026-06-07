# EPI Data Proxy Discovery Pipeline

## Notes on code exeuction etc

Always use the conda epi environment when running any code or downloading any packages.

When pushing to Hugging Face Spaces, always push to the `main` branch: `git push hf master:main`. HF Spaces reads from `main`, not `master`.

## Project Overview

This project builds a **multi-agent system for discovering data proxies** for the Yale Environmental Performance Index (EPI). The EPI ranks 180 countries across 58+ indicators spanning environmental health and ecosystem vitality, but many indicators suffer from poor country coverage, infrequent updates, or reliance on modeled (rather than directly measured) data. The goal is to find alternative data sources ("proxies") that correlate with hard-to-measure EPI indicators and could supplement or validate official statistics.

**Example:** Anti-diarrheal medication sales correlate with water quality problems, so pharmaceutical sales data could serve as a proxy for the "Unsafe Drinking Water" (UWD) indicator.

## Architecture: Two-Stage Pipeline

### Stage 1: Deep Research Agent (Hypothesis Generation)
A deep research agent performs literature review and data discovery for a given EPI indicator:
- **Causal mapping**: Identifies upstream causes and downstream effects of the target indicator
- **Literature-validated proxies**: Finds academic papers documenting proxy relationships (correlation, sample, caveats)
- **Speculative proxies**: Brainstorms novel proxy candidates based on the causal map
- **Data availability assessment**: Evaluates geographic coverage, temporal granularity, accessibility of proxy datasets
- **Confounder analysis**: Identifies spurious correlation risks and validity conditions

### Stage 2: Code Agent (Hypothesis Verification)
A code execution agent takes the structured output from Stage 1 and:
- Downloads or loads proxy datasets and the corresponding EPI indicator data
- Runs statistical tests (correlation, regression, Granger causality) to validate hypothesized proxy relationships
- Handles data cleaning, alignment (country names, time periods), and normalization
- Outputs confirmed/rejected hypotheses with statistical evidence

## Hypothesis Formalization (DiscoveryBench-inspired)

Each proxy hypothesis follows the structured formalism h = ψ(c, v, r):
- **Context (c)**: Boundary conditions — e.g., "across countries with GDP > $5000, 2010-2020"
- **Variables (v)**: Target EPI indicator + candidate proxy variable(s)
- **Relationship (r)**: The nature of the statistical link — e.g., "positive linear correlation (r=0.72)", "log-linear"

Hypotheses form a **semantic tree** where:
- **Root**: The target EPI indicator (e.g., UWD — unsafe drinking water)
- **Internal nodes**: Intermediate causal/mechanistic variables
- **Leaves**: Observable, accessible proxy data sources

This formalism provides a structured contract between Stage 1 (generates hypotheses) and Stage 2 (verifies them).

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
- **Partial correlation**: Controls for log(GDP per capita) via `pingouin`
- **Functional form testing**: Fits linear, log-linear, and quadratic models; selects best via AIC comparison (`test_functional_form()` in `src/utils/stats.py`)
- **Verdict thresholds**: Confirmed (|r|>0.3, p<0.05, partial significant), Partially Confirmed, Inconclusive (n<20 or borderline p), Rejected (p>0.10 or wrong direction)
- The verification agent (Claude Code SDK) writes `verify.py` + `result.json` per hypothesis

### Relationship Extraction (Stage 1)
- Parse prompt enforces: no `direction="unknown"` when mechanism exists (infer from causal link), default `functional_form="linear"` unless evidence of non-linearity, aggressive strength estimate extraction
- Research prompt asks for expected functional form in both literature-validated and speculative proxies

### Domain Knowledge Injection (Stage 1)
- `src/domain_knowledge.py` maps all 58 indicator TLAs → domain context strings (indicator definition, imputation model, known confounders, data quality issues, sibling relationships)
- Injected into Gemini deep research prompt as "Domain Context" section when available
- Entries validated against Technical Appendix PDF + `master_variable_list.csv`; process documented in `docs/domain_knowledge_process.txt`

### Key Source Files
- `src/schemas.py` — Pydantic v2 models: `ProxyHypothesis`, `VerificationResult`, `FunctionalFormResult`, `InclusionCriteriaScore` (10 criteria, `documented_methodology` renamed from `established_methodology`)
- `src/utils/stats.py` — `run_bivariate_correlation()`, `run_partial_correlation()`, `test_functional_form()`, `determine_verdict()`, `build_result_json()`
- `src/utils/data_utils.py` — `load_raw_indicator()` (CSV→long format, sentinel→NaN)
- `src/utils/data_fetch.py` — 9 source families (World Bank, WHO GHO, NASA POWER, Comtrade, Wikipedia, OpenAQ, GEE, GDELT BQ, FAOSTAT-offline) exposed as `search_*`/`preview_*`/`fetch_*`/`fetch_and_store_*`
- `src/stage1/research.py` — Gemini Deep Research API calls (~$4/indicator, uses `deep-research-pro-preview-12-2025`)
- `src/stage1/tools.py` — 30 discovery-agent tools (3 per source × 9 sources + 3 DB tools)
- `src/stage1/parser.py` — Claude-based structured extraction from research reports
- `src/stage2/verifier.py` — Claude Code SDK agent orchestration
- `src/stage2/prompts.py` — Verification prompt templates + validator prompt (10 inclusion criteria including `signal_independence`)
- `src/stage2/validator.py` — Post-verification validation + inclusion-gate logic (GDP-imputation-dependent escalation for WRR)
- `src/domain_knowledge.py` — Tier 1 indicator domain context + `GDP_IMPUTATION_DEPENDENT` set
- `src/config.py` — Paths, API keys, model names, thresholds. `INCLUSION_CRITICAL_CRITERIA=[spatial_completeness, open_access]` (methodology is advisory as of 2026-04-13). `DISCOVERY_MAX_TOOL_CALLS=80`.

### External API setup (novel sources)
- **Wikipedia Pageviews** — no auth; `docs/wiki_country_projects.json` maps ISO3 → primary Wikipedia language edition. Countries sharing en/es/fr/ar/pt/ru/zh receive identical values (flagged in the tool description).
- **UN Comtrade** — free subscription key at <https://comtradedeveloper.un.org/>; stored as `COMTRADE_API_KEY` in `.env`. Free tier: 500 requests/day. Retry-on-429 built into `_fetch_comtrade_one_year`. HS catalog cached at `src/utils/comtrade_hs_catalog.json`.
- **OpenAQ v3** — free key at <https://explore.openaq.org/> account; stored as `OPENAQ_API_KEY`. 2000 requests/day. Full EPI backfill (~4300 calls) exceeds the free tier — spread across multiple days or use `max_sensors_per_country` to cap.
- **Google Earth Engine** — user auth via `earthengine authenticate`; credentials at `~/.config/earthengine/credentials`; project ID in `GEE_PROJECT` (not an API key, despite the dotfile naming). Scale floor is 50 km (25 km and 10 km were tested but S5P NO2 global aggregation exceeded the 4-min timeout at those scales; see comment in `data_fetch.py` near `_GEE_SCALE_METERS`).
- **GDELT GKG (BigQuery)** — service account JSON on disk, path in `GOOGLE_APPLICATION_CREDENTIALS`. Billing must be enabled on the GCP project even for the free tier. First 1 TB/month scanned is free; default year range `(2020, 2024)` is ~2.4 TB cost/backfill.
- **FAOSTAT** — API host currently offline; all `*_faostat` tools short-circuit with a clear error (see `src/stage1/tools.py`).

### Knowledge Graph
- `src/knowledge_graph/` — NetworkX graph + clingo ASP reasoning over pipeline outputs
- `scripts/compile_knowledge_graph.py` — Standalone script: builds graph, runs reasoning, exports to `outputs/knowledge_graph/`
- Run via: `conda run -n epi python scripts/compile_knowledge_graph.py`
- Dependencies: `networkx`, `clingo` (installed in epi conda env)
- The knowledge graph is a post-hoc analysis tool — it does NOT modify the pipeline or orchestrator

## Key Directories

- `docs/` — Reference documents (EPI technical appendix, DiscoveryBench paper, EPI data)
- `outputs/knowledge_graph/` — Graph exports (graph.json, graph.html, graph.graphml, summary.md)
- `scripts/` — Standalone utility scripts (not part of the pipeline)
- `docs/EPI2024_Work/` — Full EPI 2024 data pipeline and raw data
  - `Inputs/master_variable_list.csv` — All 58+ EPI indicators with metadata (source, units, processing)
  - `Inputs/MasterFile.csv` — Authoritative list of 180 countries with ISO codes
  - `Inputs/weights2024.csv` — Indicator weights for aggregation
  - `Raw/` — 312 cleaned data files ready for the EPI pipeline (one per variable, format: `{TLA}_raw.csv`)
  - `Source/` — Original source data and processing scripts (R)
  - `PScripts/` — Pipeline scripts (P0_Master.R through P9), R-based
  - `POutputs/EPI_results.csv` — Final indicator scores for all 180 countries
  - `POutputs/Targets.csv` — Best/worst targets for normalization (68 indicators)
  - `P1_Complete/` through `P6_Aggregation/` — Pipeline intermediate outputs

## EPI Data Format

- Raw data CSVs: rows = countries (code, iso, country), columns = years (e.g., `UWD.raw.1990` ... `UWD.raw.2021`)
- Missing value codes: `-9999` (missing in source), `-8888` (country not in source), `-7777` (not material, e.g. fisheries for landlocked countries)
- 180 countries tracked; ~40 additional territories excluded due to data sparseness
- EPI pipeline is R-based; proxy validation code should be Python for broader compatibility

## EPI Data Sources (99 TLA/source entries)

Key source organizations and frequency:
- OECD (8), IHME (7), Global Forest Watch (7), World Bank/What a Waste (6), Sea Around Us (5), Copernicus (5), UNEP-WCMC (5), FAOSTAT (4), Jones et al./PANGAEA (4), Worldwide Governance Indicators (4), PRIMAP-hist (3), CEDS (3), UN Statistics Division (3)

Almost all 99 data source entries have publicly accessible URLs. Exceptions requiring special access: PAR (CSIRO, personal communication), SHI/SPI (Map of Life, personal communication), some GFW data (personal communication but viewable online), IHME data (free account required).

## EPI Indicator Structure

The EPI is organized hierarchically:
- **Policy Objectives**: Environmental Health (HLT, 25%), Ecosystem Vitality (ECO, 45%), Climate Change (PCC, 30%)
- **Issue Categories** (11): Air Quality, Sanitation & Drinking Water, Heavy Metals, Waste Management, Biodiversity & Habitat, Forests, Fisheries, Air Pollution, Agriculture, Water Resources, Climate Change Mitigation
- **Indicators**: 58+ specific measurable indicators, each with a three-letter abbreviation (TLA)

## Gotchas
- NetworkX `write_graphml` fails on Pydantic enum values — must flatten to `.value` strings before export
- Cytoscape.js `tap` events conflict with COSE layout animation — use `click` events instead, or use a flag to prevent background click from swallowing node clicks
- Gemini Deep Research costs ~$4/call — 5 pipeline runs = ~$20. No free tier for this agent.
