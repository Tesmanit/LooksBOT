from typing import Any

import pytest
from aiogram.fsm.context import FSMContext

from botlooks.bot import texts
from botlooks.bot.handlers.profile import (
    on_activity,
    on_age,
    on_gender,
    on_height,
    on_weight,
    parse_int,
    parse_weight,
    start_profile,
)
from botlooks.bot.handlers.start import cmd_help, cmd_profile, cmd_start
from botlooks.bot.keyboards import ActivityCb, GenderCb, ModeCb, main_menu, packs_kb
from botlooks.bot.states import ProfileForm
from botlooks.config import PACKS
from botlooks.domain.schemas import Profile


@pytest.mark.parametrize(
    "text,expected",
    [("72,5", 72.5), (" 80 ", 80.0), ("80 кг", 80.0), ("abc", None), ("29", None), ("301", None)],
)
def test_parse_weight(text: str, expected: float | None) -> None:
    assert parse_weight(text) == expected


@pytest.mark.parametrize(
    "text,expected", [("180", 180), (" 180 ", 180), ("180 см", 180), ("99", None), ("1.8", None)]
)
def test_parse_height(text: str, expected: int | None) -> None:
    assert parse_int(text, 100, 230) == expected


async def test_bad_height_keeps_step(state: FSMContext, make_message: Any) -> None:
    await state.set_state(ProfileForm.height)
    msg = make_message("abc")
    await on_height(msg, state)
    assert await state.get_state() == ProfileForm.height.state
    msg.answer.assert_awaited_once_with(texts.BAD_NUMBER.format(lo=100, hi=230))


async def test_bad_weight_and_age_keep_step(state: FSMContext, make_message: Any) -> None:
    await state.set_state(ProfileForm.weight)
    await on_weight(make_message("мусор"), state)
    assert await state.get_state() == ProfileForm.weight.state
    await state.set_state(ProfileForm.age)
    msg = make_message("5")
    await on_age(msg, state)
    assert await state.get_state() == ProfileForm.age.state
    msg.answer.assert_awaited_once_with(texts.BAD_NUMBER.format(lo=14, hi=100))


async def test_full_profile_saved(
    state: FSMContext, make_message: Any, make_callback: Any, user_repo_mock: Any
) -> None:
    await start_profile(make_message(), state, pending_mode=None)
    assert await state.get_state() == ProfileForm.gender.state
    cb = make_callback()
    await on_gender(cb, GenderCb(gender="female"), state)
    cb.answer.assert_awaited()
    assert await state.get_state() == ProfileForm.height.state
    await on_height(make_message(" 180 "), state)
    await on_weight(make_message("72,5"), state)
    assert await state.get_state() == ProfileForm.age.state
    await on_age(make_message("30"), state)
    assert await state.get_state() == ProfileForm.activity.state
    cb = make_callback()
    await on_activity(cb, ActivityCb(activity="medium"), state, user_repo=user_repo_mock)
    cb.answer.assert_awaited()
    user_repo_mock.save_profile.assert_awaited_once_with(
        1,
        Profile(gender="female", height_cm=180, weight_kg=72.5, age=30, activity="medium"),
    )
    assert await state.get_state() is None
    assert texts.PROFILE_SAVED in cb.message.answer.await_args.args[0]


async def test_pending_mode_shows_menu(
    state: FSMContext, make_message: Any, make_callback: Any, user_repo_mock: Any
) -> None:
    await start_profile(make_message(), state, pending_mode="style")
    await state.set_state(ProfileForm.activity)
    await state.update_data(gender="male", height=170, weight=70.0, age=25)
    cb = make_callback()
    await on_activity(cb, ActivityCb(activity="low"), state, user_repo=user_repo_mock)
    assert cb.message.answer.await_args.kwargs["reply_markup"] is not None
    assert await state.get_state() is None


async def test_start_upserts(
    make_message: Any, state: FSMContext, user_repo_mock: Any, settings: Any
) -> None:
    await state.set_state(ProfileForm.age)
    msg = make_message("/start")
    await cmd_start(msg, state, user_repo=user_repo_mock, settings=settings)
    user_repo_mock.upsert.assert_awaited_once_with(1, "tester", 3)
    assert msg.answer.await_args.args[0] == texts.WELCOME
    assert await state.get_state() is None


async def test_help_and_profile(make_message: Any, state: FSMContext) -> None:
    msg = make_message("/help")
    await cmd_help(msg)
    msg.answer.assert_awaited_once_with(texts.HELP)
    msg = make_message("/profile")
    await cmd_profile(msg, state)
    assert await state.get_state() == ProfileForm.gender.state
    assert msg.answer.await_args.args[0] == texts.ASK_GENDER


def test_keyboards() -> None:
    rows = main_menu().inline_keyboard
    assert [b.text for r in rows for b in r] == ["Внешность", "Стиль"]
    assert ModeCb.unpack(rows[0][0].callback_data).mode == "appearance"
    labels = [b.text for r in packs_kb(list(PACKS.values())).inline_keyboard for b in r]
    assert len(labels) == 3 and "15 ⭐" in labels[0]
