import copy
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from services import match_history, match_sync, team_engagement_cache


def match_fixture():
    return {
        "metadata": {"matchid": "m", "game_start": 1704067200},
        "teams": {
            "red": {"roster": {"id": "red-id", "name": "Our", "tag": "T"}, "has_won": True},
            "blue": {"roster": {"id": "blue-id", "name": "Opp", "tag": "T"}, "has_won": False},
        },
        "rounds": [{"raw": "must not be stored"}],
        "players": {"all_players": [{"puuid": "p", "stats": {"kills": 1}}]},
    }


class MatchStoragePolicyTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        # Fail on every direct DB operation. Compact-cache writes are tested separately.
        for name in ("add", "add_all", "execute", "flush", "commit", "get", "query"):
            getattr(self.db, name).side_effect = AssertionError("Unexpected DB operation: " + name)
        self.save = self.enterContext(patch.object(team_engagement_cache, "upsert_match_engagement"))
        self.enterContext(patch.object(team_engagement_cache, "ENGAGEMENT_CACHE_ENABLED", True))
        self.enterContext(patch.object(match_history.engagement_predictor, "trade_rate_from_matches", return_value=50))
        self.enterContext(patch.object(match_history.engagement_predictor, "duelist_acs_from_matches", return_value=220))

    def test_only_compact_rows_are_written_for_both_teams(self):
        match = match_fixture()
        original = copy.deepcopy(match)
        self.assertEqual(match_history.upsert_match_engagement_summary(self.db, "m", match), 2)
        self.assertEqual(match, original)
        red, blue = self.save.call_args_list
        self.assertEqual(red.args, (self.db, "red-id", "m"))
        self.assertEqual(blue.args, (self.db, "blue-id", "m"))
        self.assertEqual(red.kwargs, {
            "opponent_team_id": "blue-id", "game_start": datetime(2024, 1, 1, 9),
            "trade_rate": 50, "duelist_acs": 220, "win": True,
        })
        self.assertFalse(blue.kwargs["win"])

    def test_missing_team_id_uses_registered_team_without_inserting_accounts(self):
        match = match_fixture()
        del match["teams"]["red"]["roster"]["id"]
        with patch.object(match_history, "_find_team_id", return_value="registered-id") as lookup:
            match_history.upsert_match_engagement_summary(self.db, "m", match)
        lookup.assert_called_once_with(self.db, "Our", "T")
        self.assertEqual(self.save.call_args_list[0].args[1], "registered-id")

    def test_unknown_team_is_skipped_and_history_timestamp_is_used(self):
        match = match_fixture()
        match["metadata"].pop("game_start")
        match["teams"]["red"]["roster"].pop("id")
        with patch.object(match_history, "_find_team_id", return_value=None):
            match_history.upsert_match_engagement_summary(self.db, "m", match, "2024-01-01T00:00:00Z")
        self.save.assert_called_once()
        self.assertIsNone(self.save.call_args.kwargs["opponent_team_id"])
        self.assertEqual(self.save.call_args.kwargs["game_start"], datetime(2024, 1, 1, 9))

    def test_disabled_cache_and_empty_match_id_do_not_write(self):
        match_history.upsert_match_engagement_summary(self.db, "", match_fixture())
        with patch.object(team_engagement_cache, "ENGAGEMENT_CACHE_ENABLED", False):
            match_history.upsert_match_engagement_summary(self.db, "m", match_fixture())
        self.save.assert_not_called()

    def test_profile_accumulation_uses_only_compact_cache(self):
        from routers import teams
        teams._accumulate_match_history(self.db, ["m"], [match_fixture()])
        self.assertEqual(self.save.call_count, 2)


class SignupStoragePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_signup_skips_cached_matches_and_deduplicates_history(self):
        db = MagicMock()
        db.get.side_effect = AssertionError("Must not read matches table")
        db.execute.side_effect = AssertionError("Must not load raw-match reference tables")
        with patch.object(team_engagement_cache, "ENGAGEMENT_CACHE_ENABLED", True), \
             patch.object(team_engagement_cache, "has_match", side_effect=[True, False]) as cached, \
             patch.object(match_sync.henrik_api, "get_premier_team_history", AsyncMock(return_value={
                 "league_matches": [{"id": "cached"}, {"id": "m"}, {"id": "m"}],
             })), \
             patch.object(match_sync.henrik_api, "get_match_detail", AsyncMock(return_value=match_fixture())) as api, \
             patch.object(team_engagement_cache, "upsert_match_engagement") as save, \
             patch.object(match_history.engagement_predictor, "trade_rate_from_matches", return_value=50), \
             patch.object(match_history.engagement_predictor, "duelist_acs_from_matches", return_value=220):
            await match_sync._sync(db, "red-id", "Our", "T")
        api.assert_awaited_once_with("m")
        self.assertEqual(cached.call_count, 2)
        self.assertEqual(save.call_count, 2)
        db.add.assert_not_called()
        db.flush.assert_not_called()
        db.commit.assert_not_called()

    async def test_signup_does_not_fetch_when_cache_is_disabled(self):
        with patch.object(team_engagement_cache, "ENGAGEMENT_CACHE_ENABLED", False), \
             patch.object(match_sync, "SessionLocal") as database, \
             patch.object(match_sync.henrik_api, "get_premier_team_history", AsyncMock()) as api:
            await match_sync.sync_team_match_history("Our", "T")
        database.assert_not_called()
        api.assert_not_awaited()

    async def test_signup_rejects_unrelated_match_and_stops_on_rate_limit(self):
        unrelated = match_fixture()
        unrelated["teams"]["red"]["roster"]["name"] = "Other"
        with patch.object(team_engagement_cache, "ENGAGEMENT_CACHE_ENABLED", True), \
             patch.object(team_engagement_cache, "has_match", return_value=False), \
             patch.object(match_sync.henrik_api, "get_premier_team_history", AsyncMock(return_value={
                 "league_matches": [{"id": "unrelated"}, {"id": "limited"}, {"id": "remaining"}],
             })), \
             patch.object(match_sync.henrik_api, "get_match_detail", AsyncMock(side_effect=[
                 unrelated, match_sync.henrik_api.HenrikRateLimitError("limited"),
             ])) as api, \
             patch.object(match_history, "upsert_match_engagement_summary") as save:
            await match_sync._sync(MagicMock(), "red-id", "Our", "T")
        self.assertEqual(api.await_count, 2)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
