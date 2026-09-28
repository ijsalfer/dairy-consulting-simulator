import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import re
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

# --- HELPER FUNCTION: BOT REPLY SANITIZER ---
def sanitize_bot_reply(reply_text, user_prompt=""):
    if not reply_text:
        return "Sorry, I didn't catch that. Could you ask me that again?"
    
    cleaned = reply_text.strip()
    
    # Strip out common internal reasoning / planning blocks
    cleaned = re.sub(r'^(User|Student|Question|Goal|Salfer|Farmer|Context|Instructions?|Persona):.*?
', '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r'^\*.*?\*
?', '', cleaned)
    cleaned = re.sub(r'^(Goal|Salfer is|He manages|He's skeptical|Focus on):.*?
?', '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove leading/trailing quotation marks if whole message is wrapped
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) > 2:
        cleaned = cleaned[1:-1].strip()
    
    # If the reply accidentally echoed the user prompt verbatim, strip it
    if user_prompt and cleaned.lower().startswith(user_prompt.lower()):
        cleaned = cleaned[len(user_prompt):].strip()
        if cleaned.startswith("?") or cleaned.startswith(":"):
            cleaned = cleaned[1:].strip()
            
    # Final cleanup of extra quotes or markdown headers
    cleaned = re.sub(r'^#+\s*', '', cleaned)
    
    if not cleaned:
        cleaned = "Main thing for me is keeping the cows healthy and making sure the farm stays profitable while balancing crop work."
        
    return cleaned

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
            "dhia_details": {
                "production": {
                    "RHA Milk": "26,500 lbs (Fat 4.8%, Protein 3.4%)",
                    "305 ME Milk": "Lact 1: 26,140 lbs | Lact 2: 27,944 lbs | Lact 3+: 25,396 lbs",
                    "Peak Milk": "Lact 1: 78 lbs (DIM 81) | Lact 2: 104 lbs (DIM 61) | Lact 3+: 107 lbs (DIM 50)",
                    "Peak Ratio (1st/Others)": "0.77 (Underperforming 1st lact relative to mature cows)"
                },
                "udder_health": {
                    "Bulk Tank Raw SCC": "280,000 cells/mL (Test day range 184k - 280k)",
                    "Linear Score Distribution": "Lact 1: 58% LS 0-1, 32% LS 2-3, 11% LS 4-6 | Lact 2: 50% LS 0-1, 31% LS 2-3, 13% LS 4-6, 6% LS 7-9 (28% LS > 4.0) | Lact 3+: 30% LS 0-1, 30% LS 2-3, 40% LS 4-6",
                    "30-Day SCC Production Loss": "2,163 lbs milk lost per test ($429 monthly direct loss)",
                    "Infection Rate": "23% of mature cows chronically infected; fresh cow infection rate 20%"
                },
                "reproduction": {
                    "21-Day Pregnancy Rate": "15% (Cows) | Goal: 20%+",
                    "Heat Detection Index": "44%",
                    "Services per Conception": "1.7 (Cows) | 1.8 (Heifers)",
                    "First Service Conception": "51%",
                    "Calving Interval": "12.3 months (Open period average 70 days for cows)"
                },
                "turnover": {
                    "Annual Turnover / Cull Rate": "34% - 52% total turnover",
                    "Reasons for Leaving Herd": "Repro Failure: 42% | Low Milk: 18% | Mastitis/High SCC: 15% | Died/Mortality: 15% | Dairy/Other: 10%"
                }
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
            "persona_prompt": """You are Dan Salfer, the owner-operator of Salfer Dairy, a 500-cow Holstein farm in Central Minnesota. You are being interviewed face-to-face or via text message by a student dairy consultant.

YOUR PERSONALITY & DEMEANOR:
- Proud, hardworking, practical, and deeply committed to your herd and family farm.
- Stretched thin between managing 1,200 acres of crops and overseeing 4 hired parlor and feed staff.
- Skeptical of outside consultants who immediately offer advice without understanding your daily labor and crop realities.
- Defensive if challenged directly or accused of poor management (e.g., if a student says "Your prep routine is bad" or "Your SCC is terrible").

DETAILED HERD KNOWLEDGE BASE (YOU KNOW THESE NUMBERS IF SPECIFICALLY ASKED):
- Production & Milk: RHA is 26,500 lbs (Fat 4.8%, Protein 3.4%). 1st lactation cows peak around 78 lbs, while 2nd lactation peak at 104 lbs and 3rd+ at 107 lbs. Peak ratio is 0.77.
- Udder Health & SCC: Bulk tank SCC runs ~280,000 cells/mL. About 28% of 2nd+ lactation cows have linear scores above 4.0. The DHIA sheet shows about 2,163 lbs of milk lost every 30 days due to SCC ($429 monthly direct loss).
- Reproduction: Pregnancy rate is sitting at 15% (Heat Detection Index is 44%, Services per Conception is 1.7).
- Culling & Turnover: Turnover rate is ~34-52%. 42% of culls leave for repro failure, 18% for low milk, 15% for mastitis/high SCC, and 15% die or get emergency culled.
- Facility & Feed: 500 Holsteins in 6-row freestalls with deep sand. Double-12 parallel parlor milked 3x/day (6 AM, 2 PM, 10 PM). 1,200 acres cropland supplying 75% of feed. Milk price is $20.50/cwt.

HIDDEN OPERATIONAL REALITIES (ONLY REVEAL IF ASKED THOUGHTFUL, SPECIFIC, SOCRATIC QUESTIONS):
1. SCC / Udder Health Issue:
   - If asked about the night shift milking routine, parlor auditing, or pre-dip contact time: Reveal that during the 10:00 PM night milking, the hired night crew cuts pre-dip contact time down to 10-15 seconds (instead of the required 45-60 seconds) to finish their shift faster and go home.
2. Reproduction / Peak Milk Issue:
   - If asked how crop farming overlaps with herd health routines, or why OvSynch injections might be missed: Reveal that during spring planting and fall harvest, Timed-AI / OvSynch injections frequently get delayed by 24 to 48 hours because you are out in the tractor on 1,200 acres all day.

CRITICAL DIALOGUE & FORMATTING RULES:
- NEVER repeat or echo the user's question back.
- NEVER output character notes, planning thoughts, headers, bullet points, or labels like "Goal:", "User:", or "Dan:".
- NEVER wrap your entire response in quotation marks.
- Speak directly in character as Dan Salfer in 2 to 4 conversational sentences, exactly like a text message or face-to-face chat on the farm. Keep it grounded, practical, and natural."""
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
            
            st.markdown("---")
            st.subheader("📋 Granular DHIA 302 Benchmark Metrics")
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                st.markdown("#### 🥛 Production & Peak Yields")
                for k, v in farm_data.get("dhia_details", {}).get("production", {}).items():
                    st.write(f"**{k}:** {v}")
                
                st.markdown("#### 🦠 Udder Health & Somatic Cell Count")
                for k, v in farm_data.get("dhia_details", {}).get("udder_health", {}).items():
                    st.write(f"**{k}:** {v}")

            with d_col2:
                st.markdown("#### 🧬 Reproduction & Fertility")
                for k, v in farm_data.get("dhia_details", {}).get("reproduction", {}).items():
                    st.write(f"**{k}:** {v}")

                st.markdown("#### 🚪 Turnover & Culling Breakdown")
                for k, v in farm_data.get("dhia_details", {}).get("turnover", {}).items():
                    st.write(f"**{k}:** {v}")

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

                # Generate Response via Gemini
                try:
                    # Clean history construction with strict alternating turn pairs
                    gemini_history = []
                    
                    # Convert session state messages (skip first bot greeting if unpaired)
                    raw_messages = st.session_state.messages[:-1] # Exclude current user prompt
                    
                    for m in raw_messages:
                        role = "user" if m["role"] == "user" else "model"
                        # Prevent consecutive identical roles
                        if gemini_history and gemini_history[-1]["role"] == role:
                            continue
                        gemini_history.append({"role": role, "parts": [m["content"]]})

                    # Gemini API requires history to start with a 'user' turn
                    if gemini_history and gemini_history[0]["role"] == "model":
                        gemini_history.pop(0)

                    # Candidate models to try
                    model_candidates = [
                        "gemini-1.5-flash",
                        "models/gemini-1.5-flash",
                        "gemini-2.0-flash",
                        "models/gemini-2.0-flash",
                        "gemini-1.5-pro"
                    ]

                    # Attempt dynamic listing if available
                    try:
                        listed = [m.name for m in genai.list_models() if 'generateContent' in getattr(m, 'supported_generation_methods', [])]
                        if listed:
                            model_candidates = list(dict.fromkeys(listed + model_candidates))
                    except Exception:
                        pass

                    bot_reply = None
                    last_err = None

                    for candidate in model_candidates:
                        try:
                            model = genai.GenerativeModel(
                                model_name=candidate,
                                system_instruction=farm_data["persona_prompt"]
                            )
                            chat = model.start_chat(history=gemini_history)
                            response = chat.send_message(user_input)
                            if response and response.text:
                                raw_text = response.text
                                bot_reply = sanitize_bot_reply(raw_text, user_prompt=user_input)
                                break
                        except Exception as err:
                            last_err = err
                            continue

                    if not bot_reply:
                        raise last_err if last_err else Exception("Unable to connect to Gemini API models.")

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
                    st.error(f"Error connecting to Gemini API: {e}")

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
