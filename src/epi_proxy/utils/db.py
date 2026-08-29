"""Centralized DuckDB data store for the EPI proxy discovery pipeline.

All fetched data (EPI indicators, proxy variables, control variables) is stored
as country-year-value observations in a single DuckDB database. The stats API
operates on variable IDs rather than raw arrays, handling alignment internally.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from epi_proxy.config import DB_PATH

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS variable (
    variable_id     VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    description     VARCHAR,
    units           VARCHAR,
    source_type     VARCHAR NOT NULL,
    source_org      VARCHAR,
    source_code     VARCHAR,
    source_url      VARCHAR,
    polarity        VARCHAR,
    granularity     VARCHAR NOT NULL DEFAULT 'country_year',
    fetch_timestamp TIMESTAMP,
    metadata        JSON
);

CREATE TABLE IF NOT EXISTS observation (
    variable_id  VARCHAR NOT NULL REFERENCES variable(variable_id),
    iso          VARCHAR(3) NOT NULL,
    year         INTEGER NOT NULL,
    value        DOUBLE NOT NULL,
    PRIMARY KEY (variable_id, iso, year)
);

CREATE TABLE IF NOT EXISTS country (
    iso   VARCHAR(3) PRIMARY KEY,
    code  INTEGER NOT NULL,
    name  VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_log (
    fetch_id      INTEGER PRIMARY KEY,
    variable_id   VARCHAR NOT NULL REFERENCES variable(variable_id),
    fetched_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
    source_url    VARCHAR,
    rows_fetched  INTEGER,
    rows_inserted INTEGER,
    status        VARCHAR NOT NULL,
    error_message VARCHAR,
    triggered_by  VARCHAR
);

CREATE SEQUENCE IF NOT EXISTS fetch_log_seq START 1;

CREATE TABLE IF NOT EXISTS stat_result (
    result_id      INTEGER PRIMARY KEY,
    x_variable_id  VARCHAR NOT NULL REFERENCES variable(variable_id),
    y_variable_id  VARCHAR NOT NULL REFERENCES variable(variable_id),
    test_type      VARCHAR NOT NULL,
    computed_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
    n_observations INTEGER,
    n_countries    INTEGER,
    results        JSON NOT NULL,
    covariate_ids  JSON,
    hypothesis_id  VARCHAR
);

CREATE SEQUENCE IF NOT EXISTS stat_result_seq START 1;
"""

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

_conn_cache: dict[str, duckdb.DuckDBPyConnection] = {}


def get_connection(path: Optional[Path] = None) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection, creating the schema if needed.

    Connections are cached by path so repeated calls return the same handle.
    """
    db_path = path or DB_PATH
    key = str(db_path)
    if key not in _conn_cache:
        conn = duckdb.connect(str(db_path))
        init_schema(conn)
        _conn_cache[key] = conn
    return _conn_cache[key]


def close_connection(path: Optional[Path] = None) -> None:
    """Close and remove a cached connection."""
    key = str(path or DB_PATH)
    conn = _conn_cache.pop(key, None)
    if conn:
        conn.close()


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they don't exist."""
    for stmt in _SCHEMA_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    # Additive columns on variable — idempotent ALTER TABLE.
    # source_granularity: native granularity of the upstream data before
    #   our aggregation (e.g. "station", "article", "event", "pixel").
    # aggregation_method: how we collapsed source granularity to country-year
    #   (e.g. "mean", "sum", "count", "share").
    for alter in (
        "ALTER TABLE variable ADD COLUMN source_granularity VARCHAR",
        "ALTER TABLE variable ADD COLUMN aggregation_method VARCHAR",
    ):
        try:
            conn.execute(alter)
        except duckdb.CatalogException:
            pass


# ---------------------------------------------------------------------------
# Variable registry
# ---------------------------------------------------------------------------


