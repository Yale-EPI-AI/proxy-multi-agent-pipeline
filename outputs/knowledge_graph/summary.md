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

### Direction Conflicts (101)

- **OEB**: OEB-H03 (positive) vs OEB-H09 (negative)
- **OEB**: OEB-H04 (positive) vs OEB-H09 (negative)
- **OEB**: OEB-H06 (positive) vs OEB-H09 (negative)
- **OEB**: OEB-H09 (negative) vs OEB-H10 (positive)
- **OEB**: OEB-H03 (positive) vs OEB-H11 (nonlinear)
- **OEB**: OEB-H04 (positive) vs OEB-H11 (nonlinear)
- **OEB**: OEB-H06 (positive) vs OEB-H11 (nonlinear)
- **OEB**: OEB-H09 (negative) vs OEB-H11 (nonlinear)
- **OEB**: OEB-H10 (positive) vs OEB-H11 (nonlinear)
- **OEB**: OEB-H09 (negative) vs OEB-H12 (positive)
- **OEB**: OEB-H11 (nonlinear) vs OEB-H12 (positive)
- **OEB**: OEB-H09 (negative) vs OEB-H13 (positive)
- **OEB**: OEB-H11 (nonlinear) vs OEB-H13 (positive)
- **OEB**: OEB-H03 (positive) vs OEB-H14 (negative)
- **OEB**: OEB-H04 (positive) vs OEB-H14 (negative)
- **OEB**: OEB-H06 (positive) vs OEB-H14 (negative)
- **OEB**: OEB-H10 (positive) vs OEB-H14 (negative)
- **OEB**: OEB-H11 (nonlinear) vs OEB-H14 (negative)
- **OEB**: OEB-H12 (positive) vs OEB-H14 (negative)
- **OEB**: OEB-H13 (positive) vs OEB-H14 (negative)
- **OEB**: OEB-H09 (negative) vs OEB-H15 (positive)
- **OEB**: OEB-H11 (nonlinear) vs OEB-H15 (positive)
- **OEB**: OEB-H14 (negative) vs OEB-H15 (positive)
- **OEB**: OEB-H03 (positive) vs OEB-H16 (negative)
- **OEB**: OEB-H04 (positive) vs OEB-H16 (negative)
- **OEB**: OEB-H06 (positive) vs OEB-H16 (negative)
- **OEB**: OEB-H10 (positive) vs OEB-H16 (negative)
- **OEB**: OEB-H11 (nonlinear) vs OEB-H16 (negative)
- **OEB**: OEB-H12 (positive) vs OEB-H16 (negative)
- **OEB**: OEB-H13 (positive) vs OEB-H16 (negative)
- **OEB**: OEB-H15 (positive) vs OEB-H16 (negative)
- **PHL**: PHL-H01 (negative) vs PHL-H05 (positive)
- **PHL**: PHL-H02 (negative) vs PHL-H05 (positive)
- **PHL**: PHL-H03 (negative) vs PHL-H05 (positive)
- **PHL**: PHL-H04 (negative) vs PHL-H05 (positive)
- **PHL**: PHL-H05 (positive) vs PHL-H07 (negative)
- **PHL**: PHL-H05 (positive) vs PHL-H08 (negative)
- **SPI**: SPI-H01 (positive) vs SPI-H06 (negative)
- **SPI**: SPI-H04 (positive) vs SPI-H06 (negative)
- **SPI**: SPI-H05 (positive) vs SPI-H06 (negative)
- **SPI**: SPI-H06 (negative) vs SPI-H07 (positive)
- **SPI**: SPI-H06 (negative) vs SPI-H08 (positive)
- **SPI**: SPI-H06 (negative) vs SPI-H10 (positive)
- **SPI**: SPI-H06 (negative) vs SPI-H11 (positive)
- **UWD**: UWD-H01 (positive) vs UWD-H06 (negative)
- **UWD**: UWD-H02 (positive) vs UWD-H06 (negative)
- **UWD**: UWD-H03 (positive) vs UWD-H06 (negative)
- **UWD**: UWD-H04 (positive) vs UWD-H06 (negative)
- **UWD**: UWD-H05 (positive) vs UWD-H06 (negative)
- **UWD**: UWD-H06 (negative) vs UWD-H07 (positive)
- **UWD**: UWD-H06 (negative) vs UWD-H09 (positive)
- **UWD**: UWD-H01 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H02 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H03 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H04 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H05 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H07 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H09 (positive) vs UWD-H10 (negative)
- **UWD**: UWD-H01 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H02 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H03 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H04 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H05 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H07 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H09 (positive) vs UWD-H11 (negative)
- **UWD**: UWD-H06 (negative) vs UWD-H12 (positive)
- **UWD**: UWD-H10 (negative) vs UWD-H12 (positive)
- **UWD**: UWD-H11 (negative) vs UWD-H12 (positive)
- **UWD**: UWD-H06 (negative) vs UWD-H13 (positive)
- **UWD**: UWD-H10 (negative) vs UWD-H13 (positive)
- **UWD**: UWD-H11 (negative) vs UWD-H13 (positive)
- **UWD**: UWD-H06 (negative) vs UWD-H14 (positive)
- **UWD**: UWD-H10 (negative) vs UWD-H14 (positive)
- **UWD**: UWD-H11 (negative) vs UWD-H14 (positive)
- **UWD**: UWD-H06 (negative) vs UWD-H15 (positive)
- **UWD**: UWD-H10 (negative) vs UWD-H15 (positive)
- **UWD**: UWD-H11 (negative) vs UWD-H15 (positive)
- **WRR**: WRR-H01 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H02 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H03 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H04 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H05 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H06 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H07 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H08 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H09 (positive) vs WRR-H11 (negative)
- **WRR**: WRR-H11 (negative) vs WRR-H12 (positive)
- **WRR**: WRR-H11 (negative) vs WRR-H13 (positive)
- **WRR**: WRR-H11 (negative) vs WRR-H14 (positive)
- **WRR**: WRR-H01 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H02 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H03 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H04 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H05 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H06 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H07 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H08 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H09 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H12 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H13 (positive) vs WRR-H15 (negative)
- **WRR**: WRR-H14 (positive) vs WRR-H15 (negative)

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
