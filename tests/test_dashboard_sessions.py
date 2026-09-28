import unittest
import os
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from bot.utils import ranks
from bot.web import server


class DashboardSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sessions = server.DashboardSessions()
        self.client = TestClient(TestServer(server.create_web_app(None)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    def test_idle_expiry_slides_but_absolute_expiry_does_not(self):
        now = [1_000_000.0]
        with patch.object(server.time, "time", side_effect=lambda: now[0]):
            token = self.sessions.create(7, "owner")
            session = self.sessions.sessions[token]
            self.assertEqual(session["expires"], now[0] + 12 * 60 * 60)
            absolute_expiry = session["absolute_expires"]

            now[0] += 11 * 60 * 60
            self.assertIsNotNone(self.sessions.get(token))
            self.assertEqual(session["expires"], now[0] + 12 * 60 * 60)
            self.assertEqual(session["absolute_expires"], absolute_expiry)

            now[0] = absolute_expiry
            self.assertIsNone(self.sessions.get(token))

    async def test_logout_invalidates_token(self):
        token = self.sessions.create(7, "owner")
        original_sessions = server.SESSIONS
        server.SESSIONS = self.sessions
        try:
            response = await self.client.post(
                "/api/logout", headers={"Authorization": f"Bearer {token}"}
            )
            self.assertEqual(response.status, 200)
            self.assertIsNone(self.sessions.get(token))
            protected = await self.client.get(
                "/api/me", headers={"Authorization": f"Bearer {token}"}
            )
            self.assertEqual(protected.status, 401)
        finally:
            server.SESSIONS = original_sessions

    async def test_owner_login_accepts_unicode_password(self):
        with patch.dict(os.environ, {"OWNER_ID": "12345", "DASHBOARD_PASSWORD": "كلمة مرور"}):
            response = await self.client.post(
                "/api/login",
                json={"method": "owner", "owner_id": "12345", "password": "كلمة مرور"},
            )
            self.assertEqual(response.status, 200)
            self.assertTrue((await response.json())["ok"])

    async def test_revoking_code_invalidates_its_virtual_sessions(self):
        sessions = server.DashboardSessions()
        original_sessions = server.SESSIONS
        server.SESSIONS = sessions
        try:
            code = ranks.generate_code("team", 12345)
            owner_token = sessions.create(12345, "owner")
            virtual_token = sessions.create(0, "team", virtual=True, code=code)
            with patch.dict(os.environ, {"OWNER_ID": "12345"}):
                response = await self.client.post(
                    "/api/staff/revoke",
                    headers={"Authorization": f"Bearer {owner_token}"},
                    json={"code": code},
                )
            self.assertEqual(response.status, 200)
            self.assertIsNone(sessions.get(virtual_token))
            unauthorized = await self.client.get(
                "/api/me",
                headers={"Authorization": f"Bearer {virtual_token}"},
            )
            self.assertEqual(unauthorized.status, 401)
        finally:
            server.SESSIONS = original_sessions

    async def test_removing_staff_invalidates_member_sessions(self):
        sessions = server.DashboardSessions()
        original_sessions = server.SESSIONS
        server.SESSIONS = sessions
        try:
            self.assertTrue(ranks.set_rank(23456, "team", by_id=12345))
            owner_token = sessions.create(12345, "owner")
            member_token = sessions.create(23456, "team")
            with patch.dict(os.environ, {"OWNER_ID": "12345"}):
                response = await self.client.post(
                    "/api/staff/remove",
                    headers={"Authorization": f"Bearer {owner_token}"},
                    json={"user_id": "23456"},
                )
            self.assertEqual(response.status, 200)
            self.assertIsNone(sessions.get(member_token))
        finally:
            server.SESSIONS = original_sessions
