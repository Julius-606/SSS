import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz 
import gspread
from google.oauth2.service_account import Credentials
import urllib.parse
import random

# --- CONFIG & SECRETS SETUP ---
st.set_page_config(page_title="SSS Portal OS", layout="wide", page_icon="✨", initial_sidebar_state="collapsed")

ADMIN_USER = "admin"
ADMIN_PASS = "admin@SSS"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing"
SUPPORT_NUMBER = "254799084376" 
KISUMU_TZ = pytz.timezone('Africa/Nairobi') # East Africa Time (EAT) 

# --- 🛑 CSS INJECTION ENGINE (DYNAMIC BACKGROUNDS) 🛑 ---
def inject_custom_bg(role):
    if role == 'admin':
        bg_css = """
        <style>
        .stApp { background: linear-gradient(135deg, #e0f2fe 0%, #ffffff 50%, #e5e7eb 100%); color: #1e293b; }
        h1, h2, h3, h4, p, span, div { color: #334155; }
        </style>
        """
    elif role == 'employee':
        bg_css = """
        <style>
        .stApp { background: linear-gradient(135deg, #ffffff 0%, #f0f9ff 50%, #f3f4f6 100%); color: #1e293b; }
        h1, h2, h3, h4, p, span, div { color: #334155; }
        </style>
        """
    else:
        bg_css = """
        <style>
        .stApp { background: radial-gradient(circle, #f8fafc 0%, #bae6fd 100%); color: #1e293b; }
        h1, h2, h3, h4, p, span, div { color: #0f172a; }
        </style>
        """
    st.markdown(bg_css, unsafe_allow_html=True)

# --- 🛑 1. GOOGLE SHEETS CONNECTION (CACHED) 🛑 ---
@st.cache_resource
def get_gspread_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error("🚨 Authentication Error: Failed to connect to database. Please check your credentials. (Did we hit stop-loss?)")
        st.stop()

# --- 🛑 2. MOUNT THE WORKSHEETS (CACHED) 🛑 ---
@st.cache_resource
def get_worksheets():
    client = get_gspread_client()
    try:
        workbook = client.open_by_url(SHEET_URL)
    except Exception as e:
        st.error(f"🚨 Failed to find the target database. Bro we are getting liquidated.\n\nError: {e}")
        st.stop()
        
    def get_or_create(title, headers):
        try:
            ws = workbook.worksheet(title)
            existing_headers = ws.row_values(1)
            missing = [h for h in headers if h not in existing_headers]
            if missing:
                ws.update(f"{gspread.utils.rowcol_to_a1(1, len(existing_headers)+1)}", [missing])
        except gspread.exceptions.WorksheetNotFound:
            ws = workbook.add_worksheet(title=title, rows="1000", cols="30")
            ws.append_row(headers)
        return ws

    # Added skills and points for the point system! 🚀
    emps_ws = get_or_create("Employees", ["id", "name", "username", "password", "phone", "skills", "points"])
    # Added Category, recurrence logic, rating, and new WA notify flag! 🔁
    tasks_ws = get_or_create("Tasks", ["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned", "due_date", "time_marked_done", "payout", "msg_allocated", "msg_night_before", "msg_1hr_before", "msg_late", "cancel_reason", "instructions", "msg_admin_cancelled", "category", "is_recurring", "recurrence_pattern", "rating", "msg_admin_completed"])
    settings_ws = get_or_create("Settings", ["setting_key", "setting_value"])
    # 🏦 THE SSS FINANCE DEPARTMENT SPREADSHEET 🏦
    acct_ws = get_or_create("Accounting", ["tx_id", "date", "type", "description", "amount", "status"])
    
    if not emps_ws.get_all_records():
        emps_ws.append_row(["emp1", "Wanjiku (Nanny Pro)", "wanjiku", "password123", "254700000000", "Babysitting, Cleaning", "0"])
        emps_ws.append_row(["emp2", "Ochieng (Deep Cleaner)", "ochieng", "password123", "254700000000", "Cleaning, Janitorial", "0"])
        
    return workbook, emps_ws, tasks_ws, settings_ws, acct_ws

workbook, emps_ws, tasks_ws, settings_ws, acct_ws = get_worksheets()

# --- 🛑 3. DATA PULL (CACHED FOR 30 SECONDS) 🛑 ---
@st.cache_data(ttl=30)
def fetch_portal_data():
    emps_df = pd.DataFrame(emps_ws.get_all_records())
    if not emps_df.empty:
        emps_df['id'] = emps_df['id'].astype(str)
        emps_df['username'] = emps_df['username'].astype(str)
        emps_df['password'] = emps_df['password'].astype(str)
        if 'phone' not in emps_df.columns: emps_df['phone'] = ""
        if 'skills' not in emps_df.columns: emps_df['skills'] = "General"
        if 'points' not in emps_df.columns: emps_df['points'] = 0
        emps_df['points'] = pd.to_numeric(emps_df['points'], errors='coerce').fillna(0)

    tasks_records = tasks_ws.get_all_records()
    if tasks_records:
        tasks_df = pd.DataFrame(tasks_records)
        tasks_df['hours'] = pd.to_numeric(tasks_df['hours'], errors='coerce')
        tasks_df['rate'] = pd.to_numeric(tasks_df['rate'], errors='coerce')
        if 'payout' not in tasks_df.columns: tasks_df['payout'] = tasks_df['hours'] * tasks_df['rate']
        
        # Ensure all our new Gen-Z automation columns exist so pandas doesn't panic
        for col in ["category", "is_recurring", "recurrence_pattern", "rating", "msg_admin_completed"]:
            if col not in tasks_df.columns: tasks_df[col] = ""
    else:
        tasks_df = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned", "due_date", "time_marked_done", "payout", "category", "is_recurring", "recurrence_pattern", "rating", "msg_admin_completed"])
        
    settings_df = pd.DataFrame(settings_ws.get_all_records())
    
    acct_records = acct_ws.get_all_records()
    acct_df = pd.DataFrame(acct_records) if acct_records else pd.DataFrame(columns=["tx_id", "date", "type", "description", "amount", "status"])
    
    return emps_df, tasks_df, settings_df, acct_df

