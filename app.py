import streamlit as st
import pandas as pd
import requests
import os
import time
from datetime import date

# --- CONFIG & DB SETUP ---
st.set_page_config(page_title="SSS Portal OS", layout="wide", page_icon="✨")

API_KEY = "" # Drop your Gemini API Key here for the AI Tips!
TASKS_CSV = "tasks.csv"
EMPS_CSV = "employees.csv"

# --- THE COLD WALLETS (CSV ENGINES) ---

# 1. Initialize Employees CSV if it doesn't exist (Seed with 2 mock hustlers)
if not os.path.exists(EMPS_CSV):
    df_emps_init = pd.DataFrame([
        {"id": "emp1", "name": "Wanjiku (Nanny Pro)"},
        {"id": "emp2", "name": "Ochieng (Deep Cleaner)"}
    ])
    df_emps_init.to_csv(EMPS_CSV, index=False)

# 2. Initialize Tasks CSV if it doesn't exist
if not os.path.exists(TASKS_CSV):
    df_tasks_init = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned"])
    df_tasks_init.to_csv(TASKS_CSV, index=False)

# Load the liquidity pools (DataFrames)
try:
    emps_df = pd.read_csv(EMPS_CSV)
    # Ensure ID is treated as string to avoid weird pandas float conversions
    emps_df['id'] = emps_df['id'].astype(str) 
except Exception as e:
    st.error(f"Failed to read Employee Ledger. Error: {e}")
    emps_df = pd.DataFrame(columns=["id", "name"])

try:
    tasks_df = pd.read_csv(TASKS_CSV)
    # Convert hours/rate to numeric just in case CSV saved them as strings
    tasks_df['hours'] = pd.to_numeric(tasks_df['hours'], errors='coerce')
    tasks_df['rate'] = pd.to_numeric(tasks_df['rate'], errors='coerce')
except Exception as e:
    st.error(f"Failed to read Tasks Ledger. Error: {e}")
    tasks_df = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned"])

def save_tasks(df):
    """Saves the current tasks dataframe straight to the local CSV"""
    df.to_csv(TASKS_CSV, index=False)

def save_emps(df):
    """Saves the current employees dataframe straight to the local CSV"""
    df.to_csv(EMPS_CSV, index=False)

# Initialize Session State
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- HELPER FUNCTIONS ---
def get_employee_name(emp_id):
    # Search our dynamic dataframe for the name
    match = emps_df[emps_df['id'] == str(emp_id)]
    if not match.empty:
        return match.iloc[0]['name']
    return "Unknown Hustler 👻"

def ai_tips(task_title):
    if not API_KEY:
        return "Bro, you forgot to paste the Gemini API Key in the code! Trust your instincts and avoid the stop-loss! ✨"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": f"Give 3 short, punchy, and highly practical tips on how to excellently execute this specific task: '{task_title}'. Format as a short paragraph."}]}],
        "systemInstruction": {"parts": [{"text": "You are an expert mentor for student gig workers. Speak encouragingly. Use slight Gen-Z slang."}]}
    }
    try:
        res = requests.post(url, json=payload)
        data = res.json()
        return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return "Failed to load AI tips. Secure the bag manually! ✨"

# --- LOGIN SCREEN ---
if st.session_state.current_user is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>✨ SSS Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Swift-hands Student Services. Secure your bag. No cap.</p>", unsafe_allow_html=True)
        
        st.write("---")
        if st.button("🛡️ Login as Admin (The Boss)", use_container_width=True, type="primary"):
            st.session_state.current_user = {"role": "admin", "name": "Admin Boss"}
            st.rerun()
            
        st.markdown("<p style='text-align: center; font-size: 12px; font-weight: bold; color: gray; margin-top: 15px;'>OR HUSTLE</p>", unsafe_allow_html=True)
        
        # Pull names directly from the dynamic CSV
        emp_names = emps_df['name'].tolist()
        if not emp_names:
            st.warning("No employees enrolled yet. Admin needs to hire some hustlers!")
        else:
            selected_emp = st.selectbox("Select your profile", emp_names)
            if st.button("👤 Login as Employee", use_container_width=True):
                emp_row = emps_df[emps_df['name'] == selected_emp].iloc[0]
                st.session_state.current_user = {"role": "employee", "id": emp_row['id'], "name": emp_row['name']}
                st.rerun()

