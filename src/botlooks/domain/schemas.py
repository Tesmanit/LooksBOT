import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Mode = Literal["appearance", "style"]
Gender = Literal["male", "female"]
Activity = Literal["low", "medium", "high"]


class Profile(BaseModel):
    gender: Gender
    height_cm: int = Field(ge=100, le=230)
    weight_kg: float = Field(ge=30, le=300)
    age: int = Field(ge=14, le=100)
    activity: Activity


class Unsuitable(BaseModel):
    status: Literal["unsuitable"]
    reason: str


class Recommendations(BaseModel):
    recommendations: list[str]


class Skincare(BaseModel):
    observations: list[str]
    recommendations: list[str]


class AppearanceLook(BaseModel):
    name: str
    haircut: str
    facial_hair: str | None = None
    makeup: str | None = None
    why: str
    image_prompt: str


class AppearanceResult(BaseModel):
    status: Literal["ok"]
    face_shape: str
    looks: list[AppearanceLook] = Field(min_length=2, max_length=2)
    avoid: list[str]
    brows_lashes: Recommendations
    skincare: Skincare
    summary: str


class NamedColor(BaseModel):
    name: str
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class StyleDirection(BaseModel):
    name: str
    description: str
    items: list[str]
    image_prompt: str


class StyleResult(BaseModel):
    status: Literal["ok"]
    color_type: Literal["spring", "summer", "autumn", "winter"]
    color_type_explanation: str
    palette: list[NamedColor] = Field(min_length=6, max_length=8)
    avoid_colors: list[NamedColor] = Field(min_length=3, max_length=4)
    styles: list[StyleDirection] = Field(min_length=4, max_length=4)
    height_tips: list[str]
    summary: str


AnalysisResult = AppearanceResult | StyleResult | Unsuitable


class ResultParseError(Exception):
    pass


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_result(mode: Mode, raw: str, gender: Gender) -> AnalysisResult:
    text = raw.strip()
    fence = _FENCE_RE.match(text)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ResultParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ResultParseError("JSON root is not an object")
    try:
        if data.get("status") == "unsuitable":
            return Unsuitable.model_validate(data)
        if mode == "style":
            return StyleResult.model_validate(data)
        appearance = AppearanceResult.model_validate(data)
    except ValidationError as exc:
        raise ResultParseError(f"schema validation failed: {exc}") from exc
    for look in appearance.looks:
        if gender == "female":
            look.facial_hair = None
        else:
            look.makeup = None
    return appearance
