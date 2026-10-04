import json

from gitpulse.cli import main


def test_text_output(repo, capsys):
    assert main([str(repo), "--no-color"]) == 0
    assert "BUS FACTOR" in capsys.readouterr().out


def test_json_output(repo, capsys):
    assert main([str(repo), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["authors"] == 2


def test_html_written_to_file(repo, tmp_path, capsys):
    out = tmp_path / "r.html"
    assert main([str(repo), "--format", "html", "-o", str(out)]) == 0
    assert out.read_text().startswith("<!doctype html>")


def test_fail_under_gate(repo, capsys):
    assert main([str(repo), "--no-color", "--fail-under", "3"]) == 1
    assert main([str(repo), "--no-color", "--fail-under", "1"]) == 0


def test_not_a_repo_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nothing")]) == 2
