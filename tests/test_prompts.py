from botlooks.domain.schemas import Profile
from botlooks.services.prompts import REPAIR_SUFFIX, build_prompts

P = Profile(gender="male", height_cm=180, weight_kg=90, age=30, activity="low")
F = Profile(gender="female", height_cm=165, weight_kg=60, age=25, activity="medium")


def test_style_prompt():
    s, u = build_prompts("style", P)
    assert "color_type" in s and "unsuitable" in s and "180" in u
    assert "height_tips" in u


def test_appearance_prompt():
    s, u = build_prompts("appearance", P)
    assert "facial_hair" in s and "makeup" in s and "диагноз" in s and "мужчина" in u


def test_female_user_prompt():
    assert "женщина" in build_prompts("appearance", F)[1]


def test_no_rating_instruction():
    s = build_prompts("appearance", P)[0]
    assert "Не ставь оценок привлекательности" in s
    assert "без медицинских диагнозов" in s
    assert "brows_lashes" in s


def test_schema_embedded_and_russian():
    assert '"face_shape"' in build_prompts("appearance", P)[0]
    assert '"palette"' in build_prompts("style", P)[0]
    assert "русск" in build_prompts("style", P)[0]


def test_repair_suffix():
    assert REPAIR_SUFFIX == (
        "Предыдущий ответ не прошёл проверку. "
        "Верни строго один JSON-объект по схеме, без текста вокруг."
    )


def test_appearance_prompt_picks_two_best():
    system, _ = build_prompts("appearance", P)
    assert "2 лучших" in system and "image_prompt" in system


def test_style_prompt_picks_four_best():
    system, _ = build_prompts("style", P)
    assert "4 лучших" in system and "image_prompt" in system


def test_image_prompt_rules():
    for mode in ("appearance", "style"):
        system, _ = build_prompts(mode, P)
        assert "на английском" in system and "только" in system
        assert "знаменитостей" in system
