import json
import os
import numpy as np
import pandas as pd

from src.utils.stats import (
    run_bivariate_correlation,
    run_partial_correlation,
    determine_verdict,
    build_result_json,
    test_functional_form,
    Verdict,
)
from src.utils.data_utils import load_raw_indicator
from src.utils.data_fetch import fetch_world_bank_indicator

OUTPUT_PATH = "/Users/samkouteili/yale/rose/epi/multi-agent/outputs/PHL/stage2/PHL-H07"
os.makedirs(OUTPUT_PATH, exist_ok=True)

HYPOTHESIS_ID = "PHL-H07"
EXPECTED_DIRECTION = "negative"

print("=" * 60)
print(f"Verifying hypothesis: {HYPOTHESIS_ID}")
print("Target: PHL — % of protected area NOT covered by cropland/buildings")
print("Proxy: Nighttime Lights in Protected Areas (VIIRS DNB)")
print("=" * 60)

# ── Step 1: Load EPI target ───────────────────────────────────────────────────
print("\n[1] Loading EPI target data (PHL)…")
target = load_raw_indicator("PHL")
print(f"    Target shape: {target.shape}")
print(f"    Years in target: {sorted(target['year'].unique())}")
print(target.head())

# ── Step 2: Acquire proxy data ────────────────────────────────────────────────
print("\n[2] Attempting to acquire proxy data…")
print("    VIIRS Nighttime Lights in Protected Areas is not available via standard API.")
print("    Substituting World Bank 'Access to electricity' (EG.ELC.ACCS.ZS) as proxy.")

proxy = None
data_quality_notes = (
    "Direct VIIRS Nighttime Lights in Protected Areas data were not available through "
    "any public tabular API. The Earth Observation Group (EOG) publishes annual VIIRS "
    "composites (VNL V2), but no pre-computed country-level protected-area summary "
    "table is publicly available without custom GIS processing. "
    "Substituted World Bank indicator 'Access to electricity (%)' (EG.ELC.ACCS.ZS) "
    "as the closest available tabular proxy for human infrastructure / settlement. "
    "Note that electricity access is only loosely correlated with NTL radiance inside "
    "protected areas and does not capture the within-PA signal the hypothesis targets. "
    "Results should be interpreted with caution."
)

try:
    df = fetch_world_bank_indicator("EG.ELC.ACCS.ZS")
    if df is not None and not df.empty:
        print(f"    ✓ Retrieved {len(df)} rows for EG.ELC.ACCS.ZS")
        proxy = df.rename(columns={"value": "proxy_value"})
    else:
        print("    ✗ Empty result for EG.ELC.ACCS.ZS")
except Exception as e:
    print(f"    ✗ Failed to fetch EG.ELC.ACCS.ZS: {e}")

# ── Step 3: Merge ─────────────────────────────────────────────────────────────
merged = None
if proxy is not None:
    print("\n[3] Merging proxy with target on iso + year…")
    target_years = sorted(target["year"].unique())
    proxy_years = sorted(proxy["year"].unique())
    print(f"    Target years: {target_years}")
    print(f"    Proxy years available: {proxy_years[:10]}…")

    overlap = set(target_years) & set(proxy_years)
    if overlap:
        use_year = max(overlap)
        print(f"    Using overlapping year: {use_year}")
        proxy_sub = proxy[proxy["year"] == use_year][["iso", "year", "proxy_value"]].copy()
        merged = target.merge(proxy_sub, on=["iso", "year"])
    else:
        target_year = int(target_years[-1])
        closest_year = min(proxy_years, key=lambda y: abs(int(y) - target_year))
        print(f"    No exact overlap. Using closest proxy year: {closest_year}")
        proxy_sub = proxy[proxy["year"] == closest_year][["iso", "proxy_value"]].copy()
        # Merge on iso only, keep target year
        merged = target.merge(proxy_sub, on="iso")
        data_quality_notes += (
            f" Proxy year ({closest_year}) does not exactly match target year "
            f"({target_year}); merged on ISO code only."
        )

    print(f"    Merged shape: {merged.shape}")
    print(merged[["iso", "year", "value", "proxy_value"]].head())

    if len(merged) < 20:
        print("    ⚠ Fewer than 20 observations – marking inconclusive.")
        merged = None

