"""SSS job connection portal.

The portal keeps Google Sheets as its datastore, but presents a job-centric
workflow to three kinds of users: administrators, workers, and clients.
"""

import json
import os
import time
import urllib.parse
from datetime import datetime, timedelta

import gspread
import pandas as pd
import pytz
import streamlit as st
from google.oauth2.service_account import Credentials


# Configuration remains compatible with the original deployment.  Secrets may
# be supplied through Streamlit secrets or environment variables.
st.set_page_config(
    page_title="SSS Job Portal",
    layout="wide",
    page_icon="✨",
    initial_sidebar_state="collapsed",
)
ADMIN_USER = os.getenv("SSS_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("SSS_ADMIN_PASS", "admin@SSS")
SHEET_URL = os.getenv(
    "SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing",
)
CLIENT_SHEET_URL = os.getenv("CLIENT_SHEET_URL", SHEET_URL)
SUPPORT_NUMBER = os.getenv("SUPPORT_NUMBER", "254799084376")
KISUMU_TZ = pytz.timezone("Africa/Nairobi")

WORKER_HEADERS = [
    "id", "name", "username", "password", "phone", "skills", "active",
]
CLIENT_HEADERS = [
    "id", "name", "username", "password", "phone", "email", "address", "active",
]
JOB_HEADERS = [
    "id", "title", "client_id", "worker_id", "description", "instructions",
    "hours", "rate", "client_rate", "status", "date_posted", "due_date",
    "time_marked_done", "payout", "total_bill", "payment_status", "invoice_id",
    "applications", "application_deadline", "cancel_reason",
    "msg_posted", "msg_application", "msg_selected", "msg_allocated",
    "msg_night_before", "msg_1hr_before", "msg_late", "msg_completed",
    "msg_payment", "msg_admin_cancelled",
]
SETTINGS_HEADERS = ["setting_key", "setting_value"]
ACCOUNTING_HEADERS = ["tx_id", "date", "type", "description", "amount", "status", "job_id", "client_id"]


def inject_custom_bg(role):
    """Apply the same lightweight role-specific styling used by the old UI."""
    if role == "admin":
        colors = ("#e0f2fe", "#ffffff", "#e5e7eb", "#334155")
    elif role == "worker":
        colors = ("#ffffff", "#f0f9ff", "#f3f4f6", "#334155")
    elif role == "client":
        colors = ("#f8fafc", "#e0f2fe", "#bae6fd", "#0f172a")
    else:
        colors = ("#f8fafc", "#e0f2fe", "#bae6fd", "#0f172a")
    st.markdown(
        f"""<style>
        .stApp {{ background: linear-gradient(135deg, {colors[0]} 0%, {colors[1]} 50%, {colors[2]} 100%); color: {colors[3]}; }}
        h1, h2, h3, h4, p, span, div {{ color: {colors[3]}; }}
        </style>""",
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_gspread_client():
    """Authenticate without ever printing or exposing credentials."""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scopes))
    except Exception as exc:
        st.error(f"Database authentication failed: {exc}")
        st.stop()


def _copy_legacy_records(workbook, new_ws, legacy_title, headers):
    """Migrate an old Employees/Tasks sheet once, when present and useful."""
    if new_ws.get_all_records():
        return
    try:
        legacy = workbook.worksheet(legacy_title)
        records = legacy.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        return
    except Exception:
        return
    if not records:
        return
    migrated = []
    for record in records:
        item = {header: record.get(header, "") for header in headers}
        if legacy_title == "Employees":
            item.update({
                "id": record.get("id", ""),
                "name": record.get("name", ""),
                "username": record.get("username", ""),
                "password": record.get("password", ""),
                "phone": record.get("phone", ""),
                "active": record.get("active", "Yes"),
            })
        else:
            item.update({
                "id": record.get("id", ""),
                "title": record.get("title", ""),
                "worker_id": record.get("employee_Id", record.get("worker_id", "")),
                "hours": record.get("hours", ""),
                "rate": record.get("rate", ""),
                "status": record.get("status", "Open"),
                "date_posted": record.get("date_assigned", ""),
                "due_date": record.get("due_date", ""),
                "time_marked_done": record.get("time_marked_done", ""),
                "payout": record.get("payout", ""),
                "instructions": record.get("instructions", ""),
                "cancel_reason": record.get("cancel_reason", ""),
            })
        migrated.append([item.get(header, "") for header in headers])
    if migrated:
        new_ws.append_rows(migrated)


