"""
Central configuration for the Early-Warning Dashboard.

Every scoring threshold, band cut-off and privacy setting lives here so that
any score shown in the dashboard can be traced back to a documented rule
(Report 2 feedback: "indicator points and thresholds aren't specified").
"""

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "early_warning.db"
SEED_CSV_PATH = DATA_DIR / "synthetic_students.csv"

# ── Scoring rules (version 2) ─────────────────────────────────────────────
# Version 1 (Report 2) used coarse 0/1/2 points, which left 9 of 12 High
# students tied. Version 2 grades the absence and login indicators so that
# longer absences score higher, and adds a documented tie-break order.
RULE_VERSION = "2.0"

# Canvas logins per week (lower = less engaged)
LOGIN_RULES = [
    # (max_logins_inclusive, points, label)
    (1, 3, "very low Canvas activity ({v} {unit} a week)"),
    (3, 1, "below-average Canvas activity ({v} {unit} a week)"),
]

# Days since last Canvas login (graded so 12 and 24 days no longer tie)
ABSENCE_RULES = [
    # (min_days_inclusive, points, label)
    (21, 4, "no Canvas login for {v} days"),
    (15, 3, "no Canvas login for {v} days"),
    (10, 2, "no Canvas login for {v} days"),
    (5, 1, "no Canvas login for {v} days"),
]

ASSESSMENT_NOT_SUBMITTED_POINTS = 3
ASSESSMENT_LATE_DAYS = 3            # submitted this many days late or more
ASSESSMENT_LATE_POINTS = 1
LATE_REGISTRATION_POINTS = 1        # enrolled after semester start
NO_FORUM_POINTS = 1                 # zero discussion posts before Week 3

MAX_SCORE = 3 + 4 + 3 + 1 + 1       # = 12

# Support-priority bands (renamed from "risk" after the Week 8 walkthrough)
HIGH_MIN_SCORE = 6
MEDIUM_MIN_SCORE = 4
BANDS = ["High", "Medium", "Low"]

# ── Fairness check ────────────────────────────────────────────────────────
FAIRNESS_ATTRIBUTES = {
    "demographic_group": "Domestic / International",
    "year_level": "Year level",
}
FAIRNESS_GAP_THRESHOLD_PP = 10.0    # flag gaps larger than 10 percentage points
FAIRNESS_SMALL_GROUP_N = 20         # warn when a group is too small to compare

# ── Privacy and data handling (Privacy Act 2020, IPPs) ────────────────────
# IPP 1 / IPP 4: only fields needed for early-support prioritisation.
# Anything collected after the Week 3 checkpoint is rejected on import.
ALLOWED_STUDENT_FIELDS = [
    "student_id",
    "advisor_username",
    "course",
    "year_level",
    "demographic_group",
    "registration_days_before_start",
    "canvas_logins_per_week",
    "days_since_last_login",
    "submitted_early_assessment",
    "early_assessment_days_late",
    "forum_posts_count",
]

# IPP 9: reviewed-status records are not kept longer than needed.
REVIEW_RETENTION_DAYS = 180

# Advisor's own next-step choices. A fixed list (not free text) so that no
# sensitive personal information is typed into the system (IPP 1).
NEXT_STEP_OPTIONS = [
    "Not decided yet",
    "Send check-in email",
    "Book a meeting",
    "Refer to student support services",
    "No action needed",
]

# ── Validation ranges for imported synthetic data ─────────────────────────
FIELD_RANGES = {
    "year_level": (1, 4),
    "registration_days_before_start": (-30, 90),
    "canvas_logins_per_week": (0, 50),
    "days_since_last_login": (0, 120),
    "early_assessment_days_late": (0, 60),
    "forum_posts_count": (0, 200),
}
DEMOGRAPHIC_VALUES = {"Domestic", "International"}
