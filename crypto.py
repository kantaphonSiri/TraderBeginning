import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & UI ---
st.set_page_config(page_title="Pepper Hunter Pro", layout="wide")

# --- 2. OPTIMIZED DATA FUNCTIONS ---

@st.cache_data(ttl=300) # ปรับเป็น 5 นาที เพราะค่าเงินไม่เปลี่ยนไวมาก ลด Load API
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1].item()) if not data.empty else 35.50
    except: return 35.50

@st.cache_data(ttl=60) # แคชข้อมูลราคา 60 วินาที ป้องกันการรัว API
def get_crypto_prices(symbols):
    try:
        # ดึงทีเดียวเป็นกลุ่ม (Batch Download) ลดจำนวน Request ได้มหาศาล
        data = yf.download(symbols, period="1d", interval="1m", progress=False)['Close']
        return data.iloc[-1]
    except: return None

# --- ส่วนที่เหลือของโค้ดให้คงเดิมตามตรรกะเดิมของคุณ ---
# ... (ส่วนเชื่อมต่อ GSheet และคำนวณ Kelly) ...

# --- 3. OPTIMIZED RADAR ---
st.write("#### 🔍 Market Intelligence Radar")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "AVAX-USD"]
prices = get_crypto_prices(tickers)

if prices is not None:
    radar_df = []
    for t in tickers:
        # ตรวจสอบว่ามีข้อมูลเหรียญนั้นๆ ไหม
        val = prices[t] if t in prices else 0
        radar_df.append({"Symbol": t, "Price (฿)": f"{val * live_rate:,.2f}"})
    st.table(pd.DataFrame(radar_df))

# --- 4. AUTO REFRESH ---
# แนะนำให้ใช้ปุ่ม Sync เป็นหลัก หรือตั้งเวลาที่เหมาะสม (เช่น 5-10 นาที)
st.info(f"Last Sync: {datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
