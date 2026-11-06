"""Build a SYNTHETIC database so you can dry-run steps 3-8 without internet.
These are simulated prices, NOT real funds. Never publish results from this data.
Run:  python tests/make_synthetic_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

import common
import config


def main(seed=7, years=11, per_cat=6):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp("2026-10-30")
    dates = pd.bdate_range(end - pd.DateOffset(years=years), end)
    n = len(dates)

    market = rng.normal(0.00045, 0.0105, n)
    market[int(n * 0.45):int(n * 0.45) + 25] -= 0.012   # an artificial crash
    bench = 10000 * np.cumprod(1 + market)

    conn = common.connect()
    conn.executescript("DROP TABLE IF EXISTS fund_master; DROP TABLE IF EXISTS nav_daily;"
                       "DROP TABLE IF EXISTS benchmark_daily; DROP TABLE IF EXISTS data_quality;")
    conn.executescript(common.SCHEMA)

    master, navs = [], []
    code = 100000
    profile = {"Large Cap": (0.95, 0.003, 0.004), "Flexi Cap": (1.0, 0.004, 0.005),
               "Mid Cap": (1.15, 0.007, 0.007)}
    for cat, (beta, alpha_d, idio) in profile.items():
        for i in range(per_cat):
            code += 1
            skill = rng.normal(0, 0.0002)
            r = beta * market + alpha_d / 252 + skill + rng.normal(0, idio, n)
            nav = 20 * np.cumprod(1 + r)
            reg_code = code + 5000
            drag = 0.011 / 252                       # Regular plan costs ~1.1% a year more
            reg_nav = 19 * np.cumprod(1 + r - drag)
            pair = {"Direct": (code, nav, None), "Regular": (reg_code, reg_nav, None)}
            for plan, (c, series, _) in pair.items():
                master.append((c, f"Synthetic {cat} Fund {i+1} - {plan} Plan - Growth", "SynthAMC", cat, plan,
                               "selected" if plan == "Direct" else "regular_pair",
                               reg_code if plan == "Direct" else None,
                               dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d"), 1))
                navs.append(pd.DataFrame({"scheme_code": c, "date": dates.strftime("%Y-%m-%d"), "nav": series}))
    pd.DataFrame(master, columns=["scheme_code", "scheme_name", "fund_house", "category", "plan", "role",
                                  "pair_code", "first_nav_date", "last_nav_date", "is_active"]
                 ).to_sql("fund_master", conn, if_exists="append", index=False)
    pd.concat(navs).to_sql("nav_daily", conn, if_exists="append", index=False)
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "value": bench, "source": "SYNTHETIC"}
                 ).to_sql("benchmark_daily", conn, if_exists="append", index=False)
    conn.commit()
    print("Synthetic DB written to", config.DB_PATH)


if __name__ == "__main__":
    main()
