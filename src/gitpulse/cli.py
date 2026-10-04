from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gitpulse import __version__
from gitpulse.history import NotARepository, current_branch, read_history, tracked_files
from gitpulse.metrics import analyse
from gitpulse.render import render_html, render_json, render_text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitpulse",
        description="Find the risky parts of any git repository.",
        epilog="example: gitpulse . --since '1 year ago' --format html -o report.html",
    )
    p.add_argument("repo", nargs="?", default=".", help="path to a git repository (default: .)")
    p.add_argument("--since", help="only consider commits after this date, e.g. '6 months ago'")
    p.add_argument("-n", "--max-commits", type=int, help="cap the number of commits read")
    p.add_argument("-l", "--limit", type=int, default=15, help="rows per table (default: 15)")
    p.add_argument("-f", "--format", choices=("text", "json", "html"), default="text")
    p.add_argument("-o", "--output", type=Path, help="write to a file instead of stdout")
    p.add_argument("--all-files", action="store_true",
                   help="include files that no longer exist in the working tree")
    p.add_argument("--fail-under", type=int, metavar="N",
                   help="exit 1 if the bus factor is below N (for CI)")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("-V", "--version", action="version", version=f"gitpulse {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()

    try:
        commits = read_history(repo, since=args.since, max_commits=args.max_commits)
        branch = current_branch(repo)
        tracked = None if args.all_files else tracked_files(repo)
    except NotARepository as exc:
        print(f"gitpulse: {exc}", file=sys.stderr)
        return 2

    if not commits:
        print("gitpulse: no commits found in that range", file=sys.stderr)
        return 2

    analysis = analyse(
        commits, repo=repo.name, branch=branch, tracked=tracked, limit=args.limit
    )

    if args.format == "json":
        out = render_json(analysis)
    elif args.format == "html":
        out = render_html(analysis)
    else:
        use_color = sys.stdout.isatty() and not args.no_color and not args.output
        out = render_text(analysis, color=use_color)

    if args.output:
        args.output.write_text(out, encoding="utf-8")
        print(f"gitpulse: wrote {args.output} "
              f"({analysis.total_commits} commits, bus factor {analysis.bus_factor})")
    else:
        print(out)

    if args.fail_under is not None and analysis.bus_factor < args.fail_under:
        print(f"gitpulse: bus factor {analysis.bus_factor} is below "
              f"--fail-under {args.fail_under}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