@st.cache_resource
def get_worksheets():
    """Mount or create all portal worksheets and perform legacy migration."""
    client = get_gspread_client()
    try:
        workbook = client.open_by_url(SHEET_URL)
    except Exception as exc:
        st.error(f"Failed to open the target database: {exc}")
        st.stop()

    def get_or_create(title, headers):
        try:
            ws = workbook.worksheet(title)
            existing = ws.row_values(1)
            if not existing:
                ws.append_row(headers)
            else:
                missing = [header for header in headers if header not in existing]
                if missing:
                    ws.update(
                        values=[missing],
                        range_name=(
                            f"{gspread.utils.rowcol_to_a1(1, len(existing) + 1)}:"
                            f"{gspread.utils.rowcol_to_a1(1, len(existing) + len(missing))}"
                        ),
                    )
            return ws
        except gspread.exceptions.WorksheetNotFound:
            ws = workbook.add_worksheet(title=title, rows="2000", cols=max(20, len(headers)))
            ws.append_row(headers)
            return ws

    workers_ws = get_or_create("Workers", WORKER_HEADERS)
    clients_ws = get_or_create("Clients", CLIENT_HEADERS)
    jobs_ws = get_or_create("Jobs", JOB_HEADERS)
    settings_ws = get_or_create("Settings", SETTINGS_HEADERS)
    acct_ws = get_or_create("Accounting", ACCOUNTING_HEADERS)

    _copy_legacy_records(workbook, workers_ws, "Employees", WORKER_HEADERS)
    _copy_legacy_records(workbook, jobs_ws, "Tasks", JOB_HEADERS)
    if not workers_ws.get_all_records():
        workers_ws.append_row(["worker1", "Wanjiku (Nanny Pro)", "wanjiku", "password123", "254700000000", "Cleaning", "Yes"])
        workers_ws.append_row(["worker2", "Ochieng (Deep Cleaner)", "ochieng", "password123", "254700000000", "Cleaning", "Yes"])
    return workbook, workers_ws, clients_ws, jobs_ws, settings_ws, acct_ws


workbook, workers_ws, clients_ws, jobs_ws, settings_ws, acct_ws = get_worksheets()


def _empty_frame(headers):
    return pd.DataFrame(columns=headers)


def _normalise_people(frame, headers):
    frame = frame.copy() if not frame.empty else _empty_frame(headers)
    for header in headers:
        if header not in frame.columns:
            frame[header] = ""
    for column in ("id", "username", "password", "phone", "active"):
        if column in frame.columns:
            frame[column] = frame[column].fillna("").astype(str)
    return frame


