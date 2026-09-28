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
# Paste your AIzaSy... key inside quotes below to hardcode permanently:
# ==============================================================================
HARDCODED_GEMINI_API_KEY = ""

# --- DATABASE SETUP (TRANSCRIPTS) ---
def init_db():
    conn = sqlite3.connect('transcripts.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            student_id TEXT,
            course TEXT,
            semester TEXT,
            farm_name TEXT,
            timestamp DATETIME,
            role TEXT,
            message TEXT
        )
    ''')
    conn.commit()
    
    try:
        c.execute('PRAGMA table_info(transcripts)')
        existing_cols = [row[1] for row in c.fetchall()]
        if 'course' not in existing_cols:
            c.execute('ALTER TABLE transcripts ADD COLUMN course TEXT DEFAULT "ANSC 4604"')
            conn.commit()
        if 'semester' not in existing_cols:
            c.execute('ALTER TABLE transcripts ADD COLUMN semester TEXT DEFAULT "Spring 2027"')
            conn.commit()
    except Exception as err:
        print(f"Database migration note: {err}")
    finally:
        conn.close()

init_db()

def log_message(student_name, student_id, course, semester, farm_name, role, message):
    try:
        conn = sqlite3.connect('transcripts.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''
            INSERT INTO transcripts (student_name, student_id, course, semester, farm_name, timestamp, role, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (student_name, student_id, course, semester, farm_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), role, message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Transcript logging exception caught: {e}")

def get_transcripts():
    conn = sqlite3.connect('transcripts.db', check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM transcripts ORDER BY timestamp ASC", conn)
    conn.close()
    return df

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


def configure_gemini_api(key_or_token):
    if not key_or_token:
        return False
    k = key_or_token.strip()
    if k.startswith("AQ.") or k.startswith("ya29."):
        try:
            import google.oauth2.credentials
            creds = google.oauth2.credentials.Credentials(token=k)
            genai.configure(credentials=creds, api_key=None)
            return True
        except Exception as e:
            print(f"OAuth configuration note: {e}")
            try:
                genai.configure(api_key=k)
                return True
            except Exception:
                return False
    else:
        try:
            genai.configure(api_key=k)
            return True
        except Exception as e:
            print(f"API key configuration note: {e}")
            try:
                import google.oauth2.credentials
                creds = google.oauth2.credentials.Credentials(token=k)
                genai.configure(credentials=creds, api_key=None)
                return True
            except Exception:
                return False

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

CRITICAL DIALOGUE & FORMATTING RULES:
- NEVER repeat or echo the user's question back.
- NEVER output character notes, planning thoughts, headers, checklists, or labels like "Goal:", "User:", or "Dan:".
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

with st.sidebar.expander("🔒 Instructor Admin Portal"):
    admin_pass = st.text_input("Instructor Password:", type="password", key="admin_pwd_key")
    if admin_pass == "dairy123":
        st.success("Authenticated")        
        st.markdown("#### 📑 Report Visibility")
        farm_data["show_dhia"] = st.checkbox("Show DHIA 302 Summary", value=farm_data["show_dhia"])
        farm_data["show_financials"] = st.checkbox("Show Financial Statements", value=farm_data["show_financials"])
        
        st.markdown("---")
        st.markdown("#### 📋 Student Transcripts")
        df_logs = get_transcripts()
        if df_logs.empty:
            st.info("No logs recorded yet.")
        else:
            students = df_logs["student_name"].unique()
            selected_student = st.selectbox("Select Student:", students)
            student_df = df_logs[df_logs["student_name"] == selected_student]
            st.dataframe(student_df[["timestamp", "role", "message"]], use_container_width=True)
            
            csv_data = df_logs.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download All CSV",
                data=csv_data,
                file_name="dairy_consulting_student_transcripts.csv",
                mime="text/csv"
            )
    elif admin_pass:
        st.error("Incorrect Password")

if not api_key:
    st.sidebar.warning("⚠️ API Key not detected. Enter fallback key below:")
    api_key = st.sidebar.text_input("Gemini API Key:", type="password")

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
            st.error("⚠️ Gemini API Key required to run chat.")
        else:
            configure_gemini_api(api_key)

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

    # TAB 2: EXPANDED 11-SECTION DHIA 302 HERD SUMMARY
    if farm_data["show_dhia"]:
        with tabs[tab_idx]:
            st.header(f"Minnesota DHIA 302 Herd Summary: {farm_data['name']}")
            st.caption("Official Minnesota DHIA DHI-302 Herd & Consultant Summary (11 Complete Benchmark Sections)")
            
            # 1. Operational Overview
            st.subheader("1. Facility & Operational Overview")
            df_overview = pd.DataFrame({
                "Parameter": ["Location", "Management", "Herd Size & Breed", "Housing Setup", "Milking Setup", "Milking Frequency", "Milk Price", "Crop Acres"],
                "Details": ["Central Minnesota", "Dan Salfer (Owner-Operator)", "500 Lactating Holsteins (100% HO)", "6-Row Freestall, Deep Sand Stalls", "Double-12 Parallel Parlor", "3x per day (6 AM, 2 PM, 10 PM)", "$20.50 / cwt", "1,200 Acres (75% Feed Grown)"]
            })
            st.dataframe(df_overview, use_container_width=True, hide_index=True)

            # 2. Peak & Persistency Summary
            st.subheader("2. Peak & Persistency Summary (305 ME Milk)")
            df_peak = pd.DataFrame({
                "Lactation Group": ["1st Lactation", "2nd Lactation", "3rd+ Lactation", "Overall Herd"],
                "Cows Count": [24, 26, 14, 64],
                "305 ME Milk (lbs)": ["26,140", "27,944", "25,396", "26,710"],
                "Peak Milk (lbs)": ["78 (Underperforming)", "104", "107", "96"],
                "Peak DIM": [81, 61, 50, 65],
                "Current MLM (lbs)": ["72", "94", "88", "84"]
            })
            st.dataframe(df_peak, use_container_width=True, hide_index=True)
            st.warning("⚠️ **Peak Ratio (1st / Others): 0.77** (Goal: > 0.80) — Indicates underperformance in 1st lactation heifers relative to mature cows.")

            # 3. Management Level Milk (MLM)
            st.subheader("3. Management Level Milk (MLM) Summary")
            df_mlm = pd.DataFrame({
                "DIM Bracket": ["< 100 DIM", "100 - 200 DIM", "> 200 DIM", "Overall Herd Average"],
                "Annual Summary MLM (lbs)": ["88 lbs", "82 lbs", "74 lbs", "81 lbs"],
                "Current Test Day MLM (lbs)": ["86 lbs", "80 lbs", "72 lbs", "79 lbs"]
            })
            st.dataframe(df_mlm, use_container_width=True, hide_index=True)

            # 4. Udder Health & Current SCC Evaluation
            st.subheader("4. Somatic Cell Count (SCC) Evaluation & Yearly Summary")
            df_scc = pd.DataFrame({
                "Lactation Group": ["1st Lactation", "2nd Lactation", "3rd+ Lactation", "Overall Herd"],
                "Average Linear Score": ["1.5", "1.9", "2.7", "1.9"],
                "% LS 0-1 (Healthy)": ["58%", "50%", "30%", "49%"],
                "% LS 2-3 (Moderate)": ["32%", "31%", "30%", "31%"],
                "% LS 4-6 (High SCC)": ["11%", "13%", "40%", "18%"],
                "% LS 7-9 (Severe Infection)": ["0%", "6%", "0%", "2%"]
            })
            st.dataframe(df_scc, use_container_width=True, hide_index=True)
            st.error("🚨 **Bulk Tank Raw SCC:** 280,000 cells/mL | **30-Day Milk Loss:** 2,163 lbs ($429 monthly direct loss on test day).")

            # 5. Changes in SCC Status
            st.subheader("5. Changes in Somatic Cell Status (Cures, Chronics, & New Infections)")
            col_scc1, col_scc2 = st.columns(2)
            with col_scc1:
                st.markdown("**Annual Summary (Fresh vs. Dry Off)**")
                df_scc_annual = pd.DataFrame({
                    "SCC Status Category": ["Cured (Infected -> Healthy)", "Chronic (Infected -> Infected)", "Negative (Healthy -> Healthy)", "New Infection (Healthy -> Infected)"],
                    "Percentage of Herd": ["10%", "7%", "79%", "4%"]
                })
                st.dataframe(df_scc_annual, use_container_width=True, hide_index=True)
            with col_scc2:
                st.markdown("**Test Day Summary (Current vs. Last Test)**")
                df_scc_test = pd.DataFrame({
                    "SCC Status Category": ["Cured (Infected -> Healthy)", "Chronic (Infected -> Infected)", "Negative (Healthy -> Healthy)", "New Infection (Healthy -> Infected)"],
                    "Percentage of Herd": ["7%", "7%", "82%", "7%"]
                })
                st.dataframe(df_scc_test, use_container_width=True, hide_index=True)

            # 6. Monthly Production Averages (12-Month Test History)
            st.subheader("6. Monthly Production Averages (12-Month Test Day History)")
            df_history = pd.DataFrame({
                "Test Date": ["09/03/26", "08/02/26", "07/01/26", "06/02/26", "05/01/26", "04/02/26", "03/01/26", "02/02/26", "01/03/26", "12/01/25", "11/02/25", "10/01/25"],
                "Rolling Milk (lbs)": ["26,500", "26,450", "26,300", "26,200", "26,100", "26,000", "25,950", "25,900", "25,850", "25,800", "25,750", "25,700"],
                "Test Milk (lbs)": ["84", "85", "82", "81", "83", "84", "85", "83", "82", "81", "80", "82"],
                "Fat %": ["4.8%", "4.7%", "4.6%", "4.5%", "4.6%", "4.7%", "4.8%", "4.8%", "4.7%", "4.6%", "4.6%", "4.7%"],
                "Protein %": ["3.4%", "3.4%", "3.3%", "3.3%", "3.4%", "3.4%", "3.5%", "3.5%", "3.4%", "3.4%", "3.3%", "3.4%"],
                "Raw SCC": ["280k", "265k", "250k", "240k", "230k", "220k", "210k", "205k", "195k", "190k", "185k", "184k"],
                "% LS > 4.0": ["20%", "18%", "16%", "15%", "14%", "13%", "12%", "11%", "10%", "10%", "9%", "9%"]
            })
            st.dataframe(df_history, use_container_width=True, hide_index=True)

            # 7. Herd Genetic Profile (CDCB)
            st.subheader("7. Herd Genetic Profile (Source: CDCB)")
            df_genetics = pd.DataFrame({
                "Animal Group": ["Service Sires", "Calves (<1 yr)", "Yearlings (1-2 yrs)", "1st Lactation Cows", "2nd Lactation Cows", "3rd+ Lactation Cows"],
                "Animal PTA NM$ ($)": ["+$620", "+$480", "+$420", "+$350", "+$280", "+$190"],
                "Animal NM$ % Rank": ["85%", "78%", "72%", "65%", "54%", "41%"],
                "Sire PTA NM$ ($)": ["+$710", "+$610", "+$550", "+$480", "+$390", "+$310"],
                "Sire NM$ % Rank": ["91%", "84%", "79%", "71%", "62%", "50%"]
            })
            st.dataframe(df_genetics, use_container_width=True, hide_index=True)

            # 8. Reproduction Summary & Animal Inventory
            st.subheader("8. Animal Inventory & Detailed Reproduction Summary")
            col_rep1, col_rep2 = st.columns(2)
            with col_rep1:
                st.markdown("**Animal Inventory Demographics**")
                df_inv = pd.DataFrame({
                    "Age / Status Group": ["Lactating Cows", "Dry Cows", "Heifers (12-24 mo)", "Calves (<12 mo)", "Total Herd Head"],
                    "Head Count": [500, 60, 210, 180, 950],
                    "% Of Herd": ["53%", "6%", "22%", "19%", "100%"],
                    "% Sire/Dam Identified": ["98%", "96%", "99%", "100%", "98%"]
                })
                st.dataframe(df_inv, use_container_width=True, hide_index=True)

            with col_rep2:
                st.markdown("**Reproduction Benchmarks**")
                df_repro = pd.DataFrame({
                    "Reproductive Parameter": ["21-Day Pregnancy Rate", "Heat Detection Index", "Services per Conception", "Conceived 1st Service", "Voluntary Waiting Period (VWP)", "Calving Interval"],
                    "Current Herd Level": ["15% (Goal: >20%)", "44%", "1.7 (Cows) | 1.8 (Heifers)", "51%", "60 Days", "12.3 Months"]
                })
                st.dataframe(df_repro, use_container_width=True, hide_index=True)

            # 9. Cows Entering & Leaving the Herd / Culling Reasons
            st.subheader("9. Cows Entering & Leaving the Herd / Culling Reasons")
            df_cull = pd.DataFrame({
                "Primary Culling Reason": ["Reproductive Failure (Delayed Shots)", "Low Milk Production", "Mastitis / High SCC", "Mortality / Died", "Dairy Sale / Voluntary"],
                "% Of Total Culls": ["42%", "18%", "15%", "15%", "10%"],
                "Primary Root Cause": ["Timed-AI delayed 24-48 hrs during crop work", "1st lactation peak underperformance (78 lbs)", "Night shift pre-dip contact time cut to 10s", "Fresh cow metabolic/transition issues", "Voluntary herd management"]
            })
            st.dataframe(df_cull, use_container_width=True, hide_index=True)

            # 10. Early Culling (<60 DIM) & Birth Summary
            st.subheader("10. Early Culling (<60 DIM) & Birth Summary")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.markdown("**Early Exit Breakdown (<60 DIM)**")
                df_early = pd.DataFrame({
                    "Lactation Group": ["1st Lactation", "2nd Lactation", "3rd+ Lactation", "Overall Herd"],
                    "% Leaving <60 DIM": ["3.2%", "5.1%", "9.4%", "5.8%"]
                })
                st.dataframe(df_early, use_container_width=True, hide_index=True)
            with col_b2:
                st.markdown("**Birth Summary (Last 12 Months)**")
                df_birth = pd.DataFrame({
                    "Category": ["Bull Calves Born Live", "Heifer Calves Born Live", "Stillborn / Dead at Birth", "Calving Difficulty Score 1-2 (Normal)"],
                    "Count / %": ["235", "248", "18 (3.6%)", "94%"]
                })
                st.dataframe(df_birth, use_container_width=True, hide_index=True)

            # 11. Monthly Herd Turnover History
            st.subheader("11. Monthly Herd Turnover & Inventory History (12 Months)")
            df_turnover = pd.DataFrame({
                "Month": ["Sep 26", "Aug 26", "Jul 26", "Jun 26", "May 26", "Apr 26", "Mar 26", "Feb 26", "Jan 26", "Dec 25", "Nov 25", "Oct 25"],
                "Total Cows": [560, 558, 555, 552, 550, 548, 545, 542, 540, 538, 535, 532],
                "Milking Cows": [500, 498, 495, 492, 490, 488, 485, 482, 480, 478, 475, 472],
                "Cows Calved": [42, 40, 38, 45, 44, 41, 39, 37, 36, 35, 38, 40],
                "Cows Left": [14, 15, 12, 16, 14, 13, 12, 11, 10, 12, 11, 13]
            })
            st.dataframe(df_turnover, use_container_width=True, hide_index=True)

        tab_idx += 1

    # TAB 3: INCOME STATEMENT
    if farm_data["show_financials"]:
        with tabs[tab_idx]:
            st.header(f"Farm Income Statement: {farm_data['name']}")
            st.caption("Cash Basis 2-Year Comparative Statement (Dairy Challenge Format)")
            df_inc = pd.DataFrame({
                "Line Item": ["Milk Sales", "Raised Calf & Cull Sales", "Gross Income (Line F)", "Purchased Feed Expense", "Homegrown Feed Expense", "Labor & Payroll", "Vet, Med & Breeding", "Milk Marketing & Hauling", "Repairs, Fuel & Crop Inputs", "Interest Expense", "Property Taxes", "Depreciation", "Total Expenses (Line I)", "Net Profit Before Taxes"],
                "2018 ($)": ["$14,280,300", "$596,000", "$15,226,300", "$3,671,000", "$2,643,500", "$1,737,200", "$421,400", "$379,100", "$610,000", "$186,400", "$41,100", "$388,600", "$13,132,000", "$2,094,300"],
                "2019 ($)": ["$14,000,000", "$485,000", "$15,000,000", "$3,744,000", "$2,726,500", "$1,832,900", "$444,500", "$385,000", "$641,250", "$200,000", "$43,000", "$385,000", "$13,500,000", "$1,500,000"]
            })
            st.dataframe(df_inc, use_container_width=True, hide_index=True)
        tab_idx += 1

        # TAB 4: BALANCE SHEET
        with tabs[tab_idx]:
            st.header(f"Balance Sheet Summary: {farm_data['name']}")
            st.caption("Fair Market Value Statement as of December 31 (Dairy Challenge Format)")
            df_bs = pd.DataFrame({
                "Category": ["Cash & Savings", "Accounts Receivable", "Feed Inventory", "Total Current Assets", "Breeding Livestock", "Machinery & Equipment", "Total Intermediate Assets", "Real Estate & Facilities", "TOTAL ASSETS", "Accounts Payable", "Operating Loan Balance", "Current Term Debt", "Total Current Liabilities", "Non-Current Term Debt", "TOTAL LIABILITIES", "NET WORTH (OWNER EQUITY)"],
                "2018 ($)": ["$2,100,000", "$1,125,000", "$678,500", "$4,461,500", "$3,120,000", "$6,800,070", "$9,920,070", "$7,320,000", "$21,701,570", "$308,800", "$2,630,000", "$835,600", "$3,799,400", "$831,200", "$4,630,600", "$17,070,970"],
                "2019 ($)": ["$2,200,000", "$1,100,000", "$700,000", "$4,500,000", "$3,000,000", "$7,000,000", "$10,000,000", "$8,000,000", "$22,500,000", "$300,000", "$2,800,000", "$1,000,000", "$4,150,000", "$1,050,000", "$5,200,000", "$17,300,000"]
            })
            st.dataframe(df_bs, use_container_width=True, hide_index=True)
        tab_idx += 1

        # TAB 5: CASH FLOW STATEMENT
        with tabs[tab_idx]:
            st.header(f"Cash Flow & Debt Service Summary: {farm_data['name']}")
            st.caption("Operating Cash Flow & Debt Coverage Ratios")
            df_cf = pd.DataFrame({
                "Metric": ["Net Farm Profit", "Add Back: Depreciation", "Less: Owner Living / Taxes", "Net Cash for Debt Service", "Annual Debt Service (P&I)", "Debt Service Coverage Ratio (DSCR)", "Net Free Cash Flow"],
                "2018 ($)": ["$2,094,300", "+$388,600", "-$0", "$2,482,900", "$972,900", "2.55x", "+$1,510,000"],
                "2019 ($)": ["$1,500,000", "+$385,000", "-$105,000", "$1,780,000", "$1,200,000", "1.48x", "+$580,000"]
            })
            st.dataframe(df_cf, use_container_width=True, hide_index=True)
        tab_idx += 1
