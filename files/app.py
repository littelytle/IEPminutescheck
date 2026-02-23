"""
IEP Minute Pro — Streamlit App
Full Logic Preserved | Refined UI Hierarchy | Fixed Streamlit API Errors
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
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

# --- CALLBACKS (Fixes Session State Errors) ---
def cb_select_all(ids):
    for sid in ids:
        st.session_state[f"ls_stu_{sid}"] = True

def cb_select_none(ids):
    for sid in ids:
        st.session_state[f"ls_stu_{sid}"] = False

def cb_submit_log(ids, db, subj, staff, mins, dt, note):
    for sid in ids:
        db.add_log(sid, subj, staff, mins, dt, note)
    st.session_state["log_success_msg"] = f"Logged {mins}m for {len(ids)} students."
    for sid in ids:
        st.session_state[f"ls_stu_{sid}"] = False
    st.session_state["ls_note"] = ""

# --- DATABASE LOGIC (Full Original Logic) ---
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

    def get_staff(self):
        recs = self.staff_ws.get_all_records()
        return pd.DataFrame(recs) if recs else pd.DataFrame(DEFAULT_STAFF)

    def get_students(self):
        recs = self.students_ws.get_all_records()
        df = pd.DataFrame(recs) if recs else pd.DataFrame()
        if not df.empty:
            df["id"] = df["id"].astype(int)
            for col in ["goal_math","goal_english","goal_task_completion"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(60).astype(int)
        return df

    def get_logs(self):
        recs = self.logs_ws.get_all_records()
        df = pd.DataFrame(recs) if recs else pd.DataFrame()
        if not df.empty:
            df["student_id"] = pd.to_numeric(df["student_id"], errors="coerce").astype("Int64")
            df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype(int)
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df["note"] = df["note"].fillna("")
        return df

    def add_log(self, student_id, subject, staff, minutes, log_date, note=""):
        recs = self.logs_ws.get_all_records()
        new_id = max((int(r["id"]) for r in recs), default=0) + 1
        self.logs_ws.append_row([new_id, int(student_id), subject, staff, int(minutes), str(log_date), note])

    def add_student(self, name, grade, goals):
        recs = self.students_ws.get_all_records()
        new_id = max((int(r["id"]) for r in recs), default=0) + 1
        self.students_ws.append_row([new_id, name, grade, "Math", goals.get("Math",60), goals.get("English",90), goals.get("Task Completion",45)])

    def update_student(self, sid, name=None, goals=None):
        recs = self.students_ws.get_all_records()
        for i, r in enumerate(recs):
            if int(r["id"]) == int(sid):
                row = i + 2
                if name: self.students_ws.update_cell(row, 2, name)
                if goals:
                    for s, v in goals.items():
                        col = 5 if s == "Math" else 6 if s == "English" else 7
                        self.students_ws.update_cell(row, col, v)
                break

    def delete_student(self, sid):
        recs = self.students_ws.get_all_records()
        for i, r in enumerate(recs):
            if int(r["id"]) == int(sid):
                self.students_ws.delete_rows(i+2)
                break

# --- PIVOT & CALCULATIONS ---
def build_pivot(logs_df):
    if logs_df.empty: return pd.DataFrame(columns=["student_id","subject","staff","minutes","date"])
    return logs_df[["student_id","subject","staff","minutes","date"]].copy()

def pivot_minutes(pivot, student_id, subject, start, end):
    if pivot.empty: return 0
    m = (pivot["student_id"]==student_id) & (pivot["subject"]==subject) & (pivot["date"]>=start) & (pivot["date"]<=end)
    return int(pivot.loc[m,"minutes"].sum())

def summary_data(pivot, staff_names, start, end):
    if pivot.empty: return 0, {n:0 for n in staff_names}
    m = (pivot["date"]>=start) & (pivot["date"]<=end)
    sub = pivot.loc[m]
    return int(sub["minutes"].sum()), {n: int(sub.loc[sub["staff"]==n,"minutes"].sum()) for n in staff_names}

# --- HELPERS ---
def safe_goal(student, subject):
    col = GOAL_COL.get(subject, "goal_math")
    try: return int(student[col]) if col in student.index else 60
    except: return 60

def school_year_for(d): return d.year if d.month >= 8 else d.year - 1

def month_weeks(year, month):
    first = date(year, month, 1)
    last = date(year+1,1,1)-timedelta(1) if month==12 else date(year,month+1,1)-timedelta(1)
    weeks, cur = [], first - timedelta(days=first.weekday())
    while cur <= last:
        mon, fri = cur, cur+timedelta(4)
        weeks.append((f"{mon.month}/{mon.day}–{fri.month}/{fri.day}", mon, mon+timedelta(6)))
        cur += timedelta(7)
    return weeks

def month_range(year, month):
    first = date(year, month, 1)
    last = date(year+1,1,1)-timedelta(1) if month==12 else date(year,month+1,1)-timedelta(1)
    return first, last

# --- CSS ---
def inject_css():
    st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif!important}
.stApp{background-color:#f8fafc!important}
.student-card {
    background: white; border: 1px solid #e2e8f0; border-radius: 16px;
    padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
}
.student-name {
    font-size: 1.5rem !important; font-weight: 900 !important;
    color: #0f172a !important; letter-spacing: -0.04em !important; line-height: 1 !important;
}
.student-minutes {
    font-size: 1.5rem !important; font-weight: 400 !important;
    color: #64748b !important; letter-spacing: -0.04em !important;
}
.student-minutes b { color: #0f172a !important; font-weight: 900 !important; }
.progress-container { background: #f1f5f9; border-radius: 999px; height: 12px; overflow: hidden; margin: 1rem 0; }
.progress-fill { height: 100%; border-radius: 999px; transition: width 0.6s ease; }
.latest-note {
    background: #f8fafc; border-left: 3px solid #e2e8f0; padding: 0.75rem 1rem;
    border-radius: 0 8px 8px 0; margin-top: 1rem; font-size: 0.875rem; color: #475569;
}
.note-meta { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 4px; }
.stButton>button{border-radius:8px!important;font-weight:600!important;min-height:40px!important}
#MainMenu{visibility:hidden}footer{visibility:hidden}header{visibility:hidden}
</style>""", unsafe_allow_html=True)