def register_variable(
    conn: duckdb.DuckDBPyConnection,
    variable_id: str,
    name: str,
    source_type: str,
    *,
    description: str = None,
    units: str = None,
    source_org: str = None,
    source_code: str = None,
    source_url: str = None,
    polarity: str = None,
    granularity: str = "country_year",
    source_granularity: str = None,
    aggregation_method: str = None,
    metadata: dict = None,
) -> None:
    """Insert or replace a variable in the registry."""
    meta_json = json.dumps(metadata) if metadata else None
    conn.execute(
        """
        INSERT OR REPLACE INTO variable
            (variable_id, name, description, units, source_type, source_org,
             source_code, source_url, polarity, granularity, fetch_timestamp, metadata,
             source_granularity, aggregation_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            variable_id, name, description, units, source_type, source_org,
            source_code, source_url, polarity, granularity,
            datetime.now(timezone.utc), meta_json,
            source_granularity, aggregation_method,
        ],
    )


def variable_exists(conn: duckdb.DuckDBPyConnection, variable_id: str) -> bool:
    """Check if a variable is registered."""
    result = conn.execute(
        "SELECT 1 FROM variable WHERE variable_id = ?", [variable_id]
    ).fetchone()
    return result is not None


def list_variables(
    conn: duckdb.DuckDBPyConnection, source_type: str = None
) -> pd.DataFrame:
    """List registered variables, optionally filtered by source_type."""
    if source_type:
        return conn.execute(
            "SELECT * FROM variable WHERE source_type = ? ORDER BY variable_id",
            [source_type],
        ).df()
    return conn.execute("SELECT * FROM variable ORDER BY variable_id").df()


def variable_coverage(conn: duckdb.DuckDBPyConnection, variable_id: str) -> dict:
    """Return coverage stats for a variable."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS n_observations,
               COUNT(DISTINCT iso) AS n_countries,
               MIN(year) AS year_min,
               MAX(year) AS year_max
        FROM observation
        WHERE variable_id = ?
        """,
        [variable_id],
    ).fetchone()
    return {
        "n_observations": row[0],
        "n_countries": row[1],
        "year_min": row[2],
        "year_max": row[3],
    }


# ---------------------------------------------------------------------------
# Observation CRUD
# ---------------------------------------------------------------------------


def upsert_observations(
    conn: duckdb.DuckDBPyConnection,
    variable_id: str,
    df: pd.DataFrame,
    *,
    triggered_by: str = None,
    source_url: str = None,
) -> int:
    """Bulk upsert observations from a DataFrame with columns (iso, year, value).

    Returns the number of rows inserted/updated. Logs to fetch_log.
    """
    if df.empty:
        _log_fetch(conn, variable_id, source_url, 0, 0, "empty", triggered_by=triggered_by)
        return 0

    # Ensure correct column types
    obs = df[["iso", "year", "value"]].copy()
    obs["iso"] = obs["iso"].astype(str)
    obs["year"] = obs["year"].astype(int)
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")
    obs = obs.dropna(subset=["value"])
    obs["variable_id"] = variable_id

    rows_fetched = len(obs)

    # Use INSERT OR REPLACE for upsert
    conn.execute(
        """
        INSERT OR REPLACE INTO observation (variable_id, iso, year, value)
        SELECT variable_id, iso, year, value FROM obs
        """
    )
    rows_inserted = rows_fetched  # DuckDB INSERT OR REPLACE doesn't report individual counts

    _log_fetch(
        conn, variable_id, source_url, rows_fetched, rows_inserted,
        "success", triggered_by=triggered_by,
    )
    logger.info("Upserted %d observations for %s", rows_inserted, variable_id)
    return rows_inserted


def get_observations(
    conn: duckdb.DuckDBPyConnection, variable_id: str
) -> pd.DataFrame:
    """Return all observations for a variable as DataFrame [iso, year, value]."""
    return conn.execute(
        "SELECT iso, year, value FROM observation WHERE variable_id = ? ORDER BY iso, year",
        [variable_id],
    ).df()


def align_variables(
    conn: duckdb.DuckDBPyConnection, *variable_ids: str
) -> pd.DataFrame:
    """Strict inner join on (iso, year) across N variables.

    Returns DataFrame with columns: iso, year, {variable_id_1}, {variable_id_2}, ...
    Only rows where ALL variables have data are included.
    """
    if len(variable_ids) < 2:
        raise ValueError("Need at least 2 variable IDs to align")

    # Build the SQL with aliased self-joins
    aliases = [f"t{i}" for i in range(len(variable_ids))]
    select_parts = [f"{aliases[0]}.iso", f"{aliases[0]}.year"]
    from_part = f"observation {aliases[0]}"
    where_parts = [f"{aliases[0]}.variable_id = ?"]
    params = [variable_ids[0]]

    for i in range(1, len(variable_ids)):
        from_part += f" INNER JOIN observation {aliases[i]} ON {aliases[0]}.iso = {aliases[i]}.iso AND {aliases[0]}.year = {aliases[i]}.year"
        where_parts.append(f"{aliases[i]}.variable_id = ?")
        params.append(variable_ids[i])

    for i, vid in enumerate(variable_ids):
        # Use a safe column alias
        select_parts.append(f"{aliases[i]}.value AS \"{vid}\"")

    sql = f"SELECT {', '.join(select_parts)} FROM {from_part} WHERE {' AND '.join(where_parts)} ORDER BY {aliases[0]}.iso, {aliases[0]}.year"
    return conn.execute(sql, params).df()


# ---------------------------------------------------------------------------
# Country table
# ---------------------------------------------------------------------------


def load_countries(conn: duckdb.DuckDBPyConnection, master_file: Path) -> int:
    """Load the country reference table from MasterFile.csv. Returns row count."""
    df = pd.read_csv(master_file)
    # MasterFile has columns: code, iso, country
    countries = df[["iso", "code", "country"]].dropna(subset=["iso"]).copy()
    countries.columns = ["iso", "code", "name"]
    countries["iso"] = countries["iso"].astype(str).str.strip()
    countries["code"] = countries["code"].astype(int)

    conn.execute("DELETE FROM country")
    conn.execute("INSERT INTO country SELECT * FROM countries")
    count = conn.execute("SELECT COUNT(*) FROM country").fetchone()[0]
    logger.info("Loaded %d countries", count)
    return count


# ---------------------------------------------------------------------------
# Fetch log (internal)
# ---------------------------------------------------------------------------


def _log_fetch(
    conn: duckdb.DuckDBPyConnection,
    variable_id: str,
    source_url: str,
    rows_fetched: int,
    rows_inserted: int,
    status: str,
    *,
    error_message: str = None,
    triggered_by: str = None,
) -> None:
    """Record a fetch event in the log."""
    conn.execute(
        """
        INSERT INTO fetch_log (fetch_id, variable_id, fetched_at, source_url,
                               rows_fetched, rows_inserted, status, error_message, triggered_by)
        VALUES (nextval('fetch_log_seq'), ?, current_timestamp, ?, ?, ?, ?, ?, ?)
        """,
        [variable_id, source_url, rows_fetched, rows_inserted, status, error_message, triggered_by],
    )
