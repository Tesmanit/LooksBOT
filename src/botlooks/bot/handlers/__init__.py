from aiogram import Router

from botlooks.bot.handlers import analysis, profile, start


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(profile.router)
    root.include_router(analysis.router)
    return root