emps_df, tasks_df, settings_df, acct_df = fetch_portal_data()

# --- 🛑 4. THE MONTHLY AUTO-ARCHIVE ENGINE 🛑 ---
# Restored logic: sweeps old tasks out of the active sheet every month
CURRENT_MONTH = datetime.now(KISUMU_TZ).strftime("%Y-%m")

if settings_df.empty or 'last_reset' not in settings_df['setting_key'].values:
    settings_ws.append_row(["last_reset", CURRENT_MONTH])
    fetch_portal_data.clear()
    last_reset = CURRENT_MONTH
else:
    last_reset = settings_df.loc[settings_df['setting_key'] == 'last_reset', 'setting_value'].iloc[0]

if last_reset != CURRENT_MONTH:
    try:
        if not tasks_df.empty:
            active_statuses = ['Pending', 'Confirmed', 'In Progress', 'Completed', 'Approved']
            keep_df = tasks_df[tasks_df['status'].isin(active_statuses)]
            archive_df = tasks_df[~tasks_df['status'].isin(active_statuses)]
            
            if not archive_df.empty:
                archive_title = f"Archive_{last_reset}"
                try:
                    archive_ws = workbook.worksheet(archive_title)
                except gspread.exceptions.WorksheetNotFound:
                    archive_ws = workbook.add_worksheet(title=archive_title, rows="1000", cols="30")
                    archive_ws.append_row(list(archive_df.columns))
                archive_ws.append_rows(archive_df.values.tolist())
            
            tasks_ws.clear()
            tasks_ws.update([keep_df.columns.values.tolist()] + keep_df.fillna('').values.tolist())
        
        cell = settings_ws.find("last_reset")
        settings_ws.update_cell(cell.row, cell.col + 1, CURRENT_MONTH)
        
        fetch_portal_data.clear()
        st.rerun()
        
    except Exception as e:
        st.error(f"Archive Engine Failed: {e}")

# --- WRITE FUNCTIONS ---
def save_tasks(df):
    tasks_ws.clear()
    tasks_ws.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
    fetch_portal_data.clear() 

def save_emps(df):
    emps_ws.clear()
    emps_ws.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
    fetch_portal_data.clear() 

def save_acct(df):
    acct_ws.clear()
    acct_ws.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
    fetch_portal_data.clear()

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

def get_employee_name(emp_id):
    if emps_df.empty: return "Unknown Employee"
    match = emps_df[emps_df['id'] == str(emp_id)]
    return match.iloc[0]['name'] if not match.empty else "Unknown Employee"

# --- 1. LOGIN SCREEN ---
if st.session_state.current_user is None:
    inject_custom_bg('login')
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>✨ SSS Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #4b5563; margin-bottom: 30px;'>Swift-hands Student Services. Authorized Personnel Only. NPCs will be bounced.</p>", unsafe_allow_html=True)
        
        with st.container(border=True):
            with st.form("login_form"):
                login_user = st.text_input("Username")
                login_pass = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log In 🚀", use_container_width=True, type="primary")
                
                if submitted:
                    if login_user == ADMIN_USER and login_pass == ADMIN_PASS:
                        st.session_state.current_user = {"role": "admin", "name": "Administrator"}
                        st.rerun()
                    else:
                        match = emps_df[(emps_df['username'] == login_user) & (emps_df['password'] == login_pass)]
                        if not match.empty:
                            emp = match.iloc[0]
                            st.session_state.current_user = {"role": "employee", "id": emp['id'], "name": emp['name'], "is_phased": False}
                            st.rerun()
                        else:
                            st.error("Invalid credentials. Access Denied. You thought you cooked? 🛑")

