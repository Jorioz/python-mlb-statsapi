"""Sample seeded mutants from a finished mutmut run and export them as patches.

Run from the repo root on Linux/WSL after `mutmut run` (mutmut 3 does not run on
native Windows):

    python experiment/scripts/sample_mutants.py --seed 4150 --count 10

Outputs (all committed so the sample is reproducible without rerunning mutmut):
    experiment/mutation/mutmut-results.txt   every mutant and its status
    experiment/mutation/summary.csv          killed/survived/score per module
    experiment/defects/mutants/M01-*.patch   one git-applyable patch per sample
    experiment/defects/mutants/sample.csv    the sampled mutant names

Only killed mutants are sampled: a mutant the full offline suite cannot kill
is invisible to every CI config, so it cannot tell the configs apart.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUTMUT = [sys.executable, "-m", "mutmut"]


def run(args: list[str]) -> str:
    out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout


def module_of(name: str) -> str:
    # mlbstatsapi._http.x__build_http_error__mutmut_3 -> mlbstatsapi/_http.py
    return name.split(".x")[0].replace(".", "/") + ".py"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4150)
    ap.add_argument("--count", type=int, default=10)
    opts = ap.parse_args()

    raw = run(MUTMUT + ["results", "--all", "true"])
    results: dict[str, str] = {}
    for line in raw.splitlines():
        m = re.match(r"\s*(\S+): (.+)$", line)
        if m:
            results[m.group(1)] = m.group(2).strip()

    mut_dir = ROOT / "experiment" / "mutation"
    mut_dir.mkdir(parents=True, exist_ok=True)
    (mut_dir / "mutmut-results.txt").write_text(
        "".join(f"{k}: {v}\n" for k, v in sorted(results.items())), encoding="utf-8"
    )

    per_module: dict[str, Counter] = {}
    for name, status in results.items():
        per_module.setdefault(module_of(name), Counter())[status] += 1
    with open(mut_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["module", "total", "killed", "survived", "other", "mutation_score_pct"])
        totals = Counter()
        for mod in sorted(per_module):
            c = per_module[mod]
            total = sum(c.values())
            other = total - c["killed"] - c["survived"]
            w.writerow([mod, total, c["killed"], c["survived"], other, f"{100 * c['killed'] / total:.1f}"])
            totals.update(c)
        total = sum(totals.values())
        w.writerow(["ALL", total, totals["killed"], totals["survived"],
                    total - totals["killed"] - totals["survived"],
                    f"{100 * totals['killed'] / total:.1f}"])

    killed = sorted(n for n, s in results.items() if s == "killed")
    sample = random.Random(opts.seed).sample(killed, opts.count)

    out_dir = ROOT / "experiment" / "defects" / "mutants"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("M*.patch"):
        old.unlink()
    rows = []
    for i, name in enumerate(sample, 1):
        mod = module_of(name)
        src = ROOT / mod
        original = src.read_bytes()
        try:
            # `mutmut show` prints a function-relative diff that `git apply`
            # rejects, so write the mutant into the real file and diff that.
            run(MUTMUT + ["apply", name])
            mutated = src.read_bytes()
        finally:
            src.write_bytes(original)
        orig_copy = out_dir / "_orig.py"
        mut_copy = out_dir / "_mut.py"
        orig_copy.write_bytes(original)
        mut_copy.write_bytes(mutated)
        diff = subprocess.run(
            ["diff", "-u", "--label", f"a/{mod}", "--label", f"b/{mod}", str(orig_copy), str(mut_copy)],
            capture_output=True, text=True,
        ).stdout
        orig_copy.unlink()
        mut_copy.unlink()
        if not diff:
            raise SystemExit(f"mutmut apply produced no change for {name}")
        patch = f"diff --git a/{mod} b/{mod}\n{diff}"
        defect_id = f"M{i:02d}"
        (out_dir / f"{defect_id}.patch").write_text(patch, encoding="utf-8", newline="\n")
        rows.append([defect_id, name, mod])

    with open(out_dir / "sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["defect_id", "mutmut_name", "module", "seed"])
        for r in rows:
            w.writerow(r + [opts.seed])

    print(f"{len(results)} mutants, {len(killed)} killed; sampled {len(rows)} with seed {opts.seed}")
    for r in rows:
        print(" ", *r)


if __name__ == "__main__":
    main()
