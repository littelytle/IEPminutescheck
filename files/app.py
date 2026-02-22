"""
IEP Minute Pro — Streamlit App
Backed by Google Sheets via gspread + service account credentials.

Run with:  streamlit run app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from sheets_db import SheetsDB

# ── set_page_config MUST be the very first Streamlit call ─────────────────────
st.set_page_config(
    page_title="IEP Minute Pro",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Constants ──────────────────────────────────────────────────────────────────
SUBJECTS = ["Math", "English", "Task Completion"]
GRADES   = ["6th", "7th", "8th"]

SUBJ_COLOR = {
    "Math":            "#6366f1",
    "English":         "#8b5cf6",
    "Task Completion": "#10b981",
}
GRADE_COLOR = {
    "6th": "#f59e0b",
    "7th": "#6366f1",
    "8th": "#10b981",
}

# Goal column name mapping  (subject → sheet column)
GOAL_COL = {
    "Math":            "goal_math",
    "English":         "goal_english",
    "Task Completion": "goal_task_completion",
}


# ── CSS injection (called once inside main) ───────────────────────────────────
def inject_css():
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.stApp { background-color: #f4f5f7; }

section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e5e7eb;
}
.stButton > button {
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    border: 1px solid #e5e7eb !important;
    background: #ffffff !important;
    color: #4b5563 !important;
    transition: all 0.15s;
}
.stButton > button:hover {
    border-color: #4f46e5 !important;
    color: #4f46e5 !important;
    background: #eef2ff !important;
}
h1 { font-weight: 800 !important; letter-spacing: -0.5px !important; }
h2 { font-weight: 700 !important; }
h3 { font-weight: 600 !important; }
details summary { font-size: 13px; color: #6b7280; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* tabs */
.stTabs [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 13px;
}
/* form containers */
div[data-testid="stForm"] {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 16px;
}
</style>
""",
        unsafe_allow_html=True,
    )


# ── Google Sheets connection (cached for the whole session) ───────────────────
@st.cache_resource
def get_db() -> SheetsDB:
    return SheetsDB()


def refresh():
    """Clear cached dataframes and rerun so fresh data is loaded."""
    for key in ("students_df", "logs_df", "staff_df"):
        st.session_state.pop(key, None)
    st.rerun()


# ── Per-session dataframe loaders ─────────────────────────────────────────────
def load_students(db: SheetsDB) -> pd.DataFrame:
    if "students_df" not in st.session_state:
        st.session_state["students_df"] = db.get_students()
    return st.session_state["students_df"]


def load_logs(db: SheetsDB) -> pd.DataFrame:
    if "logs_df" not in st.session_state:
        st.session_state["logs_df"] = db.get_logs()
    return st.session_state["logs_df"]


def load_staff(db: SheetsDB) -> pd.DataFrame:
    if "staff_df" not in st.session_state:
        st.session_state["staff_df"] = db.get_staff()
    return st.session_state["staff_df"]


# ── Date helpers ───────────────────────────────────────────────────────────────
def get_week_range(ref: date = None):
    ref = ref or date.today()
    mon = ref - timedelta(days=ref.weekday())   # Monday
    sun = mon + timedelta(days=6)               # Sunday
    return mon, sun


