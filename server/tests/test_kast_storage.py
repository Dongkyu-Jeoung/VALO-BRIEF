import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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
    def test_special_events_reconciled_without_mutating_raw_data(self):
        for teamkill in (False, True):
            for counted in (False, True):
                match = match_fixture()
                for player in match["players"]["all_players"]:
                    player["team"] = "Red" if player["puuid"] == "e" else "Blue"
                match["kills"].append({"round": 2, "kill_time_in_round": 1000,
                                       "killer_puuid": "q" if teamkill else "p",
                                       "victim_puuid": "p", "assistants": []})
                match["players"]["all_players"][0]["stats"]["deaths"] += int(counted)
                original = copy.deepcopy(match)
                self.assertEqual(calculate_match_kast(match), {})
                kast = calculate_match_kast(match, reconcile_special=True)
                # A counted special death earns neither kill nor self-trade credit.
                self.assertEqual(kast["p"], 33.3 if counted else 66.7)
                self.assertEqual(match, original)

    def test_special_event_assists_validate_stats_without_kast_credit(self):
        for teamkill in (False, True):
            with self.subTest(teamkill=teamkill):
                match = match_fixture()
                for player in match["players"]["all_players"]:
                    player["team"] = "Red" if player["puuid"] == "e" else "Blue"
                match["players"]["all_players"].append({
                    "puuid": "r", "team": "Red",
                    "stats": {"kills": 0, "deaths": 0, "assists": 0},
                })
                match["kills"].append({
                    "round": 0, "kill_time_in_round": 2000,
                    "killer_puuid": "r" if teamkill else "e",
                    "victim_puuid": "e",
                    "assistants": [{"assistant_puuid": "p"}],
                })
                match["players"]["all_players"][0]["stats"]["assists"] = 1
                match["players"]["all_players"][1]["stats"]["deaths"] += 1
                original = copy.deepcopy(match)

                kast = calculate_match_kast(match, reconcile_special=True)
                # p died in round 0; the special event earns no assist or trade credit.
                self.assertEqual(kast.get("p"), 66.7)
                self.assertEqual(match, original)

                for assists in (0, 2):
                    with self.subTest(assists=assists):
                        match["players"]["all_players"][0]["stats"]["assists"] = assists
                        reports = []
                        self.assertEqual(calculate_match_kast(
                            match, report=reports.append, reconcile_special=True,
                        ), {})
                        self.assertTrue(reports[-1].startswith("EVENT_STATS_MISMATCH"))

    def test_ambiguous_special_deaths_and_unexplained_mismatch_rejected(self):
        match = match_fixture()
        event = {"round": 2, "kill_time_in_round": 1000,
                 "killer_puuid": "p", "victim_puuid": "p", "assistants": []}
        match["kills"].extend([event, {**event, "kill_time_in_round": 2000}])
        match["players"]["all_players"][0]["stats"]["deaths"] += 1
        self.assertEqual(calculate_match_kast(match, reconcile_special=True), {})
        match = match_fixture()
        match["kills"].pop()
        self.assertEqual(calculate_match_kast(match, reconcile_special=True), {})

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
