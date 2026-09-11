"""WhatsApp notifications for the SSS employment portal.

The notifier is best-effort.  A marker is written only after a message is
sent, allowing a later scan to retry failed notifications.  ``Workers`` and
``Clients`` remain supported as legacy worksheet titles.
"""

import json
import os
import time

import gspread
import pandas as pd
import pytz
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


SHEET_URL = os.getenv(
    "SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing",
)
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "0799084376")
PORTAL_URL = os.getenv("PORTAL_URL", "https://3wfppg3ykc6sulf5tclxdp.streamlit.app/")

VACANCY_HEADERS = [
    "id", "title", "employer_id", "job_seeker_id", "description", "requirements",
    "employment_type", "location", "salary", "application_deadline", "status",
    "date_posted", "applications", "cancel_reason", "msg_posted",
    "msg_application", "msg_shortlisted", "msg_hired", "msg_rejected", "msg_closed",
]
ACCEPTED = {"verified", "accredited", "approved", "yes", "true", "1"}


def send_whatsapp_msg(phone, message):
    """Send one text message through Meta's official Cloud API."""
    phone = str(phone or "").strip()
    if not phone or phone.lower() in {"nan", "none"}:
        return False
    token = os.getenv("WA_TOKEN")
    phone_id = os.getenv("WA_PHONE_ID")
    if not token or not phone_id:
        print("WhatsApp service is not configured (WA_TOKEN/WA_PHONE_ID missing).")
        return False
    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code not in (200, 201):
            print(f"WhatsApp API returned HTTP {response.status_code}.")
            return False
        return True
    except requests.RequestException as exc:
        print(f"WhatsApp request failed: {exc}")
        return False


def _load_workbook():
    credentials_value = os.getenv("GCP_SERVICE_ACCOUNT")
    if not credentials_value:
        print("No GCP credentials found; notification scan skipped.")
        return None
    try:
        credentials_value = credentials_value.strip().strip("'").strip('"')
        if credentials_value.endswith(".json") and os.path.exists(credentials_value):
            client = gspread.service_account(filename=credentials_value)
        else:
            client = gspread.service_account_from_dict(json.loads(credentials_value))
        return client.open_by_url(SHEET_URL)
    except (ValueError, json.JSONDecodeError, OSError, gspread.exceptions.GSpreadException) as exc:
        print(f"Failed to load Google Sheets: {exc}")
        return None


def _records(workbook, *titles):
    for title in titles:
        try:
            return pd.DataFrame(workbook.worksheet(title).get_all_records())
        except gspread.exceptions.WorksheetNotFound:
            continue
        except gspread.exceptions.GSpreadException as exc:
            print(f"Could not read worksheet {title}: {exc}")
            return pd.DataFrame()
    print(f"Required worksheet is missing: {titles[0]}")
    return pd.DataFrame()


def _value(row, field, default=""):
    value = row.get(field, default)
    return default if pd.isna(value) else value


def _applications(value):
    try:
        parsed = json.loads(str(value)) if value and str(value).lower() != "nan" else []
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _person(frame, person_id):
    if frame.empty or "id" not in frame:
        return None
    match = frame[frame["id"].astype(str) == str(person_id)]
    return match.iloc[0] if not match.empty else None


def _verified(person):
    if person is None:
        return False
    return (
        str(person.get("verification_status", "")).lower() in ACCEPTED
        and str(person.get("accreditation_status", "")).lower() in ACCEPTED
        and str(person.get("active", "Yes")).lower() not in {"no", "false", "0"}
    )


def _phone(frame, person_id):
    person = _person(frame, person_id)
    return str(person.get("phone", "")) if person is not None else ""


def _name(frame, person_id, fallback):
    person = _person(frame, person_id)
    return str(person.get("name", fallback)) if person is not None else fallback


def _seeker_id(application):
    return str(application.get("job_seeker_id", application.get("worker_id", "")))


def _canonical_status(value):
    value = str(value or "").strip()
    return {
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
    }.get(value.lower(), value or "Open")


def _save_jobs(ws, jobs):
    jobs = jobs.fillna("")
    ws.clear()
    ws.update([jobs.columns.tolist()] + jobs.astype(object).values.tolist())


