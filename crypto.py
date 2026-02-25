import streamlit as st
import pandas as pd
import pandas_ta as ta
import gspread
import time
import ccxt
import requests
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & GOALS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")
TARGET_BAL = 10000.0
exchange = ccxt.kucoin({'enableRateLimit': True})

# --- 2. CORE FUNCTIONS ---
def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

@st.cache_data(ttl=1800)
def get_live_thb():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        return float(res.json()['rates']['THB']) if res.status_code == 200 else 35.0
    except: return 35.0

def analyze_market(symbol):
    try:
        ccxt_symbol = symbol.replace("-USD", "/USDT")
        ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_p = float(df['Close'].iloc[-1])
        last_rsi = float(df['RSI'].iloc[-1])
        last_ema = float(df['EMA_20'].iloc[-1])
        
        # กลยุทธ์: ซื้อเมื่อ RSI ต่ำ (Oversold) และเริ่มกลับตัว (Above EMA)
        trend = "UP" if last_p > last_ema else "DOWN"
        score = 0
        if last_rsi < 35 and trend == "UP": score = 95
        elif last_rsi < 30: score = 90
        elif trend == "UP": score = 60
        else: score = 20
        
        return {"Symbol": symbol, "Price": last_p, "Score": score, "Trend": trend, "RSI": last_rsi}
    except: return None

# --- 3. DATA PROCESSING ---
current_bal = 1000.0
bot_status = "OFF"
hunting_symbol = None
entry_price_thb = 0

sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_all = pd.DataFrame(recs)
        df_all.columns = [c.strip() for c in df_all.columns]
        last_row = df_all.iloc[-1]
        current_bal = float(last_row.get('Balance', 1000))
        bot_status = last_row.get('Bot_Status', 'OFF')
        if str(last_row.get('สถานะ')).upper() == 'HUNTING':
            hunting_symbol = last_row.get('เหรียญ')
            entry_price_thb = float(last_row.get('ราคาซื้อ(฿)', 0))

# --- 4. UI & AUTO-PILOT ---
st.title("🦔 Pepper Hunter")
progress = min(current_bal / TARGET_BAL, 1.0)
st.progress(progress, text=f"Progress: {current_bal:,.2f} / {TARGET_BAL:,.2f} ฿")

if bot_status == "ON":
    if hunting_symbol:
        # ระบบเรียนรู้การ "ขาย": ตั้ง TP 3% SL 1.5%
        res = analyze_market(hunting_symbol)
        if res:
            curr_p_thb = res['Price'] * live_rate
            pnl = ((curr_p_thb - entry_price_thb) / entry_price_thb) * 100
            
            if pnl >= 3.0 or pnl <= -1.5:
                new_bal = current_bal * (1 + (pnl/100))
                # วันที่,เหรียญ,สถานะ,ราคาซื้อ,เงินลงทุน,ราคาขาย,กำไร%,Score,Balance,จำนวน,Headline,Bot_Status,News_Sentiment,News_Headline
                sheet.append_row([
                    now_th.strftime("%d/%m/%Y %H:%M:%S"), hunting_symbol, "SETTLED", 
                    entry_price_thb, current_bal, curr_p_thb, f"{pnl:.2f}%", 0, 
                    new_bal, 0, "AUTO EXIT", "ON", "Neutral", f"Profit Taken at {pnl:.2f}%"
                ])
                st.success(f"✅ ปิดงาน {hunting_symbol} กำไร {pnl:.2f}%")
                time.sleep(5)
                st.rerun()
    else:
        # ระบบเรียนรู้การ "ซื้อ": สแกนหาเหรียญ Score สูง
        tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "SUI-USD"]
        results = []
        for t in tickers:
            analysis = analyze_market(t)
            if analysis: results.append(analysis)
            time.sleep(0.2)
        
        if results:
            df_signals = pd.DataFrame(results).sort_values(by="Score", ascending=False)
            best = df_signals.iloc[0]
            
            if best['Score'] >= 90:
                p_thb = best['Price'] * live_rate
                sheet.append_row([
                    now_th.strftime("%d/%m/%Y %H:%M:%S"), best['Symbol'], "HUNTING", 
                    p_thb, current_bal, 0, "0%", best['Score'], 
                    current_bal, 0, "AUTO ENTRY", "ON", "Neutral", f"RSI: {best['RSI']:.2f}"
                ])
                st.info(f"🚀 เริ่มล่า {best['Symbol']} ที่ราคา {p_thb:,.2f} ฿")
                time.sleep(5)
                st.rerun()

st.divider()
st.write(f"ระบบกำลังเฝ้าตลาด... (Last Sync: {now_th.strftime('%H:%M:%S')})")
time.sleep(60)
st.rerun()
