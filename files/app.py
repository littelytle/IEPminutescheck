"""
IEP Minute Pro — Streamlit App
Full Logic Restored | Fixed Session State Error | Refined UI Hierarchy
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="IEP Minute Pro", page_icon="📋",
                   layout="wide", initial_sidebar_state="collapsed")

SUBJECTS     = ["Math", "English", "Task Completion"]
GRADES       = ["6th", "7th", "8th"]
SCHOOL_MONTHS = [(8,"Aug"),(9,"Sep"),(10,"Oct"),(11,"Nov"),(12,"Dec"),
                  (1,"Jan"),(2,"Feb"),(3,"Mar"),(4,"Apr"),(5,"May")]
SUBJ_COLOR   = {"Math":"#4f46e5","English":"#7c3aed","Task Completion":"#10b981"}
SUBJ_SHORT   = {"Math":"M","English":"E","Task Completion":"T"}
GRADE_COLOR  = {"6th":"#f59e0b","7th":"#4f46e5","8th":"#10b981"}
GOAL_COL     = {"Math":"goal_math","English":"goal_english","Task Completion":"goal_task_completion"}
SCOPES       = ["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
DEFAULT_STAFF = [
    {"id":1,"name":"Ms. Rivera",  "color":"#6366f1"},
    {"id":2,"name":"Mr. Thompson","color":"#f59e0b"},
    {"id":3,"name":"Ms. Chen",    "color":"#10b981"},
    {"id":4,"name":"Mr. Davis",   "color":"#ef4444"},
    {"id":5,"name":"Ms. Patel",   "color":"#ec4899"},
]

# ── CALLBACKS (Fixes the Session State Error) ──────────────────────────────────
def cb_select_all(ids):
    for sid in ids:
        st.session_state[f"ls_stu_{sid}"] = True

def cb_select_none(ids):
    for sid in ids:
        st.session_state[f"ls_stu_{sid}"] = False

def cb_clear_log_selection(ids):
    for sid in ids:
        st.session_state[f"ls_stu_{sid}"] = False
    # Clear other form fields if needed
    st.session_state["ls_note"] = ""

# ── DB ────────────────────────────────────────────────────────────────────────
class SheetsDB:
    def __init__(self):
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(st.secrets["spreadsheet_id"])
        self._ensure_sheets()

    def _get_or_create_sheet(self, title, headers):
        try:
            return self.spreadsheet.worksheet(title)
        except WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
            ws.append_row(headers)
            return ws

    def _ensure_sheets(self):
        self.staff_ws    = self._get_or_create_sheet("staff",    ["id","name","color"])
        self.students_ws = self._get_or_create_sheet("students", ["id","name","grade","active_subject","goal_math","goal_english","goal_task_completion"])
        self.logs_ws     = self._get_or_create_sheet("logs",     ["id","student_id","subject","staff","minutes","date","note"])
        if not self.staff_ws.get_all_records():
            for s in DEFAULT_STAFF:
                self.staff_ws.append_row([s["id"],s["name"],s["color"]])

    def _next_id(self, ws):
        recs = ws.get_all_records()
        return max((int(r["id"]) for r in recs), default=0) + 1

    def _to_df(self, ws):
        recs = ws.get_all_records()
        return pd.DataFrame(recs) if recs else pd.DataFrame()

    def _find_row(self, ws, col, value):
        for i, rec in enumerate(ws.get_all_records()):
            if str(rec[col]) == str(value):
                return i + 2
        return None

    def get_staff(self):
        df = self._to_df(self.staff_ws)
        if df.empty: return pd.DataFrame(DEFAULT_STAFF)
        df["id"] = df["id"].astype(int)
        return df

    def update_staff_names(self, new_names):
        recs      = self.staff_ws.get_all_records()
        old_names = {r["id"]: r["name"] for r in recs}
        for sid, new_name in new_names.items():
            row = self._find_row(self.staff_ws, "id", sid)
            if row: self.staff_ws.update_cell(row, 2, new_name)
            old = old_names.get(int(sid), "")
            if old and old != new_name:
                log_recs = self.logs_ws.get_all_records()
                hdrs = self.logs_ws.row_values(1)
                sc   = hdrs.index("staff") + 1
                for i, r in enumerate(log_recs):
                    if r["staff"] == old:
                        self.logs_ws.update_cell(i+2, sc, new_name)

    def get_students(self):
        df = self._to_df(self.students_ws)
        if df.empty:
            return pd.DataFrame(columns=["id","name","grade","active_subject",
                                          "goal_math","goal_english","goal_task_completion"])
        df["id"] = df["id"].astype(int)
        for col in ["goal_math","goal_english","goal_task_completion"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(60).astype(int)
        return df

    def add_student(self, name, grade, goals):
        self.students_ws.append_row([
            self._next_id(self.students_ws), name, grade, "Math",
            goals.get("Math",60), goals.get("English",90), goals.get("Task Completion",45),
        ])

    def update_student(self, sid, new_name=None, goals=None):
        row = self._find_row(self.students_ws, "id", sid)
        if not row: return
        hdrs = self.students_ws.row_values(1)
        if new_name:
            self.students_ws.update_cell(row, hdrs.index("name")+1, new_name)
        if goals:
            cm = {"Math":"goal_math","English":"goal_english","Task Completion":"goal_task_completion"}
            for subj, val in goals.items():
                cn = cm.get(subj)
                if cn and cn in hdrs:
                    self.students_ws.update_cell(row, hdrs.index(cn)+1, val)

    def delete_student(self, sid):
        row = self._find_row(self.students_ws, "id", sid)
        if row: self.students_ws.delete_rows(row)

    def get_logs(self):
        df = self._to_df(self.logs_ws)
        if df.empty:
            return pd.DataFrame(columns=["id","student_id","subject","staff","minutes","date","note"])
        df["id"]         = pd.to_numeric(df["id"],         errors="coerce").astype("Int64")
        df["student_id"] = pd.to_numeric(df["student_id"], errors="coerce").astype("Int64")
        df["minutes"]    = pd.to_numeric(df["minutes"],    errors="coerce").fillna(0).astype(int)
        df["date"]       = pd.to_datetime(df["date"],      errors="coerce").dt.date
        df["note"]       = df["note"].fillna("")
        return df

    def add_log(self, student_id, subject, staff, minutes, log_date, note=""):
        self.logs_ws.append_row([
            self._next_id(self.logs_ws), int(student_id), subject, staff,
            int(minutes), str(log_date), note,
        ])


# ── PIVOT & FAST CALCULATIONS ──────────────────────────────────────────────────
def build_pivot(logs_df):
    if logs_df.empty:
        return pd.DataFrame(columns=["student_id","subject","staff","minutes","date"])
    return logs_df[["student_id","subject","staff","minutes","date"]].copy()

def pivot_minutes(pivot, student_id, subject, start, end):
    if pivot.empty: return 0
    m = (pivot["student_id"]==student_id) & (pivot["subject"]==subject) & \
        (pivot["date"]>=start) & (pivot["date"]<=end)
    return int(pivot.loc[m,"minutes"].sum())

def pivot_staff_breakdown(pivot, student_id, subject, start, end, staff_names):
    result = {n: 0 for n in staff_names}
    if pivot.empty: return result
    m   = (pivot["student_id"]==student_id) & (pivot["subject"]==subject) & \
          (pivot["date"]>=start) & (pivot["date"]<=end)
    sub = pivot.loc[m]
    for staff, grp in sub.groupby("staff"):
        if staff in result:
            result[staff] = int(grp["minutes"].sum())
    return result

def summary_data(pivot, staff_names, start, end):
    if pivot.empty: return 0, {n:0 for n in staff_names}
    m   = (pivot["date"]>=start) & (pivot["date"]<=end)
    sub = pivot.loc[m]
    return int(sub["minutes"].sum()), {
        n: int(sub.loc[sub["staff"]==n,"minutes"].sum()) for n in staff_names
    }

def chart_data(pivot, students_df, weeks):
    rows = []
    for label, w_start, w_end in weeks:
        row = {"Week": label}
        if not pivot.empty:
            m       = (pivot["date"]>=w_start) & (pivot["date"]<=w_end)
            week_g  = pivot.loc[m].groupby(["student_id","subject"])["minutes"].sum()
        else:
            week_g  = pd.Series(dtype=int)
        for subj in SUBJECTS:
            count = sum(
                1 for _, stu in students_df.iterrows()
                if int(week_g.get((stu["id"],subj), 0)) >= safe_goal(stu, subj)
            )
            row[subj] = count
        rows.append(row)
    return pd.DataFrame(rows)


# ── HELPERS ────────────────────────────────────────────────────────────────────
def safe_goal(student, subject):
    col = GOAL_COL.get(subject, "goal_math")
    try: return int(student[col]) if col in student.index else 60
    except: return 60

def school_year_for(d):
    return d.year if d.month >= 8 else d.year - 1

def month_weeks(year, month):
    first = date(year, month, 1)
    last  = date(year+1,1,1)-timedelta(1) if month==12 else date(year,month+1,1)-timedelta(1)
    weeks, cur = [], first - timedelta(days=first.weekday())
    while cur <= last:
        mon, fri = cur, cur+timedelta(4)
        weeks.append((f"{mon.month}/{mon.day}–{fri.month}/{fri.day}", mon, mon+timedelta(6)))
        cur += timedelta(7)
    return weeks

def month_range(year, month):
    first = date(year, month, 1)
    last  = date(year+1,1,1)-timedelta(1) if month==12 else date(year,month+1,1)-timedelta(1)
    return first, last


# ── CSS ────────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
*,*::before,*::after{box-sizing:border-box}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important}
.stApp{background-color:#f8fafc!important}

/* Student Card Hierarchy */
.student-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
}
.student-name {
    font-size: 1.5rem !important;
    font-weight: 900 !important;
    color: #0f172a !important;
    letter-spacing: -0.04em !important;
    line-height: 1 !important;
}
.student-minutes {
    font-size: 1.5rem !important;
    font-weight: 400 !important;
    color: #64748b !important;
    letter-spacing: -0.04em !important;
}
.student-minutes b {
    color: #0f172a !important;
    font-weight: 900 !important;
}

/* Progress Bar */
.progress-container {
    background: #f1f5f9;
    border-radius: 999px;
    height: 12px;
    overflow: hidden;
    margin: 1rem 0;
}
.progress-fill {
    height: 100%;
    border-radius: 999px;
    transition: width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Note Styling */
.latest-note {
    background: #f8fafc;
    border-left: 3px solid #e2e8f0;
    padding: 0.75rem 1rem;
    border-radius: 0 8px 8px 0;
    margin-top: 1rem;
    font-size: 0.875rem;
    color: #475569;
    line-height: 1.5;
}
.note-meta {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 4px;
}

/* Selectors */
.stButton>button{border-radius:8px!important;font-family:'Inter',sans-serif!important;font-weight:600!important;border:1.5px solid #e5e7eb!important;background:#fff!important;color:#374151!important;-webkit-text-fill-color:#374151!important;transition:all 0.15s!important;min-height:40px!important}
.stButton>button:hover{border-color:#4f46e5!important;color:#4f46e5!important;-webkit-text-fill-color:#4f46e5!important;background:#eef2ff!important}

div[data-testid="stMarkdownContainer"] > p { margin-bottom: 0 !important; }
#MainMenu{visibility:hidden}footer{visibility:hidden}header{visibility:hidden}
</style>""", unsafe_allow_html=True)


