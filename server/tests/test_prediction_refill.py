import asyncio
import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ml import db_rolling, predictor
from services import prediction_refill as refill


class ValidMatchesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.db = Session(self.engine)
        self.db.execute(text("CREATE TABLE matches (match_id TEXT PRIMARY KEY, game_start DATETIME, team_a_id TEXT, team_b_id TEXT, rounds_won_a INT, rounds_won_b INT, mode TEXT)"))
        self.db.execute(text("CREATE TABLE ref_agents (uuid TEXT PRIMARY KEY, display_name TEXT)"))
        self.db.execute(text("CREATE TABLE match_player_stats (match_id TEXT, puuid TEXT, team_id TEXT, agent_uuid TEXT, role_type TEXT, acs REAL, kills INT, deaths INT, kast REAL, headshot_pct REAL)"))
        self.db.execute(text("INSERT INTO ref_agents VALUES ('latest', 'Jett'), ('old', 'Sage')"))
        for i in range(7):
            self.db.execute(text("INSERT INTO matches VALUES (:id,:dt,'A',NULL,13,8,'Premier')"),
                            {"id": str(i), "dt": datetime.now()-timedelta(days=90+i)})
            self.db.execute(text("INSERT INTO match_player_stats VALUES (:id,'p','A',:agent,NULL,200,12,10,:kast,20)"),
                            {"id": str(i), "agent": "latest" if i == 0 else "old", "kast": None if i < 2 else 75})

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_skips_invalid_and_preserves_latest_agent(self):
        df = db_rolling.load_recent_matches(self.db, "p")
        self.assertEqual(df.match_id.tolist(), ["2", "3", "4", "5", "6"])
        self.assertEqual(predictor._db_player_feature(self.db, "p")["agent"], "Jett")

    def test_zero_and_partial_valid_rows(self):
        self.assertTrue(db_rolling.load_recent_matches(self.db, "missing").empty)
        self.db.execute(text("UPDATE match_player_stats SET kast=NULL WHERE match_id IN ('4','5','6')"))
        self.assertEqual(len(db_rolling.load_recent_matches(self.db, "p")), 2)
        self.assertIsNone(predictor._db_player_feature(self.db, "p"))
        self.db.execute(text("UPDATE match_player_stats SET kast=NULL"))
        self.assertIsNone(predictor._db_player_feature(self.db, "p"))

    def test_zero_db_uses_cache_and_reports_refill(self):
        blue = [{"puuid": f"b{i}"} for i in range(5)]
        red = [{"puuid": f"r{i}"} for i in range(5)]
        feature = dict(agent="Jett", recent_acs=200., recent_kd=1.2, recent_kast=75., recent_headshot_pct=20., recent_winrate=.6)
        missing = []
        with patch.object(predictor, "_db_player_feature", return_value=None), \
             patch.object(predictor, "get_cached_player_feature", return_value=feature), \
             patch.object(predictor, "build_player_feature", side_effect=AssertionError("API called")), redirect_stdout(io.StringIO()):
            result = predictor.predict_blue_win(blue, red, db=object(), db_missing_players=missing)
        self.assertEqual(len(missing), 5)
        self.assertIn("blue_win_probability", result)


class RefillTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_db_fills_then_stops(self):
        history = {"league_matches": [{"id": "m1", "started_at": "2026-09-09"}, {"id": "m2", "started_at": "2026-09-08"}]}
        match = {"metadata": {"matchid": "m1"}, "teams": {"red": {"roster": {"name": "Our", "tag": "T"}}}}
        with patch.object(refill, "_remaining", side_effect=[["p"], []]), \
             patch.object(refill, "_store") as store, \
             patch.object(refill.henrik_api, "get_premier_team_history", AsyncMock(return_value=history)), \
             patch.object(refill.henrik_api, "get_match_detail", AsyncMock(return_value=match)) as api:
            await refill.refill("team", "Our", "T", ["p"], lambda msg: None)
        api.assert_awaited_once_with("m1")
        store.assert_called_once()

    async def test_empty_history_finishes_without_detail_calls(self):
        with patch.object(refill, "_remaining", return_value=["p"]), \
             patch.object(refill.henrik_api, "get_premier_team_history", AsyncMock(return_value={})), \
             patch.object(refill.henrik_api, "get_match_detail", AsyncMock()) as api:
            await refill.refill("team", "Our", "T", ["p"], lambda msg: None)
        api.assert_not_awaited()

    async def test_duplicate_and_cooldown(self):
        refill._last_attempt.clear()
        with patch.object(refill, "refill", AsyncMock()) as worker:
            refill.schedule_refill("team", "Our", "T", ["p"], lambda msg: None)
            task = refill._tasks["team"]
            refill.schedule_refill("team", "Our", "T", ["p"], lambda msg: None)
            await task
            refill.schedule_refill("team", "Our", "T", ["p"], lambda msg: None)
        self.assertEqual(worker.await_count, 1)
        self.assertNotIn("team", refill._tasks)
        refill._last_attempt.clear()


if __name__ == "__main__":
    unittest.main()
