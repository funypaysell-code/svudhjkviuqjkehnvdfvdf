from aiogram import Router

from . import admin, api_settings, autobuy, balance, countries, interval, monitoring, price, start, stats, tg_accounts


def setup_routers() -> Router:
    router = Router()
    router.include_router(admin.router)
    router.include_router(start.router)
    router.include_router(api_settings.router)
    router.include_router(autobuy.router)
    router.include_router(monitoring.router)
    router.include_router(countries.router)
    router.include_router(price.router)
    router.include_router(interval.router)
    router.include_router(balance.router)
    router.include_router(stats.router)
    router.include_router(tg_accounts.router)
    return router
