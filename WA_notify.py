"""WhatsApp notifier for the SSS job connection platform.

The service is intentionally best-effort: a failed notification is logged and
its sheet marker is not written, so the next scheduled run can retry it.
Credentials are read only from environment variables or a service-account
file; none are included in messages or logs.
"""

import json
import os
import time
from datetime import datetime, timedelta

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
KISUMU_TZ = pytz.timezone("Africa/Nairobi")
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "0799084376")
PORTAL_URL = os.getenv("PORTAL_URL", "https://3wfppg3ykc6sulf5tclxdp.streamlit.app/")

JOB_HEADERS = [
    "id", "title", "client_id", "worker_id", "description", "instructions",
    "hours", "rate", "client_rate", "status", "date_posted", "due_date",
    "time_marked_done", "payout", "total_bill", "payment_status", "invoice_id",
    "applications", "application_deadline", "cancel_reason",
    "msg_posted", "msg_application", "msg_selected", "msg_allocated",
    "msg_night_before", "msg_1hr_before", "msg_late", "msg_completed",
    "msg_payment", "msg_admin_cancelled",
]


def send_whatsapp_msg(phone, message):
    """Send one text message through Meta's official Cloud API."""
    phone = str(phone or "").strip()
    if not phone or phone.lower() in {"nan", "none"}:
        print("No valid phone number provided.")
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


def _records(workbook, title):
    try:
        return pd.DataFrame(workbook.worksheet(title).get_all_records())
    except gspread.exceptions.WorksheetNotFound:
        print(f"Required worksheet is missing: {title}")
        return pd.DataFrame()
    except gspread.exceptions.GSpreadException as exc:
        print(f"Could not read worksheet {title}: {exc}")
        return pd.DataFrame()


def _value(row, field, default=""):
    value = row.get(field, default)
    return default if pd.isna(value) else value


def _applications(value):
    try:
        parsed = json.loads(str(value)) if value and str(value) != "nan" else []
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _person(frame, person_id, fallback):
    if frame.empty or "id" not in frame:
        return None
    match = frame[frame["id"].astype(str) == str(person_id)]
    return match.iloc[0] if not match.empty else None


def _phone(frame, person_id):
    person = _person(frame, person_id, "")
    return str(person.get("phone", "")) if person is not None else ""


def _name(frame, person_id, fallback):
    person = _person(frame, person_id, fallback)
    return str(person.get("name", fallback)) if person is not None else fallback


def _parse_due(value):
    if not value or str(value).lower() in {"nan", "none"}:
        return None
    text = str(value)
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return KISUMU_TZ.localize(datetime.strptime(text, pattern))
        except ValueError:
            continue
    return None


def _save_jobs(ws, jobs):
    """Persist notification markers while retaining any new job columns."""
    jobs = jobs.fillna("")
    ws.clear()
    ws.update([jobs.columns.tolist()] + jobs.astype(object).values.tolist())


