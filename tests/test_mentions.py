import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from bot.services.ai_chat import AIChatService


class FakeProvider:
    async def complete(self, messages, max_tokens=1000):
        return "@everyone <@&1>"


class FakeStore:
    def prune_chat(self, guild_id, retention_days):
        return None

    def recent_chat(self, guild_id, channel_id, limit):
        return []

    def add_chat_message(self, guild_id, channel_id, user_id, role, content):
        return None


class MentionSafetyTests(unittest.IsolatedAsyncioTestCase):
    def test_bot_disables_mentions_by_default(self):
        from bot.main import bot

        self.assertFalse(bot.allowed_mentions.everyone)
        self.assertFalse(bot.allowed_mentions.users)
        self.assertFalse(bot.allowed_mentions.roles)

    async def test_ai_reply_explicitly_disallows_everyone_and_role_mentions(self):
        service = AIChatService(provider=FakeProvider(), store=FakeStore())
        message = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            author=SimpleNamespace(id=20, bot=False, display_name="member"),
            channel=SimpleNamespace(id=30),
            content="hello",
            mentions=[],
            reply=AsyncMock(),
        )

        handled = await service.handle_message(
            SimpleNamespace(user=SimpleNamespace(id=99)),
            message,
            {"enabled": True, "allowed_channels": ["30"], "response_mode": "every_message"},
        )

        self.assertTrue(handled)
        kwargs = message.reply.await_args.kwargs
        allowed_mentions = kwargs.get("allowed_mentions")
        self.assertIsInstance(allowed_mentions, discord.AllowedMentions)
        self.assertFalse(allowed_mentions.everyone)
        self.assertFalse(allowed_mentions.users)
        self.assertFalse(allowed_mentions.roles)
