from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from idea_bounty.api.dependencies import get_current_user
from idea_bounty.config import Settings, get_settings
from idea_bounty.db import get_db_session
from idea_bounty.models import User
from idea_bounty.schemas import LoginRequest, RegisterRequest, UserResponse
from idea_bounty.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    IssuedSession,
    UsernameAlreadyExistsError,
    login_user,
    register_user,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(
    response: Response,
    issued_session: IssuedSession,
    settings: Settings,
) -> None:
    """将原始 Token 写入仅浏览器可用的 Cookie。"""

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issued_session.token,
        max_age=SESSION_MAX_AGE,
        expires=issued_session.expires_at,
        path="/",
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )


def _delete_session_cookie(response: Response, settings: Settings) -> None:
    """使用与设置时一致的属性删除会话 Cookie。"""

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册普通用户",
)
def register(
    payload: RegisterRequest,
    response: Response,
    db_session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """创建用户并直接建立三天登录会话。"""

    try:
        issued_session = register_user(db_session, payload.username, payload.password)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        ) from exc
    _set_session_cookie(response, issued_session, settings)
    return issued_session.user


@router.post(
    "/login",
    response_model=UserResponse,
    summary="使用用户名和密码登录",
)
def login(
    payload: LoginRequest,
    response: Response,
    db_session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """校验凭据，并用新会话替换旧会话。"""

    issued_session = login_user(db_session, payload.username, payload.password)
    if issued_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    _set_session_cookie(response, issued_session, settings)
    return issued_session.user


@router.get(
    "/me",
    response_model=UserResponse,
    summary="获取当前登录用户",
)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """返回通过当前会话认证的用户。"""

    return current_user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="退出当前登录会话",
)
def logout(
    db_session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> Response:
    """幂等撤销当前会话并清除 Cookie。"""

    if session_token is not None:
        revoke_session(db_session, session_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _delete_session_cookie(response, settings)
    return response
