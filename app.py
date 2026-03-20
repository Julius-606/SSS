import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime

# --- CONFIG & DB SETUP ---
st.set_page_config(page_title="SSS Portal OS", layout="wide", page_icon="✨")

TASKS_CSV = "tasks.csv"
EMPS_CSV = "employees.csv"
RESET_TRACKER = "last_reset.txt"

# DEFAULT ADMIN CREDENTIALS
ADMIN_USER = "admin"
ADMIN_PASS = "admin@SSS"

# --- THE COLD WALLETS (CSV ENGINES) ---

# 1. Initialize Employees CSV
if not os.path.exists(EMPS_CSV):
    df_emps_init = pd.DataFrame([
        {"id": "emp1", "name": "Wanjiku (Nanny Pro)", "username": "wanjiku", "password": "password123"},
        {"id": "emp2", "name": "Ochieng (Deep Cleaner)", "username": "ochieng", "password": "password123"}
    ])
    df_emps_init.to_csv(EMPS_CSV, index=False)

# 2. Initialize Tasks CSV
if not os.path.exists(TASKS_CSV):
    df_tasks_init = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned"])
    df_tasks_init.to_csv(TASKS_CSV, index=False)

# 3. THE MONTHLY AUTO-ARCHIVE ENGINE
CURRENT_MONTH = datetime.now().strftime("%Y-%m")

if not os.path.exists(RESET_TRACKER):
    with open(RESET_TRACKER, "w") as f:
        f.write(CURRENT_MONTH)

with open(RESET_TRACKER, "r") as f:
    last_reset = f.read().strip()

# If we entered a new month, trigger the rollover!
if last_reset != CURRENT_MONTH and os.path.exists(TASKS_CSV):
    try:
        temp_tasks_df = pd.read_csv(TASKS_CSV)
        if not temp_tasks_df.empty:
            # Keep active gigs
            active_statuses = ['Pending', 'In Progress', 'Completed']
            keep_df = temp_tasks_df[temp_tasks_df['status'].isin(active_statuses)]
            
            # Archive settled/blown gigs
            archive_df = temp_tasks_df[~temp_tasks_df['status'].isin(active_statuses)]
            
            if not archive_df.empty:
                archive_filename = f"archive_{last_reset}.csv"
                if os.path.exists(archive_filename):
                    existing_archive = pd.read_csv(archive_filename)
                    combined_archive = pd.concat([existing_archive, archive_df], ignore_index=True)
                    combined_archive.to_csv(archive_filename, index=False)
                else:
                    archive_df.to_csv(archive_filename, index=False)
            
            # Overwrite main ledger with ONLY the carry-over active gigs
            keep_df.to_csv(TASKS_CSV, index=False)
        
        # Update the tracker file to the new month
        with open(RESET_TRACKER, "w") as f:
            f.write(CURRENT_MONTH)
    except Exception as e:
        st.error(f"Archive Engine Failed: {e}")

# Load the liquidity pools
try:
    emps_df = pd.read_csv(EMPS_CSV)
    emps_df['id'] = emps_df['id'].astype(str)
    emps_df['username'] = emps_df['username'].astype(str)
    emps_df['password'] = emps_df['password'].astype(str)
except Exception as e:
    st.error(f"Failed to read Employee Ledger. Error: {e}")
    emps_df = pd.DataFrame(columns=["id", "name", "username", "password"])

try:
    tasks_df = pd.read_csv(TASKS_CSV)
    tasks_df['hours'] = pd.to_numeric(tasks_df['hours'], errors='coerce')
    tasks_df['rate'] = pd.to_numeric(tasks_df['rate'], errors='coerce')
except Exception as e:
    st.error(f"Failed to read Tasks Ledger. Error: {e}")
    tasks_df = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned"])

def save_tasks(df):
    df.to_csv(TASKS_CSV, index=False)

def save_emps(df):
    df.to_csv(EMPS_CSV, index=False)

