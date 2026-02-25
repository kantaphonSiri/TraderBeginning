import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

# --- 2. PREDICTIVE LOGIC (จำลองความน่าจะเป็น) ---
def simulate_trade_potential(symbol, current_bal, target_bal):
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty: return None
        
        # สร้าง Features สำหรับ AI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_rsi = df['RSI'].iloc[-1]
        last_price = df['Close'].iloc[-1].item()
        trend = "UP" if last_price > df['EMA_20'].iloc[-1] else "DOWN"
        
        # จำลอง Score (Prediction Model เบื้องต้น)
        score = 0
        if 30 <= last_rsi <= 45 and trend == "UP": score = 95 # จุดกลับตัวที่แข็งแกร่ง
        elif last_rsi < 30: score = 85 # จุดขายมากเกินไป
        elif trend == "UP": score = 60 # ตามเทรนด์
        
        # คำนวณความคุ้มค่า (Risk/Reward Simulation)
        expected_profit = current_bal * 0.05 # เป้า 5%
        prob_success = score / 100
        expected_value = expected_profit * prob_success
        
        return {
            "Symbol": symbol,
            "Price": round(last_price, 4),
            "Score": score,
            "Trend": trend,
            "Exp_Value": round(expected_value, 2),
            "Action": "🔥 HIGH PROB" if score > 80 else "🔍 SCANNING"
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
    data = yf.download("THB=X", period="1d", interval="1m", progress=False)
    return float(data['Close'].iloc[-1].item()) if not data.empty else 35.50

# --- 4. PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
target_bal = 10000.0
current_bal = 1000.0
hunting_symbol = None

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_all = pd.DataFrame(recs)
        df_all.columns = df_all.columns.str.strip()
        last_row = df_all.iloc[-1]
        current_bal = float(last_row.get('Balance', 1000))
        if last_row.get('สถานะ') == 'HUNTING':
            hunting_symbol = last_row.get('เหรียญ')
            entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))

# --- 5. DASHBOARD ---
st.title("🦔 Pepper Hunter")

# AI Prediction Section
st.subheader("🎯 AI Trading Simulation (Prediction)")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "AVAX-USD", "LINK-USD", "AR-USD", "DOT-USD"]
sim_results = []
for t in tickers:
    res = simulate_trade_potential(t, current_bal, target_bal)
    if res: sim_results.append(res)

if sim_results:
    sim_df = pd.DataFrame(sim_results).sort_values(by="Score", ascending=False)
    
    # แสดงตารางวิเคราะห์
    cols = st.columns(len(sim_results[:4]))
    for i, row in enumerate(sim_results[:4]):
        with cols[i]:
            st.metric(row['Symbol'], f"{row['Score']}% Prob", delta=row['Trend'])
            st.caption(f"คาดการณ์กำไร: {row['Exp_Value']} ฿")

    st.dataframe(sim_df, use_container_width=True)

# ส่วนการคำนวณเป้าหมาย
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.write("### 📈 Roadmap to 10,000 ฿")
    trades_needed = (target_bal / current_bal) / 0.05 # สมมติกำไรไม้ละ 5%
    st.info(f"หากทำกำไรเฉลี่ยไม้ละ 5% คุณต้องชนะอีกประมาณ **{int(trades_needed)} ไม้** เพื่อถึงเป้าหมาย")

with col2:
    if not hunting_symbol:
        best = sim_df.iloc[0]
        st.write(f"### 🚀 แนะนำแผนการเทรดถัดไป")
        if st.button(f"ยืนยันเริ่มแผนล่า: {best['Symbol']}"):
            thb_price = best['Price'] * live_rate
            sheet.append_row([now_th.strftime("%d-%m-%Y %H:%M"), best['Symbol'], "HUNTING", thb_price, current_bal, 0, "0%", 0, current_bal])
            st.rerun()

st.divider()
st.caption(f"Last Prediction Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
