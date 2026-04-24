from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # clear caches
    from app.config import get_settings
    get_settings.cache_clear()
    from app.db import init
    init()
    yield db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-32-bytes-for-session-signing-ok")
    monkeypatch.setenv("APP_ENV", "test")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)
