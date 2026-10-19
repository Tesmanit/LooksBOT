from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from google.genai import errors

from botlooks.llm.base import ImageGenerationError, LLMUnavailableError
from botlooks.llm.gemini import GeminiImageGenerator


def api_error(code: int) -> errors.APIError:
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": "err", "status": "X"}})


def image_response(data: bytes = b"PNG") -> Any:
    parts = [
        SimpleNamespace(text="here you go", inline_data=None),
        SimpleNamespace(text=None, inline_data=SimpleNamespace(data=data, mime_type="image/png")),
    ]
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))])


def text_response() -> Any:
    parts = [SimpleNamespace(text="I can't help with that", inline_data=None)]
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))])


def fake_client(*side_effect: Any) -> Any:
    generate = AsyncMock(side_effect=list(side_effect))
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))


def calls(client: Any) -> AsyncMock:
    return client.aio.models.generate_content  # type: ignore[no-any-return]


async def test_returns_inline_image_bytes() -> None:
    gen = GeminiImageGenerator(fake_client(image_response(b"IMG")), "m", sleep=AsyncMock())
    assert await gen.edit(b"\xff\xd8", "do it", "4:3") == b"IMG"


async def test_sends_photo_instruction_and_aspect_ratio() -> None:
    client = fake_client(image_response())
    await GeminiImageGenerator(client, "m", sleep=AsyncMock()).edit(b"\xff\xd8", "do it", "4:3")
    kw = calls(client).await_args.kwargs
    assert kw["model"] == "m"
    photo, text = kw["contents"]
    assert photo.inline_data.data == b"\xff\xd8"
    assert photo.inline_data.mime_type == "image/jpeg"
    assert text == "do it"
    assert kw["config"].response_modalities == ["IMAGE"]
    assert kw["config"].image_config.aspect_ratio == "4:3"


async def test_text_only_response_raises() -> None:
    gen = GeminiImageGenerator(fake_client(text_response()), "m", sleep=AsyncMock())
    with pytest.raises(ImageGenerationError):
        await gen.edit(b"x", "i", "1:1")


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(candidates=None),
        SimpleNamespace(candidates=[]),
        SimpleNamespace(candidates=[SimpleNamespace(content=None)]),
        SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=None))]),
    ],
)
async def test_no_candidates_raises(response: Any) -> None:
    gen = GeminiImageGenerator(fake_client(response), "m", sleep=AsyncMock())
    with pytest.raises(ImageGenerationError):
        await gen.edit(b"x", "i", "1:1")


@pytest.mark.parametrize("code", [429, 500, 503])
async def test_retries_then_succeeds(code: int) -> None:
    sleep = AsyncMock()
    client = fake_client(api_error(code), api_error(code), image_response(b"OK"))
    assert await GeminiImageGenerator(client, "m", sleep=sleep).edit(b"x", "i", "1:1") == b"OK"
    assert [c.args[0] for c in sleep.await_args_list] == [1, 2]


async def test_retries_on_timeout() -> None:
    client = fake_client(TimeoutError(), image_response(b"OK"))
    assert await GeminiImageGenerator(client, "m", sleep=AsyncMock()).edit(b"x", "i", "1:1")


async def test_gives_up_after_three_attempts() -> None:
    client = fake_client(api_error(503), api_error(503), api_error(503))
    with pytest.raises(LLMUnavailableError):
        await GeminiImageGenerator(client, "m", sleep=AsyncMock()).edit(b"x", "i", "1:1")
    assert calls(client).await_count == 3


async def test_client_error_not_retried() -> None:
    client = fake_client(api_error(400))
    with pytest.raises(ImageGenerationError):
        await GeminiImageGenerator(client, "m", sleep=AsyncMock()).edit(b"x", "i", "1:1")
    assert calls(client).await_count == 1
