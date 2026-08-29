---
title: EPI Proxy Discovery Pipeline
emoji: "🌍"
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
---

# EPI Proxy Discovery Pipeline

Multi-agent system for discovering and validating data proxies for the
[Yale Environmental Performance Index](https://epi.yale.edu/) (EPI).


## Quick Start (local)

```bash
# Install dependencies
uv sync

# Unzip the EPI reference dataset (first time setup)
unzip docs/EPI2024_Work/EPI2024_Work.zip -d docs/

# Set API keys in .env or environment
export ANTHROPIC_API_KEY=...

# Launch Gradio web UI
uv run python web/app.py
# → opens at http://localhost:7860

# Or run via CLI
uv run python -m src -i WRR
```

## Architecture

1. **Stage 1 — Discovery Agent**: Tool-using LLM agent with ~30 data-source tools
   (World Bank, WHO GHO, NASA POWER, Wikipedia, UN Comtrade, OpenAQ, Google Earth
   Engine, GDELT) searches, previews, fetches, and pre-correlates candidate proxies
   into a centralized DuckDB (`outputs/epi_data.duckdb`), then emits structured hypotheses.
2. **Stage 2 — Verification & Validation**: For hypotheses whose data was fetched during
   discovery, a deterministic statistics pipeline (`verify_hypothesis_from_db`) computes
   bivariate + partial correlations, functional form, and verdict directly from the
   DuckDB. Literature-attested and manual-data hypotheses fall back to an LLM
   code-generation agent that writes and runs `verify.py`. An LLM validator
   then evaluates 10 inclusion criteria.

The pipeline is model-agnostic, supporting cloud providers (Anthropic, OpenAI) as well
as local open-weights models (DeepSeek, Qwen, GPT-OSS) via vLLM and SGLang.

## Deployment (Hugging Face Spaces)

1. Create a Space at `huggingface.co/new-space` with **Docker** SDK.
2. Add secrets in Space settings: `ANTHROPIC_API_KEY`.
3. Push:
   ```bash
   git remote add hf https://huggingface.co/spaces/<user>/epi-proxy-discovery
   git push hf main
   ```

