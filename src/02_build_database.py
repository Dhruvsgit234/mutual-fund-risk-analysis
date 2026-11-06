"""STEP 2 - Load cached NAVs into SQLite, clean them, log data-quality issues.

Cleaning rules (all logged, nothing is silently changed):
  * dates parsed from dd-mm-yyyy, NAV must be numeric and > 0
  * duplicate (scheme, date) rows dropped
  * gaps longer than config.DATA_GAP_DAYS and daily moves larger than
    config.SUSPICIOUS_DAILY_MOVE are written to table data_quality for review.
    They are NOT deleted: big moves can be genuine (crashes, Mar-2020) or
    corporate-action artefacts - you decide after looking.
Run:  python src/02_build_database.py
"""
import importlib

import pandas as pd

import common
import config

step1 = importlib.import_module("01_select_and_download")


def quality_checks(code, hist: pd.DataFrame):
    issues = []
    gaps = hist["date"].diff().dt.days
    for idx in gaps[gaps > config.DATA_GAP_DAYS].index:
        issues.append((code, "gap", hist.loc[idx, "date"].strftime("%Y-%m-%d"),
                       f"{int(gaps[idx])} days since previous NAV"))
    moves = hist["nav"].pct_change()
    for idx in moves[moves.abs() > config.SUSPICIOUS_DAILY_MOVE].index:
        issues.append((code, "large_move", hist.loc[idx, "date"].strftime("%Y-%m-%d"),
                       f"{moves[idx]:+.1%} in one day"))
    return issues


def main():
    sel = pd.read_csv(config.RAW_DIR / "selected_funds.csv")
    bench = pd.read_csv(config.RAW_DIR / "benchmark_used.csv", parse_dates=["date"])

    conn = common.connect()
    conn.executescript("DROP TABLE IF EXISTS fund_master; DROP TABLE IF EXISTS nav_daily;"
                       "DROP TABLE IF EXISTS benchmark_daily; DROP TABLE IF EXISTS data_quality;")
    conn.executescript(common.SCHEMA)

    master_rows, nav_frames, issues = [], [], []
    newest = None
    for _, r in sel.iterrows():
        code = int(r["scheme_code"])
        hist = step1.parse_history(step1.get_full(code))
        if hist.empty:
            print(f"  skipped {code}: no usable NAV rows")
            continue
        issues += quality_checks(code, hist)
        nav_frames.append(hist.assign(scheme_code=code))
        newest = hist["date"].max() if newest is None else max(newest, hist["date"].max())
        master_rows.append({
            "scheme_code": code, "scheme_name": r["scheme_name"], "fund_house": r["fund_house"],
            "category": r["category"], "plan": r["plan"], "role": r["role"],
            "pair_code": None if pd.isna(r.get("pair_code")) else int(r["pair_code"]),
            "first_nav_date": hist["date"].iloc[0].strftime("%Y-%m-%d"),
            "last_nav_date": hist["date"].iloc[-1].strftime("%Y-%m-%d"), "is_active": 0})

    master = pd.DataFrame(master_rows)
    master["is_active"] = ((newest - pd.to_datetime(master["last_nav_date"])).dt.days
                           <= config.ACTIVE_TOLERANCE_DAYS).astype(int)
    navs = pd.concat(nav_frames, ignore_index=True)
    navs["date"] = navs["date"].dt.strftime("%Y-%m-%d")
    bench = bench.dropna().drop_duplicates("date").sort_values("date")
    bench["date"] = bench["date"].dt.strftime("%Y-%m-%d")

    master.to_sql("fund_master", conn, if_exists="append", index=False)
    navs[["scheme_code", "date", "nav"]].to_sql("nav_daily", conn, if_exists="append", index=False)
    bench[["date", "value", "source"]].to_sql("benchmark_daily", conn, if_exists="append", index=False)
    pd.DataFrame(issues, columns=["scheme_code", "issue", "date", "detail"]).to_sql(
        "data_quality", conn, if_exists="append", index=False)
    conn.commit()

    cnt = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"fund_master {cnt('fund_master')} | nav_daily {cnt('nav_daily')} | "
          f"benchmark_daily {cnt('benchmark_daily')} | data_quality issues {cnt('data_quality')}")
    conn.close()


if __name__ == "__main__":
    main()
