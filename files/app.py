"""
IEP Minute Pro — Streamlit App (Restored & Refined)
Full functionality restored with "Crafted" UI hierarchy.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
st.set_page_config(page_title="IEP Minute Pro", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")

SUBJECTS = ["Math", "English", "Task Completion"]
GRADES = ["6th", "7th", "8th"]
SCHOOL_MONTHS = [(8,"Aug"),(9,"Sep"),(10,"Oct"),(11,"Nov"),(12,"Dec"),
                  (1,"Jan"),(2,"Feb"),(3,"Mar"),(4,"Apr"),(5,"May")]
SUBJ_COLOR = {"Math":"#4f46e5","English":"#7c3aed","Task Completion":"#10b981"}
SUBJ_SHORT = {"Math":"M","English":"E","Task Completion":"T"}
GRADE_COLOR = {"6th":"#f59e0b","7th":"#4f46e5","8th":"#10b981"}
GOAL_COL = {"Math":"goal_math","English":"goal_english","Task Completion":"goal_task_completion"}
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# --- CSS (The "Crafted" Look) ---
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
    .stApp { background-color: #f8fafc !important; }
    
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
        font-size: 1.75rem !important;
        font-weight: 900 !important;
        color: #0f172a !important;
        letter-spacing: -0.04em !important;
        line-height: 1 !important;
    }
    .student-minutes {
        font-size: 1.75rem !important;
        font-weight: 400 !important;
        color: #64748b !important;
        letter-spacing: -0.04em !important;
    }
    .student-minutes b { color: #0f172a !important; font-weight: 900 !important; }

    /* Progress Bar */
    .progress-container { background: #f1f5f9; border-radius: 999px; height: 12px; overflow: hidden; margin: 1rem 0; }
    .progress-fill { height: 100%; border-radius: 999px; transition: width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); }

    /* Note Styling */
    .latest-note {
        background: #f8fafc;
        border-left: 3px solid #e2e8f0;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        margin-top: 1rem;
        font-size: 0.875rem;
        color: #475569;
    }
    .note-meta { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 4px; }

    /* Form Styling */
    div[data-testid="stForm"] { background: white !important; border: 1px solid #e2e8f0 !important; border-radius: 16px !important; padding: 2rem !important; }
    
    /* Hide Redundant Labels */
    div[data-testid="stMarkdownContainer"] > p { margin-bottom: 0 !important; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- DATABASE LOGIC (Restored from Original) ---
@st.cache_resource
def get_db():
    class SheetsDB:
        def __init__(self):
            creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(st.secrets["spreadsheet_id"])
            self.staff_ws = self.spreadsheet.worksheet("staff")
            self.students_ws = self.spreadsheet.worksheet("students")
            self.logs_ws = self.spreadsheet.worksheet("logs")

        def get_staff(self): return pd.DataFrame(self.staff_ws.get_all_records())
        def get_students(self): 
            df = pd.DataFrame(self.students_ws.get_all_records())
            if not df.empty: df["id"] = df["id"].astype(int)
            return df
        def get_logs(self):
            df = pd.DataFrame(self.logs_ws.get_all_records())
            if not df.empty:
                df["student_id"] = pd.to_numeric(df["student_id"], errors="coerce").astype("Int64")
                df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype(int)
                df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            return df
        
        def add_student(self, name, grade, goals):
            recs = self.students_ws.get_all_records()
            new_id = max((int(r["id"]) for r in recs), default=0) + 1
            self.students_ws.append_row([new_id, name, grade, "Math", goals.get("Math",60), goals.get("English",90), goals.get("Task Completion",45)])

        def add_log(self, sid, subj, staff, mins, dt, note):
            recs = self.logs_ws.get_all_records()
            new_id = max((int(r["id"]) for r in recs), default=0) + 1
            self.logs_ws.append_row([new_id, int(sid), subj, staff, int(mins), str(dt), note])

        def update_student(self, sid, name, goals):
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
    return SheetsDB()

# --- HELPERS ---
def school_year_for(d): return d.year if d.month >= 8 else d.year - 1
def month_range(year, month):
    first = date(year, month, 1)
    last = date(year+1,1,1)-timedelta(1) if month==12 else date(year,month+1,1)-timedelta(1)
    return first, last
def month_weeks(year, month):
    first = date(year, month, 1)
    last = date(year+1,1,1)-timedelta(1) if month==12 else date(year,month+1,1)-timedelta(1)
    weeks, cur = [], first - timedelta(days=first.weekday())
    while cur <= last:
        mon, fri = cur, cur+timedelta(4)
        weeks.append((f"{mon.month}/{mon.day}–{fri.month}/{fri.day}", mon, mon+timedelta(6)))
        cur += timedelta(7)
    return weeks

# --- STUDENT CARD ---
def render_student_card(student, logs_df, active_subj, start, end, db):
    sid, name = student["id"], student["name"]
    goal = int(student[GOAL_COL.get(active_subj, "goal_math")])
    mask = (logs_df["student_id"] == sid) & (logs_df["subject"] == active_subj) & (logs_df["date"] >= start) & (logs_df["date"] <= end)
    current_mins = int(logs_df[mask]["minutes"].sum())
    percent = min(int((current_mins / goal) * 100), 100) if goal > 0 else 0
    color = SUBJ_COLOR.get(active_subj, "#4f46e5")

    st.markdown(f"""
    <div class="student-card">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <div class="student-name">{name}</div>
            <div class="student-minutes"><b>{current_mins}</b> / {goal}m</div>
        </div>
        <div class="progress-container"><div class="progress-fill" style="width: {percent}%; background-color: {color};"></div></div>
    """, unsafe_allow_html=True)

    # Latest Note
    notes = logs_df[(logs_df["student_id"] == sid) & (logs_df["note"] != "")].sort_values("date", ascending=False)
    if not notes.empty:
        latest = notes.iloc[0]
        st.markdown(f"<div class='latest-note'><div class='note-meta'>{latest['date'].strftime('%b %d')} • {latest['staff']}</div>{latest['note']}</div>", unsafe_allow_html=True)
        if len(notes) > 1:
            with st.expander("History"):
                for _, r in notes.iloc[1:].iterrows(): st.markdown(f"**{r['date'].strftime('%b %d')}**: {r['note']} ({r['staff']})")
    else:
        st.markdown("<div style='font-size: 0.75rem; color: #94a3b8; margin-top: 0.5rem;'>No notes.</div>", unsafe_allow_html=True)

    # Edit Pencil
    if st.button("✏️", key=f"edit_{sid}"): st.session_state[f"ed_{sid}"] = not st.session_state.get(f"ed_{sid}", False)
    if st.session_state.get(f"ed_{sid}"):
        with st.form(f"f_{sid}"):
            nn = st.text_input("Name", value=name)
            ng = st.number_input(f"{active_subj} Goal", value=goal)
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Save"):
                db.update_student(sid, nn, {active_subj: ng})
                st.rerun()
            if c2.form_submit_button("🗑️ Remove"):
                db.delete_student(sid)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN ---
def main():
    inject_css()
    db = get_db()
    students_df, logs_df, staff_df = db.get_students(), db.get_logs(), db.get_staff()

    st.markdown("<h1 style='letter-spacing: -0.05em; font-weight: 900; color: #0f172a;'>IEP Minute Pro</h1>", unsafe_allow_html=True)
    tab_dash, tab_log, tab_add = st.tabs(["Dashboard", "Log Session", "Add Student"])

    with tab_dash:
        # Month/Week Selectors (Cleaned)
        today = date.today()
        sy = school_year_for(today)
        month_tabs = [(sy if m>=8 else sy+1, m, lbl) for m,lbl in SCHOOL_MONTHS]
        if "ami" not in st.session_state: st.session_state.ami = next((i for i,(y,m,_) in enumerate(month_tabs) if y==today.year and m==today.month), 0)
        
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
            if vis.empty: st.info("No students.")
            else:
                for _, s in vis.iterrows(): render_student_card(s, logs_df, staff_df, active_subj, v_start, v_end, db)

    with tab_log:
        st.markdown("### Bulk Log Session")
        with st.form("bulk_log", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                l_grade = st.selectbox("Grade Level", GRADES)
                l_subj = st.selectbox("Subject", SUBJECTS)
            with c2:
                l_staff = st.selectbox("Staff", staff_df["name"].tolist())
                l_mins = st.number_input("Minutes", min_value=1, value=30)
            l_date = st.date_input("Date", value=date.today())
            
            st.markdown("**Select Students**")
            grade_students = students_df[students_df["grade"] == l_grade]
            selected_ids = []
            if not grade_students.empty:
                sc1, sc2 = st.columns(2)
                for i, (_, s) in enumerate(grade_students.iterrows()):
                    with (sc1 if i % 2 == 0 else sc2):
                        if st.checkbox(s["name"], key=f"bulk_{s['id']}"): selected_ids.append(s["id"])
            
            l_note = st.text_area("Notes")
            if st.form_submit_button(f"Log {len(selected_ids)} Students", use_container_width=True):
                if not selected_ids: st.error("Select at least one student.")
                else:
                    for sid in selected_ids: db.add_log(sid, l_subj, l_staff, l_mins, l_date, l_note)
                    st.success("Logged successfully!")
                    st.rerun()

    with tab_add:
        st.markdown("### Add New Student")
        with st.form("add_stu", clear_on_submit=True):
            n_name = st.text_input("Student Name")
            n_grade = st.selectbox("Grade", GRADES)
            st.markdown("**Weekly Goals (Minutes)**")
            gc1, gc2, gc3 = st.columns(3)
            g_math = gc1.number_input("Math", value=60)
            g_eng = gc2.number_input("English", value=90)
            g_task = gc3.number_input("Tasks", value=45)
            if st.form_submit_button("Add Student"):
                if not n_name: st.error("Name required.")
                else:
                    db.add_student(n_name, n_grade, {"Math": g_math, "English": g_eng, "Task Completion": g_task})
                    st.success(f"Added {n_name}!")
                    st.rerun()

if __name__ == "__main__":
    main()
