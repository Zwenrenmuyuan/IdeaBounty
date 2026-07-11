from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from idea_bounty.db import get_db_session
from idea_bounty.models import User, UserRole
from idea_bounty.services.auth import SESSION_COOKIE_NAME, get_user_by_session_token


def get_current_user(
    db_session: Annotated[Session, Depends(get_db_session)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    """从 Cookie 解析当前已登录用户。"""

    if session_token is not None:
        user = get_user_by_session_token(db_session, session_token)
        if user is not None:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或会话已失效",
    )


def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """只允许管理员访问后台接口。"""

    if current_user.role == UserRole.ADMIN.value:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="需要管理员权限",
    )
