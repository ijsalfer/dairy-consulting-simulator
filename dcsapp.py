import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import google.generativeai as genai

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Dairy Consulting Interview Simulator",
    page_icon="🐄",
    layout="wide"
)

# --- DATABASE SETUP (TRANSCRIPTS) ---
def init_db():
    conn = sqlite3.connect('transcripts.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            student_id TEXT,
            section TEXT,
            farm_name TEXT,
            timestamp DATETIME,
            role TEXT,
            message TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def log_message(student_name, student_id, section, farm_name, role, message):
    conn = sqlite3.connect('transcripts.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        INSERT INTO transcripts (student_name, student_id, section, farm_name, timestamp, role, message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (student_name, student_id, section, farm_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), role, message))
    conn.commit()
    conn.close()

def get_transcripts():
    conn = sqlite3.connect('transcripts.db', check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM transcripts ORDER BY timestamp ASC", conn)
    conn.close()
    return df

# --- DEFAULT SCENARIO DATA ---
if "farms" not in st.session_state:
    st.session_state.farms = {
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
            "show_dhia": True,
            "show_financials": True,
            "dhia_summary": {
                "rha": "26,500 lbs Milk",
                "scc_average": "280,000 cells/mL (Linear Score 2nd+ Lactation > 4.0)",
                "preg_rate": "15% (Goal: 20%+)",
                "cull_rate": "34% (Primary reasons: Mastitis & Repro failure)"
            },
            "financials": {
                "income_statement": {
                    "Gross Milk Revenue": "$2,716,250",
                    "Cattle Sales": "$185,000",
                    "Total Revenue": "$2,901,250",
                    "Feed Costs (Grown & Purchased)": "$1,325,000",
                    "Labor & Benefits": "$380,000",
                    "Veterinary & Supplies": "$145,000",
                    "Net Farm Income": "$312,000"
                },
                "balance_sheet": {
                    "Current Assets": "$450,000",
                    "Non-Current Assets (Land/Cattle/Machinery)": "$4,800,000",
                    "Total Liabilities": "$2,100,000",
                    "Owner Equity": "$3,150,000"
                },
                "cash_flow": {
                    "Operating Cash Flow": "$420,000",
                    "Annual Debt Service": "$210,000",
                    "Debt Service Coverage Ratio (DSCR)": "2.0x"
                }
            },
            "persona_prompt": """You are Dan Salfer, the owner-operator of Salfer Dairy, a 500-cow Holstein farm in Central Minnesota. You are being interviewed by a student dairy consultant.

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
- Keep responses conversational, natural, and realistic for a busy dairy farmer (2 to 4 sentences per response)."""
        }
    }

# --- HEADER ---
st.title("🐄 Dairy Consulting Interview Simulator")
st.caption("Powered by Google Gemini | University Dairy Consulting Program")

# --- SIDEBAR & AUTHENTICATION ---
st.sidebar.header("🔑 Student Authentication")

if "student_info" not in st.session_state:
    st.session_state.student_info = None

if st.session_state.student_info is None:
    with st.sidebar.form("student_login_form"):
        st.subheader("Sign In to Begin")
        s_name = st.text_input("Full Name:")
        s_id = st.text_input("Student ID:")
        s_section = st.text_input("Class Section:", value="ANSC 401 - Fall")
        submit_login = st.form_submit_button("Sign In")
        
        if submit_login and s_name and s_id:
            st.session_state.student_info = {
                "name": s_name,
                "id": s_id,
                "section": s_section
            }
            st.sidebar.success(f"Welcome, {s_name}!")
            st.rerun()

else:
    st.sidebar.success(f"👤 **Student:** {st.session_state.student_info['name']}")
    st.sidebar.info(f"🆔 **ID:** {st.session_state.student_info['id']} | **Section:** {st.session_state.student_info['section']}")
    if st.sidebar.button("Sign Out"):
        st.session_state.student_info = None
        st.session_state.messages = []
        st.rerun()

st.sidebar.markdown("---")

# API KEY HANDLING (SECRETS OR SIDEBAR FALLBACK)
api_key = None
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Gemini API Key (Fallback):", type="password", help="Entered automatically if configured in Streamlit Secrets.")

# SCENARIO SELECTOR
selected_farm_key = st.sidebar.selectbox("Select Farm Scenario:", list(st.session_state.farms.keys()))
farm_data = st.session_state.farms[selected_farm_key]

# --- MAIN APP BODY ---
if st.session_state.student_info is None:
    st.info("👈 Please sign in using the sidebar on the left to access the farm records and start your producer interview.")
else:
    # Build Tabs dynamically based on instructor settings
    tab_list = []
    if farm_data["show_dhia"]:
        tab_list.append("📊 DHIA 302 Summary")
    if farm_data["show_financials"]:
        tab_list.append("💰 Financial Statements")
    tab_list.append("💬 Producer Interview Chat")
    tab_list.append("🔒 Instructor Admin")

    tabs = st.tabs(tab_list)
    tab_idx = 0

    # TAB: DHIA 302
    if farm_data["show_dhia"]:
        with tabs[tab_idx]:
            st.header(f"DHIA 302 Herd Summary: {farm_data['name']}")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📍 Facility & Operational Overview")
                st.write(f"**Location:** {farm_data['location']}")
                st.write(f"**Management:** {farm_data['owner']}")
                st.write(f"**Herd Size & Breed:** {farm_data['herd_size']}")
                st.write(f"**Housing:** {farm_data['facility']}")
                st.write(f"**Milking Setup:** {farm_data['milking_system']}")
                st.write(f"**Milking Frequency:** {farm_data['milking_freq']}")
            with col2:
                st.subheader("📈 Key Herd Performance Indicators")
                st.write(f"**Rolling Herd Average (RHA):** {farm_data['dhia_summary']['rha']}")
                st.write(f"**Bulk Tank SCC:** {farm_data['dhia_summary']['scc_average']}")
                st.write(f"**Pregnancy Rate:** {farm_data['dhia_summary']['preg_rate']}")
                st.write(f"**Cull Rate:** {farm_data['dhia_summary']['cull_rate']}")
                st.write(f"**Milk Price / Land:** {farm_data['economics']['milk_price']} | {farm_data['economics']['crop_acres']}")
        tab_idx += 1

    # TAB: FINANCIAL STATEMENTS
    if farm_data["show_financials"]:
        with tabs[tab_idx]:
            st.header(f"Financial Statements: {farm_data['name']}")
            f_col1, f_col2, f_col3 = st.columns(3)
            
            with f_col1:
                st.subheader("📄 Income Statement")
                for k, v in farm_data["financials"]["income_statement"].items():
                    st.write(f"**{k}:** {v}")
                    
            with f_col2:
                st.subheader("⚖️ Balance Sheet")
                for k, v in farm_data["financials"]["balance_sheet"].items():
                    st.write(f"**{k}:** {v}")

            with f_col3:
                st.subheader("💵 Cash Flow")
                for k, v in farm_data["financials"]["cash_flow"].items():
                    st.write(f"**{k}:** {v}")
        tab_idx += 1

    # TAB: CHAT INTERFACE
    with tabs[tab_idx]:
        st.header(f"Interview with {farm_data['owner'].split(' ')[0]} ({farm_data['name']})")
        
        # Display notice if reports are locked by instructor
        hidden_reports = []
        if not farm_data["show_dhia"]: hidden_reports.append("DHIA 302 Summary")
        if not farm_data["show_financials"]: hidden_reports.append("Financial Statements")
        if hidden_reports:
            st.warning(f"🔒 Note: The following reports are withheld by the producer: {', '.join(hidden_reports)}. You must ask permission during your interview to view them.")

        if not api_key:
            st.error("⚠️ Gemini API Key not detected. Please add GEMINI_API_KEY to Streamlit Secrets or enter it in the sidebar.")
        else:
            genai.configure(api_key=api_key)

            # Initialize Chat History
            if "messages" not in st.session_state:
                st.session_state.messages = [
                    {"role": "assistant", "content": f"Hello there. I'm Dan Salfer. Thanks for coming out to {farm_data['name']}. What can I help you with today?"}
                ]

            # Display Chat History
            for msg in st.session_state.messages:
                avatar = "👨‍🌾" if msg["role"] == "assistant" else "🎓"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.write(msg["content"])

            # Chat Input
            if user_input := st.chat_input("Ask a diagnostic question..."):
                # Append and display user input
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user", avatar="🎓"):
                    st.write(user_input)

                # Log user query to SQLite
                log_message(
                    st.session_state.student_info["name"],
                    st.session_state.student_info["id"],
                    st.session_state.student_info["section"],
                    farm_data["name"],
                    "Student",
                    user_input
                )

                # Generate Response via Gemini with Automatic Model Fallback
                try:
                    # Prepare history for Gemini
                    gemini_history = []
                    for m in st.session_state.messages[:-1]:
                        role = "user" if m["role"] == "user" else "model"
                        gemini_history.append({"role": role, "parts": [m["content"]]})

                    # If history starts with model greeting, prepend dummy user prompt to satisfy Gemini API structure
                    if gemini_history and gemini_history[0]["role"] == "model":
                        gemini_history.insert(0, {"role": "user", "parts": ["Hello Mr. Salfer"]})

                    # Candidate model names to cycle through if one model string throws 404
                    model_candidates = [
                        "gemini-1.5-flash",
                        "gemini-1.5-flash-latest",
                        "gemini-2.0-flash",
                        "gemini-1.5-pro",
                        "gemini-1.5-flash-001"
                    ]

                    bot_reply = None
                    last_error = None

                    for candidate in model_candidates:
                        try:
                            model = genai.GenerativeModel(
                                model_name=candidate,
                                system_instruction=farm_data["persona_prompt"]
                            )
                            chat = model.start_chat(history=gemini_history)
                            response = chat.send_message(user_input)
                            bot_reply = response.text
                            if bot_reply:
                                break
                        except Exception as err:
                            last_error = err
                            continue

                    if not bot_reply:
                        raise last_error if last_error else Exception("Unable to connect to Gemini models.")

                    # Append and log bot response
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    with st.chat_message("assistant", avatar="👨‍🌾"):
                        st.write(bot_reply)

                    log_message(
                        st.session_state.student_info["name"],
                        st.session_state.student_info["id"],
                        st.session_state.student_info["section"],
                        farm_data["name"],
                        "Producer (Dan Salfer)",
                        bot_reply
                    )

                except Exception as e:
                    st.error(f"Error connecting to Gemini API: {e}\n\n💡 Tip: Verify your key was created at https://aistudio.google.com and entered into Streamlit Secrets.")

    tab_idx += 1

    # TAB: INSTRUCTOR ADMIN PANEL
    with tabs[tab_idx]:
        st.header("🔒 Instructor Admin & Evaluation Panel")
        admin_pass = st.text_input("Enter Instructor Password:", type="password")
        
        if admin_pass == "dairy123":
            st.success("Authenticated as Instructor")
            
            admin_tab1, admin_tab2 = st.tabs(["📑 Report Visibility Controls", "📋 Student Transcripts"])
            
            with admin_tab1:
                st.subheader("Manage Document Visibility for Selected Farm")
                farm_data["show_dhia"] = st.checkbox("Show DHIA 302 Summary to Students", value=farm_data["show_dhia"])
                farm_data["show_financials"] = st.checkbox("Show Financial Statements to Students", value=farm_data["show_financials"])
                st.info("Changes apply immediately to the current student session.")

            with admin_tab2:
                st.subheader("Student Interaction Logs")
                df_logs = get_transcripts()
                
                if df_logs.empty:
                    st.info("No student interactions recorded yet.")
                else:
                    # Filter by student
                    students = df_logs["student_name"].unique()
                    selected_student = st.selectbox("Select Student to Evaluate:", students)
                    
                    student_df = df_logs[df_logs["student_name"] == selected_student]
                    st.dataframe(student_df[["timestamp", "role", "message"]], use_container_width=True)
                    
                    # CSV Export Button
                    csv_data = df_logs.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download All Student Transcripts (CSV)",
                        data=csv_data,
                        file_name="dairy_consulting_student_transcripts.csv",
                        mime="text/csv"
                    )
        elif admin_pass:
            st.error("Incorrect Password.")
