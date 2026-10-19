from datetime import datetime
from html import escape
from typing import Any

from botlooks.bot import texts
from botlooks.domain.schemas import (
    AppearanceLook,
    AppearanceResult,
    Mode,
    NamedColor,
    StyleResult,
)
from botlooks.services.weight import WeightPlan

_MODE_LABEL = {"appearance": "Внешность", "style": "Стиль"}
_COLOR_TYPE = {
    "spring": "Весна",
    "summer": "Лето",
    "autumn": "Осень",
    "winter": "Зима",
}


def _e(value: str) -> str:
    return escape(value, quote=False)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {_e(i)}" for i in items)


def _section(title: str, body: str) -> str:
    return f"<b>{title}</b>\n{body}"


def _colors(colors: list[NamedColor]) -> str:
    return "\n".join(f"• {_e(c.name)} — {_e(c.hex.upper())}" for c in colors)


def _format_look(n: int, look: AppearanceLook) -> str:
    lines = [f"Стрижка: {_e(look.haircut)}"]
    if look.facial_hair is not None:
        lines.append(f"Борода: {_e(look.facial_hair)}")
    if look.makeup is not None:
        lines.append(f"Макияж: {_e(look.makeup)}")
    lines.append(f"Почему: {_e(look.why)}")
    return _section(f"Образ {n}: {_e(look.name)}", "\n".join(lines))


def _format_appearance(r: AppearanceResult) -> str:
    parts = [_section("Форма лица", _e(r.face_shape))]
    parts.extend(_format_look(n, look) for n, look in enumerate(r.looks, 1))
    parts.append(_section("Лучше избегать", _bullets(r.avoid)))
    if r.brows_lashes.recommendations:
        parts.append(_section("Брови и ресницы", _bullets(r.brows_lashes.recommendations)))
    parts.append(
        _section(
            "Уход за кожей",
            f"Наблюдения:\n{_bullets(r.skincare.observations)}\n"
            f"Рекомендации:\n{_bullets(r.skincare.recommendations)}",
        )
    )
    parts.append(_section("Итог", _e(r.summary)))
    return "\n\n".join(parts)


def _format_style(r: StyleResult) -> str:
    styles = "\n\n".join(
        f"<b>{n}. {_e(s.name)}</b>\n{_e(s.description)}\n{_bullets(s.items)}"
        for n, s in enumerate(r.styles, 1)
    )
    parts = [
        _section(
            f"Цветотип: {_COLOR_TYPE[r.color_type]}",
            _e(r.color_type_explanation),
        ),
        _section("Палитра", _colors(r.palette)),
        _section("Лучше избегать", _colors(r.avoid_colors)),
        _section("Стили", styles),
        _section("Советы по росту", _bullets(r.height_tips)),
        _section("Итог", _e(r.summary)),
    ]
    return "\n\n".join(parts)


def format_result(result: AppearanceResult | StyleResult) -> str:
    if isinstance(result, AppearanceResult):
        return _format_appearance(result)
    return _format_style(result)


def format_weight_plan(plan: WeightPlan) -> str:
    lines = [
        "<b>План здорового веса</b>",
        f"Целевой вес: {plan.target_kg:g} кг",
        f"Темп: {plan.rate_kg_per_week:.2f} кг/нед",
        f"Калории: {plan.kcal} ккал/день",
        f"Срок: {plan.months} мес.",
    ]
    if plan.extended:
        lines.append(
            texts.TERM_EXTENDED.format(requested=plan.requested_months, months=plan.months)
        )
    lines.append("")
    lines.append(texts.DISCLAIMER)
    return "\n".join(lines)


TELEGRAM_TEXT_LIMIT = 4096


def _pack(text: str, separators: tuple[str, ...], limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    if not separators:
        return [text[i : i + limit] for i in range(0, len(text), limit)]
    sep, rest = separators[0], separators[1:]
    chunks: list[str] = []
    current: str | None = None
    for part in text.split(sep):
        for piece in _pack(part, rest, limit):
            if current is None:
                current = piece
            elif len(current) + len(sep) + len(piece) <= limit:
                current = f"{current}{sep}{piece}"
            else:
                chunks.append(current)
                current = piece
    if current is not None:
        chunks.append(current)
    return chunks


def split_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split text into chunks of at most ``limit`` chars.

    Splits on section boundaries ("\\n\\n"), then on lines, and hard-splits by
    characters only as a last resort for a single oversized line.
    """
    return _pack(text, ("\n\n", "\n"), limit)


def format_history_item(mode: Mode, result: dict[str, Any], created_at: datetime) -> str:
    summary = _e(str(result.get("summary", "")))
    return f"{created_at:%d.%m.%Y} — <b>{_MODE_LABEL[mode]}</b>\n{summary}"
