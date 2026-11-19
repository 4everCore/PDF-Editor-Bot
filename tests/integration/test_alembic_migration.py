from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings


def test_alembic_upgrade_and_downgrade_on_clean_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "migration.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
        sync_engine = create_engine(f"sqlite:///{database}")
        try:
            with sync_engine.connect() as connection:
                names = set(inspect(connection).get_table_names())
        finally:
            sync_engine.dispose()
        assert {
            "users",
            "files",
            "processing_jobs",
            "job_results",
            "saved_workflows",
            "favorites",
            "usage_stats",
            "operation_history",
            "alembic_version",
        } <= names
        command.downgrade(config, "base")
        sync_engine = create_engine(f"sqlite:///{database}")
        try:
            with sync_engine.connect() as connection:
                assert inspect(connection).get_table_names() == ["alembic_version"]
        finally:
            sync_engine.dispose()
    finally:
        get_settings.cache_clear()
