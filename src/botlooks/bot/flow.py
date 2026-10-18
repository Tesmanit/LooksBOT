from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from botlooks.bot import texts
from botlooks.bot.keyboards import packs_kb
from botlooks.bot.states import AnalysisFlow
from botlooks.config import PACKS
from botlooks.domain.schemas import Mode
from botlooks.services.billing import BillingService


async def ask_photo_or_buy(
    message: Message,
    state: FSMContext,
    mode: Mode,
    billing: BillingService,
    user_id: int | None = None,
) -> None:
    """Ask for a photo, or offer packs when the balance is empty.

    ``user_id`` must be passed from callbacks, where ``message.from_user`` is the bot.
    """
    if user_id is None:
        if message.from_user is None:
            return
        user_id = message.from_user.id
    if await billing.balance(user_id) <= 0:
        await state.clear()
        await message.answer(texts.NO_CREDITS, reply_markup=packs_kb(PACKS.values()))
        return
    await state.set_state(AnalysisFlow.waiting_photo)
    await state.update_data(mode=mode)
    await message.answer(texts.ASK_PHOTO)
