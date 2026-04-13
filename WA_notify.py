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

    print(f"📱 Attempting to notify {phone}: {message[:30]}...")
    
    # --- META WHATSAPP API LOGIC ---
    ACCESS_TOKEN = os.getenv("WA_TOKEN")
    PHONE_ID = os.getenv("WA_PHONE_ID")
    
    if not ACCESS_TOKEN or not PHONE_ID:
        print("❌ API ERROR: Missing WA_TOKEN or WA_PHONE_ID in your environment variables. Service cannot proceed.")
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
            print(f"❌ META API ERROR (Status {response.status_code}): {response.text}")
            return False
            
        print("✅ Message successfully delivered!")
        return True
    
    except Exception as e:
        print(f"❌ FATAL ERROR executing request: {e}")
        return False

def task_scan():
    """ Main routine to scan the SSS Database for notification triggers. """
    print("🤖 Waking up... Scanning the SSS Database...")
    
    creds_json = os.getenv("GCP_SERVICE_ACCOUNT")
    if not creds_json:
        print("🚨 System Error! No GCP credentials found. Check your secrets.")
        return

    try:
        creds_json = creds_json.strip().strip("'").strip('"')
        
        if creds_json.endswith('.json') and os.path.exists(creds_json):
            print("📂 Loading credentials directly from local JSON file...")
            client = gspread.service_account(filename=creds_json)
        else:
            print("🌐 Parsing raw JSON credentials...")
            creds_dict = json.loads(creds_json)
            client = gspread.service_account_from_dict(creds_dict)
            
        workbook = client.open_by_url(SHEET_URL)
        
        tasks_ws = workbook.worksheet("Tasks")
        emps_ws = workbook.worksheet("Employees")
        
        tasks_df = pd.DataFrame(tasks_ws.get_all_records())
        emps_df = pd.DataFrame(emps_ws.get_all_records())
    except Exception as e:
        print(f"🚨 System Failure! Failed to load Google Sheets. Error: {e}")
        return
    
    if tasks_df.empty:
        print("No active tasks found. System idle. 😴")
        return

    tasks_df['employee_Id'] = tasks_df['employee_Id'].astype(str)
    emps_df['id'] = emps_df['id'].astype(str)
    emps_df['phone'] = emps_df['phone'].astype(str)

    now = datetime.now(KISUMU_TZ)
    print(f"🕒 Current Kisumu Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

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

        # 🚀 ALERT ADMIN: Cancelled Task with Reason
        if status == 'Cancelled' and row.get('cancel_reason') and not row.get('msg_admin_cancelled'):
            msg = f"🚨 *Task Cancellation Alert* 🚨\nWorker: {emp_name}\nTask: {task_title}\nReason Provided: {row.get('cancel_reason')}\n\n🤖 Note: If auto-reassign was possible, the algorithm has already created a new Pending task for another eligible worker!"
            if send_whatsapp_msg(ADMIN_CONTACT, msg):
                tasks_df.at[index, 'msg_admin_cancelled'] = 'Yes'
                updates_made = True
            continue # We don't need to process reminder alerts for cancelled tasks

        # 🚀 ALERT ADMIN: Task Completed! QC Check Required
        if status == 'Completed' and not row.get('msg_admin_completed'):
            msg = f"✨ *Task Completed Alert* ✨\nWorker: {emp_name}\nTask: {task_title}\nBro just cooked and marked this done! 🍳\n\nPlease log into the SSS Admin Portal -> Quality Control to review, drop a star rating ⭐️, and float their funds to Payroll.\nhttps://3wfppg3ykc6sulf5tclxdp.streamlit.app/ "
            if send_whatsapp_msg(ADMIN_CONTACT, msg):
                tasks_df.at[index, 'msg_admin_completed'] = 'Yes'
                updates_made = True
            continue

        # For tasks that are still active
        if status in ['Pending', 'Confirmed', 'In Progress']:
            # 🚀 ALERT 1: Task Allocated
            if not row.get('msg_allocated'):
                msg = f"🚨 *New Task Assigned!*\nHello {emp_name}, you have been assigned a new task: *{task_title}*.\nDue: {due_str}.\nPlease log into the portal to review and confirm your availability.\n https://3wfppg3ykc6sulf5tclxdp.streamlit.app/ 💼\n📞 Admin contact: {ADMIN_CONTACT}"
                if send_whatsapp_msg(emp_phone, msg):
                    tasks_df.at[index, 'msg_allocated'] = 'Yes'
                    updates_made = True

            # Parse Due Date
            if due_str:
                try:
                    due_date = KISUMU_TZ.localize(datetime.strptime(due_str, "%Y-%m-%d %H:%M:%S"))
                    time_diff = due_date - now
                    
                    # 🚀 ALERT 2: Night Before Reminder
                    if timedelta(hours=12) < time_diff <= timedelta(hours=24) and not row.get('msg_night_before'):
                        msg = f"🌙 *Task Reminder*\nHello {emp_name}, a reminder that your task *{task_title}* is scheduled for tomorrow at {due_date.strftime('%I:%M %p')}. \n https://3wfppg3ykc6sulf5tclxdp.streamlit.app/ Have a good night! 🌟\n📞 Admin contact: {ADMIN_CONTACT}"
                        if send_whatsapp_msg(emp_phone, msg):
                            tasks_df.at[index, 'msg_night_before'] = 'Yes'
                            updates_made = True

                    # 🚀 ALERT 3: Sometime Before (1 hour before gig)
                    if timedelta(minutes=0) < time_diff <= timedelta(hours=1) and not row.get('msg_1hr_before'):
                        msg = f"⏳ *1 Hour Reminder!*\nHello {emp_name}, your task *{task_title}* is due to start in less than an hour. Please ensure you are ready to begin. \n https://3wfppg3ykc6sulf5tclxdp.streamlit.app/ 🚀\n📞 Admin contact: {ADMIN_CONTACT}"
                        if send_whatsapp_msg(emp_phone, msg):
                            tasks_df.at[index, 'msg_1hr_before'] = 'Yes'
                            updates_made = True

                    # 🚀 ALERT 4: Late Alert (30 mins late AND hasn't clocked in)
                    if time_diff < timedelta(minutes=-30) and status in ['Pending', 'Confirmed'] and not row.get('msg_late'):
                        msg = f"🚩 *Task Overdue Alert!* 🚩\nHello {emp_name}, you are over 30 minutes late to start *{task_title}*. Please log in and click 'Start Task' immediately, or the task may be reassigned. \n https://3wfppg3ykc6sulf5tclxdp.streamlit.app/ 🛑\n📞 Admin contact: {ADMIN_CONTACT}"
                        if send_whatsapp_msg(emp_phone, msg):
                            tasks_df.at[index, 'msg_late'] = 'Yes'
                            updates_made = True

                except ValueError:
                    pass 

    if updates_made:
        print("💾 Updating Google Sheets with sent message records...")
        tasks_ws.clear()
        tasks_ws.update([tasks_df.columns.values.tolist()] + tasks_df.fillna('').values.tolist())
        print("✅ Data saved. Sync complete. Main character energy maintained.")
    else:
        print("💤 No new alerts needed. System on standby.")

def main():
    is_github_actions = os.getenv("GITHUB_ACTIONS") == "true"

    if is_github_actions:
        print("☁️ Cloud Environment detected. Running scheduled scan. 📊")
        task_scan()
    else:
        print("💻 Local Environment detected. Initiating 24/7 background service... 🚀")
        while True:
            try:
                task_scan()
                print("⏳ Scan complete. Pausing for 15 minutes before the next sync... 🧊")
                time.sleep(900) 
            except Exception as e:
                print(f"🚨 MAJOR ERROR ENCOUNTERED: {e}")
                print("Cooling down for 5 minutes before retrying...")
                time.sleep(300) 

if __name__ == "__main__":
    main()
