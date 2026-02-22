"""
IEP Minute Pro — Streamlit App
Single-file, mobile-friendly, Google Sheets backend.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="IEP Minute Pro",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Constants ──────────────────────────────────────────────────────────────────
SUBJECTS = ["Math", "English", "Task Completion"]
GRADES   = ["6th", "7th", "8th"]

# School year months Aug–May
SCHOOL_MONTHS = [
    (8, "Aug"), (9, "Sep"), (10, "Oct"), (11, "Nov"), (12, "Dec"),
    (1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr"), (5, "May"),
]

SUBJ_COLOR = {
    "Math":            "#6366f1",
    "English":         "#8b5cf6",
    "Task Completion": "#10b981",
}
SUBJ_SHORT = {"Math": "M", "English": "E", "Task Completion": "T"}
GRADE_COLOR = {
    "6th": "#f59e0b",
    "7th": "#6366f1",
    "8th": "#10b981",
}
GOAL_COL = {
    "Math":            "goal_math",
    "English":         "goal_english",
    "Task Completion": "goal_task_completion",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_STAFF = [
    {"id": 1, "name": "Ms. Rivera",   "color": "#6366f1"},
    {"id": 2, "name": "Mr. Thompson", "color": "#f59e0b"},
    {"id": 3, "name": "Ms. Chen",     "color": "#10b981"},
    {"id": 4, "name": "Mr. Davis",    "color": "#ef4444"},
    {"id": 5, "name": "Ms. Patel",    "color": "#ec4899"},
]


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS DB
# ══════════════════════════════════════════════════════════════════════════════
class SheetsDB:
    def __init__(self):
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(st.secrets["spreadsheet_id"])
        self._ensure_sheets()

    def _get_or_create_sheet(self, title, headers):
        try:
            ws = self.spreadsheet.worksheet(title)
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
                self.staff_ws.append_row([s["id"], s["name"], s["color"]])

    def _next_id(self, ws):
        recs = ws.get_all_records()
        return max((int(r["id"]) for r in recs), default=0) + 1

    def _ws_to_df(self, ws):
        recs = ws.get_all_records()
        return pd.DataFrame(recs) if recs else pd.DataFrame()

    def _find_row(self, ws, col, value):
        for i, rec in enumerate(ws.get_all_records()):
            if str(rec[col]) == str(value):
                return i + 2
        return None

    def get_staff(self):
        df = self._ws_to_df(self.staff_ws)
        if df.empty:
            return pd.DataFrame(DEFAULT_STAFF)
        df["id"] = df["id"].astype(int)
        return df

    def update_staff_names(self, new_names):
        recs      = self.staff_ws.get_all_records()
        old_names = {r["id"]: r["name"] for r in recs}
        for sid, new_name in new_names.items():
            row = self._find_row(self.staff_ws, "id", sid)
            if row:
                self.staff_ws.update_cell(row, 2, new_name)
            old = old_names.get(int(sid), "")
            if old and old != new_name:
                log_recs = self.logs_ws.get_all_records()
                hdrs     = self.logs_ws.row_values(1)
                sc       = hdrs.index("staff") + 1
                for i, r in enumerate(log_recs):
                    if r["staff"] == old:
                        self.logs_ws.update_cell(i + 2, sc, new_name)

    def get_students(self):
        df = self._ws_to_df(self.students_ws)
        if df.empty:
            return pd.DataFrame(columns=["id","name","grade","active_subject","goal_math","goal_english","goal_task_completion"])
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
        df = self._ws_to_df(self.logs_ws)
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


# ══════════════════════════════════════════════════════════════════════════════
# CSS  (mobile-first, explicit dark text on tabs for Safari)
# ══════════════════════════════════════════════════════════════════════════════
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.stApp { background-color: #f4f5f7 !important; }

/* ── Force ALL tab labels to be visible (Safari fix) ── */
.stTabs [data-baseweb="tab-list"] {
    background-color: #ffffff !important;
    border-bottom: 2px solid #e5e7eb !important;
    gap: 0 !important;
    flex-wrap: wrap !important;
}
.stTabs [data-baseweb="tab"] {
    background-color: #ffffff !important;
    color: #4b5563 !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 10px 16px !important;
    border: none !important;
    border-bottom: 3px solid transparent !important;
    -webkit-text-fill-color: #4b5563 !important;
}
.stTabs [aria-selected="true"] {
    color: #4f46e5 !important;
    -webkit-text-fill-color: #4f46e5 !important;
    border-bottom: 3px solid #4f46e5 !important;
    background-color: #f5f3ff !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #4f46e5 !important;
    -webkit-text-fill-color: #4f46e5 !important;
    background-color: #f5f3ff !important;
}
/* Month tab row - smaller */
.month-tabs .stTabs [data-baseweb="tab"] {
    font-size: 11px !important;
    padding: 6px 10px !important;
}

/* Buttons */
.stButton > button {
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    border: 1.5px solid #e5e7eb !important;
    background: #ffffff !important;
    color: #374151 !important;
    -webkit-text-fill-color: #374151 !important;
    transition: all 0.15s !important;
    min-height: 40px !important;
}
.stButton > button:hover {
    border-color: #4f46e5 !important;
    color: #4f46e5 !important;
    -webkit-text-fill-color: #4f46e5 !important;
    background: #eef2ff !important;
}

/* Forms */
div[data-testid="stForm"] {
    background: white !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 12px !important;
    padding: 16px !important;
}

/* Inputs */
input, select, textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
}

/* Mobile responsive */
@media (max-width: 768px) {
    .stTabs [data-baseweb="tab"] {
        font-size: 11px !important;
        padding: 8px 10px !important;
    }
    .block-container { padding: 8px 12px !important; }
}

#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* Success banner */
.log-success {
    background: #d1fae5;
    border: 1px solid #10b981;
    border-radius: 8px;
    padding: 12px 16px;
    color: #065f46;
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CACHE / LOADERS
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def get_db():
    return SheetsDB()

def refresh():
    for k in ("students_df","logs_df","staff_df"):
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


# ══════════════════════════════════════════════════════════════════════════════
# DATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def school_year_for(d: date):
    """Return the school year start year (e.g. 2025 for 2025-26)."""
    return d.year if d.month >= 8 else d.year - 1

def get_month_weeks_for(year: int, month: int):
    """Mon–Fri week labels for a given month (school weeks)."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    weeks = []
    cur   = first - timedelta(days=first.weekday())  # back to Monday
    while cur <= last:
        mon = cur
        fri = cur + timedelta(days=4)
        label = f"{mon.month}/{mon.day}–{fri.month}/{fri.day}"
        # week range for filtering is Mon–Sun (full week)
        weeks.append((label, mon, mon + timedelta(days=6)))
        cur += timedelta(days=7)
    return weeks

