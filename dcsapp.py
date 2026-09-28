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
# ==============================================================================
HARDCODED_GEMINI_API_KEY = "AQ.Ab8RN6Lw10ZXFxckakab9zIo1hmJptZ6sRUxsYcivchEPAbHgQ"

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
    
    # Auto-migrate existing database tables created under previous schemas
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
    
    # 1. Look for 'Perfect.' or 'Final Answer:' marker
    match_perfect = re.search(r'(?:Perfect\.|Final Answer:)\s*(.*)$', text, re.DOTALL | re.IGNORECASE)
    if match_perfect and len(match_perfect.group(1).strip()) > 10:
        text = match_perfect.group(1).strip()
    else:
        # Filter out lines containing meta/planning keywords
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        filtered = []
        for p in paragraphs:
            if re.search(r'^(User|Student|Greeting|Character|Goal|Tone|Check Constraints|Wait,|No headers|No labels|No quotes|2-4 conversational|Check:|Constraints:|Persona:|\*|Dan:|Farmer:)', p, re.IGNORECASE):
                continue
            filtered.append(p)
        if filtered:
            text = " ".join(filtered)
            
    # Clean up markdown headers or outer quotes
    text = re.sub(r'^#+\s*', '', text)
    if text.startswith('"') and text.endswith('"') and len(text) > 2:
        text = text[1:-1].strip()
        
    # Strip verbatim question echo
    if user_prompt and text.lower().startswith(user_prompt.lower()):
        text = text[len(user_prompt):].strip()
        if text.startswith("?") or text.startswith(":"):
            text = text[1:].strip()
            
    if not text:
        text = "I'm doing alright, just staying busy between the cows and the 1,200 acres. Main thing is keeping the place profitable."
        
    return text

