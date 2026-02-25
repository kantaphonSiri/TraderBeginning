import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import ccxt # <--- เพิ่มการ Import CCXT
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

# เชื่อมต่อ Binance ผ่าน CCXT (Public Mode ไม่ต้องใช้ Key)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

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
    # ส่วนนี้ยังคงใช้ yfinance ได้เพราะคู่เงิน THB=X ไม่ค่อยติด Rate Limit เหมือนคริปโต
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        if not data.empty:
            val = data['Close'].iloc[-1]
            return float(val.iloc[0] if hasattr(val, 'iloc') else val)
        return 35.50
    except: return 35.50

def simulate_trade_potential(symbol, current_bal):
    try:
        # แปลงชื่อ Symbol ให้เข้ากับ Format ของ Binance (เช่น BTC-USD -> BTC/USDT)
        ccxt_symbol = symbol.replace("-USD", "/USDT")
        
        # ดึงข้อมูลแท่งเทียน (OHLCV) 15 นาที จำนวน 100 แท่ง
        ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        if df.empty: return None

        # คำนวณ RSI และ EMA ด้วย pandas_ta
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
    except Exception as e:
        # st.error(f"Error fetching {symbol}: {e}") # เปิดไว้ดูตอน Debug ได้
        return None

# --- 3. DATA PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

current_bal = 1000.0
bot_status = "OFF"
hunting_symbol = None

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            df_all.columns = [c.strip() for c in df_all.columns]
            last_row = df_all.iloc[-1]
            current_bal = float(last_row.get('Balance', 1000))
            bot_status = last_row.get('Bot_Status', 'OFF')
            if str(last_row.get('สถานะ')).upper() == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
    except Exception as e:
        st.error(f"Sheet Read Error: {e}")

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")
st.write(f"**Bot Status:** {bot_status} | **Current Balance:** {current_bal:,.2f} ฿")

sim_df = pd.DataFrame()

# รายชื่อเหรียญ (ใช้ Format เดิม แต่ระบบจะแปลงเป็น /USDT ให้เอง)
tickers = [
    "BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", 
    "AVAX-USD", "RENDER-USD", "FET-USD", "TAO-USD", 
    "SUI-USD", "AR-USD", "POL-USD", "LINK-USD"
]

with st.spinner('AI Brain is scanning 2026 Gems via Binance...'):
    results = []
    for t in tickers:
        res = simulate_trade_potential(t, current_bal)
        if res:
            results.append(res)
    
    if results:
        sim_df = pd.DataFrame(results).sort_values(by="Score", ascending=False)

if not sim_df.empty:
    st.subheader("🎯 Pepper Prediction (Real-time)")
    display_df = sim_df.copy()
    display_df['Price (฿)'] = display_df.apply(lambda x: f"{x['Price'] * live_rate:,.2f}", axis=1)
    st.dataframe(display_df[["Symbol", "Price (฿)", "Score", "Trend"]], use_container_width=True)

    if not hunting_symbol and bot_status == "ON":
        best = sim_df.iloc[0]
        if st.button(f"🚀 เริ่มเทรด {best['Symbol']}"):
            price_thb = float(best['Price']) * live_rate
            new_data = [
                now_th.strftime("%d/%m/%Y %H:%M:%S"),
                best['Symbol'],
                "HUNTING",
                price_thb,
                current_bal,
                0,
                "0%",
                best['Score'],
                current_bal,
                0,
                "AI Entry (CCXT)",
                "ON",
                "Neutral",
                "Binance Real-time Data"
            ]
            sheet.append_row(new_data)
            st.success(f"Started hunting {best['Symbol']}!")
            time.sleep(1)
            st.rerun()
else:
    st.warning("⚠️ ไม่สามารถดึงข้อมูลจาก Exchange ได้ในขณะนี้")

st.divider()
st.caption(f"Last Sync: {now_th.strftime('%H:%M:%S')} (Next sync in 5 mins)")
time.sleep(300)
st.rerun()
