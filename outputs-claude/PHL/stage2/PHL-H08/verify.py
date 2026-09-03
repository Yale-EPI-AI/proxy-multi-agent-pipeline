import json
import os
import pandas as pd
import numpy as np
import requests

from src.utils.stats import (
    run_bivariate_correlation,
    run_partial_correlation,
    determine_verdict,
    build_result_json,
    test_functional_form,
)
from src.utils.data_utils import load_raw_indicator
from src.utils.data_fetch import (
    fetch_world_bank_indicator,
    search_world_bank,
    list_local_indicators,
)

output_path = "/Users/samkouteili/yale/rose/epi/multi-agent/outputs/PHL/stage2/PHL-H08"
os.makedirs(output_path, exist_ok=True)

print("=== PHL-H08: Tree Cover Loss in Protected Areas ===\n")

# 1. Load EPI target data
print("Loading PHL target indicator...")
target = load_raw_indicator("PHL")
print(f"  PHL data: {len(target)} rows, years: {target['year'].unique()}")

# 2. Try to get tree cover loss data
# Hansen Global Forest Change is a raster dataset, not available via World Bank API directly.
# Let's try Global Forest Watch / World Bank proxies for forest loss.

proxy = None
data_quality_notes = ""

# Try searching World Bank for forest-related indicators
print("\nSearching World Bank for forest loss / tree cover indicators...")
try:
    results = search_world_bank("forest area deforestation")
    print(f"  Found {len(results)} results")
    if len(results) > 0:
        print(results[["id", "name"]].head(10).to_string())
except Exception as e:
    print(f"  Search failed: {e}")

# Try AG.LND.FRST.ZS - Forest area (% of land area) from World Bank
print("\nAttempting to fetch Forest area (% of land area) - AG.LND.FRST.ZS...")
try:
    forest_area = fetch_world_bank_indicator("AG.LND.FRST.ZS")
    print(f"  Forest area data: {len(forest_area)} rows")
    print(f"  Years: {forest_area['year'].unique()[:10]}")
    proxy_candidate = forest_area.rename(columns={"value": "proxy_value"})
    # We need data around 2022 (the target year)
    # Take the most recent available year per country
    proxy_recent = proxy_candidate.sort_values("year").groupby("iso").last().reset_index()
    proxy_recent = proxy_recent[["iso", "year", "proxy_value"]]
    print(f"  Most recent forest area data per country: {len(proxy_recent)} countries")
    if len(proxy_recent) > 20:
        proxy = proxy_recent
        data_quality_notes = (
            "Hansen Global Forest Change raster data not directly accessible via API. "
            "Used World Bank indicator AG.LND.FRST.ZS (Forest area % of land area) as proxy. "
            "This measures total forest cover rather than tree cover loss in protected areas specifically. "
            "The relationship is inverted: lower forest area implies more historical loss. "
            "PHL target covers year 2022; proxy uses most recent available year per country. "
            "Forest area is a positive correlate of PHL (higher forest cover = more protected area intact), "
            "so expected direction should be positive for this proxy (despite hypothesis expecting negative for tree cover LOSS)."
        )
        proxy_direction = "positive"
    else:
        proxy = None
except Exception as e:
    print(f"  Failed to fetch AG.LND.FRST.ZS: {e}")

# If forest area failed, try AG.LND.FRST.K2 (forest area in sq km)
if proxy is None:
    print("\nTrying AG.LND.FRST.K2 (Forest area in sq km)...")
    try:
        forest_area2 = fetch_world_bank_indicator("AG.LND.FRST.K2")
        print(f"  Forest area (km2) data: {len(forest_area2)} rows")
        proxy_candidate = forest_area2.rename(columns={"value": "proxy_value"})
        proxy_recent = proxy_candidate.sort_values("year").groupby("iso").last().reset_index()
        proxy_recent = proxy_recent[["iso", "year", "proxy_value"]]
        if len(proxy_recent) > 20:
            proxy = proxy_recent
            data_quality_notes = (
                "Hansen Global Forest Change raster data not directly accessible via API. "
                "Used World Bank indicator AG.LND.FRST.K2 (Forest area in sq km) as fallback proxy. "
                "This is an absolute measure, not a rate of loss in protected areas. "
                "Expected direction: positive (more forest = more intact protected areas)."
            )
            proxy_direction = "positive"
    except Exception as e:
        print(f"  Failed: {e}")

