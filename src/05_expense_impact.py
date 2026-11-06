"""STEP 5 - How much do costs cost? Two complementary views.

A) REALISED drag: the same fund's Direct vs Regular plan NAVs (same portfolio, different
   expense ratio). A monthly SIP of config.SIP_AMOUNT is run in both over the last N years;
   the rupee gap at the end is the real cost of the Regular plan's higher expense ratio.
B) SENSITIVITY: take each Direct fund, subtract an extra annual cost (0.5%, 1.0%, 1.5%)
   from monthly returns and see the corpus gap. Shows the arithmetic of compounding costs.
Run:  python src/05_expense_impact.py
"""
import numpy as np
import pandas as pd

import common
import config


def sip_corpus_from_monthly_returns(rets: np.ndarray, amount: float) -> float:
    v = 0.0
    for r in rets:
        v = (v + amount) * (1.0 + r)
    return v


def main():
    conn = common.connect()
    master = pd.read_sql_query("SELECT * FROM fund_master", conn)
    direct = master[master["role"] == "selected"]
    wide = common.load_nav_wide(conn)
    N = config.EXPENSE_STUDY_YEARS

    realised, sens = [], []
    for _, f in direct.iterrows():
        d_nav = wide[f["scheme_code"]].dropna()
        d_m = common.first_of_month_series(d_nav)
        d_m = d_m.iloc[-(12 * N + 1):]
        d_rets = d_m.pct_change().dropna().to_numpy()
        n_months = len(d_rets)
        if n_months < 36:
            continue

        # (B) sensitivity
        base = sip_corpus_from_monthly_returns(d_rets, config.SIP_AMOUNT)
        invested = config.SIP_AMOUNT * n_months
        for extra in config.EXPENSE_SENSITIVITY:
            adj = (1 + d_rets) * (1 - extra / 12.0) - 1
            v = sip_corpus_from_monthly_returns(adj, config.SIP_AMOUNT)
            sens.append({"scheme_code": f["scheme_code"], "scheme_name": f["scheme_name"],
                         "category": f["category"], "extra_annual_cost": extra, "months": n_months,
                         "invested": invested, "corpus_base": base, "corpus_after_cost": v,
                         "rupee_gap": base - v, "gap_pct_of_base": (base - v) / base})

        # (A) realised Direct vs Regular
        if pd.notna(f["pair_code"]) and int(f["pair_code"]) in wide.columns:
            r_nav = wide[int(f["pair_code"])].dropna()
            r_m = common.first_of_month_series(r_nav)
            idx = d_m.index.intersection(r_m.index)
            if len(idx) >= 37:
                dm, rm = d_m.loc[idx], r_m.loc[idx]
                dv = sip_corpus_from_monthly_returns(dm.pct_change().dropna().to_numpy(), config.SIP_AMOUNT)
                rv = sip_corpus_from_monthly_returns(rm.pct_change().dropna().to_numpy(), config.SIP_AMOUNT)
                yrs = (idx[-1] - idx[0]).days / 365.25
                realised.append({
                    "scheme_code": f["scheme_code"], "scheme_name": f["scheme_name"],
                    "category": f["category"], "months": len(idx) - 1,
                    "direct_corpus": dv, "regular_corpus": rv, "rupee_gap": dv - rv,
                    "gap_pct": (dv - rv) / rv,
                    "direct_cagr": (dm.iloc[-1] / dm.iloc[0]) ** (1 / yrs) - 1,
                    "regular_cagr": (rm.iloc[-1] / rm.iloc[0]) ** (1 / yrs) - 1,
                })
    realised = pd.DataFrame(realised)
    sens = pd.DataFrame(sens)
    if not realised.empty:
        realised["annual_drag"] = realised["direct_cagr"] - realised["regular_cagr"]
    realised.to_csv(config.PROCESSED_DIR / "fact_expense_realised.csv", index=False)
    sens.to_csv(config.PROCESSED_DIR / "fact_expense_sensitivity.csv", index=False)

    if not realised.empty:
        print("Realised Direct vs Regular (median by category):")
        print(realised.groupby("category")[["annual_drag", "gap_pct", "rupee_gap"]].median().round(4).to_string())
    print("\nSensitivity (median rupee gap by extra annual cost):")
    print(sens.groupby("extra_annual_cost")[["rupee_gap", "gap_pct_of_base"]].median().round(3).to_string())
    conn.close()


if __name__ == "__main__":
    main()
