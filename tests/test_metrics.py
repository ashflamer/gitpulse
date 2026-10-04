from gitpulse.history import Commit, FileChange, read_history
from gitpulse.metrics import analyse, bus_factor, hotspots, knowledge_silos


def make(author: str, ts: int, *files: tuple[str, int, int]) -> Commit:
    return Commit(sha="x", author=author, email=f"{author}@x.com", timestamp=ts,
                  subject="msg", files=[FileChange(p, i, d) for p, i, d in files])


def test_bus_factor_is_one_when_a_single_author_dominates():
    commits = [make("Alice", 1700000000, ("a.py", 100, 0)) for _ in range(9)]
    commits.append(make("Bob", 1700000000, ("b.py", 1, 0)))
    assert bus_factor(commits) == 1


def test_bus_factor_grows_with_even_distribution():
    commits = [make(name, 1700000000, ("f.py", 50, 0))
               for name in ("A", "B", "C", "D", "E", "F")]
    assert bus_factor(commits) >= 3


def test_bus_factor_of_empty_history_is_zero():
    assert bus_factor([]) == 0


def test_merge_commits_are_excluded_from_bus_factor():
    merge = make("Bot", 1700000000, ("x.py", 999, 0))
    merge.subject = "Merge pull request #1"
    assert bus_factor([merge, make("Alice", 1700000000, ("a.py", 10, 0))]) == 1


def test_recent_churn_outranks_old_churn():
    import time
    now = int(time.time())
    old = [make("A", now - 86400 * 700, ("old.py", 100, 100)) for _ in range(5)]
    new = [make("A", now - 86400 * 5, ("new.py", 100, 100)) for _ in range(5)]
    ranked = hotspots(old + new, limit=5)
    assert ranked[0].path == "new.py"


def test_knowledge_silos_need_a_minimum_history():
    commits = [make("Solo", 1700000000, ("lonely.py", 5, 0)) for _ in range(4)]
    commits += [make("Solo", 1700000000, ("shared.py", 5, 0)),
                make("Other", 1700000000, ("shared.py", 5, 0))]
    silos = knowledge_silos(commits, min_commits=3)
    assert ("lonely.py", "Solo") in silos
    assert all(path != "shared.py" for path, _ in silos)


def test_analyse_end_to_end_on_real_repo(repo):
    a = analyse(read_history(repo), repo="demo", branch="main")
    assert a.total_commits == 9
    assert a.total_authors == 2
    assert a.bus_factor == 1                       # Alice wrote most of the churn
    assert a.hotspots[0].path == "core.py"         # hammered six times
    assert ("core.py", "Alice") in a.silos
    assert a.age_days > 0


def test_hotspots_respects_tracked_filter():
    commits = [make("A", 1700000000, ("deleted.py", 10, 0), ("kept.py", 10, 0))]
    paths = {r.path for r in hotspots(commits, tracked={"kept.py"})}
    assert paths == {"kept.py"}
