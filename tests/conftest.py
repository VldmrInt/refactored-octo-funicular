import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.auth import create_jwt
from app.database import Base, get_db
from app.models import User

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(reset_db) -> Session:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db) -> TestClient:
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db

    # asyncio.create_task is called from sync endpoints — there's no running
    # event loop in the test thread, so it raises RuntimeError.
    # Patch it to close the coroutine immediately (fire-and-forget skip).
    with patch("asyncio.create_task", lambda coro: coro.close()):
        yield TestClient(app)

    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user(
    db: Session,
    telegram_id: int,
    role: str = "author",
    username: str = "user",
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=f"User {telegram_id}",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    token = create_jwt(user.id, user.telegram_id, user.role)
    return {"Authorization": f"Bearer {token}"}


TICKET_PAYLOAD = {
    "title": "Тестовое обращение",
    "description": "Подробное описание проблемы",
    "is_urgent": False,
}
