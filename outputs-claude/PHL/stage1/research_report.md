# Alternative Data Sources for the Yale EPI Protected Human Land (PHL) Indicator: A Comprehensive Proxies Analysis

**Key Points**
*   **The Problem:** The current Protected Human Land (PHL) indicator provides only a single snapshot (2022) of human encroachment within protected areas (PAs), limiting the Yale Environmental Performance Index (EPI) team's ability to track longitudinal trends and perform historical baseline comparisons.
*   **The Objective:** To identify concrete, directly measurable, and high-frequency statistical proxies that capture the presence of cropland and buildings within protected areas across ~180 countries, circumventing the limitations of the single-year Dynamic World dataset.
*   **Top Recommendations:** We identify several highly promising proxies. The most direct proxy is the **Global Cropland Extent time-series** (e.g., GLAD and GACED30 datasets), which provides 30-meter resolution annual data from 2000 to 2024. Other powerful proxies include **Road Density in PAs** (GRIP dataset), **Active Fire Anomalies** (NASA FIRMS), and the **Global Human Footprint Index**. 
*   **Context and Caveats:** While these datasets offer superior temporal resolution and comparable spatial fidelity, researchers must account for definitional differences (e.g., varying thresholds for what constitutes "cropland") and the inherent limitations of optical remote sensing in cloud-prone tropical regions. High-level macroeconomic indices have been strictly excluded to avoid spurious correlations.

This report is designed to furnish the Yale EPI team with a rigorous, exhaustive literature review and data discovery analysis. It maps the causal pathways of human encroachment in protected areas, evaluates literature-validated and novel speculative proxies, and provides a structured assessment of data availability and potential confounders. 

***

## 1. Causal Map of Protected Human Land (PHL)

To identify valid statistical proxies for the PHL indicator (Percentage of protected area NOT covered by cropland and buildings), it is essential to first understand the mechanistic web of upstream drivers (causes) and downstream consequences (effects) of human encroachment in protected areas. By mapping these pathways, we can pinpoint variables that precede, co-occur with, or immediately follow the conversion of protected land into agricultural or built environments.

### 1.1 Conceptual Causal Diagram

```text
[UPSTREAM MACRO DRIVERS]
Global Commodity Demand (Agricultural Exports)
Population Growth (Peri-PA Demographics)
Poverty & Subsistence Needs
Weak Governance & Corruption
       |
       v
[INTERMEDIATE VECTORS / FACILITATORS]
Infrastructure Expansion (Roads/Railways) --------> Timber Extraction / Logging
Legal Rollbacks (Downgrading, Downsizing)           (Precursor to Agriculture)
       |                                                   |
       v                                                   v
[PROXIMATE CAUSES / DIRECT ACTIONS]
Slash-and-Burn Land Clearing (Active Fires)
Land Grabbing & Informal Settlements
       |
       v
====================================================================
--> TARGET INDICATOR (PHL): Cropland & Buildings Inside Protected Areas <--
====================================================================
       |
       v
[IMMEDIATE BIOPHYSICAL EFFECTS]
Loss of Natural Vegetation (Deforestation/Habitat Conversion)
Increased Artificial Illumination (Nighttime Lights)
Alteration of Surface Albedo & Microclimate
       |
       v
[DOWNSTREAM ECOLOGICAL OUTCOMES]
Habitat Fragmentation (Edge Effects)
Decline in Biodiversity Intactness (Species Richness/Abundance)
Disruption of Migratory Corridors
Human-Wildlife Conflict
Biomass Carbon Loss (Emissions)
```

### 1.2 Upstream Causes: Drivers of Variation Across Countries

Variation in PHL across the ~180 countries evaluated by the EPI is driven by a complex interplay of socioeconomic, legal, and infrastructural factors. 

**1. Infrastructure Proliferation (The Vector of Encroachment):**
The most potent physical precursor to the establishment of croplands and buildings in protected areas is road construction. Roads serve as the primary vector for human encroachment, lowering the economic barriers to entry for agricultural expansion and settlement [cite: 1, 2]. In tropical and sub-tropical regions, the expansion of legal, illegal, and informal ("ghost") roads consistently precedes deforestation and the subsequent establishment of agriculture [cite: 2]. As road density increases near or within a protected area boundary, the probability of cropland conversion rises exponentially.

**2. Legal Rollbacks (PADDD Events):**
Protected areas are often viewed as permanent fixtures, but they are subject to legal changes. Protected Area Downgrading, Downsizing, and Degazettement (PADDD) events legally authorize increased human use, including agriculture and infrastructure development, or shrink the boundaries of PAs entirely [cite: 3, 4]. Studies have shown that a significant majority of global PADDD events are driven by industrial agriculture, rural settlements, and infrastructure needs [cite: 3, 5]. When governments downgrade PA status, the expansion of croplands and buildings (i.e., a drop in the PHL indicator) is the immediate intended or unintended result.

**3. Economic and Demographic Pressures:**
At the macro level, global demand for agricultural commodities (e.g., soy, palm oil, beef) places immense pressure on land reserves. In regions where arable land outside of PAs is exhausted, degraded, or privately consolidated, smallholder farmers and industrial agro-corporations increasingly look to the unexploited soils within PA boundaries [cite: 6, 7]. Criminal networks and illegal land grabbing also play a significant role in driving agricultural expansion into protected zones, particularly in regions like the Amazon basin [cite: 7].

### 1.3 Downstream Effects: The Consequences of Reduced PHL

When the percentage of protected area not covered by cropland and buildings decreases, a cascade of severe ecological consequences follows:

**1. Biodiversity Loss and Fragmentation:**
The conversion of natural PA habitats into croplands completely reshapes the ecological community, driving local extinctions and significantly lowering the Biodiversity Intactness Index (BII) [cite: 8, 9]. Furthermore, agricultural patches and buildings create edge effects, fragmenting contiguous habitats and severely impacting interior-dwelling and wide-ranging species (e.g., tigers) [cite: 1, 10].

**2. Biomass Carbon Emissions:**
The clearing of natural vegetation—whether tropical forests, temperate woodlands, or peatlands—to make way for crops and buildings releases massive quantities of stored carbon into the atmosphere, transitioning the PA from a carbon sink to a carbon source [cite: 4].

**3. Alteration of Natural Disturbance Regimes:**
The presence of human infrastructure and agriculture brings secondary disturbances, including the introduction of invasive species, the application of chemical fertilizers and pesticides (which alter local hydrology), and the suppression or exacerbation of natural fire regimes.

***

## 2. Literature-Validated Proxies

Through a comprehensive review of academic literature, several well-established datasets have been validated as measuring phenomena conceptually identical, causally intertwined, or highly correlated with the presence of cropland and buildings in protected areas.

### 2.1 The Global Human Footprint (HFP) Index Time-Series

