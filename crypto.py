import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & PROFESSIONAL DARK UI ---
st.set_page_config(page_title="Pepper Hunter", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background: #0e1117; color: #e9eaeb; }
    .trade-card {
        background: #1c2128;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .status-hunting { color: #ff4b4b; font-weight: bold; }
    .status-scanning { color: #00ff88; font-weight: bold; }
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00ff88 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CORE FUNCTIONS ---
@st.cache_data(ttl=60)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1])
    except: return 35.50

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- 3. DATA PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

# Init variables
current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
next_invest = 1000.0
recent_trades = pd.DataFrame()
win_rate = 0.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            df_all.columns = df_all.columns.str.strip()
            
            # ดึงไม้ปัจจุบัน
            last_row = df_all.iloc[-1]
            current_total_bal = float(last_row.get('Balance', 1000))
            status = last_row.get('สถานะ')
            hunting_symbol = last_row.get('เหรียญ')
            entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
            next_invest = float(last_row.get('เงินลงทุน(฿)', 1000))

            # คำนวณ Win Rate จากประวัติทั้งหมด
            closed_trades = df_all[df_all['สถานะ'] == 'CLOSED']
            if not closed_trades.empty:
                wins = closed_trades['กำไร%'].apply(lambda x: 1 if '-' not in str(x) and str(x) != '0%' else 0).sum()
                win_rate = (wins / len(closed_trades)) * 100
                recent_trades = closed_trades.tail(5)[['วันที่', 'เหรียญ', 'กำไร%', 'Balance']]

            # Auto-Exit Logic
            if status == 'HUNTING' and hunting_symbol:
                ticker = yf.download(hunting_symbol, period="1d", interval="1m", progress=False)
                if not ticker.empty:
                    cur_p = float(ticker['Close'].iloc[-1]) * live_rate
                    pnl = ((cur_p - entry_p_thb) / entry_p_thb) * 100
                    if pnl >= 5.0 or pnl <= -3.0:
                        new_bal = current_total_bal * (1 + (pnl / 100))
                        sheet.append_row([now_th.strftime("%Y-%m-%d %H:%M"), hunting_symbol, "CLOSED", entry_p_thb, next_invest, cur_p, f"{pnl:.2f}%", 0, new_bal, 0, "AUTO_EXIT", "DONE", "N/A", "System Close"])
                        st.rerun()
    except Exception as e:
        st.error(f"Data Error: {e}")

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter PRO")

# Top Metrics
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Balance", f"{current_total_bal:,.2f} ฿")
with c2:
    st.metric("Win Rate", f"{win_rate:.1f}%")
with c3:
    st.metric("Live USD/THB", f"฿{live_rate:.2f}")
with c4:
    status_html = f'<span class="status-hunting">HUNTING {hunting_symbol}</span>' if hunting_symbol else '<span class="status-scanning">SCANNING</span>'
    st.markdown(f'<div class="trade-card"><small>SYSTEM STATUS</small><br>{status_html}</div>', unsafe_allow_html=True)

# Main Section
col_left, col_right = st.columns([2, 1])

with col_left:
    if hunting_symbol:
        st.subheader(f"🚀 Active Trade: {hunting_symbol}")
        hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
        hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
        units = next_invest / entry_p_thb
        st.area_chart(hist['Close'] * live_rate * units, height=250)
    else:
        st.info("🔎 Bot is scanning for RSI opportunities... No active trade.")
        st.write("#### Market Intelligence Radar")
        # ใส่ตารางย่อของ Radar
        st.caption("Scanning BTC, ETH, SOL, NEAR, LINK...")

with col_right:
    st.subheader("📜 Recent History")
    if not recent_trades.empty:
        for _, row in recent_trades.iloc[::-1].iterrows():
            color = "#00ff88" if '-' not in str(row['กำไร%']) else "#ff4b4b"
            st.markdown(f"""
                <div style="border-left: 4px solid {color}; padding-left: 10px; margin-bottom: 10px; background: #1c2128;">
                    <small>{row['วันที่']}</small><br>
                    <b>{row['เหรียญ']}</b>: <span style="color:{color}">{row['กำไร%']}</span><br>
                    <small>Bal: {row['Balance']:,.0f} ฿</small>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.write("No closed trades yet.")

# Control & Footer
st.divider()
if st.button("🔄 Force Manual Sync"):
    st.rerun()

st.progress(0, text=f"Next Update in 5 mins... Last Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
