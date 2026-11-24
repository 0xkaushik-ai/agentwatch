"""Local web dashboard: `agentwatch web` -> http://127.0.0.1:8765"""
from __future__ import annotations

import json
import threading
import time
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from .cli import parse_since
from .models import Session, Usage
from .report import project_name

ACTIVE_WINDOW = 120  # seconds since last write to count a session as "live"


def build_payload(sessions: list[Session], since: float | None, project: str | None) -> dict:
    all_projects = sorted({project_name(s) for s in sessions})
    if project:
        sessions = [s for s in sessions if project_name(s) == project]
    since_day = datetime.fromtimestamp(since).strftime("%Y-%m-%d") if since else None

    totals = Usage()
    daily: dict[str, Usage] = defaultdict(Usage)
    daily_sessions: dict[str, set] = defaultdict(set)
    by_agent: dict[str, Usage] = defaultdict(Usage)
    agent_runs: dict[str, int] = defaultdict(int)
    by_proj: dict[str, Usage] = defaultdict(Usage)
    proj_sessions: dict[str, int] = defaultdict(int)
    out_sessions = []
    now = time.time()

    for s in sessions:
        su = s.usage
        totals += su
        by_proj[project_name(s)] += su
        proj_sessions[project_name(s)] += 1
        agents = []
        for a in s.agents:
            by_agent[a.label] += a.usage
            agent_runs[a.label] += 1
            for day, du in a.daily.items():
                if day == "unknown" or (since_day and day < since_day):
                    continue
                daily[day] += du
                daily_sessions[day].add(s.session_id)
            agents.append({
                "id": a.agent_id, "label": a.label, "description": a.description,
                "depth": a.depth, "finished": a.finished,
                "start": a.start.isoformat() if a.start else None,
                "end": a.end.isoformat() if a.end else None,
                "models": {m: mu.to_dict() for m, mu in a.models.items()},
                "usage": a.usage.to_dict(),
            })
        out_sessions.append({
            "id": s.session_id, "project": project_name(s), "model": s.model,
            "start": s.start.isoformat() if s.start else None,
            "end": s.end.isoformat() if s.end else None,
            "active": now - s.mtime < ACTIVE_WINDOW,
            "usage": su.to_dict(), "agents": agents,
        })

    # continuous day axis (missing days = 0)
    days = []
    if daily:
        first = datetime.strptime(since_day or min(daily), "%Y-%m-%d")
        if since_day and min(daily) > since_day:
            first = datetime.strptime(since_day, "%Y-%m-%d")
        last = datetime.now()
        d = first
        while d.date() <= last.date():
            k = d.strftime("%Y-%m-%d")
            days.append({"date": k, **daily.get(k, Usage()).to_dict(),
                         "sessions": len(daily_sessions.get(k, ()))})
            d += timedelta(days=1)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "projects": all_projects,
        "totals": {**totals.to_dict(), "sessions": len(sessions),
                   "subagent_runs": sum(len(s.subagents) for s in sessions),
                   "active": sum(1 for x in out_sessions if x["active"])},
        "daily": days,
        "by_agent": sorted(({"label": k, "runs": agent_runs[k], **v.to_dict()}
                            for k, v in by_agent.items()), key=lambda r: -r["cost_usd"]),
        "by_project": sorted(({"project": k, "sessions": proj_sessions[k], **v.to_dict()}
                              for k, v in by_proj.items()), key=lambda r: -r["cost_usd"]),
        "sessions": out_sessions,
    }


def make_handler(source, lock: threading.Lock):
    page = resources.files("agentwatch").joinpath("static/dashboard.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if url.path == "/api/data":
                q = parse_qs(url.query)
                rng = q.get("since", ["7d"])[0]
                try:
                    since = None if rng == "all" else parse_since(rng)
                except Exception:
                    return self._send(400, b'{"error":"bad since"}', "application/json")
                with lock:
                    sessions = source.scan(since=since)
                body = json.dumps(build_payload(sessions, since, q.get("project", [None])[0] or None))
                return self._send(200, body.encode(), "application/json")
            self._send(404, b"not found", "text/plain")

    return Handler


def serve(source, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    srv = ThreadingHTTPServer((host, port), make_handler(source, threading.Lock()))
    url = f"http://{host}:{port}/"
    print(f"agentwatch dashboard on {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
