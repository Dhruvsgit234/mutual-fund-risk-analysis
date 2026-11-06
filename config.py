"""Central settings. Change values here, not inside the scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
NAV_CACHE_DIR = RAW_DIR / "nav"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "mf.db"
SQL_DIR = ROOT / "sql"

# ---------------------------------------------------------------- universe
# Label -> scheme_category text used by AMFI/mfapi (compared in lower case).
# "Large & Mid Cap" is deliberately NOT matched by "Large Cap" (exact match).
CATEGORIES = {
    "Large Cap": "equity scheme - large cap fund",
    "Flexi Cap": "equity scheme - flexi cap fund",
    "Mid Cap": "equity scheme - mid cap fund",
}
FUNDS_PER_CATEGORY = 15
MIN_HISTORY_YEARS = 8          # a fund needs this much NAV history to be eligible
SELECTION_METHOD = "oldest"    # "oldest" or "random"
RANDOM_SEED = 42
ACTIVE_TOLERANCE_DAYS = 10     # last NAV must be this close to the newest date seen

# ---------------------------------------------------------------- benchmark
# Preferred: Nifty 50 TRI downloaded from niftyindices.com saved as a CSV with
# columns Date,TRI (date format dd-mm-yyyy or yyyy-mm-dd).
BENCHMARK_CSV = RAW_DIR / "nifty50_tri.csv"
# Fallback if the CSV is missing: a Nifty 50 index fund (Direct, Growth) from mfapi.
# It is net of the fund's small expense ratio, so it slightly understates the index.
BENCHMARK_PROXY_QUERY = "nifty 50 index"

# ---------------------------------------------------------------- finance assumptions
RISK_FREE_ANNUAL = 0.065       # ASSUMPTION: update with the average 91-day T-bill yield
TRADING_DAYS = 252
WINDOWS_YEARS = [3, 5, 7]      # evaluation windows for risk/return metrics
DATA_GAP_DAYS = 7              # gaps longer than this are logged as data-quality issues
SUSPICIOUS_DAILY_MOVE = 0.15   # |daily NAV change| above this is logged for review

# ---------------------------------------------------------------- SIP study
SIP_AMOUNT = 10_000
SIP_HORIZONS_YEARS = [3, 5]
EXPENSE_SENSITIVITY = [0.005, 0.010, 0.015]   # extra annual cost, as fractions
EXPENSE_STUDY_YEARS = 10

# ---------------------------------------------------------------- clustering
CORR_WINDOW_YEARS = 3
N_CLUSTERS = 6
NEAR_DUPLICATE_CORR = 0.97

# ---------------------------------------------------------------- LLM
LLM_MODEL = "claude-sonnet-5-5"
LLM_SUMMARY_WINDOW = 5
