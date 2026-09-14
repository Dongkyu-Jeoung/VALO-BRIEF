import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from routers import predict as route
from services import prediction_cache as cache


class PredictionCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cache._results.clear()
        cache._inflight.clear()
        self.addCleanup(cache._results.clear)
        self.addCleanup(cache._inflight.clear)
        self.current = SimpleNamespace(team_id="our-id", team_name="Our", team_tag="TAG")
        self.result = {
            "blue_win_probability": 63.2, "predicted_winner": "BLUE",
            "blue_summary": {"acs": 210}, "red_summary": {"acs": 190},
        }
        self.clock = self.enterContext(patch.object(cache, "monotonic", return_value=100))
        self.info = self.enterContext(patch.object(
            route.predict_service.henrik_api, "get_premier_team",
            AsyncMock(return_value={"customization": {"image": "logo"}}),
        ))
        self.features = self.enterContext(patch.object(
            route.predict_service, "load_premier_prediction_features",
            AsyncMock(return_value=([], [])),
        ))
        self.model = self.enterContext(patch.object(
            route, "predict_from_player_features", side_effect=lambda *_: copy.deepcopy(self.result),
        ))
        self.save = self.enterContext(patch.object(route, "_save_prediction_result"))

    async def predict(self, name="Opp", current=None):
        return await route.predict_match(name, "TAG", current or self.current)

    async def test_hit_returns_complete_response_without_api_model_or_db(self):
        first = await self.predict()
        expected = copy.deepcopy(first)
        first["ourTeam"]["logoUrl"] = "changed"
        self.clock.return_value = 2499
        second = await self.predict()
        self.assertEqual(second, expected)
        self.assertEqual(second["opponentTeam"]["logoUrl"], "logo")
        self.assertEqual(self.info.await_count, 2)
        self.features.assert_awaited_once()
        self.model.assert_called_once()
        self.save.assert_called_once()

    async def test_expires_at_40_minutes_without_sliding_on_hits(self):
        await self.predict()
        self.clock.return_value = 2499
        await self.predict()
        self.clock.return_value = 2500
        self.result["blue_win_probability"] = 75
        result = await self.predict()
        self.assertEqual(result["blue_win_probability"], 75)
        self.assertEqual(self.model.call_count, 2)
        self.assertEqual(self.save.call_count, 2)

    async def test_teams_and_model_versions_have_separate_entries(self):
        await self.predict()
        await self.predict("Other")
        await self.predict(current=SimpleNamespace(
            team_id="other-id", team_name="Our", team_tag="TAG",
        ))
        with patch.object(route, "MATCH_MODEL_VERSION", "new-model"):
            await self.predict()
        self.assertEqual(self.model.call_count, 4)

    async def test_failed_prediction_is_not_cached(self):
        self.features.side_effect = ValueError("incomplete")
        with self.assertRaises(HTTPException) as caught:
            await self.predict()
        self.assertEqual(caught.exception.status_code, 422)
        self.assertFalse(cache._results)
        self.assertFalse(cache._inflight)
        self.features.side_effect = None
        await self.predict()
        self.assertEqual(self.features.await_count, 2)
        self.model.assert_called_once()

    async def test_concurrent_requests_share_work(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def features(*_):
            entered.set()
            await release.wait()
            return [], []

        self.features.side_effect = features
        first = asyncio.create_task(self.predict())
        await entered.wait()
        second = asyncio.create_task(self.predict())
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(first, second)
        self.assertEqual(results[0], results[1])
        self.assertIsNot(results[0], results[1])
        self.features.assert_awaited_once()
        self.model.assert_called_once()
        self.save.assert_called_once()

    async def test_cancelled_caller_does_not_cancel_shared_prediction(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def features(*_):
            entered.set()
            await release.wait()
            return [], []

        self.features.side_effect = features
        first = asyncio.create_task(self.predict())
        await entered.wait()
        second = asyncio.create_task(self.predict())
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        result = await second
        self.assertEqual(result["blue_win_probability"], 63.2)
        self.model.assert_called_once()

    async def test_database_failure_still_caches_successful_prediction(self):
        self.save.side_effect = RuntimeError("database unavailable")
        with self.assertLogs(route.logger, level="ERROR"):
            first = await self.predict()
        self.assertEqual(await self.predict(), first)
        self.model.assert_called_once()
        self.save.assert_called_once()

    async def test_capacity_evicts_least_recently_used_result(self):
        with patch.object(cache, "MAX_ENTRIES", 2):
            await self.predict("One")
            await self.predict("Two")
            await self.predict("One")
            await self.predict("Three")
            await self.predict("Two")
        self.assertEqual(len(cache._results), 2)
        self.assertEqual(self.model.call_count, 4)


if __name__ == "__main__":
    unittest.main()
