import json
import os
import pandas as pd
import numpy as np

from src.utils.stats import (
    run_bivariate_correlation,
    run_partial_correlation,
    determine_verdict,
    build_result_json,
    test_functional_form,
)
from src.utils.data_utils import load_raw_indicator
from src.utils.data_fetch import fetch_world_bank_indicator

OUTPUT_DIR = "/Users/samkouteili/yale/rose/epi/multi-agent/outputs/PHL/stage2/PHL-H09"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HYPOTHESIS_ID = "PHL-H09"
EXPECTED_DIRECTION = "negative"

print("=" * 60)
print(f"Verifying hypothesis: {HYPOTHESIS_ID}")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# 1. Load EPI target indicator
# ─────────────────────────────────────────────────────────────
print("\n[1] Loading PHL target indicator...")
target = load_raw_indicator("PHL")
print(f"    Loaded {len(target)} rows, columns: {target.columns.tolist()}")
print(f"    Years in target: {sorted(target['year'].unique())}")
print(f"    Countries: {target['iso'].nunique()}")

# PHL has data only for 2022
target_2022 = target[target["year"] == 2022].copy()
print(f"    2022 observations: {len(target_2022)}")

# ─────────────────────────────────────────────────────────────
# 2. Acquire proxy data from World Bank
#    AG.CON.FERT.ZS = fertilizer consumption (kg per hectare of arable land)
#    This directly represents the fertilizer-per-arable-land ratio
# ─────────────────────────────────────────────────────────────
print("\n[2] Fetching fertilizer data from World Bank (AG.CON.FERT.ZS)...")
fertilizer_wb = fetch_world_bank_indicator("AG.CON.FERT.ZS")

proxy_available = False
merged = None

if fertilizer_wb is not None and len(fertilizer_wb) > 0:
    print(f"    Fetched {len(fertilizer_wb)} rows from World Bank (fertilizer kg/ha)")
    fertilizer_wb = fertilizer_wb.rename(columns={"value": "fertilizer_per_ha"})

    # Use most recent available year per country (2019-2022)
    fert_recent = fertilizer_wb[fertilizer_wb["year"].isin([2019, 2020, 2021, 2022])]
    fert_latest = (
        fert_recent.sort_values("year", ascending=False)
        .groupby("iso")
        .first()
        .reset_index()[["iso", "year", "fertilizer_per_ha"]]
    )
    print(f"    Fertilizer data: {len(fert_latest)} countries with 2019-2022 data")

    # Merge with target (match on iso only since years differ)
    merged = target_2022[["iso", "country", "value"]].merge(
        fert_latest[["iso", "fertilizer_per_ha"]], on="iso", how="inner"
    )
    merged = merged.dropna(subset=["value", "fertilizer_per_ha"])
    merged = merged.rename(columns={"fertilizer_per_ha": "proxy_value"})
    print(f"    After merge & dropna: {len(merged)} observations, {merged['iso'].nunique()} countries")

    if len(merged) >= 20:
        proxy_available = True
    else:
        print("    WARNING: fewer than 20 observations after merge — insufficient data")
else:
    print("    World Bank fetch failed.")

# ─────────────────────────────────────────────────────────────
# Handle case where proxy is unavailable
# ─────────────────────────────────────────────────────────────
if not proxy_available:
    print("\n    Proxy data insufficient. Writing inconclusive result.")
    result = {
        "hypothesis_id": HYPOTHESIS_ID,
        "verdict": "inconclusive",
        "verification_method": "statistical_test",
        "data_quality_notes": (
            "Could not obtain sufficient proxy data for Agricultural Input Pressure Ratio. "
            "Attempted World Bank AG.CON.FERT.ZS (fertilizer kg per ha arable land) but "
            "merge with PHL 2022 target yielded insufficient observations."
        ),
        "summary": "Hypothesis could not be tested due to data unavailability.",
    }
    out_path = os.path.join(OUTPUT_DIR, "result.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n    Wrote result to {out_path}")
    import sys; sys.exit(0)

# ─────────────────────────────────────────────────────────────
# 4. Proxy summary stats
# ─────────────────────────────────────────────────────────────
print(f"\n[4] Proxy stats: mean={merged['proxy_value'].mean():.2f}, "
      f"std={merged['proxy_value'].std():.2f}, "
      f"min={merged['proxy_value'].min():.2f}, max={merged['proxy_value'].max():.2f}")
print(f"    Target (PHL) stats: mean={merged['value'].mean():.2f}, "
      f"std={merged['value'].std():.2f}")

