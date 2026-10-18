# Botlooks

Telegram-бот, который по фото даёт советы нейросети (DeepSeek) по внешности и стилю:
цветотип и палитра (с картинкой), стиль одежды, а при ИМТ ≥ 25 и возрасте ≥ 18 — ориентировочный
план здорового веса. Разборы продаются пакетами за Telegram Stars.

## Стек

Python 3.11, aiogram 3, SQLAlchemy 2 (async) + asyncpg, PostgreSQL 16, Alembic, pydantic v2,
openai-клиент (DeepSeek), Pillow, pytest + testcontainers, ruff, mypy, Docker Compose, GitHub Actions.

## Слои

```
aiogram-хендлеры (bot/) -> сервисы (services/, без aiogram) -> VisionLLM (llm/) и репозитории (db/) -> PostgreSQL
```

Каждый метод репозитория — отдельная короткая транзакция, поэтому транзакция не держится
во время вызова нейросети. Все тексты пользователю — в `src/botlooks/bot/texts.py`.

## Запуск

```bash
cp .env.example .env
# заполнить BOT_TOKEN, ADMIN_ID, DEEPSEEK_API_KEY, POSTGRES_PASSWORD
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

## Цены пакетов

| Пакет     | Разборов | Цена   |
|-----------|----------|--------|
| `pack_1`  | 1        | 15 ⭐  |
| `pack_5`  | 5        | 60 ⭐  |
| `pack_15` | 15       | 150 ⭐ |

Новому пользователю даётся `START_CREDITS=3` разбора; один разбор = 1 кредит.

## Ручная проверка

С реальными ключами:

- [ ] `/start` -> «Стиль» -> профиль -> портрет -> разбор и картинка палитры, баланс 2.
- [ ] «Внешность» с профилем ИМТ ≥ 25 -> вопрос о весе -> «Да» -> 6 мес. -> план с дисклеймером.
- [ ] Фото без лица -> `UNSUITABLE`, баланс не изменился.
- [ ] Альбом из 2 фото -> один разбор.
- [ ] Оплата (тестовое окружение Telegram: test server и отдельный тестовый бот):
  `/buy` -> `pack_5` -> оплата -> баланс +5; `/refund <charge_id>` от админа -> баланс уменьшен.
