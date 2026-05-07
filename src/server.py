"""NBA Analytics MCP Server.

Exposes the 2025-26 NBA daily leaders dataset to MCP clients (Claude Desktop,
Cursor, Inspector, etc.) via a small set of typed, parameterized tools.

Design notes worth talking about in interviews:
  - No raw-SQL surface. Each tool wraps a specific intent.
  - All user input goes through asyncpg's $1, $2 parameters (no string concat).
  - One asyncpg connection pool, opened in the lifespan hook.
  - Two transports from one binary: stdio for local Claude Desktop dev,
    streamable-http for the deployed Docker service.
"""

import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from mcp.server.fastmcp import FastMCP

DATABASE_URL = os.environ["DATABASE_URL"]

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(_app):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    try:
        yield
    finally:
        await _pool.close()


mcp = FastMCP(
    "nba-analytics",
    lifespan=lifespan,
    host="0.0.0.0",
    port=8000,
)


# ---------- Resources (read-only context for the LLM) ----------

@mcp.resource("schema://player_games")
async def schema_doc() -> str:
    """Schema and column meanings for the player_games table.
    Read this first to know what columns exist before calling tools.
    """
    return (
        "Table: player_games (one row per player per game, 2025-26 NBA season)\n"
        "  game_date    DATE       game date\n"
        "  player       TEXT       player name (e.g. 'Luka Dončić')\n"
        "  team         TEXT       3-letter team code (LAL, BOS, etc.)\n"
        "  opponent     TEXT       3-letter opponent code\n"
        "  result       CHAR(1)    'W' or 'L' from the player's team's perspective\n"
        "  minutes      NUMERIC    minutes played as a decimal (40:59 -> 40.98)\n"
        "  fg, fga, fg_pct        field goals made / attempted / pct\n"
        "  three_p, three_pa, three_pct   three-pointers\n"
        "  ft, fta, ft_pct        free throws\n"
        "  orb, drb, trb          offensive / defensive / total rebounds\n"
        "  ast, stl, blk, tov, pf assists, steals, blocks, turnovers, fouls\n"
        "  pts                    points\n"
        "  plus_minus             team net score while the player was on the floor\n"
        "  game_score             Hollinger Game Score (single-game efficiency)\n"
    )


@mcp.resource("dataset://summary")
async def dataset_summary() -> str:
    """Quick orientation: row count, date coverage, and a few top-line names."""
    async with _pool.acquire() as conn:
        meta = await conn.fetchrow(
            """
            SELECT count(*) AS rows,
                   min(game_date) AS first_date,
                   max(game_date) AS last_date,
                   count(DISTINCT player) AS players,
                   count(DISTINCT team) AS teams
            FROM player_games
            """
        )
        leaders = await conn.fetch(
            """
            SELECT player, round(avg(pts)::numeric, 1) AS ppg
            FROM player_games
            GROUP BY player
            HAVING count(*) >= 20
            ORDER BY avg(pts) DESC
            LIMIT 5
            """
        )
    leader_lines = "\n".join(f"  {r['player']}: {r['ppg']} ppg" for r in leaders)
    return (
        f"Rows: {meta['rows']:,}\n"
        f"Coverage: {meta['first_date']} to {meta['last_date']}\n"
        f"Players: {meta['players']}, Teams: {meta['teams']}\n"
        f"Top scorers (min 20 GP):\n{leader_lines}\n"
    )


# ---------- Tools ----------

@mcp.tool()
async def top_scorers(
    start_date: str,
    end_date: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Top scorers by points-per-game in a date window (ISO YYYY-MM-DD).

    Returns players with their PPG, games played, and total points. Restricted
    to players with 3+ games in the window so a single 50-point outburst
    doesn't top the list.
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT player,
                   count(*)                      AS games,
                   round(avg(pts)::numeric, 1)   AS ppg,
                   sum(pts)                      AS total_points
            FROM player_games
            WHERE game_date BETWEEN $1::date AND $2::date
            GROUP BY player
            HAVING count(*) >= 3
            ORDER BY avg(pts) DESC
            LIMIT $3
            """,
            start_date, end_date, min(limit, 50),
        )
    return [dict(r) | {"ppg": float(r["ppg"])} for r in rows]


@mcp.tool()
async def player_game_log(
    player: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Recent game log for a player (most recent first).

    Player name is matched case-insensitively. Accents must match
    (e.g. "Luka Dončić", not "Luka Doncic"). If you're unsure of the
    spelling, call search_players first.
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT game_date, team, opponent, result,
                   minutes, pts, trb, ast, stl, blk, tov,
                   plus_minus, game_score
            FROM player_games
            WHERE player ILIKE $1
            ORDER BY game_date DESC
            LIMIT $2
            """,
            player, min(limit, 100),
        )
    return [
        {
            "date":       r["game_date"].isoformat(),
            "team":       r["team"],
            "opponent":   r["opponent"],
            "result":     r["result"],
            "minutes":    float(r["minutes"]),
            "pts":        r["pts"],
            "reb":        r["trb"],
            "ast":        r["ast"],
            "stl":        r["stl"],
            "blk":        r["blk"],
            "tov":        r["tov"],
            "plus_minus": float(r["plus_minus"]) if r["plus_minus"] is not None else None,
            "game_score": float(r["game_score"]) if r["game_score"] is not None else None,
        }
        for r in rows
    ]


