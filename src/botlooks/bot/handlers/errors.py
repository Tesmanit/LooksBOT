import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import ErrorEvent

from botlooks.bot import texts

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent, state: FSMContext | None = None) -> None:
    logger.error("Unhandled error in update handler", exc_info=event.exception)
    if state is not None:
        try:
            await state.clear()
        except Exception:
            logger.exception("Failed to clear FSM state")
    update = event.update
    try:
        if update.message is not None:
            await update.message.answer(texts.GENERIC_ERROR)
        elif update.callback_query is not None:
            await update.callback_query.answer(texts.GENERIC_ERROR, show_alert=True)
    except Exception:
        logger.exception("Failed to send error reply")
