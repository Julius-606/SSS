"""SSS employment portal.

Google Sheets remains the datastore.  The ``Workers``, ``Clients`` and ``Jobs``
worksheet names are retained as storage-compatible aliases for older
deployments, while the product language is employers, job seekers and
vacancies.
"""

import json
import os
import time
from datetime import datetime

import gspread
import pandas as pd
import pytz
import streamlit as st
from google.oauth2.service_account import Credentials


st.set_page_config(
    page_title="SSS Employment Portal",
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

# Sheet titles remain compatible with the existing workbook.
JOB_SEEKER_HEADERS = [
    "id", "name", "username", "password", "phone", "skills",
    "verification_status", "accreditation_status", "accreditation_id", "active",
]
EMPLOYER_HEADERS = [
    "id", "name", "username", "password", "phone", "email", "address",
    "verification_status", "accreditation_status", "accreditation_id", "active",
]
VACANCY_HEADERS = [
    "id", "title", "employer_id", "job_seeker_id", "description", "requirements",
    "employment_type", "location", "salary", "application_deadline", "status",
    "date_posted", "applications", "cancel_reason", "msg_posted",
    "msg_application", "msg_shortlisted", "msg_hired", "msg_rejected", "msg_closed",
]
SETTINGS_HEADERS = ["setting_key", "setting_value"]
ACCOUNTING_HEADERS = [
    "tx_id", "date", "type", "description", "amount", "status", "job_id",
    "client_id",
]
# Compatibility names for integrations that imported the old constants.
WORKER_HEADERS = JOB_SEEKER_HEADERS
CLIENT_HEADERS = EMPLOYER_HEADERS
JOB_HEADERS = VACANCY_HEADERS


def inject_custom_bg(role):
    if role == "admin":
        colors = ("#e0f2fe", "#ffffff", "#e5e7eb", "#334155")
    elif role == "job_seeker":
        colors = ("#ffffff", "#f0f9ff", "#f3f4f6", "#334155")
    elif role == "employer":
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


def _canonical_status(value):
    value = str(value or "").strip()
    normalised = {
        "open": "Open",
        "applied": "Applications",
        "applications": "Applications",
        "selected": "Shortlisted",
        "shortlisted": "Shortlisted",
        "confirmed": "Hired",
        "hired": "Hired",
        "in progress": "Hired",
        "completed": "Closed",
        "payment due": "Closed",
        "paid": "Closed",
        "cancelled": "Closed",
        "closed": "Closed",
        "withdrawn": "Withdrawn",
        "rejected": "Rejected",
    }
    return normalised.get(value.lower(), value or "Open")


@st.cache_resource
def get_gspread_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        return gspread.authorize(
            Credentials.from_service_account_info(creds_dict, scopes=scopes)
        )
    except Exception as exc:
        st.error(f"Database authentication failed: {exc}")
        st.stop()


def _copy_legacy_records(workbook, new_ws, legacy_title, headers):
    """Copy old Employees/Tasks records only into an empty replacement sheet."""
    if new_ws.get_all_records():
        return
    try:
        legacy = workbook.worksheet(legacy_title)
        records = legacy.get_all_records()
    except (gspread.exceptions.WorksheetNotFound, gspread.exceptions.GSpreadException):
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
                "verification_status": record.get("verification_status", "Pending"),
                "accreditation_status": record.get("accreditation_status", "Pending"),
            })
        else:
            item.update({
                "id": record.get("id", ""),
                "title": record.get("title", ""),
                "employer_id": record.get("client_id", ""),
                "job_seeker_id": record.get("employee_Id", record.get("worker_id", "")),
                "description": record.get("description", record.get("instructions", "")),
                "requirements": record.get("requirements", record.get("instructions", "")),
                "status": _canonical_status(record.get("status", "Open")),
                "date_posted": record.get("date_assigned", ""),
                "application_deadline": record.get("application_deadline", record.get("due_date", "")),
                "applications": record.get("applications", "[]"),
            })
        migrated.append([item.get(header, "") for header in headers])
    if migrated:
        new_ws.append_rows(migrated)


