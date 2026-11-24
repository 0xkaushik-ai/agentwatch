"""USD per 1M tokens: (input, output, cache_write_5m, cache_read).

Anthropic first-party list prices. Edit or override with
~/.config/agentwatch/pricing.json  ->  {"model-id": [in, out, cw, cr]}
"""
from __future__ import annotations

import json
from pathlib import Path


def _p(inp: float, out: float, cr: float | None = None):
    return (inp, out, inp * 1.25, cr if cr is not None else inp * 0.1)


PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-2": _p(8, 40, 0.20),
    "claude-mythos-5-2": _p(8, 40, 0.20),
    "claude-fable-5-1": _p(10, 50),
    "claude-mythos-5-1": _p(10, 50),
    "claude-fable-5": _p(10, 50),
    "claude-opus-5-5": _p(4, 20, 0.20),
    "claude-opus-5": _p(5, 25),
    "claude-opus-4-8": _p(5, 25),
    "claude-opus-4-7": _p(5, 25),
    "claude-opus-4-6": _p(5, 25),
    "claude-sonnet-5-5": _p(2, 10, 0.10),
    "claude-sonnet-5": _p(2, 10),
    "claude-sonnet-4-6": _p(3, 15),
    "claude-haiku-5-5": _p(0.10, 0.50),
    "claude-haiku-4-5": _p(1, 5),
}

_override = Path.home() / ".config" / "agentwatch" / "pricing.json"
if _override.exists():
    try:
        PRICES.update({k: tuple(v) for k, v in json.loads(_override.read_text()).items()})
    except (ValueError, TypeError):
        pass


def lookup(model: str):
    if model in PRICES:
        return PRICES[model]
    # tolerate date suffixes / provider prefixes, e.g. anthropic.claude-opus-4-8-2026...
    for key in sorted(PRICES, key=len, reverse=True):
        if key in model:
            return PRICES[key]
    return None


def cost_for(model: str, i: int, o: int, cw: int, cr: int, cw_1h: int = 0) -> float:
    """cw = 5-minute cache writes (1.25x input), cw_1h = 1-hour cache writes (2x input)."""
    p = lookup(model)
    if not p:
        return 0.0
    return (i * p[0] + o * p[1] + cw * p[2] + cw_1h * p[0] * 2 + cr * p[3]) / 1_000_000