# ─────────────────────────────────────────────────────────────
# 5. Bivariate correlation
# ─────────────────────────────────────────────────────────────
print("\n[5] Computing bivariate correlation...")
corr = run_bivariate_correlation(merged["proxy_value"], merged["value"], iso=merged["iso"])
print(f"    Pearson r={corr.pearson_r:.4f}, p={corr.pearson_p:.4f}")
print(f"    Spearman rho={corr.spearman_rho:.4f}, p={corr.spearman_p:.4f}")
print(f"    n_obs={corr.n_observations}, n_countries={corr.n_countries}")

# ─────────────────────────────────────────────────────────────
# 6. Partial correlation controlling for log(GDP per capita)
# ─────────────────────────────────────────────────────────────
print("\n[6] Loading GDP per capita for partial correlation...")
gpc = load_raw_indicator("GPC")

# Use most recent GPC available per country
gpc_recent = (
    gpc[gpc["year"].isin([2019, 2020, 2021, 2022])]
    .sort_values("year", ascending=False)
    .groupby("iso")
    .first()
    .reset_index()[["iso", "value"]]
    .rename(columns={"value": "gpc"})
)

merged_gpc = merged.merge(gpc_recent, on="iso", how="inner")
merged_gpc = merged_gpc.dropna(subset=["gpc", "proxy_value", "value"])
merged_gpc["log_gpc"] = np.log(merged_gpc["gpc"].clip(lower=1))
print(f"    After GPC merge: {len(merged_gpc)} observations")

partial = None
if len(merged_gpc) >= 20:
    try:
        partial = run_partial_correlation(merged_gpc, "proxy_value", "value", ["log_gpc"])
        print(f"    Partial r={partial.partial_r:.4f}, p={partial.partial_p:.4f}")
    except Exception as e:
        print(f"    Partial correlation failed: {e}")
        partial = None
else:
    print("    Insufficient data for partial correlation.")

# ─────────────────────────────────────────────────────────────
# 7. Functional form test
# ─────────────────────────────────────────────────────────────
print("\n[7] Testing functional forms...")
try:
    form = test_functional_form(merged["proxy_value"], merged["value"])
    print(f"    Best form: {form.best_form.value}")
    print(f"    Linear R²={form.linear_r2:.4f}, AIC={form.linear_aic:.2f}")
    print(f"    Log-linear R²={form.log_linear_r2:.4f}, AIC={form.log_linear_aic:.2f}")
    print(f"    Quadratic R²={form.quadratic_r2:.4f}, AIC={form.quadratic_aic:.2f}")
except Exception as e:
    print(f"    Functional form test failed: {e}")
    form = None

# ─────────────────────────────────────────────────────────────
# 8. Verdict
# ─────────────────────────────────────────────────────────────
print("\n[8] Determining verdict...")
verdict = determine_verdict(corr, partial, EXPECTED_DIRECTION)
print(f"    Verdict: {verdict.value}")

# ─────────────────────────────────────────────────────────────
# 9. Build and write result JSON
# ─────────────────────────────────────────────────────────────
data_quality_notes = (
    "Proxy: World Bank AG.CON.FERT.ZS — fertilizer consumption (kg per hectare of arable land). "
    "This indicator directly represents the fertilizer-per-arable-land ratio hypothesized. "
    "Used most recent available year (2019–2022) per country matched against PHL 2022 target. "
    "Note: the proxy does not exclude protected areas from the arable land denominator, which is a "
    "limitation relative to the exact hypothesis specification (which calls for arable land "
    "outside protected areas specifically). "
    f"Final merged dataset: {len(merged)} countries. "
    + ("Partial correlation failed due to numerical issues in pingouin library; " if partial is None else "")
)

partial_str = ""
if partial is not None:
    partial_str = f"Partial r (controlling log GDP/cap)={partial.partial_r:.3f} (p={partial.partial_p:.3f}). "
else:
    partial_str = "Partial correlation not computed (numerical issue). "

form_str = f"Best functional form: {form.best_form.value}. " if form is not None else "Functional form test not computed. "

summary = (
    f"Bivariate Pearson r={corr.pearson_r:.3f} (p={corr.pearson_p:.3f}), "
    f"Spearman rho={corr.spearman_rho:.3f} (p={corr.spearman_p:.3f}), "
    f"n={corr.n_observations}. "
    + partial_str
    + form_str
    + f"Verdict: {verdict.value}. "
    "The hypothesis predicts that higher fertilizer pressure per arable land is associated with "
    "greater cropland encroachment into protected areas (lower PHL score)."
)

result = build_result_json(
    HYPOTHESIS_ID,
    verdict,
    corr,
    partial,
    functional_form=form,
    data_quality_notes=data_quality_notes,
    summary=summary,
)
result["verification_method"] = "statistical_test"

out_path = os.path.join(OUTPUT_DIR, "result.json")
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"\n[9] Wrote result to {out_path}")
print("\nDone.")
print("=" * 60)
print(json.dumps(result, indent=2))