def get_month_range(ref: date = None):
    ref   = ref or date.today()
    first = ref.replace(day=1)
    # first day of next month − 1 day = last day of this month
    if ref.month == 12:
        last = date(ref.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(ref.year, ref.month + 1, 1) - timedelta(days=1)
    return first, last


def get_month_weeks(ref: date = None):
    """Return list of (label, start, end) for each Mon–Sun week overlapping the month."""
    ref   = ref or date.today()
    first = ref.replace(day=1)
    if ref.month == 12:
        last = date(ref.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(ref.year, ref.month + 1, 1) - timedelta(days=1)

    weeks = []
    cur   = first - timedelta(days=first.weekday())   # rewind to Monday
    while cur <= last:
        w_end = cur + timedelta(days=6)
        label = f"{cur.month}/{cur.day}–{w_end.month}/{w_end.day}"
        weeks.append((label, cur, w_end))
        cur += timedelta(days=7)
    return weeks


def _coerce_date_col(logs_df: pd.DataFrame) -> pd.Series:
    """Return a Series of python date objects from the 'date' column."""
    return pd.to_datetime(logs_df["date"], errors="coerce").dt.date


def logs_in_range(logs_df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if logs_df.empty:
        return logs_df
    d = _coerce_date_col(logs_df)
    return logs_df[(d >= start) & (d <= end)].copy()


def student_minutes(logs_df: pd.DataFrame, student_id, subject: str,
                    start: date, end: date) -> int:
    subset = logs_in_range(logs_df, start, end)
    if subset.empty:
        return 0
    subset = subset[(subset["student_id"] == student_id) & (subset["subject"] == subject)]
    return int(subset["minutes"].sum())


def staff_breakdown(logs_df: pd.DataFrame, student_id, subject: str,
                    start: date, end: date, staff_df: pd.DataFrame) -> dict:
    """Return {staff_name: total_minutes} for one student/subject/period."""
    result = {name: 0 for name in staff_df["name"].tolist()}
    subset = logs_in_range(logs_df, start, end)
    if subset.empty:
        return result
    subset = subset[(subset["student_id"] == student_id) & (subset["subject"] == subject)]
    for _, row in subset.iterrows():
        if row["staff"] in result:
            result[row["staff"]] += int(row["minutes"])
    return result


def safe_goal(student: pd.Series, subject: str) -> int:
    """Safely read the weekly goal for a subject from a student Series."""
    col = GOAL_COL.get(subject, "goal_math")
    val = student[col] if col in student.index else 60
    try:
        return int(val)
    except (TypeError, ValueError):
        return 60


def safe_active_subject(student: pd.Series) -> str:
    val = student.get("active_subject", "Math")
    if pd.isna(val) or val not in SUBJECTS:
        return "Math"
    return str(val)


# ── Summary metric row ─────────────────────────────────────────────────────────
def render_summary_row(label: str, logs_df: pd.DataFrame, staff_df: pd.DataFrame,
                        start: date, end: date):
    subset      = logs_in_range(logs_df, start, end)
    grand_total = int(subset["minutes"].sum()) if not subset.empty else 0

    # [label col] + [one col per staff] + [total col]
    col_widths = [1] + [2] * len(staff_df) + [1]
    cols       = st.columns(col_widths)

    cols[0].markdown(
        f"<div style='font-size:10px;font-weight:700;color:#4f46e5;"
        f"text-transform:uppercase;letter-spacing:1.2px;padding-top:6px'>{label}</div>",
        unsafe_allow_html=True,
    )

    for i, (_, staff_row) in enumerate(staff_df.iterrows()):
        name  = staff_row["name"]
        color = staff_row["color"]
        mins  = (
            int(subset[subset["staff"] == name]["minutes"].sum())
            if not subset.empty else 0
        )
        cols[i + 1].markdown(
            f"<div style='display:flex;align-items:center;gap:5px;"
            f"font-size:11px;color:#4b5563'>"
            f"<span style='display:inline-block;width:7px;height:7px;"
            f"border-radius:50%;background:{color}'></span>"
            f"{name.split()[-1]}: <b style='color:#111827'>{mins}m</b></div>",
            unsafe_allow_html=True,
        )

    cols[-1].markdown(
        f"<div style='text-align:right;font-size:13px;font-weight:700;"
        f"color:#111827;padding-top:4px'>{grand_total}m total</div>",
        unsafe_allow_html=True,
    )


# ── Segmented progress bar (pure HTML) ────────────────────────────────────────
def progress_bar_html(by_staff: dict, staff_df: pd.DataFrame, goal: int) -> str:
    total     = sum(by_staff.values())
    segs_html = ""
    for _, row in staff_df.iterrows():
        mins = by_staff.get(row["name"], 0)
        if mins > 0 and goal > 0:
            pct = min(mins / goal * 100, 100)
            segs_html += (
                f"<div title='{row['name']}: {mins}m' "
                f"style='width:{pct:.1f}%;background:{row['color']};"
                f"height:100%;display:inline-block'></div>"
            )

    pct_label  = min(int(total / goal * 100), 100) if goal > 0 else 0
    goal_color = "#10b981" if total >= goal else "#9ca3af"
    fw         = "600" if total >= goal else "400"

    return (
        f"<div style='background:#f3f4f6;border-radius:6px;height:10px;"
        f"overflow:hidden;border:1px solid #e5e7eb;display:flex;margin-bottom:3px'>"
        f"{segs_html}</div>"
        f"<div style='display:flex;justify-content:space-between;"
        f"font-size:10px;color:#9ca3af'>"
        f"<span>{total}m / {goal}m</span>"
        f"<span style='color:{goal_color};font-weight:{fw}'>{pct_label}%</span>"
        f"</div>"
    )


# ── Goal-hit line chart ────────────────────────────────────────────────────────
def render_goal_chart(logs_df: pd.DataFrame, students_df: pd.DataFrame):
    weeks      = get_month_weeks()
    chart_rows = []

    for label, w_start, w_end in weeks:
        row = {"Week": label}
        for subj in SUBJECTS:
            count = 0
            for _, stu in students_df.iterrows():
                goal  = safe_goal(stu, subj)
                total = student_minutes(logs_df, stu["id"], subj, w_start, w_end)
                if total >= goal:
                    count += 1
            row[subj] = count
        chart_rows.append(row)

    df_chart = pd.DataFrame(chart_rows)
    max_y    = max(len(students_df), 1)

    fig = go.Figure()
    for subj in SUBJECTS:
        fig.add_trace(go.Scatter(
            x=df_chart["Week"],
            y=df_chart[subj],
            mode="lines+markers",
            name="Tasks" if subj == "Task Completion" else subj,
            line=dict(color=SUBJ_COLOR[subj], width=2.5),
            marker=dict(size=8, color=SUBJ_COLOR[subj],
                        line=dict(width=2, color="white")),
            hovertemplate=(
                f"<b>{'Tasks' if subj == 'Task Completion' else subj}</b><br>"
                "%{x}<br>%{y} students hit goal<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(
            text=(
                "<b>Weekly Goal Progress</b><br>"
                "<span style='font-size:11px;color:#9ca3af'>"
                "Students hitting their weekly minutes goal, by subject</span>"
            ),
            font=dict(size=14, family="Inter"),
            x=0,
            xanchor="left",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis=dict(
            range=[-0.2, max_y + 0.5],
            tickvals=list(range(max_y + 1)),
            gridcolor="#f3f4f6",
            zeroline=False,
            title="Students hitting goal",
            title_font=dict(size=11, color="#9ca3af"),
        ),
        xaxis=dict(gridcolor="#f3f4f6", title=""),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=11),
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        height=280,
        font=dict(family="Inter"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Individual student card ────────────────────────────────────────────────────
def render_student_card(student: pd.Series, logs_df: pd.DataFrame,
                         staff_df: pd.DataFrame, db: SheetsDB):
    sid         = student["id"]
    name        = str(student["name"])
    grade       = str(student["grade"])
    gc          = GRADE_COLOR.get(grade, "#9ca3af")
    active_subj = safe_active_subject(student)
    goal        = safe_goal(student, active_subj)

    week_start, week_end = get_week_range()
    by_staff  = staff_breakdown(logs_df, sid, active_subj, week_start, week_end, staff_df)
    total_min = sum(by_staff.values())
    goal_met  = total_min >= goal

    # ── Colour accent strip ────────────────────────────────────────────────────
    st.markdown(
        f"<div style='height:3px;background:{SUBJ_COLOR[active_subj]};"
        f"border-radius:3px 3px 0 0'></div>",
        unsafe_allow_html=True,
    )

    # ── Name + grade + delete ──────────────────────────────────────────────────
    col_name, col_del = st.columns([6, 1])
    with col_name:
        st.markdown(
            f"<span style='background:{gc}18;color:{gc};font-size:10px;"
            f"font-weight:700;border-radius:4px;padding:2px 7px'>{grade}</span>"
            f"&nbsp;<b style='font-size:13px;color:#111827'>{name}</b>"
            + ("&nbsp;✅" if goal_met else ""),
            unsafe_allow_html=True,
        )
    with col_del:
        if st.button("×", key=f"del_{sid}", help="Remove student"):
            db.delete_student(sid)
            refresh()

    # ── Subject switcher buttons ───────────────────────────────────────────────
    subj_cols = st.columns(3)
    for i, subj in enumerate(SUBJECTS):
        label = "Tasks" if subj == "Task Completion" else subj
        with subj_cols[i]:
            # Highlight the active subject with a coloured border via markdown
            is_active = (subj == active_subj)
            border    = f"2px solid {SUBJ_COLOR[subj]}" if is_active else "1px solid #e5e7eb"
            bg        = f"{SUBJ_COLOR[subj]}18" if is_active else "white"
            color     = SUBJ_COLOR[subj] if is_active else "#9ca3af"
            st.markdown(
                f"<div style='border:{border};background:{bg};border-radius:6px;"
                f"padding:3px;margin-bottom:4px;text-align:center;"
                f"font-size:10px;font-weight:600;color:{color};cursor:pointer'>"
                f"{label}</div>",
                unsafe_allow_html=True,
            )
            if st.button(label, key=f"subj_{sid}_{subj}",
                         use_container_width=True):
                db.update_student_subject(sid, subj)
                refresh()

    # ── Progress bar ──────────────────────────────────────────────────────────
    st.markdown(
        progress_bar_html(by_staff, staff_df, goal),
        unsafe_allow_html=True,
    )

    # ── Staff chips ────────────────────────────────────────────────────────────
    chips = ""
    for _, s in staff_df.iterrows():
        m = by_staff.get(s["name"], 0)
        if m > 0:
            s_color = s["color"]
            s_last  = s["name"].split()[-1]
            chips += (
                f"<span style='display:inline-flex;align-items:center;gap:3px;"
                f"background:#f4f5f7;border:1px solid #e5e7eb;border-radius:4px;"
                f"padding:2px 6px;font-size:9px;color:#4b5563;margin:2px'>"
                f"<span style='display:inline-block;width:5px;height:5px;"
                f"border-radius:50%;background:{s_color}'></span>"
                f"{s_last}: {m}m</span>"
            )
    if chips:
        st.markdown(chips, unsafe_allow_html=True)

    # ── Edit goal / name ──────────────────────────────────────────────────────
    with st.expander("⚙ Edit Goal / Name"):
        new_name = st.text_input("Name", value=name, key=f"ename_{sid}")
        new_goal = st.number_input(
            f"{active_subj} weekly goal (min)",
            value=goal, min_value=1,
            key=f"egoal_{sid}",
        )
        if st.button("Save", key=f"esave_{sid}"):
            db.update_student(sid, new_name, {active_subj: int(new_goal)})
            refresh()

    # ── Show notes ────────────────────────────────────────────────────────────
    with st.expander("📝 Show Notes"):
        if logs_df.empty:
            st.caption(f"No notes for {active_subj}")
        else:
            notes_df = logs_df[
                (logs_df["student_id"] == sid) &
                (logs_df["subject"] == active_subj) &
                (logs_df["note"].notna()) &
                (logs_df["note"].astype(str).str.strip() != "")
            ].sort_values("date", ascending=False)

            if notes_df.empty:
                st.caption(f"No notes for {active_subj}")
            else:
                for _, nr in notes_df.iterrows():
                    si    = staff_df[staff_df["name"] == nr["staff"]]
                    color = si["color"].values[0] if not si.empty else "#9ca3af"
                    st.markdown(
                        f"<div style='background:#f4f5f7;border:1px solid #e5e7eb;"
                        f"border-radius:7px;padding:7px 10px;margin-bottom:5px'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:3px'>"
                        f"<span style='font-size:10px;color:#4b5563'>"
                        f"<span style='display:inline-block;width:5px;height:5px;"
                        f"border-radius:50%;background:{color};margin-right:4px'></span>"
                        f"{str(nr['staff']).split()[-1]}</span>"
                        f"<span style='font-size:10px;color:#9ca3af'>"
                        f"{str(nr['date'])[5:]}</span>"
                        f"</div>"
                        f"<p style='font-size:11px;color:#4b5563;margin:0'>{nr['note']}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    st.markdown("---")


# ── Add student panel ──────────────────────────────────────────────────────────
def render_add_student(db: SheetsDB):
    st.subheader("Add Student")
    with st.form("add_student_form", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            name = st.text_input("Student Name", placeholder="Full name…")
        with c2:
            grade = st.selectbox("Grade", GRADES)

        st.markdown("**Weekly Goals (minutes)**")
        defaults = {"Math": 60, "English": 90, "Task Completion": 45}
        g_cols   = st.columns(3)
        goals    = {}
        for i, subj in enumerate(SUBJECTS):
            with g_cols[i]:
                lbl        = "Tasks" if subj == "Task Completion" else subj
                goals[subj] = st.number_input(
                    f"{lbl} (min/wk)",
                    value=defaults[subj],
                    min_value=1,
                    key=f"new_goal_{subj}",
                )

        submitted = st.form_submit_button("+ Add Student", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Please enter a student name.")
            else:
                db.add_student(name.strip(), grade, {k: int(v) for k, v in goals.items()})
                st.success(f"✓ {name.strip()} added!")
                refresh()


# ── Log session panel ──────────────────────────────────────────────────────────
def render_log_session(db: SheetsDB, students_df: pd.DataFrame,
                        staff_df: pd.DataFrame, logs_df: pd.DataFrame):
    st.subheader("Log Session")

    # The student checkboxes must live OUTSIDE the form so their values are
    # readable when the form submits.  We store selections in session_state.

    col_form, col_recent = st.columns([1, 1], gap="large")

    with col_form:
        # ── Step 1: grade + subject + staff + minutes + date ──────────────────
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            grade_sel = st.selectbox(
                "Grade", ["— select —"] + GRADES, key="ls_grade"
            )
        with r1c2:
            subj_sel = st.selectbox("Subject", SUBJECTS, key="ls_subject")

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            staff_sel = st.selectbox(
                "Staff", ["— select —"] + staff_df["name"].tolist(), key="ls_staff"
            )
        with r2c2:
            mins_val = st.number_input(
                "Minutes", min_value=1, value=30, key="ls_minutes"
            )

        log_date = st.date_input("Date", value=date.today(), key="ls_date")

        # ── Step 2: student checkboxes (filtered by grade) ────────────────────
        st.markdown("**Students**")
        selected_ids: list = []

        if grade_sel == "— select —":
            st.info("Select a grade above to see students.")
        else:
            grade_students = (
                students_df[students_df["grade"] == grade_sel]
                if not students_df.empty
                else pd.DataFrame()
            )
            if grade_students.empty:
                st.warning(f"No students in {grade_sel} grade yet.")
            else:
                sa_col, sn_col = st.columns(2)
                with sa_col:
                    if st.button("Select All", key="ls_all"):
                        for _, s in grade_students.iterrows():
                            st.session_state[f"ls_stu_{s['id']}"] = True
                with sn_col:
                    if st.button("Select None", key="ls_none"):
                        for _, s in grade_students.iterrows():
                            st.session_state[f"ls_stu_{s['id']}"] = False

                for _, stu in grade_students.iterrows():
                    checked = st.checkbox(
                        stu["name"],
                        key=f"ls_stu_{stu['id']}",
                    )
                    if checked:
                        selected_ids.append(stu["id"])

        # ── Step 3: notes + submit ────────────────────────────────────────────
        note_val = st.text_area(
            "Notes (optional)", placeholder="What did you work on?", key="ls_note"
        )

        n_sel     = len(selected_ids)
        btn_label = (
            f"Log {n_sel} Student{'s' if n_sel != 1 else ''} ✓"
            if n_sel > 0 else "Log Session ✓"
        )

        if st.button(btn_label, key="ls_submit", use_container_width=True):
            errors = []
            if grade_sel == "— select —":
                errors.append("Select a grade.")
            if staff_sel == "— select —":
                errors.append("Select a staff member.")
            if n_sel == 0:
                errors.append("Select at least one student.")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                for sid in selected_ids:
                    db.add_log(
                        student_id=sid,
                        subject=subj_sel,
                        staff=staff_sel,
                        minutes=int(mins_val),
                        log_date=str(log_date),
                        note=note_val,
                    )
                st.success(
                    f"✓ Logged {n_sel} student{'s' if n_sel != 1 else ''}!"
                )
                refresh()

    # ── Recent sessions sidebar ────────────────────────────────────────────────
    with col_recent:
        st.markdown("**Recent Sessions**")
        if logs_df.empty:
            st.caption("No sessions logged yet.")
        else:
            recent = logs_df.sort_values("date", ascending=False).head(8)
            for _, row in recent.iterrows():
                stu      = students_df[students_df["id"] == row["student_id"]]
                stu_name = stu["name"].values[0] if not stu.empty else "Unknown"
                stu_grd  = stu["grade"].values[0] if not stu.empty else ""
                gc       = GRADE_COLOR.get(str(stu_grd), "#9ca3af")
                si       = staff_df[staff_df["name"] == row["staff"]]
                sc       = si["color"].values[0] if not si.empty else "#9ca3af"
                subj_lbl = "Tasks" if row["subject"] == "Task Completion" else row["subject"]

                st.markdown(
                    f"<div style='background:#f4f5f7;border:1px solid #e5e7eb;"
                    f"border-radius:8px;padding:7px 12px;margin-bottom:5px;"
                    f"font-size:12px'>"
                    f"<span style='display:inline-block;width:7px;height:7px;"
                    f"border-radius:50%;background:{sc};margin-right:6px'></span>"
                    f"<b style='color:#111827'>{stu_name}</b>"
                    f"<span style='margin-left:6px;background:{gc}18;color:{gc};"
                    f"border-radius:4px;padding:1px 5px;font-size:9px;"
                    f"font-weight:700'>{stu_grd}</span>"
                    f"<span style='float:right;color:#9ca3af'>{subj_lbl} &nbsp;"
                    f"<b style='color:#111827'>{int(row['minutes'])}m</b>"
                    f"&nbsp; {str(row['date'])[5:]}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ── Team setup panel ───────────────────────────────────────────────────────────
def render_team_setup(db: SheetsDB, staff_df: pd.DataFrame):
    st.subheader("Team Setup — Edit Staff Names")
    with st.form("staff_form"):
        new_names: dict = {}
        for _, row in staff_df.iterrows():
            c_dot, c_inp = st.columns([1, 10])
            with c_dot:
                st.markdown(
                    f"<div style='width:12px;height:12px;border-radius:50%;"
                    f"background:{row['color']};margin-top:34px'></div>",
                    unsafe_allow_html=True,
                )
            with c_inp:
                new_names[row["id"]] = st.text_input(
                    label=f"staff_{row['id']}",
                    value=row["name"],
                    key=f"sname_{row['id']}",
                    label_visibility="collapsed",
                )
        if st.form_submit_button("Save Changes", use_container_width=True):
            db.update_staff_names(new_names)
            st.success("✓ Staff names updated!")
            refresh()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    inject_css()

    db          = get_db()
    students_df = load_students(db)
    logs_df     = load_logs(db)
    staff_df    = load_staff(db)

    # ── App header ─────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:4px'>"
        "<div style='width:32px;height:32px;background:#4f46e5;border-radius:8px;"
        "display:flex;align-items:center;justify-content:center;"
        "color:white;font-weight:800;font-size:16px'>I</div>"
        "<span style='font-size:20px;font-weight:800;color:#111827;"
        "letter-spacing:-0.5px'>IEP Minute Pro</span></div>",
        unsafe_allow_html=True,
    )
    st.caption("Monitoring service delivery — " + date.today().strftime("%B %Y"))

    # ── Tabs ───────────────────────────────────────────────────────────────────
    tab_dash, tab_log, tab_add, tab_team = st.tabs(
        ["📊 Dashboard", "✏️ Log Session", "➕ Add Student", "👥 Team Setup"]
    )

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    with tab_dash:
        week_start, week_end     = get_week_range()
        month_start, month_end   = get_month_range()

        st.markdown("### Team Tracker")

        # Summary rows inside white containers
        with st.container(border=True):
            render_summary_row("This Week",  logs_df, staff_df, week_start, week_end)
        with st.container(border=True):
            render_summary_row("This Month", logs_df, staff_df, month_start, month_end)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Goal-hit line chart
        with st.container(border=True):
            render_goal_chart(logs_df, students_df)

        st.markdown("---")

        # Student cards header + grade filter
        hdr_col, flt_col = st.columns([2, 2])
        with hdr_col:
            st.markdown("### Individual Student Progress")
        with flt_col:
            grade_filter = st.radio(
                "Filter by grade",
                ["All"] + GRADES,
                horizontal=True,
                label_visibility="collapsed",
                key="dash_grade_filter",
            )

        vis_students = (
            students_df
            if grade_filter == "All"
            else students_df[students_df["grade"] == grade_filter]
        )

        if vis_students.empty:
            msg = (
                "No students yet — go to **Add Student** to get started."
                if students_df.empty
                else f"No {grade_filter} grade students."
            )
            st.info(msg)
        else:
            # Responsive 3-column grid
            n_cols  = 3
            student_list = list(vis_students.iterrows())
            for row_start in range(0, len(student_list), n_cols):
                row_items = student_list[row_start : row_start + n_cols]
                cols      = st.columns(n_cols)
                for col_idx, (_, student) in enumerate(row_items):
                    with cols[col_idx]:
                        render_student_card(student, logs_df, staff_df, db)

    # ══════════════════════════════════════════════════════════════════════════
    # LOG SESSION
    # ══════════════════════════════════════════════════════════════════════════
    with tab_log:
        render_log_session(db, students_df, staff_df, logs_df)

    # ══════════════════════════════════════════════════════════════════════════
    # ADD STUDENT
    # ══════════════════════════════════════════════════════════════════════════
    with tab_add:
        render_add_student(db)

    # ══════════════════════════════════════════════════════════════════════════
    # TEAM SETUP
    # ══════════════════════════════════════════════════════════════════════════
    with tab_team:
        render_team_setup(db, staff_df)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
