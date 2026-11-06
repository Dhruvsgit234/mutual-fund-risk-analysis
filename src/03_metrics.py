"""STEP 3 - Risk/return metrics per fund and window, rolling returns, drawdowns.

Outputs (data/processed/):
  fact_metrics.csv          one row per fund x window (3Y/5Y/7Y)
  fact_rolling_returns.csv  month-end rolling 1Y / 3Y / 5Y returns (from SQL)
  fact_drawdown_weekly.csv  weekly drawdown curve per fund + benchmark
  fact_calendar_returns.csv calendar-year returns per fund + benchmark
All funds are compared over the SAME window end date, so numbers are comparable.
Run:  python src/03_metrics.py
"""
import numpy as np
import pandas as pd

import common
import config
import metrics_lib as m

TOL = pd.Timedelta(days=10)


def run_sql_file(conn, name):
    conn.executescript((config.SQL_DIR / name).read_text())


def slice_window(nav: pd.Series, end: pd.Timestamp, years: int):
    """Return the NAV slice for [end - years, end] or None if the fund lacks data."""
    start = end - pd.DateOffset(years=years)
    if nav.index[0] > start + TOL or nav.index[-1] < end - TOL:
        return None
    s = nav[(nav.index >= start) & (nav.index <= end)]
    return s if len(s) > 100 else None


def main():
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    conn = common.connect()
    run_sql_file(conn, "01_views.sql")
    run_sql_file(conn, "02_rolling_returns.sql")
    conn.commit()

    master = pd.read_sql_query(
        "SELECT * FROM fund_master WHERE role = 'selected' AND is_active = 1", conn)
    wide = common.load_nav_wide(conn, master["scheme_code"].tolist())
    bench = common.load_benchmark(conn)
    end = min(bench.index.max(), wide.index.max())
    print(f"{len(master)} active funds | common window end date: {end.date()}")

    rows = []
    for years in config.WINDOWS_YEARS:
        b_slice = bench[(bench.index >= end - pd.DateOffset(years=years)) & (bench.index <= end)]
        for _, f in master.iterrows():
            nav = wide[f["scheme_code"]].dropna()
            s = slice_window(nav, end, years)
            if s is None:
                continue
            r = m.returns_from_nav(s)
            br = m.returns_from_nav(b_slice)
            row = {
                "scheme_code": f["scheme_code"], "scheme_name": f["scheme_name"],
                "category": f["category"], "window_years": years,
                "start_date": s.index[0], "end_date": s.index[-1], "n_obs": len(s),
                "cagr": m.cagr(s), "volatility": m.annual_vol(r),
                "sharpe": m.sharpe(r, config.RISK_FREE_ANNUAL),
                "sortino": m.sortino(r, config.RISK_FREE_ANNUAL),
                "bench_cagr": m.cagr(b_slice),
            }
            row["excess_cagr"] = row["cagr"] - row["bench_cagr"]
            row.update(m.capture_and_beta(r, br, config.RISK_FREE_ANNUAL))
            row.update(m.max_drawdown_detail(s))
            rows.append(row)

    metrics = pd.DataFrame(rows)
    metrics["sharpe_rank_in_category"] = metrics.groupby(["category", "window_years"])["sharpe"] \
        .rank(ascending=False, method="min").astype(int)
    metrics.to_csv(config.PROCESSED_DIR / "fact_metrics.csv", index=False)
    print(f"fact_metrics: {len(metrics)} rows")

    rolling = pd.read_sql_query(
        "SELECT r.*, f.scheme_name, f.category FROM rolling_returns r "
        "JOIN fund_master f USING (scheme_code) WHERE f.role='selected'", conn)
    rolling.to_csv(config.PROCESSED_DIR / "fact_rolling_returns.csv", index=False)

    # Weekly drawdown curves (full history), funds + benchmark.
    dd_frames = []
    for _, f in master.iterrows():
        nav = wide[f["scheme_code"]].dropna()
        wk = m.drawdown_series(nav).resample("W-FRI").last().dropna()
        dd_frames.append(pd.DataFrame({"scheme_code": f["scheme_code"], "name": f["scheme_name"],
                                       "category": f["category"], "date": wk.index, "drawdown": wk.values}))
    bwk = m.drawdown_series(bench).resample("W-FRI").last().dropna()
    dd_frames.append(pd.DataFrame({"scheme_code": 0, "name": "Benchmark", "category": "Benchmark",
                                   "date": bwk.index, "drawdown": bwk.values}))
    pd.concat(dd_frames).to_csv(config.PROCESSED_DIR / "fact_drawdown_weekly.csv", index=False)

    cal = []
    for _, f in master.iterrows():
        c = m.calendar_year_returns(wide[f["scheme_code"]].dropna())
        c.insert(0, "scheme_code", f["scheme_code"])
        c.insert(1, "name", f["scheme_name"])
        c.insert(2, "category", f["category"])
        cal.append(c)
    cb = m.calendar_year_returns(bench)
    cb.insert(0, "scheme_code", 0)
    cb.insert(1, "name", "Benchmark")
    cb.insert(2, "category", "Benchmark")
    cal.append(cb)
    pd.concat(cal).to_csv(config.PROCESSED_DIR / "fact_calendar_returns.csv", index=False)

    summary = metrics[metrics["window_years"] == 5].groupby("category")[
        ["cagr", "volatility", "sharpe", "max_drawdown", "excess_cagr"]].median()
    print("\nMedian by category (5Y window):")
    print(summary.round(3).to_string())
    conn.close()


if __name__ == "__main__":
    main()
