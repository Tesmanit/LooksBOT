import json

import pytest
from pydantic import ValidationError

from botlooks.domain.schemas import (
    AppearanceResult,
    Profile,
    ResultParseError,
    StyleResult,
    Unsuitable,
    parse_result,
)


def appearance_json() -> dict:
    return {
        "status": "ok",
        "face_shape": "овальное",
        "haircut": {"recommended": ["a"], "avoid": ["b"], "comment": "c"},
        "facial_hair": {"recommendations": ["борода"]},
        "brows_lashes": {"recommendations": ["брови"]},
        "makeup": {"recommendations": ["тон"]},
        "skincare": {"observations": ["o"], "recommendations": ["r"]},
        "summary": "итог",
    }


def style_json() -> dict:
    def color(i: int) -> dict:
        return {"name": f"Цвет {i}", "hex": f"#C8553{i}"}

    return {
        "status": "ok",
        "color_type": "autumn",
        "color_type_explanation": "почему",
        "palette": [color(i) for i in range(6)],
        "avoid_colors": [color(i) for i in range(3)],
        "styles": [
            {"name": "Smart casual", "description": "d", "items": ["i"]},
            {"name": "Classic", "description": "d", "items": ["i"]},
        ],
        "height_tips": ["t"],
        "summary": "итог",
    }


def test_parse_appearance_ok():
    r = parse_result("appearance", json.dumps(appearance_json()), "male")
    assert isinstance(r, AppearanceResult)
    assert r.makeup is None
    assert r.facial_hair is not None


def test_parse_female_drops_facial_hair():
    r = parse_result("appearance", json.dumps(appearance_json()), "female")
    assert isinstance(r, AppearanceResult)
    assert r.facial_hair is None
    assert r.makeup is not None


def test_parse_strips_code_fence():
    raw = "```json\n" + json.dumps(style_json()) + "\n```"
    assert isinstance(parse_result("style", raw, "male"), StyleResult)


def test_parse_unsuitable():
    r = parse_result("style", '{"status":"unsuitable","reason":"нет лица"}', "male")
    assert r == Unsuitable(status="unsuitable", reason="нет лица")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(palette=d["palette"][:5]),
        lambda d: d.update(color_type="spring-ish"),
        lambda d: d["palette"][0].update(hex="red"),
        lambda d: d.update(avoid_colors=d["avoid_colors"][:2]),
        lambda d: d.update(styles=d["styles"][:1]),
    ],
)
def test_parse_style_constraints(mutate):
    d = style_json()
    mutate(d)
    with pytest.raises(ResultParseError):
        parse_result("style", json.dumps(d), "male")


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", ""])
def test_parse_garbage(raw):
    with pytest.raises(ResultParseError):
        parse_result("style", raw, "male")


@pytest.mark.parametrize("height", [99, 231])
def test_profile_height_bounds(height):
    with pytest.raises(ValidationError):
        Profile(gender="male", height_cm=height, weight_kg=70, age=30, activity="low")


@pytest.mark.parametrize("weight", [29.9, 300.1])
def test_profile_weight_bounds(weight):
    with pytest.raises(ValidationError):
        Profile(gender="male", height_cm=180, weight_kg=weight, age=30, activity="low")