# --- STYLED HTML TABLE GENERATORS ---
def render_income_statement(inc_data):
    html = """
    <style>
        .fin-table { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #1e293b; margin-bottom: 25px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden; }
        .fin-table th { background-color: #0f172a; color: #ffffff; font-weight: 600; text-align: right; padding: 10px 14px; border-bottom: 2px solid #0284c7; }
        .fin-table th:first-child { text-align: left; }
        .fin-table td { padding: 8px 14px; border-bottom: 1px solid #f1f5f9; text-align: right; }
        .fin-table td:first-child { text-align: left; }
        .fin-sec-header { background-color: #f8fafc; font-weight: 700; color: #0f172a; border-top: 1px solid #cbd5e1; text-transform: uppercase; font-size: 13px; letter-spacing: 0.5px; }
        .fin-indent { padding-left: 28px !important; color: #334155; }
        .fin-total { font-weight: 700; background-color: #f1f5f9; border-top: 1px solid #94a3b8; border-bottom: 2px solid #475569; color: #0f172a; }
        .fin-grand-total { font-weight: 800; background-color: #e0f2fe; color: #0369a1; border-top: 2px solid #0284c7; border-bottom: 3px double #0284c7; font-size: 15px; }
    </style>
    <table class="fin-table">
        <thead>
            <tr>
                <th>Line Item</th>
                <th>2018 (Prior Year)</th>
                <th>2019 (Current Year)</th>
            </tr>
        </thead>
        <tbody>
            <tr class="fin-sec-header"><td colspan="3">Farm Revenues</td></tr>
            <tr><td class="fin-indent">Milk Sales</td><td>$14,280,300</td><td>$14,000,000</td></tr>
            <tr><td class="fin-indent">Raised Calf, Cow, & Cull Sales</td><td>$596,000</td><td>$485,000</td></tr>
            <tr><td class="fin-indent">Other Dairy Revenues</td><td>$350,000</td><td>$515,000</td></tr>
            <tr><td class="fin-indent">Non-Dairy Farm Revenues</td><td>$0</td><td>$0</td></tr>
            <tr class="fin-total"><td>Gross Income (Line F)</td><td>$15,226,300</td><td>$15,000,000</td></tr>

            <tr class="fin-sec-header"><td colspan="3">Dairy-Specific Operating Expenses</td></tr>
            <tr><td class="fin-indent">Bedding</td><td>$258,400</td><td>$264,000</td></tr>
            <tr><td class="fin-indent">Chemicals</td><td>$247,100</td><td>$53,000</td></tr>
            <tr><td class="fin-indent">Contract Heifer Raising</td><td>$783,000</td><td>$793,600</td></tr>
            <tr><td class="fin-indent">Purchased Feed Expense</td><td>$3,671,000</td><td>$3,744,000</td></tr>
            <tr><td class="fin-indent">Homegrown Feed Expenses</td><td>$2,643,500</td><td>$2,726,500</td></tr>
            <tr><td class="fin-indent">Fuel & Oil</td><td>$70,000</td><td>$60,600</td></tr>
            <tr><td class="fin-indent">Insurance</td><td>$151,300</td><td>$168,000</td></tr>
            <tr><td class="fin-indent">Labor (Wages, Payroll)</td><td>$1,737,200</td><td>$1,832,900</td></tr>
            <tr><td class="fin-indent">Milk Marketing (Hauling, Promotion)</td><td>$379,100</td><td>$385,000</td></tr>
            <tr><td class="fin-indent">Rent/Lease (Land & Equipment)</td><td>$549,500</td><td>$612,800</td></tr>
            <tr><td class="fin-indent">Repairs (Building & Equipment)</td><td>$101,500</td><td>$125,000</td></tr>
            <tr><td class="fin-indent">Supplies</td><td>$285,500</td><td>$309,000</td></tr>
            <tr><td class="fin-indent">Utilities</td><td>$696,800</td><td>$710,700</td></tr>
            <tr><td class="fin-indent">Veterinary, Medicine & Breeding</td><td>$421,400</td><td>$444,500</td></tr>
            <tr><td class="fin-indent">Other/Misc. Dairy Expenses</td><td>$520,600</td><td>$522,400</td></tr>

            <tr class="fin-sec-header"><td colspan="3">Non-Dairy-Specific Farm Expenses</td></tr>
            <tr><td class="fin-indent">Interest</td><td>$186,400</td><td>$200,000</td></tr>
            <tr><td class="fin-indent">Property Taxes</td><td>$41,100</td><td>$43,000</td></tr>
            <tr><td class="fin-indent">Depreciation (excl. Sec 179)</td><td>$388,600</td><td>$385,000</td></tr>
            <tr><td class="fin-indent">All Other Farm Expenses</td><td>$0</td><td>$120,000</td></tr>
            <tr class="fin-total"><td>Total Farm Expenses (Line I)</td><td>$13,132,000</td><td>$13,500,000</td></tr>

            <tr class="fin-grand-total"><td>Net Farm Profit Before Taxes (Line F - Line I)</td><td>$2,094,300</td><td>$1,500,000</td></tr>

            <tr class="fin-sec-header"><td colspan="3">Other Information & Owner Withdrawals</td></tr>
            <tr><td class="fin-indent">Total Annual Non-Farm Income</td><td>$0</td><td>$20,000</td></tr>
            <tr><td class="fin-indent">Total Annual Owner Withdrawals</td><td>$0</td><td>$105,000</td></tr>
            <tr><td class="fin-indent">Total Annual Principal & Interest Payments</td><td>$972,900</td><td>$1,200,000</td></tr>

            <tr class="fin-sec-header"><td colspan="3">Capital Purchases During Year</td></tr>
            <tr><td class="fin-indent">Machinery & Equipment</td><td>$50,000</td><td>$55,000</td></tr>
            <tr><td class="fin-indent">Buildings, Improvements & Facilities</td><td>$345,000</td><td>$319,900</td></tr>
        </tbody>
    </table>
    """
    return html

