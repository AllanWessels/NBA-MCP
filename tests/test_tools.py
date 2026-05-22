from src import server


SEASON_START = "2025-10-01"
SEASON_END = "2026-05-22"


async def test_top_scorers_returns_ranked_players():
    rows = await server.top_scorers(SEASON_START, SEASON_END, limit=5)
    assert len(rows) == 5
    for row in rows:
        assert set(row) >= {"player", "games", "ppg", "total_points"}
        assert row["games"] >= 3
        assert isinstance(row["ppg"], float)
    ppgs = [r["ppg"] for r in rows]
    assert ppgs == sorted(ppgs, reverse=True)


async def test_top_scorers_rejects_malformed_dates():
    rows = await server.top_scorers("not-a-date", SEASON_END)
    assert rows == [{"error": "start_date and end_date must be ISO YYYY-MM-DD: Invalid isoformat string: 'not-a-date'"}]


async def test_top_scorers_rejects_malformed_end_date():
    rows = await server.top_scorers(SEASON_START, "2026/05/22")
    assert len(rows) == 1
    assert "error" in rows[0]


async def test_top_scorers_empty_window_returns_empty():
    rows = await server.top_scorers("2000-01-01", "2000-12-31")
    assert rows == []


async def test_top_scorers_respects_limit_cap():
    rows = await server.top_scorers(SEASON_START, SEASON_END, limit=999)
    assert len(rows) <= 50


async def test_search_players_substring_match():
    names = await server.search_players("Luka")
    assert "Luka Dončić" in names


async def test_search_players_case_insensitive():
    lower = await server.search_players("luka")
    upper = await server.search_players("LUKA")
    assert set(lower) == set(upper)


async def test_search_players_no_match():
    names = await server.search_players("zzzzzzzzz_no_such_player")
    assert names == []


async def test_player_season_averages_known_player():
    avg = await server.player_season_averages("Luka Dončić")
    assert avg["player"] == "Luka Dončić"
    assert avg["games"] >= 1
    for key in ("ppg", "rpg", "apg", "fg_pct", "avg_game_score"):
        assert isinstance(avg[key], float)


async def test_player_season_averages_missing_player():
    avg = await server.player_season_averages("Definitely Not A Player")
    assert "error" in avg


async def test_player_game_log_descending_by_date():
    games = await server.player_game_log("Luka Dončić", limit=5)
    assert len(games) > 0
    dates = [g["date"] for g in games]
    assert dates == sorted(dates, reverse=True)
    for g in games:
        assert set(g) >= {"date", "team", "opponent", "result", "minutes", "pts"}


async def test_player_game_log_respects_limit():
    games = await server.player_game_log("Luka Dončić", limit=3)
    assert len(games) <= 3


async def test_top_performances_valid_metrics():
    for metric in ("pts", "trb", "ast", "stl", "blk", "game_score", "plus_minus"):
        rows = await server.top_performances(metric=metric, limit=3)
        assert len(rows) == 3, f"metric {metric} returned {rows}"
        for row in rows:
            assert "player" in row
            assert row["minutes"] >= 20.0


async def test_top_performances_invalid_metric():
    rows = await server.top_performances(metric="bogus")
    assert len(rows) == 1
    assert "error" in rows[0]


async def test_top_performances_min_minutes_filter():
    rows = await server.top_performances(metric="pts", limit=5, min_minutes=35.0)
    assert all(r["minutes"] >= 35.0 for r in rows)


async def test_team_leaderboard_all_teams():
    rows = await server.team_leaderboard()
    assert len(rows) == 30
    teams = {r["team"] for r in rows}
    assert {"LAL", "BOS", "GSW"} <= teams


async def test_team_leaderboard_filter_consistency():
    rows = await server.team_leaderboard(team="LAL")
    assert len(rows) == 1
    row = rows[0]
    assert row["team"] == "LAL"
    assert row["wins"] + row["losses"] == row["games"]
    assert isinstance(row["ppg"], float)


async def test_head_to_head_returns_both_players():
    result = await server.head_to_head("Luka Dončić", "Shai Gilgeous-Alexander")
    assert set(result.keys()) == {"Luka Dončić", "Shai Gilgeous-Alexander"}
    for stats in result.values():
        assert {"games", "ppg", "rpg", "apg"} <= set(stats.keys())


async def test_schema_resource_describes_table():
    text = await server.schema_doc()
    assert "player_games" in text
    assert "game_date" in text


async def test_dataset_summary_resource_has_coverage():
    text = await server.dataset_summary()
    assert "Rows:" in text
    assert "Coverage:" in text
    assert "Top scorers" in text
