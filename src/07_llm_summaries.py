"""STEP 7 - Plain-English risk summary per fund with the Claude API (responsibly).

Guard-rails that make this portfolio-worthy rather than a gimmick:
  1. The model only sees pre-computed numbers formatted as strings - never raw NAVs.
  2. The system prompt forbids predictions and buy/sell/hold language.
  3. Every number in the output is checked against the numbers we supplied.
  4. Banned phrases are scanned. Failures are flagged in the CSV, not hidden.
  5. Spot-check at least 10 summaries by hand and describe the hit-rate in your README.

Setup: pip install anthropic ; export ANTHROPIC_API_KEY=...
Run:   python src/07_llm_summaries.py            (uses the API)
       python src/07_llm_summaries.py --dry-run  (template text, no API key needed)
"""
import os
import re
import sys

import pandas as pd

import common
import config

SYSTEM = (
    "You write short, neutral summaries of historical mutual fund risk and return data for "
    "educational use. Rules: (1) Use ONLY the numbers in the data provided and copy them "
    "exactly as written. (2) Describe the past only; never predict, forecast or imply future "
    "performance. (3) Never recommend, rate, or use words like buy, sell, hold, should, best. "
    "(4) 3 sentences maximum, plain English for a first-time investor. (5) Mention at least "
    "one risk measure (drawdown or volatility) and compare to the category median supplied."
)
BANNED = re.compile(r"\b(buy|sell|hold|should|recommend\w*|best|guarantee\w*|will|expected to|"
                    r"outperform in the future|safe|sure)\b", re.I)
NUM = re.compile(r"\d+(?:\.\d+)?")


def pct(x, digits=1):
    return f"{x * 100:.{digits}f}%"


def build_facts(row, cat_median):
    facts = {
        "window": f"{int(row['window_years'])} years",
        "annual_return": pct(row["cagr"]),
        "benchmark_return": pct(row["bench_cagr"]),
        "volatility": pct(row["volatility"]),
        "category_median_volatility": pct(cat_median["volatility"]),
        "max_drawdown": pct(abs(row["max_drawdown"])),
        "category_median_max_drawdown": pct(abs(cat_median["max_drawdown"])),
        "sharpe_ratio": f"{row['sharpe']:.2f}",
        "beta": f"{row['beta']:.2f}",
        "rank_in_category_by_sharpe": str(int(row["sharpe_rank_in_category"])),
    }
    return facts


def check_output(text, facts, window_years, fund_name=""):
    allowed = set(NUM.findall(fund_name))        # digits that belong to the fund's own name
    for v in facts.values():
        allowed.update(NUM.findall(v))
    allowed.update({str(window_years), "3"})                 # '3 sentences', window length
    unknown = [n for n in NUM.findall(text) if n not in allowed]
    flags = []
    if unknown:
        flags.append("numbers_not_in_data:" + ",".join(sorted(set(unknown))))
    banned = sorted({m.group(0).lower() for m in BANNED.finditer(text)})
    if banned:
        flags.append("banned_words:" + ",".join(banned))
    return ";".join(flags)


def template_text(name, facts):
    return (f"Over the last {facts['window']}, {name} returned {facts['annual_return']} a year "
            f"versus {facts['benchmark_return']} for the benchmark. Its worst fall from a peak was "
            f"{facts['max_drawdown']} (category median {facts['category_median_max_drawdown']}), "
            f"with volatility of {facts['volatility']}.")


def call_claude(client, name, category, facts):
    lines = "\n".join(f"- {k}: {v}" for k, v in facts.items())
    msg = client.messages.create(
        model=config.LLM_MODEL, max_tokens=300, system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"Fund: {name}\nCategory: {category}\nHistorical data:\n{lines}\n\n"
                              "Write the summary."}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def main():
    dry = "--dry-run" in sys.argv
    client = None
    if not dry:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("Set ANTHROPIC_API_KEY or use --dry-run.")
        import anthropic
        client = anthropic.Anthropic()

    metrics = pd.read_csv(config.PROCESSED_DIR / "fact_metrics.csv")
    w = metrics[metrics["window_years"] == config.LLM_SUMMARY_WINDOW].copy()
    med = w.groupby("category")[["volatility", "max_drawdown"]].median()
    out = []
    for _, row in w.iterrows():
        facts = build_facts(row, med.loc[row["category"]])
        text = template_text(row["scheme_name"], facts) if dry else \
            call_claude(client, row["scheme_name"], row["category"], facts)
        out.append({"scheme_code": row["scheme_code"], "scheme_name": row["scheme_name"],
                    "category": row["category"], "window_years": config.LLM_SUMMARY_WINDOW,
                    "summary": text, "source": "template" if dry else config.LLM_MODEL,
                    "validation_flags": check_output(text, facts, config.LLM_SUMMARY_WINDOW, row["scheme_name"])})
    df = pd.DataFrame(out)
    df.to_csv(config.PROCESSED_DIR / "llm_summaries.csv", index=False)
    print(f"{len(df)} summaries, {int((df['validation_flags'] != '').sum())} flagged for review")
    print(df.iloc[0]["summary"])


if __name__ == "__main__":
    main()
