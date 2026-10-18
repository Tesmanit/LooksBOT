import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from botlooks.db.repositories import PaymentRepo, UserRepo
from botlooks.services.billing import BillingService, NoCreditsError

Sm = async_sessionmaker[AsyncSession]


@pytest.fixture
def users(sm: Sm) -> UserRepo:
    return UserRepo(sm)


@pytest.fixture
def payments(sm: Sm) -> PaymentRepo:
    return PaymentRepo(sm)


@pytest.fixture
def billing(users: UserRepo, payments: PaymentRepo) -> BillingService:
    return BillingService(users, payments)


@pytest.mark.parametrize("payload", ["pack_5", "pack_99:x", "", "pack_5:"])
def test_bad_payload(billing: BillingService, payload: str) -> None:
    assert billing.pack_from_payload(payload) is None


def test_payload_roundtrip(billing: BillingService) -> None:
    pack = billing.pack_from_payload(billing.new_payload("pack_15"))
    assert pack is not None
    assert pack.credits == 15


async def test_reserve_and_release(billing: BillingService, users: UserRepo) -> None:
    await users.upsert(1, "u", 3)
    for _ in range(3):
        await billing.reserve(1)
    with pytest.raises(NoCreditsError):
        await billing.reserve(1)
    assert await billing.balance(1) == 0
    await billing.release(1)
    assert await billing.balance(1) == 1


async def test_apply_payment_twice(billing: BillingService, users: UserRepo) -> None:
    await users.upsert(1, "u", 3)
    payload = billing.new_payload("pack_5")
    assert await billing.apply_payment(1, payload, "ch1") == 5
    assert await billing.apply_payment(1, payload, "ch1") is None
    assert await billing.balance(1) == 8


async def test_apply_payment_unknown_pack(billing: BillingService, users: UserRepo) -> None:
    await users.upsert(1, "u", 3)
    assert await billing.apply_payment(1, "pack_99:x", "ch2") is None
    assert await billing.balance(1) == 3


async def test_refund_flow(billing: BillingService, users: UserRepo) -> None:
    await users.upsert(1, "u", 3)
    await billing.apply_payment(1, billing.new_payload("pack_5"), "ch3")
    assert await billing.find_refundable("ch3") is not None
    assert await billing.complete_refund("ch3") is True
    assert await billing.find_refundable("ch3") is None
    assert await billing.complete_refund("ch3") is False
    assert await billing.balance(1) == 3
