"""Data fetching utilities: World Bank, WHO GHO, NASA POWER, FAOSTAT,
Wikipedia pageviews, UN Comtrade, OpenAQ, Google Earth Engine, GDELT BQ.

Provides reusable wrappers so Stage 2 verification agents don't need to write
API boilerplate from scratch. All fetch functions return a standardized
long-format DataFrame with columns (iso, year, value) that merges directly
with load_raw_indicator() output on (iso, year).
"""

import json as _json
import logging
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from epi_proxy.config import MASTER_FILE, MASTER_VARIABLE_LIST, PROJECT_ROOT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local control variables — already on disk as raw CSVs.
# Agents should use load_raw_indicator(TLA) for these, NOT re-download them.
# ---------------------------------------------------------------------------
LOCAL_CONTROLS: dict[str, str] = {
    "GPC": "GDP per capita, PPP (constant 2017 intl $)",
    "HDI": "Human Development Index (0-1)",
    "POP": "Total population",
    "URB": "Urban population (% of total)",
}

_WB_BASE = "https://api.worldbank.org/v2"
_WHO_BASE = "https://ghoapi.azureedge.net/api"
_REQUEST_TIMEOUT = 60

_epi_iso_cache: set[str] | None = None


def _get_epi_iso_set() -> set[str]:
    """Return the set of ISO3 codes from MasterFile.csv (cached after first call).

    If the file is missing or unreadable, returns an empty set so that
    downstream filtering degrades gracefully (no ISOs are excluded).
    """
    global _epi_iso_cache
    if _epi_iso_cache is not None:
        return _epi_iso_cache
    try:
        df = pd.read_csv(MASTER_FILE)
        _epi_iso_cache = set(df["iso"].dropna().astype(str).str.strip())
    except Exception as exc:
        logger.warning("Could not read MasterFile.csv for ISO filtering: %s", exc)
        _epi_iso_cache = set()
    return _epi_iso_cache


# ---------------------------------------------------------------------------
# World Bank
# ---------------------------------------------------------------------------

def fetch_world_bank_indicator(
    indicator_code: str,
    year_range: tuple[int, int] = (1990, 2024),
) -> pd.DataFrame:
    """Fetch any World Bank indicator by code.

    Returns a DataFrame with columns ``iso``, ``year``, ``value``.
    Handles pagination, null filtering, and ISO3 validation.
    Returns an empty DataFrame on failure (with a logged warning).

    Parameters
    ----------
    indicator_code : str
        World Bank indicator code, e.g. ``"SH.H2O.BASW.ZS"`` or ``"NY.GDP.PCAP.PP.KD"``.
    year_range : tuple[int, int]
        Inclusive (start, end) year range.
    """
    start, end = year_range
    url = (
        f"{_WB_BASE}/country/all/indicator/{indicator_code}"
        f"?format=json&per_page=20000&date={start}:{end}"
    )

    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("World Bank fetch failed for %s: %s", indicator_code, exc)
        return pd.DataFrame(columns=["iso", "year", "value"])

    # The WB JSON API returns a two-element list: [metadata, records].
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        logger.warning(
            "World Bank returned unexpected payload for %s (possibly invalid code)",
            indicator_code,
        )
        return pd.DataFrame(columns=["iso", "year", "value"])

    epi_isos = _get_epi_iso_set()

    records: list[dict] = []
    for item in payload[1]:
        iso = item.get("countryiso3code", "")
        val = item.get("value")
        date = item.get("date", "")
        # Skip nulls, aggregates (empty ISO or wrong length), bad years
        if val is None or len(iso) != 3 or not date.isdigit():
            continue
        # Filter out WB region/income aggregate codes (WLD, SSA, HIC, etc.)
        if epi_isos and iso not in epi_isos:
            continue
        records.append({"iso": iso, "year": int(date), "value": float(val)})

    if not records:
        logger.warning("World Bank returned 0 valid records for %s", indicator_code)

    return pd.DataFrame(records, columns=["iso", "year", "value"])


def search_world_bank(query: str, max_results: int = 10) -> list[dict]:
    """Search the World Bank indicator catalog by keyword.

    Returns a list of ``{"id", "name", "source"}`` dicts (up to *max_results*).
    Useful when the agent doesn't know the exact indicator code.

    Uses source=2 (World Development Indicators) to limit results to the
    most relevant dataset, and fetches a larger page to allow client-side
    keyword filtering since the WB API ``qterm`` parameter is unreliable.
    """
    # Fetch a generous page from WDI (source=2) so we can filter client-side.
    fetch_size = max(max_results * 30, 300)
    url = (
        f"{_WB_BASE}/indicator"
        f"?format=json&per_page={fetch_size}&source=2"
    )

    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("World Bank search failed for %r: %s", query, exc)
        return []

    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return []

    # Client-side keyword matching (case-insensitive)
    query_lower = query.lower()
    query_words = query_lower.split()
    results: list[dict] = []
    for item in payload[1]:
        name = item.get("name", "")
        indicator_id = item.get("id", "")
        text = f"{name} {indicator_id}".lower()
        if any(word in text for word in query_words):
            results.append({
                "id": indicator_id,
                "name": name,
                "source": item.get("source", {}).get("value", ""),
            })
            if len(results) >= max_results:
                break
    return results


# ---------------------------------------------------------------------------
# WHO Global Health Observatory
# ---------------------------------------------------------------------------

def _dedup_who_gho(df: pd.DataFrame, indicator_code: str) -> pd.DataFrame:
    """Remove WHO GHO sub-dimension duplicates (sex/area breakdowns).

    Many GHO indicators return multiple rows per (iso, year) — e.g. one each
    for male, female, and both-sexes. We keep only the aggregate row:

    1. If all ``Dim1`` values are None → no breakdowns, pass through unchanged.
    2. If rows with ``_BTSX`` or ``_TOTL`` suffix exist → keep only those.
    3. Otherwise (unknown Dim1 pattern) → log a warning and pass through
       unchanged rather than silently picking an arbitrary breakdown.
    """
    if "Dim1" not in df.columns or df.empty:
        return df

    dim1_values = df["Dim1"].unique()

    # Case 1: all None — no sub-dimensions at all
    if len(dim1_values) == 1 and pd.isna(dim1_values[0]):
        return df.drop(columns=["Dim1"])

    # Case 2: aggregate markers present — keep only those
    aggregate_mask = df["Dim1"].str.endswith("_BTSX", na=False) | df["Dim1"].str.endswith("_TOTL", na=False)
    if aggregate_mask.any():
        before = len(df)
        df = df[aggregate_mask].copy()
        logger.info(
            "WHO GHO %s: deduped %d → %d rows (kept _BTSX/_TOTL aggregates)",
            indicator_code, before, len(df),
        )
        return df.drop(columns=["Dim1"])

    # Case 3: unknown Dim1 pattern — warn and pass through
    non_null = [v for v in dim1_values if pd.notna(v)]
    logger.warning(
        "WHO GHO %s: unknown Dim1 values %s — skipping dedup. "
        "Data may contain duplicate (iso, year) rows.",
        indicator_code, non_null[:5],
    )
    return df.drop(columns=["Dim1"])


def fetch_who_gho_indicator(indicator_code: str) -> pd.DataFrame:
    """Fetch any WHO GHO indicator by code.

    Returns a DataFrame with columns ``iso``, ``year``, ``value``.
    Uses the GHO OData API at ``https://ghoapi.azureedge.net/api/{code}``.
    Deduplicates sub-dimension breakdowns (sex, area) to avoid row inflation.
    Returns an empty DataFrame on failure.

    Parameters
    ----------
    indicator_code : str
        WHO GHO indicator code, e.g. ``"WHOSIS_000001"`` or ``"WHS3_41"``.
    """
    url = f"{_WHO_BASE}/{indicator_code}"

    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("WHO GHO fetch failed for %s: %s", indicator_code, exc)
        return pd.DataFrame(columns=["iso", "year", "value"])

    items = payload.get("value", [])
    records: list[dict] = []
    for item in items:
        iso = item.get("SpatialDim", "")
        year = item.get("TimeDim")
        val = item.get("NumericValue")
        dim1 = item.get("Dim1")
        if val is None or len(iso) != 3 or year is None:
            continue
        try:
            records.append({
                "iso": iso, "year": int(year), "value": float(val), "Dim1": dim1,
            })
        except (ValueError, TypeError):
            continue

    if not records:
        logger.warning("WHO GHO returned 0 valid records for %s", indicator_code)
        return pd.DataFrame(columns=["iso", "year", "value"])

    df = pd.DataFrame(records)
    df = _dedup_who_gho(df, indicator_code)
    return df[["iso", "year", "value"]]


# ---------------------------------------------------------------------------
# DB-aware fetch-and-store wrappers
# ---------------------------------------------------------------------------


def fetch_and_store_world_bank(
    conn,
    indicator_code: str,
    year_range: tuple[int, int] = (1990, 2024),
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch a World Bank indicator, store in DB, return the variable_id.

    Checks DB first — skips the API call if data already exists
    (unless force_refresh is True).
    """
    from epi_proxy.utils.db import register_variable, upsert_observations, variable_exists, variable_coverage

    variable_id = f"wb:{indicator_code}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info("DB hit: %s already has %d observations, skipping fetch", variable_id, cov["n_observations"])
            return variable_id

    df = fetch_world_bank_indicator(indicator_code, year_range)

    # Look up display name via search (best-effort)
    name = indicator_code
    try:
        results = search_world_bank(indicator_code, max_results=1)
        if results:
            name = results[0].get("name", indicator_code)
    except Exception:
        pass

    register_variable(
        conn,
        variable_id,
        name=name,
        source_type="world_bank",
        source_org="World Bank",
        source_code=indicator_code,
        source_url=f"https://data.worldbank.org/indicator/{indicator_code}",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_WB_BASE}/country/all/indicator/{indicator_code}",
    )
    return variable_id


def fetch_and_store_who_gho(
    conn,
    indicator_code: str,
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch a WHO GHO indicator, store in DB, return the variable_id.

    Checks DB first — skips the API call if data already exists
    (unless force_refresh is True).
    """
    from epi_proxy.utils.db import register_variable, upsert_observations, variable_exists, variable_coverage

    variable_id = f"who:{indicator_code}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info("DB hit: %s already has %d observations, skipping fetch", variable_id, cov["n_observations"])
            return variable_id

    df = fetch_who_gho_indicator(indicator_code)

    register_variable(
        conn,
        variable_id,
        name=indicator_code,
        source_type="who_gho",
        source_org="WHO",
        source_code=indicator_code,
        source_url=f"https://ghoapi.azureedge.net/api/{indicator_code}",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_WHO_BASE}/{indicator_code}",
    )
    return variable_id


# ---------------------------------------------------------------------------
# WHO GHO Search
# ---------------------------------------------------------------------------


def search_who_gho(query: str, max_results: int = 10) -> list[dict]:
    """Search the WHO Global Health Observatory indicator catalog by keyword.

    Returns a list of ``{"id", "name"}`` dicts (up to *max_results*).
    """
    url = f"{_WHO_BASE}/Indicator"
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("WHO GHO search failed: %s", exc)
        return []

    items = payload.get("value", [])
    query_lower = query.lower()
    matches: list[dict] = []
    for item in items:
        name = item.get("IndicatorName", "")
        code = item.get("IndicatorCode", "")
        if query_lower in name.lower() or query_lower in code.lower():
            matches.append({"id": code, "name": name})
            if len(matches) >= max_results:
                break
    return matches


