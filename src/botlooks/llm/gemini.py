from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from botlooks.llm.base import ImageGenerationError, LLMUnavailableError

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_PAUSES = (1, 2)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, errors.APIError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, TimeoutError | httpx.TransportError)


def _extract_image(response: Any) -> bytes:
    for candidate in response.candidates or []:
        content = candidate.content
        for part in (content.parts if content is not None else None) or []:
            if part.inline_data is not None and part.inline_data.data:
                return bytes(part.inline_data.data)
    raise ImageGenerationError("no image in response")


class GeminiImageGenerator:
    def __init__(
        self,
        client: genai.Client,
        model: str,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self.model = model
        self._sleep = sleep

    async def edit(self, photo: bytes, instruction: str, aspect_ratio: str) -> bytes:
        contents: list[Any] = [
            types.Part.from_bytes(data=photo, mime_type="image/jpeg"),
            instruction,
        ]
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        )
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except (errors.APIError, TimeoutError, httpx.TransportError) as exc:
                if not _retryable(exc):
                    raise ImageGenerationError(type(exc).__name__) from exc
                logger.warning(
                    "image retryable error",
                    extra={"attempt": attempt + 1, "error": type(exc).__name__},
                )
                if attempt + 1 >= _MAX_ATTEMPTS:
                    raise LLMUnavailableError(type(exc).__name__) from exc
                await self._sleep(_PAUSES[attempt])
            else:
                return _extract_image(response)
        raise LLMUnavailableError("unreachable")  # pragma: no cover