# ── SESSION STATE ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_db(): return SheetsDB()

def refresh():
    for k in ("students_df","logs_df","staff_df","pivot"):
        st.session_state.pop(k, None)
    st.rerun()

def load_students(db):
    if "students_df" not in st.session_state:
        st.session_state["students_df"] = db.get_students()
    return st.session_state["students_df"]

def load_logs(db):
    if "logs_df" not in st.session_state:
        st.session_state["logs_df"] = db.get_logs()
    return st.session_state["logs_df"]

def load_staff(db):
    if "staff_df" not in st.session_state:
        st.session_state["staff_df"] = db.get_staff()
    return st.session_state["staff_df"]

def load_pivot(logs_df):
    if "pivot" not in st.session_state:
        st.session_state["pivot"] = build_pivot(logs_df)
    return st.session_state["pivot"]


# ── PROGRESS BAR ──────────────────────────────────────────────────────────────
def progress_bar_html(by_staff, staff_df, goal):
    total = sum(by_staff.values())
    segs  = ""
    for _, r in staff_df.iterrows():
        m = by_staff.get(r["name"], 0)
        if m > 0 and goal > 0:
            pct   = min(m / goal * 100, 100)
            name  = r["name"]
            color = r["color"]
            segs += (
                "<div title='" + name + ": " + str(m) + "m' style='width:" +
                f"{pct:.1f}" + "%;background:" + color +
                ";height:100%;display:inline-block'></div>"
            )
    return (
        "<div class='progress-container'>" + segs + "</div>"
    )


