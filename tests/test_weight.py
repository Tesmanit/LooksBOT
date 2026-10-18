from typing import Any

from botlooks.domain.schemas import Profile
from botlooks.services.weight import build_plan, plan_available, target_weight


def make_male(**kw: Any) -> Profile:
    base: dict[str, Any] = {
        "gender": "male",
        "height_cm": 180,
        "weight_kg": 100,
        "age": 30,
        "activity": "medium",
    }
    return Profile(**{**base, **kw})


def make_female(**kw: Any) -> Profile:
    base: dict[str, Any] = {
        "gender": "female",
        "height_cm": 160,
        "weight_kg": 70,
        "age": 60,
        "activity": "low",
    }
    return Profile(**{**base, **kw})


def test_target_weight():
    assert target_weight(180) == 81.0
    assert target_weight(160) == 64.0


def test_available():
    assert plan_available(make_male())
    assert not plan_available(make_male(weight_kg=75))
    assert not plan_available(make_male(age=17))


def test_plan_within_term():
    p = build_plan(make_male(), 6)
    assert p is not None
    assert (p.target_kg, p.kcal, p.months, p.extended) == (81.0, 2250, 6, False)


def test_plan_rate_capped():
    p = build_plan(make_male(), 3)
    assert p is not None
    assert p.rate_kg_per_week == 0.75
    assert p.kcal == 2250
    assert p.months == 6
    assert p.extended


def test_plan_kcal_floor_female():
    p = build_plan(make_female(), 3)
    assert p is not None
    assert p.kcal == 1200
    assert p.rate_kg_per_week == 0.26
    assert p.months == 6
    assert p.extended


def test_plan_impossible():
    assert build_plan(make_female(height_cm=150, weight_kg=60, age=80), 3) is None


def test_to_dict():
    p = build_plan(make_male(), 6)
    assert p is not None
    assert p.to_dict()["kcal"] == 2250
