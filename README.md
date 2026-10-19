# Botlooks

Telegram-бот, который по фото даёт советы нейросети (DeepSeek) по внешности и стилю:
2 лучших образа (стрижка, борода/макияж) или 4 лучших стиля одежды, цветотип и палитра
(с картинкой), а при ИМТ ≥ 25 и возрасте ≥ 18 — ориентировочный план здорового веса.
К каждому разбору Gemini рисует по фото пользователя один реалистичный коллаж:
«2 в 1» для внешности и «4 в 1» для стиля. Разборы продаются пакетами за Telegram Stars.

## Стек

Python 3.11, aiogram 3, SQLAlchemy 2 (async) + asyncpg, PostgreSQL 16, Alembic, pydantic v2,
openai-клиент (DeepSeek), google-genai (Gemini), Pillow, pytest + testcontainers, ruff, mypy, Docker Compose, GitHub Actions.

## Слои

```
aiogram-хендлеры (bot/) -> сервисы (services/, без aiogram) -> VisionLLM / ImageGenerator (llm/) и репозитории (db/) -> PostgreSQL
```

Каждый метод репозитория — отдельная короткая транзакция, поэтому транзакция не держится
во время вызова нейросети. Все тексты пользователю — в `src/botlooks/bot/texts.py`.

## Запуск

```bash
cp .env.example .env
# заполнить BOT_TOKEN, ADMIN_ID, DEEPSEEK_API_KEY, GEMINI_API_KEY, POSTGRES_PASSWORD
docker compose up --build
```

Контейнер бота сам применяет миграции (`alembic upgrade head`) и запускает polling.
`DATABASE_URL` для контейнера собирается в `docker-compose.yml` из `POSTGRES_*`.

## Тесты

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Linux/macOS: .venv/bin/python
python -m pytest
python -m ruff check . && python -m ruff format --check . && python -m mypy src
```

Интеграционные тесты поднимают `postgres:16` через testcontainers — нужен запущенный Docker.

## Смена провайдера нейросети

Используется OpenAI-совместимый API. Поменяйте в `.env` `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`,
`DEEPSEEK_API_KEY` (модель должна принимать изображения). Если провайдер не поддерживает
`response_format=json_object`, поставьте `DEEPSEEK_JSON_MODE=false`. Для другого протокола
реализуйте интерфейс `VisionLLM` (`src/botlooks/llm/base.py`).

## Картинки-коллажи

Коллаж рисует Gemini одним запросом на разбор (`GEMINI_API_KEY`, модель — `GEMINI_IMAGE_MODEL`,
по умолчанию `gemini-2.5-flash-image`). Номера образов на картинке не рисуются — соответствие
панелей образам даётся в подписи к фото. Если картинка не получилась, кредит за разбор
возвращается, текст остаётся. Другой провайдер — реализуйте `ImageGenerator`
(`src/botlooks/llm/base.py`). Фото пользователя уходит и в DeepSeek, и в Gemini.

Себестоимость (оценка на 2026-10): ≈ $0.04–0.07 за разбор при выплате ≈ $0.013 за ⭐.
При переходе на более дорогую модель или 2K-разрешение пересмотрите `PACKS` в `config.py`.

## Цены пакетов

| Пакет     | Разборов | Цена   |
|-----------|----------|--------|
| `pack_1`  | 1        | 15 ⭐  |
| `pack_5`  | 5        | 60 ⭐  |
| `pack_15` | 15       | 150 ⭐ |

Новому пользователю даётся `START_CREDITS=3` разбора; один разбор = 1 кредит.

## Ручная проверка

С реальными ключами:

- [ ] `/start` -> «Стиль» -> профиль -> портрет -> разбор (4 стиля), коллаж 2×2 с легендой,
  картинка палитры, баланс 2.
- [ ] «Внешность» -> портрет -> 2 образа и коллаж 1×2; лицо узнаётся, порядок панелей = номерам.
- [ ] «Внешность» с профилем ИМТ ≥ 25 -> вопрос о весе -> «Да» -> 6 мес. -> план с дисклеймером.
- [ ] Фото без лица -> `UNSUITABLE`, баланс не изменился.
- [ ] Альбом из 2 фото -> один разбор.
- [ ] Оплата (тестовое окружение Telegram: test server и отдельный тестовый бот):
  `/buy` -> `pack_5` -> оплата -> баланс +5; `/refund <charge_id>` от админа -> баланс уменьшен.
