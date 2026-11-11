"""Collect GitHub Actions timings for the four experiment workflows into a CSV.

Needs the GitHub CLI (`gh`) logged in with read access to the fork:

    python experiment/scripts/collect_runs.py --repo <owner>/python-mlb-statsapi
    python experiment/scripts/collect_runs.py --repo <owner>/python-mlb-statsapi --branch defect/RB1

One row per completed workflow run (latest attempt). Times are seconds.
  wall_clock_s     first job start -> last job end (excludes queueing before
                   the first job starts; includes the wait between staged jobs)
  queue_s          run created -> first job start
  ttff_s           first job start -> end of the first failed job (blank if green)
  jobs             job:conclusion:seconds for every job, ';'-separated
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path

CONFIGS = {
    "ci-a-baseline.yml": "A-baseline",
    "ci-b-cached-parallel.yml": "B-cached-parallel",
    "ci-c-staged.yml": "C-staged",
    "ci-d-selective.yml": "D-selective",
}
FIELDS = [
    "config", "run_id", "run_attempt", "branch", "head_sha", "event", "conclusion",
    "created_at", "wall_clock_s", "queue_s", "ttff_s", "jobs", "html_url",
]


def gh_json(path: str) -> list | dict:
    out = subprocess.run(
        ["gh", "api", "-X", "GET", "--paginate", "--slurp", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def secs(a: datetime | None, b: datetime | None) -> str:
    return f"{(b - a).total_seconds():.0f}" if a and b else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name of the fork")
    ap.add_argument("--branch", help="only runs on this branch")
    ap.add_argument("--out", default="experiment/results/runs.csv")
    opts = ap.parse_args()

    rows = []
    for workflow, config in CONFIGS.items():
        query = f"repos/{opts.repo}/actions/workflows/{workflow}/runs?per_page=100&status=completed"
        if opts.branch:
            query += f"&branch={opts.branch}"
        pages = gh_json(query)
        for run in (r for page in pages for r in page["workflow_runs"]):
            job_pages = gh_json(f"repos/{opts.repo}/actions/runs/{run['id']}/jobs?per_page=100")
            jobs = [j for page in job_pages for j in page["jobs"]]
            starts = [ts(j["started_at"]) for j in jobs if j["started_at"]]
            ends = [ts(j["completed_at"]) for j in jobs if j["completed_at"]]
            first_start = min(starts) if starts else None
            failed_ends = [ts(j["completed_at"]) for j in jobs if j["conclusion"] == "failure"]
            rows.append({
                "config": config,
                "run_id": run["id"],
                "run_attempt": run["run_attempt"],
                "branch": run["head_branch"],
                "head_sha": run["head_sha"],
                "event": run["event"],
                "conclusion": run["conclusion"],
                "created_at": run["created_at"],
                "wall_clock_s": secs(first_start, max(ends) if ends else None),
                "queue_s": secs(ts(run["created_at"]), first_start),
                "ttff_s": secs(first_start, min(failed_ends)) if failed_ends else "",
                "jobs": ";".join(
                    f"{j['name']}:{j['conclusion']}:{secs(ts(j['started_at']), ts(j['completed_at']))}"
                    for j in jobs
                ),
                "html_url": run["html_url"],
            })

    out = Path(opts.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["config"], r["created_at"])))
    print(f"wrote {len(rows)} runs to {out}")


if __name__ == "__main__":
    main()
