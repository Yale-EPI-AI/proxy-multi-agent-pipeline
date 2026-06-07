# EPI Proxy Discovery Knowledge Graph — Summary Report

## Graph Overview

- **Total nodes**: 201
- **Total edges**: 859
- **Indicators**: 67
- **Proxy hypotheses**: 65
- **Data sources**: 55
- **Indicators with proxies**: 5
- **Indicators without proxies**: 62

## Indicator Coverage

### Indicators with Proxy Hypotheses

| TLA | Indicator | Category | Total | Confirmed | Partial | Inconclusive | Rejected | Inferred |
|-----|-----------|----------|-------|-----------|---------|--------------|----------|----------|
| OEB | Ozone Exposure in KBAs | AirPollution | 16 | 3 | 2 | 2 | 3 | 0 |
| WRR | Waste recovery rate | WasteManagement | 15 | 4 | 5 | 0 | 1 | 0 |
| UWD | Unsafe drinking water health burden | WaterQuality | 15 | 4 | 5 | 1 | 0 | 0 |
| SPI | Species Protection Index | Biodiversity | 11 | 2 | 5 | 0 | 3 | 0 |
| PHL | Protected Human Area | Biodiversity | 8 | 0 | 7 | 0 | 1 | 2 |

### Coverage Gaps (62 indicators with no proxies)

- **Agriculture**: PRS, PSU, RCY, SNM
- **AirPollution**: NXA, OEC, SDA
- **AirQuality**: COE, HFD, HFX, HPE, NOD, NOE, OZD, OZE, SOE, VOE
- **Biodiversity**: BER, MHP, MKP, MPE, PAE, PAR, RLI, SHI, TBN, TKP
- **Climate**: BCA, CBP, CDA, CDF, CHA, FGA, GHA, GHI, GHN, GHP, GTI, GTP, LUF, NDA
- **EcoSvcs**: FCL, FLI, IFL, PFL, TCG
- **Fisheries**: BTO, BTZ, FCD, FSS, RMS
- **HeavyMetals**: LED, LEX
- **WasteManagement**: SMW, WPC
- **WaterQuality**: USD, USX, UWX
- **WaterResources**: WWC, WWG, WWR, WWT

## Reasoning Results

### Cross-Indicator Candidates (129)

- SPI-H01 → MKP (same_category, confidence=0.60)
- SPI-H01 → MHP (same_category, confidence=0.60)
- SPI-H01 → MPE (same_category, confidence=0.60)
- SPI-H01 → BER (same_category, confidence=0.60)
- SPI-H01 → PAE (same_category, confidence=0.60)
- SPI-H01 → PHL (same_category, confidence=0.60)
- SPI-H01 → TBN (same_category, confidence=0.60)
- SPI-H01 → TKP (same_category, confidence=0.60)
- SPI-H05 → MKP (same_category, confidence=0.60)
- SPI-H05 → MHP (same_category, confidence=0.60)
- SPI-H05 → MPE (same_category, confidence=0.60)
- SPI-H05 → BER (same_category, confidence=0.60)
- SPI-H05 → PAE (same_category, confidence=0.60)
- SPI-H05 → PHL (same_category, confidence=0.60)
- SPI-H05 → TBN (same_category, confidence=0.60)
- SPI-H05 → TKP (same_category, confidence=0.60)
- UWD-H06 → USX (same_category, confidence=0.60)
- UWD-H06 → UWX (same_category, confidence=0.60)
- UWD-H07 → USX (same_category, confidence=0.60)
- UWD-H07 → UWX (same_category, confidence=0.60)
- ... and 109 more

### Direction-Observation Mismatches (1)

- **PHL**: PHL-H08 — hypothesized negative but observed r=0.238

### Same-Direction Verdict Conflicts (37)

