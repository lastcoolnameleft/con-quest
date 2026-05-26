"""Production smoke tests — run against live production environment.

⚠️ These tests must be READ-ONLY. Never create, modify, or delete production data.
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("PROD_BASE_URL")

pytestmark = pytest.mark.skipif(not BASE_URL, reason="PROD_BASE_URL not set")


class TestHealthEndpoint:
    """Verify the health endpoint is responding correctly."""

    def test_health_returns_200(self):
        resp = requests.get(f"{BASE_URL}/api/health/", timeout=10)
        assert resp.status_code == 200

    def test_health_returns_json_with_sha(self):
        resp = requests.get(f"{BASE_URL}/api/health/", timeout=10)
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "sha" in data
        assert len(data["sha"]) >= 7


class TestBasicConnectivity:
    """Verify core pages are reachable."""

    def test_homepage_returns_200(self):
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        assert resp.status_code == 200

    def test_login_page_reachable(self):
        resp = requests.get(f"{BASE_URL}/auth/login/", timeout=10)
        assert resp.status_code == 200
