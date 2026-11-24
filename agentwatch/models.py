from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .pricing import cost_for


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0
    cost: float = 0.0
    calls: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_write + self.cache_read

    def add_raw(self, model: str, u: dict) -> None:
        i = u.get("input_tokens", 0) or 0
        o = u.get("output_tokens", 0) or 0
        cw = u.get("cache_creation_input_tokens", 0) or 0
        cr = u.get("cache_read_input_tokens", 0) or 0
        self.input += i
        self.output += o
        self.cache_write += cw
        self.cache_read += cr
        split = u.get("cache_creation") or {}
        cw_1h = split.get("ephemeral_1h_input_tokens", 0) or 0
        self.cost += cost_for(model, i, o, cw - cw_1h, cr, cw_1h)
        self.calls += 1

    def __iadd__(self, other: "Usage") -> "Usage":
        self.input += other.input
        self.output += other.output
        self.cache_write += other.cache_write
        self.cache_read += other.cache_read
        self.cost += other.cost
        self.calls += other.calls
        return self

    def to_dict(self) -> dict:
        return {
            "input": self.input, "output": self.output,
            "cache_write": self.cache_write, "cache_read": self.cache_read,
            "total": self.total, "cost_usd": round(self.cost, 4), "calls": self.calls,
        }


@dataclass
class Agent:
    """The main agent of a session, or one subagent."""
    agent_id: str
    label: str                 # e.g. "main" or "Explore"
    description: str = ""
    depth: int = 0
    finished: bool | None = None
    usage: Usage = field(default_factory=Usage)
    models: dict[str, Usage] = field(default_factory=dict)
    daily: dict[str, Usage] = field(default_factory=dict)  # local YYYY-MM-DD -> usage
    start: datetime | None = None
    end: datetime | None = None


@dataclass
class Session:
    session_id: str
    project: str
    cwd: str = ""
    main: Agent | None = None
    subagents: list[Agent] = field(default_factory=list)
    mtime: float = 0.0

    @property
    def agents(self) -> list[Agent]:
        return ([self.main] if self.main else []) + self.subagents

    @property
    def usage(self) -> Usage:
        u = Usage()
        for a in self.agents:
            u += a.usage
        return u

    @property
    def start(self) -> datetime | None:
        ts = [a.start for a in self.agents if a.start]
        return min(ts) if ts else None

    @property
    def end(self) -> datetime | None:
        ts = [a.end for a in self.agents if a.end]
        return max(ts) if ts else None

    @property
    def model(self) -> str:
        if not self.main or not self.main.models:
            return "-"
        return max(self.main.models.items(), key=lambda kv: kv[1].total)[0]