# ── SUMMARY ROW ───────────────────────────────────────────────────────────────
def render_summary_row(label, pivot, staff_df, start, end):
    grand, by_s = summary_data(pivot, staff_df["name"].tolist(), start, end)
    cols = st.columns([1] + [2]*len(staff_df) + [1])
    cols[0].markdown(
        "<div style='font-size:10px;font-weight:700;color:#4f46e5;"
        "text-transform:uppercase;letter-spacing:1.2px;padding-top:6px'>"
        + label + "</div>", unsafe_allow_html=True)
    for i, (_, sr) in enumerate(staff_df.iterrows()):
        m     = by_s.get(sr["name"], 0)
        color = sr["color"]
        lname = sr["name"].split()[-1]
        cols[i+1].markdown(
            "<div style='display:flex;align-items:center;gap:4px;font-size:11px;color:#4b5563'>"
            "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:"
            + color + "'></span>" + lname + ": <b style='color:#111827'>" + str(m) + "m</b></div>",
            unsafe_allow_html=True)
    cols[-1].markdown(
        "<div style='text-align:right;font-size:13px;font-weight:700;color:#111827;padding-top:4px'>"
        + str(grand) + "m</div>", unsafe_allow_html=True)


# ── GOAL CHART ────────────────────────────────────────────────────────────────
def render_goal_chart(pivot, students_df, year, mo):
    weeks    = month_weeks(year, mo)
    df_chart = chart_data(pivot, students_df, weeks)
    maxy     = max(len(students_df), 1)
    fig      = go.Figure()
    for subj in SUBJECTS:
        lbl = "Tasks" if subj == "Task Completion" else subj
        fig.add_trace(go.Scatter(
            x=df_chart["Week"], y=df_chart[subj],
            mode="lines+markers", name=lbl,
            line=dict(color=SUBJ_COLOR[subj], width=2.5),
            marker=dict(size=9, color=SUBJ_COLOR[subj], line=dict(width=2, color="white")),
            hovertemplate="<b>" + lbl + "</b><br>%{x}<br>%{y} students hit goal<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text="<b>Weekly Goal Progress</b>",
                   font=dict(size=14,family="Inter"), x=0, xanchor="left"),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(range=[-0.2,maxy+0.5], tickvals=list(range(maxy+1)),
                   gridcolor="#f3f4f6", zeroline=False,
                   title="Students hitting goal", title_font=dict(size=11,color="#9ca3af")),
        xaxis=dict(gridcolor="#f3f4f6", title="", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=10,r=10,t=60,b=10), height=260,
        font=dict(family="Inter"), hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── STUDENT CARD ──────────────────────────────────────────────────────────────
def render_student_card(student, pivot, logs_df, staff_df, db,
                         active_subj, view_start, view_end, key_pfx=""):
    sid         = student["id"]
    name        = str(student["name"])
    grade       = str(student["grade"])
    gc          = GRADE_COLOR.get(grade, "#9ca3af")
    goal        = safe_goal(student, active_subj)
    staff_names = staff_df["name"].tolist()

    by_staff  = pivot_staff_breakdown(pivot, sid, active_subj, view_start, view_end, staff_names)
    total_min = sum(by_staff.values())
    color = SUBJ_COLOR.get(active_subj, "#4f46e5")

    # Card Container
    st.markdown(f"""
    <div class="student-card">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <div class="student-name">{name}</div>
            <div class="student-minutes"><b>{total_min}</b> / {goal}m</div>
        </div>
    """, unsafe_allow_html=True)

    # Progress Bar
    st.markdown(progress_bar_html(by_staff, staff_df, goal), unsafe_allow_html=True)

    # Latest Note (Instant context)
    student_notes = logs_df[(logs_df["student_id"] == sid) & (logs_df["note"] != "")].sort_values("date", ascending=False)
    if not student_notes.empty:
        latest = student_notes.iloc[0]
        st.markdown(f"""
        <div class="latest-note">
            <div class="note-meta">{latest['date'].strftime('%b %d')} • {latest['staff']}</div>
            {latest['note']}
        </div>
        """, unsafe_allow_html=True)
        
        # History Expander (Collapsed by default)
        if len(student_notes) > 1:
            with st.expander("History"):
                for _, row in student_notes.iloc[1:].iterrows():
                    st.markdown(f"**{row['date'].strftime('%b %d')}**: {row['note']} ({row['staff']})")
    else:
        st.markdown("<div style='font-size: 0.75rem; color: #94a3b8; margin-top: 0.5rem;'>No notes recorded.</div>", unsafe_allow_html=True)

    # Edit Pencil (Subtle management)
    edit_col1, edit_col2 = st.columns([10, 1])
    with edit_col2:
        if st.button("✏️", key=f"edit_btn_{key_pfx}_{sid}"):
            st.session_state[f"editing_{sid}"] = not st.session_state.get(f"editing_{sid}", False)
    
    if st.session_state.get(f"editing_{sid}"):
        with st.form(f"edit_form_{sid}"):
            nn = st.text_input("Name", value=name)
            ng = st.number_input(f"{active_subj} Goal", value=goal)
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Save"):
                db.update_student(sid, nn, {active_subj: int(ng)})
                refresh()
            if c2.form_submit_button("🗑️ Remove"):
                db.delete_student(sid)
                refresh()

    st.markdown("</div>", unsafe_allow_html=True)


# ── ADD STUDENT ───────────────────────────────────────────────────────────────
def render_add_student(db):
    st.subheader("Add Student")
    with st.form("add_student_form", clear_on_submit=True):
        c1, c2 = st.columns([3,1])
        with c1: name  = st.text_input("Student Name", placeholder="Full name")
        with c2: grade = st.selectbox("Grade", GRADES)
        st.markdown("**Weekly Goals (minutes)**")
        defaults = {"Math":60,"English":90,"Task Completion":45}
        gcols = st.columns(3)
        goals = {}
        for i, subj in enumerate(SUBJECTS):
            with gcols[i]:
                lbl = "Tasks" if subj == "Task Completion" else subj
                goals[subj] = st.number_input(lbl + " (min/wk)", value=defaults[subj],
                                               min_value=1, key="ng_" + subj)
        if st.form_submit_button("+ Add Student", use_container_width=True):
            if not name.strip():
                st.error("Please enter a student name.")
            else:
                db.add_student(name.strip(), grade, {k:int(v) for k,v in goals.items()})
                st.success("Added " + name.strip())
                refresh()


# ── LOG SESSION ───────────────────────────────────────────────────────────────
def render_log_session(db, students_df, staff_df, logs_df):
    st.subheader("Log Session")

    if st.session_state.get("log_success_msg"):
        st.markdown(
            "<div style='background:#d1fae5;border:1px solid #10b981;border-radius:8px;padding:12px 16px;color:#065f46;font-weight:600;font-size:14px;margin-bottom:10px'>" 
            + st.session_state["log_success_msg"] + "</div>",
            unsafe_allow_html=True)
        if st.session_state.get("log_success_clear"):
            st.session_state["log_success_msg"]   = ""
            st.session_state["log_success_clear"] = False
        else:
            st.session_state["log_success_clear"] = True

    col_form, col_recent = st.columns([1,1], gap="large")
    with col_form:
        r1, r2 = st.columns(2)
        with r1: grade_sel = st.selectbox("Grade",   ["select"]+GRADES,                    key="ls_grade")
        with r2: subj_sel  = st.selectbox("Subject", SUBJECTS,                              key="ls_subject")
        r3, r4 = st.columns(2)
        with r3: staff_sel = st.selectbox("Staff",   ["select"]+staff_df["name"].tolist(),  key="ls_staff")
        with r4: mins_val  = st.number_input("Minutes", min_value=1, value=30,              key="ls_minutes")
        log_date = st.date_input("Date", value=date.today(), key="ls_date")

        st.markdown("**Students**")
        selected_ids = []
        if grade_sel == "select":
            st.info("Select a grade above.")
        else:
            gs = students_df[students_df["grade"]==grade_sel] if not students_df.empty else pd.DataFrame()
            if gs.empty:
                st.warning("No students in " + grade_sel + " yet.")
            else:
                stu_ids = gs["id"].tolist()
                sa, sn = st.columns(2)
                with sa:
                    st.button("Select All", key="ls_all", on_click=cb_select_all, args=(stu_ids,))
                with sn:
                    st.button("Select None", key="ls_none", on_click=cb_select_none, args=(stu_ids,))
                
                for _, stu in gs.iterrows():
                    if st.checkbox(stu["name"], key="ls_stu_" + str(stu["id"])):
                        selected_ids.append(stu["id"])

        note_val  = st.text_area("Notes (optional)", key="ls_note")
        n_sel     = len(selected_ids)
        btn_label = ("Log " + str(n_sel) + " Student" + ("s" if n_sel!=1 else "") + " ✓"
                     if n_sel > 0 else "Log Session ✓")

        if st.button(btn_label, key="ls_submit", use_container_width=True):
            errs = []
            if grade_sel == "select": errs.append("Select a grade.")
            if staff_sel == "select": errs.append("Select a staff member.")
            if n_sel == 0:            errs.append("Select at least one student.")
            if errs:
                for e in errs: st.error(e)
            else:
                for sid in selected_ids:
                    db.add_log(sid, subj_sel, staff_sel, int(mins_val), str(log_date), note_val)
                names = [students_df[students_df["id"]==sid]["name"].values[0] for sid in selected_ids]
                st.session_state["log_success_msg"]   = (
                    "Logged " + str(int(mins_val)) + "m of " + subj_sel +
                    " for: " + ", ".join(names))
                st.session_state["log_success_clear"] = False
                # Clear selection using callback-like logic before refresh
                for sid in selected_ids:
                    st.session_state["ls_stu_" + str(sid)] = False
                refresh()

    with col_recent:
        st.markdown("**Recent Sessions**")
        if logs_df.empty:
            st.caption("No sessions logged yet.")
        else:
            for _, row in logs_df.sort_values("date", ascending=False).head(10).iterrows():
                stu  = students_df[students_df["id"]==row["student_id"]]
                sn   = stu["name"].values[0]  if not stu.empty else "Unknown"
                sg   = stu["grade"].values[0] if not stu.empty else ""
                gc   = GRADE_COLOR.get(str(sg), "#9ca3af")
                si   = staff_df[staff_df["name"]==row["staff"]]
                sc   = si["color"].values[0] if not si.empty else "#9ca3af"
                slbl = "Tasks" if row["subject"]=="Task Completion" else row["subject"]
                st.markdown(
                    "<div style='background:#f4f5f7;border:1px solid #e5e7eb;border-radius:8px;"
                    "padding:7px 12px;margin-bottom:5px;font-size:12px'>"
                    "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;"
                    "background:" + sc + ";margin-right:6px'></span>"
                    "<b style='color:#111827'>" + sn + "</b>"
                    "<span style='margin-left:6px;background:" + gc + "18;color:" + gc +
                    ";border-radius:4px;padding:1px 5px;font-size:9px;font-weight:700'>" + str(sg) + "</span>"
                    "<span style='float:right;color:#9ca3af'>" + slbl +
                    " <b style='color:#111827'>" + str(int(row["minutes"])) + "m</b>"
                    " " + str(row["date"])[5:] + "</span></div>",
                    unsafe_allow_html=True)


# ── TEAM SETUP ────────────────────────────────────────────────────────────────
def render_team_setup(db, staff_df):
    st.subheader("Team Setup")
    with st.form("staff_form"):
        new_names = {}
        for _, row in staff_df.iterrows():
            cd, ci = st.columns([1,10])
            with cd:
                color = row["color"]
                st.markdown(
                    "<div style='width:12px;height:12px;border-radius:50%;background:" +
                    color + ";margin-top:34px'></div>", unsafe_allow_html=True)
            with ci:
                new_names[row["id"]] = st.text_input(
                    label="s" + str(row["id"]), value=row["name"],
                    key="sname_" + str(row["id"]), label_visibility="collapsed")
        if st.form_submit_button("Save Changes", use_container_width=True):
            db.update_staff_names(new_names)
            st.success("Staff names updated!")
            refresh()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    inject_css()
    db          = get_db()
    students_df = load_students(db)
    logs_df     = load_logs(db)
    staff_df    = load_staff(db)
    pivot       = load_pivot(logs_df)

    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px'>"
        "<div style='width:32px;height:32px;background:#4f46e5;border-radius:8px;"
        "display:flex;align-items:center;justify-content:center;"
        "color:white;font-weight:800;font-size:16px'>I</div>"
        "<span style='font-size:20px;font-weight:800;color:#111827;"
        "letter-spacing:-0.5px'>IEP Minute Pro</span></div>",
        unsafe_allow_html=True)

    tab_dash, tab_log, tab_add, tab_team = st.tabs(
        ["Dashboard","Log Session","Add Student","Team Setup"])

    with tab_dash:
        today      = date.today()
        sy         = school_year_for(today)
        month_tabs = [(sy if m>=8 else sy+1, m, lbl) for m,lbl in SCHOOL_MONTHS]

        if "active_month_idx" not in st.session_state:
            st.session_state["active_month_idx"] = next(
                (i for i,(yr,m,_) in enumerate(month_tabs)
                 if yr==today.year and m==today.month), 0)

        m_cols = st.columns(len(month_tabs))
        for mi, (yr, mo, lbl) in enumerate(month_tabs):
            with m_cols[mi]:
                is_a = st.session_state["active_month_idx"] == mi
                if st.button(lbl, key="mtab_" + str(mi), use_container_width=True, type="primary" if is_a else "secondary"):
                    st.session_state["active_month_idx"] = mi
                    st.rerun()

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        ami       = st.session_state["active_month_idx"]
        yr, mo, _ = month_tabs[ami]

        m_start, m_end = month_range(yr, mo)
        weeks          = month_weeks(yr, mo)
        week_options   = ["Whole Month"] + [w[0] for w in weeks]
        sel_week_key   = "sel_week_" + str(yr) + "_" + str(mo)
        if sel_week_key not in st.session_state:
            st.session_state[sel_week_key] = "Whole Month"

        pill_cols = st.columns(len(week_options))
        for wi, wopt in enumerate(week_options):
            with pill_cols[wi]:
                is_sel = st.session_state[sel_week_key] == wopt
                if st.button(wopt, key="wpill_" + str(yr) + "_" + str(mo) + "_" + str(wi),
                             use_container_width=True, type="primary" if is_sel else "secondary"):
                    st.session_state[sel_week_key] = wopt
                    st.rerun()

        sel_week = st.session_state[sel_week_key]
        if sel_week == "Whole Month":
            view_start, view_end = m_start, m_end
        else:
            matched = next((w for w in weeks if w[0]==sel_week), None)
            view_start, view_end = (matched[1],matched[2]) if matched else (m_start,m_end)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            render_summary_row(
                "Month" if sel_week=="Whole Month" else sel_week,
                pivot, staff_df, view_start, view_end)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            render_goal_chart(pivot, students_df, yr, mo)

        st.markdown("---")
        st.markdown("### Individual Student Progress")

        # Grade filter
        grade_key = "grade_filter_" + str(yr) + "_" + str(mo)
        if grade_key not in st.session_state:
            st.session_state[grade_key] = "All"

        gf_cols = st.columns(len(GRADES)+1)
        for gi, g in enumerate(["All"]+GRADES):
            with gf_cols[gi]:
                is_g   = st.session_state[grade_key] == g
                if st.button(g, key="gf_" + str(yr) + "_" + str(mo) + "_" + g,
                             use_container_width=True, type="primary" if is_g else "secondary"):
                    st.session_state[grade_key] = g
                    st.rerun()

        subj_tabs = st.tabs(["Math","English","Tasks"])
        for si, subj in enumerate(SUBJECTS):
            with subj_tabs[si]:
                gf  = st.session_state[grade_key]
                vis = students_df if gf=="All" else students_df[students_df["grade"]==gf]
                if vis.empty:
                    st.info("No students yet." if students_df.empty else "No " + gf + " students.")
                else:
                    slist = list(vis.iterrows())
                    for rs in range(0, len(slist), 3):
                        row_items = slist[rs:rs+3]
                        rcols     = st.columns(3)
                        for ci, (_, student) in enumerate(row_items):
                            with rcols[ci]:
                                render_student_card(
                                    student, pivot, logs_df, staff_df, db,
                                    subj, view_start, view_end,
                                    key_pfx=subj + "_" + str(yr) + "_" + str(mo))

    with tab_log:
        render_log_session(db, students_df, staff_df, logs_df)

    with tab_add:
        render_add_student(db)

    with tab_team:
        render_team_setup(db, staff_df)


if __name__ == "__main__":
    main()
