import asyncio
import unittest
from email.utils import formatdate
from unittest.mock import AsyncMock, Mock, patch

import httpx

from services import henrik_api, rate_limiter as limiter
from services.henrik_config import build_client_configs
from ml import valorant_git


class HeaderTests(unittest.TestCase):
    def test_long_and_date_retry_after(self):
        self.assertEqual(limiter.retry_after_seconds({"Retry-After": "120"}), 120)
        with patch.object(limiter.time, "time", return_value=1_800_000_000):
            date = formatdate(1_800_000_090, usegmt=True)
            self.assertEqual(limiter.retry_after_seconds({"Retry-After": date}), 90)
            self.assertEqual(limiter.retry_after_seconds({"X-Ratelimit-Reset": "1800000090"}), 90)

    def test_multiple_exhausted_buckets(self):
        headers = {"ratelimit": '"minute";r=0;t=40, "hour";r=0;t=180, "day";r=5;t=900'}
        self.assertEqual(limiter.retry_after_seconds(headers), 180)
        self.assertEqual(limiter.retry_after_seconds({"x-ratelimit-reset": "45"}), 45)

    def test_invalid_headers_use_safe_fallback(self):
        for value in ("nan", "inf", "-10", "0", "invalid"):
            self.assertEqual(limiter.retry_after_seconds({"retry-after": value}), 60)


class SharedCooldownTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 추가 키가 없을 때 두 클라이언트가 같은 예산을 쓰는 경로도 유지한다.
        general, ml = build_client_configs("test-general", None)
        self.bucket = general.limiter
        self.general_patch = patch.object(henrik_api, "_API", general)
        self.ml_patch = patch.object(valorant_git, "_API", ml)
        self.general_patch.start()
        self.ml_patch.start()
        self.now = 100.0
        clock = Mock(wraps=limiter.time)
        clock.monotonic.side_effect = lambda: self.now
        self.clock_patch = patch.object(limiter, "time", clock)
        self.clock_patch.start()

    def tearDown(self):
        self.clock_patch.stop()
        self.general_patch.stop()
        self.ml_patch.stop()

    def advance(self, delay):
        self.now += delay

    async def advance_async(self, delay):
        self.advance(delay)

    async def test_cooldown_applies_to_sync_and_async_without_shortening(self):
        self.bucket.register_rate_limit({"retry-after": "90"})
        self.bucket.register_rate_limit({"retry-after": "10"})
        self.assertAlmostEqual(self.bucket._record_or_wait_seconds(), 90.05)
        self.assertEqual(len(self.bucket._request_times), 0)
        with patch.object(limiter.time, "sleep", side_effect=self.advance) as sleep:
            self.bucket.throttle_sync()
        sleep.assert_called_once()
        self.bucket.register_rate_limit({"retry-after": "40"})
        with patch.object(asyncio, "sleep", side_effect=self.advance_async) as sleep:
            await self.bucket.throttle_async()
        sleep.assert_awaited_once()
        self.assertGreaterEqual(self.now, 230)

    async def test_async_client_waits_before_retry_and_shares_final_429(self):
        client = Mock()
        client.get = AsyncMock(side_effect=[
            httpx.Response(429, headers={"retry-after": "40"}),
            httpx.Response(429, headers={"retry-after": "80"}),
        ])
        with patch.object(henrik_api, "_get_client", return_value=client), \
             patch.object(asyncio, "sleep", side_effect=self.advance_async):
            with self.assertRaises(henrik_api.HenrikRateLimitError) as caught:
                await henrik_api._get_uncached("/test", None)
        self.assertEqual(client.get.await_count, 2)
        self.assertAlmostEqual(self.now, 140.05)
        self.assertAlmostEqual(caught.exception.retry_after, 80.05)
        self.assertAlmostEqual(self.bucket._record_or_wait_seconds(), 80.05)

    async def test_sync_client_waits_then_returns_success(self):
        success = Mock(status_code=200)
        with patch.object(valorant_git.requests, "get", side_effect=[
            Mock(status_code=429, headers={"Retry-After": "90"}), success]) as get, \
             patch.object(limiter.time, "sleep", side_effect=self.advance):
            self.assertIs(valorant_git.api_get("https://example.test/match"), success)
        self.assertEqual(get.call_count, 2)
        self.assertAlmostEqual(self.now, 190.05)

    async def test_async_success_after_429_and_non_rate_limit_response(self):
        client = Mock()
        client.get = AsyncMock(side_effect=[
            httpx.Response(429, headers={"retry-after": "40"}),
            httpx.Response(200, json={"data": {"match": "m"}}),
            httpx.Response(404),
        ])
        with patch.object(henrik_api, "_get_client", return_value=client), \
             patch.object(asyncio, "sleep", side_effect=self.advance_async):
            self.assertEqual(await henrik_api._get_uncached("/test", None), {"match": "m"})
            self.assertIsNone(await henrik_api._get_uncached("/missing", None))
        self.assertEqual(client.get.await_count, 3)
        self.assertAlmostEqual(self.now, 140.05)

    async def test_local_budget_still_limits_58_requests(self):
        for _ in range(58):
            self.assertEqual(self.bucket._record_or_wait_seconds(), 0)
        self.assertGreater(self.bucket._record_or_wait_seconds(), 60)
        self.advance(61)
        self.assertEqual(self.bucket._record_or_wait_seconds(), 0)


class DualKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_request_budgets(self):
        general, ml = build_client_configs("test-general", "test-ml")
        with patch.object(limiter.time, "monotonic", return_value=100):
            for _ in range(58):
                self.assertEqual(general.limiter._record_or_wait_seconds(), 0)
            self.assertGreater(general.limiter._record_or_wait_seconds(), 0)
            for _ in range(43):
                self.assertEqual(ml.limiter._record_or_wait_seconds(), 0)
            self.assertGreater(ml.limiter._record_or_wait_seconds(), 0)

    async def test_sync_429_does_not_block_general_client(self):
        general, ml = build_client_configs("test-general", "test-ml")
        client = Mock(get=AsyncMock(return_value=httpx.Response(200, json={"data": "ok"})))
        with patch.object(valorant_git, "_API", ml), \
             patch.object(valorant_git, "MAX_RETRIES_ON_429", 0), \
             patch.object(valorant_git.requests, "get", return_value=Mock(status_code=429, headers={"retry-after": "90"})) as get, \
             patch.object(henrik_api, "_API", general), \
             patch.object(henrik_api, "_get_client", return_value=client), \
             patch.object(asyncio, "sleep", AsyncMock(side_effect=AssertionError("other key delayed"))):
            with self.assertRaises(henrik_api.HenrikRateLimitError):
                valorant_git.api_get("https://example.test/match")
            self.assertEqual(await henrik_api._get_uncached("/test", None), "ok")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "test-ml")
        self.assertGreater(ml.limiter._record_or_wait_seconds(), 0)
        self.assertEqual(general.limiter._record_or_wait_seconds(), 0)

    async def test_general_429_does_not_block_ml_client(self):
        general, ml = build_client_configs("test-general", "test-ml")
        general.limiter.register_rate_limit({"retry-after": "90"})
        success = Mock(status_code=200)
        with patch.object(valorant_git, "_API", ml), \
             patch.object(valorant_git.requests, "get", return_value=success), \
             patch.object(limiter.time, "sleep", side_effect=AssertionError("other key delayed")):
            self.assertIs(valorant_git.api_get("https://example.test/match"), success)
        self.assertGreater(general.limiter._record_or_wait_seconds(), 0)

    async def test_general_client_uses_general_authorization(self):
        general, _ = build_client_configs("test-general", "test-ml")
        with patch.object(henrik_api, "_API", general), patch.object(henrik_api, "_client", None):
            client = henrik_api._get_client()
            self.assertEqual(client.headers["Authorization"], "test-general")
            await henrik_api.aclose_client()

    async def test_missing_or_duplicate_key_reuses_general_budget(self):
        for value in (None, "", "   ", "test-general", " test-general "):
            general, ml = build_client_configs("test-general", value)
            self.assertIs(general, ml)
            general.limiter.register_rate_limit({"retry-after": "90"})
            self.assertGreater(ml.limiter._record_or_wait_seconds(), 0)

    async def test_config_repr_does_not_include_credentials(self):
        general, ml = build_client_configs("test-general-secret", "test-ml-secret")
        self.assertNotIn("secret", repr(general))
        self.assertNotIn("secret", repr(ml))


if __name__ == "__main__":
    unittest.main()
