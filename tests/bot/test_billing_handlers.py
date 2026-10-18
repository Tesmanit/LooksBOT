from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from botlooks.bot import texts
from botlooks.bot.handlers import build_router
from botlooks.bot.handlers.admin import on_refund
from botlooks.bot.handlers.billing import (
    on_balance,
    on_buy,
    on_pack,
    on_paysupport,
    on_pre_checkout,
    on_successful_payment,
)
from botlooks.bot.handlers.history import on_history
from botlooks.bot.keyboards import PackCb
from botlooks.services.billing import BillingService


@pytest.fixture
def real_billing() -> BillingService:
    return BillingService(AsyncMock(), AsyncMock())


@pytest.fixture
def billing() -> Any:
    b = AsyncMock(spec=BillingService)
    b.new_payload = MagicMock(return_value="pack_5:u")
    return b


async def test_pre_checkout_rejects_bad_payload(real_billing: BillingService) -> None:
    q = AsyncMock(invoice_payload="garbage")
    await on_pre_checkout(q, real_billing)
    kw = q.answer.await_args.kwargs
    assert kw["ok"] is False
    assert kw["error_message"] == texts.PRECHECKOUT_FAILED


async def test_pre_checkout_rejects_unknown_pack(real_billing: BillingService) -> None:
    q = AsyncMock(invoice_payload="pack_99:x")
    await on_pre_checkout(q, real_billing)
    assert q.answer.await_args.kwargs["ok"] is False


async def test_pre_checkout_accepts(real_billing: BillingService) -> None:
    q = AsyncMock(invoice_payload="pack_5:uuid")
    await on_pre_checkout(q, real_billing)
    assert q.answer.await_args.kwargs["ok"] is True


async def test_buy_shows_packs(make_message: Any) -> None:
    msg = make_message("/buy")
    await on_buy(msg)
    assert msg.answer.await_args.args[0] == texts.BUY_TITLE
    assert msg.answer.await_args.kwargs["reply_markup"] is not None


async def test_invoice_in_stars(make_callback: Any, billing: Any) -> None:
    cb = make_callback()
    cb.message.chat = MagicMock(id=555)
    bot = AsyncMock()
    await on_pack(cb, PackCb(pack_id="pack_5"), bot, billing)
    args, kw = bot.send_invoice.await_args
    assert args[0] == 555
    assert kw["currency"] == "XTR"
    assert kw["provider_token"] == ""
    assert kw["prices"][0].amount == 60
    assert kw["payload"] == "pack_5:u"


async def test_unknown_pack_answers_error(make_callback: Any, billing: Any) -> None:
    cb = make_callback()
    bot = AsyncMock()
    await on_pack(cb, PackCb(pack_id="nope"), bot, billing)
    cb.answer.assert_awaited_once_with(texts.GENERIC_ERROR)
    bot.send_invoice.assert_not_awaited()


def _payment_msg(make_message: Any) -> Any:
    msg = make_message()
    msg.from_user.id = 7
    msg.successful_payment = SimpleNamespace(
        invoice_payload="pack_5:u", telegram_payment_charge_id="ch"
    )
    return msg


async def test_successful_payment_upserts_then_credits(
    make_message: Any, billing: Any, user_repo_mock: Any, settings: Any
) -> None:
    msg = _payment_msg(make_message)
    calls: list[str] = []
    user_repo_mock.upsert.side_effect = lambda *a: calls.append("upsert")
    billing.apply_payment.side_effect = lambda *a: calls.append("apply") or 5
    billing.balance.return_value = 8
    await on_successful_payment(msg, billing, user_repo_mock, settings)
    assert calls == ["upsert", "apply"]
    user_repo_mock.upsert.assert_awaited_once_with(7, "tester", settings.start_credits)
    billing.apply_payment.assert_awaited_once_with(7, "pack_5:u", "ch")
    assert msg.answer.await_args.args[0] == texts.PAID.format(credits=8)


async def test_duplicate_payment_silent(
    make_message: Any, billing: Any, user_repo_mock: Any, settings: Any
) -> None:
    msg = _payment_msg(make_message)
    billing.apply_payment.return_value = None
    await on_successful_payment(msg, billing, user_repo_mock, settings)
    msg.answer.assert_not_awaited()


async def test_balance(make_message: Any, billing: Any) -> None:
    msg = make_message("/balance")
    billing.balance.return_value = 4
    await on_balance(msg, billing)
    assert msg.answer.await_args.args[0] == texts.BALANCE.format(credits=4)


