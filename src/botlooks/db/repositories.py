from typing import Any

from sqlalchemy import cast, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import func

from botlooks.config import Pack
from botlooks.db.models import Analysis, Payment, User
from botlooks.domain.schemas import Mode, Profile

Sessionmaker = async_sessionmaker[AsyncSession]


class UserRepo:
    def __init__(self, sm: Sessionmaker) -> None:
        self._sm = sm

    async def upsert(self, user_id: int, username: str | None, start_credits: int) -> None:
        stmt = pg_insert(User).values(id=user_id, username=username, credits=start_credits)
        stmt = stmt.on_conflict_do_update(index_elements=[User.id], set_={"username": username})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get_profile(self, user_id: int) -> Profile | None:
        async with self._sm.begin() as s:
            u = await s.get(User, user_id)
            if (
                u is None
                or u.gender is None
                or u.height_cm is None
                or u.weight_kg is None
                or u.age is None
                or u.activity is None
            ):
                return None
            return Profile.model_validate(
                {
                    "gender": u.gender,
                    "height_cm": u.height_cm,
                    "weight_kg": float(u.weight_kg),
                    "age": u.age,
                    "activity": u.activity,
                }
            )

    async def save_profile(self, user_id: int, profile: Profile) -> None:
        async with self._sm.begin() as s:
            await s.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    gender=profile.gender,
                    height_cm=profile.height_cm,
                    weight_kg=profile.weight_kg,
                    age=profile.age,
                    activity=profile.activity,
                )
            )

    async def try_debit(self, user_id: int) -> bool:
        stmt = (
            update(User)
            .where(User.id == user_id, User.credits > 0)
            .values(credits=User.credits - 1)
            .returning(User.credits)
        )
        async with self._sm.begin() as s:
            return (await s.execute(stmt)).first() is not None

    async def add_credits(self, user_id: int, n: int) -> None:
        async with self._sm.begin() as s:
            await s.execute(update(User).where(User.id == user_id).values(credits=User.credits + n))

    async def get_credits(self, user_id: int) -> int:
        async with self._sm.begin() as s:
            value = await s.scalar(select(User.credits).where(User.id == user_id))
            return value or 0


class AnalysisRepo:
    def __init__(self, sm: Sessionmaker) -> None:
        self._sm = sm

    async def add(self, user_id: int, mode: Mode, result: dict[str, Any], model: str) -> int:
        row = Analysis(user_id=user_id, mode=mode, result=result, model=model)
        async with self._sm.begin() as s:
            s.add(row)
            await s.flush()
            return row.id

    async def attach_weight_plan(
        self, analysis_id: int, user_id: int, plan: dict[str, Any]
    ) -> bool:
        stmt = (
            update(Analysis)
            .where(
                Analysis.id == analysis_id,
                Analysis.user_id == user_id,
                Analysis.mode == "appearance",
            )
            .values(
                result=Analysis.result.op("||")(
                    func.jsonb_build_object("weight_plan", cast(plan, JSONB))
                )
            )
            .returning(Analysis.id)
        )
        async with self._sm.begin() as s:
            return (await s.execute(stmt)).first() is not None

    async def get_for_user(self, analysis_id: int, user_id: int) -> Analysis | None:
        async with self._sm.begin() as s:
            return await s.scalar(
                select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id)
            )

    async def last(self, user_id: int, limit: int = 5) -> list[Analysis]:
        stmt = (
            select(Analysis)
            .where(Analysis.user_id == user_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(limit)
        )
        async with self._sm.begin() as s:
            return list((await s.scalars(stmt)).all())


class PaymentRepo:
    def __init__(self, sm: Sessionmaker) -> None:
        self._sm = sm

    async def record_paid(self, user_id: int, pack: Pack, charge_id: str) -> bool:
        try:
            async with self._sm.begin() as s:
                s.add(
                    Payment(
                        user_id=user_id,
                        pack=pack.id,
                        stars=pack.stars,
                        credits_added=pack.credits,
                        telegram_payment_charge_id=charge_id,
                        status="paid",
                    )
                )
                await s.flush()
                await s.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(credits=User.credits + pack.credits)
                )
        except IntegrityError as e:
            # Only a duplicate charge_id is idempotent; FK violations etc. must surface.
            if getattr(e.orig, "sqlstate", None) == "23505":
                return False
            raise
        return True

    async def get_paid(self, charge_id: str) -> Payment | None:
        async with self._sm.begin() as s:
            return await s.scalar(
                select(Payment).where(
                    Payment.telegram_payment_charge_id == charge_id, Payment.status == "paid"
                )
            )

    async def mark_refunded(self, charge_id: str) -> bool:
        async with self._sm.begin() as s:
            row = (
                await s.execute(
                    update(Payment)
                    .where(
                        Payment.telegram_payment_charge_id == charge_id, Payment.status == "paid"
                    )
                    .values(status="refunded")
                    .returning(Payment.user_id, Payment.credits_added)
                )
            ).first()
            if row is None:
                return False
            user_id, added = row
            await s.execute(
                update(User)
                .where(User.id == user_id)
                .values(credits=func.greatest(User.credits - added, 0))
            )
            return True
