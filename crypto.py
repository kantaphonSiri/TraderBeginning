import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
import numpy as np
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta, timezone

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันหลัก ---

def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sh = client.open("Blue-chip Bet")
        return sh.worksheet("trade_learning")
    except Exception as e:
        st.error(f"❌ เชื่อ m ต่อ Sheet ไม่ได้: {e}")
        return None

def get_now_thailand():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

@st.cache_data(ttl=600)
def get_live_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        return round(ticker.fast_info['last_price'], 2)
    except: return 35.0

def analyze_coin_ai(symbol, df_history):
    try:
        df = df_history.copy()
        if len(df) < 50: return None
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=25, random_state=42)
        model.fit(X.values, y.values)
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        score = 0
        if cur_p > float(last_row['EMA_20'].iloc[0]) > float(last_row['EMA_50'].iloc[0]): score += 50
        if 40 < float(last_row['RSI_14'].iloc[0]) < 65: score += 30
        pred_p = model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0]
        if pred_p > cur_p: score += 20
        
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": score}
    except: return None

# --- 3. UI & Control ---
sheet = init_gsheet()
live_rate = get_live_exchange_rate()
current_bal = 1000.0
df_perf = pd.DataFrame()
hunting_symbol = None
entry_price_thb = 0
current_qty = 0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            if not df_perf.empty:
                if 'Balance' in df_perf.columns:
                    val = df_perf.iloc[-1]['Balance']
                    if val != "": current_bal = float(val)
                h_rows = df_perf[df_perf['สถานะ'] == 'HUNTING']
                if not h_rows.empty:
                    hunting_symbol = h_rows.iloc[-1]['เหรียญ']
                    entry_price_thb = float(h_rows.iloc[-1]['ราคาซื้อ(฿)'])
                    current_qty = float(h_rows.iloc[-1]['จำนวน'])
    except: pass

# Sidebar
st.sidebar.title("🦔 Sniper Config")
init_money = st.sidebar.number_input("งบตั้งต้น (฿)", value=1000.0)
goal_money = st.sidebar.number_input("เป้าหมาย (฿)", value=10000.0)
bot_active = True # บังคับ ON เพื่อจำลองต่อเนื่อง

# --- 4. Prediction Logic (วิเคราะห์ระยะเวลาถึงเป้า) ---
st.title("🦔 Pepper Hunter")
days_elapsed = 1
win_rate_est = 0.60
avg_profit_per_trade = 0.08 # 8% per trade

if not df_perf.empty and len(df_perf) > 2:
    trades = df_perf[df_perf['สถานะ'] == 'SOLD']
    if len(trades) > 0:
        # คำนวณกำไรเฉลี่ยจริงจากประวัติ
        avg_profit_per_trade = trades['Balance'].pct_change().mean()
        first_date = pd.to_datetime(df_perf.iloc[0]['วันที่'], format="%d/%m/%Y %H:%M:%S")
        last_date = pd.to_datetime(df_perf.iloc[-1]['วันที่'], format="%d/%m/%Y %H:%M:%S")
        days_elapsed = (last_date - first_date).days if (last_date - first_date).days > 0 else 1

# คำนวณ Compound Interest เพื่อหาจำนวนวันที่ต้องใช้
# Goal = Current * (1 + avg_profit)^n
if avg_profit_per_trade > 0:
    trades_needed = np.log(goal_money / current_bal) / np.log(1 + avg_profit_per_trade)
    est_days = round(trades_needed * (days_elapsed / max(len(df_perf), 1)), 1)
else:
    est_days = "รอข้อมูลการเทรด..."

m1, m2, m3 = st.columns(3)
m1.metric("งบปัจจุบัน", f"{current_bal:,.2f} ฿")
m2.metric("เป้าหมาย", f"{goal_money:,.2f} ฿")
m3.metric("คาดการณ์ถึงเป้าใน", f"{est_days} วัน" if isinstance(est_days, float) else est_days)

st.divider()

# --- 5. Radar & Single Trade Logic ---
tickers = ["SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "DOT-USD", "XRP-USD", "ADA-USD", "BTC-USD", "ETH-USD", "BNB-USD"]
all_results = []

# ใช้ timeframe 1h เพื่อความเร็ว
for sym in tickers:
    df_h = yf.download(sym, period="7d", interval="1h", progress=False)
    res = analyze_coin_ai(sym, df_h)
    if res: all_results.append(res)

if sheet:
    now_str = get_now_thailand()
    
    # ถ้ามือว่าง -> เลือกเหรียญที่เทพที่สุดเพียงตัวเดียว
    if not hunting_symbol:
        best_pick = sorted([r for r in all_results if r['Score'] >= 85], key=lambda x: x['Score'], reverse=True)
        if best_pick:
            target = best_pick[0]
            buy_p = target['Price_USD'] * live_rate
            qty = current_bal / buy_p
            row = [now_str, target['Symbol'], "HUNTING", buy_p, 0, "0%", target['Score'], current_bal, qty, "Sniper Entry", "ON"]
            sheet.append_row(row)
            st.success(f"🎯 Sniper เข้าซื้อ: {target['Symbol']}")
            st.rerun()
    
    # ถ้าถืออยู่ -> เฝ้าจุดทำกำไร (Let Profit Run)
    else:
        current_data = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
        if current_data:
            sell_p = current_data['Price_USD'] * live_rate
            profit_pct = ((sell_p - entry_price_thb) / entry_price_thb) * 100
            new_bal = current_qty * sell_p
            
            # Logic การขายแบบ Sniper: เน้นกำไรคำใหญ่ (15%) หรือ Score ตกต่ำกว่า 45
            if current_data['Score'] < 45 or profit_pct > 15.0 or profit_pct < -5.0:
                row = [now_str, hunting_symbol, "SOLD", entry_price_thb, sell_p, f"{profit_pct:.2f}%", current_data['Score'], new_bal, 0, "Sniper Exit", "ON"]
                sheet.append_row(row)
                st.warning(f"💰 ปิดงาน {hunting_symbol} กำไร {profit_pct:.2f}%")
                st.rerun()

# กราฟ Performance
if not df_perf.empty:
    st.line_chart(df_perf['Balance'])

time.sleep(60)
st.rerun()

