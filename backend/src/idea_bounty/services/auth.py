from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from pwdlib import PasswordHash
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idea_bounty.models import User, UserRole, UserSession, UserStatus

SESSION_COOKIE_NAME = "idea_bounty_session"
SESSION_TTL = timedelta(days=3)
SESSION_MAX_AGE = int(SESSION_TTL.total_seconds())

PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASH.hash("idea-bounty-dummy-password")


class UsernameAlreadyExistsError(Exception):
    """用户名唯一约束冲突。"""


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """一次成功认证产生的用户、Token 和有效期。"""

    user: User
    token: str
    expires_at: datetime


def _new_session_token() -> tuple[str, str]:
    """生成只返回给浏览器的 Token 及其数据库哈希。"""

    token = token_urlsafe(32)
    return token, _hash_session_token(token)


def _hash_session_token(token: str) -> str:
    """将任意 Session Token 转为固定长度哈希。"""

    return sha256(token.encode()).hexdigest()


def _replace_session(user: User, now: datetime) -> tuple[str, datetime]:
    """创建或覆盖用户唯一的登录会话。"""

    token, token_hash = _new_session_token()
    expires_at = now + SESSION_TTL
    if user.session is None:
        user.session = UserSession(
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
        )
    else:
        user.session.token_hash = token_hash
        user.session.expires_at = expires_at
        user.session.revoked_at = None
        user.session.created_at = now
    return token, expires_at


def register_user(db_session: Session, username: str, password: str) -> IssuedSession:
    """在一个事务中创建普通用户并建立唯一会话。"""

    user = User(
        username=username,
        password_hash=PASSWORD_HASH.hash(password),
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    try:
        db_session.flush()
    except IntegrityError as exc:
        db_session.rollback()
        raise UsernameAlreadyExistsError from exc

    now = datetime.now(UTC)
    token, expires_at = _replace_session(user, now)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    return IssuedSession(user=user, token=token, expires_at=expires_at)


def login_user(db_session: Session, username: str, password: str) -> IssuedSession | None:
    """验证凭据，并让本次登录替换该用户的旧会话。"""

    user = db_session.scalar(select(User).where(User.username == username).with_for_update())
    if user is None:
        PASSWORD_HASH.verify(password, DUMMY_PASSWORD_HASH)
        return None

    valid_password, updated_hash = PASSWORD_HASH.verify_and_update(
        password,
        user.password_hash,
    )
    if not valid_password or user.status != UserStatus.ACTIVE.value:
        return None

    if updated_hash is not None:
        user.password_hash = updated_hash
    now = datetime.now(UTC)
    token, expires_at = _replace_session(user, now)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    return IssuedSession(user=user, token=token, expires_at=expires_at)


def get_user_by_session_token(db_session: Session, token: str) -> User | None:
    """只返回具有有效会话的启用用户。"""

    token_hash = _hash_session_token(token)
    return db_session.scalar(
        select(User)
        .join(UserSession)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
            User.status == UserStatus.ACTIVE.value,
        )
    )


def revoke_session(db_session: Session, token: str) -> None:
    """撤销匹配会话；Token 不存在时保持幂等。"""

    db_session.execute(
        update(UserSession)
        .where(UserSession.token_hash == _hash_session_token(token))
        .values(revoked_at=func.now())
    )
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
