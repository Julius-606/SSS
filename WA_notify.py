import os
import json
import gspread
import pandas as pd
from datetime import datetime, timedelta
import pytz
import requests

# 🎯 CONFIG
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing"
KISUMU_TZ = pytz.timezone('Africa/Nairobi') # East Africa Time (EAT)

def send_whatsapp_msg(phone, message):
    """
    This is where you plug in your WhatsApp API. 
    Using Meta's Official Cloud API as a placeholder.
    """
    if not phone or phone.lower() == 'nan':
        print("No phone number to send to.")
        return False

    print(f"📱 Sending to {phone}: {message}")
    
    # --- META WHATSAPP API LOGIC ---
    # ACCESS_TOKEN = os.getenv("WA_TOKEN")
    # PHONE_ID = os.getenv("WA_PHONE_ID")
    # url = f"https://graph.facebook.com/v17.0/{PHONE_ID}/messages"
    # headers = {
    #     "Authorization": f"Bearer {ACCESS_TOKEN}",
    #     "Content-Type": "application/json"
    # }
    # payload = {
    #     "messaging_product": "whatsapp",
    #     "to": phone,
    #     "type": "text",
    #     "text": {"body": message}
    # }
    # response = requests.post(url, headers=headers, json=payload)
    # return response.status_code == 200
    
    # Returning true for simulation so we know the logic holds up!
    return True

def main():
    print("🤖 Waking up... Initializing SSS Notification Bot (Checking the Sheet)")
    
    # 1. Connect to Sheets using env vars set by GitHub Actions
    creds_json = os.getenv("GCP_SERVICE_ACCOUNT")
    if not creds_json:
        print("🚨 System Error! No GCP credentials found.")
        return

    creds_dict = json.loads(creds_json)
    client = gspread.service_account_from_dict(creds_dict)
    workbook = client.open_by_url(SHEET_URL)
    
    tasks_ws = workbook.worksheet("Tasks")
    emps_ws = workbook.worksheet("Employees")
    
    tasks_df = pd.DataFrame(tasks_ws.get_all_records())
    emps_df = pd.DataFrame(emps_ws.get_all_records())
    
    if tasks_df.empty:
        print("No active tasks found. System idle.")
        return

    # Force to strings so pandas doesn't mess up the IDs
    tasks_df['employee_Id'] = tasks_df['employee_Id'].astype(str)
    emps_df['id'] = emps_df['id'].astype(str)
    emps_df['phone'] = emps_df['phone'].astype(str)

    # 2. Get current Kisumu Time
    now = datetime.now(KISUMU_TZ)
    print(f"🕒 Current Kisumu Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    updates_made = False

    for index, row in tasks_df.iterrows():
        status = row.get('status', '')
        
        # We only care about stuff that hasn't been completed/cancelled
        if status not in ['Pending', 'In Progress']:
            continue

        emp_id = row.get('employee_Id')
        task_title = row.get('title')
        due_str = row.get('due_date')
        
        # Match employee to get their phone number
        emp_match = emps_df[emps_df['id'] == emp_id]
        if emp_match.empty:
            continue
            
        emp_phone = emp_match.iloc[0].get('phone', '')
        emp_name = emp_match.iloc[0].get('name', 'Employee')

        # 🚀 ALERT 1: Task Allocated
        if not row.get('msg_allocated'):
            msg = f"🚨 *New Task Assigned!*\nHello {emp_name}, you have been assigned a new task: *{task_title}*.\nDue: {due_str}.\nPlease log into the portal to review and accept the task. 💼"
            if send_whatsapp_msg(emp_phone, msg):
                tasks_df.at[index, 'msg_allocated'] = 'Yes'
                updates_made = True

        # Parse Due Date
        if due_str:
            try:
                due_date = KISUMU_TZ.localize(datetime.strptime(due_str, "%Y-%m-%d %H:%M:%S"))
                time_diff = due_date - now
                
                # 🚀 ALERT 2: Night Before Reminder (If it's due tomorrow and time to due is between 12-24 hrs)
                if timedelta(hours=12) < time_diff <= timedelta(hours=24) and not row.get('msg_night_before'):
                    msg = f"🌙 *Task Reminder*\nHello {emp_name}, a reminder that your task *{task_title}* is scheduled for tomorrow at {due_date.strftime('%I:%M %p')}. Have a good night! 🌟"
                    if send_whatsapp_msg(emp_phone, msg):
                        tasks_df.at[index, 'msg_night_before'] = 'Yes'
                        updates_made = True

                # 🚀 ALERT 3: Sometime Before (1 hour before gig)
                if timedelta(minutes=0) < time_diff <= timedelta(hours=1) and not row.get('msg_1hr_before'):
                    msg = f"⏳ *1 Hour Reminder!*\nHello {emp_name}, your task *{task_title}* is due to start in less than an hour. Please ensure you are ready to begin. 🚀"
                    if send_whatsapp_msg(emp_phone, msg):
                        tasks_df.at[index, 'msg_1hr_before'] = 'Yes'
                        updates_made = True

                # 🚀 ALERT 4: Late Alert (30 mins late AND still marked "Pending")
                if time_diff < timedelta(minutes=-30) and status == 'Pending' and not row.get('msg_late'):
                    msg = f"🚩 *Task Overdue Alert!* 🚩\nHello {emp_name}, you are over 30 minutes late to start *{task_title}*. Please log in and click 'Start Task' immediately, or the task may be reassigned or cancelled. 🛑"
                    if send_whatsapp_msg(emp_phone, msg):
                        tasks_df.at[index, 'msg_late'] = 'Yes'
                        updates_made = True

            except ValueError:
                pass # Date wasn't formatted correctly, ignore

    # 3. Update Google Sheets if we sent messages
    if updates_made:
        print("💾 Updating Google Sheets with sent message flags...")
        tasks_ws.clear()
        tasks_ws.update([tasks_df.columns.values.tolist()] + tasks_df.fillna('').values.tolist())
        print("✅ Data saved. Bot is going back to sleep.")
    else:
        print("💤 No new alerts needed. Bot going to sleep.")

if __name__ == "__main__":
    main()