# Initialize Session State
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- HELPER FUNCTIONS ---
def get_employee_name(emp_id):
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
                if new_emp_user in emps_df['username'].values:
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
                    save_emps(emps_df)
                    st.success(f"{new_emp_name} added! They can now log in.")
                    st.rerun()
            else:
                st.error("Fill out all fields bro.")
                
    st.sidebar.write("---")
    
    # THE ADMIN PHASE SHIFT
    st.sidebar.subheader("👁️ Phase Mode")
    phase_target = st.sidebar.selectbox("Enter Hustler's Dashboard:", emps_df['name'].tolist())
    if st.sidebar.button("Phase In 👻"):
        emp_row = emps_df[emps_df['name'] == phase_target].iloc[0]
        st.session_state.current_user = {
            "role": "employee", 
            "id": emp_row['id'], 
            "name": emp_row['name'],
            "is_phased": True # Flaggers for the logout button
        }
        st.rerun()

    st.sidebar.write("---")
    if st.sidebar.button("Log Out 🚪", type="primary"):
        st.session_state.current_user = None
        st.rerun()

    col1, col2 = st.columns([1, 2])
    
    # Left Col: Create Task Form
    with col1:
        st.subheader("➕ Dispatch a Gig")
        with st.container(border=True):
            with st.form("dispatch_form"):
                final_title = st.text_input("Gig Title")
                
                emp_options = dict(zip(emps_df['name'], emps_df['id']))
                selected_squad_names = st.multiselect("👥 Build the Syndicate", list(emp_options.keys()))
                
                h_col, r_col = st.columns(2)
                hours = h_col.number_input("Hours / Person", min_value=0.5, step=0.5, value=1.0)
                # Removed the min_value limit. It can go down to 0.0 now!
                rate = r_col.number_input("Rate / Hr (Ksh)", min_value=0.0, step=10.0, value=300.0)
                
                submitted = st.form_submit_button("🚀 Dispatch to Squad", type="primary")
                
                if submitted:
                    if not selected_squad_names:
                        st.error("⚠️ Pick at least one hustler bro, don't leave the gig hanging.")
                    else:
                        new_records = []
                        # Specific down to the second!
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
                        save_tasks(tasks_df)
                        
                        st.success(f"Dispatched to {len(selected_squad_names)} hustlers!")
                        st.rerun()

    # Right Col: Active Gigs
    with col2:
        st.subheader("⚡ Active Market (Needs Attention)")
        active_tasks = tasks_df[tasks_df['status'].isin(['Pending', 'In Progress', 'Completed'])]
        
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

# --- 3. EMPLOYEE DASHBOARD (THE TRENCHES) ---
elif st.session_state.current_user['role'] == 'employee':
    user_id = str(st.session_state.current_user['id'])
    user_name = st.session_state.current_user['name']
    is_phased = st.session_state.current_user.get('is_phased', False)
    
    st.sidebar.title("👤 My Profile")
    st.sidebar.write(f"Welcome back to the trenches,\n**{user_name}**.")
    
    st.sidebar.write("---")
    
    # Check if the Admin is phasing in!
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
    
    if my_tasks.empty:
        st.info("No tasks assigned. You're officially off the clock. Go study some clinical meds or chart EUR/USD. 📉")
    else:
        for i, task in my_tasks.iloc[::-1].iterrows():
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
                            save_tasks(tasks_df)
                            st.rerun()
                    elif task['status'] == 'In Progress':
                        if st.button("Mark Done ✔️", key=f"done_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Completed'
                            save_tasks(tasks_df)
                            st.rerun()
                        if st.button("Absconded 🏃‍♂️💨", key=f"abscond_{task['id']}"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Absconded'
                            save_tasks(tasks_df)
                            st.rerun()
                    elif task['status'] == 'Completed':
                        st.warning("Awaiting Funds ⏳")
                    elif task['status'] == 'Paid':
                        st.success("Paid ✅")
                    elif task['status'] == 'Absconded':
                        st.error("Account Blown 🚩")
