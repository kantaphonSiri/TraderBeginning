import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & STYLES ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS สำหรับคนสไตล์เท่
st.markdown("""
    <style>
    /* ปรับแต่งพื้นหลังและฟอนต์ */
    .stApp { background-color: #0b0e11; color: #e9eaeb; }
    
    /* สไตล์ Card สำหรับ Metric */
    div[data-testid="stMetricValue"] { font-size: 28px; color: #00ff88 !important; }
    div[data-testid="stMetricDelta"] { font-size: 16px; }
    
    /* ตกแต่งตาราง */
    .styled-table { border-radius: 10px; overflow: hidden; border: 1px solid #30363d; }
    
    /* ส่วนหัว Expander */
    .st-ae { background-color: #161b22 !important; border: 1px solid #30363d !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CORE FUNCTIONS ---
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        rate = data['Close'].iloc[-1]
        val = rate.iloc[0] if hasattr(rate, 'iloc') else rate
        return float(val)
    except: return 35.50

def get_news_cards(symbol):
    try:
        coin = symbol.split('-')[0]
        feed = feedparser.parse(f"https://www.newsbtc.com/search/{coin}/feed/")
        return feed.entries[:2] if feed.entries else []
    except: return []

# --- 3. DATA INITIALIZATION ---
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

# (จำลองข้อมูลพอร์ต หรือดึงจาก GSheet เดิมของเจ้านาย)
# สมมติสถานะปัจจุบัน
current_bal = 1250.45 
hunting_symbol = "ETH-USD"
entry_price = 82500.0

# --- 4. TOP BAR (KPI OVERVIEW) ---
st.write(f"### 🦔 PEPPER HUNTER")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("PORTFOLIO VALUE", f"{current_bal:,.2f} ฿", "12.5% ↑")
with c2:
    st.metric("USD/THB RATE", f"{live_rate:.2f}", "-0.05 ↓")
with c3:
    status = "🔴 BUSY" if hunting_symbol else "🟢 IDLE"
    st.metric("BOT STATUS", status)
with c4:
    st.metric("ACTIVE SCAN", "8 PAIRS")

st.divider()

# --- 5. MAIN HUB ---
col_main, col_side = st.columns([2.5, 1])

with col_main:
    # --- ACTIVE TRADE SECTION ---
    if hunting_symbol:
        st.subheader(f"⚡ CURRENT MISSION: {hunting_symbol}")
        # ดึงข้อมูลกราฟละเอียด
        hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
        hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
        cur_p = float(hist['Close'].iloc[-1]) * live_rate
        pnl = ((cur_p - entry_price) / entry_price) * 100
        pnl_color = "green" if pnl >= 0 else "red"
        
        # กราฟเท่ๆ
        st.area_chart(hist['Close'] * live_rate, height=300, color="#00ff88" if pnl >=0 else "#ff4b4b")
    else:
        st.info("📡 Scanning for high-probability entries...")

    # --- RADAR TABLE ---
    st.subheader("🔍 MARKET RADAR")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD"]
    # (ประมวลผลข้อมูลเหมือนเดิม)
    # ... [โค้ดดึงข้อมูล Radar เดิม] ...
    # สมมติ df_radar คือตารางที่เตรียมไว้แล้ว
    # st.dataframe(df_radar...) 

with col_side:
    st.subheader("📰 INTELLIGENCE")
    if hunting_symbol:
        news_items = get_news_cards(hunting_symbol)
        for news in news_items:
            with st.container():
                st.markdown(f"""
                <div style="background-color: #161b22; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #00ff88;">
                    <small style="color: #888;">{news.published[:16]}</small><br>
                    <b>{news.title[:60]}...</b><br>
                    <a href="{news.link}" style="color: #00ff88; font-size: 12px;">Read Intelligence</a>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.write("No active mission news.")
    
    st.divider()
    st.subheader("🛠 CONTROL")
    if st.button("🚀 EXECUTE FORCE SYNC", use_container_width=True):
        st.rerun()
    st.button("🛑 EMERGENCY STOP", use_container_width=True)

# --- 6. FOOTER REFRESH ---


progress_text = "Wait for next scan cycle..."
my_bar = st.progress(0, text=progress_text)
for percent_complete in range(100):
    time.sleep(0.01)
    my_bar.progress(percent_complete + 1, text=progress_text)

time.sleep(295)
st.rerun()
