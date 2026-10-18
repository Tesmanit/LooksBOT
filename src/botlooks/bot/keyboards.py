from collections.abc import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from botlooks.config import Pack


class ModeCb(CallbackData, prefix="mode"):
    mode: str


class GenderCb(CallbackData, prefix="gender"):
    gender: str


class ActivityCb(CallbackData, prefix="act"):
    activity: str


class PackCb(CallbackData, prefix="pack"):
    pack_id: str


class WeightAskCb(CallbackData, prefix="wask"):
    analysis_id: int
    yes: bool


class WeightTermCb(CallbackData, prefix="wterm"):
    analysis_id: int
    months: int


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def _btn(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def main_menu() -> InlineKeyboardMarkup:
    return _kb([_btn("Внешность", ModeCb(mode="appearance")), _btn("Стиль", ModeCb(mode="style"))])


def gender_kb() -> InlineKeyboardMarkup:
    return _kb(
        [_btn("Мужчина", GenderCb(gender="male")), _btn("Женщина", GenderCb(gender="female"))]
    )


def activity_kb() -> InlineKeyboardMarkup:
    return _kb(
        [
            _btn("Низкая", ActivityCb(activity="low")),
            _btn("Средняя", ActivityCb(activity="medium")),
            _btn("Высокая", ActivityCb(activity="high")),
        ]
    )


def packs_kb(packs: Iterable[Pack]) -> InlineKeyboardMarkup:
    return _kb(
        *[[_btn(f"Разборов: {p.credits} — {p.stars} ⭐", PackCb(pack_id=p.id))] for p in packs]
    )


def weight_ask_kb(analysis_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [
            _btn("Да", WeightAskCb(analysis_id=analysis_id, yes=True)),
            _btn("Нет", WeightAskCb(analysis_id=analysis_id, yes=False)),
        ]
    )


def weight_term_kb(analysis_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn(f"{m} мес.", WeightTermCb(analysis_id=analysis_id, months=m)) for m in (3, 6, 12)]
    )
