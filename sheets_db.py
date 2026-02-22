"""
sheets_db.py — Google Sheets database layer for IEP Minute Pro.

Sheet structure inside one Google Spreadsheet:
  • "staff"    — columns: id, name, color
  • "students" — columns: id, name, grade, active_subject,
                          goal_math, goal_english, goal_task_completion
  • "logs"     — columns: id, student_id, subject, staff, minutes, date, note

Authentication uses a Google Service Account JSON key stored in
Streamlit secrets (st.secrets["gcp_service_account"]).

To set up:
1. Create a Google Cloud project → enable Sheets API + Drive API.
2. Create a Service Account → download JSON key.
3. Share your Google Sheet with the service account email (Editor).
4. In Streamlit Cloud → Settings → Secrets, paste the JSON key as shown in
   secrets.toml.example.
5. Add SPREADSHEET_ID to secrets too.
"""

import json
import pandas as pd
import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
from datetime import date

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

STAFF_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#ec4899"]

DEFAULT_STAFF = [
    {"id": 1, "name": "Ms. Rivera",   "color": "#6366f1"},
    {"id": 2, "name": "Mr. Thompson", "color": "#f59e0b"},
    {"id": 3, "name": "Ms. Chen",     "color": "#10b981"},
    {"id": 4, "name": "Mr. Davis",    "color": "#ef4444"},
    {"id": 5, "name": "Ms. Patel",    "color": "#ec4899"},
]


class SheetsDB:
    """Thin wrapper around gspread for reading/writing IEP data."""

    def __init__(self):
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        self.client = gspread.authorize(creds)
        spreadsheet_id = st.secrets["spreadsheet_id"]
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self._ensure_sheets()

    # ── Sheet bootstrap ────────────────────────────────────────────────────────
    def _get_or_create_sheet(self, title: str, headers: list[str]):
        try:
            ws = self.spreadsheet.worksheet(title)
        except WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
            ws.append_row(headers)
        return ws

    def _ensure_sheets(self):
        """Create worksheets with correct headers if they don't exist yet."""
        self.staff_ws = self._get_or_create_sheet(
            "staff", ["id", "name", "color"]
        )
        self.students_ws = self._get_or_create_sheet(
            "students",
            ["id", "name", "grade", "active_subject",
             "goal_math", "goal_english", "goal_task_completion"],
        )
        self.logs_ws = self._get_or_create_sheet(
            "logs", ["id", "student_id", "subject", "staff", "minutes", "date", "note"]
        )

        # Seed staff if empty
        staff_data = self.staff_ws.get_all_records()
        if not staff_data:
            for s in DEFAULT_STAFF:
                self.staff_ws.append_row([s["id"], s["name"], s["color"]])

    # ── Generic helpers ────────────────────────────────────────────────────────
    def _next_id(self, ws) -> int:
        records = ws.get_all_records()
        if not records:
            return 1
        return max(int(r["id"]) for r in records) + 1

    def _ws_to_df(self, ws) -> pd.DataFrame:
        records = ws.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()

    def _find_row(self, ws, col_name: str, value) -> int | None:
        """Return 1-based row index of first row where col_name == value, or None."""
        records = ws.get_all_records()
        headers = ws.row_values(1)
        col_idx = headers.index(col_name) + 1  # 1-based
        for i, rec in enumerate(records):
            if str(rec[col_name]) == str(value):
                return i + 2  # +1 for header, +1 for 0-index
        return None

    # ── Staff ──────────────────────────────────────────────────────────────────
    def get_staff(self) -> pd.DataFrame:
        df = self._ws_to_df(self.staff_ws)
        if df.empty:
            return pd.DataFrame(DEFAULT_STAFF)
        df["id"] = df["id"].astype(int)
        return df

    def update_staff_names(self, new_names: dict):
        """new_names: {staff_id: new_name}"""
        records = self.staff_ws.get_all_records()
        # Also update logs that reference old names
        old_names = {r["id"]: r["name"] for r in records}

        for staff_id, new_name in new_names.items():
            row = self._find_row(self.staff_ws, "id", staff_id)
            if row:
                self.staff_ws.update_cell(row, 2, new_name)  # col 2 = name

            # Rename in logs
            old_name = old_names.get(int(staff_id), "")
            if old_name and old_name != new_name:
                log_records = self.logs_ws.get_all_records()
                log_headers = self.logs_ws.row_values(1)
                staff_col = log_headers.index("staff") + 1
                for i, rec in enumerate(log_records):
                    if rec["staff"] == old_name:
                        self.logs_ws.update_cell(i + 2, staff_col, new_name)

    # ── Students ───────────────────────────────────────────────────────────────
    def get_students(self) -> pd.DataFrame:
        df = self._ws_to_df(self.students_ws)
        if df.empty:
            return pd.DataFrame(columns=[
                "id", "name", "grade", "active_subject",
                "goal_math", "goal_english", "goal_task_completion",
            ])
        df["id"] = df["id"].astype(int)
        for col in ["goal_math", "goal_english", "goal_task_completion"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(60).astype(int)
        return df

    def add_student(self, name: str, grade: str, goals: dict):
        new_id = self._next_id(self.students_ws)
        self.students_ws.append_row([
            new_id, name, grade, "Math",
            goals.get("Math", 60),
            goals.get("English", 90),
            goals.get("Task Completion", 45),
        ])

    def update_student(self, student_id, new_name: str = None, goals: dict = None):
        row = self._find_row(self.students_ws, "id", student_id)
        if not row:
            return
        headers = self.students_ws.row_values(1)
        if new_name:
            self.students_ws.update_cell(row, headers.index("name") + 1, new_name)
        if goals:
            col_map = {
                "Math":            "goal_math",
                "English":         "goal_english",
                "Task Completion": "goal_task_completion",
            }
            for subj, val in goals.items():
                col_name = col_map.get(subj)
                if col_name and col_name in headers:
                    self.students_ws.update_cell(
                        row, headers.index(col_name) + 1, val
                    )

    def update_student_subject(self, student_id, subject: str):
        row = self._find_row(self.students_ws, "id", student_id)
        if not row:
            return
        headers = self.students_ws.row_values(1)
        col = headers.index("active_subject") + 1
        self.students_ws.update_cell(row, col, subject)

    def delete_student(self, student_id):
        row = self._find_row(self.students_ws, "id", student_id)
        if row:
            self.students_ws.delete_rows(row)

    # ── Logs ───────────────────────────────────────────────────────────────────
    def get_logs(self) -> pd.DataFrame:
        df = self._ws_to_df(self.logs_ws)
        if df.empty:
            return pd.DataFrame(columns=[
                "id", "student_id", "subject", "staff", "minutes", "date", "note"
            ])
        df["id"]         = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
        df["student_id"] = pd.to_numeric(df["student_id"], errors="coerce").astype("Int64")
        df["minutes"]    = pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype(int)
        df["date"]       = pd.to_datetime(df["date"], errors="coerce").dt.date
        df["note"]       = df["note"].fillna("")
        return df

    def add_log(self, student_id, subject: str, staff: str,
                minutes: int, log_date: str, note: str = ""):
        new_id = self._next_id(self.logs_ws)
        self.logs_ws.append_row([
            new_id, int(student_id), subject, staff,
            int(minutes), str(log_date), note,
        ])
