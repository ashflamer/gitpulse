import pytest

from gitpulse.history import (
    FIELD_SEP, RECORD_SEP, NotARepository, _resolve_rename,
    current_branch, parse_log, read_history, tracked_files,
)


def test_reads_commits_from_real_repo(repo):
    commits = read_history(repo)
    assert len(commits) == 9
    assert {c.author for c in commits} == {"Alice", "Bob"}
    assert all(c.files for c in commits)


def test_file_stats_are_captured(repo):
    commits = read_history(repo)
    first = commits[-1]  # git log is newest-first
    assert first.files[0].path == "core.py"
    assert first.files[0].insertions > 0
    assert first.churn > 0


def test_tracked_files(repo):
    assert tracked_files(repo) == {"core.py", "util.py", "README.md"}


def test_current_branch(repo):
    assert current_branch(repo) == "main"


def test_non_repo_raises(tmp_path):
    with pytest.raises(NotARepository):
        read_history(tmp_path / "nope")


def test_parse_log_skips_binary_files():
    raw = (f"{RECORD_SEP}abc{FIELD_SEP}A{FIELD_SEP}a@x.com{FIELD_SEP}1700000000"
           f"{FIELD_SEP}msg\n-\t-\timage.png\n3\t1\tcode.py\n")
    (commit,) = parse_log(raw)
    assert [f.path for f in commit.files] == ["code.py"]
    assert commit.files[0].churn == 4


def test_parse_log_handles_empty_input():
    assert parse_log("") == []


def test_merge_commits_are_flagged():
    raw = (f"{RECORD_SEP}abc{FIELD_SEP}A{FIELD_SEP}a@x.com{FIELD_SEP}1700000000"
           f"{FIELD_SEP}Merge branch 'feature'\n")
    (commit,) = parse_log(raw)
    assert commit.is_merge


@pytest.mark.parametrize("raw,expected", [
    ("src/{old => new}/file.py", "src/new/file.py"),
    ("old.py => new.py", "new.py"),
    ("plain.py", "plain.py"),
])
def test_rename_resolution(raw, expected):
    assert _resolve_rename(raw) == expected
