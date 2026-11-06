from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
chunk_dir = ROOT / "data" / "raw" / "tri_chunks"
files = sorted(chunk_dir.glob("*.csv"))
print(f"Found {len(files)} CSV files in {chunk_dir}")
if not files:
    raise SystemExit("No CSV files found. Check the folder name and location.")

frames = []
for path in files:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    low = {c: c.lower() for c in df.columns}
    date_col = next(c for c, l in low.items() if "date" in l)
    tri_col = next(c for c, l in low.items() if "total return" in l and "net" not in l)
    frames.append(pd.DataFrame({
        "Date": pd.to_datetime(df[date_col], errors="coerce"),
        "TRI": pd.to_numeric(df[tri_col].astype(str).str.replace(",", ""), errors="coerce"),
    }))

tri = (pd.concat(frames).dropna().drop_duplicates("Date")
         .sort_values("Date").reset_index(drop=True))
tri.to_csv(ROOT / "data" / "raw" / "nifty50_tri.csv", index=False)

print(f"{len(tri)} rows, {tri['Date'].min().date()} to {tri['Date'].max().date()}")
print(tri.groupby(tri["Date"].dt.year).size().to_string())
gaps = tri["Date"].diff().dt.days
print("Gaps longer than 7 days (date the gap ends on):")
print(tri.loc[gaps > 7, "Date"].dt.date.tolist() or "none")