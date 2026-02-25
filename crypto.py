import streamlit as st
import pandas as pd
import pandas_ta as ta
import gspread
import time
import ccxt
import requests
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")
exchange = ccxt.kucoin({'enableRateLimit': True})

# เป้าหมายกำไร
TARGET_PROFIT = 10000.0
# ตั้งค่า Take Profit 3% และ Stop Loss 1.5% ต่อรอบเพื่อรักษาพอร์ต
TP_PCT = 3.0
SL_PCT = 1.5

# (ฟังก์ชัน init_gsheet และ get_live_thb ใช้ตัวเดิม)
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
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=10)
        return float(res.json()['rates']['THB']) if res.status_code == 200 else 35.0
    except: return 35.0

def simulate_trade_potential(symbol):
    try:
        ccxt_symbol = symbol.replace("-USD", "/USDT")
        ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        
        last_p = float(df['Close'].iloc[-1])
        last_rsi = float(df['RSI'].iloc[-1])
        last_ema = float(df['EMA_20'].iloc[-1])
        
        # AI Scoring: เน้นเข้าซื้อตอน RSI ต่ำและเริ่มกลับตัวเหนือ EMA
        trend = "UP" if last_p > last_ema else "DOWN"
        score = 95 if (last_rsi < 40 and trend == "UP") else (85 if last_rsi < 30 else 50)
        return {"Symbol": symbol, "Price": last_p, "Score": score, "Trend": trend}
    except: return None

# --- 2. EXECUTION LOGIC ---
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

st.title("🦔 Pepper Hunter")
progress = min(current_bal / TARGET_PROFIT, 1.0)
st.progress(progress, text=f"Progress to 10,000 ฿: {progress*100:.2f}%")

# --- 3. AUTO TRADE ACTION ---
if bot_status == "ON":
    if hunting_symbol:
        # CHECK TO SELL (ปิดงาน)
        res = simulate_trade_potential(hunting_symbol)
        if res:
            curr_p_thb = res['Price'] * live_rate
            pnl = ((curr_p_thb - entry_price_thb) / entry_price_thb) * 100
            
            if pnl >= TP_PCT or pnl <= -SL_PCT:
                new_bal = current_bal * (1 + (pnl/100))
                sheet.append_row([
                    now_th.strftime("%d/%m/%Y %H:%M:%S"), hunting_symbol, "CLOSED", 
                    entry_price_thb, current_bal, curr_p_thb, f"{pnl:.2f}%", 0, 
                    new_bal, 0, "AUTO EXIT", "ON", "Neutral", f"Exit at {pnl:.2f}%"
                ])
                st.success(f"💰 ปิดงาน {hunting_symbol}! PNL: {pnl:.2f}% | New Bal: {new_bal:.2f}")
                time.sleep(5)
                st.rerun()
    else:
        # CHECK TO BUY (เข้าซื้อ)
        tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD"]
        results = [simulate_trade_potential(t) for t in tickers]
        valid_res = [r for r in results if r and r['Score'] >= 90]
        
        if valid_res:
            best = sorted(valid_res, key=lambda x: x['Score'], reverse=True)[0]
            price_thb = best['Price'] * live_rate
            sheet.append_row([
                now_th.strftime("%d/%m/%Y %H:%M:%S"), best['Symbol'], "HUNTING", 
                price_thb, current_bal, 0, "0%", best['Score'], 
                current_bal, 0, "AUTO ENTRY", "ON", "Neutral", "AI Signal Detected"
            ])
            st.info(f"🚀 AI สั่งลุย! ซื้อ {best['Symbol']} ที่ราคา {price_thb:,.2f} ฿")
            time.sleep(5)
            st.rerun()

st.divider()
st.write(f"Last Scan: {now_th.strftime('%H:%M:%S')} | Bot is monitoring...")
time.sleep(60) # Scan ทุก 1 นาทีเพื่อความไว
st.rerun()
