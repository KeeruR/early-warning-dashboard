"""Unit tests for the rule engine (backend/scoring.py)."""

from backend import config
from backend.scoring import priority_sort_key, score_student
from conftest import student


def test_engaged_student_scores_zero_and_low():
    r = score_student(student())
    assert r.score == 0 and r.band == "Low"
    assert r.reason_text == "No early engagement concerns found."


def test_every_indicator_fires_for_maximum_score():
    r = score_student(student(canvas_logins_per_week=0, days_since_last_login=25,
                              submitted_early_assessment=False,
                              registration_days_before_start=-3, forum_posts_count=0))
    assert r.score == config.MAX_SCORE == 12
    assert r.band == "High"
    assert len(r.indicators) == 5          # all reasons shown, not just the first two


def test_absence_is_graded_so_long_absences_rank_higher():
    # Report 2 issue: 12 and 24 days scored the same.
    twelve = score_student(student(days_since_last_login=12)).score
    twenty_four = score_student(student(days_since_last_login=24)).score
    assert (twelve, twenty_four) == (2, 4)


def test_absence_boundaries():
    assert score_student(student(days_since_last_login=4)).score == 0
    assert score_student(student(days_since_last_login=5)).score == 1
    assert score_student(student(days_since_last_login=9)).score == 1
    assert score_student(student(days_since_last_login=10)).score == 2
    assert score_student(student(days_since_last_login=15)).score == 3
    assert score_student(student(days_since_last_login=21)).score == 4


def test_login_boundaries():
    assert score_student(student(canvas_logins_per_week=1)).score == 3
    assert score_student(student(canvas_logins_per_week=2)).score == 1
    assert score_student(student(canvas_logins_per_week=3)).score == 1
    assert score_student(student(canvas_logins_per_week=4)).score == 0


def test_band_boundaries():
    # 3 (not submitted) + 3 (15 days) = 6 -> High
    assert score_student(student(submitted_early_assessment=False,
                                 days_since_last_login=15)).band == "High"
    # 3 + 2 (10 days) = 5 -> Medium
    assert score_student(student(submitted_early_assessment=False,
                                 days_since_last_login=10)).band == "Medium"
    # 3 + 1 (forum) = 4 -> Medium
    assert score_student(student(submitted_early_assessment=False,
                                 forum_posts_count=0)).band == "Medium"
    # 3 -> Low
    assert score_student(student(submitted_early_assessment=False)).band == "Low"


def test_late_submission_only_counts_from_three_days():
    assert score_student(student(early_assessment_days_late=2)).score == 0
    assert score_student(student(early_assessment_days_late=3)).score == 1


def test_csv_style_booleans_are_understood():
    assert score_student(student(submitted_early_assessment="false")).score == 3
    assert score_student(student(submitted_early_assessment="true")).score == 0


def test_reason_lists_highest_points_first_with_points():
    r = score_student(student(days_since_last_login=6, submitted_early_assessment=False))
    assert r.reason_text.startswith("Did not submit the early assessment (+3)")
    assert "(+1)" in r.reason_text


def test_tie_break_uses_absence_then_logins():
    rows = [
        {"student_id": "A", "score": 6, "days_since_last_login": 10, "canvas_logins_per_week": 2},
        {"student_id": "B", "score": 6, "days_since_last_login": 17, "canvas_logins_per_week": 4},
        {"student_id": "C", "score": 8, "days_since_last_login": 3, "canvas_logins_per_week": 0},
        {"student_id": "D", "score": 6, "days_since_last_login": 10, "canvas_logins_per_week": 1},
    ]
    assert [r["student_id"] for r in sorted(rows, key=priority_sort_key)] == ["C", "B", "D", "A"]
