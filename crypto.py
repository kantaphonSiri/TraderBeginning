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

# --- 2. CORE FUNCTIONS ---
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
            val = data['Close'].iloc[-1]
            return float(val.iloc[0] if hasattr(val, 'iloc') else val)
        return 35.50
    except: return 35.50

def simulate_trade_potential(symbol, current_bal):
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_price = float(df['Close'].iloc[-1])
        last_rsi = float(df['RSI'].iloc[-1])
        last_ema = float(df['EMA_20'].iloc[-1])
        
        trend = "UP" if last_price > last_ema else "DOWN"
        score = 0
        if 30 <= last_rsi <= 45 and trend == "UP": score = 95
        elif last_rsi < 30: score = 85
        elif trend == "UP": score = 60
        else: score = 20
        
        return {"Symbol": symbol, "Price": last_price, "Score": score, "Trend": trend}
    except: return None

# --- 3. DATA PROCESSING (Match Your Columns) ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

# ตัวแปรเริ่มต้น
current_bal = 1000.0
bot_status = "OFF"
hunting_symbol = None

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            # ล้างชื่อคอลัมน์ให้สะอาด (ไม่มีช่องว่างแปลกปลอม)
            df_all.columns = [c.strip() for c in df_all.columns]
            
            last_row = df_all.iloc[-1]
            current_bal = float(last_row.get('Balance', 1000))
            bot_status = last_row.get('Bot_Status', 'OFF')
            
            # เช็คสถานะการล่า
            if str(last_row.get('สถานะ')).upper() == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
    except Exception as e:
        st.error(f"Sheet Read Error: {e}")

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")
st.write(f"**Bot Status:** {bot_status} | **Current Balance:** {current_bal:,.2f} ฿")

sim_df = pd.DataFrame()
# คัดเลือกตามกลุ่ม: Blue Chip, AI Agent, DePIN และ RWA
tickers = [
    "BTC-USD", "ETH-USD", "SOL-USD",    # เสาหลัก
    "RENDER-USD", "FET-USD", "NEAR-USD", # AI & Infrastructure (ดึงได้ปกติ)
    "AVAX-USD", "LINK-USD", "DOT-USD",   # Layer 1 & Oracle
    "ADA-USD", "MATIC-USD", "STX-USD"    # ตัวเสริมที่มีสภาพคล่องสูง
]

with st.spinner('AI Brain is scanning 2026 Gems...'):
    results = []
    for t in tickers:
        res = simulate_trade_potential(t, current_bal)
        if res:
            results.append(res)
        # เพิ่ม sleep 1 วินาที ระหว่างเหรียญ เพื่อหลบการตรวจจับของ Yahoo
        time.sleep(1) 
    
    if results:
        sim_df = pd.DataFrame(results).sort_values(by="Score", ascending=False)

if not sim_df.empty:
    st.subheader("🎯 AI Prediction")
    display_df = sim_df.copy()
    display_df['Price (฿)'] = display_df.apply(lambda x: f"{x['Price'] * live_rate:,.2f}", axis=1)
    st.dataframe(display_df[["Symbol", "Price (฿)", "Score", "Trend"]], use_container_width=True)

    if not hunting_symbol and bot_status == "ON":
        best = sim_df.iloc[0]
        if st.button(f"🚀 เริ่มเทรด {best['Symbol']}"):
            price_thb = float(best['Price']) * live_rate
            # บันทึกตามลำดับ Column ใน Sheet ของคุณเป๊ะๆ
            # วันที่, เหรียญ, สถานะ, ราคาซื้อ(฿), เงินลงทุน(฿), ราคาขาย(฿), กำไร%, Score, Balance, จำนวน, Headline, Bot_Status, News_Sentiment, News_Headline
            new_data = [
                now_th.strftime("%d/%m/%Y %H:%M:%S"), # วันที่
                best['Symbol'],                        # เหรียญ
                "HUNTING",                             # สถานะ
                price_thb,                             # ราคาซื้อ(฿)
                current_bal,                           # เงินลงทุน(฿)
                0,                                     # ราคาขาย(฿)
                "0%",                                  # กำไร%
                best['Score'],                         # Score
                current_bal,                           # Balance
                0,                                     # จำนวน
                "AI Entry",                            # Headline
                "ON",                                  # Bot_Status
                "Neutral",                             # News_Sentiment
                "Bot Start Trading"                    # News_Headline
            ]
            sheet.append_row(new_data)
            st.rerun()
else:
    st.warning("ดึงราคาจาก Yahoo ไม่สำเร็จ (Rate Limit) กรุณารอสักครู่แล้วลองใหม่")

st.divider()
time.sleep(300)
st.rerun()


