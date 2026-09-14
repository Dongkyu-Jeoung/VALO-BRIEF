import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services import predict_service as service
from ml import predictor
from ml.model_loader import get_feature_columns


def match_fixture():
    players = []
    teams = {}
    for side, name in (("blue", "Our"), ("red", "Opp")):
        members = [f"{side}{i}" for i in range(5)]
        teams[side] = {
            "roster": {"name": name, "tag": "TAG", "members": members},
            "rounds_won": 1 if side == "blue" else 0,
            "has_won": side == "blue",
        }
        for puuid in members:
            players.append({
                "puuid": puuid, "team": side.title(), "character": "Jett",
                "stats": {"score": 200, "kills": 0, "deaths": 0, "assists": 0,
                          "headshots": 1, "bodyshots": 3, "legshots": 0},
            })
    return {"teams": teams, "players": {"all_players": players}, "rounds": [{}], "kills": []}


def history(count):
    return {"league_matches": [{"id": str(i), "started_at": f"2025-01-{i+1:02d}T00:00:00Z"}
                               for i in range(count)]}


class PremierTests(unittest.IsolatedAsyncioTestCase):
    def test_kast_logging_toggle_preserves_validation_and_diagnostics(self):
        match = match_fixture()
        match["players"]["all_players"][0]["stats"]["kills"] = 1
        reasons = []
        for value, enabled in (("", False), ("false", False), ("TRUE", True), ("1", True)):
            diagnostic = {}
            with patch.dict(os.environ, {"PREMIER_KAST_DEBUG": value}), \
                 patch.object(service.logger, "warning") as warning:
                self.assertEqual(service._premier_player_rows(match, "Our", "TAG", "match-1", diagnostic), [])
            kast_logs = [call for call in warning.call_args_list if call.args[0].startswith("[PREMIER KAST]")]
            self.assertEqual(bool(kast_logs), enabled)
            self.assertIn("EVENT_STATS_MISMATCH", diagnostic["reason"])
            reasons.append(diagnostic["reason"])
        self.assertTrue(all(reason == reasons[0] for reason in reasons))

    async def test_endpoint_returns_422_without_inference(self):
        from routers import predict as route
        from fastapi import HTTPException
        with patch.object(service.henrik_api, "get_premier_team", AsyncMock(return_value={"name": "team"})), \
             patch.object(service, "load_premier_prediction_features", AsyncMock(side_effect=ValueError(service.INSUFFICIENT_PREMIER_MESSAGE))), \
             patch.object(route, "predict_from_player_features") as model:
            with self.assertRaises(HTTPException) as caught:
                await route.predict_match("Opp", "TAG", SimpleNamespace(team_name="Our", team_tag="TAG"))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail, service.INSUFFICIENT_PREMIER_MESSAGE)
        model.assert_not_called()

    async def test_selection_count_order_and_deduplication(self):
        for count in (0, 2, 3, 4, 5, 8):
            data = history(count)
            data["league_matches"] += data["league_matches"][:1] + [{"id": "bad"}]
            with patch.object(service.henrik_api, "get_premier_team_history", AsyncMock(return_value=data)):
                if count < 3:
                    with self.assertRaisesRegex(ValueError, service.INSUFFICIENT_PREMIER_MESSAGE):
                        await service.get_recent_premier_match_ids("Our", "TAG")
                else:
                    self.assertEqual(await service.get_recent_premier_match_ids("Our", "TAG"),
                                     [str(i) for i in range(count-1, max(-1, count-6), -1)])

    async def test_shared_matches_fetched_once_and_model_called_once(self):
        with patch.object(service.henrik_api, "get_premier_team_history", AsyncMock(return_value=history(8))) as hist, \
             patch.object(service.henrik_api, "get_match_detail", AsyncMock(return_value=match_fixture())) as detail:
            blue, red = await service.load_premier_prediction_features("Our", "TAG", "Opp", "TAG")
        self.assertEqual(hist.await_count, 2)
        self.assertEqual(detail.await_count, 5)
        self.assertEqual(blue[0]["recent_acs"], 200)
        self.assertEqual(blue[0]["recent_headshot_pct"], 25)
        self.assertEqual(blue[0]["recent_winrate"], 1)
        self.assertEqual(red[0]["recent_winrate"], 0)
        with patch.object(predictor.model, "predict_proba", return_value=[[0.25, 0.75]]) as model:
            result = predictor.predict_from_player_features(blue, red)
        model.assert_called_once()
        frame = model.call_args.args[0]
        self.assertEqual(frame.shape, (1, 18))
        self.assertEqual(list(frame.columns), list(get_feature_columns()))
        self.assertEqual(result["blue_win_probability"], 75)
        self.assertEqual(result["red_summary"]["winrate"], 0)

    async def test_insufficient_history_never_fetches_details(self):
        with patch.object(service.henrik_api, "get_premier_team_history", AsyncMock(return_value=history(2))), \
             patch.object(service.henrik_api, "get_match_detail", AsyncMock()) as detail:
            with self.assertRaises(ValueError):
                await service.load_premier_prediction_features("Our", "TAG", "Opp", "TAG")
        detail.assert_not_awaited()

    def test_averages_recent_matches_and_rejects_incomplete_data(self):
        matches = [match_fixture() for _ in range(3)]
        matches[0]["players"]["all_players"][0]["stats"]["score"] = 500
        features = service.build_premier_player_features(matches, "Our", "TAG")
        self.assertEqual(features[0]["recent_acs"], 220)
        for missing in (None, {}, {"kills": []}):
            with self.assertRaises(ValueError):
                service.build_premier_player_features([*matches[:2], missing], "Our", "TAG")
        broken = copy.deepcopy(matches)
        del broken[0]["players"]["all_players"][0]["stats"]["headshots"]
        with self.assertRaises(ValueError):
            service.build_premier_player_features(broken, "Our", "TAG")

    def test_roster_change_uses_all_appearances(self):
        matches = [match_fixture() for _ in range(3)]
        matches[0]["teams"]["blue"]["roster"]["members"][0] = "substitute"
        matches[0]["players"]["all_players"][0]["puuid"] = "substitute"
        matches[0]["players"]["all_players"][0]["stats"]["score"] = 500
        matches[0]["players"]["all_players"][0]["character"] = "Sage"
        features = service.build_premier_player_features(matches, "Our", "TAG")
        self.assertEqual(features[0]["recent_acs"], 220)
        self.assertEqual(sum(p["agent"] == "Jett" for p in features), 4)
        self.assertTrue(all("puuid" not in p for p in features))
        for match in matches:
            match["players"]["all_players"].reverse()
        reordered = service.build_premier_player_features(matches, "Our", "TAG")
        from ml.team_feature import build_team_feature
        self.assertTrue(build_team_feature(features, features).equals(build_team_feature(reordered, reordered)))

    def test_special_event_assists_can_reach_saved_model(self):
        matches = [match_fixture() for _ in range(3)]
        matches[0]["kills"] = [{
            "round": 0, "kill_time_in_round": 1000,
            "killer_puuid": "blue0", "victim_puuid": "blue0",
            "assistants": [{"assistant_puuid": "red0"}],
        }]
        matches[0]["players"]["all_players"][0]["stats"]["deaths"] = 1
        matches[0]["players"]["all_players"][5]["stats"]["assists"] = 1
        blue = service.build_premier_player_features(matches, "Our", "TAG")
        red = service.build_premier_player_features(matches, "Opp", "TAG")
        self.assertEqual(blue[0]["recent_kast"], 93.33)
        self.assertEqual(red[0]["recent_kast"], 100)
        result = predictor.predict_from_player_features(blue, red)
        self.assertTrue(0 <= result["blue_win_probability"] <= 100)

    def test_saved_model_accepts_premier_features(self):
        matches = [match_fixture() for _ in range(3)]
        result = predictor.predict_from_player_features(
            service.build_premier_player_features(matches, "Our", "TAG"),
            service.build_premier_player_features(matches, "Opp", "TAG"),
        )
        self.assertTrue(0 <= result["blue_win_probability"] <= 100)


if __name__ == "__main__":
    unittest.main()
