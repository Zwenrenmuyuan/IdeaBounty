from fastapi import APIRouter

from idea_bounty.api.routes.auth import router as auth_router
from idea_bounty.api.routes.health import router as health_router
from idea_bounty.api.routes.idea import router as idea_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(idea_router)
