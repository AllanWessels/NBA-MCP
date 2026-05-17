# NBA Analytics MCP Server (tech stack/example from production/private version)

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
the 2025-26 NBA daily leaders dataset (~28k player-game rows, all 30 teams) to
MCP-compatible AI clients — Claude Desktop, Cursor, MCP Inspector, and any
custom MCP host.

Built with the official Python MCP SDK (`mcp[cli]` / FastMCP), `asyncpg` for a
pooled async Postgres connection, and Docker Compose for one-command setup.

## Quickstart

```bash
docker compose up --build
```

That brings up:
- **Postgres 16** on `localhost:5432` — schema + ~28k rows loaded automatically on first start
- **MCP server** on `http://localhost:8000/mcp` (Streamable HTTP transport)

## Try it out

### Option A — MCP Inspector (browser UI)

```bash
npx @modelcontextprotocol/inspector
```

Open the URL it prints, point it at `http://localhost:8000/mcp`, and call any
tool interactively.

### Option B — Claude Desktop (stdio)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(or the equivalent path on your OS):

```json
{
  "mcpServers": {
    "nba": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/mcp-nba-server", "run", "python", "-m", "src.server"],
      "env": {
        "DATABASE_URL": "postgresql://mcp:mcp_dev_password@localhost:5432/nba",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Restart Claude Desktop. Try asking:
- *"Who's been the best scorer in the last two weeks?"*
- *"Show me Luka Dončić's last 10 games."*
- *"What were the top 5 single-game performances by Game Score this season?"*
- *"Compare Shai Gilgeous-Alexander and Jokić head-to-head."*

## Tools exposed

| Tool | Purpose |
|---|---|
| `top_scorers(start_date, end_date, limit)` | PPG leaders in a window (3+ games min) |
| `player_game_log(player, limit)` | Recent games for a player |
| `search_players(query)` | Fuzzy player-name lookup |
| `player_season_averages(player)` | Full per-game averages for a player |
| `top_performances(metric, limit, min_minutes)` | Best single-game performances by `pts`, `trb`, `ast`, `stl`, `blk`, `game_score`, or `plus_minus` |
| `team_leaderboard(team)` | Wins/losses and team PPG |
| `head_to_head(player_a, player_b)` | Side-by-side season averages |

## Resources exposed

- `schema://player_games` — column-by-column schema documentation
- `dataset://summary` — row count, date coverage, top-line names

## Architecture

```
Claude Desktop ──(MCP / stdio or HTTP)──>  FastMCP server  ──(asyncpg)──>  PostgreSQL
                                            │  pool, lifespan-managed       │  seeded from CSV
                                            └─ tools, resources, prompts    └─ via COPY + transform
```

## Design choices worth talking about

- **No `execute_sql` tool.** Every tool wraps a specific intent with
  parameterized queries — this is the difference between "exposing a database
  to an AI" and "vending it safely."
- **Whitelisted dynamic SQL.** The one place a column name is interpolated
  (`top_performances`) validates `metric` against an explicit set first.
- **Pooled connections.** `asyncpg.create_pool` opens once in the FastMCP
  lifespan hook and is shared across tool calls.
- **Two transports, one binary.** `MCP_TRANSPORT=stdio` for Claude Desktop,
  `streamable-http` for the deployed Docker service.
- **Staging-then-transform load.** The CSV ships with awkward column names
  (`FG%`, `+/-`, `MP` as `MM:SS`). A staging table mirrors the CSV exactly,
  then a single `INSERT … SELECT` cleans it into the query-friendly final
  table.

## Project layout

```
mcp-nba-server/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
├── init-db/
│   ├── 01_schema.sql
│   ├── 02_load.sql
│   └── nba_dailyleaders_full.csv     # ~2.5MB, 27,818 rows
└── src/
    ├── __init__.py
    └── server.py
```

## Extensions

- OAuth 2.1 in front of the HTTP transport via `fastmcp.auth`
- Structured logging (`structlog`) and a Prometheus `/metrics` endpoint
- GitHub Actions CI: ruff + mypy + pytest against an ephemeral Postgres service
- Deploy to Fly.io / Railway and put the live URL in this README
