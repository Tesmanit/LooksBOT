from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import openai
from openai import AsyncOpenAI

from botlooks.llm.base import LLMUnavailableError

logger = logging.getLogger(__name__)

_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)
_MAX_ATTEMPTS = 3
_PAUSES = (1, 2)


class DeepSeekVisionLLM:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        json_mode: bool = True,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self.model = model
        self._json_mode = json_mode
        self._sleep = sleep

    async def analyze(self, image: bytes, system_prompt: str, user_prompt: str) -> str:
        image_b64 = base64.b64encode(image).decode("ascii")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                },
            ],
        }
        if self._json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._client.chat.completions.create(**kwargs)
            except _RETRYABLE as exc:
                logger.warning(
                    "llm retryable error",
                    extra={"attempt": attempt + 1, "error": type(exc).__name__},
                )
                if attempt + 1 >= _MAX_ATTEMPTS:
                    raise LLMUnavailableError(type(exc).__name__) from exc
                await self._sleep(_PAUSES[attempt])
            except openai.APIError as exc:
                raise LLMUnavailableError(type(exc).__name__) from exc
            else:
                if not response.choices:
                    raise LLMUnavailableError("empty choices")
                content = response.choices[0].message.content
                if not content:
                    raise LLMUnavailableError("empty content")
                return str(content)
        raise LLMUnavailableError("unreachable")  # pragma: no cover
