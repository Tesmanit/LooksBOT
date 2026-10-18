import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from botlooks.db.repositories import AnalysisRepo, PaymentRepo, UserRepo
from botlooks.domain.schemas import Profile, ResultParseError, StyleResult, Unsuitable
from botlooks.llm.base import LLMUnavailableError
from botlooks.services.analysis import AnalysisService, ProfileIncompleteError
from botlooks.services.billing import BillingService, NoCreditsError
from botlooks.services.prompts import REPAIR_SUFFIX

Sm = async_sessionmaker[AsyncSession]
Response = str | BaseException
SvcFactory = Callable[[list[Response]], AnalysisService]


def _color(i: int) -> dict[str, str]:
    return {"name": f"Цвет {i}", "hex": f"#C8553{i}"}


STYLE = json.dumps(
    {
        "status": "ok",
        "color_type": "autumn",
        "color_type_explanation": "почему",
        "palette": [_color(i) for i in range(6)],
        "avoid_colors": [_color(i) for i in range(3)],
        "styles": [
            {"name": "Smart casual", "description": "d", "items": ["i"]},
            {"name": "Classic", "description": "d", "items": ["i"]},
        ],
        "height_tips": ["t"],
        "summary": "итог",
    }
)
APPEARANCE = json.dumps(
    {
        "status": "ok",
        "face_shape": "овальное",
        "haircut": {"recommended": ["a"], "avoid": ["b"], "comment": "c"},
        "facial_hair": {"recommendations": ["борода"]},
        "brows_lashes": {"recommendations": ["брови"]},
        "makeup": None,
        "skincare": {"observations": ["o"], "recommendations": ["r"]},
        "summary": "итог",
    }
)


