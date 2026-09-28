"""In-process fanout of real Python log records to authorized Dashboard clients."""

import asyncio
import collections
import copy
import datetime
import logging
import os
import re
import threading


class SecretRedactionFilter(logging.Filter):
    ENVIRONMENT_SECRETS = (
        "DISCORD_TOKEN",
        "ATRIA_API_KEY",
        "AI_API_KEY",
        "DASHBOARD_PASSWORD",
    )
    BEARER_PATTERN = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
    DISCORD_TOKEN_PATTERN = re.compile(
        r"\b(?:mfa\.)?[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b"
    )
    STAFF_CODE_PATTERN = re.compile(r"\bCB-[A-Z]+-[A-Z0-9]{6}\b")

    @classmethod
    def redact(cls, text: str) -> str:
        for name in cls.ENVIRONMENT_SECRETS:
            value = os.environ.get(name)
            if value:
                text = text.replace(value, f"[REDACTED:{name}]")
        text = cls.BEARER_PATTERN.sub("Bearer [REDACTED]", text)
        text = cls.DISCORD_TOKEN_PATTERN.sub("[REDACTED:DISCORD_TOKEN]", text)
        return cls.STAFF_CODE_PATTERN.sub("[REDACTED:STAFF_CODE]", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


class TerminalSubscriberLimitError(Exception):
    """Raised when the live terminal already has its maximum clients."""


class LiveTerminalHandler(logging.Handler):
    def __init__(self, history_limit=500):
        super().__init__(level=logging.INFO)
        self.history = collections.deque(maxlen=history_limit)
        self.queues = set()
        self.loop = None
        self._lock = threading.Lock()
        self.redaction_filter = SecretRedactionFilter()

    def emit(self, record):
        try:
            safe_record = copy.copy(record)
            self.redaction_filter.filter(safe_record)
            message = safe_record.getMessage()
            if safe_record.exc_text:
                message = f"{message}\n{safe_record.exc_text}"
            event = {
                "timestamp": datetime.datetime.fromtimestamp(
                    safe_record.created, datetime.timezone.utc
                ).isoformat(),
                "level": safe_record.levelname,
                "logger": safe_record.name,
                "message": message[:4000],
            }
            with self._lock:
                self.history.append(event)
                loop = self.loop
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(self._publish, event)
        except Exception:
            self.handleError(record)

    def subscribe(self):
        if len(self.queues) >= 5:
            raise TerminalSubscriberLimitError
        self.loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=200)
        self.queues.add(queue)
        with self._lock:
            history = list(self.history)[-100:]
        for event in history:
            queue.put_nowait(event)
        return queue

    def unsubscribe(self, queue):
        self.queues.discard(queue)

    def _publish(self, event):
        for queue in tuple(self.queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


live_terminal = LiveTerminalHandler()


def install_live_terminal():
    root = logging.getLogger()
    if live_terminal not in root.handlers:
        root.addHandler(live_terminal)