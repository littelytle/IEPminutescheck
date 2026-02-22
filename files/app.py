"""
IEP Minute Pro — Streamlit App
RESTORATION VERSION: All 700+ lines of logic preserved.
Only SyntaxErrors (quote nesting) have been corrected.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta, datetime
import json

from sheets_db import SheetsDB

# ── Page config ────────────────────────────────────────────────────────────────
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
    "English":          "#8b5cf6",
    "Task Completion":  "#10b981",
}
GRADE_COLOR = {
    "6th": "#f59e0b",
    "7th": "#6366f1",
    "8th": "#10b981",
}
STAFF_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#ec4899"]

# ── Styling (Full CSS Restoration) ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}
.stApp {
    background-color: #f4f5f7;
}
/* Sidebar */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e5e7eb;
}
/* Buttons */
.stButton > button {
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    border: 1px solid #e5e7eb;
    background: #ffffff;
    color: #4b5563;
}
.stButton > button:hover {
    border-color: #4f46e5;
    color: #4f46e5;
    background: #eef2ff;
}
/* Primary buttons */
.primary-btn > button {
    background: #4f46e5 !important;
    color: white !important;
    border: none !important;
}
.primary-btn > button:hover {
    background: #4338ca !important;
}
.green-btn > button {
    background: #10b981 !important;
    color: white !important;
    border: none !important;
}
/* Cards */
.student-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.student-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.10);
    border-color: #d1d5db;
}
/* Metric cards */
.metric-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
/* Grade badges */
.grade-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 700;
}
/* Progress bars */
.prog-bar-wrap {
    background: #f3f4f6;
    border-radius: 6px;
    height: 10px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
    display: flex;
}
/* Section headers */
h1 { font-weight: 800 !important; letter-spacing: -0.5px !important; }
h2 { font-weight: 700 !important; }
h3 { font-weight: 600 !important; }
/* Expander */
details summary {
    font-size: 13px;
    color: #6b7280;
}
/* Streamlit form */
.stForm {
    background: white;
    padding: 16px;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
}
/* Hide default streamlit menu/footer */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Nav pill tabs */
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] > div > div > .stButton > button {
    width: 100%;
}
</style>
""", unsafe_allow_html=True)


# ── DB connection ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return SheetsDB()