**Variable Name and Description:**
The Global Human Footprint (HFP) dataset maps the cumulative pressure of human activities on terrestrial ecosystems. It specifically integrates high-resolution spatial data on built environments, population density, nighttime lights, croplands, pastures, roads, railways, and navigable waterways [cite: 11, 12]. 

**Source Dataset:**
*   **Organization:** Multiple iterations exist, prominently updated by Mu et al. (2022) [cite: 13], Venter et al. (2016), and Williams et al. (2020) [cite: 14].
*   **Coverage:** Global terrestrial surfaces at 1 km and 100 m resolutions.
*   **Format:** GeoTIFF raster files (easily aggregable by country and PA polygons).
*   **URL/Access:** Figshare [cite: 15] and Scientific Data repositories.

**Reported Correlation Strength and Sample:**
Literature indicates near-perfect inverse theoretical alignment with PHL. Because the HFP explicitly utilizes "croplands" and "built environments" as two of its primary weighted input layers, an increase in HFP within a protected area mathematically guarantees a decrease in PHL (assuming the PA boundary remains static) [cite: 12, 14]. HFP values ranging from 0 to 50 classify areas; values >4 indicate highly modified landscapes (agriculture/buildings) [cite: 12, 16]. 

**Expected Functional Form:**
Log-linear. The initial intrusion of roads and small croplands causes a rapid spike in the HFP score from a baseline of "wilderness" (<1) to "highly modified" (>4) [cite: 12, 16]. Therefore, small decreases in the PHL percentage (initial encroachment) will correspond to massive logarithmic jumps in mean PA Human Footprint scores.

**Key Caveats or Limitations:**
The HFP is a composite of 8 variables, meaning that while it captures croplands and buildings, it also captures population density and grazing/pasture [cite: 11, 17]. If the EPI team specifically wants to isolate *only* buildings and crops (and exclude pasture or roads), the composite nature of HFP introduces minor noise. However, the researchers provide access to the underlying individual pressure layers, allowing data scientists to isolate just the crop and built-environment rasters.

**Full Citation:**
Mu, H., Li, X., Wen, Y., Huang, J., Du, P., Su, W., Miao, S., & Geng, M. (2022). A global record of annual terrestrial Human Footprint dataset from 2000 to 2018. *Scientific Data*, 9(1), 176. [cite: 13]

### 2.2 Global Cropland Extent Time-Series (GLAD & GACED30)

**Variable Name and Description:**
These datasets provide high-resolution (30-meter), multi-decadal mapping of global cropland extent derived from Landsat satellite imagery. "Cropland" is strictly defined as land used for annual and perennial herbaceous crops for human consumption, forage, and biofuel, excluding permanent pastures and shifting cultivation [cite: 18, 19]. 

**Source Dataset:**
*   **Organization:** Global Land Analysis and Discovery Lab (GLAD) at the University of Maryland (Potapov et al.) [cite: 20] and the newly developed Global 30-m Annual Cropland Extent Dynamics (GACED30) by Chen/Lou et al. [cite: 21, 22].
*   **Coverage:** Global (GLAD) and Continental/Global (GACED30), 2000–2022/2024.
*   **Format:** Cloud-optimized GeoTIFFs, accessible via Google Earth Engine and Zenodo [cite: 18, 23].

**Reported Correlation Strength and Sample:**
When masked against the World Database on Protected Areas (WDPA), these datasets provide a **direct, 1:1 volumetric proxy** for the cropland component of the PHL indicator. Potapov et al. note that global cropland expansion accelerated in the 21st century, with half of the new cropland replacing natural vegetation, heavily impacting conservation zones [cite: 24].

**Expected Functional Form:**
Linear. Because this dataset maps exactly what PHL seeks to measure (cropland area), calculating the percentage of WDPA polygons covered by GLAD/GACED30 cropland pixels per country will yield a direct linear proxy for the agricultural component of PHL.

**Key Caveats or Limitations:**
While exceptional for croplands, these datasets do not map "buildings" or urbanization. Therefore, they must be paired with an urban/built-environment dataset (such as the ESA WorldCover built-up layer or WSF) to fully replicate PHL. Additionally, the GLAD dataset uses 4-year epochs (e.g., 2016-2019) to mitigate cloud cover issues in the tropics, meaning true *annual* variation might be smoothed, though GACED30 attempts to resolve this with continuous annual tracking [cite: 19, 22].

**Full Citation:**
Potapov, P., Turubanova, S., Hansen, M. C., Tyukavina, A., Zalles, V., Khan, A., ... & Cortez, J. (2022). Global maps of cropland extent and change show accelerated cropland expansion in the twenty-first century. *Nature Food*, 3(1), 19-28. [cite: 24, 25]

### 2.3 Road Density within Protected Areas (GRIP and Ghost Roads)

**Variable Name and Description:**
Road density (meters of road per square kilometer) measured explicitly inside the boundaries of protected areas. Roads are the primary conduit for the introduction of agricultural expansion, logging, and human settlement.

**Source Dataset:**
*   **Organization:** Global Roads Inventory Project (GRIP) developed by GLOBIO [cite: 26, 27], supplemented by recent "Ghost Roads" mapping by Engert et al. (2024) [cite: 2].
*   **Coverage:** Global, 222 countries, covering ~21 million km of official roads (GRIP) [cite: 28, 29], plus an estimated 1.37 million km of unmapped informal roads in the Asia-Pacific (Ghost Roads) [cite: 2].
*   **Format:** Vector (ESRI file geodatabase/shapefile) and Raster (road density at 5 arcminutes resolution) [cite: 26, 30].

**Reported Correlation Strength and Sample:**
Engert et al. (2024) found that "road density was by far the strongest correlate of deforestation out of 38 potential biophysical and socioeconomic covariates" [cite: 2]. Similarly, a global study on tiger conservation landscapes found that road densities are a ubiquitous threat, highly correlated with the degradation of protected status and subsequent human encroachment [cite: 1]. 

**Expected Functional Form:**
Quadratic / Non-linear threshold. The relationship between road density and forest loss (and subsequent cropland establishment) is non-linear. Engert et al. note that "deforestation peaking soon after roads penetrate a landscape and then declining as roads multiply and remaining accessible forests largely disappear" [cite: 2]. Thus, the initial introduction of a road into a PA signals a massive impending spike in croplands/buildings.

**Key Caveats or Limitations:**
Official datasets like GRIP heavily underestimate informal, illegal, or unpaved logging/agricultural roads ("ghost roads"), which are precisely the roads most likely to be built inside protected areas for illicit agriculture [cite: 2]. Thus, official road density may underestimate the true threat in developing nations.

