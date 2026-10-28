# Student Early-Warning Dashboard

**INFOMGMT 399 Capstone, Team 13**
Leona Naumovska, Long Wai Wong, Raaga Rangu, Keeru Rangu

A working proof of concept that helps university student advisors see which
students in their caseload may need early support, why, and what they have
already reviewed. It runs on **synthetic data only**. The dashboard never
contacts a student or makes a decision: the advisor reviews each case and
chooses the next step.

---

## 1. Quick start (about 3 minutes)

Requirements: **Python 3.10 or later** and an internet connection for the
first install. Works on macOS, Windows and Linux.

```bash
# 1. Open a terminal in this folder (the one containing app.py)
# 2. (Optional but recommended) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install the packages
pip install -r requirements.txt

# 4. Start the app
streamlit run app.py
```

The browser opens at **http://localhost:8501**. If it does not, open that
address yourself. On first start the app creates `data/early_warning.db`,
generates 140 synthetic students and scores them. Nothing else needs setting up.

To stop the app, press `Ctrl + C` in the terminal.

### Test accounts

| Username    | Password          | Caseload |
|-------------|-------------------|----------|
| `advisor.a` | `Demo-Advisor-A1` | 70 synthetic students |
| `advisor.b` | `Demo-Advisor-B2` | 70 different synthetic students |

These are demo credentials for synthetic data only. They are not personal
passwords and protect no real information.

### Reset the demo data

```bash
python scripts/reset_demo_data.py
```

Then restart the app. This deletes all reviews and imported rows and rebuilds
the original 140 students.

### Run the automated tests

```bash
python -m pytest -v
```

26 tests run in a few seconds against a temporary database, so they never
change the demo data. Latest results: `docs/test_results.txt`.

---

## 2. What the user can do

1. **Log in** as an advisor. Wrong passwords are refused.
2. **See the caseload ranked most urgent first.** Each card shows the support
   priority (High, Medium, Low), the score out of 12, and every reason that
   added points, with the points it added.
3. **Filter** by priority, course, demographic group and review status.
4. **Open "Data used for this score"** to see the raw values behind a card.
5. **Choose a next step and click "Mark reviewed".** This saves to the
   database, so it is still there after logging out or restarting. "Undo
   review" reverses it.
6. **Fairness check:** compare priority bands by Domestic/International or by
   year level, for the advisor's caseload or the whole cohort (totals only).
   Group sizes are shown and gaps over 10 percentage points are flagged.
7. **Import data:** upload a CSV for the advisor's own caseload. It is
   validated first and rejected in full if any row is wrong. Try the files in
   `sample_data/`.
8. **How priorities are calculated** and **Privacy** pages explain the rules
   and data handling in the app itself.

---

## 3. How it works

```
Browser  ->  app.py (Streamlit UI)  ->  backend/services.py  ->  SQLite database
                                              |      |
                                    scoring.py (rules)   auth.py (passwords)
```

See `docs/architecture.png` and `docs/data_model.png`.

| File | Role |
|------|------|
| `app.py` | Frontend. Pages, filters, cards, buttons. Calls only `services.py`. |
| `backend/services.py` | Backend API: login, caseload queries, access control, reviews, fairness, import validation, retention. |
| `backend/scoring.py` | Rule engine. Turns one student record into a score, band and list of reasons. No UI or database code, so it can be unit tested. |
| `backend/config.py` | Every threshold, point value, band cut-off, allowed field and retention period. |
| `backend/database.py` | SQLite schema and connection handling. |
| `backend/auth.py` | Salted PBKDF2-SHA256 password hashing. |
| `backend/data_generator.py` | Creates the synthetic dataset (seeded, reproducible). |
| `tests/` | Unit, integration and end-to-end tests. |
| `sample_data/` | One valid and two invalid CSV files for testing the import. |

### Scoring rules (version 2.0)

Each indicator that applies adds points. Only one row per indicator can apply.

| Indicator | Condition | Points |
|-----------|-----------|--------|
| Canvas logins per week | 0 to 1 | 3 |
| Canvas logins per week | 2 to 3 | 1 |
| Days since last Canvas login | 21 or more | 4 |
| Days since last Canvas login | 15 to 20 | 3 |
| Days since last Canvas login | 10 to 14 | 2 |
| Days since last Canvas login | 5 to 9 | 1 |
| Early assessment | Not submitted | 3 |
| Early assessment | Submitted 3 or more days late | 1 |
| Registration | After semester start | 1 |
| Discussion forum | No posts | 1 |

