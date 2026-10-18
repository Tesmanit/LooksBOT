import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext

from botlooks.bot import texts
from botlooks.bot.handlers import analysis as h
from botlooks.bot.handlers.profile import on_activity
from botlooks.bot.keyboards import ActivityCb, ModeCb, WeightAskCb, WeightTermCb
from botlooks.bot.states import AnalysisFlow, ProfileForm
from botlooks.domain.schemas import (
    AppearanceResult,
    NamedColor,
    StyleDirection,
    StyleResult,
    Unsuitable,
)
from botlooks.llm.base import LLMUnavailableError
from botlooks.services.analysis import AnalysisOutcome, AnalysisService, ProfileIncompleteError
from botlooks.services.billing import BillingService, NoCreditsError
from botlooks.services.weight import WeightPlan

APPEARANCE: dict[str, Any] = {
    "status": "ok",
    "face_shape": "овал",
    "haircut": {"recommended": ["a"], "avoid": ["b"], "comment": "c"},
    "facial_hair": {"recommendations": ["x"]},
    "brows_lashes": {"recommendations": ["y"]},
    "makeup": None,
    "skincare": {"observations": ["o"], "recommendations": ["r"]},
    "summary": "<5 мин & готово",
}


def _colors(n: int) -> list[NamedColor]:
    return [NamedColor(name=f"c{i}", hex="#aabbcc") for i in range(n)]


def style_result() -> StyleResult:
    return StyleResult(
        status="ok",
        color_type="spring",
        color_type_explanation="e",
        palette=_colors(6),
        avoid_colors=_colors(3),
        styles=[
            StyleDirection(name="s1", description="d", items=["i"]),
            StyleDirection(name="s2", description="d", items=["i"]),
        ],
        height_tips=["t"],
        summary="sum",
    )


def appearance_result() -> AppearanceResult:
    return AppearanceResult.model_validate(APPEARANCE)


@pytest.fixture(autouse=True)
def _clean_guard() -> Any:
    h._in_progress.clear()
    yield
    h._in_progress.clear()


@pytest.fixture
def bot() -> Any:
    b = AsyncMock()
    b.download = AsyncMock()
    return b


@pytest.fixture
def analysis() -> Any:
    return AsyncMock(spec=AnalysisService)


@pytest.fixture
def billing() -> Any:
    b = AsyncMock(spec=BillingService)
    b.balance.return_value = 2
    return b


@pytest.fixture
def photo_msg(make_message: Any) -> Any:
    def factory() -> Any:
        m = make_message(photo=[MagicMock(), MagicMock()])
        m.chat = MagicMock()
        m.chat.id = 1
        m.answer_photo = AsyncMock()
        return m

    return factory


def _texts(msg: Any) -> list[str]:
    return [str(c) for c in msg.answer.await_args_list]


async def test_parallel_photos_single_run(
    state: FSMContext, bot: Any, analysis: Any, billing: Any, photo_msg: Any
) -> None:
    async def slow_run(*a: Any, **k: Any) -> AnalysisOutcome:
        await asyncio.sleep(0.05)
        return AnalysisOutcome(appearance_result(), 1, False)

    analysis.run.side_effect = slow_run
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="appearance")
    m1, m2 = photo_msg(), photo_msg()
    await asyncio.gather(
        h.on_photo(m1, state, bot, analysis, billing),
        h.on_photo(m2, state, bot, analysis, billing),
    )
    assert analysis.run.await_count == 1
    assert any(texts.BUSY in t for t in _texts(m2))
    assert 1 not in h._in_progress


async def test_style_sends_palette(
    state: FSMContext, bot: Any, analysis: Any, billing: Any, photo_msg: Any
) -> None:
    analysis.run.return_value = AnalysisOutcome(style_result(), 5, False)
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="style")
    m = photo_msg()
    await h.on_photo(m, state, bot, analysis, billing)
    m.answer_photo.assert_awaited_once()
    assert await state.get_state() is None


async def test_appearance_offers_weight_plan(
    state: FSMContext, bot: Any, analysis: Any, billing: Any, photo_msg: Any
) -> None:
    analysis.run.return_value = AnalysisOutcome(appearance_result(), 7, True)
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="appearance")
    m = photo_msg()
    await h.on_photo(m, state, bot, analysis, billing)
    last = m.answer.await_args_list[-1]
    assert last.args[0] == texts.ASK_WEIGHT_LOSS
    cb = last.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    assert WeightAskCb.unpack(cb) == WeightAskCb(analysis_id=7, yes=True)
    assert "&lt;5 мин &amp; готово" in m.answer.await_args_list[0].args[0]


async def test_unsuitable_escapes_reason(
    state: FSMContext, bot: Any, analysis: Any, billing: Any, photo_msg: Any
) -> None:
    analysis.run.return_value = AnalysisOutcome(
        Unsuitable(status="unsuitable", reason="<тёмное> & мутное"), None, False
    )
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="style")
    m = photo_msg()
    await h.on_photo(m, state, bot, analysis, billing)
    assert "&lt;тёмное&gt; &amp; мутное" in m.answer.await_args.args[0]
    assert await state.get_state() is None


@pytest.mark.parametrize(
    ("exc", "text"),
    [
        (LLMUnavailableError(), texts.LLM_DOWN),
        (NoCreditsError(), texts.NO_CREDITS),
    ],
)
async def test_errors_clear_state(
    state: FSMContext,
    bot: Any,
    analysis: Any,
    billing: Any,
    photo_msg: Any,
    exc: Exception,
    text: str,
) -> None:
    analysis.run.side_effect = exc
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="style")
    m = photo_msg()
    await h.on_photo(m, state, bot, analysis, billing)
    assert m.answer.await_args.args[0] == text
    assert await state.get_state() is None
    assert 1 not in h._in_progress


