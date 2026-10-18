from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from botlooks.config import Settings
from botlooks.db.repositories import UserRepo


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.fixture
def make_message() -> Callable[..., Any]:
    def factory(text: str | None = None, photo: Any = None) -> Any:
        msg = AsyncMock(spec=Message)
        msg.text = text
        msg.photo = photo
        msg.from_user = MagicMock()
        msg.from_user.id = 1
        msg.from_user.username = "tester"
        msg.answer = AsyncMock()
        return msg

    return factory


@pytest.fixture
def make_callback(make_message: Callable[..., Any]) -> Callable[..., Any]:
    def factory() -> Any:
        cb = AsyncMock(spec=CallbackQuery)
        cb.from_user = MagicMock()
        cb.from_user.id = 1
        cb.message = make_message()
        cb.answer = AsyncMock()
        return cb

    return factory


@pytest.fixture
def user_repo_mock() -> Any:
    return AsyncMock(spec=UserRepo)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        bot_token="123:abc",  # type: ignore[arg-type]
        admin_id=1,
        deepseek_api_key="k",  # type: ignore[arg-type]
        database_url="postgresql+asyncpg://x/y",
        _env_file=None,  # type: ignore[call-arg]
    )
