from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import UUID4, ValidationError
from sqlalchemy.orm import Session

from idea_bounty.api.dependencies import get_current_user
from idea_bounty.db import get_db_session
from idea_bounty.models import User
from idea_bounty.schemas import PublicIdeaSummary
from idea_bounty.services.idea import get_public_idea

router = APIRouter(prefix="/ideas", tags=["ideas"])


@router.get(
    "/{public_id}/summary",
    response_model=PublicIdeaSummary,
    responses={status.HTTP_404_NOT_FOUND: {"description": "点子不存在或不可公开"}},
    summary="查看点子脱敏摘要",
)
def get_idea_summary(
    public_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> PublicIdeaSummary:
    """允许已登录用户按随机公开 ID 查看白名单摘要。"""

    del current_user
    idea = get_public_idea(db_session, public_id)
    if idea is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="点子不存在",
        )
    try:
        return PublicIdeaSummary.from_idea(idea)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="点子不存在",
        ) from exc
