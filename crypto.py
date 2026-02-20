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
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
table_area = st.empty()
progress_bar = st.progress(0)

for i, sym in enumerate(tickers):
    df_h = yf.download(sym, period="5d", interval="1h", progress=False, timeout=10) # เพิ่ม timeout
    if not df_h.empty:
        res = analyze_coin_ai(sym, df_h)
        if res:
            all_results.append(res)
            table_area.dataframe(pd.DataFrame(all_results).sort_values('Score', ascending=False), use_container_width=True)
    progress_bar.progress((i + 1) / len(tickers))
    time.sleep(0.5) # ลด jitter ให้เหลือสั้นๆ เพื่อเลี่ยง timeout

# --- 6. ตัดสินใจและจบงาน ---
if all_results:
    # (Logic การซื้อขายคงเดิมตามที่คุณมี...)
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
