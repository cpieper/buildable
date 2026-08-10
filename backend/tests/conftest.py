from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base, create_db_engine, get_session
from app.main import create_app


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    database_engine = create_db_engine(database_url)
    Base.metadata.create_all(database_engine)
    try:
        yield database_engine
    finally:
        database_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as database_session:
        yield database_session
        database_session.rollback()


@pytest.fixture
def app(tmp_path: Path, session_factory: sessionmaker[Session]) -> Iterator[FastAPI]:
    settings = Settings(
        data_dir=tmp_path / "unused-data",
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
    )
    application = create_app(settings=settings, session_factory=session_factory)

    def override_get_session() -> Iterator[Session]:
        with session_factory() as database_session:
            yield database_session

    application.dependency_overrides[get_session] = override_get_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
