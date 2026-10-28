"""
Student Early-Warning Dashboard (frontend)
INFOMGMT 399, Team 13

Run with:  streamlit run app.py

The frontend only handles display and user input. Every action calls a
function in backend/services.py, which reads or writes the SQLite database.
All data is synthetic. The tool never contacts students or decides anything:
the advisor reviews each case and chooses the next step.
"""

import streamlit as st

from backend import config, services

st.set_page_config(page_title="Student Early-Warning Dashboard", page_icon="📋",
                   layout="wide")

# Styling for the sidebar menu and the page header. Only visual: the radio
# keeps its key ("nav") and its labels, so navigation logic is unchanged.
APP_CSS = """
<style>
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #14213D 0%, #1F3A66 100%);
}
[data-testid="stSidebar"] * { color: #F7F6F2; }
[data-testid="stSidebar"] .nav-brand {
    font-size: 1.05rem; font-weight: 700; letter-spacing: .3px;
    margin: .25rem 0 .1rem 0;
}
[data-testid="stSidebar"] .nav-user {
    font-size: .85rem; opacity: .8; margin-bottom: 1rem;
    padding-bottom: .9rem; border-bottom: 1px solid rgba(255,255,255,.15);
}
[data-testid="stSidebar"] label[data-testid="stRadioOption"] {
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.10);
    border-radius: 12px;
    padding: .55rem .8rem;
    margin: 0 0 .35rem 0;
    width: 100%;
    box-sizing: border-box;
    transition: background .15s ease, border-color .15s ease;
    cursor: pointer;
}
[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {
    background: rgba(255,255,255,.10);
}
[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {
    background: #1F5FA8;
    border-color: #9CC3F0;
    box-shadow: 0 4px 14px rgba(0,0,0,.25);
}
/* hide the radio dot, keep the text */
[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {
    display: none;
}
[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {
    font-size: .95rem; font-weight: 500; margin: 0;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%; border-radius: 10px;
    background: transparent; border: 1px solid #9CC3F0; color: #F7F6F2;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(156,195,240,.15); border-color: #F7F6F2;
}
.block-container { padding-top: 2rem; }
h1 { color: #14213D; font-weight: 700; letter-spacing: -.3px; }
h2, h3 { color: #1F3A66; }
div[data-testid="stMetric"], div[data-testid="stExpander"] {
    border-radius: 14px;
}
</style>
"""
st.html(APP_CSS)

BAND_BADGE = {
    "High": ":red-background[**High priority**]",
    "Medium": ":orange-background[**Medium priority**]",
    "Low": ":green-background[**Low priority**]",
}


@st.cache_resource
def start_backend():
    """Create the database, seed synthetic data and score it (runs once)."""
    services.init_app()
    return True


start_backend()

if "user" not in st.session_state:
    st.session_state.user = None


