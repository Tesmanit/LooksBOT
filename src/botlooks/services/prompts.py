import json

from botlooks.domain.schemas import AppearanceResult, Mode, Profile, StyleResult

REPAIR_SUFFIX = (
    "Предыдущий ответ не прошёл проверку. "
    "Верни строго один JSON-объект по схеме, без текста вокруг."
)

_GENDER_RU = {"male": "мужчина", "female": "женщина"}

_COMMON = """Ты — профессиональный стилист-консультант. По фото человека ты даёшь советы.

Отвечай строго одним JSON-объектом по схеме ниже, без текста вокруг и без markdown.
Язык ответа — русский.

Схема JSON:
{schema}

Если фото непригодно (нет лица, на фото несколько лиц, плохое освещение или лицо не различимо, \
человек похож на несовершеннолетнего), верни вместо результата JSON такого вида: \
{{"status":"unsuitable","reason":"..."}} — в reason коротко и вежливо объясни причину по-русски.

Тон: доброжелательный и конструктивный. Не ставь оценок привлекательности и не критикуй внешность. \
Говори о том, что подчеркнёт сильные стороны человека.
"""

_APPEARANCE_EXTRA = """
Правила для разбора внешности:
- Советы по коже — общие рекомендации по уходу, без медицинских диагнозов и лечения.
- Поле facial_hair заполняй только для мужчин; для женщин оно должно быть null.
- Поле makeup заполняй только для женщин; для мужчин оно должно быть null.
- Поле brows_lashes для мужчин — пустой список recommendations, если нечего улучшать.
"""

_STYLE_EXTRA = """
Правила для разбора стиля:
- Определи цветотип (color_type), подбери палитру и цвета, которых лучше избегать.
- Цвета задавай в hex-формате #RRGGBB.
- Учитывай рост человека и дай советы в height_tips.
"""


def build_prompts(mode: Mode, profile: Profile) -> tuple[str, str]:
    model = AppearanceResult if mode == "appearance" else StyleResult
    schema = json.dumps(model.model_json_schema(), ensure_ascii=False)
    system = _COMMON.format(schema=schema)
    system += _APPEARANCE_EXTRA if mode == "appearance" else _STYLE_EXTRA

    user = (
        f"Пол: {_GENDER_RU[profile.gender]}. Рост: {profile.height_cm} см. Возраст: {profile.age}."
    )
    if mode == "style":
        user += " Рост обязательно учти в height_tips."
    return system, user
