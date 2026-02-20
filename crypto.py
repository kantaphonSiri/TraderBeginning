import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta, timezone
import requests
from requests import Session

# สร้าง Session เพื่อใช้ดึงข้อมูลให้ดูเป็นธรรมชาติ
def get_session():
    session = Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session
    
# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันพื้นฐาน ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet("trade_learning")
    except Exception as e:
        st.error(f"GSheet Error: {e}")
        return None

def analyze_coin_ai(symbol, df):
    try:
        if len(df) < 50: return None
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42)
        model.fit(X.values, y.values)
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        score = 0
        if cur_p > float(last_row['EMA_20'].iloc[0]) > float(last_row['EMA_50'].iloc[0]): score += 50
        if 40 < float(last_row['RSI_14'].iloc[0]) < 65: score += 30
        if model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0] > cur_p: score += 20
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": score, "Last_Update": datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")}
    except: return None

# --- 3. ดึงข้อมูล ---
sheet = init_gsheet()
live_rate = 35.5 # หรือดึงจาก yf สั้นๆ
df_perf = pd.DataFrame()
current_bal = 1000.0
hunting_symbol = None

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        current_bal = float(df_perf.iloc[-1]['Balance']) if 'Balance' in df_perf.columns else 1000.0
        h_rows = df_perf[df_perf['สถานะ'] == 'HUNTING']
        if not h_rows.empty:
            hunting_symbol = h_rows.iloc[-1]['เหรียญ']
            entry_p = float(h_rows.iloc[-1]['ราคาซื้อ(฿)'])
            current_qty = float(h_rows.iloc[-1]['จำนวน'])

# --- 4. หน้า UI ---
st.title("🦔 Pepper Hunter")
st.write(f"💰 Balance: {current_bal:,.2f} ฿ | Target: 10,000 ฿")

# --- 5. สแกน (ลดความเสี่ยง Timeout) ---
# --- 5. สแกน (ฉบับแก้ไขตารางไม่ขึ้น) ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
session = get_session() # เรียกใช้ session ที่เราสร้างไว้

# ส่วนแสดงผลบนหน้าจอ
status_area = st.empty()
progress_bar = st.progress(0)
get_session
for i, sym in enumerate(tickers):
    status_area.info(f"🔍 AI กำลังพยายามดึงข้อมูล: {sym}...")
    try:
        # ดึงข้อมูลผ่าน session เพื่อเลี่ยงการโดนบล็อก
        ticker_obj = yf.Ticker(sym, session=session)
        df_h = ticker_obj.history(period="5d", interval="1h", timeout=15)
        
        if not df_h.empty:
            res = analyze_coin_ai(sym, df_h)
            if res:
                all_results.append(res)
        else:
            st.warning(f"⚠️ {sym}: ข้อมูลว่างเปล่า (Yahoo ไม่ตอบสนอง)")
            
    except Exception as e:
        st.error(f"❌ {sym}: เกิดข้อผิดพลาด {str(e)}")
    
    progress_bar.progress((i + 1) / len(tickers))
    time.sleep(random.uniform(1.0, 3.0)) # สุ่มเวลาพักให้เหมือนมนุษย์

status_area.empty()

# แสดงผลตาราง
if all_results:
    st.subheader("📊 AI Sniper Radar (Real-time Scans)")
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    st.dataframe(scan_df, use_container_width=True)
else:
    st.error("❌ ยังดึงข้อมูลไม่ได้ (IP อาจถูกบล็อกชั่วคราว) แนะนำให้รอ 10-15 นาทีแล้วค่อย Refresh ใหม่ครับ")

# --- 6. ตัดสินใจและจบงาน ---
# --- 6. ตัดสินใจซื้อ-ขาย (Logic) ---
if all_results:
    now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")
    
    # ดึงผลลัพธ์ที่คะแนนสูงสุดมาดู
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    best_pick = all_results[0] if all_results[0]['Score'] >= 70 else None # ปรับเหลือ 70 ให้ซื้อง่ายขึ้น

    # --- กรณีที่ 1: ยังไม่มีเหรียญในมือ (ตัดสินใจซื้อ) ---
    if not hunting_symbol:
        if best_pick:
            buy_p_thb = best_pick['Price_USD'] * live_rate
            qty = current_bal / buy_p_thb
            # เตรียมแถวข้อมูลเพื่อบันทึกลง Sheet
            row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], current_bal, qty, "AI Sniper Buy", "ON"]
            if sheet:
                sheet.append_row(row)
                st.success(f"🎯 ตัดสินใจซื้อ: {best_pick['Symbol']} ที่ราคา {buy_p_thb:,.2f} ฿")
                time.sleep(2)
                st.rerun()
        else:
            st.info("⌛ คะแนนยังไม่ถึง 70 บอทกำลังซุ่มรอโอกาส...")

    # --- กรณีที่ 2: มีเหรียญในมืออยู่แล้ว (ตัดสินใจขาย) ---
    else:
        current_coin = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
        if current_coin:
            cur_p_thb = current_coin['Price_USD'] * live_rate
            profit_pct = ((cur_p_thb - entry_p) / entry_p) * 100
            
            st.warning(f"📍 กำลังถือ: {hunting_symbol} | กำไรตอนนี้: {profit_pct:.2f}%")

            sell_trigger = False
            headline = ""

            if profit_pct >= 8.0: # กำไรถึงเป้า
                sell_trigger, headline = True, "Take Profit 🚀"
            elif profit_pct <= -4.0: # ตัดขาดทุน
                sell_trigger, headline = True, "Stop Loss 🛡️"
            elif profit_pct > 0.5 and current_coin['Score'] < 50: # กราฟเริ่มเสียทรง
                sell_trigger, headline = True, "Exit (Score Drop) 📉"

            if sell_trigger:
                new_bal = current_qty * cur_p_thb
                row = [now_str, hunting_symbol, "SOLD", entry_p, cur_p_thb, f"{profit_pct:.2f}%", current_coin['Score'], new_bal, 0, headline, "ON"]
                if sheet:
                    sheet.append_row(row)
                    st.balloons()
                    time.sleep(2)
                    st.rerun()
    pass

st.divider()
if not df_perf.empty:
    st.line_chart(df_perf['Balance'])

# แทนที่จะใช้ sleep นานๆ ให้ใช้ปุ่มหรือการรีเฟรชที่สั้นลง
if st.button("🔄 Force Refresh Now"):
    st.rerun()

st.write("ระบบจะสแกนใหม่โดยอัตโนมัติในระยะเวลาอันสั้น...")
time.sleep(30) # ลดเหลือ 30 วินาทีเพื่อเลี่ยง Health Check Fail
st.rerun()



