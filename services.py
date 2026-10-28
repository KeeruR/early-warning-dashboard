"""
Backend service layer: the only module the Streamlit frontend calls.

Every user action (log in, filter, open a student, mark reviewed, undo,
check fairness, import data) goes through a function here, which reads or
writes the SQLite database and returns plain Python data for display.
Access control is enforced here, not in the UI: an advisor can only read
or change students in their own caseload.
"""

import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

from . import auth, config, database
from .data_generator import generate_dataset
from .scoring import priority_sort_key, score_student


def _now(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _log(conn, username, action, detail=""):
    conn.execute(
        "INSERT INTO audit_log (logged_at, username, action, detail) VALUES (?, ?, ?, ?)",
        (_now(), username, action, detail))


# ── Setup ─────────────────────────────────────────────────────────────────
def init_app(db_path=None) -> None:
    """Create tables, seed demo users and data if empty, score, purge old reviews.
    Safe to call on every app start."""
    database.create_schema(db_path)
    with database.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for u in auth.DEMO_USERS:
                pw_hash, salt = auth.hash_password(u["password"])
                conn.execute(
                    "INSERT INTO users (username, display_name, role, password_hash, salt) "
                    "VALUES (?, ?, 'advisor', ?, ?)",
                    (u["username"], u["display_name"], pw_hash, salt))
        if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            df = generate_dataset()
            # Keep a CSV copy of the seed data next to the database for inspection.
            df.to_csv(database.resolve_path(db_path).parent / config.SEED_CSV_PATH.name,
                      index=False)
            _upsert_students(conn, df)
            _log(conn, "system", "seed", f"{len(df)} synthetic students loaded")
    rescore_all(db_path)
    purge_expired_reviews(db_path=db_path)


def _upsert_students(conn, df: pd.DataFrame) -> int:
    stamp = _now()
    for r in df.to_dict("records"):
        conn.execute(
            """INSERT INTO students (student_id, advisor_username, course, year_level,
                   demographic_group, registration_days_before_start, canvas_logins_per_week,
                   days_since_last_login, submitted_early_assessment,
                   early_assessment_days_late, forum_posts_count, loaded_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(student_id) DO UPDATE SET
                   course=excluded.course, year_level=excluded.year_level,
                   demographic_group=excluded.demographic_group,
                   registration_days_before_start=excluded.registration_days_before_start,
                   canvas_logins_per_week=excluded.canvas_logins_per_week,
                   days_since_last_login=excluded.days_since_last_login,
                   submitted_early_assessment=excluded.submitted_early_assessment,
                   early_assessment_days_late=excluded.early_assessment_days_late,
                   forum_posts_count=excluded.forum_posts_count,
                   loaded_at=excluded.loaded_at""",
            (r["student_id"], r["advisor_username"], r["course"], int(r["year_level"]),
             r["demographic_group"], int(r["registration_days_before_start"]),
             int(r["canvas_logins_per_week"]), int(r["days_since_last_login"]),
             1 if _to_bool(r["submitted_early_assessment"]) else 0,
             int(r["early_assessment_days_late"]), int(r["forum_posts_count"]), stamp))
    return len(df)


def rescore_all(db_path=None) -> int:
    """Run the scoring engine over every stored student and save the results."""
    with database.connect(db_path) as conn:
        students = [dict(r) for r in conn.execute("SELECT * FROM students")]
        stamp = _now()
        for s in students:
            result = score_student(s)
            reasons = [{"code": i.code, "points": i.points, "reason": i.reason}
                       for i in result.indicators]
            conn.execute(
                """INSERT INTO priority_scores (student_id, score, band, reasons_json,
                       rule_version, scored_at) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(student_id) DO UPDATE SET score=excluded.score,
                       band=excluded.band, reasons_json=excluded.reasons_json,
                       rule_version=excluded.rule_version, scored_at=excluded.scored_at""",
                (s["student_id"], result.score, result.band, json.dumps(reasons),
                 config.RULE_VERSION, stamp))
    return len(students)


# ── Authentication ────────────────────────────────────────────────────────
def authenticate(username: str, password: str, db_path=None) -> Optional[dict]:
    username = (username or "").strip().lower()
    with database.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and auth.verify_password(password or "", row["password_hash"], row["salt"]):
            _log(conn, username, "login", "success")
            return {"username": row["username"], "display_name": row["display_name"],
                    "role": row["role"]}
        _log(conn, username or "(blank)", "login", "failed")  # password never logged
    return None


# ── Caseload ──────────────────────────────────────────────────────────────
def _active_review(conn, student_id):
    row = conn.execute(
        "SELECT next_step, reviewed_at FROM reviews WHERE student_id = ? AND is_active = 1 "
        "ORDER BY review_id DESC LIMIT 1", (student_id,)).fetchone()
    return dict(row) if row else None


def get_caseload(username: str, bands=None, courses=None, groups=None,
                 review_status: str = "All", db_path=None) -> List[dict]:
    """Return the advisor's own students, filtered, scored and ranked."""
    sql = """SELECT s.*, p.score, p.band, p.reasons_json, p.rule_version, p.scored_at
             FROM students s JOIN priority_scores p ON p.student_id = s.student_id
             WHERE s.advisor_username = ?"""
    params: list = [username]
    for column, values in (("p.band", bands), ("s.course", courses),
                           ("s.demographic_group", groups)):
        if values:
            sql += f" AND {column} IN ({','.join('?' * len(values))})"
            params.extend(values)
    with database.connect(db_path) as conn:
        rows = [dict(r) for r in conn.execute(sql, params)]
        for r in rows:
            r["reasons"] = json.loads(r.pop("reasons_json"))
            r["review"] = _active_review(conn, r["student_id"])
    if review_status == "Not reviewed":
        rows = [r for r in rows if r["review"] is None]
    elif review_status == "Reviewed":
        rows = [r for r in rows if r["review"] is not None]
    rows.sort(key=priority_sort_key)
    for rank, r in enumerate(rows, start=1):
        r["rank"] = rank
    return rows


def caseload_summary(username: str, db_path=None) -> dict:
    with database.connect(db_path) as conn:
        counts = dict(conn.execute(
            """SELECT p.band, COUNT(*) FROM students s JOIN priority_scores p
               ON p.student_id = s.student_id WHERE s.advisor_username = ?
               GROUP BY p.band""", (username,)).fetchall())
        reviewed = conn.execute(
            """SELECT COUNT(DISTINCT r.student_id) FROM reviews r
               JOIN students s ON s.student_id = r.student_id
               WHERE s.advisor_username = ? AND r.is_active = 1""", (username,)).fetchone()[0]
        courses = [r[0] for r in conn.execute(
            "SELECT DISTINCT course FROM students WHERE advisor_username = ? ORDER BY course",
            (username,))]
    return {"total": sum(counts.values()), "High": counts.get("High", 0),
            "Medium": counts.get("Medium", 0), "Low": counts.get("Low", 0),
            "reviewed": reviewed, "courses": courses}


def _check_owner(conn, username, student_id):
    row = conn.execute("SELECT advisor_username FROM students WHERE student_id = ?",
                       (student_id,)).fetchone()
    if row is None:
        raise KeyError(f"Student {student_id} not found")
    if row["advisor_username"] != username:
        _log(conn, username, "access_denied", student_id)
        raise PermissionError(f"{student_id} is not in your caseload")


def get_student_detail(username: str, student_id: str, db_path=None) -> dict:
    with database.connect(db_path) as conn:
        _check_owner(conn, username, student_id)
        row = dict(conn.execute(
            """SELECT s.*, p.score, p.band, p.reasons_json, p.rule_version, p.scored_at
               FROM students s JOIN priority_scores p ON p.student_id = s.student_id
               WHERE s.student_id = ?""", (student_id,)).fetchone())
        row["reasons"] = json.loads(row.pop("reasons_json"))
        row["history"] = [dict(r) for r in conn.execute(
            "SELECT next_step, reviewed_at, is_active FROM reviews WHERE student_id = ? "
            "ORDER BY review_id DESC", (student_id,))]
    return row


# ── Reviews (human in the loop) ───────────────────────────────────────────
def mark_reviewed(username: str, student_id: str, next_step: str, db_path=None) -> dict:
    """Record that the advisor has examined the case and their own chosen next step.
    This never contacts the student or triggers any action."""
    if next_step not in config.NEXT_STEP_OPTIONS:
        raise ValueError(f"Unknown next step: {next_step}")
    with database.connect(db_path) as conn:
        _check_owner(conn, username, student_id)
        conn.execute("UPDATE reviews SET is_active = 0 WHERE student_id = ? AND is_active = 1",
                     (student_id,))
        stamp = _now()
        conn.execute(
            "INSERT INTO reviews (student_id, advisor_username, next_step, reviewed_at) "
            "VALUES (?,?,?,?)", (student_id, username, next_step, stamp))
        _log(conn, username, "mark_reviewed", f"{student_id}: {next_step}")
    return {"student_id": student_id, "next_step": next_step, "reviewed_at": stamp}


def undo_review(username: str, student_id: str, db_path=None) -> None:
    with database.connect(db_path) as conn:
        _check_owner(conn, username, student_id)
        conn.execute("UPDATE reviews SET is_active = 0 WHERE student_id = ? AND is_active = 1",
                     (student_id,))
        _log(conn, username, "undo_review", student_id)


def purge_expired_reviews(now: Optional[datetime] = None, db_path=None) -> int:
    """IPP 9: delete review records older than the retention period."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=config.REVIEW_RETENTION_DAYS)
    with database.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM reviews WHERE reviewed_at < ?",
                           (cutoff.isoformat(timespec="seconds"),))
        if cur.rowcount:
            _log(conn, "system", "retention_purge", f"{cur.rowcount} review(s) deleted")
        return cur.rowcount


# ── Fairness check ────────────────────────────────────────────────────────
def fairness_summary(username: str, attribute: str, scope: str = "mine",
                     db_path=None) -> dict:
    """Group sizes, counts and percentages per support-priority band, plus flags
    for gaps above the threshold and for groups too small to compare.
    scope="all" uses the whole synthetic cohort but returns aggregates only,
    so no other advisor's students are identifiable."""
    if attribute not in config.FAIRNESS_ATTRIBUTES:
        raise ValueError(f"Unsupported attribute: {attribute}")
    sql = f"""SELECT s.{attribute} AS grp, p.band FROM students s
              JOIN priority_scores p ON p.student_id = s.student_id"""
    params: tuple = ()
    if scope == "mine":
        sql += " WHERE s.advisor_username = ?"
        params = (username,)
    with database.connect(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if attribute == "year_level":
        df["grp"] = "Year " + df["grp"].astype(str)
    counts = pd.crosstab(df["grp"], df["band"]).reindex(columns=config.BANDS, fill_value=0)
    sizes = counts.sum(axis=1)
    pct = (counts.div(sizes, axis=0) * 100).round(1)
    table = pd.DataFrame({"Group": counts.index.astype(str), "n": sizes.values})
    for band in config.BANDS:
        table[f"{band} (count)"] = counts[band].values
        table[f"{band} (%)"] = pct[band].values
    flags = []
    for band in ["High", "Medium"]:
        gap = float(pct[band].max() - pct[band].min()) if len(pct) > 1 else 0.0
        if gap > config.FAIRNESS_GAP_THRESHOLD_PP:
            flags.append(f"{band} band: a {gap:.1f} percentage-point gap between "
                         f"{pct[band].idxmax()} and {pct[band].idxmin()}.")
    small = [str(g) for g, n in sizes.items() if n < config.FAIRNESS_SMALL_GROUP_N]
    return {"table": table, "flags": flags, "small_groups": small,
            "attribute_label": config.FAIRNESS_ATTRIBUTES[attribute]}


# ── Import new synthetic data ─────────────────────────────────────────────
@dataclass
class ImportResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    imported: int = 0


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def validate_import(df: pd.DataFrame, username: str) -> List[str]:
    errors: List[str] = []
    cols = list(df.columns)
    extra = [c for c in cols if c not in config.ALLOWED_STUDENT_FIELDS]
    missing = [c for c in config.ALLOWED_STUDENT_FIELDS if c not in cols]
    for c in extra:
        errors.append(f"Column '{c}' is not allowed: only fields available before the "
                      "Week 3 checkpoint can be imported.")
    for c in missing:
        errors.append(f"Required column '{c}' is missing.")
    if errors:
        return errors
    if df.empty:
        return ["The file has no data rows."]
    if len(df) > 2000:
        return ["The file has more than 2,000 rows."]
    dupes = df["student_id"][df["student_id"].duplicated()].unique()
    for d in dupes:
        errors.append(f"Student ID {d} appears more than once.")
    for i, r in df.iterrows():
        row_no = i + 2  # header is row 1
        if not re.fullmatch(r"STU-\d{4}", str(r["student_id"])):
            errors.append(f"Row {row_no}: student_id must look like STU-1234.")
        if r["advisor_username"] != username:
            errors.append(f"Row {row_no}: you can only import students in your own caseload.")
        if r["demographic_group"] not in config.DEMOGRAPHIC_VALUES:
            errors.append(f"Row {row_no}: demographic_group must be Domestic or International.")
        if str(r["submitted_early_assessment"]).strip().lower() not in {
                "true", "false", "1", "0", "yes", "no"}:
            errors.append(f"Row {row_no}: submitted_early_assessment must be true or false.")
        for col, (lo, hi) in config.FIELD_RANGES.items():
            try:
                v = int(r[col])
                if not lo <= v <= hi:
                    errors.append(f"Row {row_no}: {col} = {v} is outside {lo} to {hi}.")
            except (TypeError, ValueError):
                errors.append(f"Row {row_no}: {col} must be a whole number.")
    return errors


def import_students(username: str, file_bytes: bytes, db_path=None) -> ImportResult:
    """Validate an uploaded CSV, then save and score it. All-or-nothing:
    if any row fails, nothing is imported."""
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str).fillna("")
        df.columns = [c.strip() for c in df.columns]
    except Exception:
        return ImportResult(False, ["The file could not be read as a CSV."])
    errors = validate_import(df, username)
    if errors:
        with database.connect(db_path) as conn:
            _log(conn, username, "import_rejected", f"{len(errors)} error(s)")
        return ImportResult(False, errors)
    with database.connect(db_path) as conn:
        clash = conn.execute(
            f"SELECT student_id FROM students WHERE student_id IN "
            f"({','.join('?' * len(df))}) AND advisor_username != ?",
            [*df["student_id"], username]).fetchall()
        if clash:
            return ImportResult(False, [f"{r[0]} belongs to another advisor's caseload."
                                        for r in clash])
        n = _upsert_students(conn, df)
        _log(conn, username, "import", f"{n} student record(s)")
    rescore_all(db_path)
    return ImportResult(True, [], n)


def scoring_rules_table() -> pd.DataFrame:
    """The rules as a table, so the UI shows exactly what the engine applies."""
    rows = []
    lower = 0
    for max_l, pts, _ in config.LOGIN_RULES:
        rows.append(("Canvas logins per week", f"{lower} to {max_l}", pts))
        lower = max_l + 1
    upper = None
    for min_d, pts, _ in config.ABSENCE_RULES:
        cond = f"{min_d} or more" if upper is None else f"{min_d} to {upper}"
        rows.append(("Days since last Canvas login", cond, pts))
        upper = min_d - 1
    rows.append(("Early assessment", "Not submitted", config.ASSESSMENT_NOT_SUBMITTED_POINTS))
    rows.append(("Early assessment", f"Submitted {config.ASSESSMENT_LATE_DAYS}+ days late",
                 config.ASSESSMENT_LATE_POINTS))
    rows.append(("Registration", "After semester start", config.LATE_REGISTRATION_POINTS))
    rows.append(("Discussion forum", "No posts", config.NO_FORUM_POINTS))
    return pd.DataFrame(rows, columns=["Indicator", "Condition", "Points"])
