import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from botlooks.bot import texts
from botlooks.bot.keyboards import ActivityCb, GenderCb, activity_kb, gender_kb, main_menu
from botlooks.bot.states import ProfileForm
from botlooks.db.repositories import UserRepo
from botlooks.domain.schemas import Profile
from botlooks.services.billing import BillingService

router = Router(name="profile")

_SUFFIX = re.compile(r"\s*(см|кг)\.?$", re.IGNORECASE)
_INT = re.compile(r"\d+")
_FLOAT = re.compile(r"\d+(\.\d+)?")

HEIGHT_RANGE = (100, 230)
WEIGHT_RANGE = (30, 300)
AGE_RANGE = (14, 100)


def _clean(text: str) -> str:
    return _SUFFIX.sub("", text.strip()).strip()


def parse_int(text: str, lo: int, hi: int) -> int | None:
    cleaned = _clean(text)
    if not _INT.fullmatch(cleaned):
        return None
    value = int(cleaned)
    return value if lo <= value <= hi else None


def parse_weight(text: str) -> float | None:
    cleaned = _clean(text).replace(",", ".")
    if not _FLOAT.fullmatch(cleaned):
        return None
    value = round(float(cleaned), 1)
    lo, hi = WEIGHT_RANGE
    return value if lo <= value <= hi else None


async def start_profile(message: Message, state: FSMContext, pending_mode: str | None) -> None:
    await state.clear()
    await state.update_data(pending_mode=pending_mode)
    await state.set_state(ProfileForm.gender)
    await message.answer(texts.ASK_GENDER, reply_markup=gender_kb())


@router.callback_query(ProfileForm.gender, GenderCb.filter())
async def on_gender(callback: CallbackQuery, callback_data: GenderCb, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(gender=callback_data.gender)
    await state.set_state(ProfileForm.height)
    if isinstance(callback.message, Message):
        await callback.message.answer(texts.ASK_HEIGHT)


@router.message(ProfileForm.height, F.text)
async def on_height(message: Message, state: FSMContext) -> None:
    value = parse_int(message.text or "", *HEIGHT_RANGE)
    if value is None:
        await message.answer(texts.BAD_NUMBER.format(lo=HEIGHT_RANGE[0], hi=HEIGHT_RANGE[1]))
        return
    await state.update_data(height=value)
    await state.set_state(ProfileForm.weight)
    await message.answer(texts.ASK_WEIGHT)


@router.message(ProfileForm.weight, F.text)
async def on_weight(message: Message, state: FSMContext) -> None:
    value = parse_weight(message.text or "")
    if value is None:
        await message.answer(texts.BAD_NUMBER.format(lo=WEIGHT_RANGE[0], hi=WEIGHT_RANGE[1]))
        return
    await state.update_data(weight=value)
    await state.set_state(ProfileForm.age)
    await message.answer(texts.ASK_AGE)


@router.message(ProfileForm.age, F.text)
async def on_age(message: Message, state: FSMContext) -> None:
    value = parse_int(message.text or "", *AGE_RANGE)
    if value is None:
        await message.answer(texts.BAD_NUMBER.format(lo=AGE_RANGE[0], hi=AGE_RANGE[1]))
        return
    await state.update_data(age=value)
    await state.set_state(ProfileForm.activity)
    await message.answer(texts.ASK_ACTIVITY, reply_markup=activity_kb())


@router.callback_query(ProfileForm.activity, ActivityCb.filter())
async def on_activity(
    callback: CallbackQuery,
    callback_data: ActivityCb,
    state: FSMContext,
    user_repo: UserRepo,
    billing: BillingService | None = None,
) -> None:
    await callback.answer()
    data = await state.get_data()
    profile = Profile(
        gender=data["gender"],
        height_cm=data["height"],
        weight_kg=data["weight"],
        age=data["age"],
        activity=callback_data.activity,
    )
    await user_repo.save_profile(callback.from_user.id, profile)
    pending_mode = data.get("pending_mode")
    await state.clear()
    if not isinstance(callback.message, Message):
        return
    # Task 14 swaps this single call site for ask_photo_or_buy(...) when pending_mode is set.
    del pending_mode, billing
    await callback.message.answer(texts.PROFILE_SAVED, reply_markup=main_menu())
