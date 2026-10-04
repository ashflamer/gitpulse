import subprocess
from pathlib import Path

import pytest


def git(repo: Path, *args: str, **env_extra: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": env_extra.get("name", "Test User"),
        "GIT_AUTHOR_EMAIL": env_extra.get("email", "test@example.com"),
        "GIT_COMMITTER_NAME": env_extra.get("name", "Test User"),
        "GIT_COMMITTER_EMAIL": env_extra.get("email", "test@example.com"),
        "GIT_AUTHOR_DATE": env_extra.get("date", "2024-01-01T12:00:00"),
        "GIT_COMMITTER_DATE": env_extra.get("date", "2024-01-01T12:00:00"),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(repo),
    }
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small repo: alice owns core.py, bob owns util.py, core.py is hot."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)

    def commit(filename: str, content: str, author: str, email: str, date: str):
        (tmp_path / filename).write_text(content)
        git(tmp_path, "add", filename)
        git(tmp_path, "commit", "-q", "-m", f"touch {filename}",
            name=author, email=email, date=date)

    for i in range(6):
        commit("core.py", "x = 1\n" * (i + 2), "Alice", "alice@example.com",
               f"2024-0{i + 1}-10T10:00:00")
    for i in range(2):
        commit("util.py", "y = 2\n" * (i + 1), "Bob", "bob@example.com",
               f"2024-0{i + 3}-11T10:00:00")
    commit("README.md", "# hi\n", "Bob", "bob@example.com", "2024-06-12T10:00:00")
    return tmp_path
