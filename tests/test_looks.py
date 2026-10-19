import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from botlooks.domain.schemas import AppearanceResult, StyleResult
from botlooks.llm.base import ImageGenerationError, LLMUnavailableError
from botlooks.services.billing import BillingService
from botlooks.services.looks import (
    CAPTION_LIMIT,
    LooksService,
    build_caption,
    build_instruction,
)


def appearance_result(names: tuple[str, str] = ("a1", "a2")) -> AppearanceResult:
    return AppearanceResult.model_validate(
        {
            "status": "ok",
            "face_shape": "овал",
            "looks": [
                {"name": n, "haircut": "h", "why": "w", "image_prompt": f"<prompt{i}>"}
                for i, n in enumerate(names, 1)
            ],
            "avoid": ["x"],
            "brows_lashes": {"recommendations": []},
            "skincare": {"observations": ["o"], "recommendations": ["r"]},
            "summary": "s",
        }
    )


def style_result(names: list[str] | None = None) -> StyleResult:
    names = names or [f"s{i}" for i in range(1, 5)]
    color = {"name": "c", "hex": "#AABBCC"}
    return StyleResult.model_validate(
        {
            "status": "ok",
            "color_type": "autumn",
            "color_type_explanation": "e",
            "palette": [color] * 6,
            "avoid_colors": [color] * 3,
            "styles": [
                {"name": n, "description": "d", "items": ["i"], "image_prompt": f"<outfit{i}>"}
                for i, n in enumerate(names, 1)
            ],
            "height_tips": ["t"],
            "summary": "s",
        }
    )


def test_appearance_instruction_layout() -> None:
    text, ratio = build_instruction(appearance_result())
    assert ratio == "4:3"
    assert "2 panels arranged as 1 row x 2 columns" in text
    assert "Panel 1 (left): <prompt1>" in text
    assert "Panel 2 (right): <prompt2>" in text
    assert text.index("Panel 1") < text.index("Panel 2")
    assert "head and shoulders" in text
    assert "No text, numbers, labels or watermarks" in text


def test_style_instruction_layout() -> None:
    text, ratio = build_instruction(style_result())
    assert ratio == "1:1"
    assert "4 panels arranged as 2 rows x 2 columns" in text
    for i, pos in enumerate(["top-left", "top-right", "bottom-left", "bottom-right"], 1):
        assert f"Panel {i} ({pos}): <outfit{i}>" in text
    assert "waist up or full body" in text


@pytest.mark.parametrize("result", [appearance_result(), style_result()])
def test_instruction_keeps_identity(result: Any) -> None:
    text, _ = build_instruction(result)
    assert "SAME person" in text
    assert "keep their face, identity, facial features, age" in text


def test_caption_legend_order() -> None:
    style = build_caption(style_result()).splitlines()
    assert style[0] == "<b>Как вы можете выглядеть</b>"
    assert style[1:] == ["↖ 1 — s1", "↗ 2 — s2", "↙ 3 — s3", "↘ 4 — s4"]
    assert build_caption(appearance_result()).splitlines()[1:] == ["← 1 — a1", "→ 2 — a2"]


def test_caption_escapes_html() -> None:
    assert "&lt;b&gt;&amp;" in build_caption(appearance_result(("<b>&", "ok")))


def test_caption_truncated_to_limit() -> None:
    caption = build_caption(style_result(["я" * 600] * 4))
    assert len(caption) <= CAPTION_LIMIT
    assert len(caption.splitlines()) == 5
    assert "…" in caption


class FakeGenerator:
    model = "fake-image"

    def __init__(self, result: bytes | BaseException, delay: float = 0) -> None:
        self._result = result
        self._delay = delay
        self.calls: list[tuple[bytes, str, str]] = []

    async def edit(self, photo: bytes, instruction: str, aspect_ratio: str) -> bytes:
        self.calls.append((photo, instruction, aspect_ratio))
        await asyncio.sleep(self._delay)
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


@pytest.fixture
def billing() -> Any:
    return AsyncMock(spec=BillingService)


async def test_render_success(billing: Any) -> None:
    gen = FakeGenerator(b"img")
    out = await LooksService(gen, billing).render(1, b"photo", style_result())
    assert out.image == b"img"
    assert out.refunded == 0
    assert out.caption == build_caption(style_result())
    assert gen.calls == [(b"photo", *build_instruction(style_result()))]
    billing.release.assert_not_awaited()


@pytest.mark.parametrize(
    "exc", [ImageGenerationError("x"), LLMUnavailableError("x"), TimeoutError()]
)
async def test_render_failure_refunds(billing: Any, exc: BaseException) -> None:
    out = await LooksService(FakeGenerator(exc), billing).render(1, b"p", appearance_result())
    assert out.image is None
    assert out.refunded == 1
    billing.release.assert_awaited_once_with(1)


async def test_render_timeout(billing: Any) -> None:
    svc = LooksService(FakeGenerator(b"img", delay=1), billing, timeout=0.01)
    out = await svc.render(7, b"p", appearance_result())
    assert out.image is None and out.refunded == 1
    billing.release.assert_awaited_once_with(7)


async def test_render_other_errors_propagate(billing: Any) -> None:
    with pytest.raises(ValueError):
        await LooksService(FakeGenerator(ValueError()), billing).render(1, b"p", style_result())
    billing.release.assert_not_awaited()
