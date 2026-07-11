from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import UUID4
from sqlalchemy.orm import Session

from idea_bounty.ai import EvaluationProvider
from idea_bounty.api.dependencies import (
    get_current_user,
    get_embedding_provider,
    get_evaluation_provider,
)
from idea_bounty.db import get_db_session
from idea_bounty.embedding import EmbeddingProvider
from idea_bounty.models import User
from idea_bounty.schemas import (
    IdeaCreateRequest,
    IdeaListResponse,
    IdeaResponse,
    IdeaSummaryResponse,
)
from idea_bounty.services.idea import (
    SubmissionKeyConflictError,
    create_or_get_idea,
    get_user_idea,
    list_user_ideas,
)
from idea_bounty.services.pipeline import (
    IdeaRetryLimitError,
    IdeaRetryStateError,
    process_idea_pipeline,
    retry_failed_pipeline,
)

router = APIRouter(prefix="/me/ideas", tags=["ideas"])


@router.post(
    "",
    response_model=IdeaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": IdeaResponse,
            "description": "相同投稿的幂等重放",
        },
        status.HTTP_409_CONFLICT: {"description": "幂等键已用于其他投稿内容"},
    },
    summary="提交点子",
)
def create_idea(
    payload: IdeaCreateRequest,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    evaluation_provider: Annotated[EvaluationProvider, Depends(get_evaluation_provider)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> IdeaResponse:
    """为当前用户创建或返回一条幂等投稿。"""

    try:
        result = create_or_get_idea(
            db_session,
            current_user.id,
            payload.submission_key,
            payload.raw_content,
        )
    except SubmissionKeyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="submission_key 已被其他内容使用",
        ) from exc
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    idea = process_idea_pipeline(
        db_session,
        result.idea,
        evaluation_provider,
        embedding_provider,
    )
    return IdeaResponse.from_idea(idea)


@router.get("", response_model=IdeaListResponse, summary="查看个人投稿列表")
def list_ideas(
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IdeaListResponse:
    """返回当前用户的投稿分页结果。"""

    ideas, total = list_user_ideas(db_session, current_user.id, limit, offset)
    return IdeaListResponse(
        items=[IdeaSummaryResponse.from_idea(idea) for idea in ideas],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{public_id}/retry",
    response_model=IdeaResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "点子不存在"},
        status.HTTP_409_CONFLICT: {"description": "当前状态不可重试或达到重试上限"},
    },
    summary="重试失败的点子处理",
)
def retry_idea_processing(
    public_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    evaluation_provider: Annotated[EvaluationProvider, Depends(get_evaluation_provider)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> IdeaResponse:
    """只允许点子所有者按服务端记录的失败阶段重试。"""

    try:
        idea = retry_failed_pipeline(
            db_session,
            current_user.id,
            public_id,
            evaluation_provider,
            embedding_provider,
        )
    except IdeaRetryLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已达到最大重试次数",
        ) from exc
    except IdeaRetryStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前状态不可重试",
        ) from exc
    if idea is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="点子不存在",
        )
    return IdeaResponse.from_idea(idea)


@router.get("/{public_id}", response_model=IdeaResponse, summary="查看个人投稿详情")
def get_idea(
    public_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> IdeaResponse:
    """只返回属于当前用户的点子详情。"""

    idea = get_user_idea(db_session, current_user.id, public_id)
    if idea is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="点子不存在",
        )
    return IdeaResponse.from_idea(idea)
