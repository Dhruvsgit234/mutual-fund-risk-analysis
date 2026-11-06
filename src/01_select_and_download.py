"""STEP 1 - Choose the fund universe and download NAV history from mfapi.in.

What it does
  1. Lists every scheme, keeps Direct + Growth equity-style names.
  2. Looks up each scheme's SEBI category, keeps Large / Flexi / Mid Cap.
  3. Downloads full NAV history for category matches, ranks them, picks N per category.
  4. Writes a survivorship check (how many funds stopped reporting, were too young...).
  5. Finds each selected fund's Regular-plan twin (for the expense-drag study).
  6. Gets a benchmark: your Nifty 50 TRI CSV if present, else a Nifty 50 index-fund proxy.

Everything downloaded is cached in data/raw/ so re-runs do not hit the API again.
Run:  python src/01_select_and_download.py
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import common
import config

BASE = "https://api.mfapi.in/mf"

EXCLUDE_TOKENS = [
    "idcw", "dividend", "bonus", "payout", "reinvest", "segregated", "etf", "liquid",
    "overnight", "debt", "gilt", "bond", "money market", "fmp", "fixed", "ultra short",
    "low duration", "short term", "medium term", "credit", "hybrid", "arbitrage", "gold",
    "silver", "fof", "fund of fund", "index", "nifty", "sensex", "capital protection",
    "interval", "series", "balanced", "equity savings", "conservative", "retirement",
    "children", "income", "floater", "target maturity",
]


def fetch_json(url, retries=3, pause=1.5):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(pause * (attempt + 1))


def is_candidate_name(name: str, direct: bool) -> bool:
    n = name.lower()
    if "growth" not in n or any(t in n for t in EXCLUDE_TOKENS):
        return False
    return ("direct" in n) if direct else ("direct" not in n)


def parse_history(payload) -> pd.DataFrame:
    """mfapi returns newest-first rows {'date': 'dd-mm-yyyy', 'nav': '123.4'}."""
    df = pd.DataFrame(payload.get("data", []))
    if df.empty:
        return pd.DataFrame(columns=["date", "nav"])
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna().query("nav > 0").drop_duplicates("date").sort_values("date")
    return df.reset_index(drop=True)


def get_full(code):
    """Full payload for a scheme, cached on disk."""
    config.NAV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.NAV_CACHE_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text())
    payload = fetch_json(f"{BASE}/{code}")
    path.write_text(json.dumps(payload))
    time.sleep(0.15)
    return payload


def get_meta(code):
    """Cheap category lookup; falls back to the full payload if /latest is unavailable."""
    try:
        payload = fetch_json(f"{BASE}/{code}/latest")
    except Exception:
        payload = get_full(code)
    meta = payload.get("meta", {}) or {}
    time.sleep(0.1)
    return {
        "scheme_code": int(code),
        "category": str(meta.get("scheme_category", "")).strip(),
        "fund_house": str(meta.get("fund_house", "")).strip(),
    }


def build_catalog(candidates):
    """candidates: list of {'schemeCode', 'schemeName'}. Resumable (data/raw/catalog.csv)."""
    path = config.RAW_DIR / "catalog.csv"
    done = pd.read_csv(path) if path.exists() else pd.DataFrame(
        columns=["scheme_code", "scheme_name", "category", "fund_house"])
    have = set(done["scheme_code"].astype(int))
    todo = [c for c in candidates if int(c["schemeCode"]) not in have]
    print(f"catalog: {len(have)} cached, {len(todo)} to look up")
    names = {int(c["schemeCode"]): c["schemeName"] for c in candidates}
    rows = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, meta in enumerate(ex.map(lambda c: get_meta(c["schemeCode"]), todo), 1):
            meta["scheme_name"] = names[meta["scheme_code"]]
            rows.append(meta)
            if i % 100 == 0:
                print(f"  looked up {i}/{len(todo)}")
    out = pd.concat([done, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("scheme_code")
    out.to_csv(path, index=False)
    return out


def summarise_history(code):
    hist = parse_history(get_full(code))
    if hist.empty:
        return None
    return {"scheme_code": int(code), "first_date": hist["date"].iloc[0],
            "last_date": hist["date"].iloc[-1], "n_obs": len(hist)}


def select_funds(catalog: pd.DataFrame):
    rows, survivorship = [], []
    label_by_cat = {v: k for k, v in config.CATEGORIES.items()}
    catalog = catalog.assign(cat_key=catalog["category"].str.lower().str.strip())
    matched = catalog[catalog["cat_key"].isin(label_by_cat)].copy()
    if matched.empty:
        print("No category matches. Categories seen in your data:")
        print(catalog["category"].value_counts().head(25))
        raise SystemExit("Adjust config.CATEGORIES to match the text above.")

    stats = [s for s in (summarise_history(c) for c in matched["scheme_code"]) if s]
    matched = matched.merge(pd.DataFrame(stats), on="scheme_code")
    newest = matched["last_date"].max()
    matched["years"] = (matched["last_date"] - matched["first_date"]).dt.days / 365.25
    matched["is_active"] = (newest - matched["last_date"]).dt.days <= config.ACTIVE_TOLERANCE_DAYS
    matched["label"] = matched["cat_key"].map(label_by_cat)

    for label, g in matched.groupby("label"):
        eligible = g[g["is_active"] & (g["years"] >= config.MIN_HISTORY_YEARS)]
        if config.SELECTION_METHOD == "random":
            pick = eligible.sample(min(config.FUNDS_PER_CATEGORY, len(eligible)),
                                   random_state=config.RANDOM_SEED)
        else:
            pick = eligible.sort_values("years", ascending=False).head(config.FUNDS_PER_CATEGORY)
        survivorship.append({
            "category": label, "direct_growth_schemes_found": len(g),
            "stopped_reporting": int((~g["is_active"]).sum()),
            "active_but_too_young": int((g["is_active"] & (g["years"] < config.MIN_HISTORY_YEARS)).sum()),
            "eligible": len(eligible), "selected": len(pick),
            "selection_method": config.SELECTION_METHOD,
        })
        rows.append(pick.assign(plan="Direct", role="selected"))
    chosen = pd.concat(rows, ignore_index=True)
    return chosen, pd.DataFrame(survivorship), newest


def find_regular_twins(chosen: pd.DataFrame, universe):
    regular_pool = [u for u in universe if is_candidate_name(u["schemeName"], direct=False)]
    by_norm = {}
    for u in regular_pool:
        by_norm.setdefault(common.normalize_scheme_name(u["schemeName"]), []).append(u)
    twins = []
    for _, r in chosen.iterrows():
        matches = by_norm.get(common.normalize_scheme_name(r["scheme_name"]), [])
        if len(matches) >= 1:
            m = matches[0]
            twins.append({"direct_code": int(r["scheme_code"]), "scheme_code": int(m["schemeCode"]),
                          "scheme_name": m["schemeName"], "category": r["label"],
                          "fund_house": r["fund_house"], "plan": "Regular", "role": "regular_pair"})
    return pd.DataFrame(twins)


def get_benchmark(universe):
    """Return (DataFrame[date,value], source label)."""
    if config.BENCHMARK_CSV.exists():
        df = pd.read_csv(config.BENCHMARK_CSV)
        df.columns = [c.strip().lower() for c in df.columns]
        value_col = "tri" if "tri" in df.columns else df.columns[1]
        raw_dates = df[df.columns[0]].astype(str)
        df["date"] = pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="coerce")
        if df["date"].isna().mean() > 0.5:
         df["date"] = pd.to_datetime(raw_dates, dayfirst=True, errors="coerce")
        
        df = df.rename(columns={value_col: "value"})[["date", "value"]].dropna()
        return df.sort_values("date"), "Nifty 50 TRI (niftyindices.com)"
    print("No benchmark CSV found - using a Nifty 50 index-fund proxy (see README).")
    cands = [u for u in universe if "nifty 50" in u["schemeName"].lower()
             and "index" in u["schemeName"].lower() and "direct" in u["schemeName"].lower()
             and "growth" in u["schemeName"].lower()
             and not any(t in u["schemeName"].lower() for t in ["idcw", "dividend", "next", "etf", "midcap", "smallcap"])]
    best, best_len = None, 0
    for u in cands[:15]:
        hist = parse_history(get_full(u["schemeCode"]))
        if len(hist) > best_len:
            best, best_len = (u, hist), len(hist)
    if best is None:
        raise SystemExit("Could not find a proxy benchmark; supply data/raw/nifty50_tri.csv")
    u, hist = best
    return hist.rename(columns={"nav": "value"}), f"Proxy: {u['schemeName']}"


def main():
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    universe = fetch_json(BASE)
    print(f"{len(universe)} schemes listed")
    candidates = [u for u in universe if is_candidate_name(u["schemeName"], direct=True)]
    print(f"{len(candidates)} Direct+Growth candidates after name filters")

    catalog = build_catalog(candidates)
    chosen, survivorship, newest = select_funds(catalog)
    survivorship.to_csv(config.PROCESSED_DIR / "survivorship_check.csv", index=False)
    print(survivorship.to_string(index=False))

    twins = find_regular_twins(chosen, universe)
    for code in twins["scheme_code"]:
        get_full(code)
    bench, source = get_benchmark(universe)
    bench["source"] = source
    bench.to_csv(config.RAW_DIR / "benchmark_used.csv", index=False)

    sel = chosen.rename(columns={"label": "category_label"})
    out = pd.DataFrame({
        "scheme_code": sel["scheme_code"], "scheme_name": sel["scheme_name"],
        "fund_house": sel["fund_house"], "category": sel["category_label"],
        "plan": "Direct", "role": "selected", "pair_code": None})
    if not twins.empty:
        out["pair_code"] = out["scheme_code"].map(dict(zip(twins["direct_code"], twins["scheme_code"])))
        tw = twins.drop(columns="direct_code").assign(pair_code=None)
        out = pd.concat([out, tw[out.columns]], ignore_index=True)
    out.to_csv(config.RAW_DIR / "selected_funds.csv", index=False)
    print(f"\nSelected {len(chosen)} funds, {len(twins)} Regular twins. Newest NAV date: {newest.date()}")
    print("Saved: data/raw/selected_funds.csv, benchmark_used.csv, data/processed/survivorship_check.csv")


if __name__ == "__main__":
    main()
