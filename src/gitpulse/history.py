"""Read and parse git history without any third-party git bindings."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Unlikely to appear in a commit message.
RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"
LOG_FORMAT = FIELD_SEP.join(["%H", "%an", "%ae", "%at", "%s"])


class NotARepository(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    insertions: int
    deletions: int

    @property
    def churn(self) -> int:
        return self.insertions + self.deletions


@dataclass(slots=True)
class Commit:
    sha: str
    author: str
    email: str
    timestamp: int
    subject: str
    files: list[FileChange] = field(default_factory=list)

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @property
    def churn(self) -> int:
        return sum(f.churn for f in self.files)

    @property
    def is_merge(self) -> bool:
        return self.subject.startswith("Merge ")


def run_git(repo: Path, *args: str) -> str:
    """Run a git command, raising a clear error if this isn't a repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment dependent
        raise NotARepository("git executable not found on PATH") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            raise NotARepository(f"{repo} is not a git repository")
        raise NotARepository(stderr or f"git {' '.join(args)} failed")
    return result.stdout


def parse_log(raw: str) -> list[Commit]:
    """Parse the output of `git log --numstat` in our custom format."""
    commits: list[Commit] = []
    for block in raw.split(RECORD_SEP):
        block = block.strip("\n")
        if not block:
            continue
        header, _, body = block.partition("\n")
        parts = header.split(FIELD_SEP)
        if len(parts) < 5:
            continue
        sha, author, email, ts, subject = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            timestamp = int(ts)
        except ValueError:
            continue

        files: list[FileChange] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            added, removed, path = cols
            if added == "-" or removed == "-":
                continue  # binary file
            # Handle rename syntax: "old/{a => b}/file" -> take the new path.
            if " => " in path:
                path = _resolve_rename(path)
            files.append(FileChange(path=path, insertions=int(added), deletions=int(removed)))

        commits.append(Commit(
            sha=sha, author=author.strip(), email=email.strip().lower(),
            timestamp=timestamp, subject=subject.strip(), files=files,
        ))
    return commits


def _resolve_rename(path: str) -> str:
    """`src/{old => new}/file.py` -> `src/new/file.py`."""
    if "{" in path and "}" in path:
        before, rest = path.split("{", 1)
        inner, after = rest.split("}", 1)
        _, _, new = inner.partition(" => ")
        return f"{before}{new.strip()}{after}".replace("//", "/")
    _, _, new = path.partition(" => ")
    return new.strip() or path


def read_history(repo: Path, *, since: str | None = None, max_commits: int | None = None) -> list[Commit]:
    """Load commit history with per-file line statistics."""
    args = [
        "log",
        f"--pretty=format:{RECORD_SEP}{LOG_FORMAT}",
        "--numstat",
        "--find-renames",
        "--no-color",
    ]
    if since:
        args.append(f"--since={since}")
    if max_commits:
        args.append(f"-n{max_commits}")
    return parse_log(run_git(Path(repo), *args))


def tracked_files(repo: Path) -> set[str]:
    """Files that currently exist in the index (so we ignore deleted ones)."""
    out = run_git(Path(repo), "ls-files")
    return {line for line in out.splitlines() if line}


def current_branch(repo: Path) -> str:
    try:
        return run_git(Path(repo), "rev-parse", "--abbrev-ref", "HEAD").strip()
    except NotARepository:
        return "unknown"
