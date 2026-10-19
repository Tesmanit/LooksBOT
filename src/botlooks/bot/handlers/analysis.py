import contextlib
import html
import logging
from io import BytesIO
from typing import cast

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender

from botlooks.bot import texts
from botlooks.bot.flow import answer_long, ask_photo_or_buy
from botlooks.bot.formatting import format_result, format_weight_plan
from botlooks.bot.handlers.profile import start_profile
from botlooks.bot.keyboards import (
    ModeCb,
    WeightAskCb,
    WeightTermCb,
    main_menu,
    packs_kb,
    weight_ask_kb,
    weight_term_kb,
)
from botlooks.bot.states import AnalysisFlow
from botlooks.config import PACKS
from botlooks.db.repositories import UserRepo
from botlooks.domain.schemas import (
    AppearanceResult,
    Mode,
    ResultParseError,
    StyleResult,
    Unsuitable,
)
from botlooks.llm.base import LLMUnavailableError
from botlooks.services.analysis import AnalysisService, ProfileIncompleteError
from botlooks.services.billing import BillingService, NoCreditsError
from botlooks.services.looks import LooksService
from botlooks.services.palette import render_palette

router = Router(name="analysis")
log = logging.getLogger(__name__)

_in_progress: set[int] = set()


@router.callback_query(ModeCb.filter())
async def on_mode(
    callback: CallbackQuery,
    callback_data: ModeCb,
    state: FSMContext,
    user_repo: UserRepo,
    billing: BillingService,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    mode = cast(Mode, callback_data.mode)
    if mode not in ("appearance", "style"):
        return
    user_id = callback.from_user.id
    if await user_repo.get_profile(user_id) is None:
        await start_profile(callback.message, state, pending_mode=mode)
        return
    await ask_photo_or_buy(callback.message, state, mode, billing, user_id=user_id)


async def _send_collage(
    message: Message,
    bot: Bot,
    looks: LooksService,
    user_id: int,
    photo: bytes,
    result: AppearanceResult | StyleResult,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    await message.answer(texts.RENDERING)
    async with ChatActionSender.upload_photo(bot=bot, chat_id=message.chat.id):
        outcome = await looks.render(user_id, photo, result)
    if outcome.image is None:
        await message.answer(texts.IMAGE_FAILED_REFUNDED, reply_markup=reply_markup)
        return
    try:
        await message.answer_photo(
            BufferedInputFile(outcome.image, "looks.png"),
            caption=outcome.caption,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        log.warning("collage send failed", extra={"error": str(exc)})
        await message.answer(texts.IMAGE_SEND_FAILED, reply_markup=reply_markup)


@router.message(AnalysisFlow.waiting_photo, F.photo)
async def on_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    analysis: AnalysisService,
    billing: BillingService,
    looks: LooksService,
) -> None:
    user = message.from_user
    if user is None or not message.photo:
        return
    user_id = user.id
    if user_id in _in_progress:
        await message.answer(texts.BUSY)
        return
    _in_progress.add(user_id)
    try:
        data = await state.get_data()
        mode = cast(Mode, data.get("mode", "appearance"))
        buffer = BytesIO()
        await bot.download(message.photo[-1], destination=buffer)
        photo = buffer.getvalue()
        try:
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                outcome = await analysis.run(user_id, mode, photo)
        except NoCreditsError:
            await message.answer(texts.NO_CREDITS, reply_markup=packs_kb(PACKS.values()))
        except LLMUnavailableError:
            await message.answer(texts.LLM_DOWN, reply_markup=main_menu())
        except ResultParseError:
            await message.answer(texts.PARSE_FAILED, reply_markup=main_menu())
        except ProfileIncompleteError:
            await start_profile(message, state, pending_mode=mode)
            return
        else:
            result = outcome.result
            if isinstance(result, Unsuitable):
                await message.answer(
                    texts.UNSUITABLE.format(reason=html.escape(result.reason)),
                    reply_markup=main_menu(),
                )
                return  # keep waiting_photo with the same mode: the user is asked to resend
            else:
                has_plan_offer = (
                    isinstance(result, AppearanceResult)
                    and outcome.weight_plan_available
                    and outcome.analysis_id is not None
                )
                collage_markup = (
                    None if isinstance(result, StyleResult) or has_plan_offer else main_menu()
                )
                await answer_long(message, format_result(result))
                await _send_collage(
                    message, bot, looks, user_id, photo, result, reply_markup=collage_markup
                )
                if isinstance(result, StyleResult):
                    png = render_palette(result.palette, result.avoid_colors)
                    await message.answer_photo(
                        BufferedInputFile(png, "palette.png"), reply_markup=main_menu()
                    )
                elif has_plan_offer:
                    await message.answer(
                        texts.ASK_WEIGHT_LOSS,
                        reply_markup=weight_ask_kb(cast(int, outcome.analysis_id)),
                    )
        await state.clear()
    finally:
        _in_progress.discard(user_id)


@router.message(AnalysisFlow.waiting_photo)
async def on_not_photo(message: Message) -> None:
    await message.answer(texts.NOT_A_PHOTO)


@router.message(F.photo)
async def on_stray_photo(message: Message) -> None:
    await message.answer(texts.PICK_MODE_FIRST, reply_markup=main_menu())


@router.callback_query(WeightAskCb.filter())
async def on_weight_ask(
    callback: CallbackQuery, callback_data: WeightAskCb, analysis: AnalysisService
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if not callback_data.yes:
        with contextlib.suppress(TelegramBadRequest):  # double tap: "message is not modified"
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(texts.WEIGHT_DECLINED, reply_markup=main_menu())
        return
    target = await analysis.target_weight_for(callback.from_user.id)
    if target is None:
        await callback.message.answer(texts.NO_SAFE_PLAN, reply_markup=main_menu())
        return
    await callback.message.answer(
        texts.ASK_TERM.format(target=f"{target:g}"),
        reply_markup=weight_term_kb(callback_data.analysis_id),
    )


@router.callback_query(WeightTermCb.filter())
async def on_weight_term(
    callback: CallbackQuery, callback_data: WeightTermCb, analysis: AnalysisService
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        plan = await analysis.weight_plan(
            callback.from_user.id, callback_data.analysis_id, callback_data.months
        )
    except ValueError:
        await callback.message.answer(texts.GENERIC_ERROR)
        return
    if plan is None:
        await callback.message.answer(texts.NO_SAFE_PLAN, reply_markup=main_menu())
        return
    await callback.message.answer(format_weight_plan(plan), reply_markup=main_menu())