# ---------------------------------------------------------------------------
# NASA POWER
# ---------------------------------------------------------------------------

_NASA_POWER_BASE = "https://power.larc.nasa.gov/api"
_NASA_PARAMS_CACHE: list[dict] | None = None
_NASA_PARAMS_FILE = Path(__file__).parent / "nasa_power_params.json"


def _load_nasa_power_params() -> list[dict]:
    """Load NASA POWER parameter catalog (from cache file or API)."""
    global _NASA_PARAMS_CACHE
    if _NASA_PARAMS_CACHE is not None:
        return _NASA_PARAMS_CACHE

    # Try local cache first
    if _NASA_PARAMS_FILE.exists():
        try:
            _NASA_PARAMS_CACHE = _json.loads(_NASA_PARAMS_FILE.read_text())
            return _NASA_PARAMS_CACHE
        except Exception:
            pass

    # Fetch from API. NASA POWER requires community + temporal query params.
    # Use temporal=daily (139 base params) since monthly returns 1000+ duplicates
    # (one per calendar month of each param).
    try:
        resp = requests.get(
            f"{_NASA_POWER_BASE}/system/manager/parameters",
            params={"community": "ag", "temporal": "daily"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Failed to fetch NASA POWER parameter catalog: %s", exc)
        return []

    # Parse into a flat list
    params: list[dict] = []
    # The API returns a dict keyed by parameter name
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, dict):
                params.append({
                    "parameter": key,
                    "name": val.get("long_name", val.get("name", key)),
                    "units": val.get("units", ""),
                    "communities": val.get("communities", []),
                })
            else:
                params.append({"parameter": key, "name": str(val), "units": "", "communities": []})

    # Cache locally
    try:
        _NASA_PARAMS_FILE.write_text(_json.dumps(params, indent=2))
    except Exception:
        pass

    _NASA_PARAMS_CACHE = params
    return params


def search_nasa_power(query: str, max_results: int = 10) -> list[dict]:
    """Search the NASA POWER parameter catalog by keyword.

    Returns a list of ``{"parameter", "name", "units"}`` dicts.
    """
    params = _load_nasa_power_params()
    query_lower = query.lower()
    matches: list[dict] = []
    for p in params:
        if (query_lower in p.get("name", "").lower()
                or query_lower in p.get("parameter", "").lower()):
            matches.append({
                "parameter": p["parameter"],
                "name": p.get("name", ""),
                "units": p.get("units", ""),
            })
            if len(matches) >= max_results:
                break
    return matches


def _fetch_nasa_power_point(
    parameter: str, lat: float, lon: float, start_year: int, end_year: int,
) -> dict[int, float]:
    """Fetch a single NASA POWER point as monthly data, aggregate to annual mean.

    Returns a dict of ``{year: annual_mean}``. NASA POWER has no annual temporal
    endpoint — we request monthly and average on our side.
    """
    url = (
        f"{_NASA_POWER_BASE}/temporal/monthly/point"
        f"?parameters={parameter}&community=ag"
        f"&start={start_year}&end={end_year}"
        f"&latitude={lat}&longitude={lon}&format=JSON"
    )
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    # Response keys look like "YYYYMM" or "YYYY13" (annual mean row that POWER adds).
    param_data = data.get("properties", {}).get("parameter", {}).get(parameter, {})
    by_year: dict[int, list[float]] = {}
    for key, val in param_data.items():
        if val is None or val == -999.0:
            continue
        try:
            fval = float(val)
        except (ValueError, TypeError):
            continue
        key_str = str(key)
        if len(key_str) < 6:
            continue
        year = int(key_str[:4])
        month = int(key_str[4:6])
        if month == 13:
            # POWER's pre-computed annual row — prefer it
            by_year[year] = [fval]
        elif 1 <= month <= 12:
            by_year.setdefault(year, []).append(fval)

    return {y: sum(vs) / len(vs) for y, vs in by_year.items() if vs}


def preview_nasa_power(
    parameter: str,
    sample_isos: list[str] | None = None,
) -> dict:
    """Fetch NASA POWER data for a few sample countries, return coverage stats.

    Returns ``{"parameter", "sample_countries", "years", "n_observations"}``.
    """
    from epi_proxy.utils.country_codes import get_country_centroids

    if sample_isos is None:
        sample_isos = ["USA", "BRA", "IND"]

    centroids = get_country_centroids()
    records: list[dict] = []

    for iso3 in sample_isos:
        coords = centroids.get(iso3)
        if not coords:
            continue
        lat, lon = coords
        try:
            annual = _fetch_nasa_power_point(parameter, lat, lon, 2000, 2022)
        except (requests.RequestException, ValueError) as exc:
            logger.debug("NASA POWER preview failed for %s/%s: %s", iso3, parameter, exc)
            continue
        for year, val in annual.items():
            records.append({"iso": iso3, "year": year, "value": val})

    years = sorted(set(r["year"] for r in records)) if records else []
    return {
        "parameter": parameter,
        "sample_countries": sorted(set(r["iso"] for r in records))[:3],
        "years": years,
        "n_observations": len(records),
    }


def fetch_nasa_power(
    parameter: str,
    year_range: tuple[int, int] = (1990, 2022),
) -> pd.DataFrame:
    """Fetch NASA POWER data for all EPI countries via point API.

    Uses country centroids. Returns DataFrame with columns (iso, year, value).
    """
    from epi_proxy.utils.country_codes import get_country_centroids

    centroids = get_country_centroids()
    epi_isos = _get_epi_iso_set()
    start, end = year_range

    records: list[dict] = []
    target_isos = epi_isos if epi_isos else set(centroids.keys())

    for iso3 in target_isos:
        coords = centroids.get(iso3)
        if not coords:
            continue
        lat, lon = coords
        try:
            annual = _fetch_nasa_power_point(parameter, lat, lon, start, end)
        except (requests.RequestException, ValueError) as exc:
            logger.debug("NASA POWER fetch failed for %s/%s: %s", iso3, parameter, exc)
            continue
        for year, val in annual.items():
            records.append({"iso": iso3, "year": year, "value": val})

    if not records:
        logger.warning("NASA POWER returned 0 valid records for %s", parameter)

    return pd.DataFrame(records, columns=["iso", "year", "value"])


def fetch_and_store_nasa_power(
    conn,
    parameter: str,
    year_range: tuple[int, int] = (1990, 2022),
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch NASA POWER data, store in DB, return the variable_id."""
    from epi_proxy.utils.db import register_variable, upsert_observations, variable_exists, variable_coverage

    variable_id = f"nasa:{parameter}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info("DB hit: %s already has %d observations, skipping fetch", variable_id, cov["n_observations"])
            return variable_id

    df = fetch_nasa_power(parameter, year_range)

    # Look up display name
    name = parameter
    params = _load_nasa_power_params()
    for p in params:
        if p["parameter"] == parameter:
            name = p.get("name", parameter)
            break

    register_variable(
        conn,
        variable_id,
        name=name,
        source_type="nasa_power",
        source_org="NASA POWER",
        source_code=parameter,
        source_url=f"https://power.larc.nasa.gov/",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_NASA_POWER_BASE}/temporal/annual/point?parameters={parameter}",
    )
    return variable_id


# ---------------------------------------------------------------------------
# FAOSTAT
# ---------------------------------------------------------------------------

_FAO_BASE = "https://fenixservices.fao.org/faostat/api/v1/en"
_FAO_DOMAINS_CACHE: list[dict] | None = None


def _load_fao_domains() -> list[dict]:
    """Load FAOSTAT domain list (cached after first call)."""
    global _FAO_DOMAINS_CACHE
    if _FAO_DOMAINS_CACHE is not None:
        return _FAO_DOMAINS_CACHE

    try:
        resp = requests.get(f"{_FAO_BASE}/definitions/domain", timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Failed to fetch FAOSTAT domains: %s", exc)
        return []

    _FAO_DOMAINS_CACHE = [
        {"code": d.get("code", ""), "name": d.get("label", "")}
        for d in data
    ]
    return _FAO_DOMAINS_CACHE


def search_faostat(query: str, max_results: int = 10) -> list[dict]:
    """Search FAOSTAT domains and items by keyword.

    Returns a list of ``{"domain_code", "domain_name", "item_code", "item_name"}`` dicts.
    First searches domains, then fetches items for matching domains.
    """
    domains = _load_fao_domains()
    query_lower = query.lower()

    # Search domains
    matching_domains = [
        d for d in domains
        if query_lower in d["name"].lower() or query_lower in d["code"].lower()
    ]

    results: list[dict] = []

    # For each matching domain, try to get items
    for domain in matching_domains[:3]:  # Limit domain queries
        try:
            resp = requests.get(
                f"{_FAO_BASE}/definitions/domain/{domain['code']}/item",
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            items = resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            # Domain match without item detail
            results.append({
                "domain_code": domain["code"],
                "domain_name": domain["name"],
                "item_code": "",
                "item_name": "(search items within domain)",
            })
            continue

        for item in items:
            item_name = item.get("label", "")
            item_code = item.get("code", "")
            if query_lower in item_name.lower() or query_lower in domain["name"].lower():
                results.append({
                    "domain_code": domain["code"],
                    "domain_name": domain["name"],
                    "item_code": item_code,
                    "item_name": item_name,
                })
                if len(results) >= max_results:
                    return results

    return results[:max_results]


def preview_faostat(
    domain: str,
    item_code: str,
    element_code: str = "5510",
) -> dict:
    """Fetch a small sample of FAOSTAT data for coverage preview.

    Returns ``{"domain", "item_code", "element_code", "n_countries", "years", "n_observations"}``.
    """
    from epi_proxy.utils.country_codes import m49_to_iso3

    url = (
        f"{_FAO_BASE}/data/{domain}"
        f"?item_code={item_code}&element_code={element_code}"
        f"&year=2015,2016,2017,2018,2019,2020"
        f"&output_type=objects"
    )
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("FAOSTAT preview failed for %s/%s: %s", domain, item_code, exc)
        return {"domain": domain, "item_code": item_code, "element_code": element_code,
                "n_countries": 0, "years": [], "n_observations": 0}

    countries = set()
    years = set()
    for row in data:
        area_code = row.get("area_code")
        year = row.get("year")
        val = row.get("value")
        if val is not None and area_code:
            iso3 = m49_to_iso3(int(area_code)) if str(area_code).isdigit() else None
            if iso3:
                countries.add(iso3)
            years.add(year)

    return {
        "domain": domain,
        "item_code": item_code,
        "element_code": element_code,
        "n_countries": len(countries),
        "years": sorted(years),
        "n_observations": len(data),
    }


def fetch_faostat(
    domain: str,
    item_code: str,
    element_code: str = "5510",
    year_range: tuple[int, int] = (1990, 2022),
) -> pd.DataFrame:
    """Fetch FAOSTAT data for all countries.

    Uses M49 area codes mapped to ISO3 via country_codes module.
    Returns DataFrame with columns (iso, year, value).
    """
    from epi_proxy.utils.country_codes import m49_to_iso3

    start, end = year_range
    years_str = ",".join(str(y) for y in range(start, end + 1))

    url = (
        f"{_FAO_BASE}/data/{domain}"
        f"?item_code={item_code}&element_code={element_code}"
        f"&year={years_str}"
        f"&output_type=objects"
    )

    try:
        resp = requests.get(url, timeout=90)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("FAOSTAT fetch failed for %s/%s/%s: %s", domain, item_code, element_code, exc)
        return pd.DataFrame(columns=["iso", "year", "value"])

    epi_isos = _get_epi_iso_set()
    records: list[dict] = []
    for row in data:
        area_code = row.get("area_code")
        year = row.get("year")
        val = row.get("value")
        if val is None or area_code is None or year is None:
            continue
        try:
            iso3 = m49_to_iso3(int(area_code))
        except (ValueError, TypeError):
            continue
        if iso3 is None:
            continue
        if epi_isos and iso3 not in epi_isos:
            continue
        try:
            records.append({"iso": iso3, "year": int(year), "value": float(val)})
        except (ValueError, TypeError):
            continue

    if not records:
        logger.warning("FAOSTAT returned 0 valid records for %s/%s/%s", domain, item_code, element_code)

    return pd.DataFrame(records, columns=["iso", "year", "value"])


def fetch_and_store_faostat(
    conn,
    domain: str,
    item_code: str,
    element_code: str = "5510",
    year_range: tuple[int, int] = (1990, 2022),
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch FAOSTAT data, store in DB, return the variable_id."""
    from epi_proxy.utils.db import register_variable, upsert_observations, variable_exists, variable_coverage

    variable_id = f"fao:{domain}:{item_code}:{element_code}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info("DB hit: %s already has %d observations, skipping fetch", variable_id, cov["n_observations"])
            return variable_id

    df = fetch_faostat(domain, item_code, element_code, year_range)

    register_variable(
        conn,
        variable_id,
        name=f"FAOSTAT {domain}/{item_code}/{element_code}",
        source_type="faostat",
        source_org="FAO",
        source_code=f"{domain}/{item_code}/{element_code}",
        source_url=f"https://www.fao.org/faostat/en/#data/{domain}",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_FAO_BASE}/data/{domain}",
    )
    return variable_id


# ---------------------------------------------------------------------------
# Wikipedia Pageviews
# ---------------------------------------------------------------------------
#
# Per-article, per-project pageviews via the Wikimedia REST API. Country
# attribution uses a hand-curated ISO3 -> primary Wikipedia language edition
# mapping in docs/wiki_country_projects.json. For countries whose primary
# edition is shared (en, es, fr, ar, pt, ru, zh), the raw pageview count is
# identical across all countries mapped to that edition — the signal is not
# country-specific and should be treated as a coarse proxy for language-region
# attention rather than per-country behavior. The coverage string and the
# `shared_language_projects` field in variable metadata flag this bias.

_WIKI_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
_WIKI_USER_AGENT = "epi-proxy-discovery/1.0 (https://github.com/SamKouteili/multi-agent; contact@example.com)"
_WIKI_PROJECTS_FILE = PROJECT_ROOT / "docs" / "wiki_country_projects.json"
_WIKI_PROJECTS_CACHE: dict | None = None


def _load_wiki_country_projects() -> dict:
    """Return the ISO3 -> {project, shared} mapping, cached."""
    global _WIKI_PROJECTS_CACHE
    if _WIKI_PROJECTS_CACHE is not None:
        return _WIKI_PROJECTS_CACHE
    try:
        _WIKI_PROJECTS_CACHE = _json.loads(_WIKI_PROJECTS_FILE.read_text())
    except Exception as exc:
        logger.warning("Could not load wiki_country_projects.json: %s", exc)
        _WIKI_PROJECTS_CACHE = {"countries": {}, "_metadata": {}}
    return _WIKI_PROJECTS_CACHE


def _wiki_slug(article: str) -> str:
    """Normalize an article title to the URL form used by the REST API."""
    # Wikimedia expects underscores; quote everything else safely.
    return quote(article.strip().replace(" ", "_"), safe="")


def search_wikipedia(query: str, max_results: int = 10) -> list[dict]:
    """Search Wikipedia for article titles matching *query*.

    Uses the MediaWiki opensearch API against en.wikipedia.org as the primary
    catalog, because the REST pageview endpoint is article-keyed and English
    titles are the most universally present.

    Returns a list of ``{"title", "project", "description"}`` dicts.
    """
    projects_to_probe = ["en.wikipedia.org"]
    results: list[dict] = []
    for project in projects_to_probe:
        url = f"https://{project}/w/api.php"
        params = {
            "action": "opensearch",
            "search": query,
            "limit": max_results,
            "namespace": 0,
            "format": "json",
        }
        try:
            resp = requests.get(
                url, params=params,
                headers={"User-Agent": _WIKI_USER_AGENT},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Wikipedia search failed for %r on %s: %s", query, project, exc)
            continue
        if not isinstance(payload, list) or len(payload) < 4:
            continue
        titles, descriptions, urls = payload[1], payload[2], payload[3]
        for title, desc, u in zip(titles, descriptions, urls):
            results.append({
                "title": title,
                "project": project.replace(".org", ""),
                "description": desc or "",
                "url": u,
            })
            if len(results) >= max_results:
                break
        if results:
            break
    return results


def _fetch_wiki_monthly(
    project: str, article: str, start_year: int, end_year: int,
) -> dict[int, int]:
    """Fetch per-article monthly pageviews, aggregate to yearly sums.

    Returns ``{year: annual_sum_pageviews}``. Pageview counts are pure counts,
    so annual sum is the correct aggregation.
    """
    slug = _wiki_slug(article)
    start = f"{start_year}010100"
    end = f"{end_year + 1}010100"
    url = (
        f"{_WIKI_BASE}/per-article/{project}/all-access/user/"
        f"{slug}/monthly/{start}/{end}"
    )
    try:
        resp = requests.get(
            url, headers={"User-Agent": _WIKI_USER_AGENT}, timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.debug(
            "Wikipedia pageviews fetch failed for %s/%s: %s",
            project, article, exc,
        )
        return {}

    items = payload.get("items", []) if isinstance(payload, dict) else []
    by_year: dict[int, int] = {}
    for item in items:
        ts = str(item.get("timestamp", ""))
        views = item.get("views")
        if not ts or views is None or len(ts) < 6:
            continue
        try:
            year = int(ts[:4])
        except ValueError:
            continue
        if not (start_year <= year <= end_year):
            continue
        try:
            by_year[year] = by_year.get(year, 0) + int(views)
        except (ValueError, TypeError):
            continue
    return by_year


def preview_wikipedia(
    article: str, project: str = "en.wikipedia",
) -> dict:
    """Check pageview availability for an article on one project.

    Returns ``{"article", "project", "years", "n_years", "total_pageviews"}``.
    """
    by_year = _fetch_wiki_monthly(project, article, 2015, 2024)
    return {
        "article": article,
        "project": project,
        "years": sorted(by_year.keys()),
        "n_years": len(by_year),
        "total_pageviews": int(sum(by_year.values())),
    }


def fetch_wikipedia(
    article: str,
    year_range: tuple[int, int] = (2016, 2024),
    countries: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch per-article annual pageviews and attribute to EPI countries.

    Strategy: for each country, look up its primary Wikipedia project in
    docs/wiki_country_projects.json and fetch per-article monthly pageviews
    for that project. Aggregate to annual sums. Countries that share a
    project (e.g. all Anglophone countries -> en.wikipedia) will receive
    IDENTICAL values for the same year.

    Parameters
    ----------
    article : str
        Wikipedia article title (e.g. "Diarrhea", "Air pollution").
    year_range : tuple[int, int]
        Inclusive (start, end) years. Wikimedia pageview API coverage
        starts 2015-07; earlier years return empty.
    countries : list[str] | None
        Optional ISO3 filter. Default: all EPI countries present in the
        mapping file.

    Returns
    -------
    DataFrame with columns (iso, year, value).
    """
    mapping = _load_wiki_country_projects().get("countries", {})
    epi_isos = _get_epi_iso_set()
    start, end = year_range

    target_isos = set(countries) if countries else set(mapping.keys())
    if epi_isos:
        target_isos &= epi_isos

    # Batch by project: one API call per unique project serves all countries
    # that map to it.
    project_to_isos: dict[str, list[str]] = {}
    for iso in target_isos:
        entry = mapping.get(iso)
        if not entry:
            continue
        proj = entry.get("project")
        if not proj:
            continue
        project_to_isos.setdefault(proj, []).append(iso)

    records: list[dict] = []
    for project, isos in project_to_isos.items():
        by_year = _fetch_wiki_monthly(project, article, start, end)
        for year, views in by_year.items():
            for iso in isos:
                records.append({"iso": iso, "year": year, "value": float(views)})

    if not records:
        logger.warning("Wikipedia fetch returned 0 records for %r", article)
    return pd.DataFrame(records, columns=["iso", "year", "value"])


def fetch_and_store_wikipedia(
    conn,
    article: str,
    year_range: tuple[int, int] = (2016, 2024),
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch Wikipedia pageviews, store in DB, return the variable_id.

    Variable ID format: ``wiki:{article_slug}_local`` where article_slug is
    the lowercased underscore form of the article title. "_local" denotes
    that each country is queried against its primary local-language project
    (which may be shared for Anglophone/Hispanophone/etc. countries).
    """
    from epi_proxy.utils.db import (
        register_variable, upsert_observations, variable_exists, variable_coverage,
    )

    slug = article.strip().lower().replace(" ", "_").replace("/", "_")
    variable_id = f"wiki:{slug}_local"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info(
                "DB hit: %s already has %d observations, skipping fetch",
                variable_id, cov["n_observations"],
            )
            return variable_id

    df = fetch_wikipedia(article, year_range)

    # Build a coverage note that loudly flags the shared-language bias.
    mapping = _load_wiki_country_projects().get("countries", {})
    shared_isos = [iso for iso, entry in mapping.items() if entry.get("shared")]
    unique_isos = [iso for iso, entry in mapping.items() if not entry.get("shared")]
    coverage_note = (
        f"Per-article pageviews routed to each country's primary Wikipedia "
        f"edition. {len(unique_isos)} countries have unique-language editions "
        f"(country-specific signal). {len(shared_isos)} countries share a "
        f"major edition (en/es/fr/ar/pt/ru/zh) and receive identical values "
        f"per year — treat as a regional/linguistic attention signal, not a "
        f"country-specific one."
    )

    register_variable(
        conn,
        variable_id,
        name=f"Wikipedia pageviews: {article} (local-language edition)",
        description=coverage_note,
        source_type="wikipedia",
        source_org="Wikimedia Foundation",
        source_code=article,
        source_url=f"https://en.wikipedia.org/wiki/{_wiki_slug(article)}",
        source_granularity="article",
        aggregation_method="sum",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_WIKI_BASE}/per-article/{{project}}/all-access/user/{_wiki_slug(article)}/monthly/...",
    )
    return variable_id


# ---------------------------------------------------------------------------
# UN Comtrade (bilateral trade statistics)
# ---------------------------------------------------------------------------
#
# Product-level trade flows by Harmonized System (HS) code. Returns total
# imports or exports vs. world per reporter per year, aggregated across all
# partners and modes of transport. Useful for CONSUMPTION proxies — physical
# commodity flows reveal material throughput that official indicators often
# hide (fertilizer intensity, cement consumption, pharmaceutical trade).

_COMTRADE_BASE = "https://comtradeapi.un.org/data/v1/get"
_COMTRADE_HS_FILE = Path(__file__).parent / "comtrade_hs_catalog.json"
_COMTRADE_HS_CACHE: list[dict] | None = None


def _load_comtrade_hs_catalog() -> list[dict]:
    """Return the cached HS6 catalog as a list of {id, text, aggrlevel}."""
    global _COMTRADE_HS_CACHE
    if _COMTRADE_HS_CACHE is not None:
        return _COMTRADE_HS_CACHE
    try:
        payload = _json.loads(_COMTRADE_HS_FILE.read_text())
        _COMTRADE_HS_CACHE = payload.get("items", [])
    except Exception as exc:
        logger.warning("Could not load Comtrade HS catalog: %s", exc)
        _COMTRADE_HS_CACHE = []
    return _COMTRADE_HS_CACHE


def _comtrade_api_key() -> str:
    import os as _os
    key = _os.environ.get("COMTRADE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "COMTRADE_API_KEY not set in .env — sign up at "
            "https://comtradedeveloper.un.org/"
        )
    return key


def search_comtrade(query: str, max_results: int = 10) -> list[dict]:
    """Search the HS6 commodity catalog by keyword.

    Returns a list of ``{"id", "text", "aggrlevel"}`` dicts. Prefers 4-digit
    HS headings (category-level) over 6-digit subheadings so the agent gets
    broader matches first; the agent can drill down by passing a specific
    6-digit code to fetch_comtrade.
    """
    catalog = _load_comtrade_hs_catalog()
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if w]

    def score(item: dict) -> tuple:
        text = item.get("text", "").lower()
        if not any(w in text for w in query_words):
            return (-1, 0)
        hits = sum(1 for w in query_words if w in text)
        # Prefer 4-digit (aggrlevel=4) over 6-digit (aggrlevel=6) for readability
        level_pref = 0 if item.get("aggrlevel") == 4 else 1
        return (hits, -level_pref)

    scored = [(score(it), it) for it in catalog]
    matches = [it for (s, it) in scored if s[0] > 0]
    matches.sort(key=lambda it: score(it), reverse=True)
    return matches[:max_results]


def preview_comtrade(
    hs_code: str, flow: str = "M", year: int = 2022,
) -> dict:
    """Fetch one year of a commodity for coverage preview.

    Returns ``{"hs_code", "flow", "year", "n_countries", "sample"}``.
    """
    df = fetch_comtrade(hs_code, flow=flow, year_range=(year, year))
    sample = df.head(5).to_dict("records") if not df.empty else []
    return {
        "hs_code": hs_code,
        "flow": flow,
        "year": year,
        "n_countries": int(df["iso"].nunique()) if not df.empty else 0,
        "n_observations": len(df),
        "sample": sample,
    }


def _fetch_comtrade_one_year(
    hs_code: str, flow: str, year: int, reporter_m49s: list[int],
    max_attempts: int = 3,
) -> list[dict]:
    """Fetch one year of Comtrade data for a batch of reporters.

    Retries once on 429 (rate limit) with exponential backoff before giving
    up. Returns the raw JSON data list. Caller is responsible for iso3
    mapping and row-level normalization.
    """
    import time
    key = _comtrade_api_key()
    url = f"{_COMTRADE_BASE}/C/A/HS"
    params = {
        "reporterCode": ",".join(str(m) for m in reporter_m49s),
        "partnerCode": "0",       # World
        "partner2Code": "0",      # aggregate across origin countries
        "cmdCode": hs_code,
        "flowCode": flow,
        "period": str(year),
        "motCode": "0",           # all modes of transport
        "customsCode": "C00",     # all customs procedures
        "maxRecords": "500",
    }
    backoff = 2.0
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(
                url, params=params,
                headers={"Ocp-Apim-Subscription-Key": key},
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429 and attempt < max_attempts:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else backoff
                logger.info(
                    "Comtrade 429 rate-limit on HS %s %d (attempt %d/%d), "
                    "sleeping %.1fs", hs_code, year, attempt, max_attempts, wait,
                )
                time.sleep(wait)
                backoff *= 2
                continue
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                "Comtrade fetch failed for HS %s %s %d: %s",
                hs_code, flow, year, exc,
            )
            return []
        if payload.get("error"):
            logger.warning(
                "Comtrade error for HS %s %s %d: %s",
                hs_code, flow, year, payload.get("error"),
            )
            return []
        return payload.get("data") or []
    return []


def fetch_comtrade(
    hs_code: str,
    flow: str = "M",
    year_range: tuple[int, int] = (2010, 2023),
    unit: str = "usd",
) -> pd.DataFrame:
    """Fetch Comtrade trade flows for all EPI countries.

    One API call per year (all reporters in a single request). Returns a
    DataFrame with columns (iso, year, value).

    Parameters
    ----------
    hs_code : str
        Harmonized System code (4 or 6 digit). E.g. ``"3102"`` for
        nitrogenous fertilizers, ``"2523"`` for cement, ``"3004"`` for
        packaged medicaments.
    flow : {"M", "X"}
        ``"M"`` = imports, ``"X"`` = exports.
    year_range : tuple[int, int]
        Inclusive year range (HS6 starts 2017; HS4/HS2 goes earlier).
    unit : {"usd", "qty"}
        Which column to use. ``"usd"`` (default) uses primaryValue — most
        reliably populated across countries. ``"qty"`` uses physical
        quantity (kg from netWgt or qty); rows where qty is missing or
        zero are DROPPED rather than falling back to USD. Mixing units
        across rows would make cross-country comparison meaningless.
    """
    from epi_proxy.utils.country_codes import iso3_to_m49, m49_to_iso3

    if unit not in ("usd", "qty"):
        raise ValueError(f"unit must be 'usd' or 'qty', got {unit!r}")

    epi_isos = _get_epi_iso_set()
    if not epi_isos:
        logger.warning("No EPI ISO set available — Comtrade fetch aborted")
        return pd.DataFrame(columns=["iso", "year", "value"])

    reporter_m49s: list[int] = []
    for iso in sorted(epi_isos):
        m = iso3_to_m49(iso)
        if m:
            reporter_m49s.append(m)

    records: list[dict] = []
    for year in range(year_range[0], year_range[1] + 1):
        rows = _fetch_comtrade_one_year(hs_code, flow, year, reporter_m49s)
        for row in rows:
            m49 = row.get("reporterCode")
            if m49 is None:
                continue
            try:
                iso = m49_to_iso3(int(m49))
            except (ValueError, TypeError):
                iso = None
            if not iso or (epi_isos and iso not in epi_isos):
                continue
            value: float | None = None
            if unit == "usd":
                usd = row.get("primaryValue")
                if usd is not None and usd > 0:
                    value = float(usd)
            else:  # qty
                qty = row.get("qty")
                net_wgt = row.get("netWgt")
                if qty is not None and qty > 0:
                    value = float(qty)
                elif net_wgt is not None and net_wgt > 0:
                    value = float(net_wgt)
            if value is None:
                continue
            records.append({"iso": iso, "year": year, "value": value})

    if not records:
        logger.warning(
            "Comtrade returned 0 valid records for HS %s %s %d-%d (unit=%s)",
            hs_code, flow, year_range[0], year_range[1], unit,
        )
        return pd.DataFrame(columns=["iso", "year", "value"])

    df = pd.DataFrame(records, columns=["iso", "year", "value"])
    df = df.groupby(["iso", "year"], as_index=False)["value"].sum()
    df.attrs["unit"] = unit
    return df


def fetch_and_store_comtrade(
    conn,
    hs_code: str,
    flow: str = "M",
    year_range: tuple[int, int] = (2010, 2023),
    unit: str = "usd",
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch Comtrade data, store in DB, return the variable_id.

    Variable ID format: ``comtrade:HS{code}_{flow}_{unit}``. USD is the
    default because it's reliably populated across reporters; physical
    kg is available for many rows but not all, and mixing units would
    corrupt cross-country comparisons.
    """
    from epi_proxy.utils.db import (
        register_variable, upsert_observations, variable_exists, variable_coverage,
    )

    flow = flow.upper()
    unit = unit.lower()
    variable_id = f"comtrade:HS{hs_code}_{flow}_{unit}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info(
                "DB hit: %s already has %d observations, skipping fetch",
                variable_id, cov["n_observations"],
            )
            return variable_id

    df = fetch_comtrade(hs_code, flow, year_range, unit=unit)

    # Look up display text from cached catalog
    text = hs_code
    for it in _load_comtrade_hs_catalog():
        if it.get("id") == hs_code:
            text = it.get("text", hs_code)
            break
    flow_label = "imports" if flow == "M" else "exports"
    name = f"Comtrade HS {hs_code} {flow_label}: {text}"

    register_variable(
        conn,
        variable_id,
        name=name,
        description=(
            f"UN Comtrade annual {flow_label} from world, aggregated across "
            f"partners. Unit: {'kilograms' if unit == 'qty' else 'USD'}."
        ),
        source_type="comtrade",
        source_org="UN Comtrade",
        source_code=f"HS{hs_code}/{flow}",
        source_url="https://comtradeplus.un.org/",
        units="kg" if unit == "qty" else "USD",
        source_granularity="trade_flow",
        aggregation_method="sum",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_COMTRADE_BASE}/C/A/HS?cmdCode={hs_code}&flowCode={flow}",
    )
    return variable_id


# ---------------------------------------------------------------------------
# OpenAQ (air quality sensor network)
# ---------------------------------------------------------------------------
#
# OpenAQ v3 aggregates crowdsourced + institutional air quality monitors.
# Station coverage is severely biased toward rich countries (USA has
# thousands; many LDCs have 0-3). For country-year values we:
#   1. List all locations in a country that carry the target parameter
#   2. For each location, collect sensor IDs for that parameter
#   3. Pull per-sensor annual aggregates via /sensors/{id}/years
#   4. Unweighted mean across sensors -> country annual value
#   5. Drop country-years with < MIN_STATIONS sensors (noisy)

_OPENAQ_BASE = "https://api.openaq.org/v3"
_OPENAQ_MIN_STATIONS = 3
_OPENAQ_COUNTRIES_CACHE: dict | None = None
_OPENAQ_PARAMS_CACHE: list[dict] | None = None


def _openaq_api_key() -> str:
    import os as _os
    key = _os.environ.get("OPENAQ_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OPENAQ_API_KEY not set in .env — register at https://explore.openaq.org/"
        )
    return key


def _openaq_get(path: str, params: dict | None = None, max_attempts: int = 4) -> dict:
    """GET with retry-on-429 (exponential backoff)."""
    import time
    url = f"{_OPENAQ_BASE}{path}"
    headers = {"X-API-Key": _openaq_api_key()}
    backoff = 3.0
    for attempt in range(1, max_attempts + 1):
        resp = requests.get(
            url, params=params or {}, headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code == 429 and attempt < max_attempts:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            logger.info(
                "OpenAQ 429 on %s (attempt %d/%d), sleeping %.1fs",
                path, attempt, max_attempts, wait,
            )
            time.sleep(wait)
            backoff *= 2
            continue
        resp.raise_for_status()
        return resp.json()
    return {}


def _openaq_load_countries() -> dict:
    """Return cached OpenAQ country index: {iso2: {id, name, iso3}}."""
    global _OPENAQ_COUNTRIES_CACHE
    if _OPENAQ_COUNTRIES_CACHE is not None:
        return _OPENAQ_COUNTRIES_CACHE

    from epi_proxy.utils.country_codes import iso3_to_iso2

    try:
        payload = _openaq_get("/countries", {"limit": 200})
    except Exception as exc:
        logger.warning("OpenAQ countries fetch failed: %s", exc)
        _OPENAQ_COUNTRIES_CACHE = {}
        return _OPENAQ_COUNTRIES_CACHE

    # Build iso2 -> iso3 reverse map from pycountry-backed country_codes
    epi_isos = _get_epi_iso_set()
    iso2_to_iso3 = {}
    for iso3 in epi_isos:
        iso2 = iso3_to_iso2(iso3)
        if iso2:
            iso2_to_iso3[iso2] = iso3

    index: dict = {}
    for c in payload.get("results", []):
        iso2 = c.get("code")
        if not iso2 or iso2 == "-99":
            continue
        iso3 = iso2_to_iso3.get(iso2)
        if not iso3:
            continue  # not an EPI country
        index[iso2] = {
            "id": c.get("id"),
            "name": c.get("name"),
            "iso3": iso3,
        }
    _OPENAQ_COUNTRIES_CACHE = index
    return _OPENAQ_COUNTRIES_CACHE


def _openaq_load_parameters() -> list[dict]:
    global _OPENAQ_PARAMS_CACHE
    if _OPENAQ_PARAMS_CACHE is not None:
        return _OPENAQ_PARAMS_CACHE
    try:
        payload = _openaq_get("/parameters", {"limit": 100})
        _OPENAQ_PARAMS_CACHE = payload.get("results", [])
    except Exception as exc:
        logger.warning("OpenAQ parameters fetch failed: %s", exc)
        _OPENAQ_PARAMS_CACHE = []
    return _OPENAQ_PARAMS_CACHE


def _openaq_resolve_parameter(name: str) -> tuple[int | None, dict | None]:
    """Resolve a parameter name like 'pm25' to (id, metadata).

    Prefers the canonical mass-concentration entry (e.g. pm25 with µg/m³
    units, id=2) over variants like 'pm25-old' (id=97) or 'pm25' ppm (id=19860).
    """
    params = _openaq_load_parameters()
    name_lower = name.lower().strip()
    # Exact name match, preferring canonical µg/m³ units and low id
    matches = [p for p in params if p.get("name", "").lower() == name_lower]
    if not matches:
        return None, None
    # Prefer canonical unit µg/m³, then lowest id (oldest = canonical)
    def score(p: dict) -> tuple:
        unit = (p.get("units") or "").strip()
        is_canonical = unit in ("µg/m³", "ug/m3", "\u00b5g/m\u00b3")
        return (0 if is_canonical else 1, p.get("id", 9999))
    matches.sort(key=score)
    return matches[0].get("id"), matches[0]


def search_openaq(query: str, max_results: int = 10) -> list[dict]:
    """Search the OpenAQ parameter catalog by keyword.

    Returns ``{"name", "id", "units", "description"}`` dicts. Unlike other
    search tools, OpenAQ's parameter list is small (~46 entries), so this
    returns everything matching.
    """
    params = _openaq_load_parameters()
    q = query.lower().strip()
    matches: list[dict] = []
    for p in params:
        text = f"{p.get('name','')} {p.get('displayName','') or ''} {p.get('description','') or ''}".lower()
        if q in text:
            matches.append({
                "name": p.get("name"),
                "id": p.get("id"),
                "units": p.get("units"),
                "description": p.get("description") or p.get("displayName"),
            })
            if len(matches) >= max_results:
                break
    return matches


def preview_openaq(parameter: str) -> dict:
    """Check coverage for a parameter across a handful of sample countries.

    Returns ``{"parameter", "n_sample_countries_with_data", "sample"}``.
    """
    pid, _ = _openaq_resolve_parameter(parameter)
    if not pid:
        return {"parameter": parameter, "error": f"unknown parameter: {parameter}"}

    country_index = _openaq_load_countries()
    sample_iso2s = ["US", "DE", "IN", "BR", "ZA", "JP"]
    results = []
    for iso2 in sample_iso2s:
        entry = country_index.get(iso2)
        if not entry:
            continue
        try:
            payload = _openaq_get(
                "/locations",
                {"countries_id": entry["id"], "parameters_id": pid, "limit": 100},
            )
        except Exception as exc:
            logger.debug("OpenAQ preview failed for %s: %s", iso2, exc)
            continue
        n_locs = payload.get("meta", {}).get("found", 0)
        # meta.found can be ">N" string — coerce to int fallback
        if isinstance(n_locs, str):
            n_locs = int(n_locs.lstrip(">")) if n_locs.lstrip(">").isdigit() else len(payload.get("results", []))
        results.append({"iso2": iso2, "iso3": entry["iso3"], "n_locations": n_locs})

    return {
        "parameter": parameter,
        "parameter_id": pid,
        "sample": results,
    }


def _openaq_sensor_ids_for_country(
    country_id: int, parameter_id: int, max_sensors: int = 30,
) -> list[int]:
    """List up to ``max_sensors`` sensor IDs in a country for a parameter.

    The first N returned by the /locations endpoint; no selection beyond
    API-return order. 30 is enough to compute a stable country mean (well
    above MIN_STATIONS=3) while keeping total API calls per fetch below the
    2000/day free-tier quota. Larger values improve precision but may
    exhaust the quota when fetching all EPI countries.
    """
    limit = min(max(max_sensors, 1), 100)
    try:
        payload = _openaq_get(
            "/locations",
            {
                "countries_id": country_id,
                "parameters_id": parameter_id,
                "limit": limit,
            },
        )
    except Exception as exc:
        logger.debug(
            "OpenAQ locations fetch failed for country %s param %s: %s",
            country_id, parameter_id, exc,
        )
        return []
    sensor_ids: list[int] = []
    for loc in payload.get("results", []):
        for sensor in loc.get("sensors", []):
            if sensor.get("parameter", {}).get("id") == parameter_id:
                sid = sensor.get("id")
                if sid:
                    sensor_ids.append(sid)
            if len(sensor_ids) >= max_sensors:
                break
        if len(sensor_ids) >= max_sensors:
            break
    return sensor_ids


def _openaq_sensor_yearly(sensor_id: int) -> list[tuple[int, float, float]]:
    """Fetch annual aggregates for one sensor.

    Returns list of ``(year, mean, coverage_pct)`` tuples. Drops years where
    coverage is below 50% (not enough hourly observations).

    OpenAQ v3 reports periods in local time via the ``local`` subfield on
    ``datetimeFrom``; the ``utc`` subfield shows the UTC-equivalent timestamp
    (e.g. "2015-12-31T17:00Z" for 2016-01-01 local in +7). We parse the
    local year to avoid timezone boundary bugs.
    """
    try:
        payload = _openaq_get(f"/sensors/{sensor_id}/years", {"limit": 50})
    except Exception as exc:
        logger.debug("OpenAQ sensor %s years fetch failed: %s", sensor_id, exc)
        return []
    out: list[tuple[int, float, float]] = []
    for row in payload.get("results", []):
        period = row.get("period", {})
        dt_from_local = period.get("datetimeFrom", {}).get("local", "")
        val = row.get("value")
        if not dt_from_local or val is None:
            continue
        try:
            year = int(dt_from_local[:4])
        except (ValueError, TypeError):
            continue
        coverage = row.get("coverage", {})
        pct = coverage.get("percentComplete", 100.0)
        try:
            pct = float(pct)
        except (ValueError, TypeError):
            pct = 0.0
        if pct < 50:
            continue
        try:
            out.append((year, float(val), pct))
        except (ValueError, TypeError):
            continue
    return out


def fetch_openaq(
    parameter: str = "pm25",
    year_range: tuple[int, int] = (2016, 2024),
    countries: list[str] | None = None,
    max_sensors_per_country: int = 30,
) -> pd.DataFrame:
    """Fetch OpenAQ annual country-means for a parameter.

    ⚠ Expensive: 1 request for locations + 1 request per sensor per country.
    At 30 sensors/country × 143 EPI countries = ~4300 requests — over the
    2000/day free-tier quota. First-time full fetches take multiple days.
    After data is cached in the DB, subsequent calls return instantly.

    Parameters
    ----------
    parameter : str
        Parameter name, e.g. ``"pm25"``, ``"no2"``, ``"o3"``, ``"so2"``,
        ``"pm10"``, ``"co"``.
    year_range : tuple[int, int]
        Inclusive year range.
    countries : list[str] | None
        Optional ISO3 filter. Defaults to all EPI countries with OpenAQ
        presence.
    max_sensors_per_country : int
        Cap on number of sensors sampled per country. Lower values reduce
        API quota use at the cost of country-mean precision.
    """
    pid, _ = _openaq_resolve_parameter(parameter)
    if not pid:
        logger.warning("OpenAQ unknown parameter: %s", parameter)
        return pd.DataFrame(columns=["iso", "year", "value"])

    country_index = _openaq_load_countries()
    target = set(countries) if countries else None

    # Accumulator: {(iso3, year): [values]}
    accum: dict[tuple[str, int], list[float]] = {}

    for iso2, entry in country_index.items():
        iso3 = entry["iso3"]
        if target and iso3 not in target:
            continue
        sensor_ids = _openaq_sensor_ids_for_country(
            entry["id"], pid, max_sensors=max_sensors_per_country,
        )
        if not sensor_ids:
            continue
        for sid in sensor_ids:
            yearly = _openaq_sensor_yearly(sid)
            for year, val, _pct in yearly:
                if year_range[0] <= year <= year_range[1]:
                    accum.setdefault((iso3, year), []).append(val)

    records: list[dict] = []
    for (iso, year), vals in accum.items():
        if len(vals) < _OPENAQ_MIN_STATIONS:
            continue
        records.append({
            "iso": iso, "year": year,
            "value": sum(vals) / len(vals),
        })

    if not records:
        logger.warning("OpenAQ returned 0 valid records for %s", parameter)
    return pd.DataFrame(records, columns=["iso", "year", "value"])


def fetch_and_store_openaq(
    conn,
    parameter: str = "pm25",
    year_range: tuple[int, int] = (2016, 2024),
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch OpenAQ data, store in DB, return the variable_id.

    Variable ID format: ``openaq:{parameter}_mean``.
    """
    from epi_proxy.utils.db import (
        register_variable, upsert_observations, variable_exists, variable_coverage,
    )

    pname = parameter.lower().strip()
    variable_id = f"openaq:{pname}_mean"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info(
                "DB hit: %s already has %d observations, skipping fetch",
                variable_id, cov["n_observations"],
            )
            return variable_id

    df = fetch_openaq(pname, year_range=year_range)
    pid, pmeta = _openaq_resolve_parameter(pname)
    units = (pmeta or {}).get("units", "")
    display = (pmeta or {}).get("displayName") or pname.upper()

    register_variable(
        conn,
        variable_id,
        name=f"OpenAQ {display} annual country mean",
        description=(
            f"Unweighted mean across ground monitoring stations per country-year. "
            f"Minimum {_OPENAQ_MIN_STATIONS} stations required per country-year; "
            f"country-years below this threshold are dropped. Severe coverage "
            f"bias: rich countries have 100+ stations, many LDCs have 0-3."
        ),
        source_type="openaq",
        source_org="OpenAQ",
        source_code=f"parameter_id={pid}",
        source_url="https://explore.openaq.org/",
        units=units,
        source_granularity="station",
        aggregation_method="mean",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"{_OPENAQ_BASE}/locations?parameters_id={pid}",
    )
    return variable_id


# ---------------------------------------------------------------------------
# Google Earth Engine (satellite-derived)
# ---------------------------------------------------------------------------
#
# Agent-accessible wrapper with four safety constraints (design from the
# 2026-04-13 plan) that together guarantee the 4-minute sync budget:
#   1. Temporal collapse BEFORE spatial reduction — always call
#      .filterDate(y, y+1).mean() or .sum() before reduceRegions.
#   2. Scale floor of 10 km — reduceRegions scale is always 10000.
#   3. Annual output granularity only.
#   4. Hard 4-minute timeout on getInfo() — raises a clean error on overrun
#      so the agent can try a different asset.

_GEE_BASE_URL = "https://storage.googleapis.com/earthengine-stac/catalog"
# Plan Section 1.4 called for 10 km as the scale floor. Empirically that
# times out on Sentinel-5P globally (280s+ / 4-min budget). Reducing to
# 25 km still times out. At 50 km, S5P NO2 for 175 countries completes in
# ~60s (verified 2026-04-13), MODIS NDVI in ~30s. Country means at 50 km
# are indistinguishable from finer scales once spatially aggregated.
# Tradeoff: tiny countries (Luxembourg, Malta) get ~4 pixels — noisy but
# still meaningful at the country-year scale we care about.
_GEE_SCALE_METERS = 50000
_GEE_GETINFO_TIMEOUT_SEC = 240   # 4 minutes
_GEE_INITIALIZED = False
_GEE_COUNTRY_FC_CACHE = None

# LSIB_SIMPLE name -> ISO3 overrides for features that pycountry can't match.
# Limited to EPI countries; dependencies and disputed territories are
# intentionally omitted so they don't contaminate aggregates.
_LSIB_NAME_TO_ISO3: dict[str, str] = {
    "Antigua & Barbuda": "ATG",
    "Bahamas, The": "BHS",
    "Bosnia & Herzegovina": "BIH",
    "Brunei": "BRN",
    "Burma": "MMR",
    "Central African Rep": "CAF",
    "Cote d'Ivoire": "CIV",
    "Dem Rep of the Congo": "COD",
    "Rep of the Congo": "COG",
    "Fed States of Micronesia": "FSM",
    "Gambia, The": "GMB",
    "Korea, North": "PRK",
    "Korea, South": "KOR",
    "Kosovo": "XKX",
    "Macedonia": "MKD",
    "Marshall Is": "MHL",
    "Russia": "RUS",
    "Sao Tome & Principe": "STP",
    "Solomon Is": "SLB",
    "Swaziland": "SWZ",
    "Trinidad & Tobago": "TTO",
    "Turkey": "TUR",
    "St Kitts & Nevis": "KNA",
    "St Vincent & the Grenadines": "VCT",
    "United States (Alaska)": "USA",
    "United States (Hawaii)": "USA",
    "Spain (Africa)": "ESP",
    "Spain (Canary Is)": "ESP",
    "Portugal (Azores)": "PRT",
    "Portugal (Madeira Is)": "PRT",
    "Vatican City": "VAT",
    "West Bank": "PSE",
    "Gaza Strip": "PSE",
    "Cabo Verde": "CPV",
    "Cook Is": "COK",
    "Curacao": "CUW",
    "Timor-Leste": "TLS",
}


def _init_gee():
    """Initialize the EE client once per process."""
    global _GEE_INITIALIZED
    if _GEE_INITIALIZED:
        return
    import os as _os
    project = _os.environ.get("GEE_PROJECT", "")
    if not project:
        raise RuntimeError("GEE_PROJECT not set in .env")
    import ee  # noqa
    try:
        ee.Initialize(project=project)
    except Exception as exc:
        # Idempotent re-init: some ee versions raise if already initialized
        logger.debug("GEE Initialize raised (may already be init'd): %s", exc)
    _GEE_INITIALIZED = True


def _gee_country_feature_collection():
    """Return a cached EE FeatureCollection of EPI countries tagged with iso3.

    Each feature has an added ``iso3`` string property. Multiple features may
    map to the same ISO3 (e.g. USA split into mainland/Alaska/Hawaii); we
    aggregate client-side after reduceRegions.
    """
    global _GEE_COUNTRY_FC_CACHE
    if _GEE_COUNTRY_FC_CACHE is not None:
        return _GEE_COUNTRY_FC_CACHE
    _init_gee()
    import ee
    import pycountry  # type: ignore

    src_fc = ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
    info = src_fc.getInfo()
    epi_isos = _get_epi_iso_set()

    # Walk feature properties to build a list of (index_in_collection, iso3).
    tagged: list[tuple[int, str]] = []
    for idx, feat in enumerate(info.get("features", [])):
        name = feat.get("properties", {}).get("country_na", "")
        if not name:
            continue
        iso3 = _LSIB_NAME_TO_ISO3.get(name)
        if not iso3:
            try:
                iso3 = pycountry.countries.lookup(name).alpha_3
            except LookupError:
                continue
        if epi_isos and iso3 not in epi_isos:
            continue
        tagged.append((idx, iso3))

    # Rebuild FeatureCollection server-side using indices + iso3 tags.
    indices = ee.List([t[0] for t in tagged])
    isos = ee.List([t[1] for t in tagged])
    src_list = src_fc.toList(src_fc.size())

    def attach_iso(i):
        i = ee.Number(i)
        feat = ee.Feature(src_list.get(indices.get(i)))
        return feat.set("iso3", isos.get(i))

    tagged_fc = ee.FeatureCollection(
        ee.List.sequence(0, len(tagged) - 1).map(attach_iso)
    )
    _GEE_COUNTRY_FC_CACHE = tagged_fc
    return _GEE_COUNTRY_FC_CACHE


def _gee_with_timeout(ee_computation, timeout_sec: int = _GEE_GETINFO_TIMEOUT_SEC):
    """Run ``ee_computation.getInfo()`` in a background thread with a hard timeout.

    Raises ``TimeoutError`` if the computation exceeds ``timeout_sec``. The
    background thread is orphaned rather than killed — GEE will eventually
    drop the query.
    """
    import threading
    result: dict = {}
    def _run():
        try:
            result["value"] = ee_computation.getInfo()
        except Exception as exc:  # pragma: no cover
            result["error"] = exc
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        raise TimeoutError(
            f"GEE getInfo() exceeded {timeout_sec}s — the dataset is too "
            "expensive at this scale. Try a coarser band, a shorter year "
            "range, or a different asset."
        )
    if "error" in result:
        raise result["error"]
    return result.get("value")


_GEE_REDUCER_HINTS = {
    # Bands whose annual aggregate is a sum (flux, count, area)
    "sum": {"precipitation", "burndate", "pr", "burned", "gpp", "npp", "fire_mask"},
    # Bands aggregated by mode (categorical class labels)
    "mode": {"lc_type1", "land_cover", "landcover"},
}


def _gee_pick_reducer(band: str) -> str:
    """Heuristic reducer choice: mean unless the band name hints otherwise."""
    b = band.lower()
    for r, hints in _GEE_REDUCER_HINTS.items():
        for h in hints:
            if h in b:
                return r
    return "mean"


def search_gee(query: str, max_results: int = 10) -> list[dict]:
    """Search the live Earth Engine STAC catalog for image collections.

    Walks the STAC catalog JSON at fetch time (no local index). Applies
    eligibility filters: image_collection type, global coverage (lon span
    > 300, lat span > 100), temporal span >= 10 years, end year >= 2018,
    and keyword match on title/description.

    Returns ``[{"asset_id", "title", "bands", "years", "license"}]``.
    """
    # Fetch root STAC catalog
    try:
        root = requests.get(
            f"{_GEE_BASE_URL}/catalog.json",
            timeout=_REQUEST_TIMEOUT,
        ).json()
    except Exception as exc:
        logger.warning("GEE STAC root fetch failed: %s", exc)
        return []

    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if w]
    results: list[dict] = []

    # The root lists child providers (e.g. MODIS, Sentinel, NASA/...)
    for link in root.get("links", []):
        if link.get("rel") != "child":
            continue
        if len(results) >= max_results:
            break
        provider_url = link.get("href", "")
        if not provider_url.startswith("http"):
            provider_url = f"{_GEE_BASE_URL}/{provider_url}"
        try:
            prov = requests.get(provider_url, timeout=_REQUEST_TIMEOUT).json()
        except Exception:
            continue
        for child in prov.get("links", []):
            if child.get("rel") != "child" or len(results) >= max_results:
                continue
            child_url = child.get("href", "")
            if not child_url.startswith("http"):
                child_url = f"{provider_url.rsplit('/', 1)[0]}/{child_url}"
            try:
                asset = requests.get(child_url, timeout=_REQUEST_TIMEOUT).json()
            except Exception:
                continue
            if asset.get("gee:type") != "image_collection":
                continue
            title = (asset.get("title") or "").strip()
            desc = (asset.get("description") or "").strip()
            text = f"{title} {desc}".lower()
            if query_words and not any(w in text for w in query_words):
                continue
            # Temporal filter
            extent = asset.get("extent", {}).get("temporal", {}).get("interval", [[None]])
            start_s = extent[0][0] if extent and extent[0] else None
            end_s = extent[0][1] if extent and len(extent[0]) > 1 else None
            start_year = int(start_s[:4]) if start_s else None
            end_year = int(end_s[:4]) if end_s else 2026
            if start_year and end_year - start_year < 10:
                continue
            if end_year < 2018:
                continue
            # Spatial filter (global)
            sp = asset.get("extent", {}).get("spatial", {}).get("bbox", [[None]])
            if sp and sp[0] and len(sp[0]) >= 4:
                lon_span = abs(sp[0][2] - sp[0][0])
                lat_span = abs(sp[0][3] - sp[0][1])
                if lon_span < 300 or lat_span < 100:
                    continue
            bands = [b.get("name") for b in asset.get("summaries", {}).get("eo:bands", [])]
            results.append({
                "asset_id": asset.get("id"),
                "title": title,
                "bands": bands[:10],
                "years": [start_year, end_year],
                "license": asset.get("license", "unknown"),
            })
    return results


def preview_gee(asset_id: str, band: str) -> dict:
    """Thin preview: return asset metadata without running a reduction."""
    try:
        _init_gee()
        import ee
        ic = ee.ImageCollection(asset_id)
        size = ic.limit(1).size().getInfo()
    except Exception as exc:
        return {"asset_id": asset_id, "band": band, "error": str(exc)[:300]}
    return {
        "asset_id": asset_id,
        "band": band,
        "has_images": size > 0,
        "reducer_hint": _gee_pick_reducer(band),
    }


def fetch_gee(
    asset_id: str,
    band: str,
    reducer: str | None = None,
    year_range: tuple[int, int] = (2015, 2024),
) -> pd.DataFrame:
    """Fetch annual per-country reductions of one band from a GEE collection.

    Enforces the four safety constraints: temporal collapse before spatial
    reduction, 10 km scale floor, annual output, 4-minute timeout per
    getInfo call.

    Parameters
    ----------
    asset_id : str
        GEE ImageCollection asset ID, e.g. ``"MODIS/061/MOD13A3"``.
    band : str
        Band name to reduce, e.g. ``"NDVI"``.
    reducer : {"mean", "sum", "count", "mode"} or None
        Spatial+temporal reducer. Auto-picked from band name if None:
        sum for flux/count bands, mode for categorical, mean otherwise.
    year_range : tuple[int, int]
        Inclusive year range.
    """
    _init_gee()
    import ee

    countries_fc = _gee_country_feature_collection()
    if reducer is None:
        reducer = _gee_pick_reducer(band)
    ee_reducer = {
        "mean": ee.Reducer.mean(),
        "sum": ee.Reducer.sum(),
        "count": ee.Reducer.count(),
        "mode": ee.Reducer.mode(),
    }.get(reducer, ee.Reducer.mean())

    records: list[dict] = []
    start, end = year_range
    for year in range(start, end + 1):
        y_start = f"{year}-01-01"
        y_end = f"{year + 1}-01-01"
        ic = (
            ee.ImageCollection(asset_id)
            .filterDate(y_start, y_end)
            .select(band)
        )
        # TEMPORAL COLLAPSE BEFORE SPATIAL REDUCTION — sum for flux bands
        # (precipitation, burned area), mean for continuous (NDVI, temp).
        if reducer == "sum":
            img = ic.sum()
        else:
            img = ic.mean()

        reduced = img.reduceRegions(
            collection=countries_fc,
            reducer=ee_reducer,
            scale=_GEE_SCALE_METERS,
        ).select(propertySelectors=["iso3", reducer], retainGeometry=False)

        try:
            info = _gee_with_timeout(reduced)
        except TimeoutError as exc:
            logger.warning(
                "GEE timeout for %s/%s year %d: %s", asset_id, band, year, exc,
            )
            continue
        except Exception as exc:
            logger.warning(
                "GEE fetch failed for %s/%s year %d: %s",
                asset_id, band, year, exc,
            )
            continue

        # Aggregate by iso3 (multiple features may map to same country)
        by_iso: dict[str, list[float]] = {}
        for feat in (info or {}).get("features", []):
            props = feat.get("properties") or {}
            iso3 = props.get("iso3")
            val = props.get(reducer)
            if iso3 and val is not None:
                try:
                    by_iso.setdefault(iso3, []).append(float(val))
                except (ValueError, TypeError):
                    continue
        for iso, vals in by_iso.items():
            agg = sum(vals) / len(vals) if reducer == "mean" else sum(vals)
            records.append({"iso": iso, "year": year, "value": agg})

    if not records:
        logger.warning(
            "GEE fetch returned 0 records for %s/%s (%d-%d)",
            asset_id, band, start, end,
        )
    return pd.DataFrame(records, columns=["iso", "year", "value"])


def fetch_and_store_gee(
    conn,
    asset_id: str,
    band: str,
    reducer: str | None = None,
    year_range: tuple[int, int] = (2015, 2024),
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch GEE data, store in DB, return the variable_id.

    Variable ID format: ``gee:{asset_slug}_{band}_{reducer}`` where
    asset_slug is the asset ID lowercased with slashes -> underscores.
    """
    from epi_proxy.utils.db import (
        register_variable, upsert_observations, variable_exists, variable_coverage,
    )

    if reducer is None:
        reducer = _gee_pick_reducer(band)
    asset_slug = asset_id.lower().replace("/", "_")
    variable_id = f"gee:{asset_slug}_{band.lower()}_{reducer}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info(
                "DB hit: %s already has %d observations, skipping fetch",
                variable_id, cov["n_observations"],
            )
            return variable_id

    df = fetch_gee(asset_id, band, reducer=reducer, year_range=year_range)

    register_variable(
        conn,
        variable_id,
        name=f"{asset_id} ({band}) country-{reducer}",
        description=(
            f"Per-country annual {reducer} of band {band} from {asset_id}. "
            f"Temporal collapse applied before spatial reduction at "
            f"{_GEE_SCALE_METERS} m scale."
        ),
        source_type="gee",
        source_org="Google Earth Engine",
        source_code=f"{asset_id}:{band}",
        source_url=f"https://developers.google.com/earth-engine/datasets/catalog/{asset_id.replace('/', '_')}",
        source_granularity="pixel",
        aggregation_method=reducer,
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url=f"ee.ImageCollection({asset_id}).select({band})",
    )
    return variable_id


# ---------------------------------------------------------------------------
# GDELT Global Knowledge Graph (BigQuery)
# ---------------------------------------------------------------------------
#
# Queries the public ``gdelt-bq.gdeltv2.gkg_partitioned`` table to aggregate
# theme mentions per country per year. The V2Locations column is parsed
# via UNNEST+SPLIT to extract FIPS 10-4 country codes, which are then
# mapped to ISO3 for alignment with EPI data.
#
# Cost note: one theme query over 1 year ≈ 475 GB scanned (~0.5 TB). The
# first 1 TB/month is free. Multi-year / multi-theme backfills can quickly
# consume the free tier — the DB cache is critical. Default year range is
# kept narrow (2020-2024, 5 years ≈ 2.4 TB) to allow a single backfill
# within one month of free-tier quota; users can widen per-query.

# FIPS 10-4 country code -> ISO3. Only populated for the cases where FIPS
# differs from ISO2; pass-through (FIPS == ISO2 == iso3 short code) falls
# through to pycountry.
_FIPS_TO_ISO3: dict[str, str] = {
    "AC": "ATG", "AF": "AFG", "AG": "DZA", "AJ": "AZE", "AL": "ALB",
    "AM": "ARM", "AN": "AND", "AO": "AGO", "AR": "ARG", "AS": "AUS",
    "AU": "AUT", "BA": "BHR", "BC": "BWA", "BD": "BMU", "BE": "BEL",
    "BF": "BHS", "BG": "BGD", "BH": "BLZ", "BK": "BIH", "BL": "BOL",
    "BM": "MMR", "BN": "BEN", "BO": "BLR", "BP": "SLB", "BR": "BRA",
    "BT": "BTN", "BU": "BGR", "BX": "BRN", "BY": "BDI", "CA": "CAN",
    "CB": "KHM", "CD": "TCD", "CE": "LKA", "CF": "COG", "CG": "COD",
    "CH": "CHN", "CI": "CHL", "CJ": "CYM", "CM": "CMR", "CN": "COM",
    "CO": "COL", "CS": "CRI", "CT": "CAF", "CU": "CUB", "CV": "CPV",
    "CW": "COK", "CY": "CYP", "DA": "DNK", "DJ": "DJI", "DO": "DMA",
    "DR": "DOM", "EC": "ECU", "EG": "EGY", "EI": "IRL", "EK": "GNQ",
    "EN": "EST", "ER": "ERI", "ES": "SLV", "ET": "ETH", "EZ": "CZE",
    "FI": "FIN", "FJ": "FJI", "FM": "FSM", "FR": "FRA", "GA": "GMB",
    "GB": "GAB", "GG": "GEO", "GH": "GHA", "GI": "GIB", "GJ": "GRD",
    "GL": "GRL", "GM": "DEU", "GR": "GRC", "GT": "GTM", "GV": "GIN",
    "GY": "GUY", "HA": "HTI", "HO": "HND", "HR": "HRV", "HU": "HUN",
    "IC": "ISL", "ID": "IDN", "IN": "IND", "IR": "IRN", "IS": "ISR",
    "IT": "ITA", "IV": "CIV", "IZ": "IRQ", "JA": "JPN", "JM": "JAM",
    "JO": "JOR", "KE": "KEN", "KG": "KGZ", "KN": "PRK", "KR": "KIR",
    "KS": "KOR", "KT": "CUW", "KU": "KWT", "KZ": "KAZ", "LA": "LAO",
    "LE": "LBN", "LG": "LVA", "LH": "LTU", "LI": "LBR", "LO": "SVK",
    "LS": "LIE", "LT": "LSO", "LU": "LUX", "LY": "LBY", "MA": "MDG",
    "MC": "MAC", "MD": "MDA", "MF": "MYT", "MG": "MNG", "MH": "MSR",
    "MI": "MWI", "MJ": "MNE", "MK": "MKD", "ML": "MLI", "MN": "MCO",
    "MO": "MAR", "MP": "MUS", "MR": "MRT", "MT": "MLT", "MU": "OMN",
    "MV": "MDV", "MX": "MEX", "MY": "MYS", "MZ": "MOZ", "NG": "NER",
    "NH": "VUT", "NI": "NGA", "NL": "NLD", "NO": "NOR", "NP": "NPL",
    "NR": "NRU", "NS": "SUR", "NU": "NIC", "NZ": "NZL", "PA": "PRY",
    "PE": "PER", "PK": "PAK", "PL": "POL", "PM": "PAN", "PO": "PRT",
    "PP": "PNG", "PS": "PLW", "PU": "GNB", "QA": "QAT", "RM": "MHL",
    "RO": "ROU", "RP": "PHL", "RS": "RUS", "RW": "RWA", "SA": "SAU",
    "SC": "KNA", "SE": "SYC", "SF": "ZAF", "SG": "SEN", "SI": "SVN",
    "SK": "SRB", "SL": "SLE", "SM": "SMR", "SN": "SGP", "SO": "SOM",
    "SP": "ESP", "ST": "LCA", "SU": "SDN", "SV": "SVK", "SW": "SWE",
    "SY": "SYR", "SZ": "CHE", "TC": "ARE", "TD": "TTO", "TH": "THA",
    "TI": "TJK", "TN": "TON", "TO": "TGO", "TP": "STP", "TS": "TUN",
    "TT": "TLS", "TU": "TUR", "TV": "TUV", "TW": "TWN", "TX": "TKM",
    "TZ": "TZA", "UC": "CUW", "UG": "UGA", "UK": "GBR", "UP": "UKR",
    "US": "USA", "UV": "BFA", "UY": "URY", "UZ": "UZB", "VC": "VCT",
    "VE": "VEN", "VI": "VGB", "VM": "VNM", "VT": "VAT", "WA": "NAM",
    "WI": "WSM", "WZ": "SWZ", "XK": "XKX", "YM": "YEM", "ZA": "ZMB",
    "ZI": "ZWE",
}


def _fips_to_iso3(fips: str) -> str | None:
    """FIPS 10-4 country code -> ISO3. Returns None if unmappable."""
    if not fips or len(fips) != 2:
        return None
    if fips in _FIPS_TO_ISO3:
        return _FIPS_TO_ISO3[fips]
    # Pass-through: many FIPS == ISO2 codes match pycountry lookups
    try:
        import pycountry  # type: ignore
        c = pycountry.countries.get(alpha_2=fips.upper())
        if c:
            return c.alpha_3
    except Exception:
        pass
    return None


# Environment-relevant GDELT themes (hand-curated subset of the 10K+ catalog).
# Extend as needed; documented in docs/gdelt_themes.md if/when populated.
_GDELT_THEMES: list[dict] = [
    {"theme": "ENV_CLIMATECHANGE", "desc": "Climate change discussion"},
    {"theme": "ENV_WATERPOLLUTION", "desc": "Water pollution / contamination"},
    {"theme": "ENV_DEFORESTATION", "desc": "Deforestation"},
    {"theme": "ENV_BIODIVERSITY", "desc": "Biodiversity loss / protection"},
    {"theme": "ENV_SPECIESENDANGERED", "desc": "Endangered species"},
    {"theme": "ENV_AIRPOLLUTION", "desc": "Air pollution / smog / haze"},
    {"theme": "ENV_OVERFISH", "desc": "Overfishing / fisheries depletion"},
    {"theme": "ENV_MARINEPOLLUTION", "desc": "Marine pollution / plastic / oil spills"},
    {"theme": "ENV_OILBIOENERGY", "desc": "Oil / bioenergy / fossil fuels"},
    {"theme": "ENV_RENEWABLEENERGY", "desc": "Renewable energy"},
    {"theme": "ENV_NUCLEARPOWER", "desc": "Nuclear power"},
    {"theme": "NATURAL_DISASTER", "desc": "Natural disaster (any category)"},
    {"theme": "NATURAL_DISASTER_DROUGHT", "desc": "Drought events"},
    {"theme": "NATURAL_DISASTER_FLOOD", "desc": "Flood events"},
    {"theme": "NATURAL_DISASTER_WILDFIRE", "desc": "Wildfire events"},
    {"theme": "NATURAL_DISASTER_STORM", "desc": "Storm / cyclone / hurricane events"},
    {"theme": "NATURAL_DISASTER_EARTHQUAKE", "desc": "Earthquake events"},
    {"theme": "NATURAL_DISASTER_VOLCANIC", "desc": "Volcanic events"},
    {"theme": "EPU_POLICY_WATER", "desc": "Water policy / governance"},
    {"theme": "EPU_POLICY_ENERGY", "desc": "Energy policy / subsidies"},
    {"theme": "WB_567_ENERGY", "desc": "World Bank topic: energy"},
    {"theme": "WB_2024_ANTI-CORRUPTION", "desc": "World Bank topic: corruption"},
    {"theme": "ECON_SUBSIDIES", "desc": "Government subsidies"},
    {"theme": "EDUCATION", "desc": "Education coverage"},
    {"theme": "HEALTH_PANDEMIC", "desc": "Pandemic / outbreak coverage"},
    {"theme": "WATER_SECURITY", "desc": "Water security / scarcity"},
]


def search_gdelt(query: str, max_results: int = 10) -> list[dict]:
    """Search the curated GDELT theme catalog."""
    q = query.lower().strip()
    matches = [
        t for t in _GDELT_THEMES
        if q in t["theme"].lower() or q in t["desc"].lower()
    ]
    return matches[:max_results]


def _gdelt_bq_client():
    """Lazy-import google-cloud-bigquery client with lazy env check."""
    import os as _os
    if not _os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS not set in .env — service "
            "account JSON path is required for GDELT BigQuery access."
        )
    from google.cloud import bigquery  # type: ignore
    return bigquery.Client()


def preview_gdelt(theme: str) -> dict:
    """One-day sample query for cost estimate + coverage sanity.

    Runs a dry-run first to report estimated bytes, then fetches the top 5
    country-year mention counts for a narrow date range.
    """
    from google.cloud import bigquery  # type: ignore
    client = _gdelt_bq_client()
    q = f"""
    WITH parsed AS (
      SELECT
        SPLIT(loc, '#')[SAFE_OFFSET(3)] AS fips_country,
        V2Themes
      FROM `gdelt-bq.gdeltv2.gkg_partitioned`,
           UNNEST(SPLIT(V2Locations, ';')) AS loc
      WHERE _PARTITIONTIME BETWEEN TIMESTAMP('2023-06-15') AND TIMESTAMP('2023-06-16')
        AND V2Locations IS NOT NULL
    )
    SELECT
      fips_country,
      COUNTIF(V2Themes LIKE '%{theme}%') AS theme_mentions,
      COUNT(*) AS all_mentions
    FROM parsed
    WHERE fips_country IS NOT NULL AND LENGTH(fips_country) = 2
    GROUP BY fips_country
    ORDER BY theme_mentions DESC
    LIMIT 10
    """
    dry = client.query(q, job_config=bigquery.QueryJobConfig(dry_run=True))
    est_gb = dry.total_bytes_processed / 1e9
    try:
        rows = list(client.query(q).result())
    except Exception as exc:
        return {"theme": theme, "error": str(exc)[:300], "estimated_gb": est_gb}
    sample = []
    for r in rows[:5]:
        iso3 = _fips_to_iso3(r.fips_country)
        sample.append({
            "fips": r.fips_country,
            "iso3": iso3,
            "theme_mentions": int(r.theme_mentions),
            "all_mentions": int(r.all_mentions),
        })
    return {
        "theme": theme,
        "estimated_gb_per_day": round(est_gb, 3),
        "sample": sample,
    }


def fetch_gdelt(
    theme: str,
    year_range: tuple[int, int] = (2020, 2024),
    normalize_by: str = "all_mentions",
) -> pd.DataFrame:
    """Aggregate theme mentions per country-year into a share.

    One BigQuery job per year to keep individual queries within a safe
    cost envelope (~475 GB/year).

    Parameters
    ----------
    theme : str
        GDELT theme string (e.g. ``"ENV_CLIMATECHANGE"``). Matched with
        ``V2Themes LIKE '%{theme}%'``.
    year_range : tuple[int, int]
        Inclusive year range.
    normalize_by : {"all_mentions", "raw"}
        ``"all_mentions"`` returns theme_mentions / all_mentions (country's
        share of GDELT attention). ``"raw"`` returns raw mention counts.
        Default ``"all_mentions"`` controls for GDELT under-indexing of
        some countries.
    """
    from google.cloud import bigquery  # type: ignore
    client = _gdelt_bq_client()

    epi_isos = _get_epi_iso_set()
    records: list[dict] = []
    for year in range(year_range[0], year_range[1] + 1):
        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"
        q = f"""
        WITH parsed AS (
          SELECT
            SPLIT(loc, '#')[SAFE_OFFSET(3)] AS fips_country,
            V2Themes
          FROM `gdelt-bq.gdeltv2.gkg_partitioned`,
               UNNEST(SPLIT(V2Locations, ';')) AS loc
          WHERE _PARTITIONTIME BETWEEN TIMESTAMP('{start}') AND TIMESTAMP('{end}')
            AND V2Locations IS NOT NULL
        )
        SELECT
          fips_country,
          COUNTIF(V2Themes LIKE '%{theme}%') AS theme_mentions,
          COUNT(*) AS all_mentions
        FROM parsed
        WHERE fips_country IS NOT NULL AND LENGTH(fips_country) = 2
        GROUP BY fips_country
        """
        try:
            rows = list(client.query(q).result())
        except Exception as exc:
            logger.warning("GDELT query failed for theme %s year %d: %s",
                           theme, year, exc)
            continue
        for r in rows:
            iso3 = _fips_to_iso3(r.fips_country)
            if not iso3:
                continue
            if epi_isos and iso3 not in epi_isos:
                continue
            theme_n = int(r.theme_mentions or 0)
            all_n = int(r.all_mentions or 0)
            if all_n == 0:
                continue
            if normalize_by == "all_mentions":
                value = theme_n / all_n
            else:
                value = float(theme_n)
            records.append({"iso": iso3, "year": year, "value": value})

    if not records:
        logger.warning(
            "GDELT fetch returned 0 records for theme %s (%d-%d)",
            theme, year_range[0], year_range[1],
        )
        return pd.DataFrame(columns=["iso", "year", "value"])

    df = pd.DataFrame(records, columns=["iso", "year", "value"])
    df = df.groupby(["iso", "year"], as_index=False)["value"].mean()
    return df


def fetch_and_store_gdelt(
    conn,
    theme: str,
    year_range: tuple[int, int] = (2020, 2024),
    normalize_by: str = "all_mentions",
    *,
    triggered_by: str = None,
    force_refresh: bool = False,
) -> str:
    """Fetch GDELT theme share data, store in DB, return the variable_id."""
    from epi_proxy.utils.db import (
        register_variable, upsert_observations, variable_exists, variable_coverage,
    )

    theme_slug = theme.lower().replace("_", "-")
    suffix = "share" if normalize_by == "all_mentions" else "count"
    variable_id = f"gdelt:{theme_slug}_{suffix}"

    if not force_refresh and variable_exists(conn, variable_id):
        cov = variable_coverage(conn, variable_id)
        if cov["n_observations"] > 0:
            logger.info(
                "DB hit: %s already has %d observations, skipping fetch",
                variable_id, cov["n_observations"],
            )
            return variable_id

    df = fetch_gdelt(theme, year_range=year_range, normalize_by=normalize_by)

    register_variable(
        conn,
        variable_id,
        name=f"GDELT GKG {theme} ({suffix})",
        description=(
            f"Country-year share of GDELT GKG records mentioning {theme!r} "
            f"in V2Themes (parsed via FIPS country codes in V2Locations). "
            f"'share' means theme_mentions / all_mentions per country-year."
        ),
        source_type="gdelt",
        source_org="GDELT Project",
        source_code=theme,
        source_url="https://www.gdeltproject.org/",
        source_granularity="event",
        aggregation_method="share" if suffix == "share" else "count",
    )

    upsert_observations(
        conn, variable_id, df,
        triggered_by=triggered_by,
        source_url="gdelt-bq.gdeltv2.gkg_partitioned",
    )
    return variable_id


# ---------------------------------------------------------------------------
# Local indicator discovery
# ---------------------------------------------------------------------------

def list_local_indicators() -> list[dict]:
    """List all TLAs available as local raw CSVs in the EPI data directory.

    Reads ``master_variable_list.csv`` and filters to rows where
    ``RawFileExists == "yes"``. Returns a list of dicts with keys
    ``tla``, ``description``, ``type``, ``source``.

    Agents can call this to discover what's already on disk before
    attempting to download data from an external API.
    """
    try:
        df = pd.read_csv(MASTER_VARIABLE_LIST)
    except Exception as exc:
        logger.warning("Could not read master_variable_list.csv: %s", exc)
        return []

    available = df[df["RawFileExists"].str.strip().str.lower() == "yes"]

    results: list[dict] = []
    for _, row in available.iterrows():
        results.append({
            "tla": row.get("Abbreviation", ""),
            "description": row.get("Description", ""),
            "type": row.get("Type", ""),
            "source": row.get("Source", ""),
        })
    return results
