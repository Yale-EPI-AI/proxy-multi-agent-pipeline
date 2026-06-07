"""Component tests for NASA POWER and FAOSTAT data source functions.

Run: conda run -n epi python scripts/test_data_sources.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.data_fetch import (
    fetch_and_store_faostat,
    fetch_and_store_nasa_power,
    fetch_and_store_wikipedia,
    fetch_faostat,
    fetch_nasa_power,
    fetch_wikipedia,
    preview_faostat,
    preview_nasa_power,
    preview_wikipedia,
    search_faostat,
    search_nasa_power,
    search_who_gho,
    search_wikipedia,
)
from src.utils.db import get_connection, variable_coverage


def test_nasa_power():
    print("\n=== NASA POWER ===")

    # Search
    results = search_nasa_power("temperature")
    print(f"Search 'temperature': {len(results)} results")
    if results:
        print(f"  First: {results[0]}")

    # Preview
    preview = preview_nasa_power("T2M", sample_isos=["USA", "BRA", "IND"])
    print(f"Preview T2M: {preview['n_observations']} observations, years: {preview['years'][:5]}...")

    # Fetch (small range to keep it quick)
    df = fetch_nasa_power("T2M", year_range=(2015, 2020))
    print(f"Fetch T2M (2015-2020): {len(df)} rows, {df['iso'].nunique()} countries")
    assert len(df) > 0, "Expected non-empty DataFrame"
    assert set(df.columns) == {"iso", "year", "value"}, f"Wrong columns: {df.columns.tolist()}"
    print("  PASS")

    # Store in DB
    conn = get_connection()
    variable_id = fetch_and_store_nasa_power(conn, "T2M", year_range=(2015, 2020), triggered_by="test")
    cov = variable_coverage(conn, variable_id)
    print(f"DB store: {variable_id} -> {cov['n_countries']} countries, {cov['year_min']}-{cov['year_max']}")
    assert cov["n_observations"] > 0, "Expected observations in DB"
    print("  PASS")


def test_faostat():
    print("\n=== FAOSTAT ===")

    # Search
    results = search_faostat("crop")
    print(f"Search 'crop': {len(results)} results")
    if results:
        print(f"  First: {results[0]}")

    # Preview
    preview = preview_faostat("QCL", "0015", "5510")  # Wheat production
    print(f"Preview QCL/0015/5510: {preview['n_countries']} countries, {preview['n_observations']} observations")

    # Fetch
    df = fetch_faostat("QCL", "0015", "5510", year_range=(2015, 2020))
    print(f"Fetch QCL/0015/5510 (2015-2020): {len(df)} rows, {df['iso'].nunique()} countries")
    if len(df) > 0:
        assert set(df.columns) == {"iso", "year", "value"}, f"Wrong columns: {df.columns.tolist()}"
        print("  PASS")

        # Store in DB
        conn = get_connection()
        variable_id = fetch_and_store_faostat(
            conn, "QCL", "0015", "5510", year_range=(2015, 2020), triggered_by="test",
        )
        cov = variable_coverage(conn, variable_id)
        print(f"DB store: {variable_id} -> {cov['n_countries']} countries")
        assert cov["n_observations"] > 0, "Expected observations in DB"
        print("  PASS")
    else:
        print("  SKIP (no data returned — FAOSTAT API may be slow)")


def test_who_search():
    print("\n=== WHO GHO Search ===")
    results = search_who_gho("water")
    print(f"Search 'water': {len(results)} results")
    if results:
        print(f"  First: {results[0]}")
    print("  PASS")


def test_comtrade():
    print("\n=== UN Comtrade ===")
    from src.utils.data_fetch import (
        search_comtrade, preview_comtrade, fetch_comtrade, fetch_and_store_comtrade,
    )

    # 1. search
    hits = search_comtrade("fertilizer", max_results=5)
    print(f"Search 'fertilizer': {len(hits)} results")
    assert len(hits) > 0
    print(f"  Top: {hits[0]['id']} — {hits[0]['text'][:60]}")
    hs_found = any(h["id"] == "3102" for h in hits)
    assert hs_found, "Expected HS 3102 (nitrogenous fertilizers) in search results"

    # 2. preview
    prev = preview_comtrade("3102", flow="M", year=2022)
    print(f"Preview HS 3102 imports 2022: {prev['n_countries']} countries")
    assert prev["n_countries"] > 50, "Expected broad coverage for fertilizer imports"

    # 3. small fetch (single year to stay under rate limit)
    df = fetch_comtrade("3102", flow="M", year_range=(2022, 2022), unit="usd")
    print(f"Fetch 3102 imports (2022, usd): {len(df)} rows, {df['iso'].nunique()} countries")
    assert set(df.columns) == {"iso", "year", "value"}
    assert len(df) > 50

    # 4. DB store
    conn = get_connection()
    variable_id = fetch_and_store_comtrade(
        conn, "3102", flow="M", year_range=(2022, 2022),
        unit="usd", triggered_by="test",
    )
    cov = variable_coverage(conn, variable_id)
    print(f"DB store: {variable_id} -> {cov['n_countries']} countries, "
          f"{cov['year_min']}-{cov['year_max']}")
    assert cov["n_observations"] > 0
    print("  PASS")


def test_wikipedia():
    print("\n=== Wikipedia Pageviews ===")

    # 1. search
    hits = search_wikipedia("diarrhea", max_results=5)
    print(f"Search 'diarrhea': {len(hits)} results")
    assert len(hits) > 0, "Expected opensearch to return at least one article"
    print(f"  First: {hits[0]['title']}")

    # 2. preview (en.wikipedia — universal English title)
    prev = preview_wikipedia("Diarrhea", "en.wikipedia")
    print(f"Preview 'Diarrhea' on en.wikipedia: {prev['n_years']} years, "
          f"{prev['total_pageviews']:,} total pageviews")
    assert prev["n_years"] >= 5, "Expected at least 5 years of pageview data"

    # 3. small fetch — 2 years, all EPI countries mapped
    df = fetch_wikipedia("Diarrhea", year_range=(2022, 2023))
    print(f"Fetch 'Diarrhea' (2022-2023): {len(df)} rows, "
          f"{df['iso'].nunique()} countries")
    assert set(df.columns) == {"iso", "year", "value"}, \
        f"Wrong columns: {df.columns.tolist()}"
    assert len(df) > 0
    years = sorted(df["year"].unique())
    assert years == [2022, 2023], f"Year filter leaked: {years}"

    # 4. shared-language sanity — USA/GBR/CAN should receive identical values
    usa_2023 = df[(df.iso == "USA") & (df.year == 2023)]["value"].iloc[0]
    gbr_2023 = df[(df.iso == "GBR") & (df.year == 2023)]["value"].iloc[0]
    can_2023 = df[(df.iso == "CAN") & (df.year == 2023)]["value"].iloc[0]
    assert usa_2023 == gbr_2023 == can_2023, \
        "Anglophone countries should share the en.wikipedia value"
    print(f"  USA=GBR=CAN shared-en value (2023): {usa_2023:,.0f}")
    print("  PASS")

    # 5. DB store
    conn = get_connection()
    variable_id = fetch_and_store_wikipedia(
        conn, "Diarrhea", year_range=(2022, 2023), triggered_by="test",
    )
    cov = variable_coverage(conn, variable_id)
    print(f"DB store: {variable_id} -> {cov['n_countries']} countries, "
          f"{cov['year_min']}-{cov['year_max']}")
    assert cov["n_observations"] > 0
    print("  PASS")


if __name__ == "__main__":
    test_who_search()
    test_nasa_power()
    test_faostat()
    test_wikipedia()
    print("\n=== ALL TESTS PASSED ===")
