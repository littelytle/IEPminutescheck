"""
IEP Minute Pro — Streamlit App (Redesigned UI)
Matches the React "Crafted" Aesthetic
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
st.set_page_config(
    page_title="IEP Minute Pro", 
    page_icon="📋",
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- CONSTANTS ---
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
    
    /* Global Styles */
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
    .stApp { background-color: #f8fafc !important; }
    
    /* Custom Header */
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 0;
        margin-bottom: 2rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .logo-container {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    .logo-icon {
        width: 36px;
        height: 36px;
        background: #4f46e5;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: 900;
        font-size: 1.25rem;
        box-shadow: 0 4px 6px -1px rgb(79 70 229 / 0.2);
    }
    .logo-text {
        font-size: 1.25rem;
        font-weight: 900;
        color: #1e293b;
        letter-spacing: -0.025em;
        text-transform: uppercase;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        white-space: pre;
        background-color: #fff !important;
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
        color: #64748b !important;
        font-weight: 600 !important;
        padding: 0 16px !important;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4f46e5 !important;
        color: white !important;
        border-color: #4f46e5 !important;
        box-shadow: 0 4px 6px -1px rgb(79 70 229 / 0.2);
    }

    /* Card Styling */
    .student-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .student-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.05);
    }

    /* Progress Bar */
    .progress-container {
        background: #f1f5f9;
        border-radius: 999px;
        height: 8px;
        overflow: hidden;
        margin: 12px 0 6px 0;
    }
    .progress-fill {
        height: 100%;
        border-radius: 999px;
        transition: width 0.5s ease-out;
    }

    /* Metric Styling */
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        text-align: center;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 800;
        color: #1e293b;
    }
    .metric-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Form Overrides */
    div[data-testid="stForm"] {
        border: none !important;
        background: white !important;
        padding: 2rem !important;
        border-radius: 20px !important;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05);
        border: 1px solid #e2e8f0 !important;
    }
    
    /* Button Polish */
    .stButton>button {
        border-radius: 10px !important;
        font-weight: 700 !important;
        padding: 0.5rem 1.5rem !important;
        transition: all 0.2s ease !important;
    }
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- DATABASE LOGIC (Kept from your original) ---
class SheetsDB:
    def __init__(self):
        try:
            creds = Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(st.secrets["spreadsheet_id"])
            self._ensure_sheets()
        except Exception as e:
            st.error(f"Database Connection Error: {e}")
            st.stop()

    def _get_or_create_sheet(self, title, headers):
        try:
            return self.spreadsheet.worksheet(title)
        except WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
            ws.append_row(headers)
            return ws

    def _ensure_sheets(self):
        self.staff_ws = self._get_or_create_sheet("staff", ["id","name","color"])
        self.students_ws = self._get_or_create_sheet("students", ["id","name","grade","active_subject","goal_math","goal_english","goal_task_completion"])
        self.logs_ws = self._get_or_create_sheet("logs", ["id","student_id","subject","staff","minutes","date","note"])

    def get_staff(self):
        recs = self.staff_ws.get_all_records()
        return pd.DataFrame(recs) if recs else pd.DataFrame(columns=["id","name","color"])

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
        return df

    def add_log(self, student_id, subject, staff, minutes, log_date, note=""):
        recs = self.logs_ws.get_all_records()
        new_id = max((int(r["id"]) for r in recs), default=0) + 1
        self.logs_ws.append_row([new_id, int(student_id), subject, staff, int(minutes), str(log_date), note])

# --- UI COMPONENTS ---
def render_header():
    st.markdown("""
    <div class="app-header">
        <div class="logo-container">
            <div class="logo-icon">I</div>
            <div class="logo-text">IEP Minute Pro</div>
        </div>
        <div style="color: #64748b; font-size: 0.875rem; font-weight: 500;">
            Logged in as Team Member
        </div>
    </div>
    """, unsafe_allow_html=True)

def progress_bar_html(current, goal, color):
    percent = min(int((current / goal) * 100), 100) if goal > 0 else 0
    return f"""
    <div style="margin-top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 4px;">
            <span style="font-size: 0.75rem; color: #64748b; font-weight: 600;">{current}m / {goal}m</span>
            <span style="font-size: 0.875rem; color: #1e293b; font-weight: 800;">{percent}%</span>
        </div>
        <div class="progress-container">
            <div class="progress-fill" style="width: {percent}%; background-color: {color};"></div>
        </div>
    </div>
    """

def render_student_card(student, logs_df, active_subj, start_date, end_date):
    sid = student["id"]
    name = student["name"]
    grade = student["grade"]
    goal = student[GOAL_COL.get(active_subj, "goal_math")]
    
    # Calculate minutes
    mask = (logs_df["student_id"] == sid) & (logs_df["subject"] == active_subj) & \
           (logs_df["date"] >= start_date) & (logs_df["date"] <= end_date)
    current_mins = logs_df[mask]["minutes"].sum()
    
    color = SUBJ_COLOR.get(active_subj, "#4f46e5")
    
    st.markdown(f"""
    <div class="student-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <div style="font-size: 0.65rem; font-weight: 800; color: {GRADE_COLOR.get(grade, '#64748b')}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">{grade} Grade</div>
                <div style="font-size: 1.125rem; font-weight: 800; color: #1e293b; letter-spacing: -0.02em;">{name}</div>
            </div>
            <div style="background: {color}15; color: {color}; padding: 4px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: 700;">
                {active_subj.upper()}
            </div>
        </div>
        {progress_bar_html(current_mins, goal, color)}
    </div>
    """, unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    inject_css()
    render_header()
    
    db = SheetsDB()
    students_df = db.get_students()
    logs_df = db.get_logs()
    staff_df = db.get_staff()
    
    # Navigation
    tabs = st.tabs(["📊 Dashboard", "✍️ Log Session", "➕ Add Student", "⚙️ Settings"])
    
    with tabs[0]:
        # Dashboard Filters
        col1, col2, col3 = st.columns([2, 2, 4])
        with col1:
            active_subj = st.selectbox("Subject Area", SUBJECTS)
        with col2:
            grade_filter = st.selectbox("Grade Level", ["All"] + GRADES)
        
        # Date Range (Current Week)
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        st.markdown(f"### Service Minutes: {start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d')}")
        
        # Filter Students
        display_students = students_df
        if grade_filter != "All":
            display_students = display_students[display_students["grade"] == grade_filter]
            
        if display_students.empty:
            st.info("No students found for this filter.")
        else:
            # Grid Layout
            cols = st.columns(3)
            for i, (_, student) in enumerate(display_students.iterrows()):
                with cols[i % 3]:
                    render_student_card(student, logs_df, active_subj, start_of_week, end_of_week)

    with tabs[1]:
        st.markdown("### Log Service Minutes")
        with st.form("log_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                sel_student = st.selectbox("Student", students_df["name"].tolist() if not students_df.empty else ["No Students"])
                sel_subject = st.selectbox("Subject", SUBJECTS)
            with c2:
                sel_staff = st.selectbox("Staff Member", staff_df["name"].tolist() if not staff_df.empty else ["No Staff"])
                sel_mins = st.number_input("Minutes", min_value=1, value=30)
            
            sel_date = st.date_input("Date", value=date.today())
            sel_note = st.text_area("Session Notes", placeholder="What did you work on today?")
            
            submit = st.form_submit_button("Save Log Entry", use_container_width=True)
            
            if submit:
                if not students_df.empty:
                    sid = students_df[students_df["name"] == sel_student]["id"].values[0]
                    db.add_log(sid, sel_subject, sel_staff, sel_mins, sel_date, sel_note)
                    st.success(f"Logged {sel_mins}m for {sel_student}!")
                    st.rerun()

    with tabs[2]:
        st.info("Add student functionality would go here, styled similarly to the log form.")

    with tabs[3]:
        st.info("Settings and staff management.")

if __name__ == "__main__":
    main()
