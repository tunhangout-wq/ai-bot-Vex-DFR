import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.services.live_terminal import live_terminal
from bot.web import server


class SecurityHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = server.create_web_app(None)

        async def fail(request):
            raise web.HTTPInternalServerError(reason="test failure")

        app.router.add_get("/test-error", fail)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        for queue in tuple(live_terminal.queues):
            live_terminal.unsubscribe(queue)

    def assert_security_headers(self, response, api=False):
        self.assertEqual(
            response.headers.get("Content-Security-Policy"),
            "default-src 'self'; img-src 'self' https://cdn.discordapp.com "
            "https://media.discordapp.net data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
        if api:
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    async def test_headers_cover_page_asset_errors_and_sse(self):
        page = await self.client.get("/")
        self.assert_security_headers(page)
        await page.release()

        asset = await self.client.get("/assets/app.js")
        self.assert_security_headers(asset)
        await asset.release()

        unauthorized = await self.client.get("/api/me")
        self.assertEqual(unauthorized.status, 401)
        self.assert_security_headers(unauthorized, api=True)

        missing = await self.client.get("/missing")
        self.assertEqual(missing.status, 404)
        self.assert_security_headers(missing)

        failed = await self.client.get("/test-error")
        self.assertEqual(failed.status, 500)
        self.assert_security_headers(failed)

        with patch.object(server, "require_permission", return_value={"user_id": "7"}):
            stream = await self.client.get(
                "/api/terminal/stream",
                headers={"Authorization": "Bearer test"},
            )
            self.assertEqual(stream.status, 200)
            self.assert_security_headers(stream, api=True)
            stream.close()
