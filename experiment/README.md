# CIS*4150 experiment: CI speed vs. defect detection

Branch `ci-experiment` is upstream tag **v1.1.1** (`d8eb32c`) plus only the
files listed here. No library code is changed on this branch; seeded defects
live on `defect/*` branches made from it.

## What changed from v1.1.1

| Path | Why |
|---|---|
| `.github/workflows/ci-{a,b,c,d}-*.yml` | The four pipelines under test |
| `.github/workflows/claude*.yml`, `docs.yml` | Removed: need upstream secrets / Pages and would add unrelated runs |
| `.github/workflows/build-and-test.yml`, `external-tests.yml` | Kept unchanged: `tests/test_release_validation.py` reads them. They only trigger on `main`/`release/**`, a weekly schedule (off by default in forks) or manual dispatch, so they never run on experiment branches |
| `experiment/ci/requirements-ci.txt` | Pinned dependencies for every pipeline (Python 3.12) |
| `pyproject.toml` `[tool.mutmut]` | Mutation-testing scope |

## The four pipelines

All run on `ubuntu-latest`, Python 3.12, the same pinned requirements, and
trigger on pushes to `ci-experiment`, `replay/**`, `defect/**`, `timing/**`
(or manual dispatch). Each uploads JUnit XML so detection can be scored on
offline tests only.

| Config | Workflow | Tests | Cache | Parallel | Jobs |
|---|---|---|---|---|---|
| A Baseline | `ci-a-baseline.yml` | all (offline + live) | none | no | 1 |
| B Cached + parallel | `ci-b-cached-parallel.yml` | all | pip (`setup-python` cache) | `pytest -n auto` | 1 |
| C Staged | `ci-c-staged.yml` | offline, then live | none | no | 2 (`live` `needs: offline`) |
| D Selective | `ci-d-selective.yml` | testmon-affected only | `.testmondata` via `actions/cache` | no | 1 |

C and D change one thing each relative to A, so their effect is not confounded
with caching or parallelism. D treats "no tests selected" (pytest exit 5) as a
pass.

**Selective setup:** make `ci-experiment` the fork's default branch and run
CI-D there once on clean v1.1.1. That seeds `.testmondata`; `defect/*` and
`replay/*` branches fall back to the default branch's cache.

## Test suite at v1.1.1

- 1157 offline tests, 149 live MLB API tests (148 pass, 1 skipped, Nov 10 2026)
- Coverage on the offline suite (`coverage run --branch`, local Python 3.12):
  **94.8% statements (3520/3712), 71.7% branches (380/530)**. Full report in
  `coverage/`.

## Mutation testing

mutmut 3.8.1 on `mlbstatsapi/mlb_dataadapter.py` and `mlbstatsapi/_http.py`
(the sync request/response path), run under WSL Ubuntu / Python 3.10 because
mutmut 3 does not run on native Windows.

| Module | Mutants | Killed | Survived | Score |
|---|---|---|---|---|
| `_http.py` | 68 | 38 | 30 | 55.9% |
| `mlb_dataadapter.py` | 239 | 185 | 54 | 77.4% |
| **Total** | **307** | **223** | **84** | **72.6%** |

`mlb_dataadapter.py` has 100% statement and branch coverage but a 77% mutation
score, a useful contrast for the report.

Five tests are excluded **from mutation runs only** (see `pyproject.toml`): three
"warning points to caller line" tests inspect stack frames, which the mutmut
trampoline changes, and two roster-parser tests mutate a module-level payload,
so they fail when mutmut reruns the suite in one process. (That second item is
a latent test-isolation issue in the upstream suite.)

Reproduce (Linux/WSL, repo root):

```bash
pip install -r experiment/ci/requirements-ci.txt mutmut==3.8.1 && pip install --no-deps -e .
mutmut run --max-children 10
python experiment/scripts/sample_mutants.py --seed 4150 --count 10
```

## Seeded defects (15)

Every defect applies cleanly to v1.1.1 (`git apply`) and fails the full
offline suite. "Selected" is what testmon chose locally after a clean seed run.

### Real bugs restored from history (5)

| ID | Fix undone | Modules | Offline tests failing | testmon selected |
|---|---|---|---|---|
| RB1 | `a93b70e` HTTP errors lost when context extraction fails | `_http.py` | 2 | 132 |
| RB2 | `7344967` models reject inconsistent MLB API shapes | 6 model modules | 67 | 20 (17 fail) |
| RB3 | `0e3016c` `gamePks` schedule queries rejected without a date | `mlb_api.py`, `_helpers/schedule.py` | 3 | 62 |
| RB4 | `8ecb8c6` env proxies ignored by library-created async clients | `_async_transport.py` | 8 | 175 |
| RB5 | `e63e5ef` `MlbResult` mutates the caller's dict | `mlb_dataadapter.py` | 2 | 397 |

RB1, RB2 revert cleanly with `git revert`-style reverse patches. RB3, RB4, RB5
were restored by hand because later refactors moved the code; each patch
re-creates the original defect at its current location. Candidates rejected:
`717a58d`, `65c800a`, `59cdebd`, `ddb0895` revert cleanly but no offline test
fails; `113c880` is a breaking type change, not a bug.

### Mutants (10, seed 4150, sampled from killed mutants)

Surviving mutants are invisible to every config, so they cannot separate them.

| ID | Module | Mutation | Offline tests failing |
|---|---|---|---|
| M01 | `_http.py` | drop `status_code=` arg in `_build_http_error` | 132 |
| M02 | `mlb_dataadapter.py` | `pop("copyright")` → `pop(None)` | 5 |
| M03 | `_http.py` | `frame = inspect.currentframe()` → `None` | 79 |
| M04 | `mlb_dataadapter.py` | `_build_http_error(response, …)` → `(None, …)` | 1 |
| M05 | `mlb_dataadapter.py` | drop `url=` arg in `_build_http_error` | 75 |
| M06 | `mlb_dataadapter.py` | `status_code=response.status_code` → `None` | 1 |
| M07 | `mlb_dataadapter.py` | retry `allowed_methods` `"GET"` → `"get"` | 26 |
| M08 | `mlb_dataadapter.py` | `status_code <= 299` → `< 299` | 1 |
| M09 | `mlb_dataadapter.py` | `max_retries=create_retry_policy()` → `None` | 5 |
| M10 | `mlb_dataadapter.py` | `"https://"` → `"HTTPS://"` adapter mount | 5 |

M04, M06, M08 are each caught by a single test: the strongest probes for
selective testing.

## Scripts

| Script | Does |
|---|---|
| `scripts/sample_mutants.py` | Exports mutmut results, per-module scores and the seeded mutant patches |
| `scripts/make_defect_branches.sh [--push]` | One `defect/<ID>` branch per patch from `ci-experiment` |
| `scripts/collect_runs.py --repo <owner>/python-mlb-statsapi` | Workflow wall-clock, queue time, time to first failure, per-job times → `results/runs.csv` |

## Local pilot timings (Windows, 12 threads; not CI numbers)

| | Time |
|---|---|
| Offline suite, serial | 40 s |
| Offline suite, `-n auto` | 21 s |
| Live suite, serial | 46 s |
| Offline, testmon, cold (records DB) | 44 s |
| Offline, testmon, no change | <1 s (0 selected) |

The GitHub Actions pilot (one run per config) is pending the fork push.