def refresh():
    """Force re-fetch from Sheets on next render."""
    for key in ["students_df", "logs_df", "staff_df"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


# ── Cached data loaders ────────────────────────────────────────────────────────
def load_students(db: SheetsDB) -> pd.DataFrame:
    if "students_df" not in st.session_state:
        st.session_state.students_df = db.get_students()
    return st.session_state.students_df


def load_logs(db: SheetsDB) -> pd.DataFrame:
    if "logs_df" not in st.session_state:
        st.session_state.logs_df = db.get_logs()
    return st.session_state.logs_df


def load_staff(db: SheetsDB) -> pd.DataFrame:
    if "staff_df" not in st.session_state:
        st.session_state.staff_df = db.get_staff()
    return st.session_state.staff_df


# ── Date helpers ───────────────────────────────────────────────────────────────
def get_week_range(ref: date = None):
    ref = ref or date.today()
    mon = ref - timedelta(days=ref.weekday())
    sun = mon + timedelta(days=6)
    return mon, sun


def get_month_range(ref: date = None):
    ref = ref or date.today()
    first = ref.replace(day=1)
    if ref.month == 12:
        last = ref.replace(year=ref.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    return first, last


def get_month_weeks(ref: date = None):
    """Return list of (label, start, end) for each Mon-Sun week overlapping the month."""
    ref = ref or date.today()
    first = ref.replace(day=1)
    if ref.month == 12:
        last = ref.replace(year=ref.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    weeks = []
    cur = first - timedelta(days=first.weekday())  # rewind to Monday
    while cur <= last:
        w_end = cur + timedelta(days=6)
        label = f"{cur.month}/{cur.day}–{w_end.month}/{w_end.day}"
        weeks.append((label, cur, w_end))
        cur += timedelta(days=7)
    return weeks


def logs_in_range(logs_df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if logs_df.empty:
        return logs_df
    d = pd.to_datetime(logs_df["date"]).dt.date
    return logs_df[(d >= start) & (d <= end)]


def student_minutes(logs_df: pd.DataFrame, student_id, subject: str,
                    start: date, end: date) -> int:
    subset = logs_in_range(logs_df, start, end)
    subset = subset[(subset["student_id"] == student_id) & (subset["subject"] == subject)]
    return int(subset["minutes"].sum()) if not subset.empty else 0


def staff_minutes_breakdown(logs_df: pd.DataFrame, student_id, subject: str,
                             start: date, end: date, staff_df: pd.DataFrame) -> dict:
    subset = logs_in_range(logs_df, start, end)
    subset = subset[(subset["student_id"] == student_id) & (subset["subject"] == subject)]
    result = {name: 0 for name in staff_df["name"].tolist()}
    for _, row in subset.iterrows():
        if row["staff"] in result:
            result[row["staff"]] += int(row["minutes"])
    return result


# ── Summary metric row ─────────────────────────────────────────────────────────
def render_summary_row(label: str, logs_df: pd.DataFrame, staff_df: pd.DataFrame,
                        start: date, end: date):
    subset = logs_in_range(logs_df, start, end)
    grand_total = int(subset["minutes"].sum()) if not subset.empty else 0

    cols = st.columns([1] + [2] * len(staff_df) + [1])

    with cols[0]:
        st.markdown(
            f"<div style='font-size:10px;font-weight:700;color:#4f46e5;"
            f"text-transform:uppercase;letter-spacing:1.2px;padding-top:6px'>{label}</div>",
            unsafe_allow_html=True,
        )

    for i, (_, staff) in enumerate(staff_df.iterrows()):
        name = staff["name"]
        color = staff["color"]
        mins = int(subset[subset["staff"] == name]["minutes"].sum()) if not subset.empty else 0
        with cols[i + 1]:
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:5px;font-size:11px;color:#4b5563'>"
                f"<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:{color}'></span>"
                f"{name.split()[-1]}: <b style='color:#111827'>{mins}m</b></div>",
                unsafe_allow_html=True,
            )

    with cols[-1]:
        st.markdown(
            f"<div style='text-align:right;font-size:13px;font-weight:700;color:#111827;padding-top:4px'>"
            f"{grand_total}m total</div>",
            unsafe_allow_html=True,
        )


# ── Progress bar HTML ──────────────────────────────────────────────────────────
def progress_bar_html(by_staff: dict, staff_df: pd.DataFrame, goal: int) -> str:
    total = sum(by_staff.values())
    segs_html = ""
    for _, row in staff_df.iterrows():
        name = row["name"]
        color = row["color"]
        mins = by_staff.get(name, 0)
        if mins > 0:
            pct = min(mins / goal * 100, 100)
            segs_html += (
                f"<div title='{name}: {mins}m' style='width:{pct}%;background:{color};"
                f"height:100%;display:inline-block'></div>"
            )
    pct_label = min(int(total / goal * 100), 100) if goal > 0 else 0
    goal_color = "#10b981" if total >= goal else "#9ca3af"
    return f"""
    <div style='background:#f3f4f6;border-radius:6px;height:10px;overflow:hidden;border:1px solid #e5e7eb;display:flex;margin-bottom:3px'>
        {segs_html}
    </div>
    <div style='display:flex;justify-content:space-between;font-size:10px;color:#9ca3af'>
        <span>{total}m / {goal}m</span>
        <span style='color:{goal_color};font-weight:{"600" if total >= goal else "400"}'>{pct_label}%</span>
    </div>
    """


# ── Goal-hit line chart ────────────────────────────────────────────────────────
def render_goal_chart(logs_df: pd.DataFrame, students_df: pd.DataFrame):
    weeks = get_month_weeks()
    chart_data = []

    for label, w_start, w_end in weeks:
        row = {"Week": label}
        for subj in SUBJECTS:
            count = 0
            for _, stu in students_df.iterrows():
                sid = stu["id"]
                goal = int(stu.get(f"goal_{subj.lower().replace(' ', '_')}", 60))
                total = student_minutes(logs_df, sid, subj, w_start, w_end)
                if total >= goal:
                    count += 1
            row[subj] = count
        chart_data.append(row)

    df_chart = pd.DataFrame(chart_data)

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
            hovertemplate=f"<b>{subj}</b><br>%{{x}}<br>%{{y}} students hit goal<extra></extra>",
        ))

    max_y = max(len(students_df), 1)
    fig.update_layout(
        title=dict(
            text="<b>Weekly Goal Progress</b><br><span style='font-size:11px;color:#9ca3af'>"
                  "Students hitting their weekly minutes goal, by subject</span>",
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
        xaxis=dict(
            gridcolor="#f3f4f6",
            title="",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11),
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        height=280,
        font=dict(family="Inter"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Student card ───────────────────────────────────────────────────────────────
def render_student_card(student: pd.Series, logs_df: pd.DataFrame,
                        staff_df: pd.DataFrame, db: SheetsDB):
    sid = student["id"]
    name = student["name"]
    grade = student["grade"]
    gc = GRADE_COLOR.get(grade, "#9ca3af")

    week_start, week_end = get_week_range()
    active_subj = student.get("active_subject", "Math")
    
    # FIX: Changed quote nesting to avoid SyntaxError
    top_bar_color = SUBJ_COLOR.get(active_subj, '#6366f1')

    with st.container():
        st.markdown(
            f"<div style='height:3px;background:{top_bar_color};border-radius:3px 3px 0 0;margin-bottom:0'></div>",
            unsafe_allow_html=True,
        )

        # Name + grade header
        col_name, col_del = st.columns([6, 1])
        with col_name:
            st.markdown(
                f"<span style='background:{gc}18;color:{gc};font-size:10px;font-weight:700;"
                f"border-radius:4px;padding:2px 7px'>{grade}</span>&nbsp;"
                f"<b style='font-size:13px;color:#111827'>{name}</b>",
                unsafe_allow_html=True,
            )
        with col_del:
            if st.button("×", key=f"del_{sid}", help="Remove student"):
                db.delete_student(sid)
                refresh()

        # Subject tabs
        subj_cols = st.columns(3)
        for i, subj in enumerate(SUBJECTS):
            with subj_cols[i]:
                label = "Tasks" if subj == "Task Completion" else subj
                if st.button(label, key=f"subj_{sid}_{subj}",
                             use_container_width=True):
                    db.update_student_subject(sid, subj)
                    refresh()

        goal_col_name = f"goal_{active_subj.lower().replace(' ', '_')}"
        goal = int(student.get(goal_col_name, 60))

        # Progress bar
        by_staff = staff_minutes_breakdown(logs_df, sid, active_subj,
                                           week_start, week_end, staff_df)
        total_mins = sum(by_staff.values())
        goal_met = total_mins >= goal

        if goal_met:
            st.markdown("✅ **Weekly goal met!**")

        st.markdown(progress_bar_html(by_staff, staff_df, goal),
                    unsafe_allow_html=True)

        # Staff chips
        chips_html = ""
        for _, s in staff_df.iterrows():
            m = by_staff.get(s["name"], 0)
            if m > 0:
                # FIX: Used single quotes for keys inside f-string
                s_color = s['color']
                chips_html += (
                    f"<span style='display:inline-flex;align-items:center;gap:3px;"
                    f"background:#f4f5f7;border:1px solid #e5e7eb;border-radius:4px;"
                    f"padding:2px 6px;font-size:9px;color:#4b5563;margin:2px'>"
                    f"<span style='display:inline-block;width:5px;height:5px;"
                    f"border-radius:50%;background:{s_color}'></span>"
                    f"{s['name'].split()[-1]}: {m}m</span>"
                )
        if chips_html:
            st.markdown(chips_html, unsafe_allow_html=True)

        # Goal edit
        with st.expander("⚙ Edit Goal / Name"):
            new_name = st.text_input("Name", value=name, key=f"name_{sid}")
            new_goal = st.number_input(
                f"{active_subj} weekly goal (min)", value=goal, min_value=1, key=f"goal_{sid}"
            )
            if st.button("Save", key=f"save_{sid}"):
                db.update_student(sid, new_name, {active_subj: int(new_goal)})
                refresh()

        # Notes
        with st.expander(f"📝 Show Notes"):
            notes = logs_df[
                (logs_df["student_id"] == sid) &
                (logs_df["subject"] == active_subj) &
                (logs_df["note"].notna()) &
                (logs_df["note"] != "")
            ].sort_values("date", ascending=False)

            if notes.empty:
                st.caption(f"No notes for {active_subj}")
            else:
                for _, note_row in notes.iterrows():
                    staff_info = staff_df[staff_df["name"] == note_row["staff"]]
                    color = staff_info["color"].values[0] if not staff_info.empty else "#9ca3af"
                    st.markdown(
                        f"<div style='background:#f4f5f7;border:1px solid #e5e7eb;"
                        f"border-radius:7px;padding:7px 10px;margin-bottom:5px'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:3px'>"
                        f"<span style='font-size:10px;color:#4b5563'>"
                        f"<span style='display:inline-block;width:5px;height:5px;border-radius:50%;"
                        f"background:{color};margin-right:4px'></span>"
                        f"{note_row['staff'].split()[-1]}</span>"
                        f"<span style='font-size:10px;color:#9ca3af'>{str(note_row['date'])[5:]}</span>"
                        f"</div>"
                        f"<p style='font-size:11px;color:#4b5563;margin:0'>{note_row['note']}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        st.markdown("---")


# ── Add student panel ──────────────────────────────────────────────────────────
def render_add_student(db: SheetsDB):
    st.subheader("Add Student")
    with st.form("add_student_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            name = st.text_input("Student Name", placeholder="Full name…")
        with col2:
            grade = st.selectbox("Grade", GRADES)

        st.markdown("**Weekly Goals (minutes)**")
        g_cols = st.columns(3)
        goals = {}
        defaults = {"Math": 60, "English": 90, "Task Completion": 45}
        for i, subj in enumerate(SUBJECTS):
            with g_cols[i]:
                label = "Tasks" if subj == "Task Completion" else subj
                goals[subj] = st.number_input(f"{label}", value=defaults[subj],
                                               min_value=1, key=f"new_goal_{subj}")

        submitted = st.form_submit_button("+ Add Student", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Please enter a student name.")
            else:
                db.add_student(name.strip(), grade, goals)
                st.success(f"✓ {name} added!")
                refresh()


# ── Log session panel ──────────────────────────────────────────────────────────
def render_log_session(db: SheetsDB, students_df: pd.DataFrame,
                        staff_df: pd.DataFrame, logs_df: pd.DataFrame):
    st.subheader("Log Session")

    col_form, col_recent = st.columns([1, 1], gap="large")

    with col_form:
        with st.form("log_session_form"):
            fc1, fc2 = st.columns(2)
            with fc1:
                grade_filter = st.selectbox("Grade", ["— select —"] + GRADES, key="log_grade")
            with fc2:
                subject = st.selectbox("Subject", SUBJECTS, key="log_subject")

            fc3, fc4 = st.columns(2)
            with fc3:
                staff_options = staff_df["name"].tolist()
                staff_sel = st.selectbox("Staff", ["— select —"] + staff_options, key="log_staff")
            with fc4:
                minutes = st.number_input("Minutes", min_value=1, value=30, key="log_minutes")

            log_date = st.date_input("Date", value=date.today(), key="log_date")

            if grade_filter != "— select —":
                grade_students = students_df[students_df["grade"] == grade_filter]
                if grade_students.empty:
                    st.info(f"No students in {grade_filter} grade yet.")
                    student_ids = []
                else:
                    st.markdown(f"**{grade_filter} Grade Students** — select one or more:")
                    selected_ids = []
                    for _, stu in grade_students.iterrows():
                        checked = st.checkbox(
                            f"{stu['name']}",
                            key=f"log_stu_{stu['id']}",
                        )
                        if checked:
                            selected_ids.append(stu['id'])
                    student_ids = selected_ids
            else:
                st.info("Select a grade to see students.")
                student_ids = []

            note = st.text_area("Notes (optional)", placeholder="What did you work on?",
                                key="log_note")

            n_sel = len(student_ids)
            btn_label = f"Log {n_sel} Student{'s' if n_sel != 1 else ''} ✓" if n_sel > 0 else "Log Session ✓"
            submitted = st.form_submit_button(btn_label, use_container_width=True)

            if submitted:
                if grade_filter == "— select —" or staff_sel == "— select —":
                    st.error("Please select a grade and staff member.")
                elif n_sel == 0:
                    st.error("Select at least one student.")
                else:
                    for sid in student_ids:
                        db.add_log(
                            student_id=sid,
                            subject=subject,
                            staff=staff_sel,
                            minutes=int(minutes),
                            log_date=str(log_date),
                            note=note,
                        )
                    st.success(f"✓ Logged {n_sel} students!")
                    refresh()

    with col_recent:
        st.markdown("**Recent Sessions**")
        if logs_df.empty:
            st.caption("No sessions logged yet.")
        else:
            recent = logs_df.sort_values("date", ascending=False).head(8)
            for _, row in recent.iterrows():
                stu = students_df[students_df["id"] == row["student_id"]]
                stu_name = stu["name"].values[0] if not stu.empty else "Unknown"
                stu_grade = stu["grade"].values[0] if not stu.empty else ""
                gc = GRADE_COLOR.get(stu_grade, "#9ca3af")
                staff_info = staff_df[staff_df["name"] == row["staff"]]
                sc = staff_info["color"].values[0] if not staff_info.empty else "#9ca3af"
                subj_label = "Tasks" if row["subject"] == "Task Completion" else row["subject"]
                st.markdown(
                    f"<div style='background:#f4f5f7;border:1px solid #e5e7eb;border-radius:8px;"
                    f"padding:7px 12px;margin-bottom:5px;display:flex;align-items:center;gap:8px;"
                    f"font-size:12px'>"
                    f"<span style='display:inline-block;width:7px;height:7px;border-radius:50%;"
                    f"background:{sc};flex-shrink:0'></span>"
                    f"<span style='flex:1;font-weight:500;color:#111827'>{stu_name}</span>"
                    f"<span style='background:{gc}18;color:{gc};border-radius:4px;padding:1px 5px;"
                    f"font-size:9px;font-weight:700'>{stu_grade}</span>"
                    f"<span style='color:#9ca3af;font-size:10px'>{subj_label}</span>"
                    f"<span style='font-weight:600;color:#111827'>{int(row['minutes'])}m</span>"
                    f"<span style='color:#9ca3af;font-size:10px'>{str(row['date'])[5:]}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ── Team setup panel ───────────────────────────────────────────────────────────
def render_team_setup(db: SheetsDB, staff_df: pd.DataFrame):
    st.subheader("Team Setup — Edit Staff Names")
    with st.form("staff_form"):
        new_names = {}
        for _, row in staff_df.iterrows():
            color = row["color"]
            col_dot, col_inp = st.columns([1, 8])
            with col_dot:
                st.markdown(
                    f"<div style='width:12px;height:12px;border-radius:50%;"
                    f"background:{color};margin-top:30px'></div>",
                    unsafe_allow_html=True,
                )
            with col_inp:
                new_names[row["id"]] = st.text_input(
                    f"Staff {row['id']}",
                    value=row["name"],
                    key=f"staff_name_{row['id']}",
                    label_visibility="collapsed",
                )
        if st.form_submit_button("Save Changes", use_container_width=True):
            db.update_staff_names(new_names)
            st.success("✓ Staff names updated!")
            refresh()


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    db = get_db()
    students_df = load_students(db)
    logs_df     = load_logs(db)
    staff_df    = load_staff(db)

    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:4px'>"
        "<div style='width:32px;height:32px;background:#4f46e5;border-radius:8px;"
        "display:flex;align-items:center;justify-content:center;"
        "color:white;font-weight:800;font-size:16px'>I</div>"
        "<span style='font-size:20px;font-weight:800;color:#111827;letter-spacing:-0.5px'>"
        "IEP Minute Pro</span></div>",
        unsafe_allow_html=True,
    )
    st.caption("Monitoring service delivery — " + date.today().strftime("%B %Y"))

    tab_dashboard, tab_log, tab_add, tab_team = st.tabs(
        ["📊 Dashboard", "✏️ Log Session", "➕ Add Student", "👥 Team Setup"]
    )

    with tab_dashboard:
        week_start, week_end   = get_week_range()
        month_start, month_end = get_month_range()
        st.markdown("### Team Tracker")
        with st.container():
            st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
            render_summary_row("This Week", logs_df, staff_df, week_start, week_end)
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        with st.container():
            st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
            render_summary_row("This Month", logs_df, staff_df, month_start, month_end)
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        render_goal_chart(logs_df, students_df)
        st.markdown("---")
        col_header, col_filters = st.columns([2, 2])
        with col_header: st.markdown("### Individual Student Progress")
        with col_filters:
            grade_filter = st.radio("Filter by grade", ["All"] + GRADES, horizontal=True, label_visibility="collapsed")
        
        vis_students = students_df if grade_filter == "All" else students_df[students_df["grade"] == grade_filter]
        
        if vis_students.empty:
            st.info("No students found.")
        else:
            n_cols = 3
            rows = [vis_students.iloc[i:i+n_cols] for i in range(0, len(vis_students), n_cols)]
            for row_df in rows:
                cols = st.columns(n_cols)
                for j, (_, student) in enumerate(row_df.iterrows()):
                    with cols[j]:
                        render_student_card(student, logs_df, staff_df, db)

    with tab_log: render_log_session(db, students_df, staff_df, logs_df)
    with tab_add: render_add_student(db)
    with tab_team: render_team_setup(db, staff_df)

if __name__ == "__main__":
    main()
