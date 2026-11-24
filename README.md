# agentwatch

Monitor AI agent token usage **per session** and **per subagent** (labelled by agent type and task).
It reads Claude Code's local logs in `~/.claude/projects/` and never modifies them.

## Install
```bash
pip install -e .        # gives you the `agentwatch` command
# or run without installing:
python3 -m agentwatch
```

## Commands
| Command | What it shows |
|---|---|
| `agentwatch summary` | Totals per project + top sessions (default command) |
| `agentwatch sessions` | Recent sessions list |
| `agentwatch session <id-prefix>` / `latest` | One session: main agent + every subagent, with label, task, tokens, share |
| `agentwatch agents` | Totals grouped by agent type (`main`, `Explore`, `general-purpose`, ...) |
| `agentwatch live` | Live terminal view of the most recent sessions, refreshes every 3s |
| `agentwatch web` | Web dashboard at http://127.0.0.1:8765 (`--port`, `--no-browser`) |

Common flags: `--since 2h|7d|2w`, `--project <substring>`, `--json`, `--csv`, `--root <dir>`.

## Web dashboard
`agentwatch web` starts a local server (stdlib only, bound to 127.0.0.1) and opens the page.
- KPI tiles: est. cost, tokens, output tokens, sessions (live now), subagent runs, cache hit rate
- Daily bar chart, bars by agent type and by project (hover for details)
- Sessions table: click one to see main agent vs each subagent with task label and share
- Filters: 24h / 7d / 30d / all, project, metric ($ / tokens / output); auto-refresh every 5s
- Link to a session directly: `http://127.0.0.1:8765/#s=<session-id>`
- JSON API: `/api/data?since=7d&project=~/myproject`

## Cost
`Est. $` uses Anthropic API list prices (see `agentwatch/pricing.py`), including
5-minute vs 1-hour cache-write pricing. On a Claude subscription plan this is the
*API-equivalent* value, not what you are billed. Override prices in
`~/.config/agentwatch/pricing.json`: `{"model-id": [input, output, cache_write, cache_read]}` ($/1M tokens).

## Adding other agent frameworks
Subclass `Source` in `agentwatch/sources.py`, implement `scan()` returning `Session` objects,
and register it in `SOURCES`. It then becomes available as `--source <name>`.
