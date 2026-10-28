"""Integration tests for the backend service layer against a real SQLite database."""

from datetime import datetime, timedelta, timezone

import pytest

from backend import database, services


def test_login_success_and_failure_is_logged_without_password(db):
    assert services.authenticate("advisor.a", "Demo-Advisor-A1", db)["username"] == "advisor.a"
    assert services.authenticate("advisor.a", "wrong-password", db) is None
    with database.connect(db) as conn:
        details = [r["detail"] for r in conn.execute(
            "SELECT detail FROM audit_log WHERE action = 'login'")]
    assert details == ["success", "failed"]
    with database.connect(db) as conn:
        dump = " ".join(str(tuple(r)) for r in conn.execute("SELECT * FROM audit_log"))
    assert "wrong-password" not in dump


def test_advisor_only_sees_own_caseload(db):
    a = services.get_caseload("advisor.a", db_path=db)
    b = services.get_caseload("advisor.b", db_path=db)
    assert len(a) == 70 and len(b) == 70
    assert {r["advisor_username"] for r in a} == {"advisor.a"}
    assert not {r["student_id"] for r in a} & {r["student_id"] for r in b}


def test_caseload_is_ranked_and_filtered(db):
    rows = services.get_caseload("advisor.a", bands=["High"], db_path=db)
    assert rows and all(r["band"] == "High" for r in rows)
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_review_is_saved_and_survives_restart(db):
    sid = services.get_caseload("advisor.a", bands=["High"], db_path=db)[0]["student_id"]
    services.mark_reviewed("advisor.a", sid, "Book a meeting", db_path=db)
    services.init_app(db)  # simulate restarting the app
    row = next(r for r in services.get_caseload("advisor.a", db_path=db)
               if r["student_id"] == sid)
    assert row["review"]["next_step"] == "Book a meeting"
    assert services.caseload_summary("advisor.a", db)["reviewed"] == 1


def test_advisor_cannot_review_another_advisors_student(db):
    other = services.get_caseload("advisor.b", db_path=db)[0]["student_id"]
    with pytest.raises(PermissionError):
        services.mark_reviewed("advisor.a", other, "Book a meeting", db_path=db)
    with pytest.raises(PermissionError):
        services.get_student_detail("advisor.a", other, db_path=db)


def test_unknown_next_step_is_rejected(db):
    sid = services.get_caseload("advisor.a", db_path=db)[0]["student_id"]
    with pytest.raises(ValueError):
        services.mark_reviewed("advisor.a", sid, "Email the student's parents", db_path=db)


def test_undo_review(db):
    sid = services.get_caseload("advisor.a", db_path=db)[0]["student_id"]
    services.mark_reviewed("advisor.a", sid, "Send check-in email", db_path=db)
    services.undo_review("advisor.a", sid, db_path=db)
    assert services.caseload_summary("advisor.a", db)["reviewed"] == 0
    history = services.get_student_detail("advisor.a", sid, db_path=db)["history"]
    assert len(history) == 1 and history[0]["is_active"] == 0   # kept for the audit trail


def test_reviews_older_than_retention_period_are_deleted(db):
    sid = services.get_caseload("advisor.a", db_path=db)[0]["student_id"]
    services.mark_reviewed("advisor.a", sid, "No action needed", db_path=db)
    future = datetime.now(timezone.utc) + timedelta(days=181)
    assert services.purge_expired_reviews(now=future, db_path=db) == 1
    assert services.caseload_summary("advisor.a", db)["reviewed"] == 0


def test_valid_import_is_saved_and_scored(db, sample_dir):
    data = (sample_dir / "valid_new_students.csv").read_bytes()
    result = services.import_students("advisor.a", data, db_path=db)
    assert result.ok and result.imported == 3
    new = services.get_student_detail("advisor.a", "STU-2001", db_path=db)
    assert (new["score"], new["band"]) == (12, "High")
    assert services.caseload_summary("advisor.a", db)["total"] == 73


def test_import_with_post_checkpoint_column_is_rejected(db, sample_dir):
    data = (sample_dir / "invalid_leakage_column.csv").read_bytes()
    result = services.import_students("advisor.a", data, db_path=db)
    assert not result.ok
    assert "final_exam_mark" in result.errors[0]
    assert services.caseload_summary("advisor.a", db)["total"] == 70  # nothing imported


def test_import_with_bad_values_lists_every_problem(db, sample_dir):
    data = (sample_dir / "invalid_values.csv").read_bytes()
    result = services.import_students("advisor.a", data, db_path=db)
    text = " ".join(result.errors)
    assert not result.ok
    assert "canvas_logins_per_week = 75" in text
    assert "own caseload" in text
    assert "STU-1234" in text and "Domestic or International" in text
    assert services.caseload_summary("advisor.a", db)["total"] == 70


def test_fairness_summary_has_group_sizes_and_two_attributes(db):
    demo = services.fairness_summary("advisor.a", "demographic_group", db_path=db)
    assert demo["table"]["n"].sum() == 70
    year = services.fairness_summary("advisor.a", "year_level", "all", db_path=db)
    assert year["table"]["n"].sum() == 140
    assert set(year["table"]["Group"]) == {"Year 1", "Year 2", "Year 3", "Year 4"}
