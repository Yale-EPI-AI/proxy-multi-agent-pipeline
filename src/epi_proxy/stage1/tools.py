"""Tool definitions and execution dispatcher for the discovery agent.

Provides 15 tools across 4 data sources + 3 DB tools that let the
Claude discovery agent search, preview, fetch, and correlate data.
"""

from __future__ import annotations

import json
import logging
import traceback

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool JSON schemas (Anthropic tool-use format)
# ---------------------------------------------------------------------------

DISCOVERY_TOOLS: list[dict] = [
    # ── World Bank (3) ────────────────────────────────────────────────────
    {
        "name": "search_world_bank",
        "description": "Search the World Bank indicator catalog by keyword. Returns up to max_results matching indicators with their codes and names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'water access', 'fertilizer')"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_world_bank",
        "description": "Fetch a World Bank indicator for a few sample countries to check data availability and coverage before committing to a full fetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_code": {"type": "string", "description": "World Bank indicator code (e.g. 'SH.H2O.BASW.ZS')"},
            },
            "required": ["indicator_code"],
        },
    },
    {
        "name": "fetch_world_bank",
        "description": "Fetch a World Bank indicator for all EPI countries and store in the database. Returns the variable_id for use in correlations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_code": {"type": "string", "description": "World Bank indicator code"},
            },
            "required": ["indicator_code"],
        },
    },
    # ── WHO GHO (3) ──────────────────────────────────────────────────────
    {
        "name": "search_who_gho",
        "description": "Search the WHO Global Health Observatory indicator catalog by keyword. Returns matching indicator codes and names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'diarrhea', 'air pollution')"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_who_gho",
        "description": "Fetch a WHO GHO indicator for preview to check coverage before a full fetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_code": {"type": "string", "description": "WHO GHO indicator code (e.g. 'WHOSIS_000001')"},
            },
            "required": ["indicator_code"],
        },
    },
    {
        "name": "fetch_who_gho",
        "description": "Fetch a WHO GHO indicator for all countries and store in the database. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_code": {"type": "string", "description": "WHO GHO indicator code"},
            },
            "required": ["indicator_code"],
        },
    },
    # ── NASA POWER (3) ───────────────────────────────────────────────────
    {
        "name": "search_nasa_power",
        "description": "Search NASA POWER's ~380 climate/energy parameters by keyword. Returns parameter codes, names, and units.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'temperature', 'solar radiation', 'precipitation')"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_nasa_power",
        "description": "Fetch a NASA POWER parameter for 3 sample countries to check data availability before a full fetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string", "description": "NASA POWER parameter code (e.g. 'T2M', 'ALLSKY_SFC_SW_DWN')"},
            },
            "required": ["parameter"],
        },
    },
    {
        "name": "fetch_nasa_power",
        "description": "Fetch a NASA POWER parameter for all EPI countries and store in the database. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string", "description": "NASA POWER parameter code"},
            },
            "required": ["parameter"],
        },
    },
    # ── FAOSTAT (3) ──────────────────────────────────────────────────────
    {
        "name": "search_faostat",
        "description": "Search FAOSTAT domains and items by keyword. Returns domain codes, item codes, and names for agriculture/food data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'wheat production', 'fertilizer', 'pesticide')"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_faostat",
        "description": "Fetch a small FAOSTAT sample to check coverage before a full fetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "FAOSTAT domain code (e.g. 'QCL', 'RL', 'EF')"},
                "item_code": {"type": "string", "description": "Item code within the domain"},
                "element_code": {"type": "string", "default": "5510", "description": "Element code (default: 5510 = Production)"},
            },
            "required": ["domain", "item_code"],
        },
    },
    {
        "name": "fetch_faostat",
        "description": "Fetch FAOSTAT data for all countries and store in the database. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "FAOSTAT domain code"},
                "item_code": {"type": "string", "description": "Item code within the domain"},
                "element_code": {"type": "string", "default": "5510", "description": "Element code"},
            },
            "required": ["domain", "item_code"],
        },
    },
    # ── GDELT GKG (3) ────────────────────────────────────────────────────
    {
        "name": "search_gdelt",
        "description": "Search the curated GDELT GKG theme catalog for environment/policy/disaster themes. Use for NEWS SALIENCE / ATTENTION proxies — how often each country's media coverage mentions a topic. Useful for indicators where policy pressure or event frequency correlates with outcomes (deforestation, wildfires, pollution).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword (e.g. 'climate', 'pollution', 'wildfire', 'disaster')"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_gdelt",
        "description": "Preview a GDELT theme with a 1-day sample query. Returns estimated BigQuery cost + top 5 country mention counts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "GDELT theme string (e.g. 'ENV_CLIMATECHANGE')"},
            },
            "required": ["theme"],
        },
    },
    {
        "name": "fetch_gdelt",
        "description": "Fetch annual country-year share (theme_mentions / all_mentions) for a GDELT theme via BigQuery. Scans ~475 GB per year — expensive. Default year range is 5 years. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "GDELT theme string"},
            },
            "required": ["theme"],
        },
    },
    # ── Google Earth Engine (3) ──────────────────────────────────────────
    {
        "name": "search_gee",
        "description": "Search the live Earth Engine STAC catalog for ImageCollection assets. Filters to global, 10+-year, 2018+ datasets matching the query. Use for SATELLITE-DERIVED proxies: vegetation (MODIS NDVI), atmospheric composition (Sentinel-5P NO2/CH4/SO2), nighttime lights (VIIRS), burned area (MCD64A1), tree cover (MOD44B). Returns asset_id, title, band list, year range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword (e.g. 'NDVI', 'nitrogen dioxide', 'fire', 'nightlight', 'precipitation')"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_gee",
        "description": "Quick metadata check on a GEE asset+band. Verifies the asset exists and has images.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "GEE asset ID, e.g. 'MODIS/061/MOD13A3'"},
                "band": {"type": "string", "description": "Band name, e.g. 'NDVI'"},
            },
            "required": ["asset_id", "band"],
        },
    },
    {
        "name": "fetch_gee",
        "description": "Fetch per-country annual reductions (mean, sum, count, or mode) of one band from a GEE ImageCollection and store in the database. Temporal collapse happens BEFORE spatial reduction. Scale floor is 50km (country-means are indistinguishable at finer scales). Multi-minute per year; Sentinel-5P-class datasets take ~200s per year at 208 countries. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "GEE asset ID"},
                "band": {"type": "string", "description": "Band name to reduce"},
                "reducer": {"type": "string", "enum": ["mean", "sum", "count", "mode"], "description": "Reducer to use. Auto-picked by band name if omitted (mean for continuous, sum for flux/count, mode for categorical)."},
            },
            "required": ["asset_id", "band"],
        },
    },
    # ── OpenAQ (3) ───────────────────────────────────────────────────────
    {
        "name": "search_openaq",
        "description": "Search OpenAQ's air quality parameter catalog by keyword. Returns parameters like PM2.5, NO2, O3, SO2, CO, PM10. Use to find sensor network measurements as DIRECT air quality proxies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Parameter keyword (e.g. 'pm25', 'nitrogen', 'ozone')"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_openaq",
        "description": "Preview OpenAQ coverage for a parameter across a handful of sample countries. Returns per-sample-country station counts. OpenAQ has severe rich-country bias — rich countries have 100+ stations, many LDCs have 0-3.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string", "description": "Parameter name (e.g. 'pm25', 'no2', 'o3')"},
            },
            "required": ["parameter"],
        },
    },
    {
        "name": "fetch_openaq",
        "description": "Fetch OpenAQ annual country-mean for a parameter and store in the database. Aggregates unweighted across all sensors per country-year; drops country-years with fewer than 3 sensors. Slow (multi-minute per parameter). Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string", "description": "Parameter name"},
            },
            "required": ["parameter"],
        },
    },
    # ── UN Comtrade (3) ─────────────────────────────────────────────────
    {
        "name": "search_comtrade",
        "description": "Search the UN Comtrade HS6 commodity catalog by keyword. Returns matching HS codes (4-digit headings preferred). Use to find product-level trade flows as CONSUMPTION proxies — e.g. fertilizer imports, cement trade, pharma imports, petroleum. Prefer these over % of GDP or generic development indicators.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword (e.g. 'fertilizer', 'cement', 'medicament', 'petroleum', 'waste paper')"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_comtrade",
        "description": "Fetch one year of a Comtrade commodity flow to check country coverage before a full fetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hs_code": {"type": "string", "description": "HS code (4 or 6 digit), e.g. '3102' for nitrogenous fertilizers"},
                "flow": {"type": "string", "enum": ["M", "X"], "default": "M", "description": "M=imports, X=exports"},
                "year": {"type": "integer", "default": 2022, "description": "Year to preview"},
            },
            "required": ["hs_code"],
        },
    },
    {
        "name": "fetch_comtrade",
        "description": "Fetch UN Comtrade annual trade flows (imports or exports vs. world) for a commodity across all EPI countries and store in the database. One record per country-year. Returns physical kg when available, USD fallback otherwise. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hs_code": {"type": "string", "description": "HS code (4 or 6 digit)"},
                "flow": {"type": "string", "enum": ["M", "X"], "default": "M", "description": "M=imports, X=exports"},
            },
            "required": ["hs_code"],
        },
    },
    # ── Wikipedia Pageviews (3) ──────────────────────────────────────────
    {
        "name": "search_wikipedia",
        "description": "Search Wikipedia (via en.wikipedia opensearch) for article titles matching a keyword. Use this to find article names before calling preview_wikipedia or fetch_wikipedia. Pageviews are a behavioral/attention proxy — good for indicators where public awareness or information-seeking correlates with conditions (disease symptoms, pollution events, disasters).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (e.g. 'diarrhea', 'air pollution', 'drought')"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "preview_wikipedia",
        "description": "Preview an article's pageview coverage on one Wikipedia language edition. Returns years covered and total pageviews since 2015.",
        "input_schema": {
            "type": "object",
            "properties": {
                "article": {"type": "string", "description": "Exact Wikipedia article title (e.g. 'Diarrhea')"},
                "project": {"type": "string", "default": "en.wikipedia", "description": "Wikipedia project, e.g. 'en.wikipedia', 'ja.wikipedia'"},
            },
            "required": ["article"],
        },
    },
    {
        "name": "fetch_wikipedia",
        "description": "Fetch per-article annual pageviews for all EPI countries and store in the database. Each country is routed to its primary Wikipedia language edition; countries sharing a language (English, Spanish, French, Arabic, Portuguese, Russian, Chinese) receive IDENTICAL values per year — this is a regional/linguistic attention signal, not a country-specific one. Best used when the article title exists across most target Wikipedias. Returns the variable_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "article": {"type": "string", "description": "Exact Wikipedia article title"},
            },
            "required": ["article"],
        },
    },
    # ── DB tools (3) ─────────────────────────────────────────────────────
    {
        "name": "quick_correlate",
        "description": "Compute a quick bivariate correlation between two variables already in the database. Use this to pre-screen proxy candidates before committing to a full hypothesis. Returns Pearson r, Spearman rho, p-values, and sample size.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x_variable_id": {"type": "string", "description": "Variable ID for x (e.g. 'wb:SH.H2O.BASW.ZS' or 'epi:UWD')"},
                "y_variable_id": {"type": "string", "description": "Variable ID for y (e.g. 'epi:UWD')"},
            },
            "required": ["x_variable_id", "y_variable_id"],
        },
    },
    {
        "name": "list_db_variables",
        "description": "List all variables currently stored in the database. Optionally filter by source_type ('epi', 'world_bank', 'who_gho', 'nasa_power', 'faostat', 'wikipedia', 'comtrade', 'openaq', 'gee', 'gdelt').",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_type": {"type": "string", "description": "Optional filter by source type"},
            },
            "required": [],
        },
    },
    {
        "name": "variable_coverage",
        "description": "Get coverage statistics for a variable in the database: number of observations, countries, and year range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "variable_id": {"type": "string", "description": "Variable ID (e.g. 'epi:UWD', 'wb:SH.H2O.BASW.ZS')"},
            },
            "required": ["variable_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution dispatcher
# ---------------------------------------------------------------------------


def execute_tool(tool_name: str, tool_input: dict, conn) -> str:
    """Dispatch a tool call to the appropriate function.

    Returns a JSON string with the result or error.
    """
    try:
        result = _dispatch(tool_name, tool_input, conn)
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.warning("Tool %s failed: %s", tool_name, exc)
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()[-500:]})


