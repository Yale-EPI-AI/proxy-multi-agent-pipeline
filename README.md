---
title: EPI Proxy Discovery Pipeline
emoji: "\U0001F30D"
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
pip install -e .
pip install gradio

# Set API keys
export ANTHROPIC_API_KEY=...

# Launch web UI
python web/app.py
# → opens at http://localhost:7860

# Or run via CLI
python -m src -i WRR
```

## Architecture

1. **Stage 1 — Discovery Agent**: Claude Sonnet 4.6 with ~30 data-source tools
   (World Bank, WHO GHO, NASA POWER, Wikipedia, UN Comtrade, OpenAQ, Google Earth
   Engine, GDELT) searches, previews, fetches, and pre-correlates candidate proxies
   into a centralized DuckDB, then emits structured hypotheses.
2. **Stage 2 — Verification**: for hypotheses whose data was fetched during
   discovery, a deterministic statistics pipeline (`run_full_verification`) computes
   bivariate + partial correlations, functional form, and verdict directly from the
   DB. Literature-attested and manual-data hypotheses fall back to a Claude Code
   SDK agent that writes a `verify.py` and runs it.

## Deployment (Hugging Face Spaces)

1. Create a Space at `huggingface.co/new-space` with **Docker** SDK.
2. Add secrets in Space settings: `ANTHROPIC_API_KEY`.
3. Push:
   ```bash
   git remote add hf https://huggingface.co/spaces/<user>/epi-proxy-discovery
   git push hf main
   ```
