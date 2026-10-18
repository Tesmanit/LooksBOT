from aiogram import Router

from botlooks.bot.handlers import admin, analysis, billing, errors, history, profile, start


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(errors.router)
    root.include_router(start.router)
    root.include_router(profile.router)
    root.include_router(billing.router)
    root.include_router(history.router)
    root.include_router(admin.router)
    root.include_router(analysis.router)  # last: contains the stray-photo catch-all
    return root