@st.cache_resource
def get_worksheets():
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
                    start = len(existing) + 1
                    end = start + len(missing) - 1
                    ws.update(
                        values=[missing],
                        range_name=(
                            f"{gspread.utils.rowcol_to_a1(1, start)}:"
                            f"{gspread.utils.rowcol_to_a1(1, end)}"
                        ),
                    )
            return ws
        except gspread.exceptions.WorksheetNotFound:
            ws = workbook.add_worksheet(
                title=title, rows="2000", cols=max(20, len(headers))
            )
            ws.append_row(headers)
            return ws

    job_seekers_ws = get_or_create("Workers", JOB_SEEKER_HEADERS)
    employers_ws = get_or_create("Clients", EMPLOYER_HEADERS)
    vacancies_ws = get_or_create("Jobs", VACANCY_HEADERS)
    settings_ws = get_or_create("Settings", SETTINGS_HEADERS)
    # Keep this worksheet so existing finance data is not deleted, although
    # employment workflows no longer create or display payment records.
    accounting_ws = get_or_create("Accounting", ACCOUNTING_HEADERS)
    _copy_legacy_records(workbook, job_seekers_ws, "Employees", JOB_SEEKER_HEADERS)
    _copy_legacy_records(workbook, vacancies_ws, "Tasks", VACANCY_HEADERS)
    return (
        workbook, job_seekers_ws, employers_ws, vacancies_ws, settings_ws,
        accounting_ws,
    )


workbook, job_seekers_ws, employers_ws, vacancies_ws, settings_ws, accounting_ws = (
    get_worksheets()
)


def _empty_frame(headers):
    return pd.DataFrame(columns=headers)


def _normalise_people(frame, headers):
    frame = frame.copy() if not frame.empty else _empty_frame(headers)
    for header in headers:
        if header not in frame.columns:
            frame[header] = ""
    for column in headers:
        frame[column] = frame[column].fillna("").astype(str)
    for column in ("verification_status", "accreditation_status"):
        frame[column] = frame[column].replace("", "Pending")
    frame["active"] = frame["active"].replace("", "Yes")
    return frame


def _normalise_vacancies(frame):
    frame = frame.copy() if not frame.empty else _empty_frame(VACANCY_HEADERS)
    for header in VACANCY_HEADERS:
        if header not in frame.columns:
            frame[header] = ""
    # Populate canonical fields from old names without deleting old columns.
    for index, row in frame.iterrows():
        if not str(row.get("employer_id", "")).strip():
            frame.at[index, "employer_id"] = row.get("client_id", "")
        if not str(row.get("job_seeker_id", "")).strip():
            frame.at[index, "job_seeker_id"] = row.get("worker_id", "")
        if not str(row.get("description", "")).strip():
            frame.at[index, "description"] = row.get("instructions", "")
        if not str(row.get("requirements", "")).strip():
            frame.at[index, "requirements"] = row.get("description", row.get("instructions", ""))
        if not str(row.get("application_deadline", "")).strip():
            frame.at[index, "application_deadline"] = row.get("due_date", "")
        if not str(row.get("salary", "")).strip():
            legacy_pay = row.get("payout", "") or row.get("rate", "")
            if str(legacy_pay).strip():
                frame.at[index, "salary"] = f"Legacy compensation: Ksh {legacy_pay}"
        frame.at[index, "status"] = _canonical_status(row.get("status", "Open"))
        if not str(row.get("applications", "")).strip():
            frame.at[index, "applications"] = "[]"
    for column in VACANCY_HEADERS:
        frame[column] = frame[column].fillna("").astype(str)
    return frame


@st.cache_data(ttl=30)
def fetch_portal_data():
    job_seekers = _normalise_people(
        pd.DataFrame(job_seekers_ws.get_all_records()), JOB_SEEKER_HEADERS
    )
    employers = _normalise_people(
        pd.DataFrame(employers_ws.get_all_records()), EMPLOYER_HEADERS
    )
    vacancies = _normalise_vacancies(pd.DataFrame(vacancies_ws.get_all_records()))
    accounting = pd.DataFrame(accounting_ws.get_all_records())
    return job_seekers, employers, vacancies, accounting


job_seekers_df, employers_df, vacancies_df, acct_df = fetch_portal_data()


def _save_frame(ws, frame):
    clean = frame.fillna("").copy()
    ws.clear()
    ws.update([clean.columns.tolist()] + clean.astype(object).values.tolist())