def render_balance_sheet(bs_data):
    html = """
    <style>
        .bs-table { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #1e293b; margin-bottom: 25px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden; }
        .bs-table th { background-color: #0f172a; color: #ffffff; font-weight: 600; text-align: right; padding: 10px 14px; border-bottom: 2px solid #16a34a; }
        .bs-table th:first-child { text-align: left; }
        .bs-table td { padding: 8px 14px; border-bottom: 1px solid #f1f5f9; text-align: right; }
        .bs-table td:first-child { text-align: left; }
        .bs-sec-header { background-color: #f8fafc; font-weight: 700; color: #0f172a; border-top: 1px solid #cbd5e1; text-transform: uppercase; font-size: 13px; letter-spacing: 0.5px; }
        .bs-indent { padding-left: 28px !important; color: #334155; }
        .bs-subtotal { font-weight: 700; background-color: #f1f5f9; border-top: 1px solid #94a3b8; border-bottom: 2px solid #475569; color: #0f172a; }
        .bs-grand-total { font-weight: 800; background-color: #dcfce7; color: #15803d; border-top: 2px solid #16a34a; border-bottom: 3px double #16a34a; font-size: 15px; }
    </style>
    <table class="bs-table">
        <thead>
            <tr>
                <th>Balance Sheet Category (Fair Market Value as of Dec 31)</th>
                <th>2018 (Prior Year)</th>
                <th>2019 (Current Year)</th>
            </tr>
        </thead>
        <tbody>
            <tr class="bs-sec-header"><td colspan="3">CURRENT ASSETS</td></tr>
            <tr><td class="bs-indent">Cash and Savings</td><td>$2,100,000</td><td>$2,200,000</td></tr>
            <tr><td class="bs-indent">Accounts Receivable</td><td>$1,125,000</td><td>$1,100,000</td></tr>
            <tr><td class="bs-indent">Homegrown Feed Inventory</td><td>$598,500</td><td>$600,000</td></tr>
            <tr><td class="bs-indent">Purchased Feed Inventory</td><td>$80,000</td><td>$100,000</td></tr>
            <tr><td class="bs-indent">Investment in Growing Crops</td><td>$98,000</td><td>$100,000</td></tr>
            <tr><td class="bs-indent">Prepaid Expenses</td><td>$460,000</td><td>$400,000</td></tr>
            <tr class="bs-subtotal"><td>TOTAL CURRENT ASSETS</td><td>$4,461,500</td><td>$4,500,000</td></tr>

            <tr class="bs-sec-header"><td colspan="3">INTERMEDIATE ASSETS</td></tr>
            <tr><td class="bs-indent">Breeding Livestock - Dairy</td><td>$3,120,000</td><td>$3,000,000</td></tr>
            <tr><td class="bs-indent">Equipment and Farm Vehicles</td><td>$6,800,070</td><td>$7,000,000</td></tr>
            <tr class="bs-subtotal"><td>TOTAL INTERMEDIATE ASSETS</td><td>$9,920,070</td><td>$10,000,000</td></tr>

            <tr class="bs-sec-header"><td colspan="3">LONG TERM ASSETS</td></tr>
            <tr><td class="bs-indent">Farm Real Estate & Improvements</td><td>$3,100,000</td><td>$3,200,000</td></tr>
            <tr><td class="bs-indent">Buildings and Facilities</td><td>$4,220,000</td><td>$4,800,000</td></tr>
            <tr class="bs-subtotal"><td>TOTAL LONG TERM ASSETS</td><td>$7,320,000</td><td>$8,000,000</td></tr>

            <tr class="bs-grand-total"><td>TOTAL ASSETS</td><td>$21,701,570</td><td>$22,500,000</td></tr>

            <tr class="bs-sec-header"><td colspan="3">CURRENT LIABILITIES</td></tr>
            <tr><td class="bs-indent">Accounts Payable</td><td>$308,800</td><td>$300,000</td></tr>
            <tr><td class="bs-indent">Operating Loan Balance</td><td>$2,630,000</td><td>$2,800,000</td></tr>
            <tr><td class="bs-indent">Accrued Interest (Operating & Term Debt)</td><td>$25,000</td><td>$50,000</td></tr>
            <tr><td class="bs-indent">Current Portion of Term Debt (due within 1 yr)</td><td>$835,600</td><td>$1,000,000</td></tr>
            <tr class="bs-subtotal"><td>TOTAL CURRENT LIABILITIES</td><td>$3,799,400</td><td>$4,150,000</td></tr>

            <tr class="bs-sec-header"><td colspan="3">NON-CURRENT LIABILITIES</td></tr>
            <tr><td class="bs-indent">Remaining Principal on Intermediate Loans</td><td>$182,600</td><td>$1,000,000</td></tr>
            <tr><td class="bs-indent">Remaining Principal on Long Term Loans</td><td>$648,600</td><td>$50,000</td></tr>
            <tr class="bs-subtotal"><td>TOTAL NON-CURRENT LIABILITIES</td><td>$831,200</td><td>$1,050,000</td></tr>

            <tr class="bs-subtotal"><td>TOTAL LIABILITIES</td><td>$4,630,600</td><td>$5,200,000</td></tr>

            <tr class="bs-grand-total"><td>NET WORTH (OWNER EQUITY)</td><td>$17,070,970</td><td>$17,300,000</td></tr>
        </tbody>
    </table>
    """
    return html

