from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from pathlib import Path

from rich import box
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .models import Session, Usage


def fmt(n: int) -> str:
    for unit, div in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= div:
            return f"{n / div:.2f}{unit}"
    return str(n)


def money(x: float) -> str:
    return f"${x:,.2f}"


_HOME = str(Path.home())


def project_name(s: Session) -> str:
    name = s.cwd or s.project
    return "~" + name[len(_HOME):] if name.startswith(_HOME) else name


def _usage_cols(t: Table) -> None:
    for c in ("Input", "Output", "Cache W", "Cache R", "Total"):
        t.add_column(c, justify="right")
    t.add_column("Est. $", justify="right", style="green")


def _usage_cells(u: Usage) -> list[str]:
    return [fmt(u.input), fmt(u.output), fmt(u.cache_write), fmt(u.cache_read),
            Text(fmt(u.total), style="bold"), money(u.cost)]


def _when(s: Session) -> str:
    return s.end.astimezone().strftime("%Y-%m-%d %H:%M") if s.end else "-"


# --- tables -------------------------------------------------------------
def summary_tables(sessions: list[Session], top: int = 10) -> list[Table]:
    by_proj: dict[str, Usage] = defaultdict(Usage)
    counts: dict[str, int] = defaultdict(int)
    grand = Usage()
    for s in sessions:
        u = s.usage
        by_proj[project_name(s)] += u
        counts[project_name(s)] += 1
        grand += u

    t1 = Table(title="Tokens by project", box=box.SIMPLE_HEAVY)
    t1.add_column("Project", style="cyan", overflow="fold", min_width=14)
    t1.add_column("Sessions", justify="right")
    _usage_cols(t1)
    for name, u in sorted(by_proj.items(), key=lambda kv: kv[1].total, reverse=True):
        t1.add_row(name, str(counts[name]), *_usage_cells(u))
    t1.add_section()
    t1.add_row(Text("TOTAL", style="bold"), str(len(sessions)), *_usage_cells(grand))

    t2 = Table(title=f"Top {top} sessions", box=box.SIMPLE_HEAVY)
    t2.add_column("Session", style="magenta")
    t2.add_column("Last active")
    t2.add_column("Project", style="cyan", overflow="fold", max_width=30)
    t2.add_column("Model")
    t2.add_column("Subagents", justify="right")
    t2.add_column("Total", justify="right", style="bold")
    t2.add_column("Est. $", justify="right", style="green")
    for s in sorted(sessions, key=lambda s: s.usage.total, reverse=True)[:top]:
        u = s.usage
        t2.add_row(s.session_id[:8], _when(s), project_name(s), s.model,
                   str(len(s.subagents)), fmt(u.total), money(u.cost))
    return [t1, t2]


def sessions_table(sessions: list[Session], limit: int = 20) -> Table:
    t = Table(title="Sessions (most recent first)", box=box.SIMPLE_HEAVY)
    t.add_column("Session", style="magenta")
    t.add_column("Last active")
    t.add_column("Project", style="cyan", overflow="fold", max_width=30)
    t.add_column("Subagents", justify="right")
    _usage_cols(t)
    for s in sessions[:limit]:
        t.add_row(s.session_id[:8], _when(s), project_name(s), str(len(s.subagents)),
                  *_usage_cells(s.usage))
    return t


def session_tree(s: Session) -> Tree:
    u = s.usage
    root = Tree(Text.assemble(("Session ", "bold"), (s.session_id, "magenta"),
                              f"  {project_name(s)}  ",
                              (f"{fmt(u.total)} tok  {money(u.cost)}", "green")))
    t = Table(box=box.MINIMAL, show_edge=False)
    t.add_column("Agent", style="yellow")
    t.add_column("Task", overflow="fold", max_width=45)
    t.add_column("Calls", justify="right")
    _usage_cols(t)
    t.add_column("Share", justify="right")
    for a in s.agents:
        share = f"{100 * a.usage.total / u.total:.0f}%" if u.total else "-"
        label = a.label if a.label == "main" else f"{'  ' * (a.depth - 1)}↳ {a.label}"
        status = "" if a.finished in (None, True) else " (running)"
        t.add_row(label, a.description + status, str(a.usage.calls),
                  *_usage_cells(a.usage), share)
    root.add(t)
    models = defaultdict(Usage)
    for a in s.agents:
        for m, mu in a.models.items():
            models[m] += mu
    mb = root.add(Text("Models", style="bold"))
    for m, mu in sorted(models.items(), key=lambda kv: kv[1].total, reverse=True):
        mb.add(f"{m}: {fmt(mu.total)} tok, {money(mu.cost)}")
    return root


def agents_table(sessions: list[Session]) -> Table:
    by_type: dict[str, Usage] = defaultdict(Usage)
    runs: dict[str, int] = defaultdict(int)
    for s in sessions:
        for a in s.agents:
            by_type[a.label] += a.usage
            runs[a.label] += 1
    t = Table(title="Tokens by agent type", box=box.SIMPLE_HEAVY)
    t.add_column("Agent type", style="yellow")
    t.add_column("Runs", justify="right")
    _usage_cols(t)
    t.add_column("Avg / run", justify="right")
    for name, u in sorted(by_type.items(), key=lambda kv: kv[1].total, reverse=True):
        t.add_row(name, str(runs[name]), *_usage_cells(u), fmt(u.total // max(runs[name], 1)))
    return t


# --- exports ------------------------------------------------------------
def rows(sessions: list[Session]) -> list[dict]:
    out = []
    for s in sessions:
        for a in s.agents:
            out.append({
                "session_id": s.session_id, "project": project_name(s),
                "agent_id": a.agent_id, "agent_type": a.label,
                "description": a.description, "depth": a.depth,
                "models": ",".join(a.models),
                "start": a.start.isoformat() if a.start else "",
                "end": a.end.isoformat() if a.end else "",
                **a.usage.to_dict(),
            })
    return out


def to_json(sessions: list[Session]) -> str:
    return json.dumps(rows(sessions), indent=2)


def to_csv(sessions: list[Session]) -> str:
    r = rows(sessions)
    if not r:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(r[0]))
    w.writeheader()
    w.writerows(r)
    return buf.getvalue()
