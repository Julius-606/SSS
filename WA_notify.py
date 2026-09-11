import os
import json
import gspread
import pandas as pd
from datetime import datetime, timedelta
import pytz
import requests
import time 

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass 

# 🎯 CONFIG
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing"
KISUMU_TZ = pytz.timezone('Africa/Nairobi') # East Africa Time (EAT)
ADMIN_CONTACT = "0799084376" # Admin Contact Variable for task cancellation notifications

def send_whatsapp_msg(phone, message):
    """
    Function to dispatch notifications via WhatsApp API. 
    Using Meta's Official Cloud API.
    """
    if not phone or phone.lower() == 'nan':
        print("No valid phone number provided.")
        return False

    print(f"Attempting to notify {phone}: {message[:30]}...")
    
    # --- META WHATSAPP API LOGIC ---
    ACCESS_TOKEN = os.getenv("WA_TOKEN")
    PHONE_ID = os.getenv("WA_PHONE_ID")
    
    if not ACCESS_TOKEN or not PHONE_ID:
        print("API error: WA_TOKEN or WA_PHONE_ID is missing from the environment. Notification service cannot proceed.")
        return False

    url = f"https://graph.facebook.com/v17.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"Meta API error (status {response.status_code}): {response.text}")
            return False
            
        print("Message delivered successfully.")
        return True
    
    except Exception as e:
        print(f"Notification request failed: {e}")
        return False

