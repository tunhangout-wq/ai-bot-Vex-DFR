"""Shared server-side client for Atria Dawn Preview."""

import asyncio
import datetime
import json
import logging
import os
import time

import aiohttp

# Atria's official OpenAI-compatible Chat Completions endpoint.
# Keep the model ID exactly as documented by Atria (case-sensitive).
BASE_URL = os.getenv(
    "ATRIA_API_BASE_URL",
    "https://api.atria-asi.ai/v1",
).rstrip("/") + "/chat/completions"
MODEL = os.getenv("ATRIA_MODEL", "Atria-Dawn-Preview")
MAX_RESPONSE_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)


class AIProvider:
    def __init__(self):
        self._session = None
        self._semaphore = asyncio.Semaphore(3)
        self._rate_lock = asyncio.Lock()
        self._last_call = 0.0
        self._minimum_interval = 0.35
        self._status = {
            "provider": "Atria",
            "model": MODEL,
            "endpoint": BASE_URL,
            "configured": False,
            "status": "Not Configured",
            "latency_ms": None,
            "last_request": None,
            "error": None,
        }

    @property
    def api_key(self):
        # ATRIA_API_KEY is canonical for direct Atria access.
        # AI_API_KEY remains supported for compatibility with older Vixen installs.
        return os.getenv("ATRIA_API_KEY") or os.getenv("AI_API_KEY")

    @staticmethod
    def _response_error(status, payload):
        """Build a short, safe diagnostic without ever exposing credentials."""
        detail = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message") or error.get("detail") or error.get("code")
            elif isinstance(error, str):
                detail = error
            if not detail:
                detail = payload.get("message") or payload.get("detail")
        elif isinstance(payload, str):
            detail = payload
        if not isinstance(detail, str) or not detail.strip():
            detail = "request rejected"
        # Keep dashboard/log output compact and strip common credential-like fields.
        detail = " ".join(detail.split())[:180]
        return f"HTTP {status}: {detail}"

    def status(self):
        configured = bool(self.api_key)
        result = dict(self._status)
        result["configured"] = configured
        if not configured:
            result["status"] = "Not Configured"
            result["error"] = "ATRIA_API_KEY is not configured"
        elif result["status"] == "Not Configured":
            result["status"] = "Not Tested"
            result["error"] = None
        return result

    async def open(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=25, connect=5, sock_read=20),
                raise_for_status=False,
            )

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def complete(self, messages, max_tokens=1200):
        key = self.api_key
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._status["last_request"] = now
        self._status["latency_ms"] = None

        if not key:
            self._status.update(status="Not Configured", error="ATRIA_API_KEY is not configured")
            raise RuntimeError("AI service is not configured")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 50:
            raise ValueError("Invalid AI request")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not 1 <= max_tokens <= 65536:
            raise ValueError("Invalid AI request")

        await self.open()
        started = time.monotonic()
        async with self._semaphore:
            async with self._rate_lock:
                wait = max(0.0, self._minimum_interval - (time.monotonic() - self._last_call))
                if wait:
                    await asyncio.sleep(wait)
                self._last_call = time.monotonic()

            # Atria documents 429 for rate/credit pressure and 5xx for transient failures.
            retryable_statuses = {429, 500, 502, 503, 504}
            max_attempts = 3
            last_transient_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    async with self._session.post(
                        BASE_URL,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": MODEL,
                            "messages": messages,
                            "max_tokens": max_tokens,
                        },
                    ) as response:
                        raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise RuntimeError("AI provider response is too large")

                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            data = raw.decode("utf-8", errors="replace")

                        self._status["latency_ms"] = round((time.monotonic() - started) * 1000)

                        if response.status >= 400:
                            error_text = self._response_error(response.status, data)
                            if response.status in retryable_statuses and attempt < max_attempts:
                                last_transient_error = error_text
                                logger.warning(
                                    "Atria request failed with %s (attempt %s/%s), retrying",
                                    error_text,
                                    attempt,
                                    max_attempts,
                                )
                                await asyncio.sleep(0.75 * attempt)
                                continue
                            self._status.update(status="Error", error=error_text)
                            logger.warning("Atria request failed: %s", error_text)
                            raise RuntimeError("AI provider request failed")

                        if response.content_type != "application/json":
                            raise RuntimeError("AI provider returned an invalid response")

                        choices = data.get("choices") if isinstance(data, dict) else None
                        first = choices[0] if isinstance(choices, list) and choices else {}
                        message = first.get("message", {}) if isinstance(first, dict) else {}
                        content = message.get("content") if isinstance(message, dict) else None
                        # Be tolerant of providers returning structured content blocks.
                        if isinstance(content, list):
                            parts = []
                            for item in content:
                                if isinstance(item, dict) and isinstance(item.get("text"), str):
                                    parts.append(item["text"])
                            content = "".join(parts)
                        if not isinstance(content, str) or not content.strip():
                            self._status.update(status="Error", error="Atria returned no text content")
                            raise RuntimeError("AI provider returned an invalid response")

                        self._status.update(status="Connected", error=None)
                        return content.strip()

                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    if attempt < max_attempts:
                        last_transient_error = type(exc).__name__
                        logger.warning(
                            "Atria request failed: %s (attempt %s/%s), retrying",
                            type(exc).__name__,
                            attempt,
                            max_attempts,
                        )
                        await asyncio.sleep(0.75 * attempt)
                        continue
                    self._status["latency_ms"] = round((time.monotonic() - started) * 1000)
                    self._status.update(status="Error", error=type(exc).__name__)
                    logger.warning("Atria request failed: %s", type(exc).__name__)
                    raise RuntimeError("AI service is temporarily unavailable") from None
                except RuntimeError as exc:
                    self._status["latency_ms"] = round((time.monotonic() - started) * 1000)
                    if self._status["status"] != "Error":
                        self._status.update(status="Error", error=str(exc)[:180])
                    raise

            self._status["latency_ms"] = round((time.monotonic() - started) * 1000)
            self._status.update(status="Error", error=last_transient_error or "Atria request failed")
            raise RuntimeError("AI service is temporarily unavailable")

    async def test_connection(self):
        if not self.api_key:
            self._status["last_request"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._status.update(
                configured=False,
                status="Not Configured",
                latency_ms=None,
                error="ATRIA_API_KEY is not configured",
            )
            return self.status()
        try:
            await self.complete(
                [
                    {"role": "system", "content": "Reply with the single word OK."},
                    {"role": "user", "content": "Connection test"},
                ],
                max_tokens=8,
            )
        except (RuntimeError, ValueError):
            pass
        return self.status()


ai_provider = AIProvider()
