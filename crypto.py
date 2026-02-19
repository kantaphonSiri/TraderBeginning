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
        
        # Features สำหรับ AI
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42)
        model.fit(X.values, y.values)
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        score = 0
        
        # Logic การให้คะแนน (0-100)
        if cur_p > float(last_row['EMA_20'].iloc[0]) > float(last_row['EMA_50'].iloc[0]): score += 50
        if 40 < float(last_row['RSI_14'].iloc[0]) < 65: score += 30
        pred_p = model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0]
        if pred_p > cur_p: score += 20
        
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": score}
    except: return None

# --- 3. โหลดข้อมูลจาก Sheet และประมวลผลสถานะ ---
sheet = init_gsheet()
live_rate = get_live_exchange_rate()
current_bal = 1000.0
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
                # 1. ดึง Balance ล่าสุดมาเป็นทุนไม้ถัดไป
                if 'Balance' in df_perf.columns:
                    last_val = df_perf.iloc[-1]['Balance']
                    if last_val != "": current_bal = float(last_val)
                
                # 2. เช็คว่ามีเหรียญค้างในพอร์ตไหม
                h_rows = df_perf[df_perf['สถานะ'] == 'HUNTING']
                if not h_rows.empty:
                    hunting_symbol = h_rows.iloc[-1]['เหรียญ']
                    entry_price_thb = float(h_rows.iloc[-1]['ราคาซื้อ(฿)'])
                    current_qty = float(h_rows.iloc[-1]['จำนวน'])
    except: pass

# --- 4. หน้าจอ Dashboard & Prediction ---
st.title("🦔 Pepper Hunter")
goal = 10000.0

# ส่วนคำนวณระยะเวลา (Estimation)
avg_profit = 0.07 # ตั้งเป้ากำไรเฉลี่ย 7% ต่อรอบ
if not df_perf.empty:
    sold_trades = df_perf[df_perf['สถานะ'] == 'SOLD']
    if len(sold_trades) > 0:
        # พยายามคำนวณจากประวัติจริง
        avg_profit = sold_trades['Balance'].pct_change().mean()
        if pd.isna(avg_profit) or avg_profit <= 0: avg_profit = 0.07

trades_to_goal = np.log(goal / current_bal) / np.log(1 + avg_profit)
est_days = round(trades_to_goal * 1.5, 1) # สมมติ 1.5 วันต่อ 1 รอบเทรด

c1, c2, c3 = st.columns(3)
c1.metric("งบปัจจุบัน (ทุนทบต้น)", f"{current_bal:,.2f} ฿")
c2.metric("เป้าหมาย", f"{goal:,.2f} ฿")
c3.metric("คาดการณ์ถึงเป้าใน", f"{est_days} วัน", f"เหลืออีก {max(0, int(trades_to_goal))} รอบ")

st.divider()

# --- 5. ระบบสแกนและตัดสินใจ (Section 5) ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "LINK-USD", "FET-USD"]
all_results = []

with st.status("AI กำลังล่าสัญญาณ...", expanded=True) as status:
    for sym in tickers:
        df_h = yf.download(sym, period="7d", interval="1h", progress=False)
        res = analyze_coin_ai(sym, df_h)
        if res:
            all_results.append(res)
    status.update(label="สแกนเสร็จสิ้น!", state="complete")

if all_results:
    # แสดงตาราง Radar
    scan_df = pd.DataFrame(all_results).sort_values(by='Score', ascending=False)
    st.subheader("📡 Sniper Radar (1h)")
    st.dataframe(scan_df, use_container_width=True)

    if sheet:
        now_str = get_now_thailand()
        
        # --- LOGIC การซื้อ (BUY) ---
        if not hunting_symbol:
            # เลือกตัวที่ Score สูงสุดและต้อง >= 80
            best_pick = all_results[0] if all_results[0]['Score'] >= 80 else None
            if best_pick:
                buy_p_thb = best_pick['Price_USD'] * live_rate
                qty = current_bal / buy_p_thb
                # บันทึก 11 คอลัมน์
                row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], current_bal, qty, "AI Sniper Buy", "ON"]
                sheet.append_row(row)
                st.success(f"🎯 ซื้อ {best_pick['Symbol']} ที่ราคา {buy_p_thb:,.2f} ฿")
                time.sleep(2)
                st.rerun()
            else:
                st.info("⌛ ยังไม่มีเหรียญที่ Score ถึง 80... บอทกำลังรอจังหวะ")

        # --- LOGIC การขาย (SELL / PROFIT LOCKER) ---
        else:
            current_data = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
            if current_data:
                current_p_thb = current_data['Price_USD'] * live_rate
                profit_pct = ((current_p_thb - entry_price_thb) / entry_price_thb) * 100
                new_total_bal = current_qty * current_p_thb
                
                sell_trigger = False
                headline = ""

                # 1. ถึงเป้าที่ตั้งใจ (Take Profit 10%)
                if profit_pct >= 10.0:
                    sell_trigger = True
                    headline = "Take Profit (Target 10%)"
                
                # 2. Profit Locker (กำไรเริ่มลดลงแต่ยังกำไรอยู่ และ Score ตก)
                elif 2.0 < profit_pct < 6.0 and current_data['Score'] < 50:
                    sell_trigger = True
                    headline = "Lock Profit (Prevent Reversal)"
                
                # 3. Stop Loss (กันเจ๊ง)
                elif profit_pct <= -5.0:
                    sell_trigger = True
                    headline = "Stop Loss (Risk Control)"

                if sell_trigger:
                    row = [now_str, hunting_symbol, "SOLD", entry_price_thb, current_p_thb, f"{profit_pct:.2f}%", current_data['Score'], new_total_bal, 0, headline, "ON"]
                    sheet.append_row(row)
                    st.warning(f"💰 ขาย {hunting_symbol} แล้ว! {headline} กำไร {profit_pct:.2f}%")
                    time.sleep(2)
                    st.rerun()
            
            # แสดงสถานะการถือครองปัจจุบัน
            st.markdown(f"### 🎯 กำลังถือ: **{hunting_symbol}**")
            st.write(f"ราคาซื้อ: {entry_price_thb:,.2f} ฿ | ราคาปัจจุบัน: {current_data['Price_USD']*live_rate:,.2f} ฿")
            st.metric("กำไรปัจจุบัน", f"{profit_pct:.2f}%", delta=f"{profit_pct:.2f}%")

# กราฟพอร์ต
if not df_perf.empty:
    st.subheader("📉 การเติบโตของเงินต้น (Compound Interest)")
    st.line_chart(df_perf['Balance'])

# พักเครื่อง 1 นาทีแล้วสแกนใหม่
time.sleep(60)
st.rerun()