def save_vacancies(frame):
    _save_frame(vacancies_ws, _normalise_vacancies(frame))
    fetch_portal_data.clear()


def save_job_seekers(frame):
    _save_frame(job_seekers_ws, _normalise_people(frame, JOB_SEEKER_HEADERS))
    fetch_portal_data.clear()


def save_employers(frame):
    _save_frame(employers_ws, _normalise_people(frame, EMPLOYER_HEADERS))
    fetch_portal_data.clear()


def _name_for(frame, value, unknown):
    if frame.empty:
        return unknown
    match = frame[frame["id"].astype(str) == str(value)]
    return str(match.iloc[0]["name"]) if not match.empty else unknown


def get_job_seeker_name(value):
    return _name_for(job_seekers_df, value, "Unknown job seeker")


def get_employer_name(value):
    return _name_for(employers_df, value, "Unknown employer")


def _parse_applications(value):
    if not value or str(value).lower() in {"nan", "none"}:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _encode_applications(applications):
    return json.dumps(applications, separators=(",", ":"))


def _job_id():
    return f"vacancy-{int(time.time() * 1000)}"


def _refresh():
    fetch_portal_data.clear()
    st.rerun()


def _logout():
    st.session_state.current_user = None
    _refresh()


def _verified(row):
    accepted = {"verified", "accredited", "approved", "yes", "true", "1"}
    verification = str(row.get("verification_status", "")).strip().lower()
    accreditation = str(row.get("accreditation_status", "")).strip().lower()
    return verification in accepted and accreditation in accepted


def _active(row):
    return str(row.get("active", "Yes")).strip().lower() not in {"no", "false", "0"}


def _deadline_passed(value):
    if not value or str(value).strip().lower() in {"nan", "none"}:
        return False
    try:
        deadline = datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        return False
    return deadline.date() < datetime.now(KISUMU_TZ).date()


def _application_seeker_id(application):
    return str(application.get("job_seeker_id", application.get("worker_id", "")))


def _application_for(application, seeker_id):
    return _application_seeker_id(application) == str(seeker_id)


def _application_statuses(job):
    return _parse_applications(job.get("applications", ""))


