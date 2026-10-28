import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import services  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh, seeded database in a temporary folder for each test."""
    path = tmp_path / "test.db"
    monkeypatch.setenv("EWD_DB_PATH", str(path))
    services.init_app(path)
    return path


@pytest.fixture
def sample_dir():
    return ROOT / "sample_data"


def student(**overrides):
    """An engaged student (score 0) that tests can change one field at a time."""
    base = {
        "student_id": "STU-9999", "advisor_username": "advisor.a", "course": "STATS 108",
        "year_level": 1, "demographic_group": "Domestic",
        "registration_days_before_start": 14, "canvas_logins_per_week": 6,
        "days_since_last_login": 1, "submitted_early_assessment": True,
        "early_assessment_days_late": 0, "forum_posts_count": 3,
    }
    base.update(overrides)
    return base