class FakeLLM:
    model = "fake-model"

    def __init__(self, responses: list[Response]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def analyze(self, image: bytes, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def make_profile(**kw: Any) -> Profile:
    base: dict[str, Any] = {
        "gender": "male",
        "height_cm": 180,
        "weight_kg": 100,
        "age": 30,
        "activity": "medium",
    }
    return Profile(**{**base, **kw})


@pytest.fixture
def users(sm: Sm) -> UserRepo:
    return UserRepo(sm)


@pytest.fixture
def analyses(sm: Sm) -> AnalysisRepo:
    return AnalysisRepo(sm)


@pytest.fixture
async def user1(users: UserRepo) -> None:
    await users.upsert(1, "u", 3)
    await users.save_profile(1, make_profile())


@pytest.fixture
def svc_with(sm: Sm, users: UserRepo, analyses: AnalysisRepo, user1: None) -> SvcFactory:
    def factory(responses: list[Response]) -> AnalysisService:
        billing = BillingService(users, PaymentRepo(sm))
        return AnalysisService(users, analyses, billing, FakeLLM(responses))

    return factory


@pytest.fixture
def svc(svc_with: SvcFactory) -> AnalysisService:
    return svc_with([STYLE])


def calls(svc: AnalysisService) -> list[tuple[str, str]]:
    llm: FakeLLM = svc._llm  # type: ignore[assignment]
    return llm.calls


async def test_ok_saves_and_debits(
    svc: AnalysisService, users: UserRepo, analyses: AnalysisRepo
) -> None:
    out = await svc.run(1, "style", b"img")
    assert isinstance(out.result, StyleResult)
    assert out.analysis_id
    assert not out.weight_plan_available
    assert await users.get_credits(1) == 2
    row = await analyses.get_for_user(out.analysis_id, 1)
    assert row is not None
    assert row.model == "fake-model"
    assert row.result["color_type"] == "autumn"


async def test_appearance_reports_plan_available(svc_with: SvcFactory) -> None:
    out = await svc_with([APPEARANCE]).run(1, "appearance", b"img")
    assert out.weight_plan_available


async def test_unsuitable_refunds(svc_with: SvcFactory, users: UserRepo) -> None:
    out = await svc_with(['{"status":"unsuitable","reason":"r"}']).run(1, "style", b"img")
    assert isinstance(out.result, Unsuitable)
    assert out.analysis_id is None
    assert await users.get_credits(1) == 3


async def test_repair_retry(svc_with: SvcFactory, users: UserRepo) -> None:
    svc = svc_with(["garbage", STYLE])
    out = await svc.run(1, "style", b"img")
    assert isinstance(out.result, StyleResult)
    assert len(calls(svc)) == 2
    assert not calls(svc)[0][1].endswith(REPAIR_SUFFIX)
    assert calls(svc)[1][1].endswith(REPAIR_SUFFIX)
    assert await users.get_credits(1) == 2


async def test_parse_fails_twice_refunds(svc_with: SvcFactory, users: UserRepo) -> None:
    svc = svc_with(["x", "y"])
    with pytest.raises(ResultParseError):
        await svc.run(1, "style", b"img")
    assert len(calls(svc)) == 2
    assert await users.get_credits(1) == 3


async def test_llm_down_refunds(svc_with: SvcFactory, users: UserRepo) -> None:
    with pytest.raises(LLMUnavailableError):
        await svc_with([LLMUnavailableError()]).run(1, "style", b"img")
    assert await users.get_credits(1) == 3


async def test_cancellation_refunds(svc_with: SvcFactory, users: UserRepo) -> None:
    with pytest.raises(asyncio.CancelledError):
        await svc_with([asyncio.CancelledError()]).run(1, "style", b"img")
    assert await users.get_credits(1) == 3


async def test_no_credits(svc: AnalysisService, users: UserRepo) -> None:
    await users.add_credits(1, -3)
    with pytest.raises(NoCreditsError):
        await svc.run(1, "style", b"img")
    assert calls(svc) == []
    assert await users.get_credits(1) == 0


async def test_incomplete_profile(svc: AnalysisService, users: UserRepo) -> None:
    await users.upsert(2, "v", 3)
    with pytest.raises(ProfileIncompleteError):
        await svc.run(2, "style", b"img")
    assert calls(svc) == []
    assert await users.get_credits(2) == 3


async def test_weight_plan_foreign_analysis(
    svc_with: SvcFactory, users: UserRepo, analyses: AnalysisRepo
) -> None:
    svc = svc_with([APPEARANCE])
    await users.upsert(2, "v", 3)
    await users.save_profile(2, make_profile())
    out = await svc.run(1, "appearance", b"img")
    assert out.analysis_id
    assert await svc.weight_plan(2, out.analysis_id, 6) is None
    assert await svc.weight_plan(1, 999, 6) is None
    row = await analyses.get_for_user(out.analysis_id, 1)
    assert row is not None
    assert "weight_plan" not in row.result


async def test_weight_plan_attached(svc_with: SvcFactory, analyses: AnalysisRepo) -> None:
    svc = svc_with([APPEARANCE])
    out = await svc.run(1, "appearance", b"img")
    assert out.analysis_id
    plan = await svc.weight_plan(1, out.analysis_id, 6)
    assert plan is not None
    assert plan.kcal == 2250
    row = await analyses.get_for_user(out.analysis_id, 1)
    assert row is not None
    assert row.result["weight_plan"]["kcal"] == 2250


async def test_weight_plan_bad_months(svc: AnalysisService) -> None:
    with pytest.raises(ValueError):
        await svc.weight_plan(1, 1, 5)


async def test_weight_plan_unavailable_returns_none(svc: AnalysisService, users: UserRepo) -> None:
    await users.save_profile(1, make_profile(weight_kg=70))
    assert await svc.weight_plan(1, 1, 6) is None
    assert await svc.target_weight_for(1) is None


async def test_target_weight_for(svc: AnalysisService, users: UserRepo) -> None:
    assert await svc.target_weight_for(1) == 81.0
    await users.upsert(2, "v", 3)
    assert await svc.target_weight_for(2) is None


class ReleaseThenFail(BillingService):
    async def release(self, user_id: int) -> None:
        await super().release(user_id)
        raise RuntimeError("after release")


async def test_unsuitable_release_not_repeated(
    sm: Sm, users: UserRepo, analyses: AnalysisRepo, user1: None
) -> None:
    billing = ReleaseThenFail(users, PaymentRepo(sm))
    llm = FakeLLM(['{"status":"unsuitable","reason":"r"}'])
    svc = AnalysisService(users, analyses, billing, llm)
    with pytest.raises(RuntimeError):
        await svc.run(1, "style", b"img")
    assert await users.get_credits(1) == 3