# Try another approach: look for deforestation rate or annual forest change
if proxy is None:
    print("\nSearching for deforestation rate indicators...")
    try:
        results2 = search_world_bank("annual deforestation forest loss")
        print(results2[["id", "name"]].head(10).to_string() if len(results2) > 0 else "No results")
    except Exception as e:
        print(f"  Search failed: {e}")

# Try ER.LND.PTLD.ZS - terrestrial protected areas
if proxy is None:
    print("\nTrying ER.LND.PTLD.ZS (Terrestrial protected areas % total land area)...")
    try:
        prot_areas = fetch_world_bank_indicator("ER.LND.PTLD.ZS")
        print(f"  Protected areas data: {len(prot_areas)} rows")
        proxy_candidate = prot_areas.rename(columns={"value": "proxy_value"})
        proxy_recent = proxy_candidate.sort_values("year").groupby("iso").last().reset_index()
        proxy_recent = proxy_recent[["iso", "year", "proxy_value"]]
        if len(proxy_recent) > 20:
            proxy = proxy_recent
            data_quality_notes = (
                "Hansen Global Forest Change raster data not directly accessible via API. "
                "Used World Bank indicator ER.LND.PTLD.ZS (Terrestrial protected areas % total land) as fallback. "
                "This does not directly measure tree cover loss but captures protected area coverage. "
                "Expected direction: positive (more protected area coverage may correlate with higher PHL score)."
            )
            proxy_direction = "positive"
    except Exception as e:
        print(f"  Failed: {e}")

# 3. Merge and analyze
if proxy is not None:
    print(f"\nProxy data available: {len(proxy)} countries")
    # Merge with target (target year is 2022)
    # Use proxy year-agnostic (most recent) merge
    target_2022 = target[target["year"] == 2022].copy() if 2022 in target["year"].values else target.copy()
    
    # Try merging by iso only (since proxy is cross-sectional, most recent year)
    merged = target_2022.merge(proxy[["iso", "proxy_value"]], on="iso")
    print(f"  Merged dataset: {len(merged)} observations")
    
    if len(merged) < 20:
        print("  Insufficient merged data, trying year-based merge...")
        merged = target.merge(proxy, on=["iso", "year"])
        print(f"  Year-based merge: {len(merged)} observations")
    
    if len(merged) < 10:
        print("  Insufficient data after merging. Reporting inconclusive.")
        proxy = None
    else:
        print(f"  Proxy value range: {merged['proxy_value'].min():.2f} - {merged['proxy_value'].max():.2f}")
        print(f"  Target value range: {merged['value'].min():.2f} - {merged['value'].max():.2f}")

