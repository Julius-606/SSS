import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.set_page_config(page_title="Task Tracker OS", layout="wide")

st.title("🚀 Task Tracker Dashboard")
st.markdown("Syncing live with your Google Spreadsheet")

# Create connection
conn = st.connection("gsheets", type=GSheetsConnection)

# Fetch existing data
# Replace 'spreadsheet_url' with your actual link if not using secrets
df = conn.read(worksheet="Sheet1") 

# --- SIDEBAR: ADD NEW TASK ---
st.sidebar.header("📝 Add New Task")
with st.sidebar.form(key="task_form"):
    task_id = st.text_input("Task ID")
    description = st.text_area("Task Description")
    assigned_to = st.selectbox("Assigned To", ["Finya", "Orbit", "Team Member"])
    date_assigned = st.date_input("Date Assigned")
    time_allocated = st.text_input("Time Allocated (e.g., 2hrs)")
    deadline = st.date_input("Deadline")
    status = st.selectbox("Status", ["Backlog", "In Progress", "Review", "Done"])
    notes = st.text_input("Notes")
    
    submit_button = st.form_submit_button(label="Update Spreadsheet")

if submit_button:
    # Create new row
    new_data = pd.DataFrame([{
        "Task ID": task_id,
        "Task description": description,
        "assigned to": assigned_to,
        "date assigned": str(date_assigned),
        "time allocated": time_allocated,
        "deadline": str(deadline),
        "status": status,
        "Notes": notes
    }])
    
    # Append and update
    updated_df = pd.concat([df, new_data], ignore_index=True)
    conn.update(worksheet="Sheet1", data=updated_df)
    st.success("Spreadsheet updated! Manifesting productivity for you. ✨")
    st.balloons()

# --- MAIN AREA: DISPLAY TASKS ---
st.subheader("Current Sprint")
st.dataframe(df, use_container_width=True)

# Quick Filter for Status
status_filter = st.multiselect("Filter by Status", options=df["status"].unique(), default=df["status"].unique())
filtered_df = df[df["status"].isin(status_filter)]
st.table(filtered_df)
