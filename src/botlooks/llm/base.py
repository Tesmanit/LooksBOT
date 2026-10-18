from __future__ import annotations

from typing import Protocol


class LLMUnavailableError(Exception):
    """The vision model could not produce a usable answer."""


class VisionLLM(Protocol):
    model: str

    async def analyze(self, image: bytes, system_prompt: str, user_prompt: str) -> str: ...
