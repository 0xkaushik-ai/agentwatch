"""Data sources. Each source turns some log format into Session objects.

Add new agent frameworks by subclassing `Source` and registering it in SOURCES.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .models import Agent, Session, Usage


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class Source:
    name = "base"

    def scan(self, since: float | None = None) -> list[Session]:
        raise NotImplementedError


class ClaudeCodeSource(Source):
    """Reads ~/.claude/projects/<project>/<session>.jsonl and its subagents/ dir."""
    name = "claude-code"

    def __init__(self, root: str | Path | None = None):
        root = root or os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")
        self.root = Path(root) / "projects"
        # path -> (mtime, size, parsed Agent, cwd, sessionId)
        self._cache: dict[Path, tuple[float, int, Agent, str, str]] = {}

    # -- parsing ---------------------------------------------------------
    def _parse(self, path: Path, agent_id: str, label: str) -> tuple[Agent, str, str]:
        st = path.stat()
        hit = self._cache.get(path)
        if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
            return hit[2], hit[3], hit[4]

        per_msg: dict[str, tuple[str, dict, datetime | None]] = {}  # msg id -> last seen; dedup
        start = end = None
        cwd = session_id = ""
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                t = _ts(d.get("timestamp"))
                if t:
                    start = t if start is None or t < start else start
                    end = t if end is None or t > end else end
                cwd = cwd or d.get("cwd", "")
                session_id = session_id or d.get("sessionId", "")
                msg = d.get("message")
                if d.get("type") != "assistant" or not isinstance(msg, dict):
                    continue
                usage, model = msg.get("usage"), msg.get("model", "unknown")
                if not usage or model == "<synthetic>":
                    continue
                key = msg.get("id") or d.get("uuid") or str(len(per_msg))
                per_msg[key] = (model, usage, t)  # later lines carry the final usage

        agent = Agent(agent_id=agent_id, label=label, start=start, end=end)
        for model, u, t in per_msg.values():
            agent.usage.add_raw(model, u)
            agent.models.setdefault(model, Usage()).add_raw(model, u)
            day = t.astimezone().strftime("%Y-%m-%d") if t else "unknown"
            agent.daily.setdefault(day, Usage()).add_raw(model, u)
        self._cache[path] = (st.st_mtime, st.st_size, agent, cwd, session_id)
        return agent, cwd, session_id

    def _subagents(self, sess_dir: Path) -> list[Agent]:
        sub_dir = sess_dir / "subagents"
        if not sub_dir.is_dir():
            return []
        out = []
        for f in sorted(sub_dir.glob("agent-*.jsonl")):
            aid = f.stem.removeprefix("agent-")
            meta = {}
            mf = f.with_suffix(".meta.json")
            if mf.exists():
                try:
                    meta = json.loads(mf.read_text())
                except ValueError:
                    pass
            agent, _, _ = self._parse(f, aid, meta.get("agentType", "subagent"))
            agent.description = meta.get("description", "")
            agent.depth = meta.get("spawnDepth", 1)
            agent.finished = meta.get("finished")
            out.append(agent)
        return out

    # -- public ----------------------------------------------------------
    def scan(self, since: float | None = None) -> list[Session]:
        if not self.root.is_dir():
            return []
        sessions = []
        for proj in self.root.iterdir():
            if not proj.is_dir():
                continue
            for main in proj.glob("*.jsonl"):
                sess_dir = proj / main.stem
                mtimes = [main.stat().st_mtime]
                if sess_dir.is_dir():
                    mtimes += [p.stat().st_mtime for p in sess_dir.glob("subagents/*.jsonl")]
                mtime = max(mtimes)
                if since and mtime < since:
                    continue
                agent, cwd, _ = self._parse(main, main.stem, "main")
                s = Session(session_id=main.stem, project=proj.name, cwd=cwd,
                            main=agent, mtime=mtime)
                s.subagents = self._subagents(sess_dir)
                if s.usage.calls:
                    sessions.append(s)
        sessions.sort(key=lambda s: s.mtime, reverse=True)
        return sessions


SOURCES: dict[str, type[Source]] = {ClaudeCodeSource.name: ClaudeCodeSource}
