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
# เปลี่ยนเป็น KuCoin เพื่อเลี่ยงปัญหา Error 451 จากสถานที่ไม่ได้รับอนุญาต
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
        
        # กลยุทธ์ AI: เน้นจุดกลับตัว (RSI ต่ำ + ยืนเหนือ EMA)
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
                entry_price_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
    except: pass

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")

# ส่วนแสดง Progress Bar
col_bal, col_target = st.columns(2)
with col_bal:
    st.metric("Current Balance", f"{current_bal:,.2f} ฿", f"{(current_bal-1000):,.2f} ฿")
with col_target:
    st.metric("Target Goal", f"{TARGET_BAL:,.2f} ฿", f"Remaining: {TARGET_BAL-current_bal:,.2f} ฿")

progress = min(current_bal / TARGET_BAL, 1.0)
st.progress(progress, text=f"Progress to 10k: {progress*100:.2f}%")

st.divider()

# --- 5. AI INSIGHTS (TOP 6 CANDIDATES) ---
st.subheader("🎯 AI Top Picks & Real-time Analysis")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "SUI-USD", "LINK-USD"]

with st.spinner('🤖 AI Brain is scanning market candidates...'):
    all_analysis = []
    for t in tickers:
        res = analyze_market(t)
        if res: all_analysis.append(res)
    
    if all_analysis:
        df_signals = pd.DataFrame(all_analysis).sort_values(by="Score", ascending=False)
        top_6 = df_signals.head(6).copy()
        
        # คำนวณจำนวนเหรียญที่จะซื้อตามทุนที่มี (All-in strategy สำหรับพอร์ตเล็ก)
        top_6['Est. Qty'] = top_6.apply(lambda x: current_bal / (x['Price'] * live_rate), axis=1)
        top_6['Price (฿)'] = top_6['Price'] * live_rate
        
        # แสดงตาราง Insight
        st.table(top_6[["Symbol", "Score", "Trend", "RSI", "Price (฿)", "Est. Qty"]].style.format({
            "Price (฿)": "{:,.2f}",
            "Est. Qty": "{:,.4f}",
            "RSI": "{:.2f}"
        }))

        best_move = top_6.iloc[0]
        if not hunting_symbol:
            st.info(f"🔮 **AI Next Move:** เตรียมเข้าซื้อ **{best_move['Symbol']}** จำนวน **{best_move['Est. Qty']:.4f}** หากเงื่อนไขครบ (Score >= 90)")

st.divider()

# --- 6. AUTO-TRADING LOGIC ---
if bot_status == "ON":
    if hunting_symbol:
        # ระบบตรวจสอบการ "ขาย" (Exit Strategy)
        res = analyze_market(hunting_symbol)
        if res:
            curr_p_thb = res['Price'] * live_rate
            pnl = ((curr_p_thb - entry_price_thb) / entry_price_thb) * 100
            
            # เงื่อนไข Take Profit 3% หรือ Stop Loss 1.5%
            if pnl >= 3.0 or pnl <= -1.5:
                new_bal = current_bal * (1 + (pnl/100))
                sheet.append_row([
                    now_th.strftime("%d/%m/%Y %H:%M:%S"), hunting_symbol, "SETTLED", 
                    entry_price_thb, current_bal, curr_p_thb, f"{pnl:.2f}%", 0, 
                    new_bal, 0, "AUTO EXIT", "ON", "Neutral", f"Exit at {pnl:.2f}%"
                ])
                st.balloons()
                st.success(f"💰 ปิดงาน {hunting_symbol}! กำไร/ขาดทุน: {pnl:.2f}% | ยอดใหม่: {new_bal:,.2f} ฿")
                time.sleep(5)
                st.rerun()
    else:
        # ระบบตรวจสอบการ "ซื้อ" (Entry Strategy)
        best = df_signals.iloc[0]
        if best['Score'] >= 90:
            p_thb = best['Price'] * live_rate
            qty = current_bal / p_thb
            sheet.append_row([
                now_th.strftime("%d/%m/%Y %H:%M:%S"), best['Symbol'], "HUNTING", 
                p_thb, current_bal, 0, "0%", best['Score'], 
                current_bal, qty, "AUTO ENTRY", "ON", "Neutral", f"RSI: {best['RSI']:.2f}"
            ])
            st.warning(f"🚀 AI ตัดสินใจซื้อ {best['Symbol']} จำนวน {qty:.4f} หน่วย")
            time.sleep(5)
            st.rerun()

# --- 7. FOOTER ---
st.write(f"🕒 Last Update: {now_th.strftime('%H:%M:%S')} | Bot Status: {bot_status}")
time.sleep(60)
st.rerun()
