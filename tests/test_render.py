import json

from gitpulse.history import read_history
from gitpulse.metrics import analyse
from gitpulse.render import bar, render_html, render_json, render_text, sparkline


def test_sparkline_scales_to_peak():
    assert sparkline([0, 5, 10])[-1] == "█"
    assert len(sparkline([1, 2, 3, 4])) == 4
    assert sparkline([]) == ""
    assert sparkline([0, 0, 0]) == "   "


def test_bar_is_width_bounded():
    assert len(bar(5, 10, width=20)) == 20
    assert bar(0, 0) == ""


def test_text_report_mentions_key_sections(repo):
    a = analyse(read_history(repo), repo="demo")
    out = render_text(a, color=False)
    for section in ("BUS FACTOR", "TOP CONTRIBUTORS", "HOTSPOTS", "KNOWLEDGE SILOS"):
        assert section in out
    assert "\033[" not in out  # color disabled


def test_json_report_is_valid(repo):
    a = analyse(read_history(repo), repo="demo")
    payload = json.loads(render_json(a))
    assert payload["summary"]["commits"] == 9
    assert payload["hotspots"][0]["path"] == "core.py"


def test_html_report_is_self_contained(repo):
    a = analyse(read_history(repo), repo="demo")
    out = render_html(a)
    assert out.startswith("<!doctype html>")
    assert "core.py" in out
    assert "<script" not in out      # no JS needed
    assert "http://" not in out      # no external assets


def test_html_escapes_untrusted_names(repo):
    a = analyse(read_history(repo), repo="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in render_html(a)
    assert "&lt;script&gt;" in render_html(a)
