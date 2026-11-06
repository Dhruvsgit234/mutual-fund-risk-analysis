"""Pure metric functions (no I/O) so they can be unit-tested against known answers."""
import numpy as np
import pandas as pd

PPY = 252


def daily_rf(rf_annual: float, ppy: int = PPY) -> float:
    return (1.0 + rf_annual) ** (1.0 / ppy) - 1.0


def returns_from_nav(nav: pd.Series) -> pd.Series:
    return nav.pct_change().dropna()


def cagr(nav: pd.Series) -> float:
    nav = nav.dropna()
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0:
        return np.nan
    return (nav.iloc[-1] / nav.iloc[0]) ** (365.25 / days) - 1.0


def annual_vol(r: pd.Series, ppy: int = PPY) -> float:
    return float(r.std(ddof=1) * np.sqrt(ppy))


def sharpe(r: pd.Series, rf_annual: float, ppy: int = PPY) -> float:
    ex = r - daily_rf(rf_annual, ppy)
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(ppy)) if sd > 0 else np.nan


def sortino(r: pd.Series, rf_annual: float, ppy: int = PPY) -> float:
    ex = r - daily_rf(rf_annual, ppy)
    downside = np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2))
    return float(ex.mean() / downside * np.sqrt(ppy)) if downside > 0 else np.nan


def drawdown_series(nav: pd.Series) -> pd.Series:
    return nav / nav.cummax() - 1.0


def max_drawdown_detail(nav: pd.Series) -> dict:
    dd = drawdown_series(nav)
    trough = dd.idxmin()
    peak = nav.loc[:trough].idxmax()
    after = nav.loc[trough:]
    recovered = after[after >= nav.loc[peak]]
    rec_date = recovered.index[0] if len(recovered) else pd.NaT
    return {
        "max_drawdown": float(dd.min()),
        "peak_date": peak,
        "trough_date": trough,
        "recovery_date": rec_date,
        "days_peak_to_trough": int((trough - peak).days),
        "days_to_recover": (int((rec_date - trough).days) if pd.notna(rec_date) else np.nan),
    }


def capture_and_beta(fund_r: pd.Series, bench_r: pd.Series, rf_annual: float, ppy: int = PPY) -> dict:
    """CAPM beta/alpha on excess returns plus tracking error, info ratio, capture ratios.
    Inputs are daily returns; they are aligned on shared dates first."""
    a = pd.concat([fund_r.rename("f"), bench_r.rename("b")], axis=1, join="inner").dropna()
    keys = ["beta", "alpha", "r2", "tracking_error", "info_ratio", "up_capture", "down_capture"]
    if len(a) < 30:
        return {k: np.nan for k in keys}
    rf_d = daily_rf(rf_annual, ppy)
    ef, eb = a["f"] - rf_d, a["b"] - rf_d
    beta = ef.cov(eb) / eb.var(ddof=1)
    alpha_daily = ef.mean() - beta * eb.mean()
    corr = a["f"].corr(a["b"])
    active = a["f"] - a["b"]
    te = active.std(ddof=1) * np.sqrt(ppy)
    up, down = a[a["b"] > 0], a[a["b"] < 0]
    return {
        "beta": float(beta),
        "alpha": float(alpha_daily * ppy),
        "r2": float(corr ** 2),
        "tracking_error": float(te),
        "info_ratio": float(active.mean() * ppy / te) if te > 0 else np.nan,
        "up_capture": float(up["f"].mean() / up["b"].mean()) if len(up) else np.nan,
        "down_capture": float(down["f"].mean() / down["b"].mean()) if len(down) else np.nan,
    }


def calendar_year_returns(nav: pd.Series) -> pd.DataFrame:
    """Return per calendar year (last NAV of year vs last NAV of prior year).
    The final year is flagged partial if the series ends before 20 Dec."""
    nav = nav.dropna()
    year_end = nav.groupby(nav.index.year).last()
    rets = year_end.pct_change().dropna()
    out = pd.DataFrame({"year": rets.index, "return": rets.values})
    last = nav.index[-1]
    out["is_partial"] = (out["year"] == last.year) & ((last.month, last.day) < (12, 20))
    return out