**Full Citation:**
Meijer, J. R., Huijbregts, M. A., Schotten, K. C., & Schipper, A. M. (2018). Global patterns of current and future road infrastructure. *Environmental Research Letters*, 13(6), 064006. [cite: 29]
Engert, J. E., et al. (2024). Ghost roads and the destruction of Asia-Pacific tropical forests. *Nature*. [cite: 2]

### 2.4 Protected Area Downgrading, Downsizing, and Degazettement (PADDD) Events

**Variable Name and Description:**
PADDD events track legal changes to protected areas. *Downgrading* is a decrease in legal restrictions on human activities (allowing agriculture/buildings); *Downsizing* is a decrease in PA size; *Degazettement* is a complete loss of legal protection [cite: 3, 31].

**Source Dataset:**
*   **Organization:** PADDDtracker, managed by Conservation International and World Wildlife Fund (WWF) [cite: 3, 32].
*   **Coverage:** Global, 4,962 enacted events across 78 countries from 1892 to 2021 [cite: 5, 31].
*   **Format:** Geospatial database and CSV available via Zenodo (Version 2.1) [cite: 31, 32].

**Reported Correlation Strength and Sample:**
PADDD is fundamentally linked to PHL. Globally, 62% of all PADDD events are explicitly driven by the need for agriculture, mining, oil/gas, and industrialization [cite: 3]. Case studies demonstrate that post-PADDD habitats become highly fragmented, deforested, and converted to cropland [cite: 5]. 

**Expected Functional Form:**
Linear. The cumulative area (km²) of PADDD events per country strongly correlates with the loss of pristine protected area, resulting in an increase in cropland and buildings. 

**Key Caveats or Limitations:**
PADDD tracks *legal* rollbacks. In many countries with weak governance, croplands and buildings expand into PAs illegally without any formal PADDD event occurring [cite: 2, 7]. Therefore, this proxy measures state-sanctioned encroachment but misses illegal, informal encroachment. It is an excellent proxy for developed nations and legal transitions but may underestimate encroachment in the Global South.

**Full Citation:**
Conservation International & World Wildlife Fund. (2021). PADDDtracker Data Release Version 2.1. *Zenodo*. [cite: 31, 32]

### 2.5 Biodiversity Intactness Index (BII)

**Variable Name and Description:**
The BII measures the modelled average abundance of originally-present species in a grid cell, relative to their abundance in an intact ecosystem [cite: 33, 34]. It serves as a comprehensive indicator of the ecological impact of land-use change.

**Source Dataset:**
*   **Organization:** Natural History Museum (NHM), UK, utilizing the PREDICTS database [cite: 9, 34, 35].
*   **Coverage:** Global, 100-meter resolution, temporal data from 2000 onwards (updated annually combining Copernicus data and PREDICTS) [cite: 36].
*   **Format:** CSV, JSON, GeoTIFF, accessible via NHM Data Portal and GEO BON [cite: 8, 37].

**Reported Correlation Strength and Sample:**
The BII is mathematically constructed using land-use change and human pressure data. Studies show a severe drop in BII values where natural habitat transitions to agricultural or built environments. When masked to protected areas, the BII serves as an inverted mirror to PHL [cite: 9, 36]. 

**Expected Functional Form:**
Linear. As the percentage of cropland/buildings (PHL) increases, the Biodiversity Intactness Index inside the protected area proportionately decreases due to habitat loss and fragmentation.

**Key Caveats or Limitations:**
BII is a modelled outcome rather than a direct physical measurement. It relies on underlying land-use maps to model species abundance [cite: 9, 34]. Therefore, using BII as a proxy for PHL is somewhat circular if the EPI team strictly wants a physical measurement of land cover. However, as an *outcome-focused* proxy (EPI Criterion 3), it perfectly captures the actual environmental damage caused by the croplands and buildings.

**Full Citation:**
Newbold, T., et al. (2016). Has land use pushed terrestrial biodiversity beyond the planetary boundary? A global assessment. *Science*. (Data hosted via NHM [cite: 37, 38]).

***

## 3. Speculative Proxies (Novel Candidates)

Based on the causal map, we can brainstorm several datasets that have not been explicitly studied as a proxy for the EPI's exact PHL indicator but possess high mechanistic plausibility and excellent data availability. 

### 3.1 Active Fire Anomalies Inside Protected Areas

**Variable Name and Description:**
The density and frequency of active thermal anomalies (fires) detected by satellite instruments, specifically filtered to the boundaries of national and international protected areas.

**Mechanistic Reasoning:**
In tropical, sub-tropical, and many temperate developing regions, agricultural expansion does not occur via mechanical clearing alone; it relies heavily on "slash-and-burn" techniques [cite: 39, 40]. Active fires within a protected area are the most immediate, real-time indicator of forest clearing for impending crop cultivation and informal settlement. While some fires are natural, sustained or geographically clustered fire anomalies within PA boundaries correlate strongly with illegal agricultural encroachment [cite: 39].

**Likely Data Source and Accessibility:**
*   **Source:** NASA Fire Information for Resource Management System (FIRMS) [cite: 41, 42].
*   **Sensors:** MODIS (1km resolution) and VIIRS (375m resolution) [cite: 40, 41].
*   **Accessibility:** Completely open access, updated in near real-time (within 3 hours of observation), with historical archives dating back to 2000. Data available in shapefile, KML, CSV, and via API [cite: 40, 41].

**Expected Direction and Strength of Correlation:**
Strong negative correlation. A high incidence of fire anomalies in a country's PA network strongly predicts an expansion of croplands (lower PHL scores). 
*Expected Functional Form:* Linear or Log-linear. A sudden spike in fire pixels indicates mass clearing.

### 3.2 High-Resolution Nighttime Lights (NTL) in Protected Areas

**Variable Name and Description:**
The sum of artificial nighttime light radiance within protected area boundaries.

**Mechanistic Reasoning:**
While croplands represent the agricultural component of PHL, "buildings" represent the urbanization and human settlement component. Nighttime lights are the gold standard proxy for human settlement, infrastructure development, and industrial activity [cite: 16, 17]. If a protected area is truly undisturbed, its nighttime light radiance should be near zero. An increase in NTL implies the construction of buildings, facilities, and roads. 

**Likely Data Source and Accessibility:**
*   **Source:** Earth Observation Group (EOG) - VIIRS Day/Night Band (DNB) Nighttime Lights.
*   **Accessibility:** Open access, available as monthly and annual composites globally. 

**Expected Direction and Strength of Correlation:**
Strong negative correlation. Higher NTL radiance inside a PA means more buildings and human activity, meaning a worse (lower) PHL score.
*Expected Functional Form:* Log-linear. Even small settlements generate detectable light, meaning the initial transition from 0 buildings to some buildings causes a massive percentage jump in radiance.

### 3.3 Protected Area Forest Cover Loss (Deforestation Alerts)

**Variable Name and Description:**
The percentage of tree cover loss inside protected areas over time. 

