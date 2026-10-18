from typing import cast

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botlooks.bot import texts
from botlooks.bot.formatting import format_history_item
from botlooks.db.repositories import AnalysisRepo
from botlooks.domain.schemas import Mode

router = Router(name="history")


@router.message(Command("history"))
async def on_history(message: Message, analysis_repo: AnalysisRepo) -> None:
    if message.from_user is None:
        return
    items = await analysis_repo.last(message.from_user.id)
    if not items:
        await message.answer(texts.HISTORY_EMPTY)
        return
    await message.answer(
        "\n\n".join(format_history_item(cast(Mode, a.mode), a.result, a.created_at) for a in items)
    )
