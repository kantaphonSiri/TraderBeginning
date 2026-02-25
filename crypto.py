import streamlit as st
import pandas as pd
import pandas_ta as ta # ต้องมีไลบรารีนี้ใน requirements.txt
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

# --- 2. AI & ML LOGIC (NEW SECTION) ---
def analyze_coin_potential(symbol, budget):
    try:
        # ดึงข้อมูลย้อนหลังเพื่อทำ Features
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty: return None
        
        # 1. คำนวณ RSI (หาจุด Oversold/Overbought)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 2. คำนวณ Volatility (ความผันผวน)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        last_rsi = df['RSI'].iloc[-1]
        last_price = df['Close'].iloc[-1]
        volatility = (df['ATR'].iloc[-1] / last_price) * 100 # % ความแกว่ง
        
        # AI Recommendation Logic (เบื้องต้น)
        score = 0
        if 30 <= last_rsi <= 45: score += 50  # จุดเก็บของที่ได้เปรียบ
        elif last_rsi < 30: score += 80       # Oversold จัดๆ น่าลุ้นเด้ง
        
        if volatility < 2.0: score += 20     # ความเสี่ยงต่ำ เหมาะกับงบจำกัด
        
        return {
            "Symbol": symbol,
            "Score": score,
            "RSI": round(last_rsi, 2),
            "Risk": "Low" if volatility < 1.5 else "High",
            "Action": "Strong Buy" if score > 70 else "Wait"
        }
    except: return None

# --- 3. CORE FUNCTIONS ---
@st.cache_data(ttl=300)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1].item()) if not data.empty else 35.50
    except: return 35.50

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- 4. DATA PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
current_total_bal = 1000.0
hunting_symbol = None
df_all = pd.DataFrame()

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
    except: pass

# --- 5. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🔍 AI Market Scanning")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "AVAX-USD", "LINK-USD", "AR-USD", "DOT-USD"]
    
    with st.spinner('AI is analyzing coins...'):
        recommendations = []
        for t in tickers:
            analysis = analyze_coin_potential(t, current_total_bal)
            if analysis: recommendations.append(analysis)
    
    if recommendations:
        rec_df = pd.DataFrame(recommendations).sort_values(by="Score", ascending=False)
        st.dataframe(rec_df, use_container_width=True)
        
        best_coin = rec_df.iloc[0]
        if best_coin['Score'] > 60:
            st.success(f"🎯 AI แนะนำ: **{best_coin['Symbol']}** มีคะแนนความน่าจะเป็นสูงสุดที่ {best_coin['Score']} แต้ม")

with col_right:
    st.subheader("🤖 AI Strategist")
    st.markdown(f"""
    <div style="background:#1e293b; padding:15px; border-radius:10px; border-left:5px solid #38bdf8;">
        <b>งบประมาณปัจจุบัน:</b> {current_total_bal:,.2f} ฿<br>
        <b>วิเคราะห์กลยุทธ์:</b> { "เน้นเหรียญผันผวนต่ำ" if current_total_bal < 5000 else "สามารถรับความเสี่ยงเหรียญเล็กได้" }
    </div>
    """, unsafe_allow_html=True)

st.divider()
st.info(f"Last AI Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