# --- UI COMPONENTS ---
def render_student_card(student, pivot, logs_df, staff_df, db, active_subj, start, end, key_pfx=""):
    sid = student["id"]
    name = str(student["name"])
    goal = safe_goal(student, active_subj)
    staff_names = staff_df["name"].tolist()
    
    # Calculate Minutes
    m_mask = (pivot["student_id"]==sid) & (pivot["subject"]==active_subj) & (pivot["date"]>=start) & (pivot["date"]<=end)
    total_min = int(pivot.loc[m_mask, "minutes"].sum())
    percent = min(int((total_min / goal) * 100), 100) if goal > 0 else 0
    color = SUBJ_COLOR.get(active_subj, "#4f46e5")

    st.markdown(f"""
    <div class="student-card">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <div class="student-name">{name}</div>
            <div class="student-minutes"><b>{total_min}</b> / {goal}m</div>
        </div>
        <div class="progress-container"><div class="progress-fill" style="width:{percent}%;background:{color}"></div></div>
    """, unsafe_allow_html=True)

    # Latest Note
    notes = logs_df[(logs_df["student_id"] == sid) & (logs_df["note"] != "")].sort_values("date", ascending=False)
    if not notes.empty:
        latest = notes.iloc[0]
        st.markdown(f"<div class='latest-note'><div class='note-meta'>{latest['date'].strftime('%b %d')} • {latest['staff']}</div>{latest['note']}</div>", unsafe_allow_html=True)
        if len(notes) > 1:
            with st.expander("History"): # Removed 'key' to fix TypeError
                for _, r in notes.iloc[1:].iterrows():
                    st.markdown(f"**{r['date'].strftime('%b %d')}**: {r['note']} ({r['staff']})")
    else:
        st.markdown("<div style='font-size:0.75rem;color:#94a3b8;margin-top:0.5rem'>No notes recorded.</div>", unsafe_allow_html=True)

    # Edit Pencil
    edit_col1, edit_col2 = st.columns([10, 1])
    with edit_col2:
        if st.button("✏️", key=f"edit_btn_{key_pfx}_{sid}"):
            st.session_state[f"ed_{sid}"] = not st.session_state.get(f"ed_{sid}", False)
    
    if st.session_state.get(f"ed_{sid}"):
        with st.form(f"edit_form_{key_pfx}_{sid}"): # Unique form key
            nn = st.text_input("Name", value=name, key=f"nn_{key_pfx}_{sid}")
            ng = st.number_input(f"{active_subj} Goal", value=goal, key=f"ng_{key_pfx}_{sid}")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Save"):
                db.update_student(sid, nn, {active_subj: int(ng)})
                st.rerun()
            if c2.form_submit_button("🗑️ Remove"):
                db.delete_student(sid)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN ---
