"""Shared helpers: database connection, schema, XIRR, name matching."""
import sqlite3
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from scipy.optimize import brentq

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS fund_master (
    scheme_code   INTEGER PRIMARY KEY,
    scheme_name   TEXT NOT NULL,
    fund_house    TEXT,
    category      TEXT,
    plan          TEXT,
    role          TEXT,
    pair_code     INTEGER,
    first_nav_date TEXT,
    last_nav_date  TEXT,
    is_active     INTEGER
);
CREATE TABLE IF NOT EXISTS nav_daily (
    scheme_code INTEGER NOT NULL,
    date        TEXT NOT NULL,
    nav         REAL NOT NULL CHECK (nav > 0),
    PRIMARY KEY (scheme_code, date)
);
CREATE TABLE IF NOT EXISTS benchmark_daily (
    date   TEXT PRIMARY KEY,
    value  REAL NOT NULL CHECK (value > 0),
    source TEXT
);
CREATE TABLE IF NOT EXISTS data_quality (
    scheme_code INTEGER,
    issue       TEXT,
    date        TEXT,
    detail      TEXT
);
"""


def connect():
    """SQLite connection with a POW() function (not always compiled in)."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.create_function(
        "POW", 2,
        lambda a, b: None if a is None or b is None else float(a) ** float(b),
    )
    return conn


def xirr(cashflows, dates):
    """Annualised money-weighted return. dates: sequence of Timestamps/datetimes."""
    cfs = np.asarray(cashflows, dtype=float)
    if len(cfs) < 2 or not (cfs.min() < 0 < cfs.max()):
        return np.nan
    t0 = dates[0]
    years = np.array([(d - t0).days / 365.0 for d in dates])

    def f(rate):
        return np.sum(cfs / (1.0 + rate) ** years)

    try:
        return brentq(f, -0.99, 100.0)
    except ValueError:
        return np.nan


_DROP_TOKENS = {"direct", "regular", "plan", "growth", "option", "opt"}


def normalize_scheme_name(name: str) -> str:
    """'HDFC Flexi Cap Fund - Growth Option - Direct Plan' -> 'hdfc flexi cap fund'.
    Used to pair a Direct plan with its Regular twin."""
    n = name.lower()
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"[^a-z0-9& ]+", " ", n)
    tokens = [t for t in n.split() if t not in _DROP_TOKENS]
    return " ".join(tokens)


def load_nav_wide(conn, codes=None) -> pd.DataFrame:
    """Date x scheme_code matrix of NAVs (no forward fill)."""
    df = pd.read_sql_query("SELECT scheme_code, date, nav FROM nav_daily",
                           conn, parse_dates=["date"])
    if codes is not None:
        df = df[df["scheme_code"].isin(codes)]
    return df.pivot(index="date", columns="scheme_code", values="nav").sort_index()


def load_benchmark(conn) -> pd.Series:
    df = pd.read_sql_query("SELECT date, value FROM benchmark_daily ORDER BY date",
                           conn, parse_dates=["date"])
    return df.set_index("date")["value"]


def first_of_month_series(nav: pd.Series) -> pd.Series:
    """First available NAV in each calendar month (SIP instalment date)."""
    nav = nav.dropna()
    return nav.groupby([nav.index.year, nav.index.month]).head(1)


def sip_final_value(monthly_nav: np.ndarray, amount: float) -> float:
    """Invest `amount` at the start of every month; value at the last observation.
    monthly_nav has n+1 points: n instalments, valued at point n."""
    growth = monthly_nav[1:] / monthly_nav[:-1]
    v = 0.0
    for g in growth:
        v = (v + amount) * g
    return v
