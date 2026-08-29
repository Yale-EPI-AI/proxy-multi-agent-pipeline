"""DB-aware statistical analysis wrappers.

Thin layer that retrieves and aligns data from the centralized DuckDB,
then delegates to the pure-computation functions in src.utils.stats.
"""

from __future__ import annotations

from typing import Optional

import duckdb

from epi_proxy.schemas import CorrelationResult, FunctionalFormResult, PartialCorrelationResult, Verdict
from epi_proxy.utils import db
from epi_proxy.utils.stats import (
    build_result_json,
    determine_verdict,
    run_bivariate_correlation as _raw_bivariate,
    run_partial_correlation as _raw_partial,
    test_functional_form as _raw_functional_form,
)


def run_bivariate_correlation(
    conn: duckdb.DuckDBPyConnection,
    x_variable_id: str,
    y_variable_id: str,
) -> CorrelationResult:
    """Align x and y on (iso, year), then compute bivariate correlation."""
    aligned = db.align_variables(conn, x_variable_id, y_variable_id)
    return _raw_bivariate(
        aligned[x_variable_id],
        aligned[y_variable_id],
        iso=aligned["iso"],
    )


def run_partial_correlation(
    conn: duckdb.DuckDBPyConnection,
    x_variable_id: str,
    y_variable_id: str,
    covariate_ids: list[str],
) -> Optional[PartialCorrelationResult]:
    """Align all variables, then compute partial correlation."""
    all_ids = [x_variable_id, y_variable_id] + covariate_ids
    aligned = db.align_variables(conn, *all_ids)
    return _raw_partial(aligned, x_variable_id, y_variable_id, covariate_ids)


def test_functional_form(
    conn: duckdb.DuckDBPyConnection,
    x_variable_id: str,
    y_variable_id: str,
) -> Optional[FunctionalFormResult]:
    """Align x and y on (iso, year), then test functional forms."""
    aligned = db.align_variables(conn, x_variable_id, y_variable_id)
    return _raw_functional_form(aligned[x_variable_id], aligned[y_variable_id])


def run_full_verification(
    conn: duckdb.DuckDBPyConnection,
    proxy_variable_id: str,
    target_variable_id: str,
    expected_direction: str,
    *,
    hypothesis_id: str = "",
    control_ids: list[str] = None,
) -> dict:
    """Run the complete verification battery and return a result dict.

    Steps:
        1. Bivariate correlation (proxy vs target)
        2. Partial correlation controlling for covariates
        3. Functional form testing (linear, log-linear, quadratic)
        4. Verdict determination

    Returns a dict compatible with build_result_json / VerificationResult.
    """
    if control_ids is None:
        control_ids = ["epi:GPC"]

    # 1. Bivariate
    corr = run_bivariate_correlation(conn, proxy_variable_id, target_variable_id)

    # 2. Partial correlation (only if controls exist in DB)
    partial = None
    available_controls = [
        c for c in control_ids
        if db.variable_exists(conn, c) and c not in (proxy_variable_id, target_variable_id)
    ]
    if available_controls:
        partial = run_partial_correlation(
            conn, proxy_variable_id, target_variable_id, available_controls
        )

    # 3. Functional form
    func_form = test_functional_form(conn, proxy_variable_id, target_variable_id)

    # 4. Verdict
    verdict = determine_verdict(corr, partial, expected_direction)

    # Build coverage info for data quality notes
    proxy_cov = db.variable_coverage(conn, proxy_variable_id)
    target_cov = db.variable_coverage(conn, target_variable_id)
    notes = (
        f"Proxy coverage: {proxy_cov['n_countries']} countries, "
        f"{proxy_cov['year_min']}-{proxy_cov['year_max']}. "
        f"Target coverage: {target_cov['n_countries']} countries, "
        f"{target_cov['year_min']}-{target_cov['year_max']}. "
        f"Aligned observations: {corr.n_observations}."
    )

    return build_result_json(
        hypothesis_id=hypothesis_id,
        verdict=verdict,
        corr=corr,
        partial_corr=partial,
        functional_form=func_form,
        data_quality_notes=notes,
        summary=f"DB-verified: {proxy_variable_id} vs {target_variable_id}, verdict={verdict.value}",
        verification_method="db_statistical_test",
    )
