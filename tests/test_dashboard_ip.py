import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.web import server


class DashboardIPTests(unittest.TestCase):
    def test_forwarded_for_is_ignored_unless_proxy_trust_is_enabled(self):
        request = SimpleNamespace(
            remote="192.0.2.10",
            headers={"X-Forwarded-For": "198.51.100.8, 203.0.113.9"},
        )
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(server.client_ip(request), "192.0.2.10")

    def test_trusted_proxy_uses_validated_element_counted_from_right(self):
        request = SimpleNamespace(
            remote="192.0.2.10",
            headers={"X-Forwarded-For": "198.51.100.8, 203.0.113.9"},
        )
        with patch.dict(os.environ, {"TRUST_PROXY": "1", "TRUSTED_PROXY_COUNT": "1"}, clear=True):
            self.assertEqual(server.client_ip(request), "203.0.113.9")
        request.headers["X-Forwarded-For"] = "198.51.100.8, forged"
        with patch.dict(os.environ, {"TRUST_PROXY": "1", "TRUSTED_PROXY_COUNT": "1"}, clear=True):
            self.assertEqual(server.client_ip(request), "192.0.2.10")

    def test_attempt_limit_is_independent_of_client_ip(self):
        sessions = server.DashboardSessions()
        for address_number in range(20):
            sessions.record_attempt(f"198.51.100.{address_number + 1}")
            sessions.record_target_attempt("owner:123")
        self.assertTrue(sessions.too_many_target_attempts("owner:123"))
