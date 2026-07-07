from pathlib import Path

import pytest

from app.config import BACKEND_DIR, _default_database_url


def test_default_database_url_is_stable_and_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url = _default_database_url()

    assert url.startswith("sqlite:///")
    db_path = Path(url.removeprefix("sqlite:///"))
    assert db_path.is_absolute()
    assert db_path == BACKEND_DIR / "clinicflow.db"
