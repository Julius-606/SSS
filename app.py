import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz 
import gspread
from google.oauth2.service_account import Credentials
import urllib.parse

# --- CONFIG & SECRETS SETUP ---
st.set_page_config(page_title="SSS Hustle Hub", layout="wide", page_icon="🔥", initial_sidebar_state="collapsed")

ADMIN_USER = "admin"
ADMIN_PASS = "admin@SSS"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing"
SUPPORT_NUMBER = "254799084376" 
KISUMU_TZ = pytz.timezone('Africa/Nairobi') # East Africa Time (EAT) 

# --- 🛑 CSS INJECTION ENGINE (VIBE THEME) 🛑 ---
def inject_custom_bg():
    bg_css = """
    <style>
    /* Clean but chill Slate and Navy theme */
    .stApp { background-color: #f8fafc; color: #1e293b; }
    h1, h2, h3, h4, p, span, div { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stMetricValue"] { color: #0f172a; font-weight: 700; }
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
        st.error("Authentication Error: Google Sheets is acting sus. Check the credentials or tell the plug to fix the API. 🛑")
        st.stop()

# --- 🛑 2. MOUNT THE WORKSHEETS (CACHED) 🛑 ---
@st.cache_resource
def get_worksheets():
    client = get_gspread_client()
    try:
        workbook = client.open_by_url(SHEET_URL)
    except Exception as e:
        st.error(f"Database Connection Failure. The database ghosted us harder than my ex.\n\nError Details: {e}")
        st.stop()
        
    def get_or_create(title, headers):
        try:
            ws = workbook.worksheet(title)
            existing_headers = ws.row_values(1)
            missing = [h for h in headers if h not in existing_headers]
            if missing:
                # Dynamic Grid Expansion for limits
                if len(existing_headers) + len(missing) > ws.col_count:
                    ws.add_cols(len(missing) + 5) 
                    
                ws.update(
                    values=[missing], 
                    range_name=f"{gspread.utils.rowcol_to_a1(1, len(existing_headers)+1)}"
                )
        except gspread.exceptions.WorksheetNotFound:
            ws = workbook.add_worksheet(title=title, rows="1000", cols="30")
            ws.append_row(headers)
        return ws

    emps_ws = get_or_create("Employees", ["id", "name", "username", "password", "phone", "skills", "points"])
    tasks_ws = get_or_create("Tasks", ["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned", "due_date", "time_marked_done", "payout", "msg_allocated", "msg_night_before", "msg_1hr_before", "msg_late", "cancel_reason", "instructions", "msg_admin_cancelled", "category", "is_recurring", "recurrence_pattern", "rating", "msg_admin_completed"])
    settings_ws = get_or_create("Settings", ["setting_key", "setting_value"])
    
    # Updated Accounting to include detailed breakdowns
    acct_ws = get_or_create("Accounting", ["tx_id", "date", "type", "description", "amount", "status", "details"])
    
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
        
        for col in ["category", "is_recurring", "recurrence_pattern", "rating", "msg_admin_completed"]:
            if col not in tasks_df.columns: tasks_df[col] = ""
    else:
        tasks_df = pd.DataFrame(columns=["id", "title", "employee_Id", "hours", "rate", "status", "date_assigned", "due_date", "time_marked_done", "payout", "category", "is_recurring", "recurrence_pattern", "rating", "msg_admin_completed"])
        
    settings_df = pd.DataFrame(settings_ws.get_all_records())
    
    acct_records = acct_ws.get_all_records()
    if acct_records:
        acct_df = pd.DataFrame(acct_records)
        if 'details' not in acct_df.columns: acct_df['details'] = ""
    else:
        acct_df = pd.DataFrame(columns=["tx_id", "date", "type", "description", "amount", "status", "details"])
    
    return emps_df, tasks_df, settings_df, acct_df

emps_df, tasks_df, settings_df, acct_df = fetch_portal_data()

# --- 🛑 4. BI-WEEKLY AUTO-ARCHIVE ENGINE 🛑 ---
now = datetime.now(KISUMU_TZ)
current_year = now.year
current_week = now.isocalendar()[1]
bi_week_number = (current_week - 1) // 2 + 1
CURRENT_PERIOD = f"{current_year}-BiWeek-{bi_week_number}"

if settings_df.empty or 'last_reset' not in settings_df['setting_key'].values:
    settings_ws.append_row(["last_reset", CURRENT_PERIOD])
    fetch_portal_data.clear()
    last_reset = CURRENT_PERIOD
else:
    last_reset = settings_df.loc[settings_df['setting_key'] == 'last_reset', 'setting_value'].iloc[0]

if last_reset != CURRENT_PERIOD:
    try:
        if not tasks_df.empty:
            active_statuses = ['Pending', 'Confirmed', 'In Progress', 'Completed', 'Approved', 'Cancelled', 'Cancelled (Reviewed)']
            keep_df = tasks_df[tasks_df['status'].isin(active_statuses)]
            archive_df = tasks_df[~tasks_df['status'].isin(active_statuses)]
            
            if not archive_df.empty:
                # Continuous Archiving to a single master sheet with corporate spacing
                archive_title = "Audit Archives"
                try:
                    archive_ws = workbook.worksheet(archive_title)
                    is_new_sheet = False
                except gspread.exceptions.WorksheetNotFound:
                    archive_ws = workbook.add_worksheet(title=archive_title, rows="1000", cols="30")
                    is_new_sheet = True
                
                if is_new_sheet:
                    archive_ws.append_row(list(archive_df.columns))
                else:
                    audit_header = f"=== AUDIT PERIOD: {last_reset} | PROCESSED ON: {now.strftime('%Y-%m-%d %H:%M %Z')} ==="
                    archive_ws.append_rows([
                        [""], 
                        [""], 
                        [audit_header], 
                        list(archive_df.columns) 
                    ])
                
                archive_ws.append_rows(archive_df.values.tolist())
            
            tasks_ws.clear()
            tasks_ws.update(values=[keep_df.columns.values.tolist()] + keep_df.fillna('').values.tolist(), range_name="A1")
        
        cell = settings_ws.find("last_reset")
        settings_ws.update_cell(cell.row, cell.col + 1, CURRENT_PERIOD)
        
        fetch_portal_data.clear()
        st.rerun()
        
    except Exception as e:
        st.error(f"Automated Archiving Process Failed. The bot needs a coffee: {e}")

# --- WRITE FUNCTIONS ---
def save_tasks(df):
    data = [df.columns.values.tolist()] + df.fillna('').values.tolist()
    if len(data) > tasks_ws.row_count: 
        tasks_ws.add_rows(len(data) - tasks_ws.row_count + 100)
    tasks_ws.clear()
    tasks_ws.update(values=data, range_name="A1")
    fetch_portal_data.clear() 

def save_emps(df):
    data = [df.columns.values.tolist()] + df.fillna('').values.tolist()
    if len(data) > emps_ws.row_count: 
        emps_ws.add_rows(len(data) - emps_ws.row_count + 100)
    emps_ws.clear()
    emps_ws.update(values=data, range_name="A1")
    fetch_portal_data.clear() 

def save_acct(df):
    data = [df.columns.values.tolist()] + df.fillna('').values.tolist()
    if len(data) > acct_ws.row_count: 
        acct_ws.add_rows(len(data) - acct_ws.row_count + 100)
    acct_ws.clear()
    acct_ws.update(values=data, range_name="A1")
    fetch_portal_data.clear()

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

def get_employee_name(emp_id):
    if emps_df.empty: return "Ghost Worker"
    match = emps_df[emps_df['id'] == str(emp_id)]
    return match.iloc[0]['name'] if not match.empty else "Ghost Worker"

inject_custom_bg()

# --- 1. LOGIN SCREEN ---
if st.session_state.current_user is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; margin-top: 10vh;'>🔥 SSS Hustle Hub</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #64748b; margin-bottom: 30px;'>Comrades only. No ops allowed. 🛑</p>", unsafe_allow_html=True)
        
        with st.container(border=True):
            with st.form("login_form"):
                login_user = st.text_input("Username")
                login_pass = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Let's Go! 🚀", use_container_width=True, type="primary")
                
                if submitted:
                    if login_user == ADMIN_USER and login_pass == ADMIN_PASS:
                        st.session_state.current_user = {"role": "admin", "name": "The Big Boss"}
                        st.rerun()
                    else:
                        match = emps_df[(emps_df['username'] == login_user) & (emps_df['password'] == login_pass)]
                        if not match.empty:
                            emp = match.iloc[0]
                            st.session_state.current_user = {"role": "employee", "id": emp['id'], "name": emp['name'], "is_phased": False}
                            st.rerun()
                        else:
                            st.error("Nah fam, those details ain't it. Try again. 🤦‍♂️")

# --- 2. ADMIN DASHBOARD ---
elif st.session_state.current_user['role'] == 'admin':
    st.sidebar.title("🛡️ The Command Center")
    
    # NAVIGATION MENU
    admin_view = st.sidebar.radio("Where we heading?", ["🏢 The Hustle Board", "💼 The Bag (Finance)", "✅ Vibe Check (QA)"])
    
    st.sidebar.write("---")
    st.sidebar.subheader("👔 The Squad (HR)")
    with st.sidebar.expander("Add a Hustler ➕"):
        with st.form("add_employee_form"):
            new_emp_name = st.text_input("Full Name")
            new_emp_user = st.text_input("Username")
            new_emp_pass = st.text_input("Password", type="password")
            new_emp_phone = st.text_input("Phone Number", placeholder="e.g. 2547XXXXXXXX")
            new_emp_skills = st.multiselect("What are they good at?", ["Janitorial", "Deep Cleaning", "Babysitting", "Tutoring", "Event Staff", "Moving", "General"])
            if st.form_submit_button("Bring 'em In"):
                if new_emp_name and new_emp_user and new_emp_pass and new_emp_phone:
                    if not emps_df.empty and new_emp_user in emps_df['username'].values:
                        st.error("That username is taken, bro. Pick another one.")
                    else:
                        new_id = f"emp{int(time.time())}"
                        skills_str = ", ".join(new_emp_skills) if new_emp_skills else "General"
                        new_row = pd.DataFrame([{"id": new_id, "name": new_emp_name, "username": new_emp_user, "password": new_emp_pass, "phone": new_emp_phone, "skills": skills_str, "points": 0}])
                        
                        updated_emps_df = pd.concat([emps_df, new_row], ignore_index=True)
                        save_emps(updated_emps_df)
                        
                        st.success("Boom! New comrade added to the squad. 🎉")
                        st.rerun()
                else:
                    st.error("Don't leave fields blank, fill 'em all out!")

    st.sidebar.write("---")
    
    st.sidebar.subheader("👁️ Snoop Mode")
    if not emps_df.empty:
        phase_target = st.sidebar.selectbox("See what a comrade sees:", emps_df['name'].tolist())
        if st.sidebar.button("Go Undercover 🕵️‍♂️", use_container_width=True):
            emp_row = emps_df[emps_df['name'] == phase_target].iloc[0]
            st.session_state.current_user = {
                "role": "employee", 
                "id": emp_row['id'], 
                "name": emp_row['name'],
                "is_phased": True
            }
            st.rerun()

    st.sidebar.write("---")
    if st.sidebar.button("Log Out & Touch Grass 🌿", type="primary", use_container_width=True):
        st.session_state.current_user = None
        st.rerun()

    # ---------------------------------------------------------
    # VIEW 1: OPERATIONS DASHBOARD
    # ---------------------------------------------------------
    if admin_view == "🏢 The Hustle Board":
        st.title("The Hustle Board 🏢")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("➕ Drop a Gig")
            with st.container(border=True):
                with st.form("dispatch_form"):
                    final_title = st.text_input("Gig Name")
                    category = st.selectbox("Category", ["General", "Cleaning", "Janitorial", "Babysitting", "Moving", "Tutoring", "Event Staff"])
                    instructions = st.text_area("The Tea / Instructions 📝 (Optional)")
                    
                    st.write("**⚙️ Who's taking this?**")
                    allocation_mode = st.radio("Routing Method", ["Let the algorithm cook 🍳", "Handpick the squad 🤝"])
                    
                    emp_options = dict(zip(emps_df['name'], emps_df['id'])) if not emps_df.empty else {}
                    
                    if allocation_mode == "Handpick the squad 🤝":
                        selected_squad_names = st.multiselect("👥 Pick the mandem", list(emp_options.keys()))
                        workers_needed = len(selected_squad_names)
                    else:
                        workers_needed = st.number_input("How many hands we need?", min_value=1, step=1, value=1)
                        st.caption("The system will pick the best comrades for the job.")
                        
                    st.write("**🔁 Is this a regular gig?**")
                    is_recurring = st.checkbox("Yeah, make it recurring")
                    recurrence_pattern = ""
                    if is_recurring:
                        recurrence_pattern = st.selectbox("How often?", ["Daily", "Weekly", "Monthly"])
                        st.caption("We'll auto-generate the next one after they get paid.")
                    
                    h_col, r_col = st.columns(2)
                    hours = h_col.number_input("Hours / Person", min_value=0.5, step=0.5, value=1.0)
                    rate = r_col.number_input("Rate / Hr (Ksh)", min_value=0.0, step=10.0, value=150.0)
                    
                    d_col, t_col = st.columns(2)
                    due_date = d_col.date_input("Deadline Date")
                    due_time = t_col.time_input("Deadline Time")
                    
                    submitted = st.form_submit_button("Send it! 🚀", type="primary")
                    
                    if submitted:
                        if final_title == "":
                            st.error("Bruh, you gotta name the gig.")
                        else:
                            exact_time_str = datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S")
                            final_due = f"{due_date} {due_time}"
                            payout_val = hours * rate
                            
                            final_assignees = []
                            if allocation_mode == "Handpick the squad 🤝":
                                if not selected_squad_names:
                                    st.error("You gotta select at least one person, chief.")
                                else:
                                    final_assignees = [emp_options[name] for name in selected_squad_names]
                            else:
                                eligible = emps_df[emps_df['skills'].str.contains(category, case=False, na=False)]
                                if eligible.empty:
                                    st.warning(f"Nobody has '{category}' skills listed. Throwing it to the general pool! 🤷‍♂️")
                                    eligible = emps_df.copy()
                                
                                if not tasks_df.empty:
                                    active_counts = tasks_df[tasks_df['status'].isin(['Pending', 'Confirmed', 'In Progress'])].groupby('employee_Id').size()
                                    eligible['active_tasks'] = eligible['id'].map(active_counts).fillna(0)
                                else:
                                    eligible['active_tasks'] = 0
                                    
                                best_emps = eligible.sort_values(by=['active_tasks', 'points'], ascending=[True, False]).head(workers_needed)
                                final_assignees = best_emps['id'].tolist()
                                
                                if len(final_assignees) < workers_needed:
                                    st.warning("Not enough free hands matching what you need, but assigning who we can! 🏃")

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
                                
                                updated_tasks_df = pd.concat([tasks_df, new_df], ignore_index=True)
                                save_tasks(updated_tasks_df)
                                
                                st.success("Gig successfully dropped! 🎯")
                                st.rerun()

        with col2:
            st.subheader("⚡ Gigs in the Wild")
            active_tasks = tasks_df[tasks_df['status'].isin(['Pending', 'Confirmed', 'In Progress'])] if not tasks_df.empty else pd.DataFrame()
                
            if active_tasks.empty:
                st.info("No active gigs right now. Time to touch grass or scroll TikTok. 📱")
            else:
                for i, task in active_tasks.iloc[::-1].iterrows():
                    if pd.isna(task.get('title')): continue 
                    with st.container(border=True):
                        t_col1, t_col2 = st.columns([3, 1])
                        with t_col1:
                            st.markdown(f"**{task['title']}** ({task.get('category', 'General')})")
                            emp_name = get_employee_name(task['employee_Id']).split(' ')[0]
                            recur_badge = "🔁" if task.get('is_recurring') == "Yes" else ""
                            st.caption(f"👤 Assigned: {emp_name} | 🎯 Deadline: {task.get('due_date', 'N/A')} {recur_badge}")
                        with t_col2:
                            if task['status'] == 'Pending': st.warning("Pending ⏳")
                            elif task['status'] == 'Confirmed': st.success("Locked In ✅")
                            elif task['status'] == 'In Progress': st.info("Cooking 🔄")

        st.write("---")
        st.subheader("🗄️ The Master Ledger (Who's doing what)")
        
        if not tasks_df.empty:
            display_df = tasks_df.copy()
            display_df['Hustler'] = display_df['employee_Id'].apply(get_employee_name)
            display_df['Expected Payout (Ksh) 🤑'] = display_df.get('payout', display_df['hours'] * display_df['rate'])
            display_df = display_df[['id', 'date_assigned', 'due_date', 'time_marked_done', 'title', 'category', 'Hustler', 'hours', 'rate', 'Expected Payout (Ksh) 🤑', 'status']]
            st.dataframe(display_df.sort_values(by="id", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("The ledger is looking pretty empty, boss.")
            
        if st.button("Refresh the Board", type="secondary"):
            fetch_portal_data.clear()
            st.rerun()

    # ---------------------------------------------------------
    # VIEW 1.5: QUALITY CONTROL (APPROVALS & RATING)
    # ---------------------------------------------------------
    elif admin_view == "✅ Vibe Check (QA)":
        st.title("Vibe Check & Approvals ✅")
        st.caption("Check if the comrades actually did the work or if they're capping. Approve the bag or review the mess-ups.")
        
        if tasks_df.empty:
            st.info("Nothing to review right now.")
        else:
            qc_tasks = tasks_df[tasks_df['status'].isin(['Completed', 'Cancelled'])]
            
            if qc_tasks.empty:
                st.info("All review queues are clear. We're chilling. 😎")
            else:
                for i, t in qc_tasks.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        emp_name = get_employee_name(t['employee_Id'])
                        
                        if t['status'] == 'Completed':
                            with c1:
                                st.markdown(f"### ✨ {t['title']}")
                                st.caption(f"**Hustler:** {emp_name} | **Category:** {t.get('category', 'General')} | **Finished At:** {t.get('time_marked_done', 'N/A')}")
                                if t.get('is_recurring') == 'Yes':
                                    st.info(f"🔁 This is a regular gig ({t.get('recurrence_pattern')}). Approving this drops the next one in the queue.")
                                
                                rating = st.slider(f"Rate the Vibe / Quality ({emp_name})", 1, 5, 5, key=f"rate_{t['id']}")
                                st.caption(f"*Approving this gives 'em +{rating * 10} Clout Points.*")
                                
                            with c2:
                                st.markdown("<br><br>", unsafe_allow_html=True)
                                if st.button("Approve & Pay the plug ✅", key=f"apprv_{t['id']}", type="primary", use_container_width=True):
                                    tasks_df.loc[tasks_df['id'] == t['id'], 'status'] = 'Approved'
                                    tasks_df.loc[tasks_df['id'] == t['id'], 'rating'] = str(rating)
                                    
                                    emp_idx = emps_df.index[emps_df['id'] == str(t['employee_Id'])].tolist()[0]
                                    curr_pts = int(emps_df.at[emp_idx, 'points']) if pd.notna(emps_df.at[emp_idx, 'points']) else 0
                                    emps_df.at[emp_idx, 'points'] = curr_pts + (rating * 10)
                                    save_emps(emps_df)
                                    
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
                                            for key in ['msg_allocated', 'msg_night_before', 'msg_1hr_before', 'msg_late', 'msg_admin_cancelled', 'msg_admin_completed', 'time_marked_done', 'rating']:
                                                next_task[key] = ""
                                            
                                            updated_tasks_df = pd.concat([tasks_df, pd.DataFrame([next_task])], ignore_index=True)
                                            save_tasks(updated_tasks_df)
                                        except Exception as e:
                                            save_tasks(tasks_df) 
                                            st.error(f"Math ain't mathing for the recurrence schedule: {e}")
                                    else:
                                        save_tasks(tasks_df)

                                    st.success(f"Gig Verified! Sent to the payroll queue. 💸")
                                    time.sleep(1)
                                    st.rerun()

                        elif t['status'] == 'Cancelled':
                            with c1:
                                st.markdown(f"### 🚩 {t['title']} (Dropped the ball)")
                                st.caption(f"**Hustler:** {emp_name} | **Category:** {t.get('category', 'General')} | **Assigned:** {t.get('date_assigned', 'N/A')}")
                                
                                reason = t.get('cancel_reason', '')
                                if not reason: reason = "Ghosted without a word."
                                st.error(f"**Their Excuse:**\n{reason}")
                                st.info("FYI: The system is trying to pass this gig to someone else so the bag doesn't fumble.")
                                
                            with c2:
                                st.markdown("<br><br>", unsafe_allow_html=True)
                                if st.button("Acknowledge & Archive 🚮", key=f"ack_{t['id']}", use_container_width=True):
                                    tasks_df.loc[tasks_df['id'] == t['id'], 'status'] = 'Cancelled (Reviewed)'
                                    save_tasks(tasks_df)
                                    st.success("Archived! We move. 🏃‍♂️")
                                    time.sleep(1)
                                    st.rerun()

    # ---------------------------------------------------------
    # VIEW 2: FINANCE & ANALYTICS
    # ---------------------------------------------------------
    elif admin_view == "💼 The Bag (Finance)":
        st.title("The Bag Manager 💼")
        st.caption("Track the mullah coming in, pay the mandem, and see the profits.")
        
        total_income = acct_df[acct_df['type'] == 'Income']['amount'].sum() if not acct_df.empty else 0.0
        total_payroll_cleared = acct_df[acct_df['type'] == 'Expense']['amount'].sum() if not acct_df.empty else 0.0
        gross_profit = total_income - total_payroll_cleared
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Mullah In (Ksh)", f"{total_income:,.2f}")
        m2.metric("Money Out (Ksh)", f"{total_payroll_cleared:,.2f}")
        m3.metric("Profit / The Real Bag 🤑", f"{gross_profit:,.2f}", delta="We up!" if gross_profit > 0 else None)
        
        st.write("---")

        st.subheader("🧮 Client Billing Calculator")
        st.caption("Quick maths to see what we should charge the clients.")
        
        with st.container(border=True):
            q_col1, q_col2, q_col3 = st.columns(3)
            with q_col1:
                est_workers = st.number_input("How many comrades needed?", min_value=1, value=2)
                est_hours = st.number_input("Estimated Hours per Person", min_value=0.5, step=0.5, value=4.0)
            with q_col2:
                worker_rate = st.number_input("Base Pay (Ksh/hr)", min_value=50.0, step=10.0, value=150.0)
                target_margin = st.slider("Our Cut / Profit Margin (%)", min_value=10, max_value=100, value=40, step=5)
            
            total_worker_cost = est_workers * est_hours * worker_rate
            markup_multiplier = 1 + (target_margin / 100.0)
            recommended_total_bill = total_worker_cost * markup_multiplier
            projected_profit = recommended_total_bill - total_worker_cost
            recommended_hourly_bill = recommended_total_bill / (est_workers * est_hours) if (est_workers * est_hours) > 0 else 0

            with q_col3:
                st.info(f"**What we pay the team:** Ksh {total_worker_cost:,.2f}")
                st.success(f"**What to invoice the client:** Ksh {recommended_total_bill:,.2f}")
                st.metric("Our Cut (Profit)", f"Ksh {projected_profit:,.2f}")
                st.caption(f"Charge 'em: Ksh {recommended_hourly_bill:,.2f} / hr per comrade")

        st.write("---")
        
        colA, colB = st.columns([1, 1])
        
        with colA:
            st.subheader("📥 Log New Income")
            st.caption("Did a client pay up? Log the bag here.")
            with st.container(border=True):
                with st.form("income_form"):
                    inc_desc = st.text_input("Where's the money from?", placeholder="e.g., Kileleshwa Moving Gig")
                    inc_amount = st.number_input("Amount (Ksh)", min_value=0.0, step=500.0)
                    
                    if st.form_submit_button("Secure the Bag 💰", type="primary"):
                        if inc_desc and inc_amount > 0:
                            new_tx = pd.DataFrame([{
                                "tx_id": f"TX-INC-{int(time.time())}",
                                "date": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                                "type": "Income",
                                "description": inc_desc,
                                "amount": inc_amount,
                                "status": "Pending", 
                                "details": ""
                            }])
                            
                            updated_acct_df = pd.concat([acct_df, new_tx], ignore_index=True)
                            save_acct(updated_acct_df)
                            
                            st.success("Money logged! We eating good tonight. 🍗")
                            st.rerun()
                        else:
                            st.error("Bruh, fill it out properly.")

        with colB:
            st.subheader("🧾 Pay the Mandem")
            st.caption("See who's waiting on their chapaa.")
            
            unpaid_tasks = tasks_df[tasks_df['status'] == 'Approved'].copy() if not tasks_df.empty else pd.DataFrame()
            
            if unpaid_tasks.empty:
                st.info("Nobody owes nobody. Everyone is paid up! 🥳")
            else:
                unpaid_tasks['payout'] = pd.to_numeric(unpaid_tasks['payout'], errors='coerce')
                payroll_summary = unpaid_tasks.groupby('employee_Id')['payout'].sum().reset_index()
                
                payroll_report = payroll_summary.merge(emps_df[['id', 'name', 'phone']], left_on='employee_Id', right_on='id')
                payroll_report = payroll_report[['name', 'payout']]
                payroll_report.columns = ['Hustler Name', 'Owed (Ksh)']
                
                total_liability = payroll_report['Owed (Ksh)'].sum()
                st.metric("Total Cash to Send Out", f"Ksh {total_liability:,.2f}")
                st.dataframe(payroll_report, use_container_width=True, hide_index=True)
                
                if st.button("Hit Send on M-PESA / Pay All", type="primary", use_container_width=True):
                    with st.spinner("Crunching the numbers..."):
                        
                        details_list = [f"{row['Hustler Name']}: Ksh {row['Owed (Ksh)']}" for _, row in payroll_report.iterrows()]
                        details_str = " | ".join(details_list)
                        
                        tasks_df.loc[tasks_df['status'] == 'Approved', 'status'] = 'Paid'
                        save_tasks(tasks_df)
                        
                        new_tx = pd.DataFrame([{
                            "tx_id": f"TX-PAY-{int(time.time())}",
                            "date": datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                            "type": "Expense",
                            "description": "Mass Payroll Drop",
                            "amount": total_liability,
                            "status": "Pending", 
                            "details": details_str
                        }])
                        
                        updated_acct_df = pd.concat([acct_df, new_tx], ignore_index=True)
                        save_acct(updated_acct_df)
                        
                    st.success("Payroll logged! Don't forget to actually send the money. 😂")
                    st.rerun()

        st.write("---")
        st.subheader("📚 The Receipts")
        st.caption("Check the ledger. Mark 'em as Cleared once the money has officially moved.")
        
        if not acct_df.empty:
            for i, tx in acct_df.sort_values(by="date", ascending=False).iterrows():
                status_emoji = "⏳" if tx.get('status', 'Pending') == "Pending" else "✅"
                with st.expander(f"{status_emoji} {tx['date'][:10]} | {tx['tx_id']} | {tx['type']} | Ksh {tx['amount']:,.2f}"):
                    st.write(f"**What was it:** {tx['description']}")
                    
                    if pd.notna(tx.get('details')) and str(tx.get('details')).strip() != "":
                        st.markdown("**Who got paid:**")
                        for detail in str(tx['details']).split(" | "):
                            st.caption(f"🔹 {detail}")
                            
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    current_status = tx.get('status', 'Pending')
                    new_status = st.selectbox(
                        "Status", 
                        ["Pending", "Cleared"], 
                        index=0 if current_status == "Pending" else 1, 
                        key=f"status_{tx['tx_id']}"
                    )
                    
                    if new_status != current_status:
                        acct_df.at[i, 'status'] = new_status
                        save_acct(acct_df)
                        st.success(f"Status changed to {new_status}. We move!")
                        time.sleep(0.5)
                        st.rerun()
        else:
            st.info("No receipts yet. It's too quiet in here.")

# --- 3. EMPLOYEE DASHBOARD ---
elif st.session_state.current_user['role'] == 'employee':
    user_id = str(st.session_state.current_user['id'])
    user_name = st.session_state.current_user['name']
    is_phased = st.session_state.current_user.get('is_phased', False)
    
    my_emp_row = emps_df[emps_df['id'] == user_id].iloc[0] if not emps_df.empty else None
    my_points = my_emp_row['points'] if my_emp_row is not None else 0
    my_skills = my_emp_row['skills'].split(', ') if my_emp_row is not None and pd.notna(my_emp_row['skills']) else ["General"]
    
    st.sidebar.title("👤 My Vibe")
    st.sidebar.write(f"Wagwan,\n**{user_name}**! 🚀")
    st.sidebar.write("---")
    
    with st.sidebar.expander("🛠️ Update My Skills"):
        st.caption("Don't cap, what are you actually good at?")
        available_skills = ["General", "Cleaning", "Janitorial", "Babysitting", "Moving", "Tutoring", "Event Staff"]
        new_skills = st.multiselect("My skills", available_skills, default=[s for s in my_skills if s in available_skills])
        if st.button("Save Skills"):
            skills_str = ", ".join(new_skills) if new_skills else "General"
            emp_idx = emps_df.index[emps_df['id'] == user_id].tolist()[0]
            emps_df.at[emp_idx, 'skills'] = skills_str
            save_emps(emps_df)
            st.success("Profile updated! Stay on the grind. 💯")
            st.rerun()

    st.sidebar.write("---")
    wa_url = f"https://wa.me/{SUPPORT_NUMBER}?text=Yo%20Admin,%20need%20some%20help%20here:%20"
    st.sidebar.link_button("💬 Holla at Admin", wa_url, use_container_width=True)
    st.sidebar.write("---")
    
    if is_phased:
        st.sidebar.warning("👀 SNOOP MODE ON")
        if st.sidebar.button("Back to Big Boss View", type="primary", use_container_width=True):
            st.session_state.current_user = {"role": "admin", "name": "The Big Boss"}
            st.rerun()
    else:
        if st.sidebar.button("Log Out", type="primary", use_container_width=True):
            st.session_state.current_user = None
            st.rerun()

    if not tasks_df.empty:
        tasks_df['employee_Id'] = tasks_df['employee_Id'].astype(str)
        my_tasks = tasks_df[tasks_df['employee_Id'] == user_id]
        total_earned = sum(float(t.get('payout', float(t['hours']) * float(t['rate']))) for _, t in my_tasks.iterrows() if t['status'] == 'Paid')
        pending_balance = sum(float(t.get('payout', float(t['hours']) * float(t['rate']))) for _, t in my_tasks.iterrows() if t['status'] in ['Pending', 'Confirmed', 'In Progress', 'Completed', 'Approved'])
    else:
        my_tasks, total_earned, pending_balance = pd.DataFrame(), 0, 0

    st.subheader("My Stats 📊")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Bag Secured 💰", f"Ksh {total_earned}")
    c2.metric("Pending Chapaa ⏳", f"Ksh {pending_balance}")
    c3.metric("Clout Points 🌟", f"{my_points} pts")
    
    st.write("---")
    st.subheader("🏃 My Active Gigs")
    
    if st.button("Refresh Page", type="secondary"):
        fetch_portal_data.clear()
        st.rerun()
    
    if my_tasks.empty:
        st.info("No gigs right now. Sit tight or go touch grass. 🌿")
    else:
        for i, task in my_tasks.iterrows():
            if pd.isna(task.get('title')): continue
            
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    st.markdown(f"### {task['title']}")
                    if task.get('instructions'): st.info(f"**📝 The Tea / Instructions:**\n\n{task['instructions']}")
                    
                    date_str = task.get('date_assigned', 'Unknown Date')
                    due_str = task.get('due_date', 'N/A')
                    payout_val = task.get('payout', float(task['hours']) * float(task['rate']))
                    st.caption(f"🕒 Dropped on: {date_str} | 🎯 Deadline: {due_str} | Hustle: {task['hours']} hrs @ Ksh {task['rate']}/hr  => **The Bag: Ksh {payout_val}**")

                with colB:
                    if task['status'] == 'Pending':
                        if st.button("I'm on it! ✅", key=f"confirm_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Confirmed'
                            with st.spinner("Locking it in..."):
                                save_tasks(tasks_df)
                            st.rerun()
                            
                        with st.expander("Pass / I can't ❌"):
                            st.caption("Spill the tea. Why are you dodging this gig?")
                            reason = st.text_area("Reason:", key=f"reason_{task['id']}")
                            if st.button("Nah, I'm out", key=f"cancel_btn_{task['id']}", type="primary"):
                                if not reason.strip():
                                    st.error("You gotta give a reason, bro. Don't just ghost.")
                                else:
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Cancelled'
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'cancel_reason'] = reason
                                    
                                    task_cat = task.get('category', 'General')
                                    eligible_pool = emps_df[(emps_df['id'] != user_id) & (emps_df['skills'].str.contains(task_cat, case=False, na=False))]
                                    if eligible_pool.empty:
                                        eligible_pool = emps_df[emps_df['id'] != user_id]
                                        
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
                                    
                                    with st.spinner("Passing the baton..."):
                                        save_tasks(updated_tasks_df)
                                    st.session_state[f"wa_reason_{task['id']}"] = reason
                                    st.rerun()
                                    
                    elif task['status'] == 'Confirmed':
                        if st.button("Let's get this bread 🏃", key=f"start_{task['id']}", type="secondary"):
                            allowed_to_start = True
                            if due_str:
                                try:
                                    task_due_time = KISUMU_TZ.localize(datetime.strptime(due_str, "%Y-%m-%d %H:%M:%S"))
                                    now_eat = datetime.now(KISUMU_TZ)
                                    time_diff = task_due_time - now_eat
                                    
                                    if time_diff > timedelta(hours=1):
                                        allowed_to_start = False
                                        wait_time = time_diff - timedelta(hours=1)
                                        hours_wait = int(wait_time.total_seconds() // 3600)
                                        mins_wait = int((wait_time.total_seconds() % 3600) // 60)
                                        
                                        st.error(f"🛑 Hold your horses! You can only start 1 hour before the deadline. Chill for another {hours_wait}h {mins_wait}m.")
                                except Exception as e:
                                    pass 
                            
                            if allowed_to_start:
                                tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'In Progress'
                                with st.spinner("Status: Cooking 🍳"):
                                    save_tasks(tasks_df)
                                st.rerun()
                            
                        with st.expander("I gotta bounce 🚫"):
                            st.caption("Tell us why you're bailing on a gig you already took.")
                            reason = st.text_area("Reason:", key=f"reason_{task['id']}")
                            if st.button("Bail Out", key=f"cancel_btn2_{task['id']}", type="primary"):
                                if not reason.strip():
                                    st.error("No reason? That's a red card. Type something!")
                                else:
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Cancelled'
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'cancel_reason'] = reason
                                    
                                    task_cat = task.get('category', 'General')
                                    eligible_pool = emps_df[(emps_df['id'] != user_id) & (emps_df['skills'].str.contains(task_cat, case=False, na=False))]
                                    if eligible_pool.empty:
                                        eligible_pool = emps_df[emps_df['id'] != user_id]
                                        
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

                                    with st.spinner("Re-routing to another comrade..."):
                                        save_tasks(updated_tasks_df)
                                    st.session_state[f"wa_reason_{task['id']}"] = reason
                                    st.rerun()

                    elif task['status'] == 'In Progress':
                        if st.button("Finished the Gig ✔️", key=f"done_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Completed'
                            tasks_df.loc[tasks_df['id'] == task['id'], 'time_marked_done'] = datetime.now(KISUMU_TZ).strftime("%Y-%m-%d %H:%M:%S")
                            with st.spinner("Sending proof to the Big Boss..."):
                                save_tasks(tasks_df)
                            st.rerun()
                        with st.expander("Bro, I messed up 🚩"):
                            st.caption("Did you get lost in the sauce? Tell us what went wrong.")
                            reason = st.text_area("Reason:", key=f"reason_abort_{task['id']}")
                            if st.button("Abort Mission", key=f"abscond_{task['id']}"):
                                if not reason.strip():
                                    st.error("You can't just quit without an explanation. Spill it.")
                                else:
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Cancelled'
                                    tasks_df.loc[tasks_df['id'] == task['id'], 'cancel_reason'] = reason
                                    
                                    with st.spinner("Shutting it down..."):
                                        save_tasks(tasks_df)
                                    st.session_state[f"wa_reason_{task['id']}"] = reason
                                    st.rerun()
                                    
                    elif task['status'] == 'Completed':
                        st.warning("Waiting for the Boss to vibe-check this ⏳")
                    elif task['status'] == 'Approved':
                        st.info("Verified! ✨ The bag is on its way. 💸")
                    elif task['status'] == 'Paid':
                        st.success(f"Paid! ✅ | Clout Metric: {task.get('rating', '5')} / 5 ⭐")
                    elif task['status'] in ['Cancelled', 'Absconded', 'Cancelled (Reviewed)']:
                        st.error("Gig Cancelled 🚩")
                        
                        reason_text = st.session_state.get(f"wa_reason_{task['id']}", task.get('cancel_reason', ''))
                        if reason_text:
                            encoded_msg = urllib.parse.quote(f"🚨 *Bro, we have a situation*\\n*Who:* {user_name}\\n*Gig:* {task['title']}\\n*The Tea:* {reason_text}")
                            wa_url = f"https://wa.me/{SUPPORT_NUMBER}?text={encoded_msg}"
                            st.link_button("📲 Explain yourself to the Big Boss on WhatsApp", wa_url)
