"""STEP 6 - Do 'different' funds actually behave differently?

Weekly returns over the last config.CORR_WINDOW_YEARS years -> correlation matrix ->
hierarchical clustering (distance = sqrt(0.5 * (1 - corr))). Outputs:
  fact_correlation.csv     long format (for a Power BI heatmap)
  fund_clusters.csv        cluster id per fund
  cluster_vs_category.csv  how SEBI categories line up with behaviour-based clusters
  near_duplicates.csv      fund pairs with correlation above config.NEAR_DUPLICATE_CORR
Run:  python src/06_correlation_clusters.py
"""
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

import common
import config


def main():
    conn = common.connect()
    master = pd.read_sql_query(
        "SELECT * FROM fund_master WHERE role='selected' AND is_active=1", conn)
    wide = common.load_nav_wide(conn, master["scheme_code"].tolist())
    end = wide.index.max()
    start = end - pd.DateOffset(years=config.CORR_WINDOW_YEARS)
    w = wide[wide.index >= start]
    w = w.dropna(axis=1, thresh=int(0.98 * len(w)))          # drop funds without full history
    weekly = w.ffill(limit=3).resample("W-FRI").last().pct_change().dropna(how="any")
    codes = list(weekly.columns)
    names = master.set_index("scheme_code")["scheme_name"]
    cats = master.set_index("scheme_code")["category"]

    corr = weekly.corr()
    dist = np.sqrt(0.5 * (1 - corr.clip(-1, 1)).to_numpy())
    np.fill_diagonal(dist, 0.0)
    Z = linkage(squareform(dist, checks=False), method="average")
    labels = fcluster(Z, t=config.N_CLUSTERS, criterion="maxclust")

    clusters = pd.DataFrame({"scheme_code": codes, "scheme_name": [names[c] for c in codes],
                             "category": [cats[c] for c in codes], "cluster": labels})
    clusters.to_csv(config.PROCESSED_DIR / "fund_clusters.csv", index=False)
    pd.crosstab(clusters["cluster"], clusters["category"]).to_csv(
        config.PROCESSED_DIR / "cluster_vs_category.csv")

    corr.index.name, corr.columns.name = "scheme_code_a", "scheme_code_b"
    long = corr.stack().rename("correlation").reset_index()
    long["name_a"] = long["scheme_code_a"].map(names)
    long["name_b"] = long["scheme_code_b"].map(names)
    long.to_csv(config.PROCESSED_DIR / "fact_correlation.csv", index=False)

    dup = long[(long["scheme_code_a"] < long["scheme_code_b"]) &
               (long["correlation"] >= config.NEAR_DUPLICATE_CORR)] \
        .sort_values("correlation", ascending=False)
    dup.to_csv(config.PROCESSED_DIR / "near_duplicates.csv", index=False)

    print(f"{len(codes)} funds, {len(weekly)} weekly observations")
    print("\nCluster x category:")
    print(pd.crosstab(clusters["cluster"], clusters["category"]).to_string())
    print(f"\nNear-duplicate pairs (corr >= {config.NEAR_DUPLICATE_CORR}): {len(dup)}")
    conn.close()


if __name__ == "__main__":
    main()
