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
        
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": score}
    except: return None

# --- 3. ดึงข้อมูลจาก Google Sheet เพื่อวิเคราะห์ต่อ ---
sheet = init_gsheet()
live_rate = get_live_exchange_rate()
current_bal = 1000.0  # ทุนเริ่มต้นกรณีไม่มีข้อมูลใน Sheet
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
                # ดึง Balance ล่าสุดมาเป็นทุนไม้ถัดไป (Auto-Compound)
                last_row_data = df_perf.iloc[-1]
                if 'Balance' in df_perf.columns and last_row_data['Balance'] != "":
                    current_bal = float(last_row_data['Balance'])
                
                # ตรวจสอบว่ากำลังถือเหรียญอะไรอยู่หรือไม่
                h_rows = df_perf[df_perf['สถานะ'] == 'HUNTING']
                if not h_rows.empty:
                    hunting_symbol = h_rows.iloc[-1]['เหรียญ']
                    entry_price_thb = float(h_rows.iloc[-1]['ราคาซื้อ(฿)'])
                    current_qty = float(h_rows.iloc[-1]['จำนวน'])
    except Exception as e:
        st.warning(f"⚠️ ดึงข้อมูลจาก Sheet พลาด: {e}")

# --- 4. Dashboard ส่วนแสดงผล ---
st.title("🦔 Pepper Hunter")
st.subheader(f"เป้าหมาย: 10,000 ฿ | ปัจจุบัน: {current_bal:,.2f} ฿")

# --- 5. ระบบ Radar สแกนตลาด ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "AVAX-USD", "LINK-USD", "AR-USD", "DOT-USD"]
all_results = []

with st.spinner("AI กำลังวิเคราะห์ข้อมูลรายชั่วโมง..."):
    for sym in tickers:
        df_h = yf.download(sym, period="7d", interval="1h", progress=False)
        if not df_h.empty:
            res = analyze_coin_ai(sym, df_h)
            if res:
                all_results.append(res)

if all_results:
    scan_df = pd.DataFrame(all_results).sort_values(by='Score', ascending=False)
    st.dataframe(scan_df, use_container_width=True)

    if sheet:
        now_str = get_now_thailand()
        
        # --- [BUY LOGIC] ---
        if not hunting_symbol:
            best_pick = all_results[0] if all_results[0]['Score'] >= 80 else None
            if best_pick:
                buy_p_thb = best_pick['Price_USD'] * live_rate
                qty = current_bal / buy_p_thb
                row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], current_bal, qty, "AI Sniper Buy", "ON"]
                sheet.append_row(row)
                st.success(f"🎯 ซื้อเหรียญเดียวเน้นๆ: {best_pick['Symbol']}")
                st.rerun()
            else:
                st.info("⌛ รอสัญญาณ Score >= 80 เพื่อความปลอดภัยของเงินต้น")

        # --- [SELL LOGIC: เน้นไม่ขาดทุนจากทุนเดิม] ---
        else:
            current_coin = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
            if current_coin:
                current_p_thb = current_coin['Price_USD'] * live_rate
                profit_pct = ((current_p_thb - entry_price_thb) / entry_price_thb) * 100
                new_total_bal = current_qty * current_p_thb
                
                sell_trigger = False
                headline = ""

                # 1. ขายทำกำไร (Take Profit 8-10%)
                if profit_pct >= 8.0:
                    sell_trigger = True
                    headline = "Take Profit (Success)"
                
                # 2. ป้องกันเงินต้น (No-Loss Exit) 
                # ถ้ากำไรเคยขึ้นไปแล้ว และกำลังจะร่วงกลับมาที่ทุน (เหลือกำไรแค่ 0.5%) ให้ขายทิ้งทันที
                elif 0.2 < profit_pct < 1.0 and current_coin['Score'] < 50:
                    sell_trigger = True
                    headline = "No-Loss Exit (Protect Capital)"
                
                # 3. Stop Loss เมื่อผิดทางรุนแรง
                elif profit_pct <= -4.0:
                    sell_trigger = True
                    headline = "Stop Loss (Safety First)"

                if sell_trigger:
                    row = [now_str, hunting_symbol, "SOLD", entry_price_thb, current_p_thb, f"{profit_pct:.2f}%", current_coin['Score'], new_total_bal, 0, headline, "ON"]
                    sheet.append_row(row)
                    st.warning(f"💰 {headline}: {hunting_symbol} กำไร {profit_pct:.2f}%")
                    st.rerun()

            # แสดงสถานะปัจจุบัน
            st.info(f"📍 กำลังถือ: {hunting_symbol} | ทุน: {entry_price_thb:,.2f} ฿ | กำไรตอนนี้: {profit_pct:.2f}%")

# กราฟพอร์ต
if not df_perf.empty:
    st.line_chart(df_perf['Balance'])

time.sleep(60)
st.rerun()

