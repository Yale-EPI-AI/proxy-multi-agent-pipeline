"""Paths, API keys, constants, and configuration for the EPI proxy discovery pipeline."""

from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EPI_DATA_DIR = PROJECT_ROOT / "docs" / "EPI2024_Work"
RAW_DIR = EPI_DATA_DIR / "Raw"
INPUTS_DIR = EPI_DATA_DIR / "Inputs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

DB_PATH = OUTPUTS_DIR / "epi_data.duckdb"

MASTER_VARIABLE_LIST = INPUTS_DIR / "master_variable_list.csv"
MASTER_FILE = INPUTS_DIR / "MasterFile.csv"
COUNTRY_DICTIONARY = INPUTS_DIR / "cdictionary_expanded.csv"
ATTRIBUTES_FILE = INPUTS_DIR / "Attributes.csv"

# ── API Keys ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Model Names ────────────────────────────────────────────────────────────────
CLAUDE_VERIFICATION_MODEL = "claude-sonnet-4-6"
CLAUDE_VALIDATION_MODEL = "claude-haiku-4-5-20251001"
VALIDATION_MAX_TOKENS = 2048

# ── EPI Data Constants ─────────────────────────────────────────────────────────
MISSING_SENTINELS = {-9999, -8888, -7777}
CONTROL_VARIABLE_TLAS = ["GPC", "POP", "URB"]

# ── Verdict Thresholds ─────────────────────────────────────────────────────────
VERDICT_R_THRESHOLD = 0.3          # |r| must exceed this for "confirmed"
VERDICT_P_THRESHOLD = 0.05         # p must be below this for significance
VERDICT_P_BORDERLINE = 0.10        # p between 0.05-0.10 = "inconclusive"
VERDICT_MIN_N = 20                 # minimum observations for any verdict
PARTIAL_CORR_MIN_N = 30            # minimum observations for partial correlation
VERDICT_R_STRONG = 0.5             # |r| threshold for confirmed without partial corr
VERDICT_P_STRICT = 0.01            # p threshold for confirmed without partial corr

# ── Inclusion Criteria Thresholds ─────────────────────────────────────────────
INCLUSION_BINDING_MODE = "advisory"       # "advisory" | "soft_gate" | "hard_gate"
INCLUSION_MIN_COUNTRIES = 80              # spatial completeness threshold
INCLUSION_MIN_YEARS = 3                   # temporal completeness threshold
INCLUSION_RECENCY_CUTOFF = 2018           # data must include years >= this
INCLUSION_CRITICAL_CRITERIA = [           # criteria that trigger hard_gate rejection
    "spatial_completeness",
    "open_access",
    # `documented_methodology` is DELIBERATELY excluded — the 2026-04-13 plan
    # broadened acceptance to include satellite/sensor/digital-behavioral
    # sources, making methodology provenance an advisory quality hint rather
    # than a hard gate. Spatial completeness and open access remain the only
    # two essentials: a proxy must cover enough countries and be reproducible.
    # `signal_independence` is also advisory (see schemas.py comment).
]
INCLUSION_SOFT_GATE_MIN_SCORE = 6         # min criteria_met (of 10) to avoid verdict downgrade

# ── Discovery Agent ──────────────────────────────────────────────────────────
CLAUDE_DISCOVERY_MODEL = "claude-sonnet-4-6"
DISCOVERY_MAX_TOOL_CALLS = 80

# ── Pipeline Defaults ──────────────────────────────────────────────────────────
MAX_HYPOTHESES = 10
API_RETRY_ATTEMPTS = 3
API_RETRY_BACKOFF = 2.0
