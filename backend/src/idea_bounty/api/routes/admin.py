from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4
from sqlalchemy.orm import Session

from idea_bounty.api.dependencies import get_current_admin
from idea_bounty.db import get_db_session
from idea_bounty.models import AdminAction, DuplicateVerdict, InputDecision, User
from idea_bounty.schemas import (
    AdminIdeaDetailResponse,
    AdminIdeaListItem,
    AdminIdeaListResponse,
    AdminIdeaProcessRequest,
    AdminSummaryResponse,
    IdeaResponse,
    IdeaSummaryResponse,
)
from idea_bounty.services.admin import (
    AdminIdeaStateError,
    get_admin_idea,
    get_admin_summary,
    list_admin_ideas,
    process_admin_idea,
)
from idea_bounty.services.idea import get_matched_public_id

router = APIRouter(prefix="/admin", tags=["admin"])


def _build_detail(
    db_session: Session,
    public_id: UUID4,
) -> AdminIdeaDetailResponse | None:
    record = get_admin_idea(db_session, public_id)
    if record is None:
        return None
    idea, username = record
    return AdminIdeaDetailResponse(
        username=username,
        idea=IdeaResponse.from_idea(idea, get_matched_public_id(db_session, idea)),
        admin_reason=idea.admin_reason,
        admin_processed_at=idea.admin_processed_at,
    )


@router.get("/summary", response_model=AdminSummaryResponse, summary="查看后台汇总")
def admin_summary(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> AdminSummaryResponse:
    summary = get_admin_summary(db_session)
    return AdminSummaryResponse(
        total_submissions=summary.total_submissions,
        completed_accepts=summary.completed_accepts,
        duplicate_count=summary.duplicate_count,
        estimated_total=float(summary.estimated_total),
        confirmed_payout_count=summary.confirmed_payout_count,
        simulated_payout_total=float(summary.simulated_payout_total),
    )


@router.get("/ideas", response_model=AdminIdeaListResponse, summary="查看全部投稿")
def admin_idea_list(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    db_session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminIdeaListResponse:
    records, total = list_admin_ideas(db_session, limit, offset)
    items: list[AdminIdeaListItem] = []
    for idea, username in records:
        summary = IdeaSummaryResponse.from_idea(idea)
        items.append(
            AdminIdeaListItem(
                public_id=idea.public_id,
                username=username,
                generated_title=summary.generated_title,
                processing_status=summary.processing_status,
                input_decision=(
                    InputDecision(idea.input_decision) if idea.input_decision is not None else None
                ),
                commercial_score=idea.commercial_score,
                final_amount=(float(idea.final_amount) if idea.final_amount is not None else None),
                duplicate_verdict=(
                    DuplicateVerdict(idea.effective_duplicate_verdict)
                    if idea.effective_duplicate_verdict is not None
                    else None
                ),
                admin_action=(
                    AdminAction(idea.admin_action) if idea.admin_action is not None else None
                ),
                created_at=idea.created_at,
            )
        )
    return AdminIdeaListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/ideas/{public_id}",
    response_model=AdminIdeaDetailResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "点子不存在"}},
    summary="查看投稿后台详情",
)
def admin_idea_detail(
    public_id: UUID4,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> AdminIdeaDetailResponse:
    detail = _build_detail(db_session, public_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="点子不存在")
    return detail


@router.post(
    "/ideas/{public_id}/process",
    response_model=AdminIdeaDetailResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "点子不存在"},
        status.HTTP_409_CONFLICT: {"description": "点子当前不可处理或已经处理"},
    },
    summary="最终处理并确认模拟打款",
)
def process_idea(
    public_id: UUID4,
    payload: AdminIdeaProcessRequest,
    current_admin: Annotated[User, Depends(get_current_admin)],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> AdminIdeaDetailResponse:
    try:
        idea = process_admin_idea(
            db_session,
            public_id,
            current_admin.id,
            payload.action,
            payload.amount,
            payload.reason,
        )
    except AdminIdeaStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="点子当前不可处理或已经处理",
        ) from exc
    if idea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="点子不存在")
    detail = _build_detail(db_session, public_id)
    if detail is None:  # pragma: no cover - 同一事务中记录不可能消失
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="点子不存在")
    return detail
