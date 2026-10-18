from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2 as httpx
import openai
import pytest

from botlooks.llm.base import LLMUnavailableError
from botlooks.llm.deepseek import DeepSeekVisionLLM


def _request() -> httpx.Request:
    return httpx.Request("POST", "http://x")


def timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=_request())


def connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=_request())


def rate_limit_error() -> openai.RateLimitError:
    response = httpx.Response(429, request=_request())
    return openai.RateLimitError(message="err", response=response, body=None)


def server_error() -> openai.InternalServerError:
    response = httpx.Response(500, request=_request())
    return openai.InternalServerError(message="err", response=response, body=None)


def bad_request_error() -> openai.BadRequestError:
    response = httpx.Response(400, request=_request())
    return openai.BadRequestError(message="err", response=response, body=None)


@pytest.fixture
def fake_client():
    def factory(returns: str | None = None, raises: list[Exception] | None = None):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=returns))]
        )
        create = AsyncMock(side_effect=[*(raises or []), response])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    return factory


async def test_sends_image_and_returns_text(fake_client):
    fake = fake_client(returns='{"a":1}')
    llm = DeepSeekVisionLLM(fake, "m", sleep=AsyncMock())
    assert await llm.analyze(b"\xff\xd8", "sys", "usr") == '{"a":1}'
    kw = fake.chat.completions.create.await_args.kwargs
    assert kw["model"] == "m"
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["messages"][1]["content"][0] == {"type": "text", "text": "usr"}
    assert kw["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert kw["response_format"] == {"type": "json_object"}


async def test_json_mode_off_omits_response_format(fake_client):
    fake = fake_client(returns="ok")
    llm = DeepSeekVisionLLM(fake, "m", json_mode=False, sleep=AsyncMock())
    await llm.analyze(b"x", "s", "u")
    assert "response_format" not in fake.chat.completions.create.await_args.kwargs


async def test_retries_then_succeeds(fake_client):
    sleep = AsyncMock()
    llm = DeepSeekVisionLLM(
        fake_client(raises=[timeout_error(), timeout_error()], returns="ok"), "m", sleep=sleep
    )
    assert await llm.analyze(b"x", "s", "u") == "ok"
    assert [c.args[0] for c in sleep.await_args_list] == [1, 2]


@pytest.mark.parametrize(
    "make_error", [timeout_error, connection_error, rate_limit_error, server_error]
)
async def test_retryable_errors_are_retried(fake_client, make_error):
    fake = fake_client(raises=[make_error()], returns="ok")
    llm = DeepSeekVisionLLM(fake, "m", sleep=AsyncMock())
    assert await llm.analyze(b"x", "s", "u") == "ok"
    assert fake.chat.completions.create.await_count == 2


async def test_gives_up_after_three(fake_client):
    sleep = AsyncMock()
    fake = fake_client(raises=[timeout_error(), timeout_error(), timeout_error()], returns="ok")
    llm = DeepSeekVisionLLM(fake, "m", sleep=sleep)
    with pytest.raises(LLMUnavailableError):
        await llm.analyze(b"x", "s", "u")
    assert fake.chat.completions.create.await_count == 3
    assert [c.args[0] for c in sleep.await_args_list] == [1, 2]


async def test_bad_request_no_retry(fake_client):
    sleep = AsyncMock()
    fake = fake_client(raises=[bad_request_error()], returns="ok")
    llm = DeepSeekVisionLLM(fake, "m", sleep=sleep)
    with pytest.raises(LLMUnavailableError):
        await llm.analyze(b"x", "s", "u")
    assert fake.chat.completions.create.await_count == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize("content", [None, ""])
async def test_empty_content_is_unavailable(fake_client, content):
    llm = DeepSeekVisionLLM(fake_client(returns=content), "m", sleep=AsyncMock())
    with pytest.raises(LLMUnavailableError):
        await llm.analyze(b"x", "s", "u")


async def test_empty_choices_is_unavailable():
    create = AsyncMock(return_value=SimpleNamespace(choices=[]))
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm = DeepSeekVisionLLM(fake, "m", sleep=AsyncMock())
    with pytest.raises(LLMUnavailableError):
        await llm.analyze(b"x", "s", "u")
