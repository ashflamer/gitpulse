"""Turn raw commit history into risk signals."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from gitpulse.history import Commit

SECONDS_PER_DAY = 86_400


@dataclass(slots=True)
class FileRisk:
    path: str
    commits: int
    churn: int
    authors: int
    last_touched_days: float
    score: float = 0.0

    @property
    def primary_author_share(self) -> float:
        return self._share

    _share: float = 0.0


@dataclass(slots=True)
class Analysis:
    repo: str
    branch: str
    commits: list[Commit] = field(default_factory=list)
    hotspots: list[FileRisk] = field(default_factory=list)
    silos: list[tuple[str, str]] = field(default_factory=list)
    bus_factor: int = 0
    author_commits: Counter = field(default_factory=Counter)
    author_churn: Counter = field(default_factory=Counter)
    activity_by_month: dict[str, int] = field(default_factory=dict)
    activity_by_weekday: dict[str, int] = field(default_factory=dict)

    @property
    def total_commits(self) -> int:
        return len(self.commits)

    @property
    def total_authors(self) -> int:
        return len(self.author_commits)

    @property
    def first_commit(self) -> datetime | None:
        return min((c.date for c in self.commits), default=None)

    @property
    def last_commit(self) -> datetime | None:
        return max((c.date for c in self.commits), default=None)

    @property
    def age_days(self) -> float:
        if not self.commits:
            return 0.0
        return (self.last_commit - self.first_commit).total_seconds() / SECONDS_PER_DAY

    @property
    def commits_per_week(self) -> float:
        weeks = max(self.age_days / 7, 1.0)
        return round(self.total_commits / weeks, 2)


def _now() -> float:
    return datetime.now(tz=timezone.utc).timestamp()


def bus_factor(commits: list[Commit], threshold: float = 0.5) -> int:
    """How many people you'd have to lose before 50% of the work is orphaned.

    Sort authors by churn contributed, then count how many of the top authors
    it takes to cover `threshold` of total churn. A bus factor of 1 means one
    person wrote half the code.
    """
    churn_by_author: Counter[str] = Counter()
    for commit in commits:
        if commit.is_merge:
            continue
        churn_by_author[commit.author] += max(commit.churn, 1)

    total = sum(churn_by_author.values())
    if total == 0:
        return 0

    running = 0
    for index, (_, churn) in enumerate(churn_by_author.most_common(), start=1):
        running += churn
        if running / total >= threshold:
            return index
    return len(churn_by_author)


def hotspots(
    commits: list[Commit],
    *,
    limit: int = 15,
    tracked: set[str] | None = None,
    half_life_days: float = 90.0,
) -> list[FileRisk]:
    """Files that change constantly and recently - the ones most likely to break.

    Score = time-decayed churn x log(commit count) x single-author penalty.
    Recency uses exponential decay so a file hammered last week outranks one
    hammered two years ago with the same total churn.
    """
    now = _now()
    stats: dict[str, dict] = defaultdict(
        lambda: {"commits": 0, "churn": 0.0, "raw_churn": 0, "authors": Counter(), "last": 0}
    )

    for commit in commits:
        if commit.is_merge:
            continue
        age_days = max((now - commit.timestamp) / SECONDS_PER_DAY, 0.0)
        decay = 0.5 ** (age_days / half_life_days)
        for change in commit.files:
            if tracked is not None and change.path not in tracked:
                continue
            entry = stats[change.path]
            entry["commits"] += 1
            entry["raw_churn"] += change.churn
            entry["churn"] += change.churn * decay
            entry["authors"][commit.author] += change.churn
            entry["last"] = max(entry["last"], commit.timestamp)

    risks: list[FileRisk] = []
    for path, entry in stats.items():
        authors: Counter = entry["authors"]
        author_total = sum(authors.values()) or 1
        top_share = authors.most_common(1)[0][1] / author_total
        # One author owning everything compounds the risk of a hot file.
        silo_penalty = 1.0 + (top_share - 0.5 if top_share > 0.5 else 0.0)
        score = entry["churn"] * math.log1p(entry["commits"]) * silo_penalty

        risk = FileRisk(
            path=path,
            commits=entry["commits"],
            churn=entry["raw_churn"],
            authors=len(authors),
            last_touched_days=round((now - entry["last"]) / SECONDS_PER_DAY, 1),
            score=round(score, 2),
        )
        risk._share = round(top_share, 3)
        risks.append(risk)

    risks.sort(key=lambda r: r.score, reverse=True)
    return risks[:limit]


def knowledge_silos(
    commits: list[Commit],
    *,
    min_commits: int = 3,
    tracked: set[str] | None = None,
    limit: int = 15,
) -> list[tuple[str, str]]:
    """Files only one human has ever touched. If they leave, nobody knows it."""
    authors_by_file: dict[str, Counter] = defaultdict(Counter)
    for commit in commits:
        if commit.is_merge:
            continue
        for change in commit.files:
            if tracked is not None and change.path not in tracked:
                continue
            authors_by_file[change.path][commit.author] += 1

    solo = [
        (path, next(iter(authors)))
        for path, authors in authors_by_file.items()
        if len(authors) == 1 and sum(authors.values()) >= min_commits
    ]
    solo.sort(key=lambda item: -sum(authors_by_file[item[0]].values()))
    return solo[:limit]


def activity_by_month(commits: list[Commit]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for commit in commits:
        counter[commit.date.strftime("%Y-%m")] += 1
    return dict(sorted(counter.items()))


def activity_by_weekday(commits: list[Commit]) -> dict[str, int]:
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    counter: Counter[str] = Counter({n: 0 for n in names})
    for commit in commits:
        counter[names[commit.date.weekday()]] += 1
    return {n: counter[n] for n in names}


def analyse(
    commits: list[Commit],
    *,
    repo: str = ".",
    branch: str = "main",
    tracked: set[str] | None = None,
    limit: int = 15,
) -> Analysis:
    """Run every metric over a commit list."""
    author_commits: Counter[str] = Counter()
    author_churn: Counter[str] = Counter()
    for commit in commits:
        if commit.is_merge:
            continue
        author_commits[commit.author] += 1
        author_churn[commit.author] += commit.churn

    return Analysis(
        repo=repo,
        branch=branch,
        commits=commits,
        hotspots=hotspots(commits, limit=limit, tracked=tracked),
        silos=knowledge_silos(commits, tracked=tracked, limit=limit),
        bus_factor=bus_factor(commits),
        author_commits=author_commits,
        author_churn=author_churn,
        activity_by_month=activity_by_month(commits),
        activity_by_weekday=activity_by_weekday(commits),
    )
