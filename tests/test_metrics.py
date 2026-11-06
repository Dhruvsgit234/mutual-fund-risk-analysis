"""Unit tests against hand-computable answers. Run: pytest -q"""
import importlib

import numpy as np
import pandas as pd
import pytest

import common
import metrics_lib as m


def series(values, start="2020-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_cagr_doubling_in_one_year():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01"])
    nav = pd.Series([100.0, 200.0], index=idx)
    assert m.cagr(nav) == pytest.approx(1.0, abs=0.01)      # 366 days -> ~100%


def test_constant_growth_has_zero_volatility_and_no_drawdown():
    nav = series(100 * 1.001 ** np.arange(300))
    r = m.returns_from_nav(nav)
    assert m.annual_vol(r) == pytest.approx(0.0, abs=1e-12)
    assert m.max_drawdown_detail(nav)["max_drawdown"] == 0.0


def test_max_drawdown_known_answer_and_recovery():
    nav = series([100, 120, 90, 100, 130])
    d = m.max_drawdown_detail(nav)
    assert d["max_drawdown"] == pytest.approx(-0.25)          # 120 -> 90
    assert d["peak_date"] == nav.index[1] and d["trough_date"] == nav.index[2]
    assert d["recovery_date"] == nav.index[4]                 # back above 120 at 130


def test_drawdown_without_recovery_is_nat():
    nav = series([100, 120, 90, 95])
    d = m.max_drawdown_detail(nav)
    assert pd.isna(d["recovery_date"]) and np.isnan(d["days_to_recover"])


def test_sharpe_matches_manual_formula():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.0006, 0.01, 500))
    rf = 0.06
    ex = r - ((1 + rf) ** (1 / 252) - 1)
    expected = ex.mean() / ex.std(ddof=1) * np.sqrt(252)
    assert m.sharpe(r, rf) == pytest.approx(expected)


def test_sortino_ignores_upside_volatility():
    r_sym = pd.Series([0.01, -0.01] * 100)
    r_up = pd.Series([0.03, -0.01] * 100)
    assert m.sortino(r_up, 0.0) > m.sortino(r_sym, 0.0)


def test_beta_alpha_recover_known_relationship():
    rng = np.random.default_rng(3)
    b = pd.Series(rng.normal(0.0004, 0.01, 1500))
    f = 1.2 * b + 0.0002                                       # beta 1.2, alpha 0.0002/day
    out = m.capture_and_beta(f, b, rf_annual=0.0)
    assert out["beta"] == pytest.approx(1.2, abs=1e-6)
    assert out["alpha"] == pytest.approx(0.0002 * 252, abs=1e-6)
    assert out["r2"] == pytest.approx(1.0, abs=1e-9)


def test_capture_ratios_for_leveraged_clone():
    rng = np.random.default_rng(4)
    b = pd.Series(rng.normal(0, 0.01, 1000))
    out = m.capture_and_beta(1.5 * b, b, 0.0)
    assert out["up_capture"] == pytest.approx(1.5) and out["down_capture"] == pytest.approx(1.5)


def test_calendar_year_returns():
    idx = pd.to_datetime(["2020-12-30", "2021-12-30", "2022-06-30"])
    nav = pd.Series([100.0, 110.0, 99.0], index=idx)
    c = m.calendar_year_returns(nav)
    assert c.loc[c.year == 2021, "return"].iloc[0] == pytest.approx(0.10)
    assert bool(c.loc[c.year == 2022, "is_partial"].iloc[0]) is True


def test_xirr_single_lump_sum():
    d0, d1 = pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")
    assert common.xirr([-100, 110], [d0, d1]) == pytest.approx(0.10, abs=0.002)


def test_xirr_needs_both_signs():
    d = [pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")]
    assert np.isnan(common.xirr([-100, -50], d))


def test_sip_on_flat_market_returns_exactly_what_was_invested():
    nav = np.full(13, 50.0)
    assert common.sip_final_value(nav, 10_000) == pytest.approx(120_000)


def test_sip_on_steadily_rising_market_beats_invested_amount():
    nav = 100 * 1.01 ** np.arange(13)
    assert common.sip_final_value(nav, 10_000) > 120_000


def test_normalize_scheme_name_pairs_direct_and_regular():
    a = "HDFC Flexi Cap Fund - Growth Option - Direct Plan"
    b = "HDFC Flexi Cap Fund - Growth Plan"
    assert common.normalize_scheme_name(a) == common.normalize_scheme_name(b) == "hdfc flexi cap fund"


def test_normalize_keeps_large_and_mid_cap_distinct():
    assert common.normalize_scheme_name("X Large & Mid Cap Fund - Direct Plan - Growth") != \
           common.normalize_scheme_name("X Mid Cap Fund - Direct Plan - Growth")


def test_first_of_month_series():
    idx = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04"])
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    out = common.first_of_month_series(s)
    assert list(out.values) == [1.0, 3.0]


def test_step1_name_filters():
    step1 = importlib.import_module("01_select_and_download")
    assert step1.is_candidate_name("ABC Flexi Cap Fund - Direct Plan - Growth", direct=True)
    assert not step1.is_candidate_name("ABC Flexi Cap Fund - Direct Plan - IDCW", direct=True)
    assert not step1.is_candidate_name("ABC Flexi Cap Fund - Regular Plan - Growth", direct=True)
    assert step1.is_candidate_name("ABC Flexi Cap Fund - Regular Plan - Growth", direct=False)
    assert not step1.is_candidate_name("ABC Nifty 50 Index Fund - Direct - Growth", direct=True)


def test_step1_parse_history_cleans_bad_rows():
    step1 = importlib.import_module("01_select_and_download")
    payload = {"data": [{"date": "03-01-2020", "nav": "12.5"}, {"date": "02-01-2020", "nav": "12.0"},
                        {"date": "02-01-2020", "nav": "12.0"}, {"date": "01-01-2020", "nav": "0"},
                        {"date": "bad", "nav": "10"}]}
    df = step1.parse_history(payload)
    assert list(df["nav"]) == [12.0, 12.5] and df["date"].is_monotonic_increasing


def test_llm_validator_flags_invented_numbers_and_advice():
    mod = importlib.import_module("07_llm_summaries")
    facts = {"annual_return": "12.0%", "max_drawdown": "30.0%"}
    ok = "It returned 12.0% a year with a 30.0% fall."
    bad = "It returned 15.0% a year and you should buy it."
    assert mod.check_output(ok, facts, 5) == ""
    flags = mod.check_output(bad, facts, 5)
    assert "numbers_not_in_data" in flags and "banned_words" in flags
