from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from idea_bounty.config import Settings, get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """API 进程可用时返回的响应。"""

    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse, summary="检查 API 健康状态")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """报告当前进程状态，不检查后续接入的外部依赖。"""

    return HealthResponse(status="ok", service=settings.app_name)