def _dispatch(tool_name: str, tool_input: dict, conn) -> dict | list:
    """Route tool call to the right function."""
    from epi_proxy.utils.data_fetch import (
        fetch_and_store_comtrade,
        fetch_and_store_faostat,
        fetch_and_store_gdelt,
        fetch_and_store_gee,
        fetch_and_store_nasa_power,
        fetch_and_store_openaq,
        fetch_and_store_wikipedia,
        fetch_and_store_world_bank,
        fetch_and_store_who_gho,
        fetch_world_bank_indicator,
        fetch_who_gho_indicator,
        preview_comtrade,
        preview_faostat,
        preview_gdelt,
        preview_gee,
        preview_nasa_power,
        preview_openaq,
        preview_wikipedia,
        search_comtrade,
        search_faostat,
        search_gdelt,
        search_gee,
        search_nasa_power,
        search_openaq,
        search_wikipedia,
        search_who_gho,
        search_world_bank,
    )
    from epi_proxy.utils.db import list_variables, variable_coverage
    from epi_proxy.utils.db_stats import run_bivariate_correlation

    # ── World Bank ────────────────────────────────────────────────────
    if tool_name == "search_world_bank":
        return search_world_bank(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_world_bank":
        code = tool_input["indicator_code"]
        df = fetch_world_bank_indicator(code, year_range=(2010, 2022))
        if df.empty:
            return {"indicator_code": code, "n_countries": 0, "n_observations": 0, "years": []}
        return {
            "indicator_code": code,
            "n_countries": int(df["iso"].nunique()),
            "n_observations": len(df),
            "years": sorted(df["year"].unique().tolist()),
            "sample_countries": df["iso"].unique()[:5].tolist(),
        }

    if tool_name == "fetch_world_bank":
        variable_id = fetch_and_store_world_bank(
            conn, tool_input["indicator_code"], triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── WHO GHO ──────────────────────────────────────────────────────
    if tool_name == "search_who_gho":
        return search_who_gho(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_who_gho":
        code = tool_input["indicator_code"]
        df = fetch_who_gho_indicator(code)
        if df.empty:
            return {"indicator_code": code, "n_countries": 0, "n_observations": 0, "years": []}
        return {
            "indicator_code": code,
            "n_countries": int(df["iso"].nunique()),
            "n_observations": len(df),
            "years": sorted(df["year"].unique().tolist()),
            "sample_countries": df["iso"].unique()[:5].tolist(),
        }

    if tool_name == "fetch_who_gho":
        variable_id = fetch_and_store_who_gho(
            conn, tool_input["indicator_code"], triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── NASA POWER ───────────────────────────────────────────────────
    if tool_name == "search_nasa_power":
        return search_nasa_power(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_nasa_power":
        return preview_nasa_power(tool_input["parameter"])

    if tool_name == "fetch_nasa_power":
        variable_id = fetch_and_store_nasa_power(
            conn, tool_input["parameter"], triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── GDELT GKG ─────────────────────────────────────────────────────
    if tool_name == "search_gdelt":
        return search_gdelt(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_gdelt":
        return preview_gdelt(tool_input["theme"])

    if tool_name == "fetch_gdelt":
        variable_id = fetch_and_store_gdelt(
            conn, tool_input["theme"], triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── Google Earth Engine ──────────────────────────────────────────
    if tool_name == "search_gee":
        return search_gee(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_gee":
        return preview_gee(tool_input["asset_id"], tool_input["band"])

    if tool_name == "fetch_gee":
        variable_id = fetch_and_store_gee(
            conn,
            tool_input["asset_id"],
            tool_input["band"],
            reducer=tool_input.get("reducer"),
            triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── OpenAQ ───────────────────────────────────────────────────────
    if tool_name == "search_openaq":
        return search_openaq(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_openaq":
        return preview_openaq(tool_input["parameter"])

    if tool_name == "fetch_openaq":
        variable_id = fetch_and_store_openaq(
            conn, tool_input["parameter"], triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── UN Comtrade ──────────────────────────────────────────────────
    if tool_name == "search_comtrade":
        return search_comtrade(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_comtrade":
        return preview_comtrade(
            tool_input["hs_code"],
            flow=tool_input.get("flow", "M"),
            year=tool_input.get("year", 2022),
        )

    if tool_name == "fetch_comtrade":
        variable_id = fetch_and_store_comtrade(
            conn,
            tool_input["hs_code"],
            flow=tool_input.get("flow", "M"),
            triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── Wikipedia ────────────────────────────────────────────────────
    if tool_name == "search_wikipedia":
        return search_wikipedia(tool_input["query"], tool_input.get("max_results", 10))

    if tool_name == "preview_wikipedia":
        return preview_wikipedia(
            tool_input["article"],
            tool_input.get("project", "en.wikipedia"),
        )

    if tool_name == "fetch_wikipedia":
        variable_id = fetch_and_store_wikipedia(
            conn, tool_input["article"], triggered_by="discovery_agent",
        )
        cov = variable_coverage(conn, variable_id)
        return {"variable_id": variable_id, **cov}

    # ── FAOSTAT ──────────────────────────────────────────────────────
    # FAO's primary API host (fenixservices.fao.org) is currently returning
    # 521/timeouts. Short-circuit these tools with a clear message so the
    # agent doesn't waste its budget on a dead service.
    if tool_name in ("search_faostat", "preview_faostat", "fetch_faostat"):
        return {
            "error": "FAOSTAT API unavailable",
            "detail": (
                "The FAO FAOSTAT API (fenixservices.fao.org) is currently "
                "down (Cloudflare 521 / read timeout). Do not call any "
                "faostat tools for the rest of this session — use World "
                "Bank, WHO GHO, or NASA POWER instead."
            ),
        }

    # ── DB tools ─────────────────────────────────────────────────────
    if tool_name == "quick_correlate":
        corr = run_bivariate_correlation(
            conn, tool_input["x_variable_id"], tool_input["y_variable_id"],
        )
        return corr.model_dump()

    if tool_name == "list_db_variables":
        source_type = tool_input.get("source_type")
        df = list_variables(conn, source_type)
        # Return a concise summary
        records = df[["variable_id", "name", "source_type"]].to_dict("records")
        return records

    if tool_name == "variable_coverage":
        return variable_coverage(conn, tool_input["variable_id"])

    raise ValueError(f"Unknown tool: {tool_name}")