**Mechanistic Reasoning:**
In forested biomes, croplands and buildings cannot be established without first removing the canopy. Therefore, tree cover loss is the absolute prerequisite to human encroachment in forested PAs. While tree cover loss can occasionally result from natural disasters (hurricanes, natural fires), the vast majority of deforestation in tropical PAs is anthropogenic and driven by agricultural expansion [cite: 43, 44]. 

**Likely Data Source and Accessibility:**
*   **Source:** Global Forest Watch / Hansen Global Forest Change dataset (University of Maryland).
*   **Accessibility:** Open access, 30m resolution, annual updates globally from 2000 to present.

**Expected Direction and Strength of Correlation:**
Very strong negative correlation. Higher rates of tree cover loss in PAs inevitably lead to a higher percentage of the PA being covered by cropland/buildings.
*Expected Functional Form:* Linear.

### 3.4 Agricultural Chemical Inputs (Fertilizer Import / Arable Land Ratio)

**Variable Name and Description:**
A country's total synthetic fertilizer consumption divided by its officially recognized arable land outside of protected areas.

**Mechanistic Reasoning:**
This is an indirect, macroeconomic proxy, but distinct from general GDP/wealth indices. If a country has rapidly growing fertilizer imports but a stagnant or shrinking base of *official* arable land, it indicates aggressive agricultural intensification. In countries where land scarcity is high, this pressure mathematically forces farmers to expand into unprotected natural lands or illegally into protected areas [cite: 6, 45]. Intensive agriculture requires inputs; an unexplained spike in inputs relative to land suggests illegal spatial expansion (often into PAs).

**Likely Data Source and Accessibility:**
*   **Source:** FAOSTAT (Food and Agriculture Organization of the UN).
*   **Accessibility:** Open access, annual, global country-level data.

**Expected Direction and Strength of Correlation:**
Moderate negative correlation. Higher agricultural input pressure correlates with encroachment into marginal and protected lands [cite: 6].
*Expected Functional Form:* Non-linear threshold. Encroachment accelerates only when a certain density/scarcity of available land is reached.

***

## 4. Data Availability Assessment

The following table evaluates both the literature-validated and speculative proxy candidates against the Yale EPI's 9 inclusion criteria. All proposed proxies meet the baseline requirements for *Relevance*, *Outcome focus* (with the exception of PADDD, which is policy-oriented), and *Open Access*.

| Proxy Candidate | Geographic Coverage | Temporal Granularity & Range | Update Frequency | Methodology Status | Data Type | Meets EPI Spatial / Temporal Rules? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Global Cropland Extent (GLAD/GACED30)** | Global (~190 countries) [cite: 18, 24] | Annual/Epochs (2000–2024) [cite: 22] | Annual/4-year [cite: 19] | Peer-reviewed (Nature Food) [cite: 24] | Satellite (Landsat 30m) | **Yes** (>80 countries, >3 years, post-2018) |
| **2. Global Human Footprint (HFP)** | Global (~190 countries) [cite: 13] | Annual (2000–2020) [cite: 14, 15] | Irregular/Annual [cite: 15] | Peer-reviewed (Nature Sci Data) [cite: 13] | Modeled Satellite/Admin | **Yes** (>80 countries, >3 years, post-2018) |
| **3. NASA FIRMS Active Fires in PAs** | Global (~190 countries) [cite: 41] | Daily/Annual (2000–Present) [cite: 40, 42] | Real-time [cite: 42] | Government Official (NASA) | Satellite (MODIS/VIIRS) | **Yes** (>80 countries, >3 years, post-2018) |
| **4. PADDDtracker (Legal Rollbacks)** | Global (78 countries) [cite: 5, 31] | Multi-year (1892–2021) [cite: 31] | Irregular (v2.1 in 2021) [cite: 31] | Peer-reviewed / NGO [cite: 31, 32] | Administrative / Legal | **Flagged:** Covers 78 countries (falls just short of the 80 country EPI criteria). |
| **5. Road Density in PAs (GRIP)** | Global (222 countries) [cite: 28, 29] | Snapshot / Decadal | Irregular | Peer-reviewed (GLOBIO) [cite: 26, 29] | Vector / GIS | **Flagged:** Temporal completeness. GRIP is mostly a single integrated snapshot, not an annual time-series. |
| **6. Biodiversity Intactness Index (BII)** | Global (~190 countries) [cite: 34] | Annual (2000–Present) [cite: 36] | Annual | Peer-reviewed (NHM) [cite: 9, 34] | Modeled / Survey | **Yes** (>80 countries, >3 years, post-2018) |
| **7. Nighttime Lights in PAs (VIIRS)** | Global (~190 countries) | Annual (2012–Present) | Annual | Government Official (NOAA) | Satellite | **Yes** (>80 countries, >3 years, post-2018) |
| **8. Hansen Tree Cover Loss in PAs** | Global (~190 countries) | Annual (2000–Present) | Annual | Peer-reviewed (Science) | Satellite (Landsat 30m) | **Yes** (>80 countries, >3 years, post-2018) |

***

## 5. Confounder Analysis

When deploying statistical proxies for cross-country environmental comparisons, it is vital to account for systemic confounders that could create spurious correlations. While we have deliberately excluded broad macro-indices (like GDP and HDI) as proxies, these same variables act as massive confounders for the variables we *did* select.

### 5.1 The Environmental Kuznets Curve (GDP per Capita)
**Risk:** GDP per capita exhibits an inverted U-shaped relationship with deforestation and agricultural expansion. Extremely poor countries lack the industrial machinery to clear vast tracts of protected land quickly, relying instead on subsistence expansion. Middle-income developing nations undergo rapid, massive agricultural expansion into protected areas (e.g., Brazil, Indonesia). High-income nations have largely finished their agricultural expansion and are now reforesting or rigorously defending their PAs. 
**Impact on Proxies:** If the EPI team runs a correlation between Global Cropland Extent or NASA Active Fires and PHL, they must control for GDP; otherwise, the proxy will simply stratify countries by their current stage of economic development rather than measuring true performance in environmental governance.

### 5.2 Biome and Topographic Confounders
**Risk:** NASA FIRMS (Active Fires) and Hansen Tree Cover Loss are excellent proxies, but they are heavily confounded by the natural biophysical properties of the country. A country dominated by desert (e.g., Saudi Arabia) will have zero forest loss and zero agricultural fires in its PAs, not necessarily because of excellent governance, but because the biome does not support slash-and-burn agriculture. Similarly, mountainous countries (e.g., Bhutan) have natural topographic protection against cropland expansion compared to flat basin countries.
**Impact on Proxies:** Comparisons using fire or deforestation proxies must be normalized by the baseline arable capacity or forested area of the country's PA network.

