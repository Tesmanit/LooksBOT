import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from botlooks.config import PACKS
from botlooks.db.repositories import AnalysisRepo, PaymentRepo, UserRepo
from botlooks.domain.schemas import Profile

SM = async_sessionmaker[AsyncSession]


async def test_upsert_keeps_credits(sm: SM) -> None:
    u = UserRepo(sm)
    await u.upsert(1, "a", 3)
    await u.try_debit(1)
    await u.upsert(1, "b", 3)
    assert await u.get_credits(1) == 2


async def test_get_credits_unknown_user(sm: SM) -> None:
    assert await UserRepo(sm).get_credits(999) == 0


async def test_concurrent_debit(sm: SM) -> None:
    u = UserRepo(sm)
    await u.upsert(1, None, 3)
    results = await asyncio.gather(*[u.try_debit(1) for _ in range(5)])
    assert results.count(True) == 3
    assert await u.get_credits(1) == 0


async def test_add_credits(sm: SM) -> None:
    u = UserRepo(sm)
    await u.upsert(1, None, 3)
    await u.add_credits(1, 4)
    assert await u.get_credits(1) == 7


async def test_profile_roundtrip(sm: SM) -> None:
    u = UserRepo(sm)
    await u.upsert(1, None, 3)
    assert await u.get_profile(1) is None
    profile = Profile(gender="female", height_cm=170, weight_kg=72.5, age=30, activity="medium")
    await u.save_profile(1, profile)
    assert await u.get_profile(1) == profile


async def test_record_paid_idempotent(sm: SM) -> None:
    u, p = UserRepo(sm), PaymentRepo(sm)
    await u.upsert(1, None, 3)
    assert await p.record_paid(1, PACKS["pack_5"], "ch") is True
    assert await p.record_paid(1, PACKS["pack_5"], "ch") is False
    assert await u.get_credits(1) == 8
    paid = await p.get_paid("ch")
    assert paid is not None and paid.credits_added == 5 and paid.stars == 60
    assert await p.get_paid("other") is None


async def test_refund_floors_at_zero(sm: SM) -> None:
    u, p = UserRepo(sm), PaymentRepo(sm)
    await u.upsert(1, None, 3)
    await p.record_paid(1, PACKS["pack_5"], "ch")
    for _ in range(7):
        assert await u.try_debit(1) is True
    assert await u.get_credits(1) == 1
    assert await p.mark_refunded("ch") is True
    assert await u.get_credits(1) == 0
    assert await p.mark_refunded("ch") is False
    assert await p.get_paid("ch") is None


async def test_attach_weight_plan_foreign_user(sm: SM) -> None:
    u, a = UserRepo(sm), AnalysisRepo(sm)
    await u.upsert(1, None, 3)
    await u.upsert(2, None, 3)
    aid = await a.add(1, "appearance", {"status": "ok"}, "m")
    plan = {"kcal": 2000}
    assert await a.attach_weight_plan(aid, 2, plan) is False
    row = await a.get_for_user(aid, 1)
    assert row is not None and "weight_plan" not in row.result
    assert await a.get_for_user(aid, 2) is None
    assert await a.attach_weight_plan(aid, 1, plan) is True
    row = await a.get_for_user(aid, 1)
    assert row is not None and row.result["weight_plan"] == plan


async def test_attach_weight_plan_style_mode_rejected(sm: SM) -> None:
    u, a = UserRepo(sm), AnalysisRepo(sm)
    await u.upsert(1, None, 3)
    aid = await a.add(1, "style", {"status": "ok"}, "m")
    assert await a.attach_weight_plan(aid, 1, {"x": 1}) is False


async def test_last_orders_newest_first(sm: SM) -> None:
    u, a = UserRepo(sm), AnalysisRepo(sm)
    await u.upsert(1, None, 3)
    ids = [await a.add(1, "appearance", {"n": i}, "m") for i in range(6)]
    rows = await a.last(1)
    assert len(rows) == 5
    assert rows[0].id == ids[-1]
    assert [r.id for r in rows] == ids[:0:-1]
