from dataclasses import dataclass

from botlooks.db.repositories import AnalysisRepo, UserRepo
from botlooks.domain.schemas import (
    AnalysisResult,
    Mode,
    Profile,
    ResultParseError,
    Unsuitable,
    parse_result,
)
from botlooks.llm.base import VisionLLM
from botlooks.services.billing import BillingService
from botlooks.services.prompts import REPAIR_SUFFIX, build_prompts
from botlooks.services.weight import WeightPlan, build_plan, plan_available, target_weight

PLAN_MONTHS = {3, 6, 12}


class ProfileIncompleteError(Exception):
    pass


@dataclass(frozen=True)
class AnalysisOutcome:
    result: AnalysisResult
    analysis_id: int | None
    weight_plan_available: bool


class AnalysisService:
    def __init__(
        self,
        users: UserRepo,
        analyses: AnalysisRepo,
        billing: BillingService,
        llm: VisionLLM,
    ) -> None:
        self._users = users
        self._analyses = analyses
        self._billing = billing
        self._llm = llm

    async def run(self, user_id: int, mode: Mode, image: bytes) -> AnalysisOutcome:
        profile = await self._users.get_profile(user_id)
        if profile is None:
            raise ProfileIncompleteError
        await self._billing.reserve(user_id)
        try:
            result = await self._analyze(mode, image, profile)
        except BaseException:
            await self._billing.release(user_id)
            raise
        if isinstance(result, Unsuitable):
            await self._billing.release(user_id)
            return AnalysisOutcome(result, None, False)
        try:
            analysis_id = await self._analyses.add(
                user_id, mode, result.model_dump(mode="json"), self._llm.model
            )
        except BaseException:
            await self._billing.release(user_id)
            raise
        return AnalysisOutcome(
            result, analysis_id, mode == "appearance" and plan_available(profile)
        )

    async def _analyze(self, mode: Mode, image: bytes, profile: Profile) -> AnalysisResult:
        system, user = build_prompts(mode, profile)
        raw = await self._llm.analyze(image, system, user)
        try:
            return parse_result(mode, raw, profile.gender)
        except ResultParseError:
            raw = await self._llm.analyze(image, system, user + REPAIR_SUFFIX)
            return parse_result(mode, raw, profile.gender)

    async def weight_plan(self, user_id: int, analysis_id: int, months: int) -> WeightPlan | None:
        if months not in PLAN_MONTHS:
            raise ValueError(f"unsupported months: {months}")
        profile = await self._users.get_profile(user_id)
        if profile is None or not plan_available(profile):
            return None
        plan = build_plan(profile, months)
        if plan is None:
            return None
        if not await self._analyses.attach_weight_plan(analysis_id, user_id, plan.to_dict()):
            return None
        return plan

    async def target_weight_for(self, user_id: int) -> float | None:
        profile = await self._users.get_profile(user_id)
        if profile is None or not plan_available(profile):
            return None
        return target_weight(profile.height_cm)
