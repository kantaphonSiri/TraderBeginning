import streamlit as st
import pandas as pd
import pandas_ta as ta
import gspread
import time
import ccxt
import requests
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & INITIALIZATION ---
st.set_page_config(page_title="Pepper Hunter AI", layout="wide")

# เปลี่ยนจาก binance เป็น kucoin (เสถียรกว่าบน Cloud Server และดึงข้อมูลสาธารณะได้เหมือนกัน)
exchange = ccxt.kucoin({
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
    except Exception as e:
        st.sidebar.error(f"❌ Sheet Connection Error: {e}")
        return None

@st.cache_data(ttl=1800)
def get_live_thb():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return float(res.json()['rates']['THB'])
    except:
        return 35.00
    return 35.00

# ฟังก์ชันเดิมไม่ต้องแก้ แต่ KuCoin ใช้ชื่อเหรียญแบบเดิมได้เลย (BTC/USDT)
def simulate_trade_potential(symbol, current_bal):
    try:
        # แปลงชื่อ Symbol ให้เข้ากับ Format ของ KuCoin (BTC-USD -> BTC/USDT)
        ccxt_symbol = symbol.replace("-USD", "/USDT")
        
        # ดึง OHLCV (KuCoin รองรับ fetch_ohlcv เหมือนกัน)
        ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        if df.empty: return None

        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_price = float(df['Close'].iloc[-1])
        last_rsi = float(df['RSI'].iloc[-1])
        last_ema = float(df['EMA_20'].iloc[-1])
        
        trend = "UP" if last_price > last_ema else "DOWN"
        score = 95 if (30 <= last_rsi <= 45 and trend == "UP") else (85 if last_rsi < 30 else 50)
        
        return {"Symbol": symbol, "Price": last_price, "Score": score, "Trend": trend}
    except Exception as e:
        # ถ้า KuCoin ตัวนี้ไม่มีเหรียญนี้ ให้ลองเปลี่ยน /USDT เป็น -USDT หรือชื่ออื่น
        st.sidebar.warning(f"Scan error {symbol}: {e}")
        return None

# --- 3. DATA PROCESSING (Fixed NameError) ---
# --- ประกาศค่าเริ่มต้นไว้ก่อนเลย เพื่อกัน NameError ---
current_bal = 1000.0 
bot_status = "OFF"
hunting_symbol = None
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

# ถ้าเชื่อมต่อ Sheet ได้ ค่อยไปดึงค่าจริงมาทับ
if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            df_all.columns = [c.strip() for c in df_all.columns]
            
            last_row = df_all.iloc[-1]
            # ใช้ .get เพื่อป้องกันกรณีไม่มี column นั้นๆ ใน sheet
            current_bal = float(last_row.get('Balance', 1000.0))
            bot_status = last_row.get('Bot_Status', 'OFF')
            
            if str(last_row.get('สถานะ')).upper() == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
    except Exception as e:
        st.sidebar.info(f"Sheet is empty or structure mismatch: {e}")

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")
st.write(f"💵 **Balance:** {current_bal:,.2f} ฿ | 🤖 **Status:** {bot_status}")

# รายชื่อเหรียญที่แนะนำ (ดึงผ่าน Binance ชัวร์กว่า Yahoo)
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "AVAX-USD", "RENDER-USD", "FET-USD", "SUI-USD", "LINK-USD"]

sim_df = pd.DataFrame()

with st.spinner('🤖 AI Brain is scanning market...'):
    results = []
    for t in tickers:
        # ตอนนี้ current_bal จะไม่มีวัน NameError แล้ว เพราะเราประกาศไว้ด้านบน
        res = simulate_trade_potential(t, current_bal)
        if res:
            results.append(res)
        time.sleep(0.1) # CCXT เร็วกว่า ไม่ต้องรอนาน
    
    if results:
        sim_df = pd.DataFrame(results).sort_values(by="Score", ascending=False)

if not sim_df.empty:
    st.subheader("🎯 Pepper Trading Signals")
    display_df = sim_df.copy()
    display_df['Price (฿)'] = display_df.apply(lambda x: f"{x['Price'] * live_rate:,.2f}", axis=1)
    st.dataframe(display_df[["Symbol", "Price (฿)", "Score", "Trend"]], use_container_width=True)

    if not hunting_symbol and bot_status == "ON":
        best = sim_df.iloc[0]
        if st.button(f"🚀 Confirm Trade: {best['Symbol']}"):
            price_thb = float(best['Price']) * live_rate
            new_data = [
                now_th.strftime("%d/%m/%Y %H:%M:%S"), 
                best['Symbol'], "HUNTING", price_thb, current_bal, 
                0, "0%", best['Score'], current_bal, 0, 
                "AI Scanner", "ON", "Neutral", "Binance Data"
            ]
            sheet.append_row(new_data)
            st.success(f"Started hunting {best['Symbol']}!")
            time.sleep(2)
            st.rerun()
    elif hunting_symbol:
        st.warning(f"⚠️ กำลังถือเหรียญ **{hunting_symbol}** อยู่")
else:
    st.error("❌ ไม่สามารถดึงข้อมูล AI ได้ในขณะนี้ (Check Sidebar for errors)")

st.divider()
st.caption(f"Last Prediction Sync: {now_th.strftime('%H:%M:%S')}")

# Auto Refresh 5 mins
time.sleep(300)
st.rerun()

