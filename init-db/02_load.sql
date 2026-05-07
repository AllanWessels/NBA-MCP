-- Bulk load the CSV into the staging table.
-- The init scripts run as the postgres user from inside the container,
-- and /docker-entrypoint-initdb.d is mounted from ./init-db on the host.
COPY staging_games FROM '/docker-entrypoint-initdb.d/nba_dailyleaders_full.csv'
    WITH (FORMAT CSV, HEADER true);

-- Transform into the clean table:
--   - rename Tm/Opp -> team/opponent
--   - convert "MM:SS" minutes string to decimal minutes
--   - cast result to a single char
INSERT INTO player_games (
    game_date, player, team, opponent, result, minutes,
    fg, fga, fg_pct, three_p, three_pa, three_pct,
    ft, fta, ft_pct, orb, drb, trb, ast, stl, blk, tov, pf, pts,
    plus_minus, game_score
)
SELECT
    game_date,
    player,
    tm,
    opp,
    result::CHAR(1),
    (split_part(mp, ':', 1)::int + split_part(mp, ':', 2)::int / 60.0)::NUMERIC(5,2),
    fg, fga, fg_pct, three_p, three_pa, three_pct,
    ft, fta, ft_pct, orb, drb, trb, ast, stl, blk, tov, pf, pts,
    plus_minus, gm_sc
FROM staging_games;

DROP TABLE staging_games;

-- Sanity-check row count surfaces in the container logs on first start.
DO $$
DECLARE n bigint;
BEGIN
    SELECT count(*) INTO n FROM player_games;
    RAISE NOTICE 'Loaded % player-game rows', n;
END $$;
