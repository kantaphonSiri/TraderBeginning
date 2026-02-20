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

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันระบบหลังบ้าน ---

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
        st.error(f"❌ Google Sheet Connection Error: {e}")
        return None

def get_now_thailand():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

@st.cache_data(ttl=600)
def get_live_exchange_rate():
    # สุ่มหน่วงเวลาเล็กน้อยเพื่อเลียนแบบมนุษย์
    time.sleep(random.uniform(0.5, 1.2))
    try:
        ticker = yf.Ticker("THB=X")
        return round(ticker.fast_info['last_price'], 2)
    except: return 35.5

def analyze_coin_ai(symbol, df_history):
    try:
        df = df_history.copy()
        if len(df) < 50: return None
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        # Machine Learning (Predict Next Price)
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42)
        model.fit(X.values, y.values)
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        score = 0
        
        # Scoring Logic
        if cur_p > float(last_row['EMA_20'].iloc[0]) > float(last_row['EMA_50'].iloc[0]): score += 50
        if 40 < float(last_row['RSI_14'].iloc[0]) < 65: score += 30
        pred_p = model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0]
        if pred_p > cur_p: score += 20
        
        return {
            "Symbol": symbol, 
            "Price_USD": cur_p, 
            "Score": score,
            "Last_Update": datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        }
    except: return None

# --- 3. ดึงข้อมูลจาก Google Sheet ---
sheet = init_gsheet()
live_rate = get_live_exchange_rate()
current_bal = 1000.0  # ทุนเริ่มต้น
hunting_symbol = None
entry_price_thb = 0
current_qty = 0
df_perf = pd.DataFrame()

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            if not df_perf.empty:
                last_row_data = df_perf.iloc[-1]
                if 'Balance' in df_perf.columns and last_row_data['Balance'] != "":
                    current_bal = float(last_row_data['Balance'])
                
                h_rows = df_perf[df_perf['สถานะ'] == 'HUNTING']
                if not h_rows.empty:
                    hunting_symbol = h_rows.iloc[-1]['เหรียญ']
                    entry_price_thb = float(h_rows.iloc[-1]['ราคาซื้อ(฿)'])
                    current_qty = float(h_rows.iloc[-1]['จำนวน'])
    except Exception as e:
        st.warning(f"⚠️ การอ่าน Sheet ขัดข้อง: {e}")

# --- 4. Dashboard UI ---
st.title("🦔 Pepper Hunter")
st.subheader(f"เป้าหมาย: 10,000 ฿ | ปัจจุบัน: {current_bal:,.2f} ฿")

# ส่วนแสดงผลสถานะการถือครอง
if hunting_symbol:
    st.warning(f"🎯 กำลังถือ: {hunting_symbol} | ทุน: {entry_price_thb:,.2f} ฿")
else:
    st.info("🔎 สถานะ: กำลังสแกนหาจุดซื้อที่ดีที่สุด (Score >= 80)")

# --- 5. ระบบ Radar (โชว์ตารางแบบ Real-time) ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "AVAX-USD", "LINK-USD", "DOT-USD"]
all_results = []

st.divider()
st.subheader("📊 AI Sniper Radar")

# สร้างพื้นที่จองไว้สำหรับตารางและสถานะ
table_area = st.empty()
status_area = st.empty()
progress_bar = st.progress(0)

for i, sym in enumerate(tickers):
    # ระบบ Anti-Bot: สุ่มเวลาหน่วงเลียนแบบคน
    jitter = random.uniform(1.5, 4.0)
    status_area.write(f"🔍 มนุษย์จำลองกำลังตรวจสอบ {sym}... (รอ {jitter:.1f} วินาที)")
    time.sleep(jitter)
    
    df_h = yf.download(sym, period="7d", interval="1h", progress=False)
    if not df_h.empty:
        res = analyze_coin_ai(sym, df_h)
        if res:
            all_results.append(res)
            # อัปเดตตารางทันทีที่วิเคราะห์เสร็จทีละตัว
            current_df = pd.DataFrame(all_results).sort_values(by='Score', ascending=False)
            table_area.dataframe(current_df, use_container_width=True)
            
    progress_bar.progress((i + 1) / len(tickers))

status_area.empty() # ล้างข้อความสถานะเมื่อเสร็จ

# --- 6. Logic การซื้อ-ขาย (เชื่อมต่อ Google Sheet) ---
if all_results:
    now_str = get_now_thailand()
    
    # --- [BUY LOGIC] ---
    if not hunting_symbol:
        best_pick = all_results[0] if all_results[0]['Score'] >= 80 else None
        if best_pick:
            buy_p_thb = best_pick['Price_USD'] * live_rate
            qty = current_bal / buy_p_thb
            row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], current_bal, qty, "AI Sniper Buy", "ON"]
            if sheet:
                sheet.append_row(row)
                st.success(f"🎯 บันทึกการซื้อ: {best_pick['Symbol']}")
                time.sleep(2)
                st.rerun()
    
    # --- [SELL LOGIC] ---
    else:
        current_coin = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
        if current_coin:
            cur_p_thb = current_coin['Price_USD'] * live_rate
            profit = ((cur_p_thb - entry_price_thb) / entry_price_thb) * 100
            
            st.metric("กำไรปัจจุบัน", f"{profit:.2f}%", delta=f"{profit:.2f}%")

            sell_trigger = False
            headline = ""
            if profit >= 8.0:
                sell_trigger, headline = True, "Take Profit (Success)"
            elif 0.2 < profit < 1.0 and current_coin['Score'] < 50:
                sell_trigger, headline = True, "No-Loss Exit (Protect Capital)"
            elif profit <= -4.0:
                sell_trigger, headline = True, "Stop Loss (Safety First)"

            if sell_trigger:
                new_bal = current_qty * cur_p_thb
                row = [now_str, hunting_symbol, "SOLD", entry_price_thb, cur_p_thb, f"{profit:.2f}%", current_coin['Score'], new_bal, 0, headline, "ON"]
                if sheet:
                    sheet.append_row(row)
                    st.balloons()
                    time.sleep(2)
                    st.rerun()

# --- 7. กราฟและการรอรอบถัดไป ---
st.divider()
if not df_perf.empty:
    st.subheader("📈 กราฟการเติบโตของพอร์ต")
    # พล็อตเฉพาะคอลัมน์ Balance
    st.line_chart(df_perf['Balance'])

# สุ่มเวลา Refresh ครั้งใหญ่ (1-2 นาที) เพื่อความเป็นธรรมชาติ
refresh_time = random.randint(60, 120)
st.write(f"⏱️ ระบบสแกนเสร็จสิ้น จะเริ่มรอบใหม่ในอีก {refresh_time} วินาที...")
time.sleep(refresh_time)
st.rerun()
