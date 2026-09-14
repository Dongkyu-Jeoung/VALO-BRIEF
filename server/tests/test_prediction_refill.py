import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

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
    async def test_retired_refill_does_not_fetch_or_open_database(self):
        from services import henrik_api
        from database import connection
        checkpoint = Mock()
        with patch.object(henrik_api, "get_premier_team_history", AsyncMock()) as history, \
             patch.object(henrik_api, "get_match_detail", AsyncMock()) as detail, \
             patch.object(connection, "SessionLocal") as database:
            await refill.refill("team", "Our", "T", ["p"], checkpoint)
            refill.schedule_refill("team", "Our", "T", ["p"], checkpoint)
        history.assert_not_awaited()
        detail.assert_not_awaited()
        database.assert_not_called()
        self.assertEqual(checkpoint.call_count, 2)
        self.assertTrue(all("Disabled" in call.args[0] for call in checkpoint.call_args_list))

    async def test_retired_agent_backfill_does_not_rewrite_matches(self):
        import backfill_missing_agents
        with self.assertRaisesRegex(RuntimeError, "Raw match storage is disabled"):
            await backfill_missing_agents.backfill()


if __name__ == "__main__":
    unittest.main()
