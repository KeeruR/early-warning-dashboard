"""
Rule-based support-priority scoring.

Pure functions with no database or UI code, so the logic can be unit tested
on its own. Each indicator that fires returns its points AND a plain-language
reason, which means every point in a student's score is visible to the advisor.
"""

from dataclasses import dataclass, field
from typing import List

from . import config


@dataclass
class Indicator:
    code: str
    points: int
    reason: str


@dataclass
class ScoreResult:
    score: int
    band: str
    indicators: List[Indicator] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        """All triggered indicators, highest points first, with their points."""
        if not self.indicators:
            return "No early engagement concerns found."
        parts = [f"{i.reason} (+{i.points})" for i in self.indicators]
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def score_student(student: dict) -> ScoreResult:
    """Apply the version 2 rules in config.py to one student record."""
    indicators: List[Indicator] = []

    logins = int(student["canvas_logins_per_week"])
    for max_logins, points, label in config.LOGIN_RULES:
        if logins <= max_logins:
            unit = "login" if logins == 1 else "logins"
            indicators.append(Indicator("low_logins", points, label.format(v=logins, unit=unit)))
            break

    absent = int(student["days_since_last_login"])
    for min_days, points, label in config.ABSENCE_RULES:
        if absent >= min_days:
            indicators.append(Indicator("absence", points, label.format(v=absent)))
            break

    if not _as_bool(student["submitted_early_assessment"]):
        indicators.append(Indicator(
            "assessment", config.ASSESSMENT_NOT_SUBMITTED_POINTS,
            "did not submit the early assessment"))
    elif int(student["early_assessment_days_late"]) >= config.ASSESSMENT_LATE_DAYS:
        days = int(student["early_assessment_days_late"])
        indicators.append(Indicator(
            "assessment", config.ASSESSMENT_LATE_POINTS,
            f"submitted the early assessment {days} days late"))

    if int(student["registration_days_before_start"]) < 0:
        indicators.append(Indicator(
            "late_registration", config.LATE_REGISTRATION_POINTS,
            "enrolled after the semester started"))

    if int(student["forum_posts_count"]) == 0:
        indicators.append(Indicator(
            "no_forum", config.NO_FORUM_POINTS, "no discussion forum posts"))

    indicators.sort(key=lambda i: i.points, reverse=True)
    score = sum(i.points for i in indicators)
    return ScoreResult(score=score, band=band_for(score), indicators=indicators)


def band_for(score: int) -> str:
    if score >= config.HIGH_MIN_SCORE:
        return "High"
    if score >= config.MEDIUM_MIN_SCORE:
        return "Medium"
    return "Low"


def priority_sort_key(row: dict):
    """
    Order used for the caseload list: highest score first, then the longest
    absence, then the fewest logins, then student ID so the order is stable.
    This tie-break is shown to the advisor on screen.
    """
    return (-int(row["score"]), -int(row["days_since_last_login"]),
            int(row["canvas_logins_per_week"]), str(row["student_id"]))