def task_scan():
    """ Main routine to scan the SSS Database for notification triggers. """
    print("Scanning the SSS database for notification triggers...")
    
    creds_json = os.getenv("GCP_SERVICE_ACCOUNT")
    if not creds_json:
        print("System error: Google Cloud credentials were not found. Review the configured secrets.")
        return

    try:
        creds_json = creds_json.strip().strip("'").strip('"')
        
        if creds_json.endswith('.json') and os.path.exists(creds_json):
            print("Loading credentials from the local JSON file...")
            client = gspread.service_account(filename=creds_json)
        else:
            print("Parsing service account credentials...")
            creds_dict = json.loads(creds_json)
            client = gspread.service_account_from_dict(creds_dict)
            
        workbook = client.open_by_url(SHEET_URL)
        
        tasks_ws = workbook.worksheet("Tasks")
        emps_ws = workbook.worksheet("Employees")
        
        tasks_df = pd.DataFrame(tasks_ws.get_all_records())
        emps_df = pd.DataFrame(emps_ws.get_all_records())
    except Exception as e:
        print(f"System failure: unable to load Google Sheets. Error: {e}")
        return
    
    if tasks_df.empty:
        print("No active assignments found. Notification scan complete.")
        return

    tasks_df['employee_Id'] = tasks_df['employee_Id'].astype(str)
    emps_df['id'] = emps_df['id'].astype(str)
    emps_df['phone'] = emps_df['phone'].astype(str)

    now = datetime.now(KISUMU_TZ)
    print(f"Current Kisumu time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    updates_made = False

    for index, row in tasks_df.iterrows():
        status = row.get('status', '')
        
        # We also need to scan 'Completed' for the new QC Admin approval alert!
        if status not in ['Pending', 'Confirmed', 'In Progress', 'Completed', 'Cancelled']:
            continue

        emp_id = row.get('employee_Id')
        task_title = row.get('title')
        due_str = row.get('due_date')
        
        emp_match = emps_df[emps_df['id'] == emp_id]
        if emp_match.empty:
            continue
            
        emp_phone = emp_match.iloc[0].get('phone', '')
        emp_name = emp_match.iloc[0].get('name', 'Employee')

        # Notify the administrator about a cancelled task with a reason.
        if status == 'Cancelled' and row.get('cancel_reason') and not row.get('msg_admin_cancelled'):
            msg = f"*Assignment Cancellation Alert*\nEmployee: {emp_name}\nAssignment: {task_title}\nReason provided: {row.get('cancel_reason')}\n\nIf reassignment was possible, the system has created a new pending assignment for another eligible employee."
            if send_whatsapp_msg(ADMIN_CONTACT, msg):
                tasks_df.at[index, 'msg_admin_cancelled'] = 'Yes'
                updates_made = True
            continue # We don't need to process reminder alerts for cancelled tasks

        # Notify the administrator that quality control review is required.
        if status == 'Completed' and not row.get('msg_admin_completed'):
            msg = f"*Assignment Completed*\nEmployee: {emp_name}\nAssignment: {task_title}\nThe employee has marked this assignment as complete.\n\nPlease sign in to the SSS Administration Portal and open Quality Control to review the assignment, record a rating, and approve payment.\nhttps://3wfppg3ykc6sulf5tclxdp.streamlit.app/ "
            if send_whatsapp_msg(ADMIN_CONTACT, msg):
                tasks_df.at[index, 'msg_admin_completed'] = 'Yes'
                updates_made = True
            continue

        # For tasks that are still active
        if status in ['Pending', 'Confirmed', 'In Progress']:
            # Notify the employee that an assignment has been allocated.
            if not row.get('msg_allocated'):
                msg = f"*New Assignment*\nDear {emp_name}, you have been assigned: *{task_title}*.\nDeadline: {due_str}.\nPlease sign in to the portal to review and confirm your availability.\nhttps://3wfppg3ykc6sulf5tclxdp.streamlit.app/\nAdministrator contact: {ADMIN_CONTACT}"
                if send_whatsapp_msg(emp_phone, msg):
                    tasks_df.at[index, 'msg_allocated'] = 'Yes'
                    updates_made = True

            # Parse Due Date
            if due_str:
                try:
                    due_date = KISUMU_TZ.localize(datetime.strptime(due_str, "%Y-%m-%d %H:%M:%S"))
                    time_diff = due_date - now
                    
                    # Send the scheduled reminder for the following day.
                    if timedelta(hours=12) < time_diff <= timedelta(hours=24) and not row.get('msg_night_before'):
                        msg = f"*Assignment Reminder*\nDear {emp_name}, your assignment *{task_title}* is scheduled for tomorrow at {due_date.strftime('%I:%M %p')}.\nhttps://3wfppg3ykc6sulf5tclxdp.streamlit.app/\nAdministrator contact: {ADMIN_CONTACT}"
                        if send_whatsapp_msg(emp_phone, msg):
                            tasks_df.at[index, 'msg_night_before'] = 'Yes'
                            updates_made = True

                    # Send the one-hour reminder.
                    if timedelta(minutes=0) < time_diff <= timedelta(hours=1) and not row.get('msg_1hr_before'):
                        msg = f"*One-Hour Assignment Reminder*\nDear {emp_name}, your assignment *{task_title}* is scheduled to begin in less than one hour. Please ensure you are ready to begin.\nhttps://3wfppg3ykc6sulf5tclxdp.streamlit.app/\nAdministrator contact: {ADMIN_CONTACT}"
                        if send_whatsapp_msg(emp_phone, msg):
                            tasks_df.at[index, 'msg_1hr_before'] = 'Yes'
                            updates_made = True

                    # Notify the employee when an assignment is overdue.
                    if time_diff < timedelta(minutes=-30) and status in ['Pending', 'Confirmed'] and not row.get('msg_late'):
                        msg = f"*Assignment Overdue*\nDear {emp_name}, assignment *{task_title}* is more than 30 minutes overdue. Please sign in and select 'Start Assignment' immediately; otherwise, the assignment may be reassigned.\nhttps://3wfppg3ykc6sulf5tclxdp.streamlit.app/\nAdministrator contact: {ADMIN_CONTACT}"
                        if send_whatsapp_msg(emp_phone, msg):
                            tasks_df.at[index, 'msg_late'] = 'Yes'
                            updates_made = True

                except ValueError:
                    pass 

    if updates_made:
        print("Updating Google Sheets with notification records...")
        tasks_ws.clear()
        tasks_ws.update([tasks_df.columns.values.tolist()] + tasks_df.fillna('').values.tolist())
        print("Notification records saved successfully. Synchronization complete.")
    else:
        print("No new notifications are required. System on standby.")

def main():
    is_github_actions = os.getenv("GITHUB_ACTIONS") == "true"

    if is_github_actions:
        print("Cloud environment detected. Running scheduled scan.")
        task_scan()
    else:
        print("Local environment detected. Starting the background notification service.")
        while True:
            try:
                task_scan()
                print("Scan complete. Pausing for 15 minutes before the next synchronization.")
                time.sleep(900) 
            except Exception as e:
                print(f"Notification service error: {e}")
                print("Retrying after a five-minute delay.")
                time.sleep(300) 

if __name__ == "__main__":
    main()
