"""
SQLAlchemy 2.0 Engine & Session factory.
Supports PostgreSQL in production and SQLite for isolated pytest runs.
"""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def build_engine(db_url: str | None = None):
    url = db_url or settings.sqlalchemy_database_url
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in url:
            return create_engine(
                url,
                connect_args=connect_args,
                poolclass=StaticPool,
                future=True,
            )
        return create_engine(url, connect_args=connect_args, future=True)

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


engine = build_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional SQLAlchemy Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
