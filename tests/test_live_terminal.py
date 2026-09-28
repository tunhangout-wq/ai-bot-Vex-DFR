import asyncio
import json
import logging
import os
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from bot.services.live_terminal import (
    SecretRedactionFilter,
    install_live_terminal,
    live_terminal,
)
from bot.web import server


class LiveTerminalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        install_live_terminal()
        self.client = TestClient(TestServer(server.create_web_app(None)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        for queue in tuple(live_terminal.queues):
            live_terminal.unsubscribe(queue)

    async def test_stream_requires_auth_and_delivers_real_log_records(self):
        denied = await self.client.get("/api/terminal/stream")
        self.assertEqual(denied.status, 401)

        with patch.object(server, "require_permission", return_value={"user_id": "7"}):
            response = await self.client.get(
                "/api/terminal/stream",
                headers={"Authorization": "Bearer test"},
            )
            logging.getLogger("vixen.terminal.test").warning("terminal-regression-event")
            found = False
            for _ in range(200):
                line = await asyncio.wait_for(response.content.readline(), timeout=2)
                if not line.startswith(b"data: "):
                    continue
                event = json.loads(line[6:])
                if event["message"] == "terminal-regression-event":
                    found = True
                    break
            response.close()

        self.assertTrue(found)

    async def test_environment_secrets_are_redacted_from_history_and_sse(self):
        live_terminal.history.clear()
        secret = "dynamic-terminal-secret-82731"
        logger = logging.getLogger("vixen.terminal.redaction")
        with patch.dict(os.environ, {"DISCORD_TOKEN": secret}):
            with patch.object(server, "require_permission", return_value={"user_id": "7"}):
                response = await self.client.get(
                    "/api/terminal/stream",
                    headers={"Authorization": "Bearer test"},
                )
                logger.error("key=%s", secret)
                try:
                    raise RuntimeError(f"trace={secret}")
                except RuntimeError:
                    logger.exception("exception event")

                events = []
                while len(events) < 2:
                    line = await asyncio.wait_for(response.content.readline(), timeout=2)
                    if line.startswith(b"data: "):
                        events.append(json.loads(line[6:]))
                response.close()

        self.assertTrue(all(secret not in str(event) for event in live_terminal.history))
        self.assertTrue(all(secret not in str(event) for event in events))
        self.assertIn("[REDACTED:DISCORD_TOKEN]", events[0]["message"])
        self.assertIn("[REDACTED:DISCORD_TOKEN]", events[1]["message"])

    async def test_stream_requires_manage_settings_and_caps_subscribers(self):
        queues = [live_terminal.subscribe() for _ in range(5)]
        try:
            with patch.object(server, "require_permission", return_value={"user_id": "7"}) as require:
                response = await self.client.get(
                    "/api/terminal/stream",
                    headers={"Authorization": "Bearer test"},
                )
                self.assertEqual(response.status, 429)
                require.assert_called_once()
                self.assertEqual(require.call_args.args[1], "manage_settings")
        finally:
            for queue in queues:
                live_terminal.unsubscribe(queue)

    def test_bearer_discord_token_and_staff_code_patterns_are_redacted(self):
        discord_token = ".".join(("A" * 24, "B" * 8, "C" * 27))
        staff_code = "CB-" + "TEAM-" + "A1B2C3"
        message = f"Bearer access-value {discord_token} {staff_code}"

        redacted = SecretRedactionFilter.redact(message)

        self.assertNotIn("access-value", redacted)
        self.assertNotIn(discord_token, redacted)
        self.assertNotIn(staff_code, redacted)
        self.assertIn("[REDACTED:DISCORD_TOKEN]", redacted)
        self.assertIn("[REDACTED:STAFF_CODE]", redacted)


if __name__ == "__main__":
    unittest.main()