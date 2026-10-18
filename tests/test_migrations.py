import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from botlooks.db.models import Payment, User


async def test_migrations_create_tables(sm):
    async with sm() as s:
        names = (
            (await s.execute(text("select tablename from pg_tables where schemaname='public'")))
            .scalars()
            .all()
        )
    assert {"users", "analyses", "payments", "alembic_version"} <= set(names)


def _payment() -> Payment:
    return Payment(
        user_id=1,
        pack="pack_1",
        stars=15,
        credits_added=1,
        telegram_payment_charge_id="c",
        status="paid",
    )


async def test_charge_id_unique(sm):
    async with sm.begin() as s:
        s.add(User(id=1))
        await s.flush()
        s.add(_payment())
    with pytest.raises(IntegrityError):
        async with sm.begin() as s:
            s.add(_payment())