- **OEB**: OEB-H04 vs OEB-H05 (both positive, but conflicting verdicts)
- **OEB**: OEB-H10 vs OEB-H05 (both positive, but conflicting verdicts)
- **OEB**: OEB-H04 vs OEB-H07 (both positive, but conflicting verdicts)
- **OEB**: OEB-H10 vs OEB-H07 (both positive, but conflicting verdicts)
- **PHL**: PHL-H01 vs PHL-H09 (both negative, but conflicting verdicts)
- **PHL**: PHL-H02 vs PHL-H09 (both negative, but conflicting verdicts)
- **PHL**: PHL-H03 vs PHL-H09 (both negative, but conflicting verdicts)
- **PHL**: PHL-H04 vs PHL-H09 (both negative, but conflicting verdicts)
- **PHL**: PHL-H07 vs PHL-H09 (both negative, but conflicting verdicts)
- **PHL**: PHL-H08 vs PHL-H09 (both negative, but conflicting verdicts)
- **SPI**: SPI-H04 vs SPI-H02 (both positive, but conflicting verdicts)
- **SPI**: SPI-H07 vs SPI-H02 (both positive, but conflicting verdicts)
- **SPI**: SPI-H08 vs SPI-H02 (both positive, but conflicting verdicts)
- **SPI**: SPI-H10 vs SPI-H02 (both positive, but conflicting verdicts)
- **SPI**: SPI-H04 vs SPI-H03 (both positive, but conflicting verdicts)
- **SPI**: SPI-H07 vs SPI-H03 (both positive, but conflicting verdicts)
- **SPI**: SPI-H08 vs SPI-H03 (both positive, but conflicting verdicts)
- **SPI**: SPI-H10 vs SPI-H03 (both positive, but conflicting verdicts)
- **SPI**: SPI-H06 vs SPI-H09 (both negative, but conflicting verdicts)
- **WRR**: WRR-H01 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H02 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H03 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H06 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H09 vs WRR-H10 (both positive, but conflicting verdicts)
- **OEB**: OEB-H03 vs OEB-H05 (both positive, but conflicting verdicts)
- **OEB**: OEB-H06 vs OEB-H05 (both positive, but conflicting verdicts)
- **OEB**: OEB-H03 vs OEB-H07 (both positive, but conflicting verdicts)
- **OEB**: OEB-H06 vs OEB-H07 (both positive, but conflicting verdicts)
- **OEB**: OEB-H09 vs OEB-H08 (both negative, but conflicting verdicts)
- **SPI**: SPI-H01 vs SPI-H02 (both positive, but conflicting verdicts)
- **SPI**: SPI-H05 vs SPI-H02 (both positive, but conflicting verdicts)
- **SPI**: SPI-H01 vs SPI-H03 (both positive, but conflicting verdicts)
- **SPI**: SPI-H05 vs SPI-H03 (both positive, but conflicting verdicts)
- **WRR**: WRR-H04 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H05 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H07 vs WRR-H10 (both positive, but conflicting verdicts)
- **WRR**: WRR-H08 vs WRR-H10 (both positive, but conflicting verdicts)

### Confounder Warnings (6)

- OEB-H13: mechanism mentions confounder keywords, weak/missing partial correlation
- SPI-H11: mechanism mentions confounder keywords, weak/missing partial correlation
- UWD-H02: mechanism mentions confounder keywords, weak/missing partial correlation
- SPI-H06: mechanism mentions confounder keywords, weak/missing partial correlation
- SPI-H07: mechanism mentions confounder keywords, weak/missing partial correlation
- SPI-H04: mechanism mentions confounder keywords, weak/missing partial correlation

### Shared Source Opportunities (39)

- Source `waqi` → indicator OEC
- Source `waqi` → indicator NXA
- Source `waqi` → indicator SDA
- Source `oica` → indicator OEC
- Source `oica` → indicator NXA
- Source `oica` → indicator SDA
- Source `nasa` → indicator OEC
- Source `nasa` → indicator NXA
- Source `nasa` → indicator SDA
- Source `geo_bon,_ipbes` → indicator PAR
- Source `geo_bon,_ipbes` → indicator SHI
- Source `geo_bon,_ipbes` → indicator RLI
- Source `world_bank` → indicator PAR
- Source `world_bank` → indicator SHI
- Source `world_bank` → indicator RLI
- Source `unicef/who` → indicator USD
- Source `unicef/who` → indicator HFD
- Source `unicef/who` → indicator WWT
- Source `unicef/who` → indicator WWC
- Source `unicef/who` → indicator WWG
- ... and 19 more
