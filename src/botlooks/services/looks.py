import asyncio
import logging
import time
from dataclasses import dataclass
from html import escape

from botlooks.domain.schemas import AppearanceResult, StyleResult
from botlooks.llm.base import ImageGenerationError, ImageGenerator, LLMUnavailableError
from botlooks.services.billing import BillingService

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
_NAME_LIMIT = 200
_CAPTION_TITLE = "<b>Как вы можете выглядеть</b>"

_TEMPLATE = """\
Using this photo of one person, create a single photorealistic collage image
with {n} panels arranged as {layout}, separated by thin white lines.
Every panel shows the SAME person: keep their face, identity, facial features, age,
skin tone and body proportions exactly as in the photo. Panels differ only as follows:
{panels}
Framing: {framing}.
Natural lighting, realistic skin texture, consistent framing across panels.
No text, numbers, labels or watermarks."""

# (layout, aspect ratio, panel positions, legend arrows, framing)
_APPEARANCE_GRID = (
    "1 row x 2 columns",
    "4:3",
    ("left", "right"),
    ("←", "→"),
    "head and shoulders",
)
_STYLE_GRID = (
    "2 rows x 2 columns",
    "1:1",
    ("top-left", "top-right", "bottom-left", "bottom-right"),
    ("↖", "↗", "↙", "↘"),
    "from the waist up or full body, so the outfit is visible",
)

_semaphore = asyncio.Semaphore(4)


@dataclass(frozen=True)
class LooksOutcome:
    image: bytes | None
    caption: str
    refunded: int


def _looks(result: AppearanceResult | StyleResult) -> list[tuple[str, str]]:
    if isinstance(result, AppearanceResult):
        return [(look.name, look.image_prompt) for look in result.looks]
    return [(style.name, style.image_prompt) for style in result.styles]


def _grid(
    result: AppearanceResult | StyleResult,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...], str]:
    return _APPEARANCE_GRID if isinstance(result, AppearanceResult) else _STYLE_GRID


def build_instruction(result: AppearanceResult | StyleResult) -> tuple[str, str]:
    layout, ratio, positions, _, framing = _grid(result)
    looks = _looks(result)
    panels = "\n".join(
        f"Panel {n} ({pos}): {prompt}"
        for n, (pos, (_, prompt)) in enumerate(zip(positions, looks, strict=True), 1)
    )
    text = _TEMPLATE.format(n=len(looks), layout=layout, panels=panels, framing=framing)
    return text, ratio


def _short(name: str) -> str:
    return name if len(name) <= _NAME_LIMIT else name[: _NAME_LIMIT - 1] + "…"


def build_caption(result: AppearanceResult | StyleResult) -> str:
    _, _, _, arrows, _ = _grid(result)
    legend = [
        f"{arrow} {n} — {escape(_short(name), quote=False)}"
        for n, (arrow, (name, _)) in enumerate(zip(arrows, _looks(result), strict=True), 1)
    ]
    return "\n".join([_CAPTION_TITLE, *legend])[:CAPTION_LIMIT]


class LooksService:
    def __init__(
        self, generator: ImageGenerator, billing: BillingService, *, timeout: float = 90
    ) -> None:
        self._generator = generator
        self._billing = billing
        self._timeout = timeout

    async def render(
        self, user_id: int, photo: bytes, result: AppearanceResult | StyleResult
    ) -> LooksOutcome:
        instruction, ratio = build_instruction(result)
        caption = build_caption(result)
        started = time.monotonic()
        try:
            async with _semaphore:
                image = await asyncio.wait_for(
                    self._generator.edit(photo, instruction, ratio), self._timeout
                )
        except (ImageGenerationError, LLMUnavailableError, TimeoutError) as exc:
            logger.warning(
                "looks failed",
                extra={
                    "model": self._generator.model,
                    "error": type(exc).__name__,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            await self._billing.release(user_id)
            return LooksOutcome(None, caption, 1)
        logger.info(
            "looks rendered",
            extra={
                "model": self._generator.model,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return LooksOutcome(image, caption, 0)
