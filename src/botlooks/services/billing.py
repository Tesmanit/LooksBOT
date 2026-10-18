from uuid import uuid4

from botlooks.config import PACKS, Pack
from botlooks.db.models import Payment
from botlooks.db.repositories import PaymentRepo, UserRepo


class NoCreditsError(Exception):
    pass


class BillingService:
    def __init__(
        self, users: UserRepo, payments: PaymentRepo, packs: dict[str, Pack] = PACKS
    ) -> None:
        self._users = users
        self._payments = payments
        self._packs = packs

    async def reserve(self, user_id: int) -> None:
        if not await self._users.try_debit(user_id):
            raise NoCreditsError

    async def release(self, user_id: int) -> None:
        await self._users.add_credits(user_id, 1)

    async def balance(self, user_id: int) -> int:
        return await self._users.get_credits(user_id)

    def new_payload(self, pack_id: str) -> str:
        return f"{pack_id}:{uuid4()}"

    def pack_from_payload(self, payload: str) -> Pack | None:
        pack_id, sep, suffix = payload.partition(":")
        if not sep or not suffix:
            return None
        return self._packs.get(pack_id)

    async def apply_payment(self, user_id: int, payload: str, charge_id: str) -> int | None:
        pack = self.pack_from_payload(payload)
        if pack is None:
            return None
        if not await self._payments.record_paid(user_id, pack, charge_id):
            return None
        return pack.credits

    async def find_refundable(self, charge_id: str) -> Payment | None:
        return await self._payments.get_paid(charge_id)

    async def complete_refund(self, charge_id: str) -> bool:
        return await self._payments.mark_refunded(charge_id)