async def test_profile_incomplete_restarts_form(
    state: FSMContext, bot: Any, analysis: Any, billing: Any, photo_msg: Any
) -> None:
    analysis.run.side_effect = ProfileIncompleteError()
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="style")
    await h.on_photo(photo_msg(), state, bot, analysis, billing)
    assert await state.get_state() == ProfileForm.gender.state
    assert (await state.get_data())["pending_mode"] == "style"


async def test_mode_without_profile_starts_form(
    state: FSMContext, make_callback: Any, user_repo_mock: Any, billing: Any
) -> None:
    user_repo_mock.get_profile.return_value = None
    cb = make_callback()
    await h.on_mode(cb, ModeCb(mode="style"), state, user_repo_mock, billing)
    assert await state.get_state() == ProfileForm.gender.state
    assert (await state.get_data())["pending_mode"] == "style"
    cb.answer.assert_awaited_once()


async def test_mode_with_profile_asks_photo(
    state: FSMContext, make_callback: Any, user_repo_mock: Any, billing: Any
) -> None:
    cb = make_callback()
    await h.on_mode(cb, ModeCb(mode="style"), state, user_repo_mock, billing)
    assert await state.get_state() == AnalysisFlow.waiting_photo.state
    assert (await state.get_data())["mode"] == "style"
    assert cb.message.answer.await_args.args[0] == texts.ASK_PHOTO


async def test_no_credits_shows_packs(
    state: FSMContext, make_callback: Any, user_repo_mock: Any, billing: Any
) -> None:
    billing.balance.return_value = 0
    cb = make_callback()
    await h.on_mode(cb, ModeCb(mode="style"), state, user_repo_mock, billing)
    assert cb.message.answer.await_args.args[0] == texts.NO_CREDITS
    assert cb.message.answer.await_args.kwargs["reply_markup"] is not None
    assert await state.get_state() != AnalysisFlow.waiting_photo.state


async def test_profile_done_with_pending_mode_asks_photo(
    state: FSMContext, make_callback: Any, user_repo_mock: Any, billing: Any
) -> None:
    await state.set_state(ProfileForm.activity)
    await state.update_data(
        gender="male", height=170, weight=70.0, age=25, pending_mode="appearance"
    )
    cb = make_callback()
    await on_activity(cb, ActivityCb(activity="low"), state, user_repo_mock, billing)
    assert await state.get_state() == AnalysisFlow.waiting_photo.state
    assert cb.message.answer.await_args.args[0] == texts.ASK_PHOTO


async def test_text_while_waiting(make_message: Any) -> None:
    m = make_message("hi")
    await h.on_not_photo(m)
    m.answer.assert_awaited_once_with(texts.NOT_A_PHOTO)


async def test_stray_photo(make_message: Any) -> None:
    m = make_message(photo=[MagicMock()])
    await h.on_stray_photo(m)
    assert m.answer.await_args.args[0] == texts.PICK_MODE_FIRST
    assert m.answer.await_args.kwargs["reply_markup"] is not None


async def test_weight_ask_no_removes_keyboard(make_callback: Any, analysis: Any) -> None:
    cb = make_callback()
    cb.message.edit_reply_markup = AsyncMock()
    await h.on_weight_ask(cb, WeightAskCb(analysis_id=1, yes=False), analysis)
    cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    cb.answer.assert_awaited_once()


async def test_weight_ask_yes_asks_term(make_callback: Any, analysis: Any) -> None:
    analysis.target_weight_for.return_value = 74.5
    cb = make_callback()
    await h.on_weight_ask(cb, WeightAskCb(analysis_id=1, yes=True), analysis)
    assert cb.message.answer.await_args.args[0] == texts.ASK_TERM.format(target="74.5")


async def test_weight_term_plan_and_none(make_callback: Any, analysis: Any) -> None:
    plan = WeightPlan(
        target_kg=74.5,
        rate_kg_per_week=0.5,
        kcal=2000,
        months=6,
        requested_months=6,
        extended=False,
    )
    analysis.weight_plan.return_value = plan
    cb = make_callback()
    await h.on_weight_term(cb, WeightTermCb(analysis_id=1, months=6), analysis)
    assert texts.DISCLAIMER in cb.message.answer.await_args.args[0]
    analysis.weight_plan.return_value = None
    cb = make_callback()
    await h.on_weight_term(cb, WeightTermCb(analysis_id=1, months=6), analysis)
    assert cb.message.answer.await_args.args[0] == texts.NO_SAFE_PLAN


async def test_weight_term_forged_months(make_callback: Any, analysis: Any) -> None:
    analysis.weight_plan.side_effect = ValueError("unsupported")
    cb = make_callback()
    await h.on_weight_term(cb, WeightTermCb(analysis_id=1, months=99), analysis)
    assert cb.message.answer.await_args.args[0] == texts.GENERIC_ERROR
    cb.answer.assert_awaited_once()


async def test_long_result_split_markup_only_on_last(
    state: FSMContext, bot: Any, analysis: Any, billing: Any, photo_msg: Any
) -> None:
    long = appearance_result().model_copy(update={"summary": "s" * 3000, "face_shape": "f" * 3000})
    analysis.run.return_value = AnalysisOutcome(long, 7, False)
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode="appearance")
    m = photo_msg()
    await h.on_photo(m, state, bot, analysis, billing)
    calls = m.answer.await_args_list
    assert len(calls) >= 2
    assert all(len(c.args[0]) <= 4096 for c in calls)
    assert all(c.kwargs.get("reply_markup") is None for c in calls[:-1])
    assert calls[-1].kwargs["reply_markup"] is not None
