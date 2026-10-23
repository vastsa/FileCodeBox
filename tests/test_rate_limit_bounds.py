"""IPRateLimit is bounded and uses a monotonic clock."""
import unittest
from unittest import mock

from apps.base.dependencies import IPRateLimit


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class IPRateLimitBoundsTests(unittest.TestCase):
    def test_first_add_returns_one(self):
        limiter = IPRateLimit(count=3, minutes=1)

        self.assertEqual(limiter.add_ip("203.0.113.1"), 1)
        self.assertEqual(limiter.add_ip("203.0.113.1"), 2)

    def test_capacity_evicts_least_recently_active_ip(self):
        limiter = IPRateLimit(count=10, minutes=1, max_ips=3)

        for ip in ("a", "b", "c", "d"):
            limiter.add_ip(ip)

        self.assertEqual(len(limiter.ips), 3)
        self.assertEqual(list(limiter.ips), ["b", "c", "d"])

    def test_activity_refreshes_recency(self):
        limiter = IPRateLimit(count=10, minutes=1, max_ips=2)

        limiter.add_ip("a")
        limiter.add_ip("b")
        limiter.add_ip("a")
        limiter.add_ip("c")

        self.assertEqual(list(limiter.ips), ["a", "c"])

    def test_window_blocks_then_resets(self):
        clock = FakeClock()
        with mock.patch("time.monotonic", clock):
            limiter = IPRateLimit(count=3, minutes=1)
            for _ in range(3):
                limiter.add_ip("198.51.100.9")

            self.assertFalse(limiter.check_ip("198.51.100.9"))
            clock.now += 30
            self.assertFalse(limiter.check_ip("198.51.100.9"))
            clock.now += 31
            self.assertTrue(limiter.check_ip("198.51.100.9"))
            self.assertNotIn("198.51.100.9", limiter.ips)

    def test_remove_expired_compacts_old_entries_only(self):
        clock = FakeClock()
        with mock.patch("time.monotonic", clock):
            limiter = IPRateLimit(count=10, minutes=1)
            limiter.add_ip("old")
            clock.now += 30
            limiter.add_ip("fresh")
            clock.now += 31

            import asyncio

            asyncio.run(limiter.remove_expired_ip())

        self.assertEqual(list(limiter.ips), ["fresh"])

    def test_record_count_is_bounded_under_ip_scan(self):
        limiter = IPRateLimit(count=10, minutes=1, max_ips=10_000)

        for i in range(50_000):
            limiter.add_ip(f"10.0.{i // 256}.{i % 256}")

        self.assertEqual(len(limiter.ips), 10_000)


if __name__ == "__main__":
    unittest.main()
