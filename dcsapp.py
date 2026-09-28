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

# ==============================================================================
# 🔑 PERMANENT GEMINI API KEY CONFIGURATION
# Set your AIzaSy... API key here if you want it hardcoded. Leave empty otherwise.
# ==============================================================================
HARDCODED_GEMINI_API_KEY = ""

# --- DATABASE SETUP (TRANSCRIPTS) ---
def init_db():
    try:
        conn = sqlite3.connect('transcripts.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            student_id TEXT,
            course TEXT,
            semester TEXT,
            farm_name TEXT,
            timestamp DATETIME,
            role TEXT,
            message TEXT
        )''')
        conn.commit()
        
        # Auto-migrate columns if table exists from old schema
        c.execute('PRAGMA table_info(transcripts)')
        existing_cols = [row[1] for row in c.fetchall()]
        if 'course' not in existing_cols:
            c.execute('ALTER TABLE transcripts ADD COLUMN course TEXT DEFAULT "ANSC 4604"')
            conn.commit()
        if 'semester' not in existing_cols:
            c.execute('ALTER TABLE transcripts ADD COLUMN semester TEXT DEFAULT "Spring 2027"')
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database init note: {e}")

init_db()

def log_message(student_name, student_id, course, semester, farm_name, role, message):
    try:
        conn = sqlite3.connect('transcripts.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''INSERT INTO transcripts (student_name, student_id, course, semester, farm_name, timestamp, role, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (student_name, student_id, course, semester, farm_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), role, message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Logging exception: {e}")

def get_transcripts():
    try:
        conn = sqlite3.connect('transcripts.db', check_same_thread=False)
        df = pd.read_sql_query("SELECT * FROM transcripts ORDER BY timestamp ASC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# --- HELPER FUNCTION: BOT REPLY SANITIZER ---
def sanitize_bot_reply(reply_text, user_prompt=""):
    if not reply_text:
        return "I'm doing alright, just staying busy between the cows and the 1,200 acres. What can I help you with today?"
    
    text = reply_text.strip()
    match_perfect = re.search(r'(?:Perfect\.|Final Answer:)\s*(.*)$', text, re.DOTALL | re.IGNORECASE)
    if match_perfect and len(match_perfect.group(1).strip()) > 10:
        text = match_perfect.group(1).strip()
    else:
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        filtered = []
        for p in paragraphs:
            if re.search(r'^(User|Student|Greeting|Character|Goal|Tone|Check Constraints|Wait,|No headers|No labels|No quotes|2-4 conversational|Check:|Constraints:|Persona:|\*|Dan:|Farmer:)', p, re.IGNORECASE):
                continue
            filtered.append(p)
        if filtered:
            text = " ".join(filtered)
            
    text = re.sub(r'^#+\s*', '', text)
    if text.startswith('"') and text.endswith('"') and len(text) > 2:
        text = text[1:-1].strip()
        
    if user_prompt and text.lower().startswith(user_prompt.lower()):
        text = text[len(user_prompt):].strip()
        if text.startswith("?") or text.startswith(":"):
            text = text[1:].strip()
            
    if not text:
        text = "I'm doing alright, just staying busy between the cows and the 1,200 acres. Main thing is keeping the place profitable."
        
    return text

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
            "persona_prompt": """You are Dan Salfer, the owner-operator of Salfer Dairy, a 500-cow Holstein farm in Central Minnesota. You are being interviewed face-to-face or via text message by a student dairy consultant.

YOUR PERSONALITY & DEMEANOR:
- Proud, hardworking, practical, and deeply committed to your herd and family farm.
- Stretched thin between managing 1,200 acres of crops and overseeing 4 hired parlor and feed staff.
- Skeptical of outside consultants who immediately offer advice without understanding your daily labor and crop realities.

YOUR GOAL & CONCRETE TARGET ISSUE:
- Your main goal is to keep the operation steady and profitable so your children can eventually take over.
- You are open about wanting to LOWER YOUR BULK TANK SOMATIC CELL COUNT (SCC) from 280,000 cells/mL down under 200,000 cells/mL so you stop leaving quality bonus money on the table ($429+ monthly direct loss on DHIA).
- You express frustration that between field work on 1,200 acres and managing the parlor, you feel like you are constantly playing catch-up.

HIDDEN OPERATIONAL REALITIES (ONLY REVEAL IF ASKED THOUGHTFUL, SPECIFIC, SOCRATIC QUESTIONS):
1. SCC / Udder Health Issue:
   - If asked about the night shift milking routine, parlor auditing, or pre-dip contact time: Reveal that during the 10:00 PM night milking, the hired night crew cuts pre-dip contact time down to 10-15 seconds (instead of the required 45-60 seconds) to finish their shift faster and go home.
2. Reproduction / Peak Milk Issue:
   - If asked how crop farming overlaps with herd health routines, or why OvSynch injections might be missed: Reveal that during spring planting and fall harvest, Timed-AI / OvSynch injections frequently get delayed by 24 to 48 hours because you are out in the tractor on 1,200 acres all day.

CRITICAL DIALOGUE RULES:
- NEVER repeat or echo the user's question back.
- NEVER output character notes, planning thoughts, headers, checklists, or labels.
- Speak directly in character as Dan Salfer in 2 to 4 conversational sentences, exactly like a text message or face-to-face chat on the farm."""
        }
    }

# --- HEADER ---
st.title("🐄 Dairy Consulting Interview Simulator")
st.caption("Powered by Google Gemini | University Dairy Consulting Program")

# --- API KEY RESOLUTION ---
api_key = None
if HARDCODED_GEMINI_API_KEY.strip():
    api_key = HARDCODED_GEMINI_API_KEY.strip()
elif "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]

# --- SIDEBAR: AUTHENTICATION & INSTRUCTOR ADMIN ---
st.sidebar.header("🔑 Student Authentication")

if "student_info" not in st.session_state:
    st.session_state.student_info = None

if st.session_state.student_info is None:
    with st.sidebar.form("student_login_form"):
        st.subheader("Sign In to Begin")
        s_name = st.text_input("Full Name:")
        s_id = st.text_input("Student ID:")
        s_course = st.text_input("Course Number:", value="ANSC 4604")
        s_semester = st.text_input("Semester:", value="Spring 2027")
        submit_login = st.form_submit_button("Sign In")
        
        if submit_login and s_name and s_id:
            st.session_state.student_info = {
                "name": s_name,
                "id": s_id,
                "course": s_course,
                "semester": s_semester
            }
            st.sidebar.success(f"Welcome, {s_name}!")
            st.rerun()

else:
    st.sidebar.success(f"👤 **Student:** {st.session_state.student_info['name']}")
    st.sidebar.info(f"🆔 **ID:** {st.session_state.student_info['id']} | **Course:** {st.session_state.student_info['course']} ({st.session_state.student_info['semester']})")
    if st.sidebar.button("Sign Out"):
        st.session_state.student_info = None
        st.session_state.messages = []
        st.rerun()

st.sidebar.markdown("---")

selected_farm_key = st.sidebar.selectbox("Select Farm Scenario:", list(st.session_state.farms.keys()))
farm_data = st.session_state.farms[selected_farm_key]

# --- SIDEBAR EXPANDER: INSTRUCTOR ADMIN PORTAL ---
with st.sidebar.expander("🔒 Instructor Admin Portal"):
    admin_pass = st.text_input("Instructor Password:", type="password", key="admin_pwd_key")
    if admin_pass == "dairy123":
        st.success("Authenticated")
        
        st.markdown("#### 📑 Report Visibility Controls")
        farm_data["show_dhia"] = st.checkbox("Show DHIA 302 Summary", value=farm_data["show_dhia"])
        farm_data["show_financials"] = st.checkbox("Show Financial Statements", value=farm_data["show_financials"])
        
        st.markdown("---")
        st.markdown("#### 📋 Student Transcripts")
        df_logs = get_transcripts()
        if df_logs.empty:
            st.info("No logs recorded yet.")
        else:
            students = df_logs["student_name"].unique() if "student_name" in df_logs.columns else []
            if len(students) > 0:
                selected_student = st.selectbox("Select Student:", students)
                student_df = df_logs[df_logs["student_name"] == selected_student]
                cols_to_show = [c for c in ["timestamp", "role", "message"] if c in student_df.columns]
                st.dataframe(student_df[cols_to_show], use_container_width=True)
                
                csv_data = df_logs.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download All Transcripts (CSV)",
                    data=csv_data,
                    file_name="dairy_consulting_student_transcripts.csv",
                    mime="text/csv"
                )
    elif admin_pass:
        st.error("Incorrect Password")

if not api_key:
    st.sidebar.warning("⚠️ API Key not detected. Enter key below:")
    api_key = st.sidebar.text_input("Gemini API Key:", type="password", key="fallback_key")

# --- MAIN APP BODY (TABS) ---
if st.session_state.student_info is None:
    st.info("👈 Please sign in using the sidebar on the left to access farm records and start your producer interview.")
else:
    tab_titles = ["💬 Producer Interview Chat"]
    if farm_data["show_dhia"]:
        tab_titles.append("📊 DHIA 302 Herd Summary")
    if farm_data["show_financials"]:
        tab_titles.append("📄 Income Statement")
        tab_titles.append("⚖️ Balance Sheet")
        tab_titles.append("💵 Cash Flow Statement")

    tabs = st.tabs(tab_titles)
    tab_idx = 0

    # TAB 1: CHAT INTERFACE
    with tabs[tab_idx]:
        st.header(f"Interview with {farm_data['owner'].split(' ')[0]} ({farm_data['name']})")
        
        hidden_reports = []
        if not farm_data["show_dhia"]: hidden_reports.append("DHIA 302 Herd Summary")
        if not farm_data["show_financials"]: hidden_reports.append("Financial Statements")
        if hidden_reports:
            st.warning(f"🔒 Note: The following reports are withheld by the producer: {', '.join(hidden_reports)}. You must ask permission during your interview to view them.")

        if not api_key:
            st.error("⚠️ Gemini API Key required to run chat. Enter key in the sidebar.")
        else:
            try:
                genai.configure(api_key=api_key)
            except Exception as e:
                st.error(f"API Configuration Warning: {e}")

            if "messages" not in st.session_state:
                st.session_state.messages = [
                    {"role": "assistant", "content": f"Hello there. I'm Dan Salfer. Thanks for coming out to {farm_data['name']}. What can I help you with today?"}
                ]

            for msg in st.session_state.messages:
                avatar = "👨‍🌾" if msg["role"] == "assistant" else "🎓"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.write(msg["content"])

            if user_input := st.chat_input("Ask a diagnostic question..."):
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user", avatar="🎓"):
                    st.write(user_input)

                log_message(
                    st.session_state.student_info["name"],
                    st.session_state.student_info["id"],
                    st.session_state.student_info.get("course", "ANSC 4604"),
                    st.session_state.student_info.get("semester", "Spring 2027"),
                    farm_data["name"],
                    "Student",
                    user_input
                )

                try:
                    gemini_history = []
                    raw_messages = st.session_state.messages[:-1]
                    for m in raw_messages:
                        role = "user" if m["role"] == "user" else "model"
                        if gemini_history and gemini_history[-1]["role"] == role:
                            continue
                        gemini_history.append({"role": role, "parts": [m["content"]]})

                    if gemini_history and gemini_history[0]["role"] == "model":
                        gemini_history.pop(0)

                    model_candidates = ["gemini-1.5-flash", "models/gemini-1.5-flash", "gemini-2.0-flash", "models/gemini-2.0-flash", "gemini-1.5-pro"]
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
                            model = genai.GenerativeModel(model_name=candidate, system_instruction=farm_data["persona_prompt"])
                            chat = model.start_chat(history=gemini_history)
                            response = chat.send_message(user_input)
                            if response and response.text:
                                bot_reply = sanitize_bot_reply(response.text, user_prompt=user_input)
                                break
                        except Exception as err:
                            last_err = err
                            continue

                    if not bot_reply:
                        raise last_err if last_err else Exception("Unable to connect to Gemini API.")

                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    with st.chat_message("assistant", avatar="👨‍🌾"):
                        st.write(bot_reply)

                    log_message(
                        st.session_state.student_info["name"],
                        st.session_state.student_info["id"],
                        st.session_state.student_info.get("course", "ANSC 4604"),
                        st.session_state.student_info.get("semester", "Spring 2027"),
                        farm_data["name"],
                        "Producer (Dan Salfer)",
                        bot_reply
                    )

                except Exception as e:
                    st.error(f"Error connecting to Gemini API: {e}")

    tab_idx += 1

    # TAB 2: HERD SUMMARY (DHIA 302) USING NATIVE STREAMLIT DATASETS
    if farm_data["show_dhia"]:
        with tabs[tab_idx]:
            st.header(f"Minnesota DHIA 302 Summary: {farm_data['name']}")
            st.caption("Official Minnesota DHIA DHI-302 Herd & Consultant Summary")

            st.subheader("📍 Facility & Operational Overview")
            df_ops = pd.DataFrame({
                "Operational Category": ["Location", "Management", "Herd Size & Breed", "Housing Setup", "Milking System", "Milking Schedule"],
                "Farm Status": [farm_data["location"], farm_data["owner"], farm_data["herd_size"], farm_data["facility"], farm_data["milking_system"], farm_data["milking_freq"]]
            })
            st.dataframe(df_ops, use_container_width=True, hide_index=True)

            st.subheader("🥛 Peak & Persistency Summary (305 ME Milk)")
            df_peak = pd.DataFrame({
                "Lactation Group": ["1st Lactation", "2nd Lactation", "3rd+ Lactation", "All Herd Overall"],
                "Cows Tested": [24, 26, 14, 64],
                "305 ME Milk (lbs)": ["26,140", "27,944", "25,396", "26,710"],
                "Peak Milk Yield (lbs)": ["78 (Underperforming)", "104", "107", "96"],
                "DIM at Peak": [81, 61, 50, 65]
            })
            st.dataframe(df_peak, use_container_width=True, hide_index=True)
            st.info("💡 **Peak Ratio (1st / Mature Others):** **0.77** *(Benchmark Goal: > 0.80. Indicates 1st lactation heifer peak underperformance)*")

            col_scc, col_repro = st.columns(2)
            with col_scc:
                st.subheader("🦠 Udder Health & Somatic Cell Evaluation")
                df_scc = pd.DataFrame({
                    "Lactation Group": ["1st Lactation", "2nd Lactation", "3rd+ Lactation", "All Herd"],
                    "Avg LS": [1.5, 1.9, 2.7, 1.9],
                    "% LS 0-1": ["58%", "50%", "30%", "49%"],
                    "% LS 2-3": ["32%", "31%", "30%", "31%"],
                    "% LS 4-6": ["11%", "13%", "40%", "18%"],
                    "% LS 7-9": ["0%", "6%", "0%", "2%"]
                })
                st.dataframe(df_scc, use_container_width=True, hide_index=True)
                st.error("⚠️ **Bulk Tank Raw SCC:** 280,000 cells/mL | **30-Day Milk Loss:** 2,163 lbs ($429 direct loss/mo)")

            with col_repro:
                st.subheader("🧬 Reproduction & Herd Turnover")
                df_repro = pd.DataFrame({
                    "Performance Metric": ["21-Day Pregnancy Rate", "Heat Detection Index", "Services / Conception (Cows)", "Services / Conception (Heifers)", "Top Culling Driver"],
                    "Farm Level": ["15% (Low)", "44%", "1.7", "1.8", "Reproduction Failure (42%)"],
                    "Benchmark Goal": ["20% - 24%", "55%+", "< 1.8", "< 1.8", "< 15% Culls"]
                })
                st.dataframe(df_repro, use_container_width=True, hide_index=True)

        tab_idx += 1

    # TAB 3: INCOME STATEMENT USING NATIVE STREAMLIT DATAFRAMES
    if farm_data["show_financials"]:
        with tabs[tab_idx]:
            st.header(f"Farm Income Statement: {farm_data['name']}")
            st.caption("Cash Basis 2-Year Comparative Statement (Dairy Challenge Format)")

            df_inc = pd.DataFrame({
                "Financial Category": [
                    "--- FARM REVENUES ---",
                    "Milk Sales",
                    "Raised Calf, Cow, & Cull Sales",
                    "Other Dairy Revenues",
                    "GROSS FARM INCOME (Line F)",
                    "--- DAIRY OPERATING EXPENSES ---",
                    "Feed (Grown & Purchased)",
                    "Labor & Employee Benefits",
                    "Veterinary, Medicine & Breeding",
                    "Milk Marketing & Supplies",
                    "Repairs, Fuel, & Crop Inputs",
                    "--- NON-DAIRY & OVERHEAD EXPENSES ---",
                    "Interest & Taxes",
                    "Depreciation",
                    "TOTAL FARM EXPENSES (Line I)",
                    "--- NET FARM PROFIT BEFORE TAXES ---",
                    "NET FARM PROFIT (Line F - Line I)"
                ],
                "2018 Prior Year ($)": [
                    "", "$2,580,000", "$170,000", "$15,000", "$2,765,000",
                    "", "$1,250,000", "$360,000", "$138,000", "$92,000", "$610,000",
                    "", "$227,500", "$388,600", "$2,450,000",
                    "", "$315,000"
                ],
                "2019 Current Year ($)": [
                    "", "$2,716,250", "$185,000", "$0", "$2,901,250",
                    "", "$1,325,000", "$380,000", "$145,000", "$98,000", "$641,250",
                    "", "$243,000", "$385,000", "$2,589,250",
                    "", "$312,000"
                ]
            })
            st.dataframe(df_inc, use_container_width=True, hide_index=True)

            col_supp1, col_supp2 = st.columns(2)
            with col_supp1:
                st.subheader("📌 Capital Purchases During Year")
                df_cap = pd.DataFrame({
                    "Category": ["Machinery & Equipment Purchases", "Buildings, Improvements & Facilities"],
                    "2018 ($)": ["$50,000", "$345,000"],
                    "2019 ($)": ["$55,000", "$319,900"]
                })
                st.dataframe(df_cap, use_container_width=True, hide_index=True)
            with col_supp2:
                st.subheader("📌 Debt Service & Owner Cash Flow")
                df_dflow = pd.DataFrame({
                    "Category": ["Total Annual Principal & Interest", "Total Annual Owner Withdrawals"],
                    "2018 ($)": ["$972,900", "$0"],
                    "2019 ($)": ["$1,200,000", "$105,000"]
                })
                st.dataframe(df_dflow, use_container_width=True, hide_index=True)

        tab_idx += 1

        # TAB 4: BALANCE SHEET USING NATIVE STREAMLIT DATAFRAMES
        with tabs[tab_idx]:
            st.header(f"Balance Sheet Summary: {farm_data['name']}")
            st.caption("Fair Market Value Statement as of December 31 (Dairy Challenge Format)")

            df_bs = pd.DataFrame({
                "Balance Sheet Line Item": [
                    "--- CURRENT ASSETS ---",
                    "Cash and Savings",
                    "Accounts Receivable",
                    "Homegrown Feed Inventory",
                    "Purchased Feed Inventory & Prepaids",
                    "TOTAL CURRENT ASSETS",
                    "--- INTERMEDIATE ASSETS ---",
                    "Breeding Livestock (Dairy Herd)",
                    "Equipment and Farm Vehicles",
                    "TOTAL INTERMEDIATE ASSETS",
                    "--- LONG TERM ASSETS ---",
                    "Farm Real Estate, Land & Buildings",
                    "TOTAL LONG TERM ASSETS",
                    "=== TOTAL ASSETS ===",
                    "--- CURRENT LIABILITIES ---",
                    "Accounts Payable & Operating Loans",
                    "Current Portion of Term Debt",
                    "TOTAL CURRENT LIABILITIES",
                    "--- NON-CURRENT LIABILITIES ---",
                    "Remaining Intermediate & Long Term Debt Principal",
                    "TOTAL NON-CURRENT LIABILITIES",
                    "=== TOTAL LIABILITIES ===",
                    "🏆 NET WORTH (OWNER EQUITY)"
                ],
                "2018 Prior Year ($)": [
                    "", "$2,100,000", "$1,125,000", "$598,500", "$638,000", "$4,461,500",
                    "", "$3,120,000", "$6,800,070", "$9,920,070",
                    "", "$7,320,000", "$7,320,000",
                    "$21,701,570",
                    "", "$2,963,800", "$835,600", "$3,799,400",
                    "", "$831,200", "$831,200",
                    "$4,630,600",
                    "$17,070,970"
                ],
                "2019 Current Year ($)": [
                    "", "$2,200,000", "$1,100,000", "$600,000", "$600,000", "$4,500,000",
                    "", "$3,000,000", "$7,000,000", "$10,000,000",
                    "", "$8,000,000", "$8,000,000",
                    "$22,500,000",
                    "", "$3,150,000", "$1,000,000", "$4,150,000",
                    "", "$1,050,000", "$1,050,000",
                    "$5,200,000",
                    "$17,300,000"
                ]
            })
            st.dataframe(df_bs, use_container_width=True, hide_index=True)

        tab_idx += 1

        # TAB 5: CASH FLOW STATEMENT USING NATIVE WIDGETS & DATAFRAME
        with tabs[tab_idx]:
            st.header(f"Cash Flow & Debt Service Summary: {farm_data['name']}")
            st.caption("Operating Cash Flow & Debt Coverage Ratios")

            df_cf = pd.DataFrame({
                "Cash Flow & Coverage Metric": [
                    "Net Farm Profit / Operating Profit",
                    "Add back: Depreciation (Non-cash expense)",
                    "Less: Estimated Family Living & Taxes",
                    "Net Operating Cash Available for Debt Service",
                    "Annual Principal & Interest Debt Service",
                    "Debt Service Coverage Ratio (DSCR)",
                    "Net Free Cash Flow After Debt Service"
                ],
                "2018 Prior Year": ["$2,094,300", "+$388,600", "-$0", "$2,482,900", "$972,900", "2.55x", "+$1,510,000"],
                "2019 Current Year": ["$1,500,000", "+$385,000", "-$105,000", "$1,780,000", "$1,200,000", "1.48x", "+$580,000"]
            })
            st.dataframe(df_cf, use_container_width=True, hide_index=True)

            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric(label="2019 Operating Cash Available", value="$1,780,000")
            with m_col2:
                st.metric(label="2019 Debt Service Coverage Ratio (DSCR)", value="1.48x", delta="Bench: >1.25x")
            with m_col3:
                st.metric(label="Net Free Cash Flow", value="+$580,000")
        tab_idx += 1
