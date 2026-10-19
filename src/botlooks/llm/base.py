from __future__ import annotations

from typing import Protocol


class LLMUnavailableError(Exception):
    """The vision model could not produce a usable answer."""


class VisionLLM(Protocol):
    model: str

    async def analyze(self, image: bytes, system_prompt: str, user_prompt: str) -> str: ...


class ImageGenerationError(Exception):
    """The image could not be produced (refusal, no image in response, API error)."""


class ImageGenerator(Protocol):
    model: str

    async def edit(self, photo: bytes, instruction: str, aspect_ratio: str) -> bytes: ...
