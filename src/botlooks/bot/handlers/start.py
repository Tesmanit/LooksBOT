from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from botlooks.bot import texts
from botlooks.bot.handlers.profile import start_profile
from botlooks.bot.keyboards import main_menu
from botlooks.config import Settings
from botlooks.db.repositories import UserRepo

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, user_repo: UserRepo, settings: Settings
) -> None:
    user = message.from_user
    if user is None:
        return
    await user_repo.upsert(user.id, user.username, settings.start_credits)
    await state.clear()
    await message.answer(texts.WELCOME, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext) -> None:
    await start_profile(message, state, pending_mode=None)