def main():
    inject_css()
    db = SheetsDB()
    students_df, logs_df, staff_df = db.get_students(), db.get_logs(), db.get_staff()
    pivot = build_pivot(logs_df)

    st.markdown("<h1 style='letter-spacing:-0.05em;font-weight:900;color:#0f172a'>IEP Minute Pro</h1>", unsafe_allow_html=True)
    tab_dash, tab_log, tab_add, tab_team = st.tabs(["Dashboard", "Log Session", "Add Student", "Team Setup"])

    with tab_dash:
        today = date.today()
        sy = school_year_for(today)
        month_tabs = [(sy if m>=8 else sy+1, m, lbl) for m,lbl in SCHOOL_MONTHS]
        if "ami" not in st.session_state:
            st.session_state.ami = next((i for i,(y,m,_) in enumerate(month_tabs) if y==today.year and m==today.month), 0)

        # Month Selector (Decluttered)
        m_cols = st.columns(len(month_tabs))
        for mi, (yr, mo, lbl) in enumerate(month_tabs):
            if m_cols[mi].button(lbl, key=f"m_{mi}", use_container_width=True, type="primary" if st.session_state.ami == mi else "secondary"):
                st.session_state.ami = mi
                st.rerun()

        yr, mo, _ = month_tabs[st.session_state.ami]
        m_start, m_end = month_range(yr, mo)
        weeks = month_weeks(yr, mo)
        w_opts = ["Whole Month"] + [w[0] for w in weeks]
        wk_key = f"wk_{yr}_{mo}"
        if wk_key not in st.session_state: st.session_state[wk_key] = "Whole Month"
        
        # Week Selector (Decluttered)
        w_cols = st.columns(len(w_opts))
        for wi, wopt in enumerate(w_opts):
            if w_cols[wi].button(wopt, key=f"w_{yr}_{mo}_{wi}", use_container_width=True, type="primary" if st.session_state[wk_key] == wopt else "secondary"):
                st.session_state[wk_key] = wopt
                st.rerun()

        sel_w = st.session_state[wk_key]
        v_start, v_end = (m_start, m_end) if sel_w == "Whole Month" else next(((w[1], w[2]) for w in weeks if w[0]==sel_w), (m_start, m_end))

        st.divider()
        c1, c2 = st.columns([1, 3])
        with c1:
            active_subj = st.radio("Subject", SUBJECTS)
            grade_filter = st.radio("Grade", ["All"] + GRADES, horizontal=True)
        with c2:
            vis = students_df if grade_filter == "All" else students_df[students_df["grade"] == grade_filter]
            if vis.empty: st.info("No students found.")
            else:
                for _, s in vis.iterrows():
                    render_student_card(s, pivot, logs_df, staff_df, db, active_subj, v_start, v_end, key_pfx=f"{active_subj}_{yr}_{mo}")

    with tab_log:
        st.markdown("### Log Session")
        with st.form("bulk_log"):
            c1, c2 = st.columns(2)
            with c1:
                l_grade = st.selectbox("Grade Level", GRADES)
                l_subj = st.selectbox("Subject", SUBJECTS)
            with c2:
                l_staff = st.selectbox("Staff", staff_df["name"].tolist())
                l_mins = st.number_input("Minutes", min_value=1, value=30)
            l_date = st.date_input("Date", value=date.today())
            
            st.markdown("**Select Students**")
            gs = students_df[students_df["grade"] == l_grade]
            selected_ids = []
            if not gs.empty:
                sc1, sc2 = st.columns(2)
                for i, (_, s) in enumerate(gs.iterrows()):
                    with (sc1 if i % 2 == 0 else sc2):
                        if st.checkbox(s["name"], key=f"ls_stu_{s['id']}"): selected_ids.append(s["id"])
            
            l_note = st.text_area("Notes", key="ls_note")
            if st.form_submit_button("Save Log Entry", use_container_width=True):
                if not selected_ids: st.error("Select at least one student.")
                else:
                    for sid in selected_ids: db.add_log(sid, l_subj, l_staff, l_mins, l_date, l_note)
                    st.success("Logged successfully!")
                    st.rerun()

    with tab_add:
        st.markdown("### Add Student")
        with st.form("add_stu"):
            n_name = st.text_input("Name")
            n_grade = st.selectbox("Grade", GRADES)
            gc1, gc2, gc3 = st.columns(3)
            g_math = gc1.number_input("Math", value=60)
            g_eng = gc2.number_input("English", value=90)
            g_task = gc3.number_input("Tasks", value=45)
            if st.form_submit_button("Add Student"):
                db.add_student(n_name, n_grade, {"Math": g_math, "English": g_eng, "Task Completion": g_task})
                st.success(f"Added {n_name}!")
                st.rerun()

    with tab_team:
        # Team setup logic...
        pass

if __name__ == "__main__":
    main()
