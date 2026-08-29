"""ISO3/ISO2/M49 country code mapping utilities.

NASA POWER uses ISO2 codes, FAOSTAT uses M49 numeric codes.
Mappings are built from the EPI country dictionary + pycountry as fallback.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd

try:
    import pycountry
except ImportError:
    pycountry = None

from epi_proxy.config import COUNTRY_DICTIONARY, MASTER_FILE

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_mappings() -> tuple[dict[str, str], dict[str, int], dict[int, str]]:
    """Build all code mapping dicts from EPI data + pycountry.

    Returns (iso3_to_iso2, iso3_to_m49, m49_to_iso3).
    """
    iso3_to_iso2: dict[str, str] = {}
    iso3_to_m49: dict[str, int] = {}
    m49_to_iso3: dict[int, str] = {}

    # Load M49 codes from MasterFile (code column = M49 numeric)
    try:
        mf = pd.read_csv(MASTER_FILE)
        for _, row in mf.iterrows():
            iso3 = str(row["iso"]).strip()
            code = int(row["code"])
            iso3_to_m49[iso3] = code
            m49_to_iso3[code] = iso3
    except Exception as exc:
        logger.warning("Could not load MasterFile for M49 mapping: %s", exc)

    # Build ISO3→ISO2 from pycountry (most reliable source)
    if pycountry:
        for c in pycountry.countries:
            iso3 = getattr(c, "alpha_3", None)
            iso2 = getattr(c, "alpha_2", None)
            if iso3 and iso2:
                iso3_to_iso2[iso3] = iso2
            # Fill M49 gaps from pycountry
            numeric = getattr(c, "numeric", None)
            if iso3 and numeric:
                code = int(numeric)
                iso3_to_m49.setdefault(iso3, code)
                m49_to_iso3.setdefault(code, iso3)
    else:
        logger.warning("pycountry not installed — ISO2 mapping will be incomplete")

    return iso3_to_iso2, iso3_to_m49, m49_to_iso3


def iso3_to_iso2(iso3: str) -> str | None:
    """Convert ISO3 code to ISO2 (e.g. 'USA' -> 'US'). Returns None if unknown."""
    mapping, _, _ = _build_mappings()
    return mapping.get(iso3.upper())


def iso3_to_m49(iso3: str) -> int | None:
    """Convert ISO3 code to M49 numeric (e.g. 'USA' -> 840). Returns None if unknown."""
    _, mapping, _ = _build_mappings()
    return mapping.get(iso3.upper())


def m49_to_iso3(m49: int) -> str | None:
    """Convert M49 numeric code to ISO3 (e.g. 840 -> 'USA'). Returns None if unknown."""
    _, _, mapping = _build_mappings()
    return mapping.get(m49)


@lru_cache(maxsize=1)
def get_country_centroids() -> dict[str, tuple[float, float]]:
    """Return {iso3: (latitude, longitude)} for all EPI countries.

    Uses pycountry + a small built-in table for common countries.
    NASA POWER's point API needs lat/lon per country.
    """
    # Built-in centroids for EPI countries (approximate capital/centroid coordinates)
    # This covers the most common cases; pycountry doesn't include coordinates
    centroids: dict[str, tuple[float, float]] = {}

    try:
        # Try to load from cdictionary_expanded if it has lat/lon columns
        df = pd.read_csv(COUNTRY_DICTIONARY)
        if "latitude" in df.columns and "longitude" in df.columns:
            for _, row in df.iterrows():
                iso = str(row.get("iso", "")).strip()
                if iso and len(iso) == 3:
                    centroids[iso] = (float(row["latitude"]), float(row["longitude"]))
            if centroids:
                return centroids
    except Exception:
        pass

    # Fallback: use a static mapping of ~200 country centroids
    # Generated from Natural Earth / CIA World Factbook
    _CENTROIDS = {
        "AFG": (33.9, 67.7), "ALB": (41.2, 20.2), "DZA": (28.0, 3.0),
        "AND": (42.5, 1.5), "AGO": (-12.5, 18.5), "ATG": (17.1, -61.8),
        "ARG": (-34.0, -64.0), "ARM": (40.0, 45.0), "AUS": (-25.0, 135.0),
        "AUT": (47.3, 13.3), "AZE": (40.4, 49.9), "BHS": (24.2, -76.0),
        "BHR": (26.0, 50.5), "BGD": (24.0, 90.0), "BRB": (13.2, -59.5),
        "BLR": (53.0, 28.0), "BEL": (50.8, 4.0), "BLZ": (17.2, -88.7),
        "BEN": (9.3, 2.3), "BTN": (27.5, 90.5), "BOL": (-17.0, -65.0),
        "BIH": (44.0, 18.0), "BWA": (-22.3, 24.7), "BRA": (-10.0, -55.0),
        "BRN": (4.5, 114.7), "BGR": (42.7, 25.5), "BFA": (13.0, -1.5),
        "BDI": (-3.5, 30.0), "CPV": (15.0, -23.6), "KHM": (13.0, 105.0),
        "CMR": (6.0, 12.5), "CAN": (56.0, -106.0), "CAF": (7.0, 21.0),
        "TCD": (15.0, 19.0), "CHL": (-30.0, -71.0), "CHN": (35.0, 105.0),
        "COL": (4.0, -72.0), "COM": (-12.2, 44.2), "COG": (-1.0, 15.0),
        "COD": (-2.5, 23.5), "CRI": (10.0, -84.0), "CIV": (7.5, -5.5),
        "HRV": (45.2, 15.5), "CUB": (22.0, -79.5), "CYP": (35.0, 33.0),
        "CZE": (49.8, 15.5), "DNK": (56.0, 10.0), "DJI": (11.5, 43.1),
        "DMA": (15.4, -61.4), "DOM": (19.0, -70.7), "ECU": (-2.0, -77.5),
        "EGY": (27.0, 30.0), "SLV": (13.8, -88.9), "GNQ": (1.5, 10.0),
        "ERI": (15.0, 39.0), "EST": (59.0, 26.0), "SWZ": (-26.5, 31.5),
        "ETH": (8.0, 38.0), "FJI": (-18.0, 178.0), "FIN": (64.0, 26.0),
        "FRA": (46.0, 2.0), "GAB": (-1.0, 11.8), "GMB": (13.5, -15.4),
        "GEO": (42.0, 43.5), "DEU": (51.0, 9.0), "GHA": (8.0, -2.0),
        "GRC": (39.0, 22.0), "GRD": (12.1, -61.7), "GTM": (15.5, -90.2),
        "GIN": (11.0, -10.0), "GNB": (12.0, -15.0), "GUY": (5.0, -59.0),
        "HTI": (19.0, -72.4), "HND": (15.0, -86.5), "HUN": (47.0, 20.0),
        "ISL": (65.0, -18.0), "IND": (20.0, 77.0), "IDN": (-5.0, 120.0),
        "IRN": (32.0, 53.0), "IRQ": (33.0, 44.0), "IRL": (53.0, -8.0),
        "ISR": (31.5, 34.8), "ITA": (42.8, 12.8), "JAM": (18.2, -77.5),
        "JPN": (36.0, 138.0), "JOR": (31.0, 36.0), "KAZ": (48.0, 68.0),
        "KEN": (1.0, 38.0), "KIR": (1.4, 173.0), "PRK": (40.0, 127.0),
        "KOR": (37.0, 127.5), "KWT": (29.5, 47.5), "KGZ": (41.0, 75.0),
        "LAO": (18.0, 105.0), "LVA": (57.0, 25.0), "LBN": (33.8, 35.8),
        "LSO": (-29.5, 28.5), "LBR": (6.5, -9.5), "LBY": (25.0, 17.0),
        "LIE": (47.2, 9.5), "LTU": (56.0, 24.0), "LUX": (49.8, 6.2),
        "MDG": (-20.0, 47.0), "MWI": (-13.5, 34.0), "MYS": (2.5, 112.5),
        "MDV": (3.2, 73.2), "MLI": (17.0, -4.0), "MLT": (35.9, 14.4),
        "MHL": (7.1, 171.2), "MRT": (20.0, -10.0), "MUS": (-20.3, 57.6),
        "MEX": (23.0, -102.0), "FSM": (6.9, 158.2), "MDA": (47.0, 29.0),
        "MCO": (43.7, 7.4), "MNG": (46.0, 105.0), "MNE": (42.5, 19.3),
        "MAR": (32.0, -5.0), "MOZ": (-18.3, 35.0), "MMR": (22.0, 98.0),
        "NAM": (-22.0, 17.0), "NRU": (-0.5, 166.9), "NPL": (28.0, 84.0),
        "NLD": (52.5, 5.8), "NZL": (-42.0, 174.0), "NIC": (13.0, -85.0),
        "NER": (16.0, 8.0), "NGA": (10.0, 8.0), "MKD": (41.5, 21.7),
        "NOR": (62.0, 10.0), "OMN": (21.0, 57.0), "PAK": (30.0, 70.0),
        "PLW": (7.5, 134.6), "PAN": (9.0, -80.0), "PNG": (-6.0, 147.0),
        "PRY": (-23.0, -58.0), "PER": (-10.0, -76.0), "PHL": (13.0, 122.0),
        "POL": (52.0, 20.0), "PRT": (39.5, -8.0), "QAT": (25.3, 51.2),
        "ROU": (46.0, 25.0), "RUS": (60.0, 100.0), "RWA": (-2.0, 30.0),
        "KNA": (17.3, -62.7), "LCA": (13.9, -61.0), "VCT": (13.2, -61.2),
        "WSM": (-13.6, -172.3), "SMR": (43.8, 12.4), "STP": (1.0, 7.0),
        "SAU": (24.0, 45.0), "SEN": (14.5, -14.3), "SRB": (44.0, 21.0),
        "SYC": (-4.7, 55.5), "SLE": (8.5, -12.0), "SGP": (1.4, 103.8),
        "SVK": (48.7, 19.7), "SVN": (46.1, 14.8), "SLB": (-8.0, 159.0),
        "SOM": (5.0, 46.0), "ZAF": (-29.0, 24.0), "SSD": (7.0, 30.0),
        "ESP": (40.0, -4.0), "LKA": (7.0, 81.0), "SDN": (15.0, 30.0),
        "SUR": (4.0, -56.0), "SWE": (62.0, 15.0), "CHE": (47.0, 8.0),
        "SYR": (35.0, 38.0), "TWN": (24.0, 121.0), "TJK": (39.0, 71.0),
        "TZA": (-6.0, 35.0), "THA": (15.0, 100.0), "TLS": (-8.8, 126.0),
        "TGO": (8.0, 1.2), "TON": (-20.0, -175.0), "TTO": (10.4, -61.3),
        "TUN": (34.0, 9.0), "TUR": (39.0, 35.0), "TKM": (40.0, 60.0),
        "TUV": (-8.0, 178.0), "UGA": (1.0, 32.0), "UKR": (49.0, 32.0),
        "ARE": (24.0, 54.0), "GBR": (54.0, -2.0), "USA": (38.0, -97.0),
        "URY": (-33.0, -56.0), "UZB": (41.0, 64.0), "VUT": (-16.0, 167.0),
        "VEN": (8.0, -66.0), "VNM": (16.0, 108.0), "YEM": (15.0, 48.0),
        "ZMB": (-15.0, 28.0), "ZWE": (-20.0, 30.0), "PSE": (32.0, 35.2),
        "XKX": (42.6, 21.0),
    }

    centroids.update(_CENTROIDS)
    return centroids
