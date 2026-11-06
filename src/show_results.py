from pathlib import Path

import pandas as pd

P = Path(__file__).resolve().parents[1] / "data" / "processed"

sip = pd.read_csv(P / "fact_sip_summary.csv")
cols = ["category", "horizon_years", "n_windows", "pct_sip_beats_lump",
        "median_sip_xirr", "median_lump_cagr", "p10_sip_xirr", "p10_lump_cagr",
        "pct_sip_loss", "pct_lump_loss"]
sip = sip[cols].copy()
for c in cols[3:]:
    sip[c] = (sip[c] * 100).round(1)
sip["n_windows"] = sip["n_windows"].astype(int)
print("STEP 4 - SIP vs lump sum (all values in %)")
print(sip.to_string(index=False))

real = pd.read_csv(P / "fact_expense_realised.csv")
print("\nSTEP 5A - Direct vs Regular, real data")
print(f"fund pairs: {len(real)}")
g = real.groupby("category")[["annual_drag", "gap_pct", "rupee_gap"]].median()
g["annual_drag"] = (g["annual_drag"] * 100).round(2)
g["gap_pct"] = (g["gap_pct"] * 100).round(1)
g["rupee_gap"] = g["rupee_gap"].round(0).astype(int)
print(g.rename(columns={"annual_drag": "annual_drag_%", "gap_pct": "corpus_gap_%"}).to_string())

sens = pd.read_csv(P / "fact_expense_sensitivity.csv")
print("\nSTEP 5B - extra annual cost sensitivity (median)")
s = sens.groupby("extra_annual_cost")[["rupee_gap", "gap_pct_of_base"]].median()
s["rupee_gap"] = s["rupee_gap"].round(0).astype(int)
s["gap_pct_of_base"] = (s["gap_pct_of_base"] * 100).round(1)
print(s.to_string())