def _new_vacancy_row(**values):
    row = {header: "" for header in VACANCY_HEADERS}
    row.update(values)
    row["applications"] = row.get("applications") or "[]"
    row["date_posted"] = row.get("date_posted") or datetime.now(KISUMU_TZ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return row


if "current_user" not in st.session_state:
    st.session_state.current_user = None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
if st.session_state.current_user is None:
    inject_custom_bg("login")
    left, centre, right = st.columns([1, 2, 1])
    with centre:
        st.markdown(
            "<h1 style='text-align:center'>SSS Employment Portal</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center'>Verified businesses and accredited job seekers.</p>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            with st.form("login_form"):
                login_user = st.text_input("Username")
                login_pass = st.text_input("Password", type="password")
                submitted = st.form_submit_button(
                    "Sign In", use_container_width=True, type="primary"
                )
            if submitted:
                if login_user == ADMIN_USER and login_pass == ADMIN_PASS:
                    st.session_state.current_user = {
                        "role": "admin", "name": "Administrator",
                    }
                    _refresh()
                seeker_match = job_seekers_df[
                    (job_seekers_df["username"] == login_user)
                    & (job_seekers_df["password"] == login_pass)
                    & job_seekers_df.apply(_active, axis=1)
                ]
                employer_match = employers_df[
                    (employers_df["username"] == login_user)
                    & (employers_df["password"] == login_pass)
                    & employers_df.apply(_active, axis=1)
                ]
                if not seeker_match.empty or not employer_match.empty:
                    row = (
                        seeker_match.iloc[0] if not seeker_match.empty
                        else employer_match.iloc[0]
                    )
                    role = "job_seeker" if not seeker_match.empty else "employer"
                    if not _verified(row):
                        st.error("Your account must be verified and accredited before you can participate.")
                    else:
                        st.session_state.current_user = {
                            "role": role, "id": row["id"], "name": row["name"],
                            "is_phased": False,
                        }
                        _refresh()
                elif not (login_user == ADMIN_USER and login_pass == ADMIN_PASS):
                    st.error("The credentials provided are invalid. Access denied.")


elif st.session_state.current_user["role"] == "admin":
    inject_custom_bg("admin")
    st.sidebar.title("Administration Portal")
    admin_view = st.sidebar.radio(
        "Navigation", ["Employer and Job Seeker Management", "Vacancy Management"]
    )
    if st.sidebar.button("Sign Out", type="primary", use_container_width=True):
        _logout()

    st.sidebar.subheader("Preview User Dashboard")
    phase_type = st.sidebar.selectbox("Dashboard type", ["Job Seeker", "Employer"])
    phase_frame = job_seekers_df if phase_type == "Job Seeker" else employers_df
    verified_phase = phase_frame[phase_frame.apply(_verified, axis=1)] if not phase_frame.empty else phase_frame
    if not verified_phase.empty:
        phase_target = st.sidebar.selectbox("Select user", verified_phase["name"].tolist())
        if st.sidebar.button("Open Dashboard", use_container_width=True):
            row = verified_phase[verified_phase["name"] == phase_target].iloc[0]
            st.session_state.current_user = {
                "role": "job_seeker" if phase_type == "Job Seeker" else "employer",
                "id": row["id"], "name": row["name"], "is_phased": True,
            }
            _refresh()

    if admin_view == "Employer and Job Seeker Management":
        st.title("Employer and Job Seeker Management")
        employer_col, seeker_col = st.columns(2)
        with employer_col:
            st.subheader("Register Employer or Business")
            with st.form("add_employer_form"):
                name = st.text_input("Business name")
                username = st.text_input("Employer username")
                password = st.text_input("Employer password", type="password")
                phone = st.text_input("Business phone")
                email = st.text_input("Business email")
                address = st.text_input("Business address")
                verification = st.selectbox("Verification", ["Pending", "Verified"])
                accreditation = st.selectbox("Accreditation", ["Pending", "Accredited"])
                accreditation_id = st.text_input("Accreditation ID")
                if st.form_submit_button("Register Employer"):
                    usernames = set(job_seekers_df["username"]) | set(employers_df["username"])
                    if not all([name, username, password, phone]):
                        st.error("Name, username, password and phone are required.")
                    elif username in usernames:
                        st.error("Username already taken.")
                    elif accreditation == "Accredited" and not accreditation_id.strip():
                        st.error("An accreditation ID is required for an accredited employer.")
                    else:
                        employers_df = pd.concat([employers_df, pd.DataFrame([{
                            "id": f"employer-{int(time.time())}", "name": name,
                            "username": username, "password": password, "phone": phone,
                            "email": email, "address": address,
                            "verification_status": verification,
                            "accreditation_status": accreditation,
                            "accreditation_id": accreditation_id, "active": "Yes",
                        }])], ignore_index=True)
                        save_employers(employers_df)
                        st.success("Employer account created successfully.")
                        _refresh()
            st.dataframe(
                employers_df.drop(columns=["password"], errors="ignore"),
                hide_index=True, use_container_width=True,
            )
            if not employers_df.empty:
                edit_name = st.selectbox(
                    "Employer account to manage", employers_df["name"].tolist(),
                    key="edit_employer_name",
                )
                selected = employers_df[employers_df["name"] == edit_name].iloc[0]
                with st.form("edit_employer_form"):
                    edit_verification = st.selectbox(
                        "Employer verification",
                        ["Pending", "Verified"],
                        index=0 if str(selected["verification_status"]).lower() != "verified" else 1,
                    )
                    edit_accreditation = st.selectbox(
                        "Employer accreditation",
                        ["Pending", "Accredited"],
                        index=0 if str(selected["accreditation_status"]).lower() != "accredited" else 1,
                    )
                    edit_accreditation_id = st.text_input(
                        "Employer accreditation ID",
                        value=str(selected.get("accreditation_id", "")),
                    )
                    edit_active = st.selectbox(
                        "Employer account active", ["Yes", "No"],
                        index=0 if _active(selected) else 1,
                    )
                    if st.form_submit_button("Save Employer Account"):
                        employers_df.loc[
                            employers_df["id"] == selected["id"],
                            ["verification_status", "accreditation_status", "accreditation_id", "active"],
                        ] = [
                            edit_verification, edit_accreditation,
                            edit_accreditation_id, edit_active,
                        ]
                        save_employers(employers_df)
                        _refresh()
        with seeker_col:
            st.subheader("Register Job Seeker")
            with st.form("add_seeker_form"):
                name = st.text_input("Full name")
                username = st.text_input("Job seeker username")
                password = st.text_input("Job seeker password", type="password")
                phone = st.text_input("Job seeker phone")
                skills = st.text_input("Skills and experience")
                verification = st.selectbox("Verification status", ["Pending", "Verified"])
                accreditation = st.selectbox("Accreditation status", ["Pending", "Accredited"])
                accreditation_id = st.text_input("Job seeker accreditation ID")
                if st.form_submit_button("Register Job Seeker"):
                    usernames = set(job_seekers_df["username"]) | set(employers_df["username"])
                    if not all([name, username, password, phone]):
                        st.error("Name, username, password and phone are required.")
                    elif username in usernames:
                        st.error("Username already taken.")
                    elif accreditation == "Accredited" and not accreditation_id.strip():
                        st.error("An accreditation ID is required for an accredited job seeker.")
                    else:
                        job_seekers_df = pd.concat([job_seekers_df, pd.DataFrame([{
                            "id": f"job-seeker-{int(time.time())}", "name": name,
                            "username": username, "password": password, "phone": phone,
                            "skills": skills, "verification_status": verification,
                            "accreditation_status": accreditation,
                            "accreditation_id": accreditation_id, "active": "Yes",
                        }])], ignore_index=True)
                        save_job_seekers(job_seekers_df)
                        st.success("Job seeker account created successfully.")
                        _refresh()
            st.dataframe(
                job_seekers_df.drop(columns=["password"], errors="ignore"),
                hide_index=True, use_container_width=True,
            )
            if not job_seekers_df.empty:
                edit_name = st.selectbox(
                    "Job seeker account to manage", job_seekers_df["name"].tolist(),
                    key="edit_seeker_name",
                )
                selected = job_seekers_df[job_seekers_df["name"] == edit_name].iloc[0]
                with st.form("edit_seeker_form"):
                    edit_verification = st.selectbox(
                        "Job seeker verification",
                        ["Pending", "Verified"],
                        index=0 if str(selected["verification_status"]).lower() != "verified" else 1,
                    )
                    edit_accreditation = st.selectbox(
                        "Job seeker accreditation",
                        ["Pending", "Accredited"],
                        index=0 if str(selected["accreditation_status"]).lower() != "accredited" else 1,
                    )
                    edit_accreditation_id = st.text_input(
                        "Job seeker accreditation ID",
                        value=str(selected.get("accreditation_id", "")),
                    )
                    edit_active = st.selectbox(
                        "Job seeker account active", ["Yes", "No"],
                        index=0 if _active(selected) else 1,
                    )
                    if st.form_submit_button("Save Job Seeker Account"):
                        job_seekers_df.loc[
                            job_seekers_df["id"] == selected["id"],
                            ["verification_status", "accreditation_status", "accreditation_id", "active"],
                        ] = [
                            edit_verification, edit_accreditation,
                            edit_accreditation_id, edit_active,
                        ]
                        save_job_seekers(job_seekers_df)
                        _refresh()
    else:
        st.title("Vacancy Management")
        employer_options = {
            row["name"]: row["id"]
            for _, row in employers_df[employers_df.apply(_verified, axis=1)].iterrows()
        }
        with st.form("admin_post_vacancy_form"):
            title = st.text_input("Vacancy title")
            description = st.text_area("Role description")
            requirements = st.text_area("Requirements and qualifications")
            employment_type = st.selectbox(
                "Employment type", ["Full-time", "Part-time", "Contract", "Temporary", "Internship"]
            )
            location = st.text_input("Location / work arrangement")
            salary = st.text_input("Salary / compensation")
            deadline = st.date_input("Application deadline")
            employer_name = st.selectbox("Employer", list(employer_options) or ["No verified employers"])
            post = st.form_submit_button("Publish Vacancy", type="primary")
        if post:
            if not title.strip() or not description.strip() or not employer_options:
                st.error("A title, description and verified employer are required.")
            else:
                vacancies_df = pd.concat([vacancies_df, pd.DataFrame([_new_vacancy_row(
                    id=_job_id(), title=title.strip(), employer_id=employer_options[employer_name],
                    description=description, requirements=requirements,
                    employment_type=employment_type, location=location, salary=salary,
                    application_deadline=str(deadline), status="Open",
                )])], ignore_index=True)
                save_vacancies(vacancies_df)
                st.success("Vacancy published.")
                _refresh()
        st.dataframe(
            vacancies_df[["id", "title", "employer_id", "employment_type", "location",
                          "salary", "application_deadline", "status"]],
            hide_index=True, use_container_width=True,
        )


elif st.session_state.current_user["role"] == "employer":
    inject_custom_bg("employer")
    current = st.session_state.current_user
    employer_id = str(current["id"])
    st.sidebar.title("Employer Dashboard")
    st.sidebar.write(f"Signed in as **{current['name']}**.")
    if current.get("is_phased"):
        st.sidebar.warning("Administrator Preview Mode")
        if st.sidebar.button("Return to Administration Dashboard", type="primary"):
            st.session_state.current_user = {"role": "admin", "name": "Administrator"}
            _refresh()
    elif st.sidebar.button("Sign Out", type="primary"):
        _logout()
    st.sidebar.link_button("Contact Administrator", f"https://wa.me/{SUPPORT_NUMBER}", use_container_width=True)

    st.title("Vacancy Administration")
    with st.expander("Publish a New Vacancy", expanded=True):
        with st.form("employer_post_vacancy_form"):
            title = st.text_input("Vacancy title")
            description = st.text_area("Role description")
            requirements = st.text_area("Requirements and qualifications")
            employment_type = st.selectbox(
                "Employment type", ["Full-time", "Part-time", "Contract", "Temporary", "Internship"]
            )
            location = st.text_input("Location / work arrangement")
            salary = st.text_input("Salary / compensation")
            deadline = st.date_input("Application deadline")
            if st.form_submit_button("Publish Vacancy", type="primary"):
                if not title.strip() or not description.strip():
                    st.error("A title and role description are required.")
                else:
                    vacancies_df = pd.concat([vacancies_df, pd.DataFrame([_new_vacancy_row(
                        id=_job_id(), title=title.strip(), employer_id=employer_id,
                        description=description, requirements=requirements,
                        employment_type=employment_type, location=location, salary=salary,
                        application_deadline=str(deadline), status="Open",
                    )])], ignore_index=True)
                    save_vacancies(vacancies_df)
                    st.success("Vacancy published.")
                    _refresh()

    my_vacancies = vacancies_df[vacancies_df["employer_id"].astype(str) == employer_id]
    if my_vacancies.empty:
        st.info("No vacancies have been published for this employer account.")
    for _, vacancy in my_vacancies.iterrows():
        with st.container(border=True):
            st.markdown(f"### {vacancy['title']} · {vacancy['status']}")
            st.write(vacancy.get("description", ""))
            st.caption(
                f"{vacancy.get('employment_type', '')} · {vacancy.get('location', '')} · "
                f"Compensation: {vacancy.get('salary', 'Not specified')} · "
                f"Deadline: {vacancy.get('application_deadline', 'Not specified')}"
            )
            applications = _application_statuses(vacancy)
            if applications:
                st.write("**Applications**")
                for application in applications:
                    seeker_id = _application_seeker_id(application)
                    seeker_name = application.get("name", get_job_seeker_name(seeker_id))
                    app_status = application.get("status", "Applied")
                    st.write(f"• {seeker_name} — {app_status}")
                    action_col, reject_col = st.columns(2)
                    if app_status in {"Applied", "Pending"}:
                        if action_col.button("Shortlist", key=f"shortlist_{vacancy['id']}_{seeker_id}"):
                            application["status"] = "Shortlisted"
                            vacancies_df.loc[vacancies_df["id"] == vacancy["id"], ["applications", "status"]] = [
                                _encode_applications(applications), "Shortlisted"
                            ]
                            save_vacancies(vacancies_df)
                            _refresh()
                        if reject_col.button("Reject", key=f"reject_{vacancy['id']}_{seeker_id}"):
                            application["status"] = "Rejected"
                            vacancies_df.loc[vacancies_df["id"] == vacancy["id"], "applications"] = _encode_applications(applications)
                            save_vacancies(vacancies_df)
                            _refresh()
                    elif app_status == "Shortlisted":
                        if action_col.button("Hire", key=f"hire_{vacancy['id']}_{seeker_id}", type="primary"):
                            for item in applications:
                                if _application_seeker_id(item) == seeker_id:
                                    item["status"] = "Hired"
                                elif item.get("status") not in {"Withdrawn", "Rejected"}:
                                    item["status"] = "Rejected"
                            vacancies_df.loc[vacancies_df["id"] == vacancy["id"], ["applications", "job_seeker_id", "status"]] = [
                                _encode_applications(applications), seeker_id, "Hired"
                            ]
                            save_vacancies(vacancies_df)
                            _refresh()
            if vacancy["status"] != "Closed":
                if st.button("Close vacancy", key=f"close_{vacancy['id']}"):
                    for item in applications:
                        if item.get("status") in {"Applied", "Pending", "Shortlisted"}:
                            item["status"] = "Rejected"
                    vacancies_df.loc[vacancies_df["id"] == vacancy["id"], ["applications", "status"]] = [
                        _encode_applications(applications), "Closed"
                    ]
                    save_vacancies(vacancies_df)
                    _refresh()


elif st.session_state.current_user["role"] == "job_seeker":
    inject_custom_bg("job_seeker")
    current = st.session_state.current_user
    seeker_id = str(current["id"])
    st.sidebar.title("Job Seeker Dashboard")
    st.sidebar.write(f"Signed in as **{current['name']}**.")
    if current.get("is_phased"):
        st.sidebar.warning("Administrator Preview Mode")
        if st.sidebar.button("Return to Administration Dashboard", type="primary"):
            st.session_state.current_user = {"role": "admin", "name": "Administrator"}
            _refresh()
    elif st.sidebar.button("Sign Out", type="primary"):
        _logout()
    st.sidebar.link_button("Contact Administrator", f"https://wa.me/{SUPPORT_NUMBER}", use_container_width=True)

    st.title("Browse employment opportunities")
    available = vacancies_df[vacancies_df["status"].isin(["Open", "Applications"])]
    for _, vacancy in available.iterrows():
        with st.container(border=True):
            st.markdown(f"### {vacancy['title']}")
            st.write(vacancy.get("description", ""))
            st.write(f"**Requirements:** {vacancy.get('requirements', 'Not specified')}")
            st.caption(
                f"Employer: {get_employer_name(vacancy['employer_id'])} · "
                f"{vacancy.get('employment_type', '')} · {vacancy.get('location', '')} · "
                f"Compensation: {vacancy.get('salary', 'Not specified')} · "
                f"Apply by: {vacancy.get('application_deadline', 'Not specified')}"
            )
            applications = _application_statuses(vacancy)
            existing = next((app for app in applications if _application_for(app, seeker_id)), None)
            deadline_passed = _deadline_passed(vacancy.get("application_deadline", ""))
            if existing:
                st.info(f"Application status: {existing.get('status', 'Applied')}")
                if existing.get("status") in {"Applied", "Pending", "Shortlisted"}:
                    if st.button("Withdraw application", key=f"withdraw_{vacancy['id']}"):
                        existing["status"] = "Withdrawn"
                        vacancies_df.loc[vacancies_df["id"] == vacancy["id"], "applications"] = _encode_applications(applications)
                        save_vacancies(vacancies_df)
                        _refresh()
            elif deadline_passed:
                st.warning("The application deadline has passed.")
            elif st.button("Submit Application", key=f"apply_{vacancy['id']}"):
                applications.append({
                    "job_seeker_id": seeker_id, "name": current["name"],
                    "applied_at": datetime.now(KISUMU_TZ).isoformat(), "status": "Applied",
                })
                vacancies_df.loc[vacancies_df["id"] == vacancy["id"], ["applications", "status"]] = [
                    _encode_applications(applications), "Applications"
                ]
                save_vacancies(vacancies_df)
                _refresh()

    st.subheader("My applications")
    for _, vacancy in vacancies_df.iterrows():
        applications = _application_statuses(vacancy)
        mine = next((app for app in applications if _application_for(app, seeker_id)), None)
        if mine:
            st.write(f"**{vacancy['title']}** — {mine.get('status', 'Applied')} ({vacancy['status']})")
