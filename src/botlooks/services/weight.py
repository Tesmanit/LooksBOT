import math
from dataclasses import asdict, dataclass

from botlooks.domain.schemas import Profile

TARGET_BMI = 24.9
WEEKS_PER_MONTH = 4.345
KCAL_PER_KG = 7700
MAX_RATE_FRACTION = 0.0075
ACTIVITY_FACTOR = {"low": 1.2, "medium": 1.55, "high": 1.725}
KCAL_FLOOR = {"male": 1500, "female": 1200}


@dataclass(frozen=True)
class WeightPlan:
    target_kg: float
    rate_kg_per_week: float
    kcal: int
    months: int
    requested_months: int
    extended: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def bmi(weight_kg: float, height_cm: int) -> float:
    return weight_kg / (height_cm / 100) ** 2


def target_weight(height_cm: int) -> float:
    h_m = height_cm / 100
    return math.ceil(TARGET_BMI * h_m**2 * 2) / 2


def plan_available(profile: Profile) -> bool:
    return (
        profile.age >= 18
        and bmi(profile.weight_kg, profile.height_cm) >= 25
        and profile.weight_kg > target_weight(profile.height_cm)
    )


def build_plan(profile: Profile, months: int) -> WeightPlan | None:
    weight = profile.weight_kg
    target = target_weight(profile.height_cm)
    sex_term = 5 if profile.gender == "male" else -161
    bmr = 10 * weight + 6.25 * profile.height_cm - 5 * profile.age + sex_term
    tdee = bmr * ACTIVITY_FACTOR[profile.activity]
    floor = KCAL_FLOOR[profile.gender]
    if tdee <= floor:
        return None

    to_lose = weight - target
    rate = to_lose / (months * WEEKS_PER_MONTH)
    rate = min(rate, MAX_RATE_FRACTION * weight)
    kcal = tdee - rate * (KCAL_PER_KG / 7)
    if kcal < floor:
        kcal = floor
        rate = (tdee - kcal) / (KCAL_PER_KG / 7)

    weeks = to_lose / rate
    total_months = math.ceil(weeks / WEEKS_PER_MONTH - 1e-9)
    return WeightPlan(
        target_kg=target,
        rate_kg_per_week=round(rate, 2),
        kcal=round(kcal / 50) * 50,
        months=total_months,
        requested_months=months,
        extended=total_months > months,
    )
