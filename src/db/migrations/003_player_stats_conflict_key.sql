ALTER TABLE player_stats
    DROP CONSTRAINT IF EXISTS unique_game_player;

ALTER TABLE player_stats
    ADD CONSTRAINT unique_game_player UNIQUE (game_id, player_name);