# ── Login ─────────────────────────────────────────────────────────────────
def login_page():
    st.title("Student Early-Warning Dashboard")
    st.caption("Proof of concept for student advisors. Synthetic data only.")
    with st.form("login"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = services.authenticate(username, password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Username or password is incorrect.")
    st.info("Test accounts are listed in the README. They only give access to "
            "synthetic data.")


# ── Caseload ──────────────────────────────────────────────────────────────
def caseload_page(user):
    username = user["username"]
    summary = services.caseload_summary(username)

    st.title("Your caseload")
    st.caption("Checkpoint: end of Week 3  |  Synthetic data only  |  "
               "You decide every next step. The dashboard never contacts a student.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Students in your caseload", summary["total"])
    c2.metric("High priority", summary["High"])
    c3.metric("Medium priority", summary["Medium"])
    c4.metric("Reviewed", summary["reviewed"])

    f1, f2, f3, f4 = st.columns(4)
    bands = f1.multiselect("Support priority", config.BANDS, default=["High", "Medium"],
                           key="f_bands")
    courses = f2.multiselect("Course", summary["courses"], key="f_courses")
    groups = f3.multiselect("Demographic group", sorted(config.DEMOGRAPHIC_VALUES),
                            key="f_groups")
    status = f4.selectbox("Review status", ["All", "Not reviewed", "Reviewed"],
                          key="f_status")

    rows = services.get_caseload(username, bands=bands or None, courses=courses or None,
                                 groups=groups or None, review_status=status)

    st.subheader(f"{len(rows)} students shown, most urgent first")
    st.caption(f"Order: highest score first (out of {config.MAX_SCORE}), then longest time "
               "since last login, then fewest logins. Each reason shows the points it adds.")

    if not rows:
        st.info("No students match these filters.")
    for r in rows:
        student_card(username, r)


def student_card(username, r):
    sid = r["student_id"]
    with st.container(border=True, key=f"card_{sid}"):
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"**#{r['rank']}  {sid}**  ·  {r['course']}  ·  Year {r['year_level']}")
            st.markdown(f"{BAND_BADGE[r['band']]}  Score **{r['score']} / {config.MAX_SCORE}**")
            if r["reasons"]:
                st.markdown("\n".join(
                    f"- {ind['reason'][0].upper() + ind['reason'][1:]} (+{ind['points']})"
                    for ind in r["reasons"]))
            else:
                st.markdown("- No early engagement concerns found.")
        with right:
            review = r["review"]
            if review:
                st.success(f"Reviewed {review['reviewed_at'][:10]}. "
                           f"Your next step: {review['next_step']}")
                if st.button("Undo review", key=f"undo_{sid}"):
                    services.undo_review(username, sid)
                    st.rerun()
            else:
                step = st.selectbox("Your next step", config.NEXT_STEP_OPTIONS,
                                    key=f"step_{sid}")
                if st.button("Mark reviewed", key=f"rev_{sid}", type="primary"):
                    services.mark_reviewed(username, sid, step)
                    st.rerun()
                st.caption("Records that you have looked at this case and the next step "
                           "you chose. It does not contact the student.")
        with st.expander("Data used for this score"):
            detail = r
            st.table({
                "Field": ["Canvas logins per week", "Days since last login",
                          "Early assessment submitted", "Days late (if submitted)",
                          "Days registered before start", "Forum posts"],
                "Value": [str(detail["canvas_logins_per_week"]),
                          str(detail["days_since_last_login"]),
                          "Yes" if detail["submitted_early_assessment"] else "No",
                          str(detail["early_assessment_days_late"]),
                          str(detail["registration_days_before_start"]),
                          str(detail["forum_posts_count"])],
            })
            st.caption(f"Scored with rule version {detail['rule_version']} "
                       f"at {detail['scored_at'][:16].replace('T', ' ')} UTC.")


# ── Fairness ──────────────────────────────────────────────────────────────
def fairness_page(user):
    st.title("Fairness check")
    st.caption("Demographic fields are never used in the score. This page shows whether "
               "the score still places one group in a priority band more often than another.")
    a1, a2 = st.columns(2)
    attribute = a1.radio("Compare by", list(config.FAIRNESS_ATTRIBUTES),
                         format_func=config.FAIRNESS_ATTRIBUTES.get, key="fair_attr")
    scope = a2.radio("Students", ["mine", "all"], key="fair_scope",
                     format_func=lambda s: "My caseload" if s == "mine"
                     else "Whole cohort (totals only)")
    result = services.fairness_summary(user["username"], attribute, scope)
    st.dataframe(result["table"], hide_index=True, width="stretch")
    st.caption("n = number of students in the group. Percentages are within each group.")
    for flag in result["flags"]:
        st.warning(f"Check suggested. {flag} Gaps above "
                   f"{config.FAIRNESS_GAP_THRESHOLD_PP:.0f} points are flagged for review.")
    if not result["flags"]:
        st.success(f"No gap above {config.FAIRNESS_GAP_THRESHOLD_PP:.0f} percentage points.")
    if result["small_groups"]:
        st.info(f"Small groups (fewer than {config.FAIRNESS_SMALL_GROUP_N} students): "
                f"{', '.join(result['small_groups'])}. One or two students change these "
                "percentages a lot, so treat gaps involving them with caution.")
    st.caption("This dataset is synthetic and group membership was generated independently "
               "of engagement, so any gap here reflects random variation, not a real pattern.")


# ── Import ────────────────────────────────────────────────────────────────
def import_page(user):
    st.title("Import student data")
    st.write("Upload a CSV of synthetic engagement data for your own caseload. The file is "
             "checked before anything is saved. If any row fails, nothing is imported.")
    with st.expander("Required columns"):
        st.write(", ".join(config.ALLOWED_STUDENT_FIELDS))
        st.caption("Any other column is rejected, so data collected after the Week 3 "
                   "checkpoint cannot enter the system.")
    template = (",".join(config.ALLOWED_STUDENT_FIELDS) + "\n"
                f"STU-2001,{user['username']},STATS 108,1,Domestic,10,2,12,false,0,0\n")
    st.download_button("Download CSV template", template, "import_template.csv", "text/csv")
    uploaded = st.file_uploader("CSV file", type=["csv"], key="upload")
    if uploaded is not None and st.button("Validate and import", type="primary"):
        if uploaded.size > 1_000_000:
            st.error("The file is larger than 1 MB.")
            return
        result = services.import_students(user["username"], uploaded.getvalue())
        if result.ok:
            st.success(f"Imported and scored {result.imported} student record(s). "
                       "They now appear in your caseload.")
        else:
            st.error(f"Nothing was imported. {len(result.errors)} problem(s) found:")
            for e in result.errors[:20]:
                st.markdown(f"- {e}")


# ── Rules and data ────────────────────────────────────────────────────────
def rules_page(user):
    st.title("How priorities are calculated")
    st.write("Each indicator that applies adds points. The total sets the support "
             "priority. Only one row per indicator can apply.")
    st.dataframe(services.scoring_rules_table(), hide_index=True, width="stretch")
    st.markdown(f"- **High priority:** {config.HIGH_MIN_SCORE} to {config.MAX_SCORE} points\n"
                f"- **Medium priority:** {config.MEDIUM_MIN_SCORE} to "
                f"{config.HIGH_MIN_SCORE - 1} points\n"
                f"- **Low priority:** 0 to {config.MEDIUM_MIN_SCORE - 1} points")
    st.caption(f"Rule version {config.RULE_VERSION}. These thresholds are a first design and "
               "have not been validated against real student outcomes.")
    st.subheader("Data dictionary")
    st.table({
        "Field": ["student_id", "course", "year_level", "demographic_group",
                  "registration_days_before_start", "canvas_logins_per_week",
                  "days_since_last_login", "submitted_early_assessment",
                  "early_assessment_days_late", "forum_posts_count"],
        "Meaning": ["Synthetic ID, no names stored", "Enrolled course",
                    "Year of study (1 to 4)", "Domestic or International (fairness check only)",
                    "Negative = enrolled after semester start",
                    "Average Canvas logins per week, Weeks 1 to 3",
                    "Days since last Canvas login at the checkpoint",
                    "Early assessment submitted (true/false)",
                    "Days late if submitted", "Discussion forum posts before the checkpoint"],
        "Used in score": ["No", "No", "No", "No", "Yes", "Yes", "Yes", "Yes", "Yes", "Yes"],
    })


# ── Privacy ───────────────────────────────────────────────────────────────
def privacy_page(user):
    st.title("Privacy and data handling")
    st.markdown(
        "- **Synthetic data only.** No real student is in this system.\n"
        "- **Minimum fields (IPP 1).** No names, contact details or grades. Imports with any "
        "other column are rejected.\n"
        "- **Access limited to your caseload (IPP 5).** Advisors log in and the backend only "
        "returns their own students. Other caseloads appear only as totals in the fairness check.\n"
        f"- **Retention (IPP 9).** Review records are deleted after "
        f"{config.REVIEW_RETENTION_DAYS} days, checked each time the app starts.\n"
        "- **Next steps are a fixed list,** not free text, so no sensitive notes are typed in.\n"
        "- **Human in the loop.** The dashboard never contacts a student or makes a decision.\n"
        "- **Audit log.** Logins, reviews, imports and refused access are recorded "
        "(passwords are never logged).")


# ── Router ────────────────────────────────────────────────────────────────
PAGES = {
    "Caseload": caseload_page,
    "Fairness check": fairness_page,
    "Import data": import_page,
    "How priorities are calculated": rules_page,
    "Privacy": privacy_page,
}

user = st.session_state.user
if user is None:
    login_page()
else:
    with st.sidebar:
        st.html(f'<div class="nav-brand">📋 Early-Warning</div>'
                f'<div class="nav-user">Signed in as <b>{user["display_name"]}</b></div>')
        page = st.radio("Go to", list(PAGES), key="nav")
        if st.button("Log out"):
            st.session_state.user = None
            st.rerun()
    PAGES[page](user)