### 5.3 Protected Area Network Age and Size
**Risk:** Countries that established their protected area networks a century ago (e.g., USA, South Africa) often secured prime, unpopulated real estate. Countries rapidly expanding their PA networks today to meet the 30x30 Kunming-Montreal Global Biodiversity Framework targets are increasingly forced to designate "paper parks" that already contain legacy human settlements, croplands, and roads [cite: 46, 47]. 
**Impact on Proxies:** Older, smaller PA networks will naturally show higher PHL (better performance) and lower road density (GRIP), while newly established, massive PA networks might look worse statistically simply because they recently grandfathered in existing villages and farms.

### 5.4 Spatial Autocorrelation and the Modifiable Areal Unit Problem (MAUP)
**Risk:** When combining raster datasets (like GLAD cropland or Human Footprint) with vector polygons (WDPA protected areas), spatial misalignment causes massive errors. A 1-kilometer pixel from the Human Footprint dataset might overlap a PA boundary by 10%, but the entire 1km² area gets flagged as "encroachment" inside the PA. 
**Impact on Proxies:** This confounder artificially punishes countries with many small, fragmented protected areas compared to countries with a few massive, contiguous protected areas, because the edge-to-area ratio is higher, increasing the likelihood of boundary pixel bleed.

***

## 6. Ranked Candidates

Based on a synthesis of expected correlation strength, alignment with the original PHL indicator's mechanistic intent, spatial/temporal data availability, and adherence to EPI inclusion criteria, the following is a ranked list of the top proxy candidates.

### #1. Global Cropland Extent Time-Series (GLAD / GACED30)
*   **Summary:** High-resolution (30m) mapping of annual or epochal global cropland from 2000 to present.
*   **Expected Relationship:** Near 1:1 direct measurement of the cropland component of PHL.
*   **Data Source:** GLAD (Potapov et al., Univ. of Maryland) [cite: 20, 24] / GACED30 (Lou et al.) [cite: 21, 22].
*   **Why it ranks 1st:** It perfectly targets the exact physical phenomenon (cropland) that Dynamic World v1 attempted to capture, but does so with a bespoke, peer-reviewed agricultural model over a 20+ year time series, rather than a single 2022 snapshot. 

### #2. The Global Human Footprint (HFP) Index
*   **Summary:** A spatial dataset aggregating built environments, croplands, roads, and nighttime lights into a 0-50 pressure score.
*   **Expected Relationship:** Strong negative correlation (higher HFP = lower PHL).
*   **Data Source:** Mu et al. (2022), Figshare / Scientific Data [cite: 13, 15].
*   **Why it ranks 2nd:** It captures *both* halves of the PHL indicator (croplands and buildings). Furthermore, it is updated annually (2000-2020) and is already pre-processed into an easy-to-use continuous variable [cite: 13, 14].

### #3. NASA FIRMS Active Fire Anomalies (Masked to PAs)
*   **Summary:** Satellite detection of thermal anomalies, acting as a direct signal of slash-and-burn agricultural clearing.
*   **Expected Relationship:** Strong negative correlation (more fires = faster loss of PHL).
*   **Data Source:** NASA LANCE / FIRMS (MODIS & VIIRS) [cite: 41, 42].
*   **Why it ranks 3rd:** Fires are the most immediate, real-time indicator of environmental destruction and agricultural encroachment in the developing world [cite: 39, 40]. The data is hyper-granular, daily, and highly sensitive to sudden changes in environmental enforcement.