def get_month_range_for(year: int, month: int):
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last

def logs_in_range(logs_df, start, end):
    if logs_df.empty: return logs_df
    d = pd.to_datetime(logs_df["date"], errors="coerce").dt.date
    return logs_df[(d >= start) & (d <= end)].copy()

def student_minutes(logs_df, student_id, subject, start, end):
    sub = logs_in_range(logs_df, start, end)
    if sub.empty: return 0
    sub = sub[(sub["student_id"] == student_id) & (sub["subject"] == subject)]
    return int(sub["minutes"].sum())

def staff_breakdown(logs_df, student_id, subject, start, end, staff_df):
    result = {n: 0 for n in staff_df["name"].tolist()}
    sub    = logs_in_range(logs_df, start, end)
    if sub.empty: return result
    sub = sub[(sub["student_id"] == student_id) & (sub["subject"] == subject)]
    for _, row in sub.iterrows():
        if row["staff"] in result:
            result[row["staff"]] += int(row["minutes"])
    return result

def safe_goal(student, subject):
    col = GOAL_COL.get(subject, "goal_math")
    val = student[col] if col in student.index else 60
    try: return int(val)
    except: return 60


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS BAR HTML
# ══════════════════════════════════════════════════════════════════════════════
def progress_bar_html(by_staff, staff_df, goal):
    total = sum(by_staff.values())
    segs  = ""
    for _, row in staff_df.iterrows():
        m = by_staff.get(row["name"], 0)
        if m > 0 and goal > 0:
            pct  = min(m / goal * 100, 100)
            name = row["name"]
            col  = row["color"]
            segs += f"<div title='{name}: {m}m' style='width:{pct:.1f}%;background:{col};height:100%;display:inline-block'></div>"
    pct_n = min(int(total/goal*100),100) if goal > 0 else 0
    gc    = "#10b981" if total >= goal else "#9ca3af"
    fw    = "700" if total >= goal else "400"
    return (
        f"<div style='background:#f3f4f6;border-radius:6px;height:10px;overflow:hidden;"
        f"border:1px solid #e5e7eb;display:flex;margin-bottom:3px'>{segs}</div>"
        f"<div style='display:flex;justify-content:space-between;font-size:10px;color:#9ca3af'>"
        f"<span>{total}m / {goal}m</span>"
        f"<span style='color:{gc};font-weight:{fw}'>{pct_n}%</span></div>"
    )


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY ROW
# ══════════════════════════════════════════════════════════════════════════════
def render_summary_row(label, logs_df, staff_df, start, end):
    sub   = logs_in_range(logs_df, start, end)
    grand = int(sub["minutes"].sum()) if not sub.empty else 0
    cols  = st.columns([1] + [2]*len(staff_df) + [1])
    cols[0].markdown(
        f"<div style='font-size:10px;font-weight:700;color:#4f46e5;"
        f"text-transform:uppercase;letter-spacing:1.2px;padding-top:6px'>{label}</div>",
        unsafe_allow_html=True)
    for i, (_, sr) in enumerate(staff_df.iterrows()):
        m = int(sub[sub["staff"]==sr["name"]]["minutes"].sum()) if not sub.empty else 0
        cols[i+1].markdown(
            f"<div style='display:flex;align-items:center;gap:4px;font-size:11px;color:#4b5563'>"
            f"<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:{sr['color']}'></span>"
            f"{sr['name'].split()[-1]}: <b style='color:#111827'>{m}m</b></div>",
            unsafe_allow_html=True)
    cols[-1].markdown(
        f"<div style='text-align:right;font-size:13px;font-weight:700;color:#111827;padding-top:4px'>{grand}m</div>",
        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# GOAL HIT CHART  (shows Mon-Fri week labels, filtered to selected month)
# ══════════════════════════════════════════════════════════════════════════════
def render_goal_chart(logs_df, students_df, year, month):
    weeks = get_month_weeks_for(year, month)
    rows  = []
    for label, w_start, w_end in weeks:
        row = {"Week": label}
        for subj in SUBJECTS:
            count = sum(
                1 for _, stu in students_df.iterrows()
                if student_minutes(logs_df, stu["id"], subj, w_start, w_end) >= safe_goal(stu, subj)
            )
            row[subj] = count
        rows.append(row)

    df   = pd.DataFrame(rows)
    maxy = max(len(students_df), 1)
    fig  = go.Figure()

    for subj in SUBJECTS:
        fig.add_trace(go.Scatter(
            x=df["Week"], y=df[subj],
            mode="lines+markers",
            name="Tasks" if subj=="Task Completion" else subj,
            line=dict(color=SUBJ_COLOR[subj], width=2.5),
            marker=dict(size=9, color=SUBJ_COLOR[subj], line=dict(width=2, color="white")),
            hovertemplate=f"<b>{'Tasks' if subj=='Task Completion' else subj}</b><br>%{{x}}<br>%{{y}} students hit goal<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="<b>Weekly Goal Progress</b>", font=dict(size=14,family="Inter"), x=0, xanchor="left"),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(range=[-0.2, maxy+0.5], tickvals=list(range(maxy+1)), gridcolor="#f3f4f6", zeroline=False,
                   title="Students hitting goal", title_font=dict(size=11, color="#9ca3af")),
        xaxis=dict(gridcolor="#f3f4f6", title="", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=10, r=10, t=60, b=10), height=260,
        font=dict(family="Inter"), hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT CARD  (subject controlled globally, shows M/E/T check badges)
# ══════════════════════════════════════════════════════════════════════════════
def render_student_card(student, logs_df, staff_df, db, active_subj, view_start, view_end, key_pfx=""):
    sid   = student["id"]
    name  = str(student["name"])
    grade = str(student["grade"])
    gc    = GRADE_COLOR.get(grade, "#9ca3af")
    goal  = safe_goal(student, active_subj)

    by_staff  = staff_breakdown(logs_df, sid, active_subj, view_start, view_end, staff_df)
    total_min = sum(by_staff.values())
    goal_met  = total_min >= goal

    # Check all 3 subjects for THIS week (always use current week for badges)
    week_start = view_start
    week_end   = view_end
    badges_html = ""
    for subj in SUBJECTS:
        short = SUBJ_SHORT[subj]
        color = SUBJ_COLOR[subj]
        g     = safe_goal(student, subj)
        m     = student_minutes(logs_df, sid, subj, week_start, week_end)
        done  = m >= g
        if done:
            badges_html += (
                f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                f"width:20px;height:20px;border-radius:50%;background:{color};"
                f"color:white;font-size:9px;font-weight:800;margin-left:2px' title='{subj}: {m}m/{g}m ✓'>"
                f"{short}</span>"
            )
        else:
            badges_html += (
                f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                f"width:20px;height:20px;border-radius:50%;background:#f3f4f6;"
                f"color:#9ca3af;font-size:9px;font-weight:700;border:1px solid #e5e7eb;margin-left:2px' "
                f"title='{subj}: {m}m/{g}m'>{short}</span>"
            )

    # Card top accent
    st.markdown(
        f"<div style='height:3px;background:{SUBJ_COLOR[active_subj]};border-radius:3px 3px 0 0'></div>",
        unsafe_allow_html=True)

    # Name row
    col_name, col_del = st.columns([6, 1])
    with col_name:
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:2px 0'>"
            f"<span style='background:{gc}18;color:{gc};font-size:10px;font-weight:700;"
            f"border-radius:4px;padding:2px 6px;white-space:nowrap'>{grade}</span>"
            f"<b style='font-size:13px;color:#111827'>{name}</b>"
            f"<span style='display:inline-flex;gap:2px;align-items:center'>{badges_html}</span>"
            f"</div>",
            unsafe_allow_html=True)
    with col_del:
        if st.button("×", key=f"del_{key_pfx}_{sid}", help="Remove student"):
            db.delete_student(sid)
            refresh()

    # Progress bar for active subject
    st.markdown(progress_bar_html(by_staff, staff_df, goal), unsafe_allow_html=True)

    # Staff chips
    chips = ""
    for _, s in staff_df.iterrows():
        m = by_staff.get(s["name"], 0)
        if m > 0:
            chips += (
                f"<span style='display:inline-flex;align-items:center;gap:3px;"
                f"background:#f4f5f7;border:1px solid #e5e7eb;border-radius:4px;"
                f"padding:2px 6px;font-size:9px;color:#4b5563;margin:2px'>"
                f"<span style='width:5px;height:5px;border-radius:50%;background:{s['color']};display:inline-block'></span>"
                f"{s['name'].split()[-1]}: {m}m</span>"
            )
    if chips:
        st.markdown(chips, unsafe_allow_html=True)

    # Edit + Notes
    with st.expander("⚙ Edit Goal / Name"):
        nn = st.text_input("Name", value=name, key=f"ename_{key_pfx}_{sid}")
        ng = st.number_input(f"{active_subj} goal (min/wk)", value=goal, min_value=1, key=f"egoal_{key_pfx}_{sid}")
        if st.button("Save", key=f"esave_{key_pfx}_{sid}"):
            db.update_student(sid, nn, {active_subj: int(ng)})
            refresh()

    with st.expander("📝 Notes"):
        if logs_df.empty:
            st.caption("No notes yet")
        else:
            ndf = logs_df[
                (logs_df["student_id"] == sid) &
                (logs_df["subject"] == active_subj) &
                (logs_df["note"].astype(str).str.strip() != "")
            ].sort_values("date", ascending=False)
            if ndf.empty:
                st.caption(f"No notes for {active_subj}")
            else:
                for _, nr in ndf.iterrows():
                    si  = staff_df[staff_df["name"] == nr["staff"]]
                    col = si["color"].values[0] if not si.empty else "#9ca3af"
                    st.markdown(
                        f"<div style='background:#f4f5f7;border:1px solid #e5e7eb;"
                        f"border-radius:7px;padding:7px 10px;margin-bottom:5px'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:3px'>"
                        f"<span style='font-size:10px;color:#4b5563'>"
                        f"<span style='display:inline-block;width:5px;height:5px;border-radius:50%;"
                        f"background:{col};margin-right:4px'></span>"
                        f"{str(nr['staff']).split()[-1]}</span>"
                        f"<span style='font-size:10px;color:#9ca3af'>{str(nr['date'])[5:]}</span>"
                        f"</div><p style='font-size:11px;color:#4b5563;margin:0'>{nr['note']}</p></div>",
                        unsafe_allow_html=True)
    st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ADD STUDENT
# ══════════════════════════════════════════════════════════════════════════════
def render_add_student(db):
    st.subheader("Add Student")
    with st.form("add_student_form", clear_on_submit=True):
        c1, c2 = st.columns([3,1])
        with c1: name  = st.text_input("Student Name", placeholder="Full name…")
        with c2: grade = st.selectbox("Grade", GRADES)
        st.markdown("**Weekly Goals (minutes)**")
        defaults = {"Math":60,"English":90,"Task Completion":45}
        g_cols   = st.columns(3)
        goals    = {}
        for i, subj in enumerate(SUBJECTS):
            with g_cols[i]:
                lbl = "Tasks" if subj=="Task Completion" else subj
                goals[subj] = st.number_input(f"{lbl} (min/wk)", value=defaults[subj], min_value=1, key=f"ng_{subj}")
        if st.form_submit_button("+ Add Student", use_container_width=True):
            if not name.strip():
                st.error("Please enter a student name.")
            else:
                db.add_student(name.strip(), grade, {k:int(v) for k,v in goals.items()})
                st.success(f"✓ {name.strip()} added!")
                refresh()


# ══════════════════════════════════════════════════════════════════════════════
# LOG SESSION  (with proper reset + confirmation)
# ══════════════════════════════════════════════════════════════════════════════
def render_log_session(db, students_df, staff_df, logs_df):
    st.subheader("Log Session")

    # Show persistent success message if set
    if st.session_state.get("log_success_msg"):
        st.markdown(
            f"<div class='log-success'>✓ {st.session_state['log_success_msg']}</div>",
            unsafe_allow_html=True)
        # Clear after showing once more
        if st.session_state.get("log_success_clear"):
            st.session_state["log_success_msg"] = ""
            st.session_state["log_success_clear"] = False
        else:
            st.session_state["log_success_clear"] = True

    col_form, col_recent = st.columns([1,1], gap="large")

    with col_form:
        r1, r2 = st.columns(2)
        with r1: grade_sel = st.selectbox("Grade",   ["— select —"] + GRADES,               key="ls_grade")
        with r2: subj_sel  = st.selectbox("Subject", SUBJECTS,                               key="ls_subject")
        r3, r4 = st.columns(2)
        with r3: staff_sel = st.selectbox("Staff",   ["— select —"] + staff_df["name"].tolist(), key="ls_staff")
        with r4: mins_val  = st.number_input("Minutes", min_value=1, value=30,               key="ls_minutes")

        log_date = st.date_input("Date", value=date.today(), key="ls_date")

        st.markdown("**Students**")
        selected_ids = []

        if grade_sel == "— select —":
            st.info("Select a grade above to see students.")
        else:
            gs = students_df[students_df["grade"] == grade_sel] if not students_df.empty else pd.DataFrame()
            if gs.empty:
                st.warning(f"No students in {grade_sel} grade yet.")
            else:
                sa, sn = st.columns(2)
                with sa:
                    if st.button("Select All", key="ls_all"):
                        for _, s in gs.iterrows():
                            st.session_state[f"ls_stu_{s['id']}"] = True
                with sn:
                    if st.button("Select None", key="ls_none"):
                        for _, s in gs.iterrows():
                            st.session_state[f"ls_stu_{s['id']}"] = False
                for _, stu in gs.iterrows():
                    if st.checkbox(stu["name"], key=f"ls_stu_{stu['id']}"):
                        selected_ids.append(stu["id"])

        note_val  = st.text_area("Notes (optional)", placeholder="What did you work on?", key="ls_note")
        n_sel     = len(selected_ids)
        btn_label = f"Log {n_sel} Student{'s' if n_sel!=1 else ''} ✓" if n_sel > 0 else "Log Session ✓"

        if st.button(btn_label, key="ls_submit", use_container_width=True):
            errs = []
            if grade_sel == "— select —": errs.append("Select a grade.")
            if staff_sel == "— select —": errs.append("Select a staff member.")
            if n_sel == 0:               errs.append("Select at least one student.")
            if errs:
                for e in errs: st.error(e)
            else:
                for sid in selected_ids:
                    db.add_log(sid, subj_sel, staff_sel, int(mins_val), str(log_date), note_val)
                # Set success message and reset checkboxes
                names = [students_df[students_df["id"]==sid]["name"].values[0] for sid in selected_ids]
                st.session_state["log_success_msg"] = (
                    f"Logged {int(mins_val)} min of {subj_sel} for: {', '.join(names)}"
                )
                st.session_state["log_success_clear"] = False
                # Reset student checkboxes
                for sid in selected_ids:
                    st.session_state[f"ls_stu_{sid}"] = False
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
                    f"<div style='background:#f4f5f7;border:1px solid #e5e7eb;border-radius:8px;"
                    f"padding:7px 12px;margin-bottom:5px;font-size:12px'>"
                    f"<span style='display:inline-block;width:7px;height:7px;border-radius:50%;"
                    f"background:{sc};margin-right:6px'></span>"
                    f"<b style='color:#111827'>{sn}</b>"
                    f"<span style='margin-left:6px;background:{gc}18;color:{gc};border-radius:4px;"
                    f"padding:1px 5px;font-size:9px;font-weight:700'>{sg}</span>"
                    f"<span style='float:right;color:#9ca3af'>{slbl} "
                    f"<b style='color:#111827'>{int(row['minutes'])}m</b>"
                    f" {str(row['date'])[5:]}</span></div>",
                    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TEAM SETUP
# ══════════════════════════════════════════════════════════════════════════════
def render_team_setup(db, staff_df):
    st.subheader("Team Setup — Edit Staff Names")
    with st.form("staff_form"):
        new_names = {}
        for _, row in staff_df.iterrows():
            cd, ci = st.columns([1,10])
            with cd:
                st.markdown(
                    f"<div style='width:12px;height:12px;border-radius:50%;"
                    f"background:{row['color']};margin-top:34px'></div>",
                    unsafe_allow_html=True)
            with ci:
                new_names[row["id"]] = st.text_input(
                    label=f"s{row['id']}", value=row["name"],
                    key=f"sname_{row['id']}", label_visibility="collapsed")
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

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px'>"
        "<div style='width:32px;height:32px;background:#4f46e5;border-radius:8px;"
        "display:flex;align-items:center;justify-content:center;"
        "color:white;font-weight:800;font-size:16px'>I</div>"
        "<span style='font-size:20px;font-weight:800;color:#111827;letter-spacing:-0.5px'>"
        "IEP Minute Pro</span></div>",
        unsafe_allow_html=True)

    # ── Main nav tabs ───────────────────────────────────────────────────────────
    tab_dash, tab_log, tab_add, tab_team = st.tabs(
        ["📊 Dashboard", "✏️ Log Session", "➕ Add Student", "👥 Team Setup"])

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    with tab_dash:

        # ── Month selector tabs (school year Aug–May) ─────────────────────────
        today      = date.today()
        sy         = school_year_for(today)
        # Build ordered list with correct years
        month_tabs = []
        for m, lbl in SCHOOL_MONTHS:
            yr = sy if m >= 8 else sy + 1
            month_tabs.append((yr, m, lbl))

        # Find which tab index = current month
        default_month_idx = next(
            (i for i,(yr,m,_) in enumerate(month_tabs) if yr==today.year and m==today.month),
            0)

        month_labels = [lbl for _,_,lbl in month_tabs]
        sel_month_tab = st.tabs(month_labels)

        for tab_i, (yr, mo, lbl) in enumerate(month_tabs):
            with sel_month_tab[tab_i]:

                month_start, month_end = get_month_range_for(yr, mo)
                weeks_in_month         = get_month_weeks_for(yr, mo)

                # ── Week selector pills ────────────────────────────────────────
                st.markdown(
                    "<p style='font-size:11px;font-weight:600;color:#9ca3af;"
                    "text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px'>WEEKS</p>",
                    unsafe_allow_html=True)

                week_options = ["Whole Month"] + [w[0] for w in weeks_in_month]
                sel_week_key = f"sel_week_{yr}_{mo}"
                if sel_week_key not in st.session_state:
                    st.session_state[sel_week_key] = "Whole Month"

                # Render week pills as columns of buttons
                pill_cols = st.columns(len(week_options))
                for wi, wopt in enumerate(week_options):
                    with pill_cols[wi]:
                        is_sel = st.session_state[sel_week_key] == wopt
                        bg     = "#4f46e5" if is_sel else "#ffffff"
                        col    = "#ffffff" if is_sel else "#4b5563"
                        st.markdown(
                            f"<div style='background:{bg};color:{col};border:1.5px solid "
                            f"{'#4f46e5' if is_sel else '#e5e7eb'};border-radius:20px;"
                            f"padding:4px 8px;text-align:center;font-size:10px;font-weight:600;"
                            f"-webkit-text-fill-color:{col};cursor:pointer'>{wopt}</div>",
                            unsafe_allow_html=True)
                        if st.button(wopt, key=f"wpill_{yr}_{mo}_{wi}", use_container_width=True):
                            st.session_state[sel_week_key] = wopt
                            st.rerun()

                # Determine view range
                sel_week = st.session_state[sel_week_key]
                if sel_week == "Whole Month":
                    view_start, view_end = month_start, month_end
                else:
                    matched = next((w for w in weeks_in_month if w[0]==sel_week), None)
                    view_start, view_end = (matched[1], matched[2]) if matched else (month_start, month_end)

                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

                # ── Summary rows ───────────────────────────────────────────────
                with st.container(border=True):
                    render_summary_row(
                        "Month" if sel_week=="Whole Month" else sel_week,
                        logs_df, staff_df, view_start, view_end)

                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

                # ── Goal chart ─────────────────────────────────────────────────
                with st.container(border=True):
                    render_goal_chart(logs_df, students_df, yr, mo)

                st.markdown("---")

                # ── Individual Student Progress ────────────────────────────────
                st.markdown("### Individual Student Progress")

                # Grade filter
                grade_key = f"grade_filter_{yr}_{mo}"
                gf_cols   = st.columns(len(GRADES)+1)
                if grade_key not in st.session_state:
                    st.session_state[grade_key] = "All"

                for gi, g in enumerate(["All"]+GRADES):
                    with gf_cols[gi]:
                        is_g   = st.session_state[grade_key] == g
                        gc_btn = GRADE_COLOR.get(g, "#4f46e5") if g != "All" else "#4f46e5"
                        bg_g   = f"{gc_btn}18" if is_g else "#ffffff"
                        col_g  = gc_btn if is_g else "#4b5563"
                        st.markdown(
                            f"<div style='background:{bg_g};color:{col_g};border:1.5px solid "
                            f"{''+gc_btn if is_g else '#e5e7eb'};border-radius:8px;padding:5px;"
                            f"text-align:center;font-size:11px;font-weight:700;"
                            f"-webkit-text-fill-color:{col_g}'>{g}</div>",
                            unsafe_allow_html=True)
                        if st.button(g, key=f"gf_{yr}_{mo}_{g}", use_container_width=True):
                            st.session_state[grade_key] = g
                            st.rerun()

                # Subject tabs (3 big tabs for Math / English / Tasks)
                subj_tab_labels = ["📐 Math", "📖 English", "✅ Tasks"]
                subj_tabs       = st.tabs(subj_tab_labels)

                for si, subj in enumerate(SUBJECTS):
                    with subj_tabs[si]:
                        grade_filter = st.session_state[grade_key]
                        vis = (students_df if grade_filter=="All"
                               else students_df[students_df["grade"]==grade_filter])

                        if vis.empty:
                            st.info("No students yet." if students_df.empty else f"No {grade_filter} students.")
                        else:
                            n_cols = 3
                            slist  = list(vis.iterrows())
                            for rs in range(0, len(slist), n_cols):
                                row_items = slist[rs:rs+n_cols]
                                rcols     = st.columns(n_cols)
                                for ci, (_, student) in enumerate(row_items):
                                    with rcols[ci]:
                                        render_student_card(
                                            student, logs_df, staff_df, db,
                                            subj, view_start, view_end,
                                            key_pfx=f"{subj}_{yr}_{mo}")

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


if __name__ == "__main__":
    main()
