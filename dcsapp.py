import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import openai
import os
import json

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Dairy Consulting Interview Simulator",
    page_icon="🐄",
    layout="wide"
)

# --- DATABASE INITIALIZATION (SQLite) ---
DB_FILE = "simulator_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table for student logins
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            student_id TEXT NOT NULL UNIQUE,
            section TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for logging chat interactions
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            farm_scenario TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for instructor settings (visibility toggles, scenarios)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- DATABASE HELPER FUNCTIONS ---
def register_or_login_student(name, student_id, section):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO students (name, student_id, section) VALUES (?, ?, ?)",
                  (name, student_id, section))
        conn.commit()
    finally:
        conn.close()

def log_chat_message(student_id, student_name, farm_scenario, role, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO chat_logs (student_id, student_name, farm_scenario, role, message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (student_id, student_name, farm_scenario, role, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_student_list():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT DISTINCT student_id, name, section FROM students ORDER BY name ASC", conn)
    conn.close()
    return df

def get_student_logs(student_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT timestamp, farm_scenario, role, message FROM chat_logs WHERE student_id = ? ORDER BY id ASC", conn, params=(student_id,))
    conn.close()
    return df

def get_all_logs_df():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT timestamp, student_id, student_name, farm_scenario, role, message FROM chat_logs ORDER BY id ASC", conn)
    conn.close()
    return df

# --- DEFAULT SCENARIO DATABASE ---
DEFAULT_FARMS = {
    "Salfer Dairy (Scenario 1)": {
        "name": "Salfer Dairy",
        "location": "Central Minnesota",
        "owner": "Dan Salfer (Owner-Operator)",
        "herd_size": "500 lactating Holsteins (100% Holstein)",
        "facility": "6-row freestall barn, deep-bedded sand stalls, natural curtain ventilation",
        "milking_system": "Double-12 Parallel Parlor (No robots)",
        "milking_freq": "3x per day (6:00 AM, 2:00 PM, 10:00 PM)",
        "economics": {
            "milk_price": "$20.50 / cwt",
            "crop_acres": "1,200 acres",
            "feed_ratio": "75% Grown / 25% Purchased"
        },
        "dhia_summary": {
            "rha": "26,500 lbs Milk",
            "scc_average": "280,000 cells/mL (Linear Score 2nd+ Lactation > 4.0)",
            "preg_rate": "15% (Goal: 20%+)",
            "cull_rate": "34% (Primary reasons: Mastitis & Repro failure)"
        },
        "financials": {
            "gross_revenue": "$2,716,250",
            "feed_cost": "$1,120,000",
            "labor_cost": "$280,000",
            "vet_med_cost": "$62,000",
            "net_farm_income": "$345,000",
            "total_assets": "$6,800,000",
            "total_liabilities": "$2,400,000",
            "owner_equity": "$4,400,000",
            "dscr": "1.35"
        },
        "persona_prompt": """
You are Dan Salfer, the owner-operator of Salfer Dairy, a 500-cow Holstein farm in Central Minnesota.
You are being interviewed by a student dairy consultant.

YOUR PERSONALITY & DEMEANOR:
- Proud, hardworking, practical, and deeply committed to your herd.
- Stretched thin between managing 1,200 acres of crops and overseeing 4 hired labor staff.
- Skeptical of outside consultants who immediately tell you what to do without understanding your daily labor realities.
- Defensive if challenged directly or accused of poor management (e.g., if a student says "Your prep routine is bad").

HIDDEN OPERATIONAL REALITIES (ONLY REVEAL IF ASKED THOUGHTFUL, SOCRATIC QUESTIONS):
1. SCC / Udder Health Issue:
   - If asked about night shift routine or parlor auditing: Reveal that during the 10:00 PM night milking, the hired night crew cuts pre-dip contact time to 10-15 seconds (instead of 45-60) to finish their shift early.
2. Reproduction Issue:
   - If asked how crop work aligns with herd health schedules: Reveal that during spring planting and fall harvest, Timed-AI / OvSynch injections frequently get delayed by 24-48 hours because you are in the tractor all day.

RULES FOR INTERACTION:
- Stay strictly in character at all times. Do NOT break character.
- Do NOT volunteer the hidden root causes right away. The student MUST earn the information by asking specific, respectful, diagnostic questions about routines, schedules, and labor.
- Keep responses conversational, natural, and realistic for a busy dairy farmer (2 to 4 sentences per response).
"""
    }
}

# Session state initialization for settings
if "show_dhia" not in st.session_state:
    st.session_state.show_dhia = True
if "show_financials" not in st.session_state:
    st.session_state.show_financials = True
if "is_instructor" not in st.session_state:
    st.session_state.is_instructor = False
if "student_user" not in st.session_state:
    st.session_state.student_user = None

# --- HEADER ---
st.title("🐄 Dairy Consulting Interview Simulator")
st.markdown("*Practice Socratic interviewing, diagnostic investigation, and herd evaluation with simulated farm managers.*")

# --- SIDEBAR: AUTHENTICATION & INSTRUCTOR CONTROLS ---
st.sidebar.header("⚙️ Navigation & Settings")

# Instructor Login Section
with st.sidebar.expander("🔒 Instructor Login", expanded=False):
    admin_password = st.text_input("Instructor Password:", type="password", key="pwd_input")
    if st.button("Login as Instructor"):
        if admin_password == "dairy123":
            st.session_state.is_instructor = True
            st.success("Authenticated as Instructor!")
        else:
            st.error("Incorrect Password.")

if st.session_state.is_instructor:
    st.sidebar.success("🟢 Logged in as Instructor")
    if st.sidebar.button("Logout Instructor"):
        st.session_state.is_instructor = False
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("API Configuration")
api_key = st.sidebar.text_input("OpenAI API Key:", type="password", help="Enter OpenAI API key for live AI conversations.")

# --- STUDENT REGISTRATION / SIGN-IN SCREEN ---
if not st.session_state.student_user and not st.session_state.is_instructor:
    st.info("👋 **Welcome Students!** Please sign in below before starting your consulting simulation.")
    
    with st.form("student_signin_form"):
        st.subheader("Student Sign-In / Account Creation")
        col_a, col_b = st.columns(2)
        with col_a:
            s_name = st.text_input("Full Name (First & Last):")
            s_id = st.text_input("Student ID Number:")
        with col_b:
            s_section = st.text_input("Class Section / Semester (e.g., ANSC 401 - Fall):")
        
        submit_btn = st.form_submit_button("Start Interview Simulation")
        
        if submit_btn:
            if s_name and s_id:
                register_or_login_student(s_name, s_id, s_section)
                st.session_state.student_user = {
                    "name": s_name,
                    "id": s_id,
                    "section": s_section
                }
                st.success(f"Welcome, {s_name}! Loading simulation...")
                st.rerun()
            else:
                st.error("Please provide both your Name and Student ID Number.")

# --- MAIN SIMULATOR INTERFACE (AFTER STUDENT SIGN-IN OR INSTRUCTOR LOGIN) ---
if st.session_state.student_user or st.session_state.is_instructor:
    
    # Header Banner showing logged in status
    if st.session_state.student_user:
        st.sidebar.markdown(f"👤 **Student:** {st.session_state.student_user['name']}")
        st.sidebar.markdown(f"🆔 **ID:** {st.session_state.student_user['id']}")
        if st.sidebar.button("Sign Out Student"):
            st.session_state.student_user = None
            st.session_state.messages = []
            st.rerun()

    # Scenario Selection
    st.sidebar.subheader("Farm Selection")
    selected_farm_key = st.sidebar.selectbox("Select Farm Scenario:", list(DEFAULT_FARMS.keys()))
    farm_data = DEFAULT_FARMS[selected_farm_key]

    # --- TAB NAVIGATION ---
    tab_list = []
    if st.session_state.show_dhia or st.session_state.is_instructor:
        tab_list.append("📊 DHIA 302 Herd Summary")
    if st.session_state.show_financials or st.session_state.is_instructor:
        tab_list.append("📈 Financial Statements")
    
    tab_list.append("💬 Producer Interview Chat")
    
    if st.session_state.is_instructor:
        tab_list.append("🔒 Instructor Admin Panel")

    tabs = st.tabs(tab_list)
    tab_idx = 0

    # TAB: DHIA 302 REPORT
    if st.session_state.show_dhia or st.session_state.is_instructor:
        with tabs[tab_idx]:
            st.header(f"DHIA 302 Herd Summary: {farm_data['name']}")
            if not st.session_state.show_dhia and st.session_state.is_instructor:
                st.warning("⚠️ Note: This tab is currently HIDDEN from students.")
                
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📍 Facility & Operational Profile")
                st.write(f"**Location:** {farm_data['location']}")
                st.write(f"**Management:** {farm_data['owner']}")
                st.write(f"**Herd Size & Breed:** {farm_data['herd_size']}")
                st.write(f"**Housing:** {farm_data['facility']}")
                st.write(f"**Milking Setup:** {farm_data['milking_system']}")
                st.write(f"**Milking Frequency:** {farm_data['milking_freq']}")
                
            with col2:
                st.subheader("🌾 Economics & Land")
                st.write(f"**Current Milk Price:** {farm_data['economics']['milk_price']}")
                st.write(f"**Cropland:** {farm_data['economics']['crop_acres']}")
                st.write(f"**Feed Share:** {farm_data['economics']['feed_ratio']}")
                
                st.subheader("📈 Key DHIA Metrics")
                st.write(f"**Rolling Herd Average (RHA):** {farm_data['dhia_summary']['rha']}")
                st.write(f"**Bulk Tank SCC:** {farm_data['dhia_summary']['scc_average']}")
                st.write(f"**Pregnancy Rate:** {farm_data['dhia_summary']['preg_rate']}")
                st.write(f"**Cull Rate:** {farm_data['dhia_summary']['cull_rate']}")
        tab_idx += 1

    # TAB: FINANCIAL STATEMENTS
    if st.session_state.show_financials or st.session_state.is_instructor:
        with tabs[tab_idx]:
            st.header(f"Financial Statements: {farm_data['name']}")
            if not st.session_state.show_financials and st.session_state.is_instructor:
                st.warning("⚠️ Note: This tab is currently HIDDEN from students.")
                
            fin = farm_data["financials"]
            col_inc, col_bal, col_cash = st.columns(3)
            
            with col_inc:
                st.subheader("💵 Income Statement (Annual)")
                st.write(f"**Gross Milk Revenue:** {fin['gross_revenue']}")
                st.write(f"**Total Feed Expense:** {fin['feed_cost']}")
                st.write(f"**Hired Labor Expense:** {fin['labor_cost']}")
                st.write(f"**Veterinary & Supplies:** {fin['vet_med_cost']}")
                st.markdown("---")
                st.write(f"**Net Farm Income:** {fin['net_farm_income']}")

            with col_bal:
                st.subheader("🏛️ Balance Sheet")
                st.write(f"**Total Farm Assets:** {fin['total_assets']}")
                st.write(f"**Total Liabilities:** {fin['total_liabilities']}")
                st.markdown("---")
                st.write(f"**Owner Equity:** {fin['owner_equity']}")

            with col_cash:
                st.subheader("🔄 Cash Flow & Ratios")
                st.write(f"**Debt Service Coverage Ratio (DSCR):** {fin['dscr']}")
                st.caption("A DSCR above 1.25 indicates healthy debt servicing capability.")
        tab_idx += 1

    # TAB: PRODUCER INTERVIEW CHAT
    with tabs[tab_idx]:
        st.header(f"Interview with {farm_data['owner'].split(' ')[0]} Salfer ({farm_data['name']})")
        st.caption("Ask open-ended, Socratic questions to investigate farm operations, labor routines, and herd health.")

        if not api_key:
            st.warning("⚠️ Please enter an OpenAI API Key in the sidebar to begin the conversation.")
        else:
            openai.api_key = api_key

            # Initialize Chat Session
            if "messages" not in st.session_state:
                st.session_state.messages = [
                    {"role": "system", "content": farm_data["persona_prompt"]},
                    {"role": "assistant", "content": f"Hello there. I'm Dan Salfer. Thanks for stopping by {farm_data['name']}. What questions do you have for me today?"}
                ]

            # Display Chat History
            for msg in st.session_state.messages:
                if msg["role"] != "system":
                    avatar = "👨‍🌾" if msg["role"] == "assistant" else "🎓"
                    with st.chat_message(msg["role"], avatar=avatar):
                        st.write(msg["content"])

            # Chat Input
            if user_input := st.chat_input("Ask Mr. Salfer a diagnostic question..."):
                # Append user message
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user", avatar="🎓"):
                    st.write(user_input)

                # Log student question to DB
                st_id = st.session_state.student_user['id'] if st.session_state.student_user else "INSTRUCTOR_TEST"
                st_name = st.session_state.student_user['name'] if st.session_state.student_user else "Instructor"
                log_chat_message(st_id, st_name, selected_farm_key, "Student", user_input)

                # Generate AI Response
                try:
                    client = openai.OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=st.session_state.messages,
                        temperature=0.7
                    )
                    bot_reply = response.choices[0].message.content
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    
                    with st.chat_message("assistant", avatar="👨‍🌾"):
                        st.write(bot_reply)

                    # Log producer reply to DB
                    log_chat_message(st_id, st_name, selected_farm_key, "Producer (AI)", bot_reply)

                except Exception as e:
                    st.error(f"Error connecting to AI model: {e}")
    tab_idx += 1

    # TAB: INSTRUCTOR ADMIN PANEL
    if st.session_state.is_instructor:
        with tabs[tab_idx]:
            st.header("🔒 Instructor Control & Student Interaction Logs")
            
            admin_sub1, admin_sub2 = st.tabs(["📋 Student Interaction Transcripts", "⚙️ Visibility & Scenario Settings"])
            
            # SUBTAB 1: STUDENT TRANSCRIPTS & LOGS
            with admin_sub1:
                st.subheader("Student Chat Logs & Evaluation")
                
                students_df = get_student_list()
                if students_df.empty:
                    st.info("No student interactions recorded yet.")
                else:
                    st.write(f"Total Enrolled/Interacting Students: **{len(students_df)}**")
                    
                    student_options = [f"{row['name']} (ID: {row['student_id']}) - {row['section']}" for _, row in students_df.iterrows()]
                    selected_student_str = st.selectbox("Select Student to Evaluate:", student_options)
                    
                    if selected_student_str:
                        selected_id = selected_student_str.split("ID: ")[1].split(")")[0]
                        logs_df = get_student_logs(selected_id)
                        
                        st.markdown(f"### Chat Transcript for Student ID: `{selected_id}`")
                        
                        if logs_df.empty:
                            st.write("No messages recorded for this student yet.")
                        else:
                            for _, log_row in logs_df.iterrows():
                                role_icon = "🎓 **Student**" if log_row['role'] == "Student" else "👨‍🌾 **Producer**"
                                st.markdown(f"**[{log_row['timestamp']}] {role_icon}:** {log_row['message']}")
                                st.divider()
                                
                    st.markdown("---")
                    st.subheader("📥 Export Complete Class Data")
                    all_logs_df = get_all_logs_df()
                    if not all_logs_df.empty:
                        csv_data = all_logs_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="Download All Student Chat Logs (CSV)",
                            data=csv_data,
                            file_name=f"dairy_consulting_student_logs_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )

            # SUBTAB 2: REPORT VISIBILITY TOGGLES
            with admin_sub2:
                st.subheader("Document Visibility Controls")
                st.caption("Toggle which reports are visible to students for diagnostic evaluation.")
                
                st.session_state.show_dhia = st.checkbox("Show DHIA 302 Herd Summary to Students", value=st.session_state.show_dhia)
                st.session_state.show_financials = st.checkbox("Show Financial Statements to Students", value=st.session_state.show_financials)
                
                st.success("Settings updated dynamically!")
