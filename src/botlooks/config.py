from dataclasses import dataclass

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: SecretStr
    admin_id: int
    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_json_mode: bool = True
    gemini_api_key: SecretStr
    gemini_image_model: str = "gemini-2.5-flash-image"
    database_url: str
    start_credits: int = 3
    log_level: str = "INFO"


@dataclass(frozen=True)
class Pack:
    id: str
    credits: int
    stars: int


PACKS: dict[str, Pack] = {
    p.id: p
    for p in (
        Pack("pack_1", 1, 15),
        Pack("pack_5", 5, 60),
        Pack("pack_15", 15, 150),
    )
}
