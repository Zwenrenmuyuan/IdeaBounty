from fastapi import FastAPI

from idea_bounty.api.router import api_router
from idea_bounty.config import get_settings


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""

    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
    )
    application.include_router(api_router, prefix="/api")
    return application


app = create_app()
