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

# เชื่อมต่อ Binance (Public API - ไม่ต้องใช้ Key สำหรับดึงราคา)
exchange = ccxt.binance({'enableRateLimit': True})

# --- 2. CORE FUNCTIONS ---
def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except Exception as e:
        st.error(f"❌ เชื่อมต่อ Google Sheets ไม่สำเร็จ: {e}")
        return None

@st.cache_data(ttl=1800)
def get_live_thb():
    """ดึงค่าเงินบาทผ่าน API เพื่อเลี่ยงปัญหา Yahoo Rate Limit"""
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return float(res.json()['rates']['THB'])
    except:
        return 35.00  # ค่าเริ่มต้นกรณี API ล่ม
    return 35.00

def simulate_trade_potential(symbol, current_bal):
    try:
        ccxt_symbol = symbol.replace("-USD", "/USDT")
        # เพิ่ม timeout เพื่อไม่ให้แอปรอนานเกินไปถ้า network มีปัญหา
        ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe='15m', limit=100)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        if df.empty: 
            return None

        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_price = float(df['Close'].iloc[-1])
        last_rsi = float(df['RSI'].iloc[-1])
        last_ema = float(df['EMA_20'].iloc[-1])
        
        trend = "UP" if last_price > last_ema else "DOWN"
        score = 95 if (30 <= last_rsi <= 45 and trend == "UP") else (85 if last_rsi < 30 else 50)
        
        return {"Symbol": symbol, "Price": last_price, "Score": score, "Trend": trend}
    except Exception as e:
        # พิมพ์ Error ออกมาทางหน้าจอตอนสแกน เพื่อให้เรารู้ว่าพังเพราะอะไร
        st.sidebar.error(f"⚠️ {symbol}: {str(e)}") 
        return None

# --- ส่วนการสแกนที่ทนทานขึ้น ---
with st.spinner('🤖 AI Brain is scanning...'):
    results = []
    # ลองทดสอบด้วยเหรียญหลักแค่ 3 ตัวก่อนเพื่อดูว่า API ทำงานไหม
    test_tickers = ["BTC-USD", "ETH-USD", "SOL-USD"] 
    
    for t in test_tickers:
        res = simulate_trade_potential(t, current_bal)
        if res:
            results.append(res)
        time.sleep(0.5) # เว้นจังหวะนิดนึง

# --- 3. DATA PROCESSING ---
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
            df_all.columns = [c.strip() for c in df_all.columns]
            
            last_row = df_all.iloc[-1]
            current_bal = float(last_row.get('Balance', 1000))
            bot_status = last_row.get('Bot_Status', 'OFF')
            
            if str(last_row.get('สถานะ')).upper() == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
    except Exception as e:
        st.warning(f"ยังไม่มีข้อมูลใน Sheet หรืออ่านค่าไม่ได้: {e}")

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter AI (2026 Edition)")
st.write(f"💵 **Balance:** {current_bal:,.2f} ฿ | 🤖 **Status:** {bot_status} | 🌏 **USD/THB:** {live_rate:.2f}")

# รายชื่อเหรียญที่แนะนำในปี 2026 (ดึงผ่าน Binance ได้ชัวร์)
tickers = [
    "BTC-USD", "ETH-USD", "SOL-USD", 
    "NEAR-USD", "AVAX-USD", "RENDER-USD", 
    "FET-USD", "TAO-USD", "SUI-USD", 
    "AR-USD", "LINK-USD", "DOT-USD"
]

sim_df = pd.DataFrame()

with st.spinner('🤖 AI Brain is scanning market via Binance...'):
    results = []
    for t in tickers:
        res = simulate_trade_potential(t, current_bal)
        if res:
            results.append(res)
    
    if results:
        sim_df = pd.DataFrame(results).sort_values(by="Score", ascending=False)

if not sim_df.empty:
    st.subheader("🎯 AI Trading Signals")
    display_df = sim_df.copy()
    display_df['Price (฿)'] = display_df.apply(lambda x: f"{x['Price'] * live_rate:,.2f}", axis=1)
    
    # แสดงตารางวิเคราะห์
    st.dataframe(display_df[["Symbol", "Price (฿)", "Score", "Trend"]], use_container_width=True)

    # เงื่อนไขการเข้าเทรด
    if not hunting_symbol and bot_status == "ON":
        best = sim_df.iloc[0]
        st.info(f"🚀 แนะนำให้เข้าซื้อ: **{best['Symbol']}** เนื่องจากมี Score สูงสุดที่ {best['Score']}")
        if st.button(f"Confirm Trade: {best['Symbol']}"):
            price_thb = float(best['Price']) * live_rate
            
            # เรียงข้อมูลตาม Column ใน Google Sheets ของคุณเป๊ะๆ
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
                "AI Scanner Entry",                    # Headline
                "ON",                                  # Bot_Status
                "Neutral",                             # News_Sentiment
                "Real-time Signal from CCXT"           # News_Headline
            ]
            sheet.append_row(new_data)
            st.success(f"บันทึกแผนการเข้าซื้อ {best['Symbol']} เรียบร้อย!")
            time.sleep(2)
            st.rerun()
    elif hunting_symbol:
        st.warning(f"⚠️ กำลังล่าเหรียญ **{hunting_symbol}** อยู่... กรุณารอจนกว่าจะปิดงานใน Google Sheets")
else:
    st.error("❌ ไม่สามารถดึงข้อมูล AI ได้ในขณะนี้ กรุณารีเฟรชหน้าจอ")

st.divider()
st.caption(f"Last Prediction Sync: {now_th.strftime('%H:%M:%S')} | Data Provider: Binance via CCXT")

# Auto Refresh ทุก 5 นาที
time.sleep(300)
st.rerun()

