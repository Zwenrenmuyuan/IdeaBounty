from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from idea_bounty.config import get_settings
from idea_bounty.db import get_db_session
from idea_bounty.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://idea_bounty:idea_bounty_dev@localhost:5432/idea_bounty_test"
)


def _get_test_database_url() -> str:
    """读取测试数据库地址，并拒绝任何非测试数据库。"""

    database_url = os.getenv("IDEA_BOUNTY_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database_name = make_url(database_url).database
    if database_name is None or not database_name.endswith("_test"):
        raise RuntimeError("测试数据库名称必须以 _test 结尾")
    return database_url


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """在独立测试数据库执行迁移往返，并提供测试 Engine。"""

    test_database_url = _get_test_database_url()
    original_database_url = os.environ.get("IDEA_BOUNTY_DATABASE_URL")
    os.environ["IDEA_BOUNTY_DATABASE_URL"] = test_database_url
    get_settings.cache_clear()

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    engine = create_engine(test_database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        if original_database_url is None:
            os.environ.pop("IDEA_BOUNTY_DATABASE_URL", None)
        else:
            os.environ["IDEA_BOUNTY_DATABASE_URL"] = original_database_url
        get_settings.cache_clear()


@pytest.fixture
def clean_database(test_engine: Engine) -> Generator[None, None, None]:
    """在每个数据库测试前后清空认证表。"""

    truncate_statement = text("TRUNCATE TABLE ideas, sessions, users RESTART IDENTITY CASCADE")
    with test_engine.begin() as connection:
        connection.execute(truncate_statement)

    yield

    with test_engine.begin() as connection:
        connection.execute(truncate_statement)


@pytest.fixture
def db_session(test_engine: Engine, clean_database: None) -> Generator[Session, None, None]:
    """为单个测试提供直接访问测试数据库的会话。"""

    with Session(test_engine, expire_on_commit=False) as session:
        yield session
        session.rollback()


@pytest.fixture
def app(test_engine: Engine, clean_database: None) -> FastAPI:
    """创建将数据库依赖指向测试库的应用。"""

    application = create_app()

    def override_get_db_session() -> Generator[Session, None, None]:
        with Session(
            test_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as session:
            yield session

    application.dependency_overrides[get_db_session] = override_get_db_session
    return application


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    """提供保存 Cookie 的认证 API 测试客户端。"""

    with TestClient(app) as test_client:
        yield test_client
