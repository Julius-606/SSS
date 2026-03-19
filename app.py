import streamlit as st
import pandas as pd
import requests
import json
import time
from streamlit_gsheets import GSheetsConnection

# --- CONFIG & MOCK DB ---
st.set_page_config(page_title="SSS Portal OS", layout="wide", page_icon="✨")

API_KEY = "" # Your Gemini API Key goes here!

EMPLOYEES = [
    {"id": "emp1", "name": "Wanjiku (Nanny Pro)"},
    {"id": "emp2", "name": "Ochieng (Deep Cleaner)"},
    {"id": "emp3", "name": "Amina (Catering Whiz)"},
    {"id": "emp4", "name": "Kevo (Heavy Lifting)"},
    {"id": "emp5", "name": "Kamaa (Emergency Plumber)"},
    {"id": "emp6", "name": "Njeri (Math Tutor)"},
    {"id": "emp7", "name": "Brian (Tech Support/WIFI Guy)"},
    {"id": "emp8", "name": "Stacy (Event Usher)"}
]

# --- GOOGLE SHEETS CONNECTION ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    tasks_df = conn.read(worksheet="Tasks", ttl=0) # ttl=0 keeps data fresh, no lagging indicators
    tasks_df = tasks_df.dropna(how="all") # Drop completely empty rows
except Exception as e:
    # Fallback to empty dataframe so the UI doesn't crash while you setup secrets
    tasks_df = pd.DataFrame(columns=["id", "title", "employeeId", "hours", "rate", "status"])
    st.error("📉 Database Margin Call! Connect your Google Sheet in Secrets.")

# Initialize Session State
if 'current_user' not in st.session_state:
    st.session_state.current_user = None
if 'ai_draft' not in st.session_state:
    st.session_state.ai_draft = {"title": "", "hours": 1.0, "rate": 300.0}

# --- HELPER FUNCTIONS ---
def get_employee_name(emp_id):
    for emp in EMPLOYEES:
        if emp['id'] == emp_id:
            return emp['name']
    return "Unknown Hustler"

def ai_estimate(task_idea):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": f"Based on this basic task idea: '{task_idea}', provide a more professional task title, an estimate of hours needed per person (0.5 to 10), and a reasonable hourly rate in Kenyan Shillings (Ksh 100 to 1000) for a student worker."}]}],
        "systemInstruction": {"parts": [{"text": "You are an AI assistant for a student services platform in Kenya."}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "suggestedTitle": {"type": "STRING"},
                    "suggestedHours": {"type": "NUMBER"},
                    "suggestedRate": {"type": "NUMBER"}
                }
            }
        }
    }
    try:
        res = requests.post(url, json=payload)
        data = res.json()
        result = json.loads(data['candidates'][0]['content']['parts'][0]['text'])
        return result
    except Exception as e:
        st.error(f"AI Hit Stop-Loss: {e}")
        return None

def ai_tips(task_title):
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
        return "Failed to load tips. Trust your instincts and secure the bag! ✨"

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
        
        emp_names = [e['name'] for e in EMPLOYEES]
        selected_emp = st.selectbox("Select your profile", emp_names)
        if st.button("👤 Login as Employee", use_container_width=True):
            emp_obj = next(e for e in EMPLOYEES if e['name'] == selected_emp)
            st.session_state.current_user = {"role": "employee", **emp_obj}
            st.rerun()

