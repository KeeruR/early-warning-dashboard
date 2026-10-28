"""
End-to-end tests of the core user journey through the real Streamlit app,
using Streamlit's built-in AppTest (no browser needed). Each test drives the
interface the way an advisor would: log in, read the list, mark a student
reviewed, and check the result came back from the database.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def login(username, password):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.text_input(key="login_username").input(username)
    at.text_input(key="login_password").input(password)
    at.button[0].click().run()
    return at


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_wrong_password_shows_error_and_no_data(db):
    at = login("advisor.a", "not-the-password")
    assert any("incorrect" in e.value for e in at.error)
    assert not at.metric


def test_core_journey_mark_top_student_reviewed(db):
    at = login("advisor.a", "Demo-Advisor-A1")
    assert not at.exception
    assert metric(at, "Students in your caseload") == "70"
    assert metric(at, "Reviewed") == "0"
    first_card = at.markdown[0].value
    assert first_card.startswith("**#1  STU-")
    sid = first_card.split()[1].rstrip("*")

    at.selectbox(key=f"step_{sid}").select("Book a meeting").run()
    at.button(key=f"rev_{sid}").click().run()

    assert metric(at, "Reviewed") == "1"
    assert any("Book a meeting" in s.value for s in at.success)


def test_second_advisor_sees_a_different_caseload(db):
    a = login("advisor.a", "Demo-Advisor-A1")
    b = login("advisor.b", "Demo-Advisor-B2")
    assert a.markdown[0].value != b.markdown[0].value
    assert metric(b, "High priority") != metric(a, "High priority")


def test_every_page_loads_without_errors(db):
    at = login("advisor.a", "Demo-Advisor-A1")
    for page in ["Fairness check", "Import data", "How priorities are calculated", "Privacy"]:
        at.radio(key="nav").set_value(page).run()
        assert not at.exception, page