def render_cash_flow(cf_data):
    html = """
    <style>
        .cf-table { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #1e293b; margin-bottom: 25px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden; }
        .cf-table th { background-color: #0f172a; color: #ffffff; font-weight: 600; text-align: right; padding: 10px 14px; border-bottom: 2px solid #eab308; }
        .cf-table th:first-child { text-align: left; }
        .cf-table td { padding: 9px 14px; border-bottom: 1px solid #f1f5f9; text-align: right; }
        .cf-table td:first-child { text-align: left; font-weight: 600; }
        .cf-highlight { background-color: #fef9c3; color: #854d0e; font-weight: 700; border-top: 2px solid #eab308; border-bottom: 2px solid #eab308; }
    </style>
    <table class="cf-table">
        <thead>
            <tr>
                <th>Cash Flow & Debt Service Coverage Metric</th>
                <th>2018 (Prior Year)</th>
                <th>2019 (Current Year)</th>
            </tr>
        </thead>
        <tbody>
            <tr><td>Net Farm Income / Operating Profit</td><td>$2,094,300</td><td>$1,500,000</td></tr>
            <tr><td>Add back: Depreciation (Non-cash expense)</td><td>+$388,600</td><td>+$385,000</td></tr>
            <tr><td>Less: Estimated Income Taxes & Family Living</td><td>-$0</td><td>-$105,000</td></tr>
            <tr style="background-color: #f8fafc;"><td>Net Operating Cash Available for Debt Service</td><td>$2,482,900</td><td>$1,780,000</td></tr>
            <tr><td>Annual Principal & Interest Debt Payments</td><td>$972,900</td><td>$1,200,000</td></tr>
            <tr class="cf-highlight"><td>Debt Service Coverage Ratio (DSCR)</td><td>2.55x</td><td>1.48x</td></tr>
            <tr><td>Net Free Cash Flow After Debt Service</td><td>+$1,510,000</td><td>+$580,000</td></tr>
        </tbody>
    </table>
    """
    return html