# --- ADMIN DASHBOARD ---
elif st.session_state.current_user['role'] == 'admin':
    st.sidebar.title("🛡️ Admin Command Center")
    st.sidebar.write("Managing the SSS Prop Firm.")
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
                
                # SQUAD MODE - Streamlit multiselect is built for this!
                emp_options = {e['name']: e['id'] for e in EMPLOYEES}
                selected_squad_names = st.multiselect("👥 Build the Syndicate", list(emp_options.keys()))
                
                h_col, r_col = st.columns(2)
                hours = h_col.number_input("Hours / Person", min_value=0.5, step=0.5, value=1.0)
                rate = r_col.number_input("Rate / Hr (Ksh)", min_value=50.0, step=10.0, value=300.0)
                
                submitted = st.form_submit_button("🚀 Dispatch to Squad", type="primary")
                
                if submitted:
                    if not selected_squad_names:
                        st.error("⚠️ Pick at least one hustler bro, don't leave the gig hanging.")
                    else:
                        new_rows = []
                        for name in selected_squad_names:
                            emp_id = emp_options[name]
                            new_rows.append({
                                "id": int(time.time() * 1000) + hash(emp_id) % 1000,
                                "title": final_title,
                                "employeeId": emp_id,
                                "hours": hours,
                                "rate": rate,
                                "status": "Pending"
                            })
                        
                        new_df = pd.DataFrame(new_rows)
                        updated_df = pd.concat([tasks_df, new_df], ignore_index=True)
                        conn.update(worksheet="Tasks", data=updated_df)
                        
                        st.success(f"Dispatched to {len(selected_squad_names)} hustlers!")
                        st.rerun()

    # Right Col: Task List
    with col2:
        st.subheader("📈 Active & Settled Gigs")
        if tasks_df.empty:
            st.info("The dashboard is looking as empty as a blown Forex account. Time to dish out some jobs!")
        else:
            for i, task in tasks_df.iloc[::-1].iterrows():
                with st.container(border=True):
                    t_col1, t_col2 = st.columns([3, 1])
                    with t_col1:
                        st.markdown(f"**{task['title']}**")
                        emp_name = get_employee_name(task['employeeId']).split(' ')[0]
                        st.caption(f"👤 {emp_name} | ⏳ {task['hours']}h | 💵 Ksh {task['rate']}/h")
                    with t_col2:
                        st.markdown(f"**Ksh {float(task['hours']) * float(task['rate'])}**")
                        
                        if task['status'] == 'Pending':
                            st.warning("Cooking ⏳")
                        elif task['status'] == 'In Progress':
                            st.info("Grinding 🏃")
                        elif task['status'] == 'Completed':
                            if st.button("Mark Paid 💸", key=f"pay_{task['id']}"):
                                tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Paid'
                                conn.update(worksheet="Tasks", data=tasks_df)
                                st.rerun()
                        elif task['status'] == 'Paid':
                            st.success("Settled ✅")
                        elif task['status'] == 'Absconded':
                            st.error("MIA 🚩")

# --- EMPLOYEE DASHBOARD ---
elif st.session_state.current_user['role'] == 'employee':
    user_id = st.session_state.current_user['id']
    user_name = st.session_state.current_user['name']
    
    st.sidebar.title("👤 My Profile")
    st.sidebar.write(f"Welcome to the trenches, **{user_name}**.")
    if st.sidebar.button("Go Ghost (Logout)"):
        st.session_state.current_user = None
        st.rerun()

    my_tasks = tasks_df[tasks_df['employeeId'] == user_id]
    
    # Calculate P/L using float conversion in case Google Sheets sends strings
    total_earned = sum(float(t['hours']) * float(t['rate']) for _, t in my_tasks.iterrows() if t['status'] == 'Paid')
    pending_bag = sum(float(t['hours']) * float(t['rate']) for _, t in my_tasks.iterrows() if t['status'] in ['Pending', 'In Progress', 'Completed'])

    # Stats Cards
    c1, c2 = st.columns(2)
    c1.metric("💵 Secured Bag (TP Hit)", f"Ksh {total_earned}")
    c2.metric("📉 Floating P/L", f"Ksh {pending_bag}")
    
    st.write("---")
    st.subheader("💼 My Hitlist")
    
    if my_tasks.empty:
        st.info("No tasks assigned. You're officially off the clock. Go trade some London Session. 📉")
    else:
        for i, task in my_tasks.iloc[::-1].iterrows():
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    st.markdown(f"### {task['title']}")
                    st.caption(f"Allocated: {task['hours']} hrs @ Ksh {task['rate']}/hr  => **Target TP: Ksh {float(task['hours']) * float(task['rate'])}**")
                    
                    if st.button("✨ AI Hack (Pro Tips)", key=f"tip_{task['id']}"):
                        with st.spinner("Consulting the Thika algorithms..."):
                            tips = ai_tips(task['title'])
                            st.info(tips)

                with colB:
                    if task['status'] == 'Pending':
                        if st.button("Start Gig 🏃", key=f"start_{task['id']}", type="secondary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'In Progress'
                            conn.update(worksheet="Tasks", data=tasks_df)
                            st.rerun()
                    elif task['status'] == 'In Progress':
                        if st.button("Mark Done ✔️", key=f"done_{task['id']}", type="primary"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Completed'
                            conn.update(worksheet="Tasks", data=tasks_df)
                            st.rerun()
                        if st.button("Absconded 🏃‍♂️💨", key=f"abscond_{task['id']}"):
                            tasks_df.loc[tasks_df['id'] == task['id'], 'status'] = 'Absconded'
                            conn.update(worksheet="Tasks", data=tasks_df)
                            st.rerun()
                    elif task['status'] == 'Completed':
                        st.warning("Awaiting Funds ⏳")
                    elif task['status'] == 'Paid':
                        st.success("Paid ✅")
                    elif task['status'] == 'Absconded':
                        st.error("Account Blown 🚩")