async def test_paysupport(make_message: Any) -> None:
    msg = make_message("/paysupport")
    await on_paysupport(msg)
    assert msg.answer.await_args.args[0] == texts.PAYSUPPORT


async def test_history_empty(make_message: Any) -> None:
    msg = make_message("/history")
    repo = AsyncMock()
    repo.last.return_value = []
    await on_history(msg, repo)
    assert msg.answer.await_args.args[0] == texts.HISTORY_EMPTY


async def test_history_lists_items(make_message: Any) -> None:
    msg = make_message("/history")
    repo = AsyncMock()
    now = datetime(2026, 1, 2, tzinfo=UTC)
    repo.last.return_value = [
        SimpleNamespace(mode="style", result={"summary": "aaa"}, created_at=now),
        SimpleNamespace(mode="appearance", result={"summary": "bbb"}, created_at=now),
    ]
    await on_history(msg, repo)
    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "\n\n" in text and "aaa" in text and "bbb" in text
    repo.last.assert_awaited_once_with(1)


async def test_history_long_is_split(make_message: Any) -> None:
    msg = make_message("/history")
    repo = AsyncMock()
    now = datetime(2026, 1, 2, tzinfo=UTC)
    repo.last.return_value = [
        SimpleNamespace(mode="style", result={"summary": "a" * 1500}, created_at=now)
        for _ in range(5)
    ]
    await on_history(msg, repo)
    calls = msg.answer.await_args_list
    assert len(calls) >= 2
    assert all(len(c.args[0]) <= 4096 for c in calls)


def _cmd(args: str | None) -> Any:
    return SimpleNamespace(args=args)


async def test_refund_non_admin_ignored(make_message: Any, billing: Any, settings: Any) -> None:
    msg = make_message("/refund ch")
    msg.from_user.id = 999
    bot = AsyncMock()
    await on_refund(msg, _cmd("ch"), bot, billing, settings)
    bot.refund_star_payment.assert_not_awaited()
    msg.answer.assert_not_awaited()


async def test_refund_admin(make_message: Any, billing: Any, settings: Any) -> None:
    msg = make_message("/refund ch")
    msg.from_user.id = settings.admin_id
    billing.find_refundable.return_value = SimpleNamespace(user_id=7)
    bot = AsyncMock()
    await on_refund(msg, _cmd("ch"), bot, billing, settings)
    bot.refund_star_payment.assert_awaited_once_with(user_id=7, telegram_payment_charge_id="ch")
    billing.complete_refund.assert_awaited_once_with("ch")
    assert msg.answer.await_args.args[0] == texts.REFUND_OK


@pytest.mark.parametrize("args", [None, "  ", "unknown"])
async def test_refund_not_found(
    make_message: Any, billing: Any, settings: Any, args: str | None
) -> None:
    msg = make_message("/refund")
    msg.from_user.id = settings.admin_id
    billing.find_refundable.return_value = None
    bot = AsyncMock()
    await on_refund(msg, _cmd(args), bot, billing, settings)
    bot.refund_star_payment.assert_not_awaited()
    assert msg.answer.await_args.args[0] == texts.REFUND_NOT_FOUND


def test_build_router_includes_all() -> None:
    root = build_router()
    names = [r.name for r in root.sub_routers]
    assert names == ["errors", "start", "profile", "billing", "history", "admin", "analysis"]


async def test_refund_db_not_updated(make_message: Any, billing: Any, settings: Any) -> None:
    msg = make_message("/refund ch")
    msg.from_user.id = settings.admin_id
    billing.find_refundable.return_value = SimpleNamespace(user_id=7)
    billing.complete_refund.return_value = False
    bot = AsyncMock()
    await on_refund(msg, _cmd("ch"), bot, billing, settings)
    bot.refund_star_payment.assert_awaited_once()
    assert msg.answer.await_args.args[0] == texts.REFUND_DB_NOT_UPDATED


async def test_refund_telegram_failure(make_message: Any, billing: Any, settings: Any) -> None:
    msg = make_message("/refund ch")
    msg.from_user.id = settings.admin_id
    billing.find_refundable.return_value = SimpleNamespace(user_id=7)
    bot = AsyncMock()
    bot.refund_star_payment.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await on_refund(msg, _cmd("ch"), bot, billing, settings)
    billing.complete_refund.assert_not_awaited()
    msg.answer.assert_not_awaited()