def render_dhia_summary(dhia_data):
    html = """
    <style>
        .dhia-card { border: 2px solid #0284c7; border-radius: 8px; background-color: #ffffff; padding: 18px; font-family: 'Segoe UI', Arial, sans-serif; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .dhia-header { background-color: #0284c7; color: #ffffff; padding: 10px 15px; margin: -18px -18px 15px -18px; border-radius: 6px 6px 0 0; display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 16px; }
        .dhia-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 15px; margin-bottom: 15px; }
        .dhia-box { border: 1px solid #cbd5e1; border-radius: 6px; background-color: #f8fafc; padding: 12px; }
        .dhia-box-title { font-weight: 700; color: #0f172a; border-bottom: 2px solid #0284c7; padding-bottom: 4px; margin-bottom: 10px; font-size: 14px; text-transform: uppercase; }
        .dhia-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .dhia-table th { background-color: #e2e8f0; color: #1e293b; font-weight: 600; text-align: center; padding: 5px; border: 1px solid #cbd5e1; }
        .dhia-table td { text-align: center; padding: 5px; border: 1px solid #e2e8f0; background-color: #ffffff; }
        .dhia-warn { background-color: #fef08a !important; font-weight: 700; color: #854d0e; }
        .dhia-good { background-color: #dcfce7 !important; font-weight: 700; color: #15803d; }
    </style>
    <div class="dhia-card">
        <div class="dhia-header">
            <span>MINNESOTA DHIA - HERD SUMMARY REPORT (DHI-302)</span>
            <span>ST. PAUL DAIRY / SALFER DAIRY (Herd #41-62-7001)</span>
        </div>
        
        <div class="dhia-grid">
            <div class="dhia-box">
                <div class="dhia-box-title">📊 Peak & Persistency Summary (305 ME Milk)</div>
                <table class="dhia-table">
                    <thead>
                        <tr><th>Lactation</th><th>Cows</th><th>305 ME (lbs)</th><th>Peak Milk (lbs)</th><th>Peak DIM</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>1st Lactation</td><td>24</td><td>26,140</td><td class="dhia-warn">78 lbs</td><td>81</td></tr>
                        <tr><td>2nd Lactation</td><td>26</td><td>27,944</td><td>104 lbs</td><td>61</td></tr>
                        <tr><td>3rd+ Lactation</td><td>14</td><td>25,396</td><td>107 lbs</td><td>50</td></tr>
                        <tr style="font-weight:700; background-color:#f1f5f9;"><td>All Herd</td><td>64</td><td>26,710</td><td>96 lbs</td><td>65</td></tr>
                    </tbody>
                </table>
                <p style="font-size:12px; margin-top:8px; color:#475569;"><b>Peak Ratio (1st / Others):</b> <span class="dhia-warn">0.77</span> <i>(Indicates underperformance in 1st lactation heifers vs. mature cows)</i></p>
            </div>

            <div class="dhia-box">
                <div class="dhia-box-title">🦠 Somatic Cell Count (SCC) & Udder Health</div>
                <table class="dhia-table">
                    <thead>
                        <tr><th>Lactation</th><th>Avg LS</th><th>% LS 0-1</th><th>% LS 2-3</th><th>% LS 4-6</th><th>% LS 7-9</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>1st Lact</td><td>1.5</td><td>58%</td><td>32%</td><td>11%</td><td>0%</td></tr>
                        <tr><td>2nd Lact</td><td>1.9</td><td>50%</td><td>31%</td><td>13%</td><td class="dhia-warn">6%</td></tr>
                        <tr><td>3rd+ Lact</td><td>2.7</td><td>30%</td><td>30%</td><td class="dhia-warn">40%</td><td>0%</td></tr>
                        <tr style="font-weight:700; background-color:#f1f5f9;"><td>All Herd</td><td>1.9</td><td>49%</td><td>31%</td><td>18%</td><td>2%</td></tr>
                    </tbody>
                </table>
                <p style="font-size:12px; margin-top:8px; color:#b91c1c;"><b>Bulk Tank Raw SCC:</b> 280,000 cells/mL | <b>30-Day Milk Loss:</b> 2,163 lbs ($429 direct loss/mo)</p>
            </div>
        </div>

        <div class="dhia-grid">
            <div class="dhia-box">
                <div class="dhia-box-title">🧬 Reproduction & Fertility Performance</div>
                <table class="dhia-table">
                    <thead>
                        <tr><th>Metric</th><th>Cows</th><th>Heifers</th><th>Benchmark Goal</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>21-Day Pregnancy Rate</td><td class="dhia-warn">15%</td><td>-</td><td>20% - 24%</td></tr>
                        <tr><td>Heat Detection Index</td><td>44%</td><td>-</td><td>55%+</td></tr>
                        <tr><td>Conceived 1st Service</td><td>51%</td><td>55%</td><td>50%+</td></tr>
                        <tr><td>Services per Conception</td><td>1.7</td><td>1.8</td><td>&lt; 1.8</td></tr>
                        <tr><td>Calving Interval</td><td>12.3 mo</td><td>24.2 mo</td><td>12.5 mo</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="dhia-box">
                <div class="dhia-box-title">🚪 Herd Turnover & Culling Reasons</div>
                <table class="dhia-table">
                    <thead>
                        <tr><th>Culling Reason</th><th>% of Culls</th><th>Primary Driver</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>Reproductive Failure</td><td class="dhia-warn">42%</td><td>Delayed OvSynch / Missed Shots</td></tr>
                        <tr><td>Low Milk Production</td><td>18%</td><td>Heifer peak underperformance</td></tr>
                        <tr><td>Mastitis / High SCC</td><td>15%</td><td>Night shift pre-dip routine cut short</td></tr>
                        <tr><td>Died / Mortality</td><td>15%</td><td>Fresh cow transition issues</td></tr>
                        <tr><td>Other / Dairy Sale</td><td>10%</td><td>Voluntary cull</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """
    return html

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

