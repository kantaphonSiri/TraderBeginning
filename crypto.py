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
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty: return None
        
        # Feature Engineering
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_rsi = df['RSI'].iloc[-1]
        last_price = df['Close'].iloc[-1].item()
        trend = "UP" if last_price > df['EMA_20'].iloc[-1] else "DOWN"
        
        # Machine Learning Scoring Logic
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
    except: return None

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
        return float(data['Close'].iloc[-1].item()) if not data.empty else 35.50
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
            if last_row.get('สถานะ') == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
    except: pass

# --- 5. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")

# ส่วนที่แก้ NameError: ประกาศ sim_df เป็นค่าว่างไว้ก่อนเสมอ
sim_df = pd.DataFrame()

st.subheader("🎯 Trading Simulation")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "AVAX-USD", "LINK-USD", "AR-USD", "DOT-USD"]

with st.spinner('Pepper is simulating trades...'):
    sim_results = []
    for t in tickers:
        res = simulate_trade_potential(t, current_bal)
        if res: sim_results.append(res)
    
    if sim_results:
        sim_df = pd.DataFrame(sim_results).sort_values(by="Score", ascending=False)

# แสดงตารางวิเคราะห์
if not sim_df.empty:
    st.dataframe(sim_df, use_container_width=True)
    
    # Roadmap to Target
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.write("### 📈 Roadmap to 10,000 ฿")
        trades_needed = (target_bal / current_bal) / 0.05
        st.info(f"ยอดปัจจุบัน: {current_bal:,.2f} ฿ | เป้าหมาย: {target_bal:,.2f} ฿\n\nต้องการชนะอีกประมาณ **{int(trades_needed)} ไม้** (ไม้ละ 5%)")

    with col2:
        if not hunting_symbol:
            best = sim_df.iloc[0] # ตอนนี้ปลอดภัยแล้วเพราะเช็ค empty ด้านบน
            st.write(f"### 🚀 แผนแนะนำถัดไป: {best['Symbol']}")
            if st.button(f"ยืนยันเริ่มแผน: {best['Symbol']}"):
                thb_price = best['Price'] * live_rate
                sheet.append_row([
                    now_th.strftime("%d-%m-%Y %H:%M"), 
                    best['Symbol'], "HUNTING", thb_price, 
                    current_bal, 0, "0%", 0, current_bal
                ])
                st.success("บันทึกลง Google Sheets สำเร็จ!")
                st.rerun()
        else:
            st.warning(f"กำลังถือเหรียญ {hunting_symbol} อยู่... กรุณารอระบบ Auto-Exit ปิดงานก่อนเริ่มแผนใหม่")

else:
    st.error("ไม่สามารถดึงข้อมูล AI ได้ในขณะนี้ กรุณาลองใหม่")

st.divider()
st.caption(f"Last Prediction Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