# ── Step 4–7: Analysis ────────────────────────────────────────────────────────
if merged is not None and len(merged) >= 20:
    print("\n[4] Running bivariate correlation…")
    corr = run_bivariate_correlation(
        merged["proxy_value"], merged["value"], iso=merged["iso"]
    )
    print(f"    Pearson r    = {corr.pearson_r:.4f}, p = {corr.pearson_p:.4f}")
    print(f"    Spearman rho = {corr.spearman_rho:.4f}, p = {corr.spearman_p:.4f}")
    print(f"    n = {corr.n_observations}, countries = {corr.n_countries}")

    print("\n[5] Running partial correlation controlling for log(GPC)…")
    gpc = load_raw_indicator("GPC")

    # Get the year present in merged
    merge_year = int(merged["year"].iloc[0])
    gpc_years = sorted(gpc["year"].unique())

    if merge_year in gpc_years:
        gpc_sub = gpc[gpc["year"] == merge_year][["iso", "year", "value"]].rename(
            columns={"value": "gpc"}
        )
    else:
        closest_gpc_year = min(gpc_years, key=lambda y: abs(int(y) - merge_year))
        print(f"    GPC year {merge_year} not found; using {closest_gpc_year}")
        gpc_sub = gpc[gpc["year"] == closest_gpc_year][["iso", "value"]].rename(
            columns={"value": "gpc"}
        )
        # Add year column to allow merge
        gpc_sub = gpc_sub.copy()
        gpc_sub["year"] = merge_year

    # Merge GPC into merged dataframe (on iso + year)
    merged_gpc = merged.merge(gpc_sub[["iso", "year", "gpc"]], on=["iso", "year"], how="inner")
    merged_gpc = merged_gpc[merged_gpc["gpc"] > 0].copy()
    merged_gpc["log_gpc"] = np.log(merged_gpc["gpc"])
    print(f"    Rows after GPC merge: {len(merged_gpc)}")

    partial = None
    if len(merged_gpc) >= 20:
        # run_partial_correlation needs: df with columns for x, y, controls
        # Ensure all needed columns present
        print(f"    Columns in merged_gpc: {list(merged_gpc.columns)}")
        try:
            partial = run_partial_correlation(
                merged_gpc, "proxy_value", "value", ["log_gpc"]
            )
            print(f"    Partial r = {partial.partial_r:.4f}, p = {partial.partial_p:.4f}")
        except Exception as e:
            print(f"    ✗ Partial correlation failed: {e}")
            print("    Proceeding without partial correlation.")
            partial = None
    else:
        print("    ⚠ Too few rows for partial correlation after GPC merge.")

    print("\n[6] Testing functional form…")
    # Drop NaNs for functional form test
    form_data = merged[["proxy_value", "value"]].dropna()
    form = test_functional_form(form_data["proxy_value"], form_data["value"])
    print(f"    Best form: {form.best_form.value}")
    print(f"    Linear R²={form.linear_r2:.4f}, Log-linear R²={form.log_linear_r2:.4f}, Quadratic R²={form.quadratic_r2:.4f}")

    print("\n[7] Determining verdict…")
    verdict = determine_verdict(corr, partial, EXPECTED_DIRECTION)
    print(f"    Verdict: {verdict.value}")

    result = build_result_json(
        HYPOTHESIS_ID,
        verdict,
        corr,
        partial,
        functional_form=form,
        data_quality_notes=data_quality_notes,
        summary=(
            f"Tested whether {corr.n_observations} country-level observations show a "
            f"negative relationship between access-to-electricity (EG.ELC.ACCS.ZS, used "
            f"as substitute for VIIRS Nighttime Lights in Protected Areas) and the "
            f"proportion of protected areas free from cropland/buildings (PHL). "
            f"Pearson r = {corr.pearson_r:.3f} (p = {corr.pearson_p:.3f}), "
            f"Spearman rho = {corr.spearman_rho:.3f} (p = {corr.spearman_p:.3f}). "
            f"Best functional form: {form.best_form.value}. "
            f"True VIIRS Nighttime Lights in Protected Areas data were unavailable; "
            f"the substitute indicator is a weak proxy that operates at the national "
            f"rather than within-protected-area level."
        ),
    )

else:
    # ── Inconclusive path ─────────────────────────────────────────────────────
    print("\n[4–7] Insufficient data → verdict = inconclusive")

    if not data_quality_notes:
        data_quality_notes = (
            "VIIRS Day/Night Band Nighttime Lights data inside protected area boundaries "
            "is a specialised geospatial product not distributed through any standard "
            "tabular API. No substitute with sufficient coverage was found."
        )

    result = {
        "hypothesis_id": HYPOTHESIS_ID,
        "verdict": Verdict.inconclusive.value,
        "verification_method": "statistical_test",
        "bivariate": None,
        "partial": None,
        "functional_form": None,
        "data_quality_notes": data_quality_notes,
        "summary": (
            "Hypothesis PHL-H07 could not be verified because Nighttime Lights "
            "in Protected Areas data are not available as a pre-computed tabular "
            "dataset through any accessible API. Custom GIS processing of VIIRS "
            "composites and protected-area polygons (WDPA) would be required."
        ),
    }

# ── Ensure verification_method key ───────────────────────────────────────────
if isinstance(result, dict):
    result["verification_method"] = "statistical_test"

# ── Write result ──────────────────────────────────────────────────────────────
out_file = os.path.join(OUTPUT_PATH, "result.json")
print(f"\n[8] Writing result to {out_file}…")

with open(out_file, "w") as f:
    json.dump(result, f, indent=2, default=str)

print("    ✓ Done.")
print("\nFinal result summary:")
print(json.dumps(result, indent=2, default=str))