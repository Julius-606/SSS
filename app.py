import streamlit as st
import pandas as pd
import time
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import traceback

# --- CONFIG & SECRETS SETUP ---
st.set_page_config(page_title="SSS Portal OS", layout="wide", page_icon="✨")

ADMIN_USER = "admin"
ADMIN_PASS = "admin@SSS"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing"

# --- 🛑 1. THE VIP CONNECTION (CACHED - ONLY RUNS ONCE) 🛑 ---
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
        st.error("🚨 Stop-loss hit! Failed to authenticate with Google. Check your secrets!")
        st.stop()

# --- 🛑 2. MOUNT THE WORKSHEETS (CACHED - ONLY RUNS ONCE) 🛑 ---
@st.cache_resource
def get_worksheets():
    client = get_gspread_client()
    try:
        workbook = client.open_by_url(SHEET_URL)
    except Exception as e:
        st.error(f"🚨 Failed to find the target Google Sheet.\n\nError: {e}")
        st.stop()
        
    def get_or_create(title, headers):
        try:
            ws = workbook.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            ws = workbook.add_worksheet(title=title, rows="1000", cols="20")
            ws.append_row(headers)
        return ws

    emps_ws = get_or_create("Employees", ["id", "name", "username", "password"])
    tasks_ws = get_or_create("Tasks", ["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned"])
    settings_ws = get_or_create("Settings", ["setting_key", "setting_value"])
    
    # Initialize default admins if Employees is empty
    if not emps_ws.get_all_records():
        emps_ws.append_row(["emp1", "Wanjiku (Nanny Pro)", "wanjiku", "password123"])
        emps_ws.append_row(["emp2", "Ochieng (Deep Cleaner)", "ochieng", "password123"])
        
    return workbook, emps_ws, tasks_ws, settings_ws

workbook, emps_ws, tasks_ws, settings_ws = get_worksheets()

# --- 🛑 3. THE LIQUIDITY POOL (PULL DATA & CACHE FOR 30 SECONDS) 🛑 ---
# ttl=30 means it won't ask Google for new data for 30 secs unless we manually clear the cache!
@st.cache_data(ttl=30)
def fetch_market_data():
    emps_df = pd.DataFrame(emps_ws.get_all_records())
    if not emps_df.empty:
        emps_df['id'] = emps_df['id'].astype(str)
        emps_df['username'] = emps_df['username'].astype(str)
        emps_df['password'] = emps_df['password'].astype(str)

    tasks_records = tasks_ws.get_all_records()
    if tasks_records:
        tasks_df = pd.DataFrame(tasks_records)
        tasks_df['hours'] = pd.to_numeric(tasks_df['hours'], errors='coerce')
        tasks_df['rate'] = pd.to_numeric(tasks_df['rate'], errors='coerce')
    else:
        tasks_df = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned"])
        
    settings_df = pd.DataFrame(settings_ws.get_all_records())
    
    return emps_df, tasks_df, settings_df

# Load the cached data
emps_df, tasks_df, settings_df = fetch_market_data()

# --- THE MONTHLY AUTO-ARCHIVE ENGINE ---
CURRENT_MONTH = datetime.now().strftime("%Y-%m")

if settings_df.empty or 'last_reset' not in settings_df['setting_key'].values:
    settings_ws.append_row(["last_reset", CURRENT_MONTH])
    fetch_market_data.clear() # Clear cache so it re-pulls next time
    last_reset = CURRENT_MONTH
else:
    last_reset = settings_df.loc[settings_df['setting_key'] == 'last_reset', 'setting_value'].iloc[0]

if last_reset != CURRENT_MONTH:
    try:
        if not tasks_df.empty:
            active_statuses = ['Pending', 'In Progress', 'Completed']
            keep_df = tasks_df[tasks_df['status'].isin(active_statuses)]
            archive_df = tasks_df[~tasks_df['status'].isin(active_statuses)]
            
            if not archive_df.empty:
                archive_title = f"Archive_{last_reset}"
                try:
                    archive_ws = workbook.worksheet(archive_title)
                except gspread.exceptions.WorksheetNotFound:
                    archive_ws = workbook.add_worksheet(title=archive_title, rows="1000", cols="20")
                    archive_ws.append_row(list(archive_df.columns))
                archive_ws.append_rows(archive_df.values.tolist())
            
            # Save the active ones back
            tasks_ws.clear()
            tasks_ws.update([keep_df.columns.values.tolist()] + keep_df.fillna('').values.tolist())
        
        # Update settings tracker
        cell = settings_ws.find("last_reset")
        settings_ws.update_cell(cell.row, cell.col + 1, CURRENT_MONTH)
        
        # MAJOR KEY: Clear the cache because we just edited the cloud data!
        fetch_market_data.clear()
        st.rerun()
        
    except Exception as e:
        st.error(f"Archive Engine Failed: {e}")

# --- WRITE FUNCTIONS (WITH CACHE CLEARING) ---
def save_tasks(df):
    tasks_ws.clear()
    tasks_ws.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
    fetch_market_data.clear() # Flushes the cache so the next rerun sees the new data! 🚀

def save_emps(df):
    emps_ws.clear()
    emps_ws.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
    fetch_market_data.clear() 

# Initialize Session State
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- HELPER FUNCTIONS ---
def get_employee_name(emp_id):
    if emps_df.empty: return "Unknown Hustler 👻"
    match = emps_df[emps_df['id'] == str(emp_id)]
    if not match.empty:
        return match.iloc[0]['name']
    return "Unknown Hustler 👻"

# --- 1. LOGIN SCREEN (THE FIREWALL) ---
if st.session_state.current_user is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>✨ SSS Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray; margin-bottom: 30px;'>Swift-hands Student Services. Authorized Personnel Only.</p>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("### 🔐 Secure Login")
            with st.form("login_form"):
                login_user = st.text_input("Username")
                login_pass = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Enter the Market 🚀", use_container_width=True, type="primary")
                
                if submitted:
                    if login_user == ADMIN_USER and login_pass == ADMIN_PASS:
                        st.session_state.current_user = {"role": "admin", "name": "Admin Boss"}
                        st.rerun()
                    else:
                        match = emps_df[(emps_df['username'] == login_user) & (emps_df['password'] == login_pass)]
                        if not match.empty:
                            emp = match.iloc[0]
                            st.session_state.current_user = {"role": "employee", "id": emp['id'], "name": emp['name'], "is_phased": False}
                            st.rerun()
                        else:
                            st.error("Invalid credentials. Stop-loss hit. 📉 Try again.")

# --- 2. ADMIN DASHBOARD (GOD MODE) ---
elif st.session_state.current_user['role'] == 'admin':
    st.sidebar.title("🛡️ Admin Command Center")
    st.sidebar.write("Managing the SSS Prop Firm.")
    
    st.sidebar.write("---")
    st.sidebar.subheader("👔 HR Dept (Onboarding)")
    with st.sidebar.form("add_employee_form"):
        new_emp_name = st.text_input("Full Name", placeholder="e.g. Kamaa (Plumber)")
        new_emp_user = st.text_input("Username", placeholder="e.g. kamaa99")
        new_emp_pass = st.text_input("Password", type="password", placeholder="Assign a password")
        
        if st.form_submit_button("Hire Hustler 🤝"):
            if new_emp_name and new_emp_user and new_emp_pass:
                if not emps_df.empty and new_emp_user in emps_df['username'].values:
                    st.error("Username already taken! Pick another one.")
                else:
                    new_id = f"emp{int(time.time())}"
                    new_row = pd.DataFrame([{
                        "id": new_id, 
                        "name": new_emp_name, 
                        "username": new_emp_user, 
                        "password": new_emp_pass
                    }])
                    emps_df = pd.concat([emps_df, new_row], ignore_index=True)
                    with st.spinner("Writing to Google Cloud..."):
                        save_emps(emps_df)
                    st.success(f"{new_emp_name} added! They can now log in.")
                    st.rerun()
            else:
                st.error("Fill out all fields bro.")
                
    st.sidebar.write("---")
    
    st.sidebar.subheader("👁️ Phase Mode")
    if not emps_df.empty:
        phase_target = st.sidebar.selectbox("Enter Hustler's Dashboard:", emps_df['name'].tolist())
        if st.sidebar.button("Phase In 👻"):
            emp_row = emps_df[emps_df['name'] == phase_target].iloc[0]
            st.session_state.current_user = {
                "role": "employee", 
                "id": emp_row['id'], 
                "name": emp_row['name'],
                "is_phased": True
            }
            st.rerun()

    st.sidebar.write("---")
    if st.sidebar.button("Log Out 🚪", type="primary"):
        st.session_state.current_user = None
        st.rerun()

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("➕ Dispatch a Gig")
        with st.container(border=True):
            with st.form("dispatch_form"):
                final_title = st.text_input("Gig Title")
                
                emp_options = dict(zip(emps_df['name'], emps_df['id'])) if not emps_df.empty else {}
                selected_squad_names = st.multiselect("👥 Build the Syndicate", list(emp_options.keys()))
                
                h_col, r_col = st.columns(2)
                hours = h_col.number_input("Hours / Person", min_value=0.5, step=0.5, value=1.0)
                rate = r_col.number_input("Rate / Hr (Ksh)", min_value=0.0, step=10.0, value=300.0)
                
                submitted = st.form_submit_button("🚀 Dispatch to Squad", type="primary")
                
                if submitted:
                    if not selected_squad_names:
                        st.error("⚠️ Pick at least one hustler bro, don't leave the gig hanging.")
                    else:
                        new_records = []
                        exact_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        for name in selected_squad_names:
                            emp_id = emp_options[name]
                            new_records.append({
                                "id": int(time.time() * 1000) + hash(emp_id) % 1000,
                                "title": final_title,
                                "employee_Id": emp_id,
                                "hours": hours,
                                "rate": rate,
                                "status": "Pending",
                                "date_assigned": exact_time_str
                            })
                        
                        new_df = pd.DataFrame(new_records)
                        tasks_df = pd.concat([tasks_df, new_df], ignore_index=True)
                        with st.spinner("Dispatching gigs to the blockchain..."):
                            save_tasks(tasks_df)
                        
                        st.success(f"Dispatched to {len(selected_squad_names)} hustlers!")
                        st.rerun()

    with col2:
        st.subheader("⚡ Active Market (Needs Attention)")
        if not tasks_df.empty:
            active_tasks = tasks_df[tasks_df['status'].isin(['Pending', 'In Progress', 'Completed'])]
        else:
            active_tasks = pd.DataFrame()
            
        if active_tasks.empty:
            st.info("No active gigs right now. The market is consolidating. 📉")
        else:
            for i, task in active_tasks.iloc[::-1].iterrows():
                if pd.isna(task.get('title')): continue 
                
                with st.container(border=True):
                    t_col1, t_col2 = st.columns([3, 1])
                    with t_col1:
                        st.markdown(f"**{task['title']}**")
                        emp_name = get_employee_name(task['employee_Id']).split(' ')[0]
                        date_str = task.get('date_assigned', 'Unknown Date')
                        st.caption(f"👤 {emp_name} | ⏳ {task['hours']}h | 💵 Ksh {task['rate']}/h | 🕒 {date_str}")
                    with t_col2:
                        st.markdown(f"**Ksh {float(task['hours']) * float(task['rate'])}**")
                        
                        if task['status'] == 'Pending':
                            st.warning("Cooking ⏳")
                        elif task['status'] == 'In Progress':
                            st.info("Grinding 🏃")
                        elif task['status'] == 'Completed':
                            if st.button("Mark Paid 💸", key=f"pay_{task['id']}"):
                                tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Paid'
                                with st.spinner("Settling funds..."):
                                    save_tasks(tasks_df)
                                st.rerun()

    st.write("---")
    st.subheader("🗄️ The Master Ledger (Current Month)")
    
    if not tasks_df.empty:
        display_df = tasks_df.copy()
        display_df['Employee Name'] = display_df['employee_Id'].apply(get_employee_name)
        display_df['Total Payout (Ksh)'] = display_df['hours'] * display_df['rate']
        display_df = display_df[['id', 'date_assigned', 'title', 'Employee Name', 'hours', 'rate', 'Total Payout (Ksh)', 'status']]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Ledger is completely empty.")
        
    if st.button("🔄 Force Refresh Ledger", type="secondary"):
        fetch_market_data.clear()
        st.rerun()