### #4. VIIRS Nighttime Lights (Masked to PAs)
*   **Summary:** High-resolution detection of artificial radiance, serving as an un-gamable proxy for buildings, settlements, and infrastructure.
*   **Expected Relationship:** Strong negative correlation (higher radiance = more buildings, lower PHL).
*   **Data Source:** NOAA / Earth Observation Group.
*   **Why it ranks 4th:** While GLAD (#1) perfectly captures the *cropland* half of the indicator, NTL perfectly captures the *buildings* half. Combining GLAD with VIIRS NTL provides a complete, longitudinally robust alternative to Dynamic World.

### #5. Biodiversity Intactness Index (BII)
*   **Summary:** Modelled percentage of original species abundance remaining in a given area.
*   **Expected Relationship:** Strong positive correlation (higher BII = higher PHL).
*   **Data Source:** Natural History Museum (PREDICTS database) [cite: 9, 34].
*   **Why it ranks 5th:** It provides an *outcome-focused* measure. Rather than just measuring the physical presence of a farm, it measures the actual biological damage that farm caused [cite: 8, 36]. It perfectly aligns with the EPI's outcome-focus criteria, though it is a modelled composite.

### #6. Protected Area Downgrading, Downsizing, and Degazettement (PADDD) Events
*   **Summary:** Database tracking legal rollbacks of protected area status.
*   **Expected Relationship:** Moderate negative correlation (more PADDD area = lower PHL).
*   **Data Source:** PADDDtracker (WWF / Conservation International) [cite: 31, 32].
*   **Why it ranks 6th:** Captures the legal mechanism that allows croplands and buildings to enter PAs [cite: 4]. However, it ranks lower because it only covers 78 countries (missing the EPI's 80-country threshold) [cite: 5] and completely ignores illegal, informal encroachment.

### #7. Road Density in Protected Areas (GRIP)
*   **Summary:** Total length of mapped roads per square kilometer inside PA boundaries.
*   **Expected Relationship:** Strong negative correlation (more roads = impending loss of PHL).
*   **Data Source:** GLOBIO / GRIP [cite: 26, 29].
*   **Why it ranks 7th:** Roads are the ultimate precursor to agriculture [cite: 1, 2]. However, the official GRIP dataset lacks rigorous annual temporal granularity, functioning more as a static baseline, and often misses the informal "ghost roads" that are most prevalent in encroached areas [cite: 2, 29].

**Sources:**
1. [nih.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEk_VTw6HL8B4SJKJvFgUcJZTbwnSUfEcJSQHSas77sNpw4gaJC5voaSK1JMvhUkDMwCTMHBhx_8X4SYXxxTfvcjS47VodEAGv68Hzf19JOOYNTqSyNaB01iIXS30lmABKPYBI4KJhb)
2. [nzif.org.nz](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHQpniV4spWu6Lt2AzKIQ73sA4RCDm4o1Du_OFfcK2pS1MgjStoVUPouoGlHfsdLRsEGB_SobokO-O-bREjvU6zzsQPVNu4o3qum0XbxW-__vnhj0o9YVc1KBjlLICyk-ipRSa99Ci63ndhVgQZxOeVmw-H5otbtSHvLC2EwhZfz0QAbPK_hh4=)
3. [wikipedia.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGxQOhvFgsLuOdCLR4aGFrZsAurkhf92zAC1_nKO_5Jyh7jbaJFbFFkBckPg3wjlf5oYo8tkvHvqtEnLvBXR6wCafBWW8p5EtV4_uzLD1rIKReKGrAlgYkHCiuYPH2Q3gIlSEIwhjzq-RhdLyOww7R3Nxk3fAuq5Okc8hPr5S-OZmPGVo9WffTayQjPTiE=)
4. [abcg.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE2QLl2jTL9P0B7xjJqHjZFTP9vLKsH8OjyXSsHvbCnLlZwS9MK1gcd-ybgUwiVnR0qB9U3Km5glx2rII7Wa-lwZ-YVhHprnX9YNmtYB2CD1X_WMMacr_BFZeR5rBVbvCCI4B0Dli7fT6RlA6AYeg227Dw7Q7PE_MWG2ZoT17Ke)
5. [mdpi.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF99nbrpLNYttkISVT2l-WG-SqQHxhrG4XftDOZ7rrbc9hii7pMUV9kLl_mQGaQB_CaPIQ5AZSdGpoyPGdV5E7J1iIR7VkMseJQReUh9xVP5zLxV4XyjLDAYnynvGrt)
6. [forestplanning.jp](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQETVk0AiH4tkvKhrgy5Z58kWk2RAz0g5lmzQawnYDsMKRw1QWWNUE797o7yajZN5PjJJOI0wMdDKLkf8GTnXrqnoAPb8iTupPx6SZl4g8Fb0clOsoa2BJIa1Dh7pQYjwCUsFS6pPoMMMbI=)
7. [liberalamazon.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGLSEkI0Lge1YNMdLyy-flWheAC8e9K9P7b0v0r728UI3SEdWIvcGKZHp6y60XBr47IhXl1HmYhlcXt4-A8TLRhHsRBVuYd38X6njLIYKUHwuOf7U8FYVrgaljjZ1caAK3lePkuduzQjoprQHCJKUMgvEPcceuaJRdiXsmPdpZJPR8-QdpEjDTnobtttoaJxCuIXbeo0w==)
8. [geobon.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEQF0OGTyGeKgiCMf51V8GnmiUH2x5fsdfDr0rY5MSEfVR1Kl9UkieE11HLI745U8Fg_4I6GwKEuY2vDM5JPZtKoNYbDue8X7dSRNMz4ve0E53wiDJPljYXngHczzxnSkULuQ==)
9. [ipbes.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE0AXPemmOhxQK64KW00n6iDTucUPkC1fxNGWYSpUwVZ6wqRgL3iYADhykQqS5yCSsFGMr6c5fr43diWQplBIBSPmmjtFNT3ikAj55sfoZUD45VUKLW5aUUyk2R09IcXr_3BIutBoEjKfQtTtgwNMS1W9bQNYpXJe3Gv4LCmLcKrl2XN6BuPh_TJXsSeTOEaoEzWDtWA8KQs5xgG0WIDdSxUxrKh72eIcx3dxU=)
10. [frontiersin.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG6yoRlpFeaXTC0OCEw7q0dYs0M8e85c0dzyfFDa-HJ65hj-eqyi-2gIl4LGJDLuPCZBqTa48i54shhkhTmuB_66yvJaNj0SIIWRBagKPZTJOOXbcaOWpeHdc1jUUY_qTyGb6NNP_0kmwpJM__jwncxsXT5DIEL4vvlm8ND8GKQlX2jMtBBLDmMQumrNpHsi0e_XfpwddP-)
11. [semanticscholar.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEY3dSMVgR6_u7mfXuX-2j36LUCjxty3e80307u9vRlccEWs-adeYIVMIWlD8ulL5GFn6kxJIslBWu_Y3VyoADEA20GLc2Mp8Acu_Ql5hlERYi-fX5_GtsH9ywha19uTJFsd6AeSeWnCcpbIaYL19DsU02BUd3FafGt0Gnq3lYMPwPK5Mc=)
12. [researchgate.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEGqDj01Ljf0McgJNWGSbCxYxfEjfYZ6FGcF36VCpmYqKv21TUvQbcDv2q9i6d6OP5PvDeQnl5BTTBjQpnBaXE-xTPpswJBFNBtamKHQXDjGycB5TpegNSS7OcINiO63knGYey_VkF6ZeeEpIDg2p9twi9p50Slwlhnq3ngGtin0VQuEQoanT-jw6RKlnGJX0ZIcKwBXZuhvFml_QA3qzFGTAWD2Ot7-Wthvc7zPqd7TiGCWH5-UO95a64bxLy0pqz_)
13. [nih.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFolbgxvkL_NJNAiMZ6QEAf54Xr1sZa3EfRzpQJ9mTDm3grqOxOYaQiCfwzfwMlpNKZwFHgVXPBxekyRje3_9tbI8lusw11qZ1TRtstP7VwQRmMGkggT6yM6m48UDDGEQ==)
14. [frontiersin.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEe4dm1Tqi16a7dfQ4WkGZovG_UDCx6Qra591iHajn0PWRyWaxX5K-e6FS1Xp6COWYIYkaskKnx0ggwgv6MyJPHzehz08pRhriFqVlyGgktzw4EzArXxqS1AEGDq8uzm4OLWJR2571TT5uuFnw4ymSS_Whhzl9zi-D3o_DqCRMjQsj0_3xQFY4dzvSixJIW4XYdMg==)
15. [figshare.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFntCiVv_jIPrsnWeCrX_9eYSI0o2FnLnCxA1d81f4c0142oc50hhZ3_8L_rBQnkLljxkaL_TDBFqS0Sx3iq2zjpwVp_slbyCjfesa3PqfwAMwTcywldLNu15YmNXAinmLDS9tCg41wlGNwyC0FprLotxbvFoMDVF5Ciu5HQnnVrSlEC-I_EWfM0D2oPe6tu6LN1-Q31kNXHH8M2w9cBL_bRCMmYe9QYjUnfw==)
16. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHzL2hugNBkb8tr9ygRPkyNZuEJKVmvY4HyCSZ7eqNxyArCGMJNK8U7Nxvj_Ea0J_C9ntPN2OnsMhebQcvXj1d1LtA_n0hYLar7tXldr_7kkIdPwn9LzXN4asJs17eNFIte817h_DbSPL3tf426diX9WeqS_9cCqd5Q4oGhw05oXuOqPra_NeJxGwFr8aMC62bMzojfj7pPNlNX6VKNUHg3HoDnmWd7gLOgj9QCAk8czUzFg4tq9GbiRp1TmgBdeW9ZM24gqw==)
17. [mdpi.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHXgp8-xz2YgzqhwuyNOB0ixDp1BzUnL3zPLMyUemi8mqMfIuB88VxZ0EZxdxP_MH-Lq2ulHiKPLGAy85h_gZLzIQJ9e0RUnxvbSr7Ij3M4JZbDisLFr1WVy79id7M=)
18. [zenodo.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF3CHb5Amv7q8BMSci2DsW7FXImR-wSSFBDNK_7R8-q01NdQL57RVR938RPT2IB8ZHXkwPfVrrH-e1fbW3RNiAlt66oGFcmDEu5k06fCacUTQfPIjGQMthcPw==)
19. [europa.eu](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEtiC33rshNx0sF8ZLHGXWYjwkAF_zRu72FKv1764A15kd74EByo3BAO39og1xr3xFxbfDtBf5AD0bmbwWZ0W_7SSTwGa4KiP8ReSwrUvCKeKz77lSELlYjlLxLHii5uJCStsqc86264Ff3Ug7zz6Kjp70tn12HSCkeb5-B8fhBGBgbBa28g7kdIFh59M4sCnFl0MQAMhUV3hNEICPPFC04TRdnPndPWub9eTMGf_3OOUB5Y1yn2eriL28wEfj4GSKo4r7a84sdOxqMjNwSHh5ON7epvgNW)
20. [resourcewatch.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF4EndQLTl-AyYcNaoZQY1YeFLl10-MvlCJQiiwKI0VoIuGxXOzJOoXlHQlLWFklr7nbV1r0L-jvYOjwajqPVMmqSplznkJD1fsiVp_3F-Mcyk9SfrKk4zKrdYgSdAvaEheaREvc_lInZ1K2L4SjgbmJ3R-lPH6)
21. [copernicus.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEfH9KfzZaAGSrobqwhzVTwEadO4A4GYgeGDOcN5KkpvTZK3nrkGjMU7ZjfrCaRmDySpKQ109PP4Bsby6fNGGYt8ncbJEALw7C-OUNeTZZEIwoPKvFRIHJYaGtFQJXGJC9QIZVwZkqDxA==)
22. [researchgate.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE0s5EEbYX6fKBNNs7X_umC5UDrrVBf2XE597yLq5FjNJfZJTRI4_Ro7SGi5BdYMvKfFjtcvL3yj_nL1Mm8RGhJIT2KhI60d7r1nBFKeFM8YRDiEetdjGM5S3mCju23pf0cSK4yG3BYFnH3q0MgRo8ET3bCyPG8xrZbVSenLFeY0zwJhtxA5VhzUYz2hGiDpF_7ramP6UsascjrLo_JY0B1yM2VOXxQVQ99QG3tAruAgLVv5x54ml29cJ5iL6xJfiV75gNvv7AY59CxgreosyHWCS0Ah3Z6hUSsCE7m33cUpipnUl74sRzH4xrMiS498EXkVSzFKirMJw1d6nApmHjYieDplsqB3HovVV02l3A90d2eSkTtn6w8n-FI_5V5Eb3B0JKPUd_GAXZtrTy7RoO-uu5-MDpVXO_3B_CjrUqAHqXn63MDxTUMrfV5SQXz3IlPkB3edQVyYGGyDB2NdHTkFSYWqeWCpfDi0zcqS49C7qkLvV-Xl2s2wk5qHCe5Xj4AooCpPNmlZltc8vQmik2dfYbPKFmbixzfWmJwQDzSnu5ayf46CIz1)
23. [openaire.eu](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGm4P44CMZTH3zt9oWdhjFDYZQ0V2J8UOxdv1GdxTjrF_R08wyql0PKThYzdodtRV7hE43jRdSsWYAR7pV55amGVfRvjNpeD6sdUX56vNyVIhMDsHycIhpfWDQw4zIPY6mGVOyCVo3SKeJYcdbCQ9s2aOtTjy9Grusfet0=)
24. [nih.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEc9NpJE77KwwfxjTVQdmrlLZqnrNrApcCy3oWluD15l9X-fJC4DBqPxZIlFPdyaCn10GoLcD7HrxEC7jSWeuT6-f4pAYcQN9qjQMAIqa0jcHPfD1aR7i9BWoxypoEYPw==)
25. [tdl.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFnMlIALMudtu6DNvrRGuPIAu4014trJYb0yUNWIxDHcH1E9oC2pvq4qc7bDcafQbKaUimgIJprHF_wMRjETsVbKAOGDCXb9BVvI-ppmLVvnzp0xI2viaKfQzx_PlwJwIJ-GMGPswjM0dqDk0RIEARsFuVRZ7_vgvJYI3ZdfJ6dNRiLyJOECCUkYpHXpbVgkYhRQHwI)
26. [globio.info](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGFZwzrRKwKIkWh7gIJqmj6Avq5DNmyvGUKoQTt118eTvSJS8lMiVrrvbufrPZpEwarJJXmgaXRoCTunw_b7VqKwHObnSNM646HYLvhEVwhl0p5-vkeayezbtNuG9ao5SbJbHM=)
27. [undp.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG4k-hrJ_tXoy6iZfqIpjwsBZkGpcNh10KOGuV9KabNMP1jPdftCt8EUzvLF_ZIv9f04dZP9AJBsgdVKlSk7BpqbRJ9NHv4QzQtyzrNxGVJIAA1aPb5eqYvDM5U2vptSq-UEil6ojr2btxMQYpE-orV7f0Q-_u30HE=)
28. [regulations.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHKGX-aSf3Pqsrx6Qj6LdrJ5asA1dtQUZmb6oolcexflHXLFBnSAFg814CdvLarL3fTW8hv5J65kG2RoUq49kUDRKwpWbxMmRiaJztMEcyFGKoV5Bl-QuOKm7hCG0E4be47d6DAa38ME45OfVXGaOG02ylMP5978tsUMvVEgtI1pqie)
29. [globio.info](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFo2BV6H3ArVLdebJAyjlDAWc00ZC8fmTvTKzsy32Vi54XiEGXuu-IFAn5YKL-s08cpczhmJnQdSpkm1ekHJ3TZ08Gl_NMpv6iqydJ_WcAz2WrA_Kzl20J2Oz5bpC6nHFVPCIG8nVXfLlVCM2BCGygwIRu5S16FXe8hoqMd3CmKhQjwicgqcbM=)
30. [arcgis.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHEfh1xZgIA8U04rEQD2AvGnZtHdQ-zpzN-pyRdL4sic8prWtcLI4FL9cSwnwRRzs0YpyGgthfebrQKNUO0vtyPibY0R0UoEE-ytrDK9Fxka533wLzvwgWZOV9uKmcPNRSe2QW_Lga-scF577dYEkcVMusvXxdYEaTtX3YtsQNU)
31. [zenodo.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGIcWAJJcMCBpQrd9fuVrjX9HnfX69I-y8duZ7mKvjVfUuMt4cS1joPP0nRKBIcvp5AWPwHJIj6qwqQExTnBzU4lLgMf5vZp4QAXARFqSHkZgX3xCJcDxEZ)
32. [padddtracker.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQERn4FTTEnzt5kPTV-EkL3mGISpLDiXuu_ENxkXvW6s3XXARzymBVd-27-p-7c_x5U6IkRCGco1UjJaijJ6acafDhJChyoaW4dwiDnjnEioiRLERMBn2Q==)
33. [europa.eu](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFyjlTbfKe7QMMIVvrE6D-rxdG1rc9t3uTipdmcdgjs03wbGnEtEiewBBEJfEX9HbzkquOPK-UnZivcrlYNWbUogeSAYTLeH-mYwWaOZvAs_GhNDyMCrgEIGkUtZkLgKqIwHZSTM5Z1FSlMpbiZGXhPLa69kOtl70tP1lTz8B9Rck89ZeU=)
34. [nhm.ac.uk](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEZ75kLjdv2mxu824MNS05hHEeGt7Vq9cLtr0yEC7VPnwxXyKm96auWe-w1v_fWEBus7Zw7Q4U6-M1HVOelA1d3gRulKJzWcfug3XCcv0wZO8GAOzHZT5VPB6ER-3EhJnbLup09C51ZREEmG5fRo4A_MGVkCGyMd3kyuEkKz6J86GRQEkuZLUgx)
35. [speciesmonitoring.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGTmhoeBDrJggU6KUgtMapW6xly3Lp_z9spLT-q0fUcWpkD_MVAaQeljYzUQtTYaWkhHMXeIGJYd-ZIZtCXR6DQFT4XwufyQbLIbIHVYqbspN2ohdw_oFJn3CcckNUhpE8=)
36. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEZ9KDamy9SAjBSXJdEQ2XZM4qhxHCJ4ayVO-x1w3JPxCW_NPDoOcJUBcF3WtjHRIMY0UMluU04FrLs5QlQIcPo7ibSxn5WmzNgEGxWtYlD446S7pmqFFiefLLitvkf_sbYgmOAots1kJ4gSeTKR8rtY_tnSu_cbgjzttAPD1KuPair-WMB2ioLlj-iulum_Nif4pKk0_xsYfMqUkFqh2Ll6H7piBD5mk7zkI6gyWk=)
37. [nhm.ac.uk](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFwsGdrrDcSPdKXJz-wn1hsmGqT4sLDI1UQOjVdxKIvglnko-WVuHIQMj8YuDEnawhgGpgMR73QnvFtO3cL4voL3HuxD2mAqHCrKq3_vdivgQOiXT2GPs_Kd7jvF3djVAI2qQhu_Z6U8A==)
38. [nhm.ac.uk](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGmEAFx_V6n0ZYtIF7IJBSHSFCnYACoLK0ak-S2JTm3j10MI4uDYa0Q-0z-bWHz14gbNGsTR9VCRi9PLT5owOAHDxvVUm-JN3EFBJjjjIg3fLrCTL_uVbGGfek96RQaxJL0AHiC47Ng)
39. [nasa.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEVPcQOQvXbUBD5h55T3AtCBTyQKR5s49_AmSnaZOrLeFkZdcUqUWOb2yw-ASAgThfk8eptsxGgQL_Q022ajG-CzVepu8YbesK2oZSepFLHuMq8Yqg3wQ==)
40. [nasa.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG7a0Iw7Y2kBZOPQhxY1G4Q9AUuxAkMlrqWrR1ABfqrKJ7LjsdeaIEn4j4ilXWuM2FQgdpWrXlLU0p_cxceZv7V2ddgNArdZaY1hbe4iKimrIAH0V9KFDZhcJpYfzT_c0PB1j_JctVvHlYWpkAJV2K3ep1ZriXyxUZwTL_6SRTRxah4Qcp16UKTORrt7N0RAMrqsmE-_00E_zZGHYbmYg==)
41. [nasa.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEa6UWdsEmo7qhUsnC4Y53jET3BZinrGYyVEyoBoXnhPlrgAZNPsqvEyKlWNHyPVikDqV1eHwH_RiIGJLBZGmC7nPL3HPIVSEiLz0eUx-G1MJSMHZj8NN3ADF2kNXoEp-m9Ohr_FeiEnw==)
42. [nasa.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGuX_fYFb-xncTgHklcWfmuzphg7n63OKljg2lA4FM6NtBA54eAysGf3Eqg3jgRn8-zkozNvzo7qLRm47Vx_wpiok6SHHzsBwN3CovFmT9k1FgVfRETVB4dgAkcijc0pV8bb7hpt6EFxnUXLbDSIgQ4MoqPKo-Y9WBgzweBRHdGGfRCOLwPeYS7fEE9wZTpBwUER5p3jMXmFgYkJVDJ3Es=)
43. [unl.pt](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGWca3Hvc_eZKFLHQqLOv4tXxVlrVgPldE0J12xaqhGeuA1AQdhW3mFTsDWjtTncdgGke8R3EZO71qZP_LwLMCX9bWzDDDqTu-95alsuwqeARlVh6jQo2UQrinbcp6FhNZ67vD7PMbSQtbSa-e2jRBcgOJUnwAddJvoxKkE59XAnyz5)
44. [plos.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEDteaoGzmVm1uHVkeE71o7whLZ3lS11kb_axZ-xef47V8cm6RwQ6pr8uaDDYcO_wBFEDLMOzMiZomkz0DvYFd0TfM-8y3U7av1J3ELZZvnuSrDfn9wYjKeOAmxtryZVzapoZveNBJEDAOGD-o1AI6ZYlnM9F6j_S3FnEEQ2tKz)
45. [nerc.ac.uk](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEnsDnYZrCJ8I-MhJO0RKEWoFtn1dOOxnCs_KBV1fN0ArkgSEprpDHd_xwovm4LryStqVZsPMs7nw4qDqm9Qy-EWgk78cA-1GNANODkhMUM244DmEXweOvdEf0z5iW37ZTfHwMMyMG9r0sGAZp1fA==)
46. [researchgate.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHSWllY1RcHLiH9QUdDYnyyvGN4EoBf3jhchtxpAJw8fwdkhuLZY97EF8e6eWblYusGFFzcQ5iFS_qKQhwNpYd2u4r9sHJAC97mK8E2_MgHLW-629oXA5b5rDHX846meUNQXzsNlfKVloRlvI3-xQZqGi2-v5NrNiZWgAnJEgmZdN7MGIb7nvX5P8koZmKDxkj-ayvt)
47. [protectedplanet.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQENRa7lYasTYDmzXB5br0KpP1t503Y0Z_-wm2rF6tYqAI__PW4NRyxlZVMb64fAs4GK0aYK6RMgVRIh2zlkUMaGWEa7kB6BefDLmaVLyEFv1WX97CS7c5REy0zEBxh8Gbw=)
