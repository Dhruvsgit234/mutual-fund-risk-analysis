"""STEP 4 - SIP vs lump sum over EVERY possible start month (rolling windows).

For each fund, horizon H (years) and start month i:
  SIP       : config.SIP_AMOUNT invested on the first NAV date of each of the next 12*H months
  Lump sum  : the same TOTAL amount invested on the first NAV date of month i
  Both are valued on the first NAV date of month i + 12*H.
Measured: final value, XIRR (SIP) vs CAGR (lump sum), who won, and the spread of outcomes.

Honest reading: lump sum has more money invested for longer, so it usually wins in rising
markets. The point of SIP is the *risk profile* (worse-case, dispersion), not beating lump sum.
Overlapping windows are NOT independent observations - say so in your write-up.
Run:  python src/04_sip_vs_lumpsum.py
"""
import numpy as np
import pandas as pd

import common
import config


def simulate_fund(code, name, category, nav: pd.Series):
    monthly = common.first_of_month_series(nav)
    dates, vals = list(monthly.index), monthly.to_numpy()
    out = []
    for H in config.SIP_HORIZONS_YEARS:
        n = 12 * H
        for i in range(0, len(vals) - n):
            window_vals = vals[i:i + n + 1]
            sip_final = common.sip_final_value(window_vals, config.SIP_AMOUNT)
            invested = config.SIP_AMOUNT * n
            lump_final = invested * window_vals[-1] / window_vals[0]
            cfs = [-config.SIP_AMOUNT] * n + [sip_final]
            cf_dates = dates[i:i + n] + [dates[i + n]]
            sip_xirr = common.xirr(cfs, cf_dates)
            years = (dates[i + n] - dates[i]).days / 365.25
            lump_cagr = (window_vals[-1] / window_vals[0]) ** (1 / years) - 1
            out.append({
                "scheme_code": code, "scheme_name": name, "category": category,
                "horizon_years": H, "start_date": dates[i], "end_date": dates[i + n],
                "invested": invested, "sip_final": sip_final, "lump_final": lump_final,
                "sip_xirr": sip_xirr, "lump_cagr": lump_cagr,
                "sip_beats_lump": sip_final > lump_final,
            })
    return out


def main():
    conn = common.connect()
    master = pd.read_sql_query("SELECT * FROM fund_master WHERE role='selected'", conn)
    wide = common.load_nav_wide(conn, master["scheme_code"].tolist())
    rows = []
    for _, f in master.iterrows():
        rows += simulate_fund(f["scheme_code"], f["scheme_name"], f["category"],
                              wide[f["scheme_code"]].dropna())
    res = pd.DataFrame(rows)
    res.to_csv(config.PROCESSED_DIR / "fact_sip_windows.csv", index=False)

    def summarise(g):
        return pd.Series({
            "n_windows": len(g),
            "pct_sip_beats_lump": g["sip_beats_lump"].mean(),
            "median_sip_xirr": g["sip_xirr"].median(),
            "median_lump_cagr": g["lump_cagr"].median(),
            "p10_sip_xirr": g["sip_xirr"].quantile(0.10),
            "p10_lump_cagr": g["lump_cagr"].quantile(0.10),
            "worst_sip_xirr": g["sip_xirr"].min(),
            "worst_lump_cagr": g["lump_cagr"].min(),
            "pct_sip_loss": (g["sip_final"] < g["invested"]).mean(),
            "pct_lump_loss": (g["lump_final"] < g["invested"]).mean(),
            "sip_xirr_std": g["sip_xirr"].std(),
            "lump_cagr_std": g["lump_cagr"].std(),
        })

    summary = res.groupby(["category", "horizon_years"]).apply(summarise, include_groups=False).reset_index()
    summary.to_csv(config.PROCESSED_DIR / "fact_sip_summary.csv", index=False)
    print(summary.round(3).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
