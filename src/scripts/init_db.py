"""Bulk-load all EPI indicator data and country reference into the centralized DuckDB.

Usage:
    uv run python src/scripts/init_db.py
"""

import logging
import re
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from epi_proxy.config import DB_PATH, RAW_DIR, INPUTS_DIR, MASTER_VARIABLE_LIST, MISSING_SENTINELS
from epi_proxy.utils.db import (
    get_connection,
    load_countries,
    register_variable,
    upsert_observations,
    variable_coverage,
    list_variables,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_indicator_metadata() -> dict[str, dict]:
    """Read master_variable_list.csv and return a dict keyed by Abbreviation."""
    df = pd.read_csv(MASTER_VARIABLE_LIST)
    indicators = df[df["Type"] == "Indicator"]
    result = {}
    for _, row in indicators.iterrows():
        result[row["Abbreviation"]] = {
            "name": row.get("Variable", ""),
            "description": row.get("Description", ""),
            "units": row.get("Units", ""),
            "issue_category": row.get("IssueCategory", ""),
            "policy_objective": row.get("PolicyObjective", ""),
            "raw_polarity": row.get("RawPolarity", ""),
            "source": row.get("Source", ""),
        }
    return result


def load_raw_csv_to_long(path: Path) -> tuple[str, pd.DataFrame]:
    """Load a raw EPI CSV and return (tla, long-format DataFrame).

    Returns DataFrame with columns: iso, year, value.
    """
    # Extract TLA from filename: {TLA}_raw.csv
    tla = path.stem.replace("_raw", "")

    df = pd.read_csv(path)

    # Identify year columns matching pattern {TLA}.raw.{YYYY}
    year_cols = [c for c in df.columns if re.match(rf"{re.escape(tla)}\.raw\.\d{{4}}", c)]
    if not year_cols:
        return tla, pd.DataFrame(columns=["iso", "year", "value"])

    id_cols = [c for c in ["code", "iso", "country"] if c in df.columns]
    if "iso" not in id_cols:
        return tla, pd.DataFrame(columns=["iso", "year", "value"])

    long = df.melt(id_vars=id_cols, value_vars=year_cols, var_name="year_col", value_name="value")
    long["year"] = long["year_col"].str.extract(r"(\d{4})").astype(int)
    long = long.drop(columns=["year_col"])

    # Replace sentinels with NaN
    long.loc[long["value"].isin(MISSING_SENTINELS), "value"] = pd.NA
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value"]).reset_index(drop=True)

    return tla, long[["iso", "year", "value"]]


def main():
    # Delete existing DB to start fresh
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("Removed existing database at %s", DB_PATH)

    conn = get_connection(DB_PATH)

    # 1. Load countries
    master_file = INPUTS_DIR / "MasterFile.csv"
    n_countries = load_countries(conn, master_file)
    logger.info("Loaded %d countries from MasterFile.csv", n_countries)

    # 2. Load indicator metadata
    meta = load_indicator_metadata()
    logger.info("Found metadata for %d indicators", len(meta))

    # 3. Load all raw CSVs
    raw_files = sorted(RAW_DIR.glob("*_raw.csv"))
    # Filter out _raw_na.csv and other variant files
    raw_files = [f for f in raw_files if not re.search(r"_raw_\w+\.csv$", str(f))]
    logger.info("Found %d raw CSV files to load", len(raw_files))

    loaded = 0
    skipped = 0
    total_obs = 0

    for path in raw_files:
        tla, df = load_raw_csv_to_long(path)
        if df.empty:
            skipped += 1
            continue

        variable_id = f"epi:{tla}"
        indicator_meta = meta.get(tla, {})

        # Determine polarity
        raw_pol = str(indicator_meta.get("raw_polarity", ""))
        polarity = None
        if raw_pol.lower() in ("positive", "1", "1.0"):
            polarity = "higher_is_better"
        elif raw_pol.lower() in ("negative", "-1", "-1.0"):
            polarity = "lower_is_better"

        register_variable(
            conn,
            variable_id,
            name=indicator_meta.get("name", tla),
            source_type="epi",
            description=indicator_meta.get("description"),
            units=indicator_meta.get("units"),
            source_org="Yale/CIESIN",
            source_code=tla,
            polarity=polarity,
            metadata={
                "issue_category": indicator_meta.get("issue_category", ""),
                "policy_objective": indicator_meta.get("policy_objective", ""),
                "raw_polarity": raw_pol,
                "source": indicator_meta.get("source", ""),
            },
        )

        n = upsert_observations(conn, variable_id, df, triggered_by="bulk_load")
        loaded += 1
        total_obs += n

    logger.info(
        "Loaded %d variables (%d skipped), %d total observations",
        loaded, skipped, total_obs,
    )

    # 4. Print coverage summary for a few key indicators
    print("\n--- Coverage Summary ---")
    sample_tlas = ["UWD", "WRR", "OEB", "SPI", "PHL", "GPC", "HDI", "POP", "URB"]
    for tla in sample_tlas:
        vid = f"epi:{tla}"
        try:
            cov = variable_coverage(conn, vid)
            if cov["n_observations"] > 0:
                print(
                    f"  {vid:15s}  {cov['n_observations']:6d} obs, "
                    f"{cov['n_countries']:3d} countries, "
                    f"{cov['year_min']}-{cov['year_max']}"
                )
        except Exception:
            pass

    # 5. Print totals
    total_vars = conn.execute("SELECT COUNT(*) FROM variable").fetchone()[0]
    total_obs_db = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    total_countries = conn.execute("SELECT COUNT(*) FROM country").fetchone()[0]
    print(f"\n--- Database Totals ---")
    print(f"  Variables:    {total_vars}")
    print(f"  Observations: {total_obs_db}")
    print(f"  Countries:    {total_countries}")
    print(f"  DB file:      {DB_PATH}")
    print(f"  DB size:      {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")

    conn.close()


if __name__ == "__main__":
    main()