# --- 2. ADMIN DASHBOARD ---
elif st.session_state.current_user['role'] == 'admin':
    inject_custom_bg('admin')
    st.sidebar.title("🛡️ Admin Portal")
    
    # NAVIGATION MENU
    admin_view = st.sidebar.radio("Navigation", ["🏢 Operations Dashboard", "💼 Finance & Analytics", "✅ Quality Control (Approvals)"])
    
    st.sidebar.write("---")
    st.sidebar.subheader("👔 HR Department")
    with st.sidebar.expander("Add New Employee"):
        with st.form("add_employee_form"):
            new_emp_name = st.text_input("Full Name")
            new_emp_user = st.text_input("Username")
            new_emp_pass = st.text_input("Password", type="password")
            new_emp_phone = st.text_input("Phone Number", placeholder="e.g. 2547XXXXXXXX")
            # Added skills during onboarding
            new_emp_skills = st.multiselect("Worker Skills", ["Janitorial", "Deep Cleaning", "Babysitting", "Tutoring", "Event Staff", "Moving", "General"])
            if st.form_submit_button("Add Employee 🤝"):
                if new_emp_name and new_emp_user and new_emp_pass and new_emp_phone:
                    if not emps_df.empty and new_emp_user in emps_df['username'].values:
                        st.error("Username already taken! Please choose another one.")
                    else:
                        new_id = f"emp{int(time.time())}"
                        skills_str = ", ".join(new_emp_skills) if new_emp_skills else "General"
                        new_row = pd.DataFrame([{"id": new_id, "name": new_emp_name, "username": new_emp_user, "password": new_emp_pass, "phone": new_emp_phone, "skills": skills_str, "points": 0}])
                        
                        # Fix applied here: Clean local variable creation, zero global scopes ✅
                        updated_emps_df = pd.concat([emps_df, new_row], ignore_index=True)
                        save_emps(updated_emps_df)
                        
                        st.success("Employee added successfully! Big W.")
                        st.rerun()
                else:
                    st.error("Please fill out all fields.")

    st.sidebar.write("---")
    
    # 🧠 THE RESTORED PHASING LOGIC (View as Employee)
    st.sidebar.subheader("👁️ View As Employee")
    if not emps_df.empty:
        phase_target = st.sidebar.selectbox("Select Employee Dashboard:", emps_df['name'].tolist())
        if st.sidebar.button("View Dashboard 👁️", use_container_width=True):
            emp_row = emps_df[emps_df['name'] == phase_target].iloc[0]
            st.session_state.current_user = {
                "role": "employee", 
                "id": emp_row['id'], 
                "name": emp_row['name'],
                "is_phased": True
            }
            st.rerun()

    st.sidebar.write("---")
    if st.sidebar.button("Log Out 🚪", type="primary", use_container_width=True):
        st.session_state.current_user = None
        st.rerun()

    # ---------------------------------------------------------
    # VIEW 1: OPERATIONS DASHBOARD
    # ---------------------------------------------------------
    if admin_view == "🏢 Operations Dashboard":
        st.title("Operations Dashboard 🛠️")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("➕ Dispatch Task")
            with st.container(border=True):
                with st.form("dispatch_form"):
                    final_title = st.text_input("Task Title")
                    category = st.selectbox("Task Category", ["General", "Cleaning", "Janitorial", "Babysitting", "Moving", "Tutoring", "Event Staff"])
                    instructions = st.text_area("Instructions (Optional)")
                    
                    st.write("**⚙️ Automation Engine**")
                    allocation_mode = st.radio("Allocation Mode 🎲", ["Auto-Assign (Fair System 🤖)", "Manual Selection (Boomer way 👴)"])
                    
                    emp_options = dict(zip(emps_df['name'], emps_df['id'])) if not emps_df.empty else {}
                    
                    if allocation_mode == "Manual Selection (Boomer way 👴)":
                        selected_squad_names = st.multiselect("👥 Select Employees", list(emp_options.keys()))
                        workers_needed = len(selected_squad_names)
                    else:
                        workers_needed = st.number_input("How many workers needed? 🔢", min_value=1, step=1, value=1)
                        st.caption("System will auto-pick based on category matching & least active tasks to keep it fair. No cap.")
                        
                    st.write("**🔁 Repetitive Task Logic**")
                    is_recurring = st.checkbox("Is this a recurring task? 🔁")
                    recurrence_pattern = ""
                    if is_recurring:
                        recurrence_pattern = st.selectbox("Recurrence Pattern", ["Daily", "Weekly", "Monthly"])
                        st.caption("When approved, the system will auto-generate the next one. Compound interest baby! 📈")
                    
                    h_col, r_col = st.columns(2)
                    hours = h_col.number_input("Hours / Person", min_value=0.5, step=0.5, value=1.0)
                    rate = r_col.number_input("Worker Pay Rate / Hr (Ksh)", min_value=0.0, step=10.0, value=150.0)
                    
                    d_col, t_col = st.columns(2)
                    due_date = d_col.date_input("Due Date")
                    due_time = t_col.time_input("Due Time")
                    
                    submitted = st.form_submit_button("🚀 Deploy Task", type="primary")
                    
                    if submitted:
                        if final_title == "":
                            st.error("Bruh, you need a task title.")
                        else:
                            exact_time_str = datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S")
                            final_due = f"{due_date} {due_time}"
                            payout_val = hours * rate
                            
                            final_assignees = []
                            if allocation_mode == "Manual Selection (Boomer way 👴)":
                                if not selected_squad_names:
                                    st.error("⚠️ Please select at least one employee.")
                                else:
                                    final_assignees = [emp_options[name] for name in selected_squad_names]
                            else:
                                # THE AUTOMATION ENGINE 🧠
                                # 1. Find employees matching the category (case insensitive)
                                eligible = emps_df[emps_df['skills'].str.contains(category, case=False, na=False)]
                                if eligible.empty:
                                    st.warning(f"No one has the '{category}' skill! Falling back to the general pool.")
                                    eligible = emps_df.copy()
                                
                                # 2. Sort by least active tasks to be fair
                                if not tasks_df.empty:
                                    active_counts = tasks_df[tasks_df['status'].isin(['Pending', 'Confirmed', 'In Progress'])].groupby('employee_Id').size()
                                    eligible['active_tasks'] = eligible['id'].map(active_counts).fillna(0)
                                else:
                                    eligible['active_tasks'] = 0
                                    
                                # Sort: fewest tasks first. If tied, pick highest points (reward the GOATs)
                                best_emps = eligible.sort_values(by=['active_tasks', 'points'], ascending=[True, False]).head(workers_needed)
                                final_assignees = best_emps['id'].tolist()
                                
                                if len(final_assignees) < workers_needed:
                                    st.warning("Not enough workers available! Assigned to the ones we could find.")

                            if final_assignees:
                                new_records = []
                                for emp_id in final_assignees:
                                    new_records.append({
                                        "id": int(time.time() * 1000) + hash(emp_id) % 1000,
                                        "title": final_title,
                                        "employee_Id": emp_id,
                                        "hours": hours,
                                        "rate": rate,
                                        "status": "Pending",
                                        "date_assigned": exact_time_str,
                                        "due_date": final_due,
                                        "time_marked_done": "", 
                                        "payout": payout_val,
                                        "msg_allocated": "", "msg_night_before": "", "msg_1hr_before": "", "msg_late": "",
                                        "cancel_reason": "", "instructions": instructions, "msg_admin_cancelled": "",
                                        "category": category, "is_recurring": "Yes" if is_recurring else "No", 
                                        "recurrence_pattern": recurrence_pattern, "rating": "", "msg_admin_completed": ""
                                    })
                                
                                new_df = pd.DataFrame(new_records)
                                
                                # Fix applied here: Clean local variable creation, zero global scopes ✅
                                updated_tasks_df = pd.concat([tasks_df, new_df], ignore_index=True)
                                save_tasks(updated_tasks_df)
                                
                                st.success("Tasks dispatched successfully! The algorithm cooked. 🧠🔥")
                                st.rerun()

        with col2:
            st.subheader("⚡ Active Field Operations")
            # Notice we leave 'Completed' out of active field, as it moves to QC Approval now. 
            active_tasks = tasks_df[tasks_df['status'].isin(['Pending', 'Confirmed', 'In Progress'])] if not tasks_df.empty else pd.DataFrame()
                
            if active_tasks.empty:
                st.info("No active operations currently. Everyone is chilling.")
            else:
                for i, task in active_tasks.iloc[::-1].iterrows():
                    if pd.isna(task.get('title')): continue 
                    with st.container(border=True):
                        t_col1, t_col2 = st.columns([3, 1])
                        with t_col1:
                            st.markdown(f"**{task['title']}** ({task.get('category', 'General')})")
                            emp_name = get_employee_name(task['employee_Id']).split(' ')[0]
                            recur_badge = "🔁" if task.get('is_recurring') == "Yes" else ""
                            st.caption(f"👤 {emp_name} | 🎯 Due: {task.get('due_date', 'N/A')} {recur_badge}")
                        with t_col2:
                            if task['status'] == 'Pending': st.warning("Pending ⏳")
                            elif task['status'] == 'Confirmed': st.success("Worker Confirmed 🤝")
                            elif task['status'] == 'In Progress': st.info("In Progress 🏃")

        st.write("---")
        # 🧠 THE RESTORED TASK LEDGER (Table Log)
        st.subheader("🗄️ Master Task Ledger (Current Month)")
        
        if not tasks_df.empty:
            display_df = tasks_df.copy()
            display_df['Employee Name'] = display_df['employee_Id'].apply(get_employee_name)
            display_df['Total Payout (Ksh)'] = display_df.get('payout', display_df['hours'] * display_df['rate'])
            display_df = display_df[['id', 'date_assigned', 'due_date', 'time_marked_done', 'title', 'category', 'Employee Name', 'hours', 'rate', 'Total Payout (Ksh)', 'status']]
            st.dataframe(display_df.sort_values(by="id", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Ledger is completely empty.")
            
        if st.button("🔄 Force Refresh Ledger", type="secondary"):
            fetch_portal_data.clear()
            st.rerun()

    # ---------------------------------------------------------
    # VIEW 1.5: QUALITY CONTROL (APPROVALS & RATING)
    # ---------------------------------------------------------
    elif admin_view == "✅ Quality Control (Approvals)":
        st.title("Task Approvals & QC 🔎")
        st.caption("Workers marked these as done. Your job is to verify, drop a star rating, and float the money to their payroll account. No cap, keep the standards high.")
        
        if tasks_df.empty:
            st.info("Database is empty. No setups forming right now.")
        else:
            completed_tasks = tasks_df[tasks_df['status'] == 'Completed']
            if completed_tasks.empty:
                st.info("Zero tasks waiting for approval. Go touch some grass. 🌱")
            else:
                for i, t in completed_tasks.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        emp_name = get_employee_name(t['employee_Id'])
                        with c1:
                            st.markdown(f"### {t['title']}")
                            st.caption(f"**Worker:** {emp_name} | **Category:** {t.get('category', 'General')} | **Marked Done:** {t.get('time_marked_done', 'N/A')}")
                            if t.get('is_recurring') == 'Yes':
                                st.info(f"🔁 This is a recurring task ({t.get('recurrence_pattern')}). Approving this will auto-generate the next session!")
                            
                            rating = st.slider(f"Rate {emp_name}'s performance ⭐️", 1, 5, 5, key=f"rate_{t['id']}")
                            st.caption(f"*{rating} Stars = +{rating * 10} SSS Points for {emp_name}*")
                            
                        with c2:
                            st.markdown("<br><br>", unsafe_allow_html=True)
                            if st.button("Approve & Award Points ✅", key=f"apprv_{t['id']}", type="primary", use_container_width=True):
                                # 1. Update Status & Rating
                                tasks_df.loc[tasks_df['id'] == t['id'], 'status'] = 'Approved'
                                tasks_df.loc[tasks_df['id'] == t['id'], 'rating'] = rating
                                
                                # 2. Add Points to Worker
                                emp_idx = emps_df.index[emps_df['id'] == str(t['employee_Id'])].tolist()[0]
                                curr_pts = int(emps_df.at[emp_idx, 'points']) if pd.notna(emps_df.at[emp_idx, 'points']) else 0
                                emps_df.at[emp_idx, 'points'] = curr_pts + (rating * 10)
                                save_emps(emps_df)
                                
                                # 3. Auto-generate next instance if recurring
                                if t.get('is_recurring') == 'Yes':
                                    pattern = t.get('recurrence_pattern', 'Weekly')
                                    old_due = t.get('due_date')
                                    try:
                                        old_due_dt = datetime.strptime(old_due, "%Y-%m-%d %H:%M:%S")
                                        if pattern == 'Daily': next_due = old_due_dt + timedelta(days=1)
                                        elif pattern == 'Weekly': next_due = old_due_dt + timedelta(days=7)
                                        elif pattern == 'Monthly': next_due = old_due_dt + timedelta(days=30)
                                        else: next_due = old_due_dt + timedelta(days=7)
                                        
                                        next_task = t.copy()
                                        next_task['id'] = int(time.time() * 1000)
                                        next_task['due_date'] = next_due.strftime("%Y-%m-%d %H:%M:%S")
                                        next_task['date_assigned'] = datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S")
                                        next_task['status'] = 'Pending'
                                        # Reset notification flags for the new baby task
                                        for key in ['msg_allocated', 'msg_night_before', 'msg_1hr_before', 'msg_late', 'msg_admin_cancelled', 'msg_admin_completed', 'time_marked_done', 'rating']:
                                            next_task[key] = ""
                                        
                                        # Fix applied here: Clean local variable creation, zero global scopes ✅
                                        updated_tasks_df = pd.concat([tasks_df, pd.DataFrame([next_task])], ignore_index=True)
                                        save_tasks(updated_tasks_df)

                                        st.toast("🔁 Recurring task generated for the future!")
                                    except Exception as e:
                                        save_tasks(tasks_df) # Save anyway if recurrence fails
                                        st.error(f"Failed to calculate next recurring date: {e}")
                                else:
                                    save_tasks(tasks_df)

                                st.success(f"Task Approved! Funds have been floated to Payroll, and {emp_name} got their points! W Admin. 👑")
                                time.sleep(1)
                                st.rerun()

    # ---------------------------------------------------------
    # VIEW 2: FINANCE & ANALYTICS (THE NEW ACCOUNTING HUB)
    # ---------------------------------------------------------
    elif admin_view == "💼 Finance & Analytics":
        st.title("Corporate Finance & Payroll 📈")
        st.caption("We are extremely Bullish today. Hitting those TP (Take-Profit) levels! 💸")
        
        # Calculate Macro Metrics
        total_income = acct_df[acct_df['type'] == 'Income']['amount'].sum() if not acct_df.empty else 0.0
        total_payroll_cleared = acct_df[acct_df['type'] == 'Expense']['amount'].sum() if not acct_df.empty else 0.0
        gross_profit = total_income - total_payroll_cleared
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Gross Tender Income (Ksh)", f"Ksh {total_income:,.2f}")
        m2.metric("Cleared Payroll (Ksh)", f"Ksh {total_payroll_cleared:,.2f}")
        m3.metric("SSS Gross Profit (Ksh)", f"Ksh {gross_profit:,.2f}", delta="Company Retained Margin" if gross_profit > 0 else None)
        
        st.write("---")

        # 🧮 TENDER QUOTATION ENGINE
        st.subheader("🧮 Tender Quotation Engine")
        st.caption("Calculate exactly what to charge the campus administration to secure your profit margin.")
        
        with st.container(border=True):
            q_col1, q_col2, q_col3 = st.columns(3)
            with q_col1:
                est_workers = st.number_input("Number of Workers Needed", min_value=1, value=2)
                est_hours = st.number_input("Hours per Worker", min_value=0.5, step=0.5, value=4.0)
            with q_col2:
                worker_rate = st.number_input("Worker Pay Rate (Ksh/hr)", min_value=50.0, step=10.0, value=150.0)
                target_margin = st.slider("Desired SSS Markup (%)", min_value=10, max_value=100, value=40, step=5)
            
            total_worker_cost = est_workers * est_hours * worker_rate
            markup_multiplier = 1 + (target_margin / 100.0)
            recommended_total_bill = total_worker_cost * markup_multiplier
            projected_profit = recommended_total_bill - total_worker_cost
            recommended_hourly_bill = recommended_total_bill / (est_workers * est_hours) if (est_workers * est_hours) > 0 else 0

            with q_col3:
                st.info(f"**Total Worker Cost:** Ksh {total_worker_cost:,.2f}")
                st.success(f"**Recommended Bill to Admin:** Ksh {recommended_total_bill:,.2f}")
                st.metric("Projected SSS Profit", f"Ksh {projected_profit:,.2f}")
                st.caption(f"Suggested Bill Rate: Ksh {recommended_hourly_bill:,.2f} / hr per worker")

        st.write("---")
        
        colA, colB = st.columns([1, 1])
        
        with colA:
            st.subheader("📥 Log Corporate Income")
            st.caption("Record payments received from campus administration or clients here.")
            with st.container(border=True):
                with st.form("income_form"):
                    inc_desc = st.text_input("Tender / Client Name", placeholder="e.g., Campus Library Cleaning Tender - March")
                    inc_amount = st.number_input("Amount Received (Ksh)", min_value=0.0, step=500.0)
                    
                    if st.form_submit_button("Log Income 💰", type="primary"):
                        if inc_desc and inc_amount > 0:
                            new_tx = pd.DataFrame([{
                                "tx_id": f"TX-INC-{int(time.time())}",
                                "date": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                                "type": "Income",
                                "description": inc_desc,
                                "amount": inc_amount,
                                "status": "Cleared"
                            }])
                            
                            # Fix applied here: Clean local variable creation, zero global scopes ✅
                            updated_acct_df = pd.concat([acct_df, new_tx], ignore_index=True)
                            save_acct(updated_acct_df)
                            
                            st.success("Tender income logged to the general ledger! Green candles everywhere 🟢")
                            st.rerun()
                        else:
                            st.error("Please provide a valid description and amount.")

        with colB:
            st.subheader("🧾 SSS Payroll Generator")
            # Changed logic: Now looking for 'Approved' tasks instead of just 'Completed'
            st.caption("Tasks marked as 'Approved' by Admin are aggregated here automatically.")
            
            unpaid_tasks = tasks_df[tasks_df['status'] == 'Approved'].copy() if not tasks_df.empty else pd.DataFrame()
            
            if unpaid_tasks.empty:
                st.info("No outstanding payroll liabilities. All workers are paid up! ✅ (Or tasks are still waiting in QC Approval)")
            else:
                unpaid_tasks['payout'] = pd.to_numeric(unpaid_tasks['payout'], errors='coerce')
                payroll_summary = unpaid_tasks.groupby('employee_Id')['payout'].sum().reset_index()
                
                payroll_report = payroll_summary.merge(emps_df[['id', 'name', 'phone']], left_on='employee_Id', right_on='id')
                payroll_report = payroll_report[['name', 'payout']]
                payroll_report.columns = ['Worker Name', 'Owed (Ksh)']
                
                total_liability = payroll_report['Owed (Ksh)'].sum()
                st.metric("Pending Payroll Liability", f"Ksh {total_liability:,.2f}")
                st.dataframe(payroll_report, use_container_width=True, hide_index=True)
                
                if st.button("Disburse Payroll & Update Ledger 💸", type="primary", use_container_width=True):
                    with st.spinner("Processing payroll across the organization... Dropping the bag 💰"):
                        # 1. Update tasks to 'Paid'
                        tasks_df.loc[tasks_df['status'] == 'Approved', 'status'] = 'Paid'
                        save_tasks(tasks_df)
                        
                        # 2. Log single bulk expense to Accounting
                        new_tx = pd.DataFrame([{
                            "tx_id": f"TX-PAY-{int(time.time())}",
                            "date": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                            "type": "Expense",
                            "description": "Bulk Worker Payroll Disbursement",
                            "amount": total_liability,
                            "status": "Cleared"
                        }])
                        
                        updated_acct_df = pd.concat([acct_df, new_tx], ignore_index=True)
                        save_acct(updated_acct_df)
                        
                    st.success("Payroll fully disbursed and recorded in the ledger! W Business.")
                    st.rerun()

        st.write("---")
        st.subheader("📚 General Accounting Ledger")
        if not acct_df.empty:
            display_acct = acct_df.copy()
            st.dataframe(display_acct.sort_values(by="date", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("The ledger is completely clean.")

# --- 3. EMPLOYEE DASHBOARD ---
elif st.session_state.current_user['role'] == 'employee':
    inject_custom_bg('employee')
    user_id = str(st.session_state.current_user['id'])
    user_name = st.session_state.current_user['name']
    is_phased = st.session_state.current_user.get('is_phased', False)
    
    # Grab the employee's current data
    my_emp_row = emps_df[emps_df['id'] == user_id].iloc[0] if not emps_df.empty else None
    my_points = my_emp_row['points'] if my_emp_row is not None else 0
    my_skills = my_emp_row['skills'].split(', ') if my_emp_row is not None and pd.notna(my_emp_row['skills']) else ["General"]
    
    st.sidebar.title("👤 My Profile")
    st.sidebar.write(f"Welcome back,\n**{user_name}**.")
    st.sidebar.write("---")
    
    with st.sidebar.expander("🛠️ Update My Skills"):
        st.caption("Tell the system what you're good at so you get the right gigs!")
        available_skills = ["General", "Cleaning", "Janitorial", "Babysitting", "Moving", "Tutoring", "Event Staff"]
        new_skills = st.multiselect("My Domains", available_skills, default=[s for s in my_skills if s in available_skills])
        if st.button("Save Skills 💾"):
            skills_str = ", ".join(new_skills) if new_skills else "General"
            emp_idx = emps_df.index[emps_df['id'] == user_id].tolist()[0]
            emps_df.at[emp_idx, 'skills'] = skills_str
            save_emps(emps_df)
            st.success("Skills updated! The algorithm will remember this.")
            st.rerun()

    st.sidebar.write("---")
    wa_url = f"https://wa.me/{SUPPORT_NUMBER}?text=Hello! I need assistance regarding the SSS portal:%20"
    st.sidebar.link_button("💬 Contact Administrator", wa_url, use_container_width=True)
    st.sidebar.write("---")
    
    # 🧠 RETURN LOGIC FOR PHASED ADMINS
    if is_phased:
        st.sidebar.warning("👁️ ADMIN VIEW MODE")
        if st.sidebar.button("Return to Admin Dashboard ⚡", type="primary", use_container_width=True):
            st.session_state.current_user = {"role": "admin", "name": "Administrator"}
            st.rerun()
    else:
        if st.sidebar.button("Log Out 🚪", type="primary", use_container_width=True):
            st.session_state.current_user = None
            st.rerun()

    if not tasks_df.empty:
        tasks_df['employee_Id'] = tasks_df['employee_Id'].astype(str)
        my_tasks = tasks_df[tasks_df['employee_Id'] == user_id]
        total_earned = sum(float(t.get('payout', float(t['hours']) * float(t['rate']))) for _, t in my_tasks.iterrows() if t['status'] == 'Paid')
        # Pending balance now includes Approved status as money floats
        pending_balance = sum(float(t.get('payout', float(t['hours']) * float(t['rate']))) for _, t in my_tasks.iterrows() if t['status'] in ['Pending', 'Confirmed', 'In Progress', 'Completed', 'Approved'])
    else:
        my_tasks, total_earned, pending_balance = pd.DataFrame(), 0, 0

    st.subheader("My Stats 🏆")
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Total Earnings (Your Take Profits)", f"Ksh {total_earned}")
    c2.metric("📊 Floating Balance", f"Ksh {pending_balance}")
    c3.metric("✨ SSS Points (Your Flex)", f"{my_points} pts")
    
    st.write("---")
    st.subheader("💼 My Assigned Tasks")
    
    if st.button("🔄 Refresh Dashboard", type="secondary"):
        fetch_portal_data.clear()
        st.rerun()
    
    if my_tasks.empty:
        st.info("No tasks assigned at the moment. You are caught up! Enjoy the peace. 🧘‍♂️")
    else:
        for i, task in my_tasks.iterrows():
            if pd.isna(task.get('title')): continue
            
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    st.markdown(f"### {task['title']}")
                    if task.get('instructions'): st.info(f"**📝 Instructions:**\n\n{task['instructions']}")
                    
                    date_str = task.get('date_assigned', 'Unknown Date')
                    due_str = task.get('due_date', 'N/A')
                    payout_val = task.get('payout', float(task['hours']) * float(task['rate']))
                    st.caption(f"🕒 Assigned: {date_str} | 🎯 Due: {due_str} | Allocated: {task['hours']} hrs @ Ksh {task['rate']}/hr  => **Expected Payout: Ksh {payout_val}**")

                with colB:
                    # FLOW: PENDING -> CONFIRMED
                    if task['status'] == 'Pending':
                        if st.button("Confirm Availability ✅", key=f"confirm_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Confirmed'
                            with st.spinner("Confirming your availability... W move."):
                                save_tasks(tasks_df)
                            st.rerun()
                            
                        with st.expander("Decline Task ❌"):
                            st.caption("Unable to take this task? Please provide a reason.")
                            reason = st.text_area("Reason for declining:", key=f"reason_{task['id']}")
                            if st.button("Submit Decline", key=f"cancel_btn_{task['id']}", type="primary"):
                                if not reason.strip():
                                    st.error("Please provide a reason for declining. Don't ghost us! 👻")
                                else:
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Cancelled'
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'cancel_reason'] = reason
                                    
                                    # 🤖 AUTO-REASSIGN LOGIC 🤖
                                    task_cat = task.get('category', 'General')
                                    eligible_pool = emps_df[(emps_df['id'] != user_id) & (emps_df['skills'].str.contains(task_cat, case=False, na=False))]
                                    if eligible_pool.empty:
                                        eligible_pool = emps_df[emps_df['id'] != user_id] # fallback
                                        
                                    if not eligible_pool.empty:
                                        active_counts = tasks_df[tasks_df['status'].isin(['Pending', 'Confirmed', 'In Progress'])].groupby('employee_Id').size()
                                        eligible_pool['active_tasks'] = eligible_pool['id'].map(active_counts).fillna(0)
                                        best_emp = eligible_pool.sort_values(by=['active_tasks', 'points'], ascending=[True, False]).iloc[0]
                                        
                                        new_task = task.copy()
                                        new_task['id'] = int(time.time() * 1000)
                                        new_task['employee_Id'] = best_emp['id']
                                        new_task['status'] = 'Pending'
                                        for key in ['msg_allocated', 'msg_night_before', 'msg_1hr_before', 'msg_late', 'msg_admin_cancelled', 'msg_admin_completed', 'time_marked_done', 'rating']:
                                            new_task[key] = ""
                                        
                                        # Clean local assignment
                                        updated_tasks_df = pd.concat([tasks_df, pd.DataFrame([new_task])], ignore_index=True)
                                    else:
                                        updated_tasks_df = tasks_df
                                    
                                    with st.spinner("Processing cancellation and triggering auto-reassignment AI... 🧠"):
                                        save_tasks(updated_tasks_df)
                                    st.session_state[f"wa_reason_{task['id']}"] = reason
                                    st.rerun()
                                    
                    # FLOW: CONFIRMED -> IN PROGRESS
                    elif task['status'] == 'Confirmed':
                        if st.button("Start Task 🏃", key=f"start_{task['id']}", type="secondary"):
                            allowed_to_start = True
                            if due_str:
                                try:
                                    task_due_time = KISUMU_TZ.localize(datetime.strptime(due_str, "%Y-%m-%d %H:%M:%S"))
                                    now_eat = datetime.now(KISUMU_TZ)
                                    time_diff = task_due_time - now_eat
                                    
                                    # Anti-sniper logic: Cannot start more than 1 hr before schedule
                                    if time_diff > timedelta(hours=1):
                                        allowed_to_start = False
                                        wait_time = time_diff - timedelta(hours=1)
                                        hours_wait = int(wait_time.total_seconds() // 3600)
                                        mins_wait = int((wait_time.total_seconds() % 3600) // 60)
                                        
                                        st.error(f"🛑 **Action Denied:** You are attempting to start this task too early. System policy allows clocking in up to 1 hour before the scheduled start time. Please try again in {hours_wait}h {mins_wait}m. Stop trying to speedrun! 🎮")
                                except Exception as e:
                                    pass 
                            
                            if allowed_to_start:
                                tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'In Progress'
                                with st.spinner("Clocking in... Status updated to In Progress 🚀 Get to work!"):
                                    save_tasks(tasks_df)
                                st.rerun()
                            
                        with st.expander("Cancel Confirmed Task 🚫"):
                            st.caption("Unable to complete the task? Please provide a reason.")
                            reason = st.text_area("Reason:", key=f"reason_{task['id']}")
                            if st.button("Cancel Task 🚩", key=f"cancel_btn2_{task['id']}", type="primary"):
                                if not reason.strip():
                                    st.error("Please provide a reason for cancellation. 🛑")
                                else:
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Cancelled'
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'cancel_reason'] = reason
                                    
                                    # 🤖 AUTO-REASSIGN LOGIC 🤖
                                    task_cat = task.get('category', 'General')
                                    eligible_pool = emps_df[(emps_df['id'] != user_id) & (emps_df['skills'].str.contains(task_cat, case=False, na=False))]
                                    if eligible_pool.empty:
                                        eligible_pool = emps_df[emps_df['id'] != user_id] # fallback
                                        
                                    if not eligible_pool.empty:
                                        active_counts = tasks_df[tasks_df['status'].isin(['Pending', 'Confirmed', 'In Progress'])].groupby('employee_Id').size()
                                        eligible_pool['active_tasks'] = eligible_pool['id'].map(active_counts).fillna(0)
                                        best_emp = eligible_pool.sort_values(by=['active_tasks', 'points'], ascending=[True, False]).iloc[0]
                                        
                                        new_task = task.copy()
                                        new_task['id'] = int(time.time() * 1000)
                                        new_task['employee_Id'] = best_emp['id']
                                        new_task['status'] = 'Pending'
                                        for key in ['msg_allocated', 'msg_night_before', 'msg_1hr_before', 'msg_late', 'msg_admin_cancelled', 'msg_admin_completed', 'time_marked_done', 'rating']:
                                            new_task[key] = ""
                                        
                                        updated_tasks_df = pd.concat([tasks_df, pd.DataFrame([new_task])], ignore_index=True)
                                    else:
                                        updated_tasks_df = tasks_df

                                    with st.spinner("Processing cancellation and triggering auto-reassignment AI..."):
                                        save_tasks(updated_tasks_df)
                                    st.session_state[f"wa_reason_{task['id']}"] = reason
                                    st.rerun()

                    # FLOW: IN PROGRESS -> COMPLETED
                    elif task['status'] == 'In Progress':
                        if st.button("Mark Done ✔️", key=f"done_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Completed'
                            tasks_df.loc[tasks_df['id'] == task['id'], 'time_marked_done'] = datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S")
                            with st.spinner("Marking as completed and notifying admin for QC approval... Bro cooked! 🍳"):
                                save_tasks(tasks_df)
                            st.rerun()
                        with st.expander("Abort Task 🚩"):
                            st.caption("Abandoning an in-progress gig? Leave a reason.")
                            reason = st.text_area("Reason:", key=f"reason_abort_{task['id']}")
                            if st.button("Abort Task 🚩", key=f"abscond_{task['id']}"):
                                if not reason.strip():
                                    st.error("A reason is required to abort an active task.")
                                else:
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Cancelled'
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'cancel_reason'] = reason
                                    
                                    # Since they aborted mid-task, we probably shouldn't blindly auto-reassign. 
                                    # We'll leave it to admin to figure out what went wrong.
                                    
                                    with st.spinner("Canceling task..."):
                                        save_tasks(tasks_df)
                                    st.session_state[f"wa_reason_{task['id']}"] = reason
                                    st.rerun()
                                    
                    elif task['status'] == 'Completed':
                        st.warning("QC Approval Pending ⏳ (Admin is reviewing your work)")
                    elif task['status'] == 'Approved':
                        st.info("Approved! ✨ Awaiting Funds Disbursement.")
                    elif task['status'] == 'Paid':
                        st.success(f"Paid ✅ | Rated: {task.get('rating', '5')} ⭐️")
                    elif task['status'] in ['Cancelled', 'Absconded']:
                        st.error("Task Cancelled 🚩")
                        
                        reason_text = st.session_state.get(f"wa_reason_{task['id']}", task.get('cancel_reason', ''))
                        if reason_text:
                            encoded_msg = urllib.parse.quote(f"🚨 *Task Cancelled!*\n*Worker:* {user_name}\n*Task:* {task['title']}\n*Reason:* {reason_text}")
                            wa_url = f"https://wa.me/{SUPPORT_NUMBER}?text={encoded_msg}"
                            st.link_button("📲 Send Manual Follow-up to Admin", wa_url)
