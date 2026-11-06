"""Run the whole pipeline. Use --offline-test to run steps 3-8 on synthetic data."""
import subprocess
import sys

STEPS = ["src/01_select_and_download.py", "src/02_build_database.py", "src/03_metrics.py",
         "src/04_sip_vs_lumpsum.py", "src/05_expense_impact.py", "src/06_correlation_clusters.py",
         "src/07_llm_summaries.py", "src/08_validate_and_export.py"]

if __name__ == "__main__":
    offline = "--offline-test" in sys.argv
    steps = STEPS[2:] if offline else STEPS
    if offline:
        subprocess.check_call([sys.executable, "tests/make_synthetic_data.py"])
    for s in steps:
        args = [sys.executable, s]
        if offline and s.endswith("07_llm_summaries.py"):
            args.append("--dry-run")
        print(f"\n=== {s} ===")
        subprocess.check_call(args)