# SCENARIO SELECTOR IN SIDEBAR
selected_farm_key = st.sidebar.selectbox("Select Farm Scenario:", list(st.session_state.farms.keys()))
farm_data = st.session_state.farms[selected_farm_key]

# --- SIDEBAR EXPANDER: INSTRUCTOR ADMIN PORTAL ---
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
    # BUILD TABS IN EXACT ORDER REQUESTED:
    # 1. Chat Interface
    # 2. Herd Summary (DHIA 302)
    # 3. Income Statement
    # 4. Balance Sheet
    # 5. Cash Flow Statement
    
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
        if not farm_data["show_financials"]: hidden_reports.append("Financial Statements (Income, Balance Sheet, Cash Flow)")
        if hidden_reports:
            st.warning(f"🔒 Note: The following reports are withheld by the producer: {', '.join(hidden_reports)}. You must ask permission during your interview to view them.")

        if not api_key:
            st.error("⚠️ Gemini API Key required to run chat.")
        else:
            genai.configure(api_key=api_key)

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

    # TAB 2: HERD SUMMARY (DHIA 302)
    if farm_data["show_dhia"]:
        with tabs[tab_idx]:
            st.header(f"Minnesota DHIA 302 Summary: {farm_data['name']}")
            st.caption("Official Minnesota DHIA DHI-302 Herd & Consultant Summary Format")
            st.markdown(render_dhia_summary(farm_data), unsafe_allow_html=True)
        tab_idx += 1

    # TAB 3: INCOME STATEMENT
    if farm_data["show_financials"]:
        with tabs[tab_idx]:
            st.header(f"Farm Income Statement: {farm_data['name']}")
            st.caption("Cash Basis 2-Year Comparative Statement (Dairy Challenge Format)")
            st.markdown(render_income_statement(farm_data), unsafe_allow_html=True)
        tab_idx += 1

        # TAB 4: BALANCE SHEET
        with tabs[tab_idx]:
            st.header(f"Balance Sheet Summary: {farm_data['name']}")
            st.caption("Fair Market Value Statement as of December 31 (Dairy Challenge Format)")
            st.markdown(render_balance_sheet(farm_data), unsafe_allow_html=True)
        tab_idx += 1

        # TAB 5: CASH FLOW STATEMENT
        with tabs[tab_idx]:
            st.header(f"Cash Flow & Debt Service Summary: {farm_data['name']}")
            st.caption("Operating Cash Flow & Debt Coverage Ratios")
            st.markdown(render_cash_flow(farm_data), unsafe_allow_html=True)
        tab_idx += 1
