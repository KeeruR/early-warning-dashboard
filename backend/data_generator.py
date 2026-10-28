"""
Synthetic student engagement dataset generator.

Produces fake student records following the field structure in the project
brief. No real student data is used. Only fields available before the end of
Week 3 are generated, so later-semester outcomes cannot leak into the scores.

Generation method
-----------------
Each synthetic student is given a hidden "engagement tendency" between 0 and 1
(drawn from a Beta(2.5, 2.0) distribution, which leans towards engaged
students, as most students are). The observable fields are then drawn from
distributions that depend on that tendency, so the fields are correlated the
way they would be in practice (a disengaged student tends to log in less AND
miss the early assessment). The hidden tendency is NOT saved, so the scoring
rules never see it. A fixed random seed makes the dataset reproducible.
"""

import random

import numpy as np
import pandas as pd

COURSES = ["INFOSYS 110", "BUSINESS 102", "STATS 108", "MGMT 101", "ACCTG 102"]
ADVISORS = ["advisor.a", "advisor.b"]


def generate_dataset(n: int = 140, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        tendency = np_rng.beta(2.5, 2.0)

        logins = max(0, round(np_rng.normal(2 + tendency * 6, 1.8)))
        days_absent = max(0, round(np_rng.exponential((1 - tendency) * 10 + 1)))
        if logins == 0:
            # Consistency rule: a student with no logins this week cannot
            # have logged in during the last 7 days.
            days_absent = max(days_absent, 7)
        submitted = bool(np_rng.random() < 0.35 + tendency * 0.6)
        days_late = 0
        if submitted and np_rng.random() < 0.25:
            days_late = rng.randint(1, 6)
        registration = round(np_rng.normal(14 + tendency * 10, 8))
        forum_posts = int(np_rng.poisson(tendency * 3))

        rows.append({
            "student_id": f"STU-{1000 + i:04d}",
            "advisor_username": ADVISORS[i % len(ADVISORS)],
            "course": rng.choice(COURSES),
            "year_level": rng.choices([1, 2, 3, 4], weights=[0.4, 0.3, 0.2, 0.1])[0],
            "demographic_group": rng.choices(["Domestic", "International"],
                                             weights=[0.7, 0.3])[0],
            "registration_days_before_start": int(registration),
            "canvas_logins_per_week": int(logins),
            "days_since_last_login": int(days_absent),
            "submitted_early_assessment": submitted,
            "early_assessment_days_late": int(days_late),
            "forum_posts_count": forum_posts,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate_dataset()
    print(df.head())
    print(df.describe(include="all"))