# --- 3. EMPLOYEE DASHBOARD (THE TRENCHES) ---
elif st.session_state.current_user['role'] == 'employee':
    user_id = str(st.session_state.current_user['id'])
    user_name = st.session_state.current_user['name']
    is_phased = st.session_state.current_user.get('is_phased', False)
    
    st.sidebar.title("👤 My Profile")
    st.sidebar.write(f"Welcome back to the trenches,\n**{user_name}**.")
    
    st.sidebar.write("---")
    
    if is_phased:
        st.sidebar.warning("👁️ ADMIN PHASED IN")
        if st.sidebar.button("Return to God-Mode ⚡", type="primary"):
            st.session_state.current_user = {"role": "admin", "name": "Admin Boss"}
            st.rerun()
    else:
        if st.sidebar.button("Log Out 🚪", type="primary"):
            st.session_state.current_user = None
            st.rerun()

    if not tasks_df.empty:
        tasks_df['employee_Id'] = tasks_df['employee_Id'].astype(str)
        my_tasks = tasks_df[tasks_df['employee_Id'] == user_id]
        total_earned = sum(float(t['hours']) * float(t['rate']) for _, t in my_tasks.iterrows() if t['status'] == 'Paid')
        pending_bag = sum(float(t['hours']) * float(t['rate']) for _, t in my_tasks.iterrows() if t['status'] in ['Pending', 'In Progress', 'Completed'])
    else:
        my_tasks = pd.DataFrame()
        total_earned = 0
        pending_bag = 0

    c1, c2 = st.columns(2)
    c1.metric("💵 Secured Bag (TP Hit)", f"Ksh {total_earned}")
    c2.metric("📉 Floating P/L", f"Ksh {pending_bag}")
    
    st.write("---")
    st.subheader("💼 My Hitlist")
    
    if st.button("🔄 Refresh Market", type="secondary"):
        fetch_market_data.clear()
        st.rerun()
    
    if my_tasks.empty:
        st.info("No tasks assigned. You're officially off the clock. Go study some clinical meds or chart EUR/USD. 📉")
    else:
        for i, task in my_tasks.iterrows():
            if pd.isna(task.get('title')): continue
            
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    st.markdown(f"### {task['title']}")
                    date_str = task.get('date_assigned', 'Unknown Date')
                    st.caption(f"🕒 Assigned: {date_str} | Allocated: {task['hours']} hrs @ Ksh {task['rate']}/hr  => **Target TP: Ksh {float(task['hours']) * float(task['rate'])}**")

                with colB:
                    if task['status'] == 'Pending':
                        if st.button("Start Gig 🏃", key=f"start_{task['id']}", type="secondary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'In Progress'
                            with st.spinner("Locking in entry..."):
                                save_tasks(tasks_df)
                            st.rerun()
                    elif task['status'] == 'In Progress':
                        if st.button("Mark Done ✔️", key=f"done_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Completed'
                            with st.spinner("Securing profits..."):
                                save_tasks(tasks_df)
                            st.rerun()
                        if st.button("Absconded 🏃‍♂️💨", key=f"abscond_{task['id']}"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Absconded'
                            with st.spinner("Blowing the account..."):
                                save_tasks(tasks_df)
                            st.rerun()
                    elif task['status'] == 'Completed':
                        st.warning("Awaiting Funds ⏳")
                    elif task['status'] == 'Paid':
                        st.success("Paid ✅")
                    elif task['status'] == 'Absconded':
                        st.error("Account Blown 🚩")
