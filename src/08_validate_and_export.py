"""STEP 8 - Integrity checks, dimension tables and a data dictionary for Power BI.
Fails loudly if anything the dashboard depends on is missing or inconsistent.
Run:  python src/08_validate_and_export.py
"""
import pandas as pd

import common
import config

REQUIRED = ["fact_metrics.csv", "fact_rolling_returns.csv", "fact_drawdown_weekly.csv",
            "fact_calendar_returns.csv", "fact_sip_summary.csv", "fact_sip_windows.csv",
            "fact_expense_realised.csv", "fact_expense_sensitivity.csv", "fact_correlation.csv",
            "fund_clusters.csv"]


def main():
    P = config.PROCESSED_DIR
    problems = []
    for f in REQUIRED:
        if not (P / f).exists():
            problems.append(f"missing file: {f}")
    if problems:
        raise SystemExit("\n".join(problems))

    conn = common.connect()
    funds = pd.read_sql_query("SELECT * FROM fund_master WHERE role='selected'", conn)
    dim = funds[["scheme_code", "scheme_name", "fund_house", "category", "plan",
                 "first_nav_date", "last_nav_date", "is_active"]]
    dim.to_csv(P / "dim_fund.csv", index=False)

    metrics = pd.read_csv(P / "fact_metrics.csv")
    checks = {
        "every metrics fund exists in dim_fund": set(metrics["scheme_code"]) <= set(dim["scheme_code"]),
        "no duplicate fund x window rows": not metrics.duplicated(["scheme_code", "window_years"]).any(),
        "max drawdown between -100% and 0": metrics["max_drawdown"].between(-1, 0).all(),
        "volatility positive": (metrics["volatility"] > 0).all(),
        "beta in a sane range (-0.5 to 2.5)": metrics["beta"].dropna().between(-0.5, 2.5).all(),
        "only Direct plans in dim_fund": (dim["plan"] == "Direct").all(),
    }
    sip = pd.read_csv(P / "fact_sip_summary.csv")
    checks["SIP win-rate is a probability"] = sip["pct_sip_beats_lump"].between(0, 1).all()
    for name, ok in checks.items():
        print(("PASS  " if bool(ok) else "FAIL  ") + name)
        if not ok:
            problems.append(name)

    dd = pd.read_sql_query("SELECT * FROM data_quality", conn)
    print(f"\ndata_quality issues logged: {len(dd)} "
          f"({(dd['issue'] == 'gap').sum()} gaps, {(dd['issue'] == 'large_move').sum()} large moves)")
    dd.to_csv(P / "data_quality.csv", index=False)

    dictionary = pd.DataFrame([
        ("cagr", "Annualised return over the window (compound)"),
        ("volatility", "Annualised standard deviation of daily returns"),
        ("sharpe", "Mean excess return over risk-free / its std dev, annualised"),
        ("sortino", "Like Sharpe but penalises only downside deviation"),
        ("beta", "Sensitivity to the benchmark (excess-return regression)"),
        ("alpha", "Annualised return not explained by beta (simple, daily x 252)"),
        ("max_drawdown", "Worst peak-to-trough fall inside the window"),
        ("days_to_recover", "Days from trough back to the prior peak (blank if not recovered)"),
        ("up_capture / down_capture", "Average fund return / average benchmark return on up / down days"),
        ("info_ratio", "Annualised active return / tracking error"),
        ("pct_sip_beats_lump", "Share of start months where SIP ended above lump sum (same total invested)"),
        ("annual_drag", "Direct CAGR minus Regular CAGR for the same fund"),
    ], columns=["field", "meaning"])
    dictionary.to_csv(P / "data_dictionary.csv", index=False)
    conn.close()
    if problems:
        raise SystemExit("\nValidation FAILED - fix before building the dashboard.")
    print("\nAll checks passed. Load the CSVs in data/processed/ into Power BI.")


if __name__ == "__main__":
    main()
