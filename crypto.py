import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & STYLES ---
st.set_page_config(page_title="Pepper Hunter AI", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CORE FUNCTIONS ---
def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

@st.cache_data(ttl=60)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1])
    except: return 35.50

# --- 3. DATA LOAD & AUTO-EXIT LOGIC ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

# ตัวแปรเป้าหมาย (ปรับเปลี่ยนได้ตามใจเจ้านาย)
TP_PCT = 5.0  # กำไร 5% ขาย
SL_PCT = -3.0 # ขาดทุน 3% ขาย

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            df_perf.columns = df_perf.columns.str.strip()
            last_row = df_perf.iloc[-1]
            
            # ดึงข้อมูลปัจจุบัน
            balance = float(last_row.get('Balance', 1000))
            status = last_row.get('สถานะ')
            coin = last_row.get('เหรียญ')
            entry_price = float(last_row.get('ราคาซื้อ(฿)', 0))

            # --- [ 핵심 ] ระบบขายอัตโนมัติ ---
            if status == 'HUNTING' and coin:
                # ดึงราคาปัจจุบันมาเช็ค
                ticker_data = yf.download(coin, period="1d", interval="1m", progress=False)
                if not ticker_data.empty:
                    current_price_usd = float(ticker_data['Close'].iloc[-1])
                    current_price_thb = current_price_usd * live_rate
                    pnl_pct = ((current_price_thb - entry_price) / entry_price) * 100

                    # เช็คเงื่อนไข TP หรือ SL
                    if pnl_pct >= TP_PCT or pnl_pct <= SL_PCT:
                        st.warning(f"🚀 AUTO-EXIT TRIGGERED: {coin} at {pnl_pct:.2f}%")
                        
                        # คำนวณ Balance ใหม่ (แบบง่าย)
                        new_balance = balance * (1 + (pnl_pct/100))
                        
                        # บันทึกข้อมูลปิดไม้ลง Sheet
                        new_row = [
                            now_th.strftime("%Y-%m-%d %H:%M"), # วันที่
                            coin,                             # เหรียญ
                            "CLOSED",                         # สถานะ
                            entry_price,                      # ราคาซื้อ
                            current_price_thb,                # ราคาขาย
                            f"{pnl_pct:.2f}%",                # กำไร%
                            0,                                # Score
                            new_balance,                      # Balance ใหม่
                            0,                                # จำนวน
                            "AUTO_EXIT_TRIGGER",              # Headline
                            "DONE",                           # Bot_Status
                            "N/A",                            # Sentiment
                            f"Exit at {current_price_thb:.2f}"# News_Headline
                        ]
                        sheet.append_row(new_row)
                        st.success("✅ บันทึกการขายลง Google Sheets เรียบร้อย!")
                        time.sleep(3)
                        st.rerun()

    except Exception as e:
        st.error(f"Error in Logic: {e}")

# --- 4. UI DISPLAY (เหมือนเดิมแต่เพิ่มความล้ำ) ---
st.title(f"🦔 Pepper Hunter")
st.write(f"Last Scan: `{update_time}` | USD/THB: `{live_rate:.2f}`")

# แสดงข้อมูลพอร์ตปัจจุบัน
c1, c2, c3 = st.columns(3)
if 'df_perf' in locals() and not df_perf.empty:
    c1.metric("Balance", f"{balance:,.2f} ฿")
    c2.metric("Status", status)
    c3.metric("Current Asset", coin if coin else "None")

st.divider()

# --- ส่วนของการวิเคราะห์ Market Radar (ใส่โค้ดเดิมของเจ้านายตรงนี้) ---
# ... (ดึง tickers และสร้างตาราง Market Radar เหมือนชุดก่อน) ...

# --- 5. FOOTER & REFRESH ---
st.info(f"⚙️ Auto-Exit Active: TP {TP_PCT}% | SL {SL_PCT}%")
bar = st.progress(0, text="System scanning 24/7 on Streamlit Cloud...")
for i in range(100):
    time.sleep(0.01)
    bar.progress(i + 1)

time.sleep(295)
st.rerun()
