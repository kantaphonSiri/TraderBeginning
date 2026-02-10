import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
import numpy as np
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from textblob import TextBlob
from datetime import datetime, timedelta, timezone

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="Pepper Hunter - Eternal AI", layout="wide")

# --- 2. ฟังก์ชันสนับสนุน ---

def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sh = client.open("Blue-chip Bet")
        return sh.worksheet("trade_learning")
    except Exception as e:
        st.error(f"❌ เชื่อมต่อ Sheet ไม่ได้: {e}")
        return None

def get_bot_status(sheet):
    """เช็คสถานะจากช่อง K1 (Column 11)"""
    try:
        val = sheet.cell(1, 11).value
        return val == "ON"
    except: return False

def set_bot_status(sheet, status):
    """บันทึกสถานะลงช่อง K1"""
    try:
        val = "ON" if status else "OFF"
        sheet.update_cell(1, 11, val)
    except: pass

def get_top_30_tickers():
    return [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "LINK-USD", "AVAX-USD",
        "POL-USD", "TRX-USD", "SHIB-USD", "LTC-USD", "BCH-USD", "UNI-USD", "NEAR-USD", "APT-USD", "DAI-USD",
        "STX-USD", "FIL-USD", "ARB-USD", "ETC-USD", "IMX-USD", "FTM-USD", "RENDER-USD", "SUI-USD", "OP-USD", "PEPE-USD", "HBAR-USD"
    ]

# --- ฟังก์ชันวิเคราะห์ AI ---
def analyze_coin_ai(symbol, df_history):
    try:
        df = df_history.copy()
        if len(df) < 50: return None
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X.values, y.values)
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        rsi_val = float(last_row['RSI_14'].iloc[0])
        ema20 = float(last_row['EMA_20'].iloc[0])
        ema50 = float(last_row['EMA_50'].iloc[0])
        pred_p = model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0]
        
        score = 0
        if cur_p > ema20 > ema50: score += 50
        if 40 < rsi_val < 65: score += 30
        if pred_p > cur_p: score += 20
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": score}
    except: return None

# --- 3. UI & Logic ---

sheet = init_gsheet()
current_bal = 1000.0
df_perf = pd.DataFrame()

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        if not df_perf.empty and 'Balance' in df_perf.columns:
            current_bal = float(df_perf.iloc[-1]['Balance'])

# Sidebar
st.sidebar.title("🤖 Pepper Control")
init_money = st.sidebar.number_input("งบตั้งต้น (บาท)", value=1000.0)
profit_want = st.sidebar.number_input("กำไรที่ต้องการ (บาท)", value=10000.0)
rate = st.sidebar.number_input("USD/THB", value=35.0)

# เช็คสถานะบอทจาก Sheet เพื่อให้ Sync กันทุกเครื่อง
bot_active = get_bot_status(sheet)

if st.sidebar.button("START BOT" if not bot_active else "STOP BOT"):
    set_bot_status(sheet, not bot_active)
    st.rerun()

# Dashboard
st.title("🌶️ Pepper Hunter - AI Perpetual")
target_total = init_money + profit_want
profit_now = current_bal - init_money

c1, c2, c3 = st.columns(3)
c1.metric("งบปัจจุบัน", f"{current_bal:,.2f} ฿", f"{profit_now:,.2f} ฿")
c2.metric("เป้าหมายเส้นชัย", f"{target_total:,.2f} ฿")
c3.metric("สถานะ", "กำลังรันอยู่ 🟢" if bot_active else "หยุดพัก 🔴")

# Progress Bar
progress = min(max((current_bal - init_money) / profit_want, 0.0), 1.0)
st.progress(progress)
st.write(f"ความคืบหน้า: {progress*100:.2f}%")

if bot_active:
    if current_bal >= target_total:
        st.balloons()
        st.success("🏆 ถึงเป้าหมายกำไร 10,000 บาทแล้ว! ระบบหยุดทำงานอัตโนมัติ")
        set_bot_status(sheet, False)
    else:
        st.info("🔄 กำลังสแกนตลาดและวิเคราะห์โอกาสเทรด...")
        tickers = get_top_30_tickers()
        sample = random.sample(tickers, 5)
        for s_sym in sample:
            with st.status(f"วิเคราะห์ {s_sym}...", expanded=False):
                df_h = yf.download(s_sym, period="60d", interval="1d", progress=False)
                if not df_h.empty:
                    res = analyze_coin_ai(s_sym, df_h)
                    if res:
                        # ฟังก์ชัน run_auto_trade (ใช้ตัวแปรจากด้านบน)
                        from __main__ import run_auto_trade
                        run_auto_trade(res, sheet, current_bal, rate)
        time.sleep(10)
        st.rerun()

if not df_perf.empty:
    st.area_chart(df_perf['Balance'])
