import json
import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

from botlooks.bot import texts
from botlooks.bot.handlers.errors import on_error
from botlooks.log import JsonFormatter


def test_json_formatter():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("w",), None)
    d = json.loads(JsonFormatter().format(rec))
    assert d["msg"] == "hello w" and d["level"] == "INFO" and d["logger"] == "x"
    assert "ts" in d and "exc" not in d


def test_json_formatter_includes_exc():
    try:
        raise ValueError("boom")
    except ValueError:
        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "bad", (), sys.exc_info())
    d = json.loads(JsonFormatter().format(rec))
    assert "ValueError: boom" in d["exc"]


def _event(message=None, callback_query=None):
    update = SimpleNamespace(message=message, callback_query=callback_query)
    return SimpleNamespace(update=update, exception=RuntimeError("x"))


async def test_error_handler_replies_to_message_and_clears_state():
    message = SimpleNamespace(answer=AsyncMock())
    state = AsyncMock()
    await on_error(_event(message=message), state)
    message.answer.assert_awaited_once_with(texts.GENERIC_ERROR)
    state.clear.assert_awaited_once()


async def test_error_handler_alerts_on_callback():
    cb = SimpleNamespace(answer=AsyncMock())
    await on_error(_event(callback_query=cb), None)
    cb.answer.assert_awaited_once_with(texts.GENERIC_ERROR, show_alert=True)


async def test_error_handler_never_raises():
    message = SimpleNamespace(answer=AsyncMock(side_effect=RuntimeError("tg down")))
    state = AsyncMock()
    state.clear.side_effect = RuntimeError("storage down")
    await on_error(_event(message=message), state)
    message.answer.assert_awaited_once()