def job_scan():
    """Scan Jobs and emit posting, application, selection and job reminders."""
    print("Scanning SSS job database...")
    workbook = _load_workbook()
    if workbook is None:
        return
    workers = _records(workbook, "Workers")
    clients = _records(workbook, "Clients")
    jobs_ws = None
    try:
        jobs_ws = workbook.worksheet("Jobs")
    except gspread.exceptions.WorksheetNotFound:
        print("Required worksheet is missing: Jobs")
        return
    jobs = pd.DataFrame(jobs_ws.get_all_records())
    if jobs.empty:
        print("No jobs found.")
        return
    for header in JOB_HEADERS:
        if header not in jobs.columns:
            jobs[header] = ""
    jobs["client_id"] = jobs["client_id"].fillna("").astype(str)
    jobs["worker_id"] = jobs["worker_id"].fillna("").astype(str)
    now = datetime.now(KISUMU_TZ)
    updates_made = False

    for index, job in jobs.iterrows():
        job_id = str(_value(job, "id", index))
        title = str(_value(job, "title", "Untitled job"))
        status = str(_value(job, "status", ""))
        client_id = str(_value(job, "client_id"))
        worker_id = str(_value(job, "worker_id"))
        payment_status = str(_value(job, "payment_status"))
        client_name = _name(clients, client_id, "Client")
        worker_name = _name(workers, worker_id, "Worker")
        client_phone = _phone(clients, client_id)
        worker_phone = _phone(workers, worker_id)

        # Notify all active workers once when a client/admin posts a job.
        if status in {"Open", "Applied"} and not _value(job, "msg_posted"):
            sent_any = False
            if not workers.empty:
                for _, worker in workers.iterrows():
                    active = str(worker.get("active", "Yes")).lower()
                    if active not in {"no", "false", "0"}:
                        sent_any = send_whatsapp_msg(
                            worker.get("phone", ""),
                            f"📢 *New Job Posting*\nHello {worker.get('name', 'Worker')}, "
                            f"*{title}* is available from {client_name}.\nDue: {_value(job, 'due_date', 'TBC')}.\n"
                            f"Apply in the portal: {PORTAL_URL}",
                        ) or sent_any
            if client_phone:
                sent_any = send_whatsapp_msg(
                    client_phone,
                    f"📌 *Job Posted*\nYour job *{title}* is now visible to verified workers.\n"
                    f"Track applications in the portal: {PORTAL_URL}",
                ) or sent_any
            if sent_any or workers.empty:
                jobs.at[index, "msg_posted"] = "Yes"
                updates_made = True

        # One notification per scan cycle is enough for a new application.
        applications = _applications(_value(job, "applications"))
        pending_apps = [app for app in applications if str(app.get("status", "Pending")) == "Pending"]
        if pending_apps and client_phone and not _value(job, "msg_application"):
            applicant_names = ", ".join(str(app.get("name", "Worker")) for app in pending_apps)
            if send_whatsapp_msg(
                client_phone,
                f"📝 *New Job Application*\n{applicant_names} applied for *{title}*.\n"
                f"Review applications in the SSS portal: {PORTAL_URL}",
            ):
                jobs.at[index, "msg_application"] = "Yes"
                updates_made = True

        # Selection/assignment notification goes to both sides.
        if worker_id and status in {"Selected", "Confirmed"} and not _value(job, "msg_selected"):
            sent = send_whatsapp_msg(
                worker_phone,
                f"🎉 *Worker Selected*\nHello {worker_name}, {client_name} selected you for "
                f"*{title}*, due {_value(job, 'due_date', 'TBC')}.\nConfirm in the portal: {PORTAL_URL}",
            )
            sent = send_whatsapp_msg(
                client_phone,
                f"✅ *Worker Selection Confirmed*\n{worker_name} is assigned to *{title}*.\n"
                f"Track the job in the portal: {PORTAL_URL}",
            ) or sent
            if sent:
                jobs.at[index, "msg_selected"] = "Yes"
                jobs.at[index, "msg_allocated"] = "Yes"
                updates_made = True

        # Completed jobs prompt the client to pay; paid jobs close the loop.
        if status in {"Completed", "Payment Due"} and not _value(job, "msg_completed"):
            if send_whatsapp_msg(
                client_phone,
                f"✔️ *Job Completed*\n{worker_name} marked *{title}* complete.\n"
                f"Invoice total: Ksh {_value(job, 'total_bill', '0')}.\nPlease review and pay in the portal.",
            ):
                jobs.at[index, "msg_completed"] = "Yes"
                updates_made = True
        if (status == "Paid" or payment_status == "Paid") and not _value(job, "msg_payment"):
            sent = send_whatsapp_msg(
                worker_phone,
                f"💰 *Payment Released*\nPayment for *{title}* from {client_name} has been recorded.\n"
                f"Amount: Ksh {_value(job, 'payout', '0')}.",
            )
            if sent:
                jobs.at[index, "msg_payment"] = "Yes"
                updates_made = True

        # Cancellation is an administrative alert, independent of reminders.
        if status == "Cancelled" and _value(job, "cancel_reason") and not _value(job, "msg_admin_cancelled"):
            if send_whatsapp_msg(
                ADMIN_CONTACT,
                f"🚨 *Job Cancellation Alert*\nWorker: {worker_name}\nClient: {client_name}\n"
                f"Job: {title}\nReason: {_value(job, 'cancel_reason')}",
            ):
                jobs.at[index, "msg_admin_cancelled"] = "Yes"
                updates_made = True
            continue

        # Job-centric schedule reminders and late alerts.
        due = _parse_due(_value(job, "due_date"))
        if due is None or not worker_phone or status not in {"Selected", "Confirmed", "In Progress"}:
            continue
        time_diff = due - now
        if timedelta(hours=12) < time_diff <= timedelta(hours=24) and not _value(job, "msg_night_before"):
            if send_whatsapp_msg(worker_phone, f"🌙 *Job Reminder*\n{title} is scheduled tomorrow at {due.strftime('%I:%M %p')}."):
                jobs.at[index, "msg_night_before"] = "Yes"
                updates_made = True
        if timedelta(minutes=0) < time_diff <= timedelta(hours=1) and not _value(job, "msg_1hr_before"):
            if send_whatsapp_msg(worker_phone, f"⏳ *1 Hour Reminder*\nPlease prepare for *{title}*.\n{PORTAL_URL}"):
                jobs.at[index, "msg_1hr_before"] = "Yes"
                updates_made = True
        if time_diff < timedelta(minutes=-30) and status in {"Selected", "Confirmed"} and not _value(job, "msg_late"):
            if send_whatsapp_msg(worker_phone, f"🚩 *Job Overdue*\nYou are over 30 minutes late for *{title}*. Please update the portal."):
                jobs.at[index, "msg_late"] = "Yes"
                updates_made = True

    if updates_made:
        try:
            _save_jobs(jobs_ws, jobs)
            print("Notification markers saved.")
        except gspread.exceptions.GSpreadException as exc:
            print(f"Failed to save notification markers: {exc}")
    else:
        print("No new notifications needed.")


# Backwards-compatible entry point for scheduled deployments using the old name.
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