Maximum score 12. **High** 6 to 12, **Medium** 4 to 5, **Low** 0 to 3.
Ties are ordered by longest time since last login, then fewest logins, then
student ID. These thresholds are a first design and have **not** been
validated against real student outcomes.

### Data dictionary

| Field | Type | Range | Used in score | Meaning |
|-------|------|-------|---------------|---------|
| `student_id` | text | `STU-0000` | No | Synthetic ID. No names stored. |
| `advisor_username` | text | existing advisor | No | Which advisor's caseload |
| `course` | text | 5 courses | No | Enrolled course |
| `year_level` | integer | 1 to 4 | No (fairness only) | Year of study |
| `demographic_group` | text | Domestic, International | No (fairness only) | Used only to check fairness |
| `registration_days_before_start` | integer | -30 to 90 | Yes | Negative means enrolled after start |
| `canvas_logins_per_week` | integer | 0 to 50 | Yes | Average logins per week, Weeks 1 to 3 |
| `days_since_last_login` | integer | 0 to 120 | Yes | At the Week 3 checkpoint |
| `submitted_early_assessment` | true/false | | Yes | Early assessment submitted |
| `early_assessment_days_late` | integer | 0 to 60 | Yes | Days late if submitted |
| `forum_posts_count` | integer | 0 to 200 | Yes | Posts before the checkpoint |

Sample rows (from `data/synthetic_students.csv`, created on first run):

```
student_id,advisor_username,course,year_level,demographic_group,registration_days_before_start,canvas_logins_per_week,days_since_last_login,submitted_early_assessment,early_assessment_days_late,forum_posts_count
STU-1053,advisor.b,INFOSYS 110,1,International,21,5,32,False,0,1
STU-1064,advisor.a,MGMT 101,3,International,31,1,13,False,0,2
```

**How the synthetic data is generated:** each student gets a hidden
"engagement tendency" between 0 and 1 (Beta(2.5, 2.0) distribution). Logins,
absence, submission, lateness, registration and forum posts are drawn from
distributions that depend on that tendency, so the fields are correlated.
The tendency is not saved, so the rules never see it. A student with 0 logins
a week always has at least 7 days since last login. Seed 42 makes the data
reproducible. Demographic group and year level are drawn independently of
engagement, so any gap in the fairness check reflects random variation.

---

## 4. Privacy and safeguards

- Synthetic data only. No real student information anywhere.
- Minimum fields (IPP 1). Imports with any extra column, such as a final
  exam mark, are rejected, which also stops post-checkpoint data entering.
- Access control (IPP 5). Each advisor only sees and changes their own
  students; this is enforced in the backend, not just hidden in the UI.
- Retention (IPP 9). Review records older than 180 days are deleted each time
  the app starts.
- Next steps are chosen from a fixed list, not typed, so no sensitive notes.
- Passwords are salted and hashed, and never written to the audit log.
- No external services or API keys are used.

---

## 5. What is implemented, simulated or not built

**Implemented:** login, ranked caseload, all-reasons scoring with points,
filters, review with next step, undo, persistence in SQLite, access control,
fairness check by two attributes with group sizes and flags, validated CSV
import, retention purge, audit log, automated tests.

**Simulated:** all student data is synthetic; advisor accounts are demo
accounts; there is no link to Canvas or any university system; the scoring
thresholds are a team design, not a validated predictive model.

**Not built (future work):** real-data integration and ethics approval,
university single sign-on, validation of thresholds against real outcomes,
statistical significance testing in the fairness check, engagement history
over several weeks, hosting on a server.

---

## 6. Troubleshooting

- `command not found: streamlit` → run `pip install -r requirements.txt`, or
  start with `python -m streamlit run app.py`.
- `pip` not found → use `pip3` or `python3 -m pip`.
- Port already in use → `streamlit run app.py --server.port 8502`.
- Strange data after testing → `python scripts/reset_demo_data.py`.

---

## 7. AI use

The team wrote the initial code. Generative AI (Claude, Anthropic) was then used to help write and revise parts of this artefact, including code, tests and documentation. The AI-use declaration in the final report sets out which parts the team designed, wrote, changed, checked and tested.
