from pathlib import Path

import pytest
from pydantic import ValidationError

from botlooks.config import PACKS, Settings


def test_settings_reads_env(monkeypatch):
    for k, v in {
        "BOT_TOKEN": "SECRET-TOKEN-123",
        "ADMIN_ID": "42",
        "DEEPSEEK_API_KEY": "k",
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)
    assert s.admin_id == 42 and s.start_credits == 3 and s.deepseek_model == "deepseek-flash"
    assert s.deepseek_json_mode is True
    assert "SECRET-TOKEN-123" not in repr(s)


def test_settings_missing_required(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_packs():
    assert [(p.id, p.credits, p.stars) for p in PACKS.values()] == [
        ("pack_1", 1, 15),
        ("pack_5", 5, 60),
        ("pack_15", 15, 150),
    ]


def test_env_example_explains_database_url():
    lines = (Path(__file__).parent.parent / ".env.example").read_text("utf-8").splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("DATABASE_URL="))
    comment = lines[idx - 1]
    assert comment.startswith("#")
    assert "compose" in comment.lower() and "literal" in comment.lower()