if proxy is not None and len(merged) >= 10:
    # 4. Bivariate correlation
    print("\nRunning bivariate correlation...")
    corr = run_bivariate_correlation(merged["proxy_value"], merged["value"], iso=merged["iso"])
    print(f"  Pearson r={corr.pearson_r:.4f}, p={corr.pearson_p:.4f}")
    print(f"  Spearman rho={corr.spearman_rho:.4f}, p={corr.spearman_p:.4f}")
    print(f"  n_observations={corr.n_observations}, n_countries={corr.n_countries}")

    # 5. Partial correlation controlling for log(GDP per capita)
    print("\nLoading GPC for partial correlation...")
    gpc = load_raw_indicator("GPC")
    merged_with_iso_year = merged.copy()
    if "year" not in merged_with_iso_year.columns:
        merged_with_iso_year["year"] = 2022
    
    gpc_recent = gpc.sort_values("year").groupby("iso").last().reset_index()[["iso", "value"]].rename(columns={"value": "gpc"})
    merged_gpc = merged_with_iso_year.merge(gpc_recent, on="iso")
    merged_gpc["log_gpc"] = np.log(merged_gpc["gpc"].clip(lower=1))
    print(f"  Merged with GPC: {len(merged_gpc)} observations")

    partial = None
    if len(merged_gpc) >= 15:
        try:
            partial = run_partial_correlation(merged_gpc, "proxy_value", "value", ["log_gpc"])
            print(f"  Partial r={partial.partial_r:.4f}, p={partial.partial_p:.4f}")
        except Exception as e:
            print(f"  Partial correlation failed: {e}")

    # 6. Functional form test
    print("\nTesting functional forms...")
    try:
        form = test_functional_form(merged["proxy_value"], merged["value"])
        print(f"  Best form: {form.best_form.value}")
        print(f"  Linear R²={form.linear_r2:.4f}, Log-linear R²={form.log_linear_r2:.4f}, Quadratic R²={form.quadratic_r2:.4f}")
    except Exception as e:
        print(f"  Functional form test failed: {e}")
        form = None

    # 7. Verdict
    print("\nDetermining verdict...")
    verdict = determine_verdict(corr, partial, proxy_direction)
    print(f"  Verdict: {verdict.value}")

    # 8. Build result
    result = build_result_json(
        "PHL-H08",
        verdict,
        corr,
        partial,
        functional_form=form,
        data_quality_notes=data_quality_notes + 
            " Note: The original hypothesis uses 'tree cover loss' (negative direction), "
            "but the proxy used here is 'forest area' (positive direction). "
            "The verdict reflects the proxy used, not the original hypothesis exactly.",
        summary=(
            f"Used World Bank forest area indicator as proxy for tree cover loss in protected areas. "
            f"Bivariate: Pearson r={corr.pearson_r:.3f} (p={corr.pearson_p:.3f}), "
            f"Spearman rho={corr.spearman_rho:.3f} (p={corr.spearman_p:.3f}), "
            f"n={corr.n_observations}. "
            f"{'Partial r=' + str(round(partial.partial_r, 3)) + ' (p=' + str(round(partial.partial_p, 3)) + ')' if partial else 'No partial correlation.'} "
            f"Verdict: {verdict.value}. "
            "The Hansen Global Forest Change raster data was not accessible via available APIs."
        )
    )
    result["verification_method"] = "statistical_test"

else:
    # Cannot get proxy data
    print("\nUnable to obtain suitable proxy data. Reporting inconclusive.")
    
    result = {
        "hypothesis_id": "PHL-H08",
        "verdict": "inconclusive",
        "verification_method": "statistical_test",
        "data_quality_notes": (
            "Hansen Global Forest Change dataset is a raster dataset (GeoTIFF) at 30m resolution "
            "and is not accessible via standard data APIs (World Bank, WHO GHO). "
            "Attempted to use World Bank forest area indicators (AG.LND.FRST.ZS, AG.LND.FRST.K2, ER.LND.PTLD.ZS) "
            "as fallbacks, but merged data was insufficient for statistical analysis. "
            "The hypothesis specifically requires tree cover loss within protected areas, "
            "which requires specialized GIS processing of the Hansen dataset overlaid with WDPA boundaries. "
            "Global Forest Watch provides pre-processed statistics but requires web API access not available here."
        ),
        "summary": (
            "Verdict is inconclusive due to inability to access tree cover loss data in protected areas. "
            "The Hansen Global Forest Change dataset requires specialized GIS tools or Global Forest Watch API access "
            "to extract tree cover loss statistics within protected area boundaries. "
            "This data is not available through standard World Bank or WHO APIs."
        ),
        "bivariate_correlation": None,
        "partial_correlation": None,
        "functional_form": None,
    }

# Write result
output_file = f"{output_path}/result.json"
print(f"\nWriting results to {output_file}...")
with open(output_file, "w") as f:
    json.dump(result, f, indent=2, default=str)

print(f"\n=== DONE ===")
print(f"Verdict: {result['verdict']}")
print(f"Results written to: {output_file}")