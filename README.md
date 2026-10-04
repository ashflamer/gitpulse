# gitpulse

**Find the risky parts of any git repository.** Bus factor, churn hotspots, knowledge silos — from `git log` alone. No API token, no third-party dependencies, works offline.

[![CI](https://github.com/ashflamer/gitpulse/actions/workflows/ci.yml/badge.svg)](https://github.com/ashflamer/gitpulse/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](pyproject.toml)

---

## Why

Every codebase has a file that everybody is scared of. `gitpulse` finds it, and tells you who the only person is that understands it.

Real run against [`pallets/click`](https://github.com/pallets/click):

```console
$ gitpulse ~/code/click --since "2 years ago"

gitpulse  click  (main)
  873 commits · 98 authors · 2024-05-22 → 2026-09-23 · 7.16/week

BUS FACTOR  2  AT RISK
  2 person(s) account for 50% of all code churn.

ACTIVITY  last 24 months
   ▂▁    ▄▂▁▄▃▂▁   ▁▄█▁▂▂▁
  2024-10          2026-09

TOP CONTRIBUTORS
  Rowlando13             ████████████████████████   224 (25.7%)
  Kevin Deldycke         ████████████████████····   183 (21.0%)
  Edward G               ████████················    70 ( 8.0%)
  David Lord             ███████·················    66 ( 7.6%)

HOTSPOTS  changed often, changed recently
  file                                         commits   churn authors     last
  CHANGES.md                                        42    3291       6      12d
  tests/test_options.py                             51    4672      15      23d
  src/click/core.py                                102    3264      27      23d
  uv.lock                                           28    3673       6      12d

KNOWLEDGE SILOS  only one person has ever touched these
  .github/workflows/nightly.yaml                       Kevin Deldycke
  docs/contributing.md                                 Kevin Deldycke

  weekend commits: 239 (27%) ← burnout signal
```

There's also a **self-contained HTML report** — one file, no CDN, no JavaScript. See [`examples/sample-report.html`](examples/sample-report.html).

## Install

```bash
pip install gitpulse
pipx install gitpulse
git clone https://github.com/ashflamer/gitpulse && cd gitpulse && pip install -e ".[dev]"
```

## Usage

```bash
gitpulse                                        # analyse the repo you're standing in
gitpulse ~/code/some-project                    # or any other one
gitpulse . --since "6 months ago"               # recent history only
gitpulse . --format html -o report.html         # shareable dashboard
gitpulse . --format json | jq '.summary'        # pipe into anything
gitpulse . --fail-under 2                       # CI gate on bus factor
gitpulse . --all-files                          # include deleted files
```

| Flag | Description |
| --- | --- |
| `--since` | Any git date expression: `"6 months ago"`, `2024-01-01` |
| `-n, --max-commits` | Cap how much history is read (fast on huge repos) |
| `-l, --limit` | Rows per table, default 15 |
| `-f, --format` | `text`, `json`, `html` |
| `-o, --output` | Write to a file |
| `--fail-under N` | Exit `1` when bus factor `< N` |
| `--all-files` | Don't filter to files that still exist |

## The metrics

### Bus factor

> How many people would have to leave before 50% of the codebase is orphaned?

Authors are ranked by lines of churn contributed. We walk down that list accumulating churn and return how many authors it takes to cross 50%. **A bus factor of 1 means one person wrote half your code.** Merge commits are excluded — they inflate totals without representing authored work.

| Value | Reading |
| --- | --- |
| 1 | CRITICAL |
| 2 | AT RISK |
| 3–4 | OK |
| 5+ | HEALTHY |

### Hotspots

Files that change *a lot* and changed *recently*. Total churn alone is misleading: a file rewritten 50 times in 2019 and untouched since isn't a risk, it's settled.

```
score = Σ(churn × 0.5^(age_days / 90)) × log(1 + commits) × silo_penalty
```

- **Exponential decay, 90-day half-life** — a change from last week counts fully, one from a year ago counts ~6%.
- **`log(1 + commits)`** — rewarding frequency without letting a single noisy file dominate.
- **`silo_penalty`** — scales up when one author owns >50% of the file's churn. Hot *and* solo-owned is the dangerous combination.

High score = where your next bug is most likely to come from, and where tests pay for themselves.

### Knowledge silos

Files with exactly one author across their whole history and at least 3 commits. These are your single points of failure.

### Weekend commits

Share of commits landing Saturday/Sunday. Over 25% gets flagged. It's not a code metric; it's a team-health one.

## In CI

Gate merges on team resilience:

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }      # gitpulse needs full history, not a shallow clone
- run: pip install gitpulse
- run: gitpulse . --fail-under 2
```

Or publish the report to the Actions summary tab — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml), which runs gitpulse on itself every push.

## Design notes

- **No `GitPython`, no `pygit2`.** One `git log --numstat` subprocess with a `\x1e`/`\x1f`-delimited format string that commit messages can't break.
- **Renames are followed.** `src/{old => new}/f.py` resolves to the new path, so history isn't fragmented at rename boundaries.
- **Binary files are skipped** (git reports `-` instead of line counts).
- **Deleted files are filtered** against `git ls-files` by default — no point flagging a hotspot that no longer exists.
- **HTML output is escaped** — a branch named `<script>` can't inject into your report (there's a test for exactly this).

## Development

```bash
pip install -e ".[dev]"
pytest -q          # 30 tests, including a real git repo built in a fixture
ruff check .
```

The test suite shells out to real `git` to build a fixture repo with known authorship, so the metrics are verified against actual git behaviour rather than mocks.

## Roadmap

- [ ] Coupling analysis — files that always change together
- [ ] `--compare <ref>` to diff health between two points in time
- [ ] Per-directory rollups for monorepos
- [ ] `.mailmap` support to merge duplicate author identities

## License

MIT © ashflamer
