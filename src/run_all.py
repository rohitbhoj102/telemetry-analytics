"""One command that rebuilds every generated output from the raw data, in the right order.

    python src/run_all.py            # everything (about 3 minutes)
    python src/run_all.py --from insights   # restart at a named step

Steps run as separate processes with the current Python; the first failure stops the run (each script
has its own built-in checks). Order: profile -> clean -> dq -> model -> insights (first-round rows)
-> candidate-round rows (n_) -> round-2 numbers -> final rows (f_) -> final charts -> deck numbers -> Tableau export -> dashboard data.
`insights.py` keeps the n_ and f_ rows already in reports/insights/key_numbers.csv; the later steps
replace only their own rows, so the file ends with every row regardless of what ran before.
Notebooks and the draft deck script are not part of this run.
"""
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
STEPS = [
    ("profile", "profile.py"), ("inspect", "inspect_decoded.py"), ("dups", "dup_diagnostics.py"), ("cumulative", "cumulative_check.py"),
    ("spec", "build_parsing_spec.py"), ("links", "link_checks.py"), ("bands", "check_band_order.py"),
    ("clean", "build_clean.py"), ("dq", "dq.py"), ("model", "model.py"),
    ("insights", "insights.py"),               # key_numbers.csv first-round rows (174), step6_consistency.csv, figures/final, figures/slide
    ("candidates", "insights3.py"),            # n_ rows + reports/insights/n_*.csv   (needs the model; recomputes the round-2 numbers it uses)
    ("round2", "insights2.py"),                # key_numbers_v2.csv (working file; the deck uses key_numbers.csv only)
    ("final", "insights_final.py"),            # f_ rows (I1-I4) + reports/insights/f_*.csv
    ("charts", "charts_final.py"),             # reports/figures/final_v2/*
    ("decknumbers", "make_deck_numbers.py"),   # reports/insights/deck_numbers.md (from the f_ rows)
    ("tableau", "tableau_export.py"),          # data/model/tableau/*.csv
    ("dashboard", "make_dashboard_data.py"),   # data/model/tableau/insights_dashboard.csv (from the f_ rows; checks values against key_numbers.csv)
]


def main(argv):
    start = 0
    if "--from" in argv:
        names = [n for n, _ in STEPS]
        start = names.index(argv[argv.index("--from") + 1])
    t0 = time.time()
    for name, script in STEPS[start:]:
        t = time.time()
        print("== %-10s python src/%s" % (name, script), flush=True)
        r = subprocess.run([sys.executable, str(SRC / script)], cwd=str(ROOT))
        if r.returncode != 0:
            print("FAILED at step '%s' (exit %d)" % (name, r.returncode))
            return r.returncode
        print("   done in %.0f s" % (time.time() - t), flush=True)
    print("all steps finished in %.0f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
