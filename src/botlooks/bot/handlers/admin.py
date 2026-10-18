from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from botlooks.bot import texts
from botlooks.config import Settings
from botlooks.services.billing import BillingService

router = Router(name="admin")


@router.message(Command("refund"))
async def on_refund(
    message: Message,
    command: CommandObject,
    bot: Bot,
    billing: BillingService,
    settings: Settings,
) -> None:
    if message.from_user is None or message.from_user.id != settings.admin_id:
        return
    charge_id = (command.args or "").strip()
    payment = await billing.find_refundable(charge_id) if charge_id else None
    if payment is None:
        await message.answer(texts.REFUND_NOT_FOUND)
        return
    await bot.refund_star_payment(user_id=payment.user_id, telegram_payment_charge_id=charge_id)
    await billing.complete_refund(charge_id)
    await message.answer(texts.REFUND_OK)
