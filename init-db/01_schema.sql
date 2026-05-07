-- Final, query-friendly table the MCP server reads from.
CREATE TABLE player_games (
    id          SERIAL PRIMARY KEY,
    game_date   DATE         NOT NULL,
    player      TEXT         NOT NULL,
    team        TEXT         NOT NULL,
    opponent    TEXT         NOT NULL,
    result      CHAR(1)      NOT NULL CHECK (result IN ('W', 'L')),
    minutes     NUMERIC(5,2) NOT NULL,   -- decimal minutes (e.g. 40:59 -> 40.98)
    fg          INT,
    fga         INT,
    fg_pct      NUMERIC(4,3),
    three_p     INT,
    three_pa    INT,
    three_pct   NUMERIC(4,3),
    ft          INT,
    fta         INT,
    ft_pct      NUMERIC(4,3),
    orb         INT,
    drb         INT,
    trb         INT,
    ast         INT,
    stl         INT,
    blk         INT,
    tov         INT,
    pf          INT,
    pts         INT,
    plus_minus  NUMERIC(5,1),
    game_score  NUMERIC(5,1)
);

CREATE INDEX idx_pg_date    ON player_games (game_date);
CREATE INDEX idx_pg_player  ON player_games (player);
CREATE INDEX idx_pg_team    ON player_games (team);
CREATE INDEX idx_pg_pts     ON player_games (pts DESC);
CREATE INDEX idx_pg_gmsc    ON player_games (game_score DESC);

-- Staging table mirrors the raw CSV column order exactly so COPY can ingest it
-- with no header gymnastics. We drop it after the transform step.
CREATE TABLE staging_games (
    player     TEXT,
    tm         TEXT,
    opp        TEXT,
    result     TEXT,
    mp         TEXT,
    fg         INT,
    fga        INT,
    fg_pct     NUMERIC,
    three_p    INT,
    three_pa   INT,
    three_pct  NUMERIC,
    ft         INT,
    fta        INT,
    ft_pct     NUMERIC,
    orb        INT,
    drb        INT,
    trb        INT,
    ast        INT,
    stl        INT,
    blk        INT,
    tov        INT,
    pf         INT,
    pts        INT,
    plus_minus NUMERIC,
    gm_sc      NUMERIC,
    game_date  DATE
);