def _normalise_jobs(frame):
    frame = frame.copy() if not frame.empty else _empty_frame(JOB_HEADERS)
    for header in JOB_HEADERS:
        if header not in frame.columns:
            frame[header] = ""
    for column in ("id", "client_id", "worker_id", "status", "applications"):
        frame[column] = frame[column].fillna("").astype(str)
    for column in ("hours", "rate", "client_rate", "payout", "total_bill"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame


@st.cache_data(ttl=30)
def fetch_portal_data():
    """Fetch Workers, Clients, Jobs, Settings and Accounting in one read."""
    workers = _normalise_people(pd.DataFrame(workers_ws.get_all_records()), WORKER_HEADERS)
    clients = _normalise_people(pd.DataFrame(clients_ws.get_all_records()), CLIENT_HEADERS)
    jobs = _normalise_jobs(pd.DataFrame(jobs_ws.get_all_records()))
    settings = pd.DataFrame(settings_ws.get_all_records())
    accounting = pd.DataFrame(acct_ws.get_all_records())
    if accounting.empty:
        accounting = _empty_frame(ACCOUNTING_HEADERS)
    for column in ("amount",):
        accounting[column] = pd.to_numeric(accounting[column], errors="coerce").fillna(0.0)
    return workers, clients, jobs, settings, accounting


workers_df, clients_df, jobs_df, settings_df, acct_df = fetch_portal_data()


def _save_frame(ws, frame):
    """Replace a worksheet atomically enough for gspread's row-oriented API."""
    clean = frame.fillna("").copy()
    try:
        ws.clear()
        ws.update([clean.columns.tolist()] + clean.astype(object).values.tolist())
    except gspread.exceptions.GSpreadException as exc:
        st.error(f"Could not save portal data: {exc}")
        raise


def save_jobs(frame):
    _save_frame(jobs_ws, _normalise_jobs(frame))
    fetch_portal_data.clear()


def save_workers(frame):
    _save_frame(workers_ws, _normalise_people(frame, WORKER_HEADERS))
    fetch_portal_data.clear()


def save_clients(frame):
    _save_frame(clients_ws, _normalise_people(frame, CLIENT_HEADERS))
    fetch_portal_data.clear()


def save_acct(frame):
    _save_frame(acct_ws, frame if not frame.empty else _empty_frame(ACCOUNTING_HEADERS))
    fetch_portal_data.clear()


def _name_for(frame, value, unknown):
    if frame.empty:
        return unknown
    match = frame[frame["id"].astype(str) == str(value)]
    return str(match.iloc[0]["name"]) if not match.empty else unknown


def get_worker_name(worker_id):
    return _name_for(workers_df, worker_id, "Unknown Worker")


def get_client_name(client_id):
    return _name_for(clients_df, client_id, "Unknown Client")


def _parse_applications(value):
    if not value or str(value).lower() == "nan":
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _job_applications(job):
    return _parse_applications(job.get("applications", ""))


def _encode_applications(applications):
    return json.dumps(applications, separators=(",", ":"))


def _job_id():
    return f"job-{int(time.time() * 1000)}"


def _refresh():
    fetch_portal_data.clear()
    st.rerun()


def _logout():
    st.session_state.current_user = None
    _refresh()


def _add_accounting(description, amount, tx_type, job_id="", client_id=""):
    row = pd.DataFrame([{
        "tx_id": f"TX-{tx_type.upper()}-{int(time.time())}",
        "date": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "type": tx_type,
        "description": description,
        "amount": float(amount),
        "status": "Cleared",
        "job_id": job_id,
        "client_id": client_id,
    }])
    save_acct(pd.concat([acct_df, row], ignore_index=True))


def run_monthly_job_archive():
    """Move closed jobs to a dated archive sheet at the start of each month."""
    global jobs_df
    current_month = datetime.now(KISUMU_TZ).strftime("%Y-%m")
    if settings_df.empty or "setting_key" not in settings_df.columns:
        settings_ws.append_row(["last_reset", current_month])
        return
    matches = settings_df.loc[
        settings_df["setting_key"].astype(str) == "last_reset", "setting_value"
    ]
    if matches.empty:
        settings_ws.append_row(["last_reset", current_month])
        return
    last_reset = str(matches.iloc[0])
    if last_reset == current_month:
        return
    try:
        active_statuses = {
            "Open", "Applied", "Selected", "Confirmed", "In Progress",
            "Completed", "Payment Due",
        }
        archive_df = jobs_df[~jobs_df["status"].isin(active_statuses)].copy()
        keep_df = jobs_df[jobs_df["status"].isin(active_statuses)].copy()
        if not archive_df.empty:
            archive_title = f"Archive_{last_reset}"
            try:
                archive_ws = workbook.worksheet(archive_title)
            except gspread.exceptions.WorksheetNotFound:
                archive_ws = workbook.add_worksheet(
                    title=archive_title, rows="2000", cols=max(20, len(JOB_HEADERS))
                )
                archive_ws.append_row(archive_df.columns.tolist())
            archive_ws.append_rows(archive_df.astype(object).fillna("").values.tolist())
        _save_frame(jobs_ws, keep_df)
        cell = settings_ws.find("last_reset")
        settings_ws.update_cell(cell.row, cell.col + 1, current_month)
        jobs_df = keep_df
        fetch_portal_data.clear()
    except (gspread.exceptions.GSpreadException, ValueError) as exc:
        st.error(f"Monthly job archive failed: {exc}")


run_monthly_job_archive()


if "current_user" not in st.session_state:
    st.session_state.current_user = None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
if st.session_state.current_user is None:
    inject_custom_bg("login")
    left, centre, right = st.columns([1, 2, 1])
    with centre:
        st.markdown("<h1 style='text-align:center'>✨ SSS Job Portal</h1>", unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align:center'>Swift-hands Student Services. Authorized Users Only.</p>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            with st.form("login_form"):
                login_user = st.text_input("Username")
                login_pass = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log In 🚀", use_container_width=True, type="primary")
            if submitted:
                if login_user == ADMIN_USER and login_pass == ADMIN_PASS:
                    st.session_state.current_user = {"role": "admin", "name": "Administrator"}
                    _refresh()
                worker_match = workers_df[
                    (workers_df["username"] == login_user)
                    & (workers_df["password"] == login_pass)
                    & (workers_df["active"].str.lower().isin(["yes", "true", "1", ""]))
                ]
                client_match = clients_df[
                    (clients_df["username"] == login_user)
                    & (clients_df["password"] == login_pass)
                    & (clients_df["active"].str.lower().isin(["yes", "true", "1", ""]))
                ]
                if not worker_match.empty:
                    row = worker_match.iloc[0]
                    st.session_state.current_user = {
                        "role": "worker", "id": row["id"], "name": row["name"], "is_phased": False,
                    }
                    _refresh()
                elif not client_match.empty:
                    row = client_match.iloc[0]
                    st.session_state.current_user = {
                        "role": "client", "id": row["id"], "name": row["name"], "is_phased": False,
                    }
                    _refresh()
                elif not (login_user == ADMIN_USER and login_pass == ADMIN_PASS):
                    st.error("Invalid credentials. Access denied. 🛑")


elif st.session_state.current_user["role"] == "admin":
    inject_custom_bg("admin")
    user = st.session_state.current_user
    st.sidebar.title("🛡️ Admin Portal")
    admin_view = st.sidebar.radio(
        "Navigation",
        ["🏢 Job & Worker Management", "👥 Client Management", "💼 Finance & Client Billing"],
    )
    st.sidebar.write("---")
    if st.sidebar.button("Log Out 🚪", type="primary", use_container_width=True):
        _logout()

    # Admin can phase into either type of user without changing credentials.
    st.sidebar.subheader("👁️ View As Worker / Client")
    phase_type = st.sidebar.selectbox("Dashboard type", ["Worker", "Client"])
    phase_frame = workers_df if phase_type == "Worker" else clients_df
    if not phase_frame.empty:
        phase_target = st.sidebar.selectbox("Select user", phase_frame["name"].tolist())
        if st.sidebar.button("View Dashboard 👁️", use_container_width=True):
            row = phase_frame[phase_frame["name"] == phase_target].iloc[0]
            st.session_state.current_user = {
                "role": phase_type.lower(), "id": row["id"], "name": row["name"], "is_phased": True,
            }
            _refresh()

    if admin_view == "🏢 Job & Worker Management":
        st.title("Job & Worker Management")
        add_col, list_col = st.columns([1, 2])
        with add_col:
            st.subheader("➕ Add New Worker")
            with st.form("add_worker_form"):
                name = st.text_input("Full Name")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                phone = st.text_input("Phone Number")
                skills = st.text_input("Skills")
                if st.form_submit_button("Add Worker 🤝"):
                    if not all([name, username, password, phone]):
                        st.error("Please fill out all required fields.")
                    elif username in workers_df["username"].values or username in clients_df["username"].values:
                        st.error("Username already taken.")
                    else:
                        workers_df = pd.concat([workers_df, pd.DataFrame([{
                            "id": f"worker-{int(time.time())}", "name": name, "username": username,
                            "password": password, "phone": phone, "skills": skills, "active": "Yes",
                        }])], ignore_index=True)
                        save_workers(workers_df)
                        st.success("Worker added successfully.")
                        _refresh()
            st.subheader("Worker Directory")
            st.dataframe(workers_df[["id", "name", "username", "phone", "skills", "active"]], hide_index=True, use_container_width=True)

        with list_col:
            st.subheader("🚀 Post a Job")
            with st.form("admin_post_job_form"):
                title = st.text_input("Job Title")
                description = st.text_area("Description / Instructions")
                client_options = dict(zip(clients_df["name"], clients_df["id"])) if not clients_df.empty else {}
                client_name = st.selectbox("Client", list(client_options) or ["No clients registered"])
                hours = st.number_input("Estimated Hours", min_value=0.5, value=1.0, step=0.5)
                worker_rate = st.number_input("Worker Pay (Ksh/hr)", min_value=0.0, value=150.0, step=10.0)
                client_rate = st.number_input("Client Bill (Ksh/hr)", min_value=0.0, value=250.0, step=10.0)
                due_date = st.date_input("Due Date")
                due_time = st.time_input("Due Time")
                post = st.form_submit_button("Post Job 🚀", type="primary")
            if post:
                if not title.strip() or not client_options:
                    st.error("A title and registered client are required.")
                else:
                    jobs_df = pd.concat([jobs_df, pd.DataFrame([{
                        "id": _job_id(), "title": title.strip(), "client_id": client_options[client_name],
                        "worker_id": "", "description": description, "instructions": description,
                        "hours": hours, "rate": worker_rate, "client_rate": client_rate,
                        "status": "Open", "date_posted": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                        "due_date": f"{due_date} {due_time}", "payout": hours * worker_rate,
                        "total_bill": hours * client_rate, "payment_status": "Unpaid",
                        "invoice_id": "", "applications": "[]",
                    }])], ignore_index=True)
                    save_jobs(jobs_df)
                    st.success("Job posted successfully.")
                    _refresh()

        st.subheader("📋 Active Job Postings")
        active = jobs_df[jobs_df["status"].isin(["Open", "Applied", "Selected", "Confirmed", "In Progress", "Completed", "Payment Due", "Paid"])]
        if active.empty:
            st.info("No jobs have been posted yet.")
        else:
            display = active[["id", "title", "client_id", "worker_id", "status", "due_date", "total_bill", "payment_status"]].copy()
            display["Client"] = display["client_id"].apply(get_client_name)
            display["Worker"] = display["worker_id"].apply(get_worker_name)
            st.dataframe(display[["id", "title", "Client", "Worker", "status", "due_date", "total_bill", "payment_status"]], hide_index=True, use_container_width=True)

    elif admin_view == "👥 Client Management":
        st.title("Client Management")
        with st.form("add_client_form"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Client / Organisation Name")
                username = st.text_input("Client Username")
                password = st.text_input("Client Password", type="password")
            with c2:
                phone = st.text_input("Phone Number")
                email = st.text_input("Email")
                address = st.text_input("Address")
            if st.form_submit_button("Add Client 🤝"):
                if not all([name, username, password, phone]):
                    st.error("Name, username, password and phone are required.")
                elif username in workers_df["username"].values or username in clients_df["username"].values:
                    st.error("Username already taken.")
                else:
                    clients_df = pd.concat([clients_df, pd.DataFrame([{
                        "id": f"client-{int(time.time())}", "name": name, "username": username,
                        "password": password, "phone": phone, "email": email, "address": address, "active": "Yes",
                    }])], ignore_index=True)
                    save_clients(clients_df)
                    st.success("Client added successfully.")
                    _refresh()
        st.subheader("Registered Clients")
        st.dataframe(clients_df.drop(columns=["password"], errors="ignore"), hide_index=True, use_container_width=True)
        if not clients_df.empty:
            st.subheader("Edit Client")
            edit_name = st.selectbox("Select client to edit", clients_df["name"].tolist())
            selected = clients_df[clients_df["name"] == edit_name].iloc[0]
            with st.form("edit_client_form"):
                edit_phone = st.text_input("Phone", value=str(selected.get("phone", "")))
                edit_email = st.text_input("Email", value=str(selected.get("email", "")))
                edit_address = st.text_input("Address", value=str(selected.get("address", "")))
                edit_active = st.selectbox(
                    "Account status", ["Yes", "No"],
                    index=0 if str(selected.get("active", "Yes")).lower() in {"yes", "true", "1"} else 1,
                )
                if st.form_submit_button("Save Client Changes"):
                    clients_df.loc[clients_df["id"] == selected["id"], ["phone", "email", "address", "active"]] = [
                        edit_phone, edit_email, edit_address, edit_active,
                    ]
                    save_clients(clients_df)
                    st.success("Client details updated.")
                    _refresh()

    else:
        st.title("Finance & Client Billing")
        total_income = acct_df[acct_df["type"] == "Income"]["amount"].sum() if not acct_df.empty else 0
        total_payroll = acct_df[acct_df["type"] == "Expense"]["amount"].sum() if not acct_df.empty else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Client Income (Ksh)", f"{total_income:,.2f}")
        m2.metric("Worker Payroll (Ksh)", f"{total_payroll:,.2f}")
        m3.metric("Gross Margin (Ksh)", f"{total_income - total_payroll:,.2f}")
        st.subheader("Client invoices")
        invoice_jobs = jobs_df[jobs_df["status"].isin(["Completed", "Payment Due", "Paid"])]
        if invoice_jobs.empty:
            st.info("No completed jobs require billing.")
        else:
            st.dataframe(invoice_jobs[["id", "title", "client_id", "worker_id", "total_bill", "payment_status", "invoice_id"]], hide_index=True, use_container_width=True)
            for _, job in invoice_jobs.iterrows():
                if job["status"] != "Paid" and st.button(f"Record client payment: {job['title']}", key=f"admin_pay_{job['id']}"):
                    jobs_df.loc[jobs_df["id"] == job["id"], ["status", "payment_status"]] = ["Paid", "Paid"]
                    save_jobs(jobs_df)
                    _add_accounting(f"Payment for {job['title']}", job["total_bill"], "Income", job["id"], job["client_id"])
                    _refresh()
        unpaid = jobs_df[jobs_df["status"] == "Completed"]
        if not unpaid.empty:
            st.subheader("Worker payroll")
            report = unpaid.groupby("worker_id")["payout"].sum().reset_index()
            report["Worker"] = report["worker_id"].apply(get_worker_name)
            st.dataframe(report[["Worker", "payout"]].rename(columns={"payout": "Owed (Ksh)"}), hide_index=True)
            if st.button("Disburse all worker payroll 💸", type="primary"):
                total = unpaid["payout"].sum()
                jobs_df.loc[jobs_df["status"] == "Completed", "status"] = "Payment Due"
                save_jobs(jobs_df)
                _add_accounting("Worker payroll disbursement", total, "Expense")
                _refresh()
        if not acct_df.empty:
            st.subheader("Accounting ledger")
            st.dataframe(acct_df.sort_values("date", ascending=False), hide_index=True, use_container_width=True)


elif st.session_state.current_user["role"] == "worker":
    inject_custom_bg("worker")
    current = st.session_state.current_user
    user_id = str(current["id"])
    st.sidebar.title("👤 Worker Dashboard")
    st.sidebar.write(f"Welcome back, **{current['name']}**.")
    if current.get("is_phased"):
        st.sidebar.warning("👁️ ADMIN VIEW MODE")
        if st.sidebar.button("Return to Admin Dashboard ⚡", type="primary"):
            st.session_state.current_user = {"role": "admin", "name": "Administrator"}
            _refresh()
    elif st.sidebar.button("Log Out 🚪", type="primary"):
        _logout()
    st.sidebar.link_button("💬 Contact Administrator", f"https://wa.me/{SUPPORT_NUMBER}", use_container_width=True)

    my_jobs = jobs_df[jobs_df["worker_id"].astype(str) == user_id]
    paid = my_jobs[my_jobs["status"] == "Paid"]["payout"].sum() if not my_jobs.empty else 0
    pending = my_jobs[my_jobs["status"].isin(["Selected", "Confirmed", "In Progress", "Completed", "Payment Due"])]["payout"].sum() if not my_jobs.empty else 0
    c1, c2 = st.columns(2)
    c1.metric("💵 Total Earnings (Paid)", f"Ksh {paid:,.2f}")
    c2.metric("📊 Pending Balance", f"Ksh {pending:,.2f}")
    st.subheader("💼 Available Jobs")
    available = jobs_df[jobs_df["status"].isin(["Open", "Applied"])]
    for _, job in available.iterrows():
        if not pd.isna(job.get("title")):
            with st.container(border=True):
                st.markdown(f"### {job['title']}")
                st.write(job.get("description") or job.get("instructions", ""))
                st.caption(f"Client: {get_client_name(job['client_id'])} | Due: {job['due_date']} | Pay: Ksh {job['payout']:,.2f}")
                applications = _job_applications(job)
                already_applied = any(str(app.get("worker_id")) == user_id for app in applications)
                if not already_applied and not (job["worker_id"] and job["status"] != "Open"):
                    if st.button("Apply for this job ✅", key=f"apply_{job['id']}"):
                        applications.append({"worker_id": user_id, "name": current["name"], "applied_at": datetime.now(KISUMU_TZ).isoformat(), "status": "Pending"})
                        jobs_df.loc[jobs_df["id"] == job["id"], "applications"] = _encode_applications(applications)
                        jobs_df.loc[jobs_df["id"] == job["id"], "status"] = "Applied"
                        save_jobs(jobs_df)
                        _refresh()
    st.subheader("My Accepted Jobs")
    for _, job in my_jobs.iterrows():
        with st.container(border=True):
            st.markdown(f"**{job['title']}** — {job['status']}")
            st.caption(f"Due: {job['due_date']} | Expected payout: Ksh {job['payout']:,.2f}")
            if job["status"] == "Selected":
                if st.button("Confirm availability ✅", key=f"confirm_{job['id']}"):
                    jobs_df.loc[jobs_df["id"] == job["id"], "status"] = "Confirmed"
                    save_jobs(jobs_df)
                    _refresh()
            elif job["status"] == "Confirmed":
                if st.button("Start job 🏃", key=f"start_{job['id']}"):
                    jobs_df.loc[jobs_df["id"] == job["id"], "status"] = "In Progress"
                    save_jobs(jobs_df)
                    _refresh()
            elif job["status"] == "In Progress":
                if st.button("Mark job complete ✔️", key=f"done_{job['id']}"):
                    jobs_df.loc[jobs_df["id"] == job["id"], "status"] = "Completed"
                    jobs_df.loc[jobs_df["id"] == job["id"], "time_marked_done"] = datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S")
                    save_jobs(jobs_df)
                    _refresh()
            elif job["status"] == "Completed":
                st.info("Completed — awaiting client payment.")
            elif job["status"] == "Paid":
                st.success("Paid ✅")


elif st.session_state.current_user["role"] == "client":
    inject_custom_bg("client")
    current = st.session_state.current_user
    client_id = str(current["id"])
    st.sidebar.title("🏢 Client Dashboard")
    st.sidebar.write(f"Welcome, **{current['name']}**.")
    if current.get("is_phased"):
        st.sidebar.warning("👁️ ADMIN VIEW MODE")
        if st.sidebar.button("Return to Admin Dashboard ⚡", type="primary"):
            st.session_state.current_user = {"role": "admin", "name": "Administrator"}
            _refresh()
    elif st.sidebar.button("Log Out 🚪", type="primary"):
        _logout()
    st.sidebar.link_button("💬 Contact Administrator", f"https://wa.me/{SUPPORT_NUMBER}", use_container_width=True)

    st.title("Client Job Centre")
    with st.expander("➕ Post a New Job", expanded=True):
        with st.form("client_post_job_form"):
            title = st.text_input("Job title")
            description = st.text_area("Describe the work and requirements")
            hours = st.number_input("Estimated hours", min_value=0.5, value=1.0, step=0.5)
            worker_rate = st.number_input("Worker pay (Ksh/hr)", min_value=0.0, value=150.0, step=10.0)
            client_rate = st.number_input("Your quoted bill (Ksh/hr)", min_value=0.0, value=250.0, step=10.0)
            due_date = st.date_input("Due date")
            due_time = st.time_input("Due time")
            if st.form_submit_button("Post Job 🚀", type="primary"):
                if not title.strip() or not description.strip():
                    st.error("A title and description are required.")
                else:
                    jobs_df = pd.concat([jobs_df, pd.DataFrame([{
                        "id": _job_id(), "title": title.strip(), "client_id": client_id, "worker_id": "",
                        "description": description, "instructions": description, "hours": hours, "rate": worker_rate,
                        "client_rate": client_rate, "status": "Open",
                        "date_posted": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                        "due_date": f"{due_date} {due_time}", "payout": hours * worker_rate,
                        "total_bill": hours * client_rate, "payment_status": "Unpaid", "applications": "[]",
                    }])], ignore_index=True)
                    save_jobs(jobs_df)
                    _refresh()

    my_jobs = jobs_df[jobs_df["client_id"].astype(str) == client_id]
    if my_jobs.empty:
        st.info("You have not posted any jobs.")
    for _, job in my_jobs.iterrows():
        with st.container(border=True):
            st.markdown(f"### {job['title']} · {job['status']}")
            st.caption(f"Due: {job['due_date']} | Invoice total: Ksh {job['total_bill']:,.2f}")
            applications = _job_applications(job)
            if applications and job["status"] in ["Open", "Applied"]:
                st.write("**Applications**")
                for application in applications:
                    worker_id = str(application.get("worker_id", ""))
                    st.write(f"• {application.get('name', get_worker_name(worker_id))} — {application.get('status', 'Pending')}")
                    if application.get("status") != "Selected" and st.button("Select worker", key=f"select_{job['id']}_{worker_id}"):
                        for item in applications:
                            item["status"] = "Selected" if str(item.get("worker_id")) == worker_id else "Declined"
                        jobs_df.loc[jobs_df["id"] == job["id"], ["applications", "worker_id", "status"]] = [_encode_applications(applications), worker_id, "Selected"]
                        save_jobs(jobs_df)
                        _refresh()
            if job["status"] in ["Completed", "Payment Due"]:
                st.info("Job complete. Please settle the invoice.")
                if st.button("Pay invoice 💳", key=f"pay_{job['id']}", type="primary"):
                    jobs_df.loc[jobs_df["id"] == job["id"], ["status", "payment_status", "invoice_id"]] = ["Paid", "Paid", f"INV-{job['id']}"]
                    save_jobs(jobs_df)
                    _add_accounting(f"Client payment for {job['title']}", job["total_bill"], "Income", job["id"], client_id)
                    _refresh()
            elif job["status"] == "Paid":
                st.success(f"Invoice {job.get('invoice_id') or job['id']} paid ✅")