def job_scan():
    """Announce vacancies and hiring lifecycle changes, not execution or financial reminders."""
    print("Scanning SSS employment database...")
    workbook = _load_workbook()
    if workbook is None:
        return
    job_seekers = _records(workbook, "Workers", "Job Seekers")
    employers = _records(workbook, "Clients", "Employers")
    try:
        jobs_ws = workbook.worksheet("Jobs")
    except gspread.exceptions.WorksheetNotFound:
        print("Required worksheet is missing: Jobs")
        return
    jobs = pd.DataFrame(jobs_ws.get_all_records())
    if jobs.empty:
        print("No vacancies found.")
        return
    for header in VACANCY_HEADERS:
        if header not in jobs.columns:
            jobs[header] = ""
    for index, row in jobs.iterrows():
        title = str(_value(row, "title", "Untitled vacancy"))
        status = _canonical_status(_value(row, "status", "Open"))
        employer_id = str(_value(row, "employer_id", _value(row, "client_id")))
        employer = _person(employers, employer_id)
        if not _verified(employer):
            continue
        employer_name = _name(employers, employer_id, "Employer")
        employer_phone = _phone(employers, employer_id)
        applications = _applications(_value(row, "applications"))
        updates_made = False

        # Announce a new vacancy only to active, verified and accredited seekers.
        if status in {"Open", "Applications"} and not _value(row, "msg_posted"):
            sent_any = False
            for _, seeker in job_seekers.iterrows():
                if _verified(seeker):
                    sent_any = send_whatsapp_msg(
                        seeker.get("phone", ""),
                        f"*New Employment Vacancy*\nDear {seeker.get('name', 'Job seeker')}, "
                        f"*{title}* is available from {employer_name}.\n"
                        f"Employment: {_value(row, 'employment_type', 'Not specified')} | "
                        f"Location: {_value(row, 'location', 'Not specified')}\n"
                        f"Compensation: {_value(row, 'salary', 'Not specified')}\n"
                        f"Apply by: {_value(row, 'application_deadline', 'Not specified')}.\n"
                        f"Apply in the portal: {PORTAL_URL}",
                    ) or sent_any
            if employer_phone:
                sent_any = send_whatsapp_msg(
                    employer_phone,
                    f"*Vacancy Published*\nYour vacancy *{title}* is now visible "
                    f"to verified and accredited job seekers.\n{PORTAL_URL}",
                ) or sent_any
            if sent_any or job_seekers.empty:
                jobs.at[index, "msg_posted"] = "Yes"
                updates_made = True

        pending = [
            app for app in applications
            if str(app.get("status", "Applied")) in {"Applied", "Pending"}
            and _verified(_person(job_seekers, _seeker_id(app)))
        ]
        if pending and employer_phone and not _value(row, "msg_application"):
            names = ", ".join(str(app.get("name", "Job seeker")) for app in pending)
            if send_whatsapp_msg(
                employer_phone,
                f"*New Vacancy Application*\n{names} submitted an application for *{title}*.\n"
                f"Review applications in the portal: {PORTAL_URL}",
            ):
                jobs.at[index, "msg_application"] = "Yes"
                updates_made = True

        shortlisted = [
            app for app in applications if str(app.get("status")) == "Shortlisted"
        ]
        if shortlisted and not _value(row, "msg_shortlisted"):
            sent = False
            for app in shortlisted:
                seeker = _person(job_seekers, _seeker_id(app))
                if _verified(seeker):
                    sent = send_whatsapp_msg(
                        seeker.get("phone", ""),
                        f"*Application Shortlisted*\nYour application for *{title}* "
                        f"with {employer_name} was shortlisted.\n{PORTAL_URL}",
                    ) or sent
            if sent:
                jobs.at[index, "msg_shortlisted"] = "Yes"
                updates_made = True

        hired = [
            app for app in applications if str(app.get("status")) == "Hired"
        ]
        if hired and not _value(row, "msg_hired"):
            sent = False
            for app in hired:
                seeker = _person(job_seekers, _seeker_id(app))
                if _verified(seeker):
                    sent = send_whatsapp_msg(
                        seeker.get("phone", ""),
                        f"*Employment Confirmed*\n{employer_name} has selected you for *{title}*.\n"
                        f"Please review the employment details: {PORTAL_URL}",
                    ) or sent
            if employer_phone:
                sent = send_whatsapp_msg(
                    employer_phone,
                    f"*Hiring Decision Recorded*\nThe hiring decision for *{title}* has been recorded.\n"
                    f"Manage the vacancy: {PORTAL_URL}",
                ) or sent
            if sent:
                jobs.at[index, "msg_hired"] = "Yes"
                updates_made = True

        rejected = [
            app for app in applications if str(app.get("status")) == "Rejected"
        ]
        if rejected and not _value(row, "msg_rejected"):
            sent = False
            for app in rejected:
                seeker = _person(job_seekers, _seeker_id(app))
                if _verified(seeker):
                    sent = send_whatsapp_msg(
                        seeker.get("phone", ""),
                        f"*Application Update*\nYour application for *{title}* "
                        f"was not selected. Please browse other verified opportunities: {PORTAL_URL}",
                    ) or sent
            if sent:
                jobs.at[index, "msg_rejected"] = "Yes"
                updates_made = True

        if status == "Closed" and not _value(row, "msg_closed"):
            sent = send_whatsapp_msg(
                employer_phone,
                f"*Vacancy Closed*\n*{title}* is now closed in the employment portal.",
            ) if employer_phone else False
            for app in applications:
                if app.get("status") in {"Applied", "Pending", "Shortlisted"}:
                    seeker = _person(job_seekers, _seeker_id(app))
                    if _verified(seeker):
                        sent = send_whatsapp_msg(
                            seeker.get("phone", ""),
                            f"*Vacancy Closed*\nApplications for *{title}* are now closed.",
                        ) or sent
            if sent or (employer is None and not applications):
                jobs.at[index, "msg_closed"] = "Yes"
                updates_made = True

        if updates_made:
            jobs.at[index, "status"] = status

    if any(
        str(jobs.at[index, header]) != str(row.get(header, ""))
        for index, row in jobs.iterrows()
        for header in ("msg_posted", "msg_application", "msg_shortlisted", "msg_hired", "msg_rejected", "msg_closed")
    ):
        try:
            _save_jobs(jobs_ws, jobs)
            print("Notification markers saved.")
        except gspread.exceptions.GSpreadException as exc:
            print(f"Failed to save notification markers: {exc}")
    else:
        print("No new notifications needed.")


# Scheduled deployments may still call the old function name.
task_scan = job_scan


def main():
    if os.getenv("GITHUB_ACTIONS") == "true":
        job_scan()
        return
    while True:
        try:
            job_scan()
            time.sleep(900)
        except Exception as exc:
            print(f"Notification scan failed: {exc}")
            time.sleep(300)


if __name__ == "__main__":
    main()