@mcp.tool()
async def search_players(query: str, limit: int = 10) -> list[str]:
    """Find player names matching a substring (handy for fuzzy lookups)."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT player
            FROM player_games
            WHERE player ILIKE $1
            ORDER BY player
            LIMIT $2
            """,
            f"%{query}%", min(limit, 50),
        )
    return [r["player"] for r in rows]


@mcp.tool()
async def player_season_averages(player: str) -> dict[str, Any]:
    """Season-long per-game averages for a single player."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT player,
                   count(*)                                    AS games,
                   round(avg(minutes)::numeric, 1)             AS mpg,
                   round(avg(pts)::numeric, 1)                 AS ppg,
                   round(avg(trb)::numeric, 1)                 AS rpg,
                   round(avg(ast)::numeric, 1)                 AS apg,
                   round(avg(stl)::numeric, 2)                 AS spg,
                   round(avg(blk)::numeric, 2)                 AS bpg,
                   round(avg(tov)::numeric, 2)                 AS tpg,
                   round(avg(fg_pct)::numeric, 3)              AS fg_pct,
                   round(avg(three_pct)::numeric, 3)           AS three_pct,
                   round(avg(ft_pct)::numeric, 3)              AS ft_pct,
                   round(avg(plus_minus)::numeric, 1)          AS avg_plus_minus,
                   round(avg(game_score)::numeric, 1)          AS avg_game_score
            FROM player_games
            WHERE player ILIKE $1
            GROUP BY player
            """,
            player,
        )
    if row is None:
        return {"error": f"No games found for player matching '{player}'"}
    return {k: (float(v) if hasattr(v, "is_finite") else v) for k, v in dict(row).items()}


@mcp.tool()
async def top_performances(
    metric: str = "game_score",
    limit: int = 10,
    min_minutes: float = 20.0,
) -> list[dict[str, Any]]:
    """Best individual single-game performances by a chosen metric.

    metric must be one of: pts, trb, ast, stl, blk, game_score, plus_minus.
    Filters out garbage-time outbursts via min_minutes.
    """
    allowed = {"pts", "trb", "ast", "stl", "blk", "game_score", "plus_minus"}
    if metric not in allowed:
        return [{"error": f"metric must be one of {sorted(allowed)}"}]

    # metric is whitelist-validated above, so safe to interpolate as an identifier.
    sql = f"""
        SELECT game_date, player, team, opponent, result,
               minutes, pts, trb, ast, stl, blk, plus_minus, game_score
        FROM player_games
        WHERE minutes >= $1 AND {metric} IS NOT NULL
        ORDER BY {metric} DESC
        LIMIT $2
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(sql, min_minutes, min(limit, 50))
    return [
        {
            "date":       r["game_date"].isoformat(),
            "player":     r["player"],
            "team":       r["team"],
            "opponent":   r["opponent"],
            "result":     r["result"],
            "minutes":    float(r["minutes"]),
            "pts":        r["pts"],
            "reb":        r["trb"],
            "ast":        r["ast"],
            "stl":        r["stl"],
            "blk":        r["blk"],
            "plus_minus": float(r["plus_minus"]) if r["plus_minus"] is not None else None,
            "game_score": float(r["game_score"]) if r["game_score"] is not None else None,
        }
        for r in rows
    ]


@mcp.tool()
async def team_leaderboard(team: str | None = None) -> list[dict[str, Any]]:
    """Team-level summary: wins/losses, average team PPG, average plus-minus.

    Pass a 3-letter team code (LAL, BOS, ...) to filter, or omit for all 30.
    Wins/losses are counted from any single player's row in that game,
    deduped via DISTINCT (game_date, team).
    """
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH games AS (
                SELECT DISTINCT game_date, team, opponent, result
                FROM player_games
                WHERE ($1::text IS NULL OR team = $1)
            ),
            team_pts AS (
                SELECT game_date, team, sum(pts) AS team_points
                FROM player_games
                WHERE ($1::text IS NULL OR team = $1)
                GROUP BY game_date, team
            )
            SELECT g.team,
                   count(*)                                         AS games,
                   sum((g.result = 'W')::int)                       AS wins,
                   sum((g.result = 'L')::int)                       AS losses,
                   round(avg(tp.team_points)::numeric, 1)           AS ppg
            FROM games g
            JOIN team_pts tp USING (game_date, team)
            GROUP BY g.team
            ORDER BY wins DESC, ppg DESC
            """,
            team,
        )
    return [
        {
            "team":   r["team"],
            "games":  r["games"],
            "wins":   r["wins"],
            "losses": r["losses"],
            "ppg":    float(r["ppg"]),
        }
        for r in rows
    ]


@mcp.tool()
async def head_to_head(player_a: str, player_b: str) -> dict[str, Any]:
    """Side-by-side season averages for two players."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT player,
                   count(*)                            AS games,
                   round(avg(pts)::numeric, 1)         AS ppg,
                   round(avg(trb)::numeric, 1)         AS rpg,
                   round(avg(ast)::numeric, 1)         AS apg,
                   round(avg(fg_pct)::numeric, 3)      AS fg_pct,
                   round(avg(three_pct)::numeric, 3)   AS three_pct,
                   round(avg(game_score)::numeric, 1)  AS avg_gmsc
            FROM player_games
            WHERE player ILIKE $1 OR player ILIKE $2
            GROUP BY player
            """,
            player_a, player_b,
        )
    return {
        r["player"]: {k: (float(v) if v is not None and k != "games" else v)
                      for k, v in dict(r).items() if k != "player"}
        for r in rows
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
