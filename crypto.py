import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & UI ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

st.markdown("""
<style>
    .stApp { background: #0e1117; color: #e9eaeb; }
    .metric-card { background: #1c2128; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

# --- 2. PREDICTIVE LOGIC (AI Brain) ---
def simulate_trade_potential(symbol, current_bal):
    try:
        # ดึงข้อมูลย้อนหลัง 5 วัน (เพิ่ม Retry และลดความถี่การดึง)
        df = yf.download(symbol, period="5d", interval="15m", progress=False, timeout=10)
        
        if df is None or df.empty or len(df) < 20: 
            return None
        
        # จัดการเรื่อง Multi-index ของ yfinance เวอร์ชั่นใหม่
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Feature Engineering
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_rsi = float(df['RSI'].iloc[-1])
        last_price = float(df['Close'].iloc[-1])
        last_ema = float(df['EMA_20'].iloc[-1])
        
        trend = "UP" if last_price > last_ema else "DOWN"
        
        # ML Scoring Logic
        score = 0
        if 30 <= last_rsi <= 45 and trend == "UP": score = 95
        elif last_rsi < 30: score = 85
        elif trend == "UP": score = 60
        else: score = 20
        
        expected_profit = current_bal * 0.05
        prob_success = score / 100
        
        return {
            "Symbol": symbol,
            "Price": round(last_price, 4),
            "Score": score,
            "Trend": trend,
            "Exp_Value": round(expected_profit * prob_success, 2),
            "Action": "🔥 STRONG BUY" if score > 80 else "🔍 WATCH"
        }
    except Exception as e:
        # แสดง Error เล็กๆ ไว้ใน Log เผื่อ Debug
        print(f"Error fetching {symbol}: {e}")
        return None

# --- 3. CORE FUNCTIONS ---
def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

@st.cache_data(ttl=300)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        if not data.empty:
            return float(data['Close'].iloc[-1])
        return 35.50
    except: return 35.50

# --- 4. DATA PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
target_bal = 10000.0
current_bal = 1000.0
hunting_symbol = None
df_all = pd.DataFrame()

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            df_all.columns = df_all.columns.str.strip()
            last_row = df_all.iloc[-1]
            current_bal = float(last_row.get('Balance', 1000))
            if str(last_row.get('สถานะ')).upper() == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
    except: pass

# --- 5. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")

sim_df = pd.DataFrame()
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD"]

with st.spinner('AI Brain is simulating trades...'):
    sim_results = []
    # สร้าง Placeholder สำหรับแสดง Progress
    progress_bar = st.progress(0)
    for idx, t in enumerate(tickers):
        res = simulate_trade_potential(t, current_bal)
        if res:
            sim_results.append(res)
        progress_bar.progress((idx + 1) / len(tickers))
    
    if sim_results:
        sim_df = pd.DataFrame(sim_results).sort_values(by="Score", ascending=False)
    progress_bar.empty()

# แสดงผลลัพธ์
if not sim_df.empty:
    st.subheader("🎯 AI Trading Simulation Results")
    st.dataframe(sim_df, use_container_width=True)
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.write("### 📈 Roadmap to 10,000 ฿")
        # คำนวณจำนวนไม้ที่ต้องชนะ (Compound Interest)
        import math
        needed_multiplier = target_bal / current_bal
        if needed_multiplier > 1:
            trades_needed = math.log(needed_multiplier, 1.05) # คิดแบบทบต้นไม้ละ 5%
            st.info(f"ยอดปัจจุบัน: {current_bal:,.2f} ฿ | เป้าหมาย: {target_bal:,.2f} ฿\n\nต้องการชนะอีกประมาณ **{ceil(trades_needed) if 'ceil' in dir() else int(trades_needed)+1} ไม้** (ไม้ละ 5%)")
        else:
            st.success("คุณถึงเป้าหมาย 10,000 ฿ แล้ว!")

    with col2:
        if not hunting_symbol:
            best = sim_df.iloc[0]
            st.write(f"### 🚀 แผนแนะนำถัดไป: {best['Symbol']}")
            if st.button(f"ยืนยันเริ่มแผน: {best['Symbol']}"):
                thb_price = best['Price'] * live_rate
                sheet.append_row([
                    now_th.strftime("%d-%m-%Y %H:%M"), 
                    best['Symbol'], "HUNTING", thb_price, 
                    current_bal, 0, "0%", 0, current_bal
                ])
                st.success("บันทึกเรียบร้อย! กำลังรีโหลด...")
                time.sleep(1)
                st.rerun()
        else:
            st.warning(f"กำลังถือเหรียญ {hunting_symbol} อยู่... ระบบกำลังเฝ้าจุดปิดงาน")

else:
    st.warning("⚠️ ไม่สามารถดึงข้อมูล AI ได้ในขณะนี้ (Yahoo Finance อาจจำกัดการเข้าถึง) กรุณารอ 1-2 นาทีแล้วกด Refresh")
    if st.button("Retry Now"):
        st.rerun()

st.divider()
st.caption(f"Last Prediction Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