# --- ADMIN DASHBOARD ---
elif st.session_state.current_user['role'] == 'admin':
    st.sidebar.title("🛡️ Admin Command Center")
    st.sidebar.write("Managing the SSS Prop Firm.")
    
    st.sidebar.write("---")
    st.sidebar.subheader("👔 HR Dept (Onboarding)")
    with st.sidebar.form("add_employee_form"):
        new_emp_name = st.text_input("New Hustler Name", placeholder="e.g. Kamaa (Plumber)")
        if st.form_submit_button("Hire Hustler 🤝"):
            if new_emp_name:
                new_id = f"emp{int(time.time())}"
                new_row = pd.DataFrame([{"id": new_id, "name": new_emp_name}])
                emps_df = pd.concat([emps_df, new_row], ignore_index=True)
                save_emps(emps_df)
                st.success(f"{new_emp_name} added to the liquidity pool!")
                st.rerun()
            else:
                st.error("Name cannot be empty bro.")
                
    st.sidebar.write("---")
    if st.sidebar.button("Log Out"):
        st.session_state.current_user = None
        st.rerun()

    col1, col2 = st.columns([1, 2])
    
    # Left Col: Create Task Form
    with col1:
        st.subheader("➕ Dispatch a Gig")
        with st.container(border=True):
            with st.form("dispatch_form"):
                final_title = st.text_input("Gig Title")
                
                # Dynamic Squad Mode
                emp_options = dict(zip(emps_df['name'], emps_df['id']))
                selected_squad_names = st.multiselect("👥 Build the Syndicate", list(emp_options.keys()))
                
                h_col, r_col = st.columns(2)
                hours = h_col.number_input("Hours / Person", min_value=0.5, step=0.5, value=1.0)
                rate = r_col.number_input("Rate / Hr (Ksh)", min_value=50.0, step=10.0, value=300.0)
                
                submitted = st.form_submit_button("🚀 Dispatch to Squad", type="primary")
                
                if submitted:
                    if not selected_squad_names:
                        st.error("⚠️ Pick at least one hustler bro, don't leave the gig hanging.")
                    else:
                        new_records = []
                        today_str = date.today().strftime("%Y-%m-%d")
                        for name in selected_squad_names:
                            emp_id = emp_options[name]
                            new_records.append({
                                "id": int(time.time() * 1000) + hash(emp_id) % 1000,
                                "title": final_title,
                                "employee_Id": emp_id,
                                "hours": hours,
                                "rate": rate,
                                "status": "Pending",
                                "date_assigned": today_str
                            })
                        
                        # Add to DataFrame and save to CSV
                        new_df = pd.DataFrame(new_records)
                        tasks_df = pd.concat([tasks_df, new_df], ignore_index=True)
                        save_tasks(tasks_df)
                        
                        st.success(f"Dispatched to {len(selected_squad_names)} hustlers! Ledger updated.")
                        st.rerun()

    # Right Col: Active Gigs (Only showing stuff that needs attention)
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
                        st.caption(f"👤 {emp_name} | ⏳ {task['hours']}h | 💵 Ksh {task['rate']}/h | 📅 {date_str}")
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
    # Bottom Section: The Master Ledger
    st.subheader("🗄️ The Master Ledger (All Transactions)")
    st.write("This is the raw, unfiltered block-chain of your operations. Every TP hit and every Stop Loss blown.")
    
    if not tasks_df.empty:
        # Create a display-friendly version of the dataframe (swap IDs for actual names)
        display_df = tasks_df.copy()
        display_df['Employee Name'] = display_df['employee_Id'].apply(get_employee_name)
        display_df['Total Payout (Ksh)'] = display_df['hours'] * display_df['rate']
        
        # Reorder columns to make it look professional
        display_df = display_df[['id', 'date_assigned', 'title', 'Employee Name', 'hours', 'rate', 'Total Payout (Ksh)', 'status']]
        
        # Display the interactive dataframe
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Ledger is completely empty.")

# --- EMPLOYEE DASHBOARD ---
elif st.session_state.current_user['role'] == 'employee':
    user_id = str(st.session_state.current_user['id'])
    user_name = st.session_state.current_user['name']
    
    st.sidebar.title("👤 My Profile")
    st.sidebar.write(f"Welcome to the trenches, **{user_name}**.")
    if st.sidebar.button("Go Ghost (Logout)"):
        st.session_state.current_user = None
        st.rerun()

    if not tasks_df.empty:
        # Ensure we are comparing strings
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
        st.info("No tasks assigned. You're officially off the clock. Go trade some London Session or touch grass in Dunga Beach. 📉")
    else:
        for i, task in my_tasks.iloc[::-1].iterrows():
            if pd.isna(task.get('title')): continue
            
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    st.markdown(f"### {task['title']}")
                    date_str = task.get('date_assigned', 'Unknown Date')
                    st.caption(f"Assigned: {date_str} | Allocated: {task['hours']} hrs @ Ksh {task['rate']}/hr  => **Target TP: Ksh {float(task['hours']) * float(task['rate'])}**")
                    
                    if st.button("✨ AI Hack (Pro Tips)", key=f"tip_{task['id']}"):
                        with st.spinner("Consulting the algorithms..."):
                            tips = ai_tips(task['title'])
                            st.info(tips)

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