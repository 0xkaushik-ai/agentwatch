from __future__ import annotations

import argparse
import re
import sys
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel

from . import report
from .sources import SOURCES

console = Console()


def parse_since(s: str | None) -> float | None:
    if not s:
        return None
    m = re.fullmatch(r"(\d+)([mhdw])", s)
    if not m:
        raise argparse.ArgumentTypeError("use e.g. 30m, 12h, 7d, 2w")
    mult = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[m[2]]
    return time.time() - int(m[1]) * mult


def load(args):
    src = SOURCES[args.source](args.root) if args.root else SOURCES[args.source]()
    sessions = src.scan(since=parse_since(args.since))
    if args.project:
        sessions = [s for s in sessions
                    if args.project.lower() in (s.cwd or s.project).lower()]
    return src, sessions


def emit_export(args, sessions) -> bool:
    if args.json:
        print(report.to_json(sessions))
    elif args.csv:
        print(report.to_csv(sessions), end="")
    else:
        return False
    return True


def cmd_summary(args):
    _, sessions = load(args)
    if emit_export(args, sessions):
        return
    if not sessions:
        console.print("[yellow]No sessions found.[/]")
        return
    for t in report.summary_tables(sessions, top=args.top):
        console.print(t)


def cmd_sessions(args):
    _, sessions = load(args)
    if not emit_export(args, sessions):
        console.print(report.sessions_table(sessions, limit=args.limit))


def cmd_session(args):
    _, sessions = load(args)
    if args.id == "latest":
        match = sessions[:1]
    else:
        match = [s for s in sessions if s.session_id.startswith(args.id)]
    if not match:
        console.print(f"[red]No session matching '{args.id}'.[/]")
        sys.exit(1)
    if len(match) > 1:
        console.print(f"[yellow]'{args.id}' matches {len(match)} sessions; be more specific.[/]")
        sys.exit(1)
    if not emit_export(args, match):
        console.print(report.session_tree(match[0]))


def cmd_agents(args):
    _, sessions = load(args)
    if not emit_export(args, sessions):
        console.print(report.agents_table(sessions))


def cmd_live(args):
    src, _ = load(args)
    since = parse_since(args.since or "1d")

    def render():
        sessions = src.scan(since=since)
        if args.project:
            sessions = [s for s in sessions
                        if args.project.lower() in (s.cwd or s.project).lower()]
        parts = [report.session_tree(s) for s in sessions[: args.count]]
        body = Group(*parts) if parts else "[yellow]No active sessions in window.[/]"
        return Panel(body, title=f"agentwatch live · refresh {args.interval}s · "
                                 f"{time.strftime('%H:%M:%S')} · Ctrl+C to quit")

    try:
        with Live(render(), console=console, screen=False, auto_refresh=False) as live:
            while True:
                time.sleep(args.interval)
                live.update(render(), refresh=True)
    except KeyboardInterrupt:
        pass


def cmd_web(args):
    from .web import serve
    src = SOURCES[args.source](args.root) if args.root else SOURCES[args.source]()
    serve(src, host=args.host, port=args.port, open_browser=not args.no_browser)


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", default="claude-code", choices=list(SOURCES))
    common.add_argument("--root", help="override log root (default ~/.claude)")
    common.add_argument("--since", help="only sessions active within e.g. 2h, 7d")
    common.add_argument("--project", help="filter by project path substring")
    g = common.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="export per-agent rows as JSON")
    g.add_argument("--csv", action="store_true", help="export per-agent rows as CSV")

    p = argparse.ArgumentParser(prog="agentwatch",
                                description="Monitor AI agent token usage per session and subagent.")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("summary", parents=[common], help="totals per project + top sessions")
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(fn=cmd_summary)

    s = sub.add_parser("sessions", parents=[common], help="list sessions")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_sessions)

    s = sub.add_parser("session", parents=[common], help="one session: main agent + subagents")
    s.add_argument("id", nargs="?", default="latest", help="session id prefix or 'latest'")
    s.set_defaults(fn=cmd_session)

    s = sub.add_parser("agents", parents=[common], help="totals grouped by subagent type")
    s.set_defaults(fn=cmd_agents)

    s = sub.add_parser("live", parents=[common], help="live dashboard of recent sessions")
    s.add_argument("--interval", type=float, default=3.0)
    s.add_argument("--count", type=int, default=3, help="sessions to show")
    s.set_defaults(fn=cmd_live)

    s = sub.add_parser("web", help="local web dashboard")
    s.add_argument("--source", default="claude-code", choices=list(SOURCES))
    s.add_argument("--root", help="override log root (default ~/.claude)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_web)

    args = p.parse_args(argv)
    if not args.cmd:
        args = p.parse_args(["summary", *(argv or sys.argv[1:])])
    args.fn(args)


if __name__ == "__main__":
    main()
