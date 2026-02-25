import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. UI SETTINGS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stApp { background: #0e1117; color: #e9eaeb; }
.trade-card { background: #1c2128; border: 1px solid #30363d; border-radius: 10px; padding: 15px; margin-bottom: 10px; }
.status-hunting { color: #ff4b4b; font-weight: bold; }
.status-scanning { color: #00ff88; font-weight: bold; }
.ai-box { background: #1e293b; padding: 15px; border-radius: 10px; border-left: 5px solid #38bdf8; }
[data-testid="stMetricValue"] { font-size: 24px !important; color: #00ff88 !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNCTIONS ---
@st.cache_data(ttl=60)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1])
    except:
        return 35.50

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except:
        return None

# --- 3. LOGIC ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

current_total_bal = 1000.0
hunting_symbol = None
entry_p_thb = 0.0
next_invest = 1000.0
df_all = pd.DataFrame()
win_rate = 0.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            last_row = df_all.iloc[-1]
            current_total_bal = float(last_row.get('Balance', 1000))
            status = last_row.get('สถานะ')
            if status == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
                entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
    except:
        pass

# --- 4. DASHBOARD ---
st.title("🦔 Pepper Hunter")

c1, c2, c3 = st.columns(3)
with c1: st.metric("Balance", f"{current_total_bal:,.2f} ฿")
with c2: st.metric("Live THB", f"฿{live_rate:.2f}")
with c3:
    st.markdown(f'<div class="trade-card">STATUS: {"HUNTING" if hunting_symbol else "SCANNING"}</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([2, 1])

with col_left:
    if hunting_symbol:
        st.subheader(f"🚀 Mission: {hunting_symbol}")
        st.info("Tracking price...")
    else:
        st.subheader("📈 Portfolio History")
        if not df_all.empty:
            st.line_chart(df_all['Balance'])

    # บรรทัดที่เคยมีปัญหา - ตรงนี้ผมจัดระดับ 4-space เป๊ะๆ
    st.write("#### 🔍 Market Intelligence Radar")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD"]
    radar_data = []
    for t in tickers:
        try:
            px = yf.download(t, period="1d", interval="1m", progress=False)['Close'].iloc[-1]
            radar_data.append({"Symbol": t, "Price (฿)": f"{px * live_rate:,.2f}"})
        except:
            continue
    if radar_data:
        st.table(pd.DataFrame(radar_data))

with col_right:
    st.subheader("🤖 AI Strategist")
    st.markdown('<div class="ai-box">System is ready for next trade.</div>', unsafe_allow_html=True)

st.divider()
if st.button("🔄 Sync"):
    st.rerun()

time.sleep(300)
st.rerun()
