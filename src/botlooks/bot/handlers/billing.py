from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from botlooks.bot import texts
from botlooks.bot.keyboards import PackCb, packs_kb
from botlooks.config import PACKS, Settings
from botlooks.db.repositories import UserRepo
from botlooks.services.billing import BillingService

router = Router(name="billing")


@router.message(Command("buy"))
async def on_buy(message: Message) -> None:
    await message.answer(texts.BUY_TITLE, reply_markup=packs_kb(PACKS.values()))


@router.callback_query(PackCb.filter())
async def on_pack(
    callback: CallbackQuery, callback_data: PackCb, bot: Bot, billing: BillingService
) -> None:
    pack = PACKS.get(callback_data.pack_id)
    if pack is None or not isinstance(callback.message, Message):
        await callback.answer(texts.GENERIC_ERROR)
        return
    await callback.answer()
    title = texts.PACK_TITLE.format(credits=pack.credits)
    await bot.send_invoice(
        callback.message.chat.id,
        title=title,
        description=texts.PACK_DESCRIPTION.format(credits=pack.credits),
        payload=billing.new_payload(pack.id),
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=pack.stars)],
        provider_token="",
    )


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, billing: BillingService) -> None:
    if billing.pack_from_payload(query.invoice_payload) is not None:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=texts.PRECHECKOUT_FAILED)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message, billing: BillingService, user_repo: UserRepo, settings: Settings
) -> None:
    user = message.from_user
    sp = message.successful_payment
    if user is None or sp is None:
        return
    await user_repo.upsert(user.id, user.username, settings.start_credits)
    added = await billing.apply_payment(user.id, sp.invoice_payload, sp.telegram_payment_charge_id)
    if added is None:
        return
    await message.answer(texts.PAID.format(credits=await billing.balance(user.id)))


@router.message(Command("balance"))
async def on_balance(message: Message, billing: BillingService) -> None:
    if message.from_user is None:
        return
    credits = await billing.balance(message.from_user.id)
    await message.answer(texts.BALANCE.format(credits=credits))


@router.message(Command("paysupport"))
async def on_paysupport(message: Message) -> None:
    await message.answer(texts.PAYSUPPORT)
