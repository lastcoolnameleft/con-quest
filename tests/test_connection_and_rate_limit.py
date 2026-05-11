from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache

from apps.seasons.models import Season


class ConnectionAndRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.season = Season.objects.create(title="Conn Season", slug="conn-season", join_code="CONN1234")

    def test_connection_test_returns_clock_offset(self):
        response = self.client.get(
            reverse("season-connection-test", kwargs={"slug": self.season.slug}),
            {"client_time_ms": "1000"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("clock_offset_ms", payload)
        self.assertIn("X-RateLimit-Limit", response)

    def test_season_state_is_rate_limited(self):
        url = reverse("season-state", kwargs={"slug": self.season.slug})
        last_response = None
        for _ in range(121):
            last_response = self.client.get(url)

        self.assertIsNotNone(last_response)
        self.assertEqual(last_response.status_code, 429)
        self.assertIn("Retry-After", last_response)
        payload = last_response.json()
        self.assertEqual(payload.get("error"), "rate_limited")
        self.assertIn("retry_after_seconds", payload)

    def test_connection_test_is_rate_limited_with_standard_payload(self):
        url = reverse("season-connection-test", kwargs={"slug": self.season.slug})
        last_response = None
        for _ in range(21):
            last_response = self.client.get(url)

        self.assertIsNotNone(last_response)
        self.assertEqual(last_response.status_code, 429)
        self.assertIn("Retry-After", last_response)
        payload = last_response.json()
        self.assertEqual(payload.get("error"), "rate_limited")
        self.assertIn("retry_after_seconds", payload)
        self.assertEqual(payload.get("status"), "Not Ready")
