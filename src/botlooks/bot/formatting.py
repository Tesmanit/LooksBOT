from datetime import datetime
from html import escape
from typing import Any

from botlooks.bot import texts
from botlooks.domain.schemas import AppearanceResult, Mode, NamedColor, StyleResult
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


def _format_appearance(r: AppearanceResult) -> str:
    parts = [
        _section("Форма лица", _e(r.face_shape)),
        _section(
            "Стрижка",
            f"Рекомендуется:\n{_bullets(r.haircut.recommended)}\n"
            f"Лучше избегать:\n{_bullets(r.haircut.avoid)}\n{_e(r.haircut.comment)}",
        ),
    ]
    if r.facial_hair is not None:
        parts.append(_section("Борода", _bullets(r.facial_hair.recommendations)))
    if r.brows_lashes.recommendations:
        parts.append(_section("Брови и ресницы", _bullets(r.brows_lashes.recommendations)))
    if r.makeup is not None:
        parts.append(_section("Макияж", _bullets(r.makeup.recommendations)))
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
        f"<b>{_e(s.name)}</b>\n{_e(s.description)}\n{_bullets(s.items)}" for s in r.styles
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


def format_history_item(mode: Mode, result: dict[str, Any], created_at: datetime) -> str:
    summary = _e(str(result.get("summary", "")))
    return f"{created_at:%d.%m.%Y} — <b>{_MODE_LABEL[mode]}</b>\n{summary}"
