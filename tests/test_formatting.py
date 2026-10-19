from datetime import datetime
from typing import Any

from botlooks.bot.formatting import (
    format_history_item,
    format_result,
    format_weight_plan,
    split_message,
)
from botlooks.bot.texts import DISCLAIMER
from botlooks.domain.schemas import AppearanceResult, StyleResult
from botlooks.services.weight import WeightPlan


def look(i: int, **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": f"Образ-{i}",
        "haircut": "каре",
        "facial_hair": "щетина",
        "makeup": "тон",
        "why": "подчёркивает скулы",
        "image_prompt": "SECRET-PROMPT",
    }
    data.update(over)
    return data


def appearance_result(**over: Any) -> AppearanceResult:
    data: dict[str, Any] = {
        "status": "ok",
        "face_shape": "овал",
        "looks": [look(1), look(2)],
        "avoid": ["чёлка"],
        "brows_lashes": {"recommendations": ["гребень"]},
        "skincare": {"observations": ["сухость"], "recommendations": ["крем"]},
        "summary": "итог",
    }
    data.update(over)
    return AppearanceResult.model_validate(data)


def style_result() -> StyleResult:
    colors = [{"name": f"c{i}", "hex": "#C8553D"} for i in range(6)]
    return StyleResult.model_validate(
        {
            "status": "ok",
            "color_type": "autumn",
            "color_type_explanation": "тёплый",
            "palette": colors,
            "avoid_colors": [{"name": "x", "hex": "#000000"}] * 3,
            "styles": [
                {
                    "name": f"casual{i}",
                    "description": "d",
                    "items": ["джинсы"],
                    "image_prompt": "SECRET-PROMPT",
                }
                for i in range(4)
            ],
            "height_tips": ["tip"],
            "summary": "итог",
        }
    )


def test_html_escaped() -> None:
    out = format_result(appearance_result(summary="<b>x</b> & <5 мин"))
    assert "&lt;b&gt;x&lt;/b&gt; &amp; &lt;5 мин" in out


def test_appearance_numbered_looks() -> None:
    out = format_result(appearance_result())
    assert "Образ 1: Образ-1" in out and "Образ 2: Образ-2" in out
    assert "Лучше избегать" in out and "чёлка" in out
    assert "подчёркивает скулы" in out


def test_appearance_look_skips_none_fields() -> None:
    no_beard = appearance_result(looks=[look(1, facial_hair=None), look(2, facial_hair=None)])
    assert "Борода" not in format_result(no_beard)
    no_makeup = appearance_result(looks=[look(1, makeup=None), look(2, makeup=None)])
    assert "Макияж" not in format_result(no_makeup)


def test_style_four_numbered_directions() -> None:
    out = format_result(style_result())
    assert all(f"{i}. casual{i - 1}" in out for i in range(1, 5))


def test_image_prompt_not_shown() -> None:
    assert "SECRET-PROMPT" not in format_result(appearance_result())
    assert "SECRET-PROMPT" not in format_result(style_result())


def test_style_lists_hex() -> None:
    assert "#C8553D" in format_result(style_result())


def test_weight_plan_extended() -> None:
    out = format_weight_plan(WeightPlan(81.0, 0.75, 2250, 6, 3, True))
    assert "За 3 мес. безопасно не получится, реалистичный срок — 6 мес." in out
    assert DISCLAIMER in out
    assert "0.75 кг/нед" in out


def test_weight_plan_not_extended() -> None:
    out = format_weight_plan(WeightPlan(81.0, 0.5, 2250, 6, 6, False))
    assert "безопасно не получится" not in out
    assert DISCLAIMER in out


def test_history_item() -> None:
    out = format_history_item("style", {"summary": "<i>x</i>"}, datetime(2026, 10, 18))
    assert "18.10.2026" in out
    assert "Стиль" in out
    assert "&lt;i&gt;x&lt;/i&gt;" in out


def test_split_message_short_text_single_chunk() -> None:
    assert split_message("abc") == ["abc"]


def test_split_message_on_section_boundaries() -> None:
    sections = [f"<b>S{i}</b>\n" + "x" * 40 for i in range(10)]
    text = "\n\n".join(sections)
    chunks = split_message(text, limit=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    assert "\n\n".join(chunks) == text
    for c in chunks:
        assert c.count("<b>") == c.count("</b>")


def test_split_message_oversized_section_on_lines_then_chars() -> None:
    section = "<b>T</b>\n" + "\n".join("y" * 30 for _ in range(10))
    chunks = split_message(section, limit=70)
    assert all(len(c) <= 70 for c in chunks)
    assert "\n".join(chunks) == section
    assert split_message("z" * 250, limit=100) == ["z" * 100, "z" * 100, "z" * 50]


def test_split_message_default_limit_is_telegram_max() -> None:
    text = "\n\n".join("w" * 1000 for _ in range(10))
    chunks = split_message(text)
    assert all(len(c) <= 4096 for c in chunks)
    assert len(chunks) == 3
