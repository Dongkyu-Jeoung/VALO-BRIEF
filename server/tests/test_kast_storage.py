import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services import match_history
from services.match_sync import calculate_match_kast
from services import backfill_kast


def match_fixture():
    return {
        "rounds": [{}, {}, {}],
        "teams": {"red": {"rounds_won": 3}, "blue": {"rounds_won": 0}},
        "players": {"all_players": [
            {"puuid": "p", "stats": {"kills": 0, "deaths": 2, "assists": 0}},
            {"puuid": "e", "stats": {"kills": 2, "deaths": 1, "assists": 0}},
            {"puuid": "q", "stats": {"kills": 1, "deaths": 0, "assists": 0}},
        ]},
        "kills": [
            {"round": 0, "kill_time_in_round": 1000, "killer_puuid": "e", "victim_puuid": "p", "assistants": []},
            {"round": 1, "kill_time_in_round": 1000, "killer_puuid": "e", "victim_puuid": "p", "assistants": []},
            {"round": 1, "kill_time_in_round": 2000, "killer_puuid": "q", "victim_puuid": "e", "assistants": []},
        ],
    }


class KastStorageTests(unittest.TestCase):
    def test_trade_and_no_kill_survival(self):
        self.assertEqual(calculate_match_kast(match_fixture())["p"], 66.7)

    def test_incomplete_events_are_not_survival(self):
        for key in ("kills", "rounds"):
            match = match_fixture()
            match.pop(key)
            self.assertEqual(calculate_match_kast(match), {})
        match = match_fixture()
        match["kills"] = []
        self.assertEqual(calculate_match_kast(match), {})

    def test_partial_and_bad_round_events(self):
        match = match_fixture()
        match["kills"].pop()
        self.assertEqual(calculate_match_kast(match), {})
        match = match_fixture()
        match["kills"][0]["round"] = 3
        self.assertEqual(calculate_match_kast(match), {})

    def test_score_round_mismatch(self):
        match = match_fixture()
        match["teams"]["red"]["rounds_won"] = 4
        self.assertEqual(calculate_match_kast(match), {})

    def test_upsert_fills_and_preserves_kast(self):
        for complete in (True, False):
            match = copy.deepcopy(match_fixture())
            if not complete:
                match.pop("kills")
            rows = [MagicMock(kast=42.) for _ in range(3)]
            db = MagicMock()
            db.get.return_value = None
            db.query.return_value.filter.return_value.first.side_effect = rows
            with patch.object(match_history, "_find_team_id", return_value=None), \
                 patch.object(match_history, "_load_map_uuid_by_name", return_value={}), \
                 patch.object(match_history, "_load_agent_info_by_name", return_value={}), \
                 patch.object(match_history, "_ensure_riot_account_placeholder"):
                match_history.upsert_match_history(db, "m", match)
            self.assertEqual(rows[0].kast, 66.7 if complete else 42.)
            db.commit.assert_called_once()


class BackfillTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_does_not_fetch_or_write(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [("m",)]
        with patch.object(backfill_kast, "SessionLocal") as factory, \
             patch.object(backfill_kast.henrik_api, "get_match_detail", new_callable=AsyncMock) as api:
            factory.return_value.__enter__.return_value = db
            self.assertEqual(await backfill_kast.backfill("team", 20), 0)
        api.assert_not_awaited()
        db.execute.assert_not_called()

    async def test_apply_updates_only_null_kast(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [("m",)]
        db.execute.return_value.rowcount = 1
        match = match_fixture()
        match["metadata"] = {"matchid": "m"}
        with patch.object(backfill_kast, "SessionLocal") as factory, \
             patch.object(backfill_kast.henrik_api, "get_match_detail", new_callable=AsyncMock, return_value=match) as api:
            factory.return_value.__enter__.return_value = db
            self.assertEqual(await backfill_kast.backfill("team", 20, apply=True), 3)
        api.assert_awaited_once_with("m")
        for call in db.execute.call_args_list:
            self.assertIn("kast IS NULL", str(call.args[0]))
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
