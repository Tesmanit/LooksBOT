import asyncio
from typing import cast

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine

from botlooks.bot.handlers import build_router
from botlooks.config import Settings
from botlooks.db.repositories import AnalysisRepo, PaymentRepo, UserRepo
from botlooks.db.session import make_sessionmaker
from botlooks.llm.deepseek import DeepSeekVisionLLM
from botlooks.llm.gemini import GeminiImageGenerator
from botlooks.log import setup_logging
from botlooks.services.analysis import AnalysisService
from botlooks.services.billing import BillingService
from botlooks.services.looks import LooksService

COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="history", description="История разборов"),
    BotCommand(command="balance", description="Баланс"),
    BotCommand(command="buy", description="Купить разборы"),
    BotCommand(command="paysupport", description="Поддержка по оплате"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    sm = make_sessionmaker(settings.database_url)
    engine = cast(AsyncEngine, sm.kw["bind"])
    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        user_repo = UserRepo(sm)
        analysis_repo = AnalysisRepo(sm)
        billing = BillingService(user_repo, PaymentRepo(sm))
        llm = DeepSeekVisionLLM(
            AsyncOpenAI(
                api_key=settings.deepseek_api_key.get_secret_value(),
                base_url=settings.deepseek_base_url,
                timeout=60,
                max_retries=0,
            ),
            settings.deepseek_model,
            json_mode=settings.deepseek_json_mode,
        )
        analysis = AnalysisService(user_repo, analysis_repo, billing, llm)
        images = GeminiImageGenerator(
            genai.Client(
                api_key=settings.gemini_api_key.get_secret_value(),
                # our generator retries itself; keep the SDK from multiplying attempts
                http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
            ),
            settings.gemini_image_model,
        )
        looks = LooksService(images, billing)
        dp = Dispatcher(
            storage=MemoryStorage(),
            settings=settings,
            user_repo=user_repo,
            analysis_repo=analysis_repo,
            billing=billing,
            analysis=analysis,
            looks=looks,
        )
        dp.include_router(build_router())
        await bot.set_my_commands(COMMANDS)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
