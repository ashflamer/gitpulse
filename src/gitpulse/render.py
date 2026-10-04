"""Render an Analysis as terminal text, JSON, or a standalone HTML page."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from gitpulse.metrics import Analysis

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, YELLOW, GREEN, CYAN, MAGENTA = "\033[31m", "\033[33m", "\033[32m", "\033[36m", "\033[35m"

BLOCKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    """Unicode sparkline - no plotting library required."""
    if not values:
        return ""
    peak = max(values)
    if peak == 0:
        return BLOCKS[0] * len(values)
    return "".join(BLOCKS[min(int(v / peak * (len(BLOCKS) - 1)), len(BLOCKS) - 1)] for v in values)


def bar(value: int, peak: int, width: int = 24) -> str:
    if peak <= 0:
        return ""
    filled = max(1, round(value / peak * width)) if value else 0
    return "█" * filled + "·" * (width - filled)


def risk_label(bus: int) -> tuple[str, str]:
    if bus <= 1:
        return "CRITICAL", RED
    if bus == 2:
        return "AT RISK", YELLOW
    if bus <= 4:
        return "OK", CYAN
    return "HEALTHY", GREEN


def render_text(a: Analysis, *, color: bool = True) -> str:
    def c(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    lines: list[str] = []
    add = lines.append

    add(c(f"gitpulse  {a.repo}", BOLD) + c(f"  ({a.branch})", DIM))
    if not a.commits:
        add(c("  no commits found in range", DIM))
        return "\n".join(lines)

    span = f"{a.first_commit:%Y-%m-%d} → {a.last_commit:%Y-%m-%d}"
    add(c(f"  {a.total_commits} commits · {a.total_authors} authors · {span} · "
          f"{a.commits_per_week}/week", DIM))
    add("")

    label, colour = risk_label(a.bus_factor)
    add(f"{c('BUS FACTOR', BOLD)}  {c(str(a.bus_factor), colour)}  {c(label, colour)}")
    add(c(f"  {a.bus_factor} person(s) account for 50% of all code churn.", DIM))
    add("")

    if a.activity_by_month:
        months = list(a.activity_by_month.items())[-24:]
        add(c("ACTIVITY", BOLD) + c(f"  last {len(months)} months", DIM))
        add("  " + c(sparkline([v for _, v in months]), MAGENTA))
        add(c(f"  {months[0][0]}{' ' * max(0, len(months) - 14)}{months[-1][0]}", DIM))
        add("")

    if a.author_commits:
        add(c("TOP CONTRIBUTORS", BOLD))
        peak = a.author_commits.most_common(1)[0][1]
        for author, count in a.author_commits.most_common(8):
            share = count / a.total_commits * 100
            name = author[:22].ljust(22)
            add(f"  {name} {c(bar(count, peak), CYAN)} {count:>5} ({share:4.1f}%)")
        add("")

    if a.hotspots:
        add(c("HOTSPOTS", BOLD) + c("  changed often, changed recently", DIM))
        add(c(f"  {'file':<44} {'commits':>7} {'churn':>7} {'authors':>7} {'last':>8}", DIM))
        for risk in a.hotspots[:10]:
            path = risk.path if len(risk.path) <= 44 else "…" + risk.path[-43:]
            flag = c(" ⚠", YELLOW) if risk.authors == 1 else ""
            add(f"  {path:<44} {risk.commits:>7} {risk.churn:>7} "
                f"{risk.authors:>7} {risk.last_touched_days:>7.0f}d{flag}")
        add("")

    if a.silos:
        add(c("KNOWLEDGE SILOS", BOLD) + c("  only one person has ever touched these", DIM))
        for path, author in a.silos[:8]:
            shown = path if len(path) <= 50 else "…" + path[-49:]
            add(f"  {shown:<52} {c(author, YELLOW)}")
        add("")

    weekday = a.activity_by_weekday
    weekend = weekday.get("Sat", 0) + weekday.get("Sun", 0)
    if a.total_commits:
        pct = weekend / a.total_commits * 100
        note = c(" ← burnout signal", RED) if pct > 25 else ""
        add(c(f"  weekend commits: {weekend} ({pct:.0f}%)", DIM) + note)

    return "\n".join(lines)


def to_dict(a: Analysis) -> dict:
    return {
        "repo": a.repo,
        "branch": a.branch,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": {
            "commits": a.total_commits,
            "authors": a.total_authors,
            "bus_factor": a.bus_factor,
            "risk": risk_label(a.bus_factor)[0],
            "first_commit": a.first_commit.isoformat() if a.first_commit else None,
            "last_commit": a.last_commit.isoformat() if a.last_commit else None,
            "age_days": round(a.age_days, 1),
            "commits_per_week": a.commits_per_week,
        },
        "top_contributors": [
            {"author": name, "commits": n, "churn": a.author_churn[name]}
            for name, n in a.author_commits.most_common(20)
        ],
        "hotspots": [
            {
                "path": r.path, "commits": r.commits, "churn": r.churn,
                "authors": r.authors, "last_touched_days": r.last_touched_days,
                "score": r.score, "primary_author_share": r.primary_author_share,
            }
            for r in a.hotspots
        ],
        "knowledge_silos": [{"path": p, "author": au} for p, au in a.silos],
        "activity_by_month": a.activity_by_month,
        "activity_by_weekday": a.activity_by_weekday,
    }


def render_json(a: Analysis) -> str:
    return json.dumps(to_dict(a), indent=2)


def render_html(a: Analysis) -> str:
    """A single self-contained HTML file - no CDN, no build step."""
    e = html.escape
    label, _ = risk_label(a.bus_factor)
    risk_class = {"CRITICAL": "crit", "AT RISK": "warn", "OK": "ok", "HEALTHY": "good"}[label]

    months = list(a.activity_by_month.items())[-24:]
    peak_month = max((v for _, v in months), default=1) or 1
    month_bars = "".join(
        f'<div class="mb" style="height:{max(4, round(v / peak_month * 100))}%" '
        f'title="{e(m)}: {v} commits"></div>'
        for m, v in months
    )
    month_labels = (f"<span>{e(months[0][0])}</span><span>{e(months[-1][0])}</span>"
                    if months else "")

    peak_author = a.author_commits.most_common(1)[0][1] if a.author_commits else 1
    author_rows = "".join(
        f'<tr><td>{e(name)}</td>'
        f'<td class="barcell"><div class="bar" style="width:{n / peak_author * 100:.1f}%"></div></td>'
        f'<td class="num">{n}</td>'
        f'<td class="num">{a.author_churn[name]:,}</td></tr>'
        for name, n in a.author_commits.most_common(12)
    )

    peak_score = a.hotspots[0].score if a.hotspots else 1
    hotspot_rows = "".join(
        f'<tr><td class="mono">{e(r.path)}</td>'
        f'<td class="barcell"><div class="bar heat" style="width:{r.score / (peak_score or 1) * 100:.1f}%"></div></td>'
        f'<td class="num">{r.commits}</td><td class="num">{r.churn:,}</td>'
        f'<td class="num">{r.authors}{" ⚠" if r.authors == 1 else ""}</td>'
        f'<td class="num">{r.last_touched_days:.0f}d</td></tr>'
        for r in a.hotspots
    )

    silo_rows = "".join(
        f'<tr><td class="mono">{e(p)}</td><td>{e(au)}</td></tr>' for p, au in a.silos
    ) or '<tr><td colspan="2" class="empty">None found — knowledge is well spread.</td></tr>'

    span = (f"{a.first_commit:%d %b %Y} → {a.last_commit:%d %b %Y}" if a.commits else "—")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitpulse — {e(a.repo)}</title>
<style>
  :root {{
    --bg:#0d1117; --panel:#161b22; --line:#30363d; --text:#e6edf3; --dim:#8b949e;
    --accent:#58a6ff; --crit:#f85149; --warn:#d29922; --ok:#58a6ff; --good:#3fb950;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:2.5rem 1.5rem; background:var(--bg); color:var(--text);
    font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  h1 {{ font-size:1.6rem; margin:0 0 .2rem; }}
  h2 {{ font-size:1rem; text-transform:uppercase; letter-spacing:.08em; color:var(--dim);
    margin:2.5rem 0 .8rem; font-weight:600; }}
  .sub {{ color:var(--dim); font-size:.9rem; margin-bottom:2rem; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1rem; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:1.1rem; }}
  .card .k {{ color:var(--dim); font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; }}
  .card .v {{ font-size:1.9rem; font-weight:700; margin-top:.35rem; line-height:1; }}
  .crit .v {{ color:var(--crit); }} .warn .v {{ color:var(--warn); }}
  .ok .v {{ color:var(--ok); }} .good .v {{ color:var(--good); }}
  .card .n {{ color:var(--dim); font-size:.75rem; margin-top:.4rem; }}
  .chart {{ display:flex; align-items:flex-end; gap:3px; height:120px;
    background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:.9rem; }}
  .mb {{ flex:1; background:linear-gradient(180deg,var(--accent),#1f6feb); border-radius:2px 2px 0 0;
    min-height:4px; transition:opacity .15s; }}
  .mb:hover {{ opacity:.65; }}
  .axis {{ display:flex; justify-content:space-between; color:var(--dim);
    font-size:.72rem; margin-top:.4rem; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:.88rem; }}
  th {{ text-align:left; color:var(--dim); font-weight:600; font-size:.72rem;
    text-transform:uppercase; letter-spacing:.06em; padding:.65rem .9rem;
    border-bottom:1px solid var(--line); }}
  td {{ padding:.55rem .9rem; border-bottom:1px solid rgba(48,54,61,.5); }}
  tr:last-child td {{ border-bottom:none; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82rem;
    word-break:break-all; }}
  .barcell {{ width:34%; }}
  .bar {{ height:8px; background:var(--accent); border-radius:4px; min-width:2px; }}
  .bar.heat {{ background:linear-gradient(90deg,var(--warn),var(--crit)); }}
  .empty {{ color:var(--dim); text-align:center; padding:1.2rem; }}
  footer {{ color:var(--dim); font-size:.78rem; margin-top:3rem;
    border-top:1px solid var(--line); padding-top:1rem; }}
  a {{ color:var(--accent); }}
</style>
</head>
<body><div class="wrap">
  <h1>{e(a.repo)}</h1>
  <div class="sub">branch <strong>{e(a.branch)}</strong> · {span}</div>

  <div class="cards">
    <div class="card {risk_class}"><div class="k">Bus factor</div><div class="v">{a.bus_factor}</div>
      <div class="n">{label}</div></div>
    <div class="card"><div class="k">Commits</div><div class="v">{a.total_commits:,}</div>
      <div class="n">{a.commits_per_week}/week</div></div>
    <div class="card"><div class="k">Authors</div><div class="v">{a.total_authors}</div>
      <div class="n">{len(a.silos)} solo-owned files</div></div>
    <div class="card"><div class="k">Age</div><div class="v">{a.age_days / 365:.1f}y</div>
      <div class="n">{a.age_days:.0f} days</div></div>
  </div>

  <h2>Commit activity</h2>
  <div class="chart">{month_bars}</div>
  <div class="axis">{month_labels}</div>

  <h2>Contributors</h2>
  <table><thead><tr><th>Author</th><th></th><th class="num">Commits</th>
    <th class="num">Lines changed</th></tr></thead><tbody>{author_rows}</tbody></table>

  <h2>Hotspots <span style="text-transform:none;font-weight:400">— high churn, recently touched</span></h2>
  <table><thead><tr><th>File</th><th>Risk</th><th class="num">Commits</th>
    <th class="num">Churn</th><th class="num">Authors</th><th class="num">Last</th></tr></thead>
    <tbody>{hotspot_rows}</tbody></table>

  <h2>Knowledge silos</h2>
  <table><thead><tr><th>File</th><th>Sole author</th></tr></thead><tbody>{silo_rows}</tbody></table>

  <footer>Generated by <a href="https://github.com/ashflamer/gitpulse">gitpulse</a>
    on {datetime.now(tz=timezone.utc):%d %b %Y %H:%M} UTC. Hotspot score = time-decayed churn ×
    log(commits) × single-author penalty.</footer>
</div></body></html>"""
