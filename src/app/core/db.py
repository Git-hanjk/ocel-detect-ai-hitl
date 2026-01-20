from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .models import Base

DEFAULT_DB_PATH = "data/derived/serving.sqlite"


def resolve_db_path(override: str | None = None) -> str:
    return override or os.environ.get("SERVING_DB_PATH") or DEFAULT_DB_PATH


def get_engine(db_path: str | None = None):
    path = resolve_db_path(db_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(candidates)")).fetchall()
        cols = {row[1] for row in rows}
        if "run_id" not in cols:
            conn.execute(text("ALTER TABLE candidates ADD COLUMN run_id STRING"))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_candidates_run_id ON candidates (run_id)")
            )
        if "severity" not in cols:
            conn.execute(text("ALTER TABLE candidates ADD COLUMN severity REAL"))
        if "priority_score" not in cols:
            conn.execute(text("ALTER TABLE candidates ADD COLUMN priority_score REAL"))
        rows = conn.execute(text("PRAGMA table_info(llm_results)")).fetchall()
        llm_cols = {row[1] for row in rows}
        if "provider" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_results ADD COLUMN provider STRING"))
        if "schema_version" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_results ADD COLUMN schema_version STRING"))
        if "prompt_tokens" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_results ADD COLUMN prompt_tokens INTEGER"))
        if "completion_tokens" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_results ADD COLUMN completion_tokens INTEGER"))
        if "total_tokens" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_results ADD COLUMN total_tokens INTEGER"))


@contextmanager
def session_scope(engine):
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
