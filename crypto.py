import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import json

# --- 1. การตั้งค่าหน้าจอและระบบ Auto-refresh ---
st.set_page_config(page_title="Blue-chip Bet", layout="wide")
# ระบบจะ Refresh ตัวเองอัตโนมัติทุก 10 นาที (600,000 มิลลิวินาที)
count = st_autorefresh(interval=600 * 1000, key="crypto_live_update")

# --- 2. ฟังก์ชันเชื่อมต่อ Google Sheets ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # ดึง Credentials จาก Streamlit Secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # ค้นหาไฟล์ Google Sheets (แก้ชื่อไฟล์ตรงนี้)
        sheet = client.open("Blue-chip Bet").sheet1 
        return sheet
    except Exception as e:
        st.error(f"เชื่อมต่อ Google Sheets ไม่ได้: {e}")
        return None

# --- 3. ฟังก์ชันวิเคราะห์เหรียญด้วย AI ---
@st.cache_data(ttl=300) # แคชผลวิเคราะห์ไว้ 5 นาที
def analyze_coin_ai(symbol, timeframe):
    try:
        # ดึงข้อมูลย้อนหลัง 100 วัน
        df = yf.download(symbol, period="100d", interval=timeframe, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty or len(df) < 50: return None

        # คำนวณ Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        # สร้างโมเดล AI ทำนายราคาแท่งถัดไป
        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X = df[features].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        
        # ทำนายผล
        last_row = df[features].iloc[[-1]]
        pred_price = model.predict(last_row)[0]
        
        cur_price = df.iloc[-1]['Close']
        rsi = df.iloc[-1]['RSI_14']
        ema20 = df.iloc[-1]['EMA_20']
        ema50 = df.iloc[-1]['EMA_50']

        # ระบบคำนวณคะแนนความเชื่อมั่น (0-100)
        score = 0
        if cur_price > ema20 > ema50: score += 40  # เทรนขาขึ้นชัดเจน
        if 40 < rsi < 65: score += 30             # ไม่แพงเกินไป
        if pred_price > cur_price: score += 30     # AI มองว่าไปต่อได้

        return {
            "Symbol": symbol,
            "Price": round(float(cur_price), 2),
            "Target": round(float(pred_price), 2),
            "Score": score,
            "RSI": round(float(rsi), 2)
        }
    except Exception as e:
        return None

# --- 4. ส่วนการแสดงผล UI ---
st.title("💎 Blue-chip Bet")
st.caption(f"อัปเดตอัตโนมัติรอบที่: {count} | เวลา: {datetime.now().strftime('%H:%M:%S')}")

# Sidebar
budget = st.sidebar.number_input("เงินงบประมาณ (USD):", value=1000.0)
tf = st.sidebar.selectbox("ช่วงเวลา (Timeframe):", ["1h", "15m", "1d"])
blue_chips = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD"]

# เริ่มกระบวนการสแกน
sheet = init_gsheet()
results = []

st.subheader("🚀 สรุปโอกาสการลงทุนล่าสุด")
cols = st.columns(len(blue_chips))

for i, ticker in enumerate(blue_chips):
    res = analyze_coin_ai(ticker, tf)
    if res:
        results.append(res)
        with cols[i]:
            # เลือกสีตามความมั่นใจ
            status_color = "#28a745" if res['Score'] >= 80 else "#ffc107" if res['Score'] >= 60 else "#dc3545"
            
            st.markdown(f"""
                <div style="border: 1px solid #444; padding: 10px; border-radius: 10px; border-left: 8px solid {status_color}; background-color: #1e1e1e; min-height: 180px;">
                    <h3 style="color:white; margin:0;">{res['Symbol']}</h3>
                    <h2 style="color:{status_color}; margin:10px 0;">${res['Price']:,}</h2>
                    <p style="color:#ccc; margin:0;">มั่นใจ: <b>{res['Score']}%</b></p>
                    <p style="color:#888; font-size:12px; margin:0;">เป้าหมาย: ${res['Target']:,}</p>
                    <p style="color:#888; font-size:12px; margin:0;">ซื้อได้: {(budget/res['Price']):.4f}</p>
                </div>
            """, unsafe_allow_html=True)

            # บันทึกลง Google Sheets อัตโนมัติเฉพาะตัวที่คะแนนสูง (Signal Detected)
            if res['Score'] >= 80 and sheet:
                try:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row = [now, res['Symbol'], res['Price'], res['Target'], f"{res['Score']}%", tf, "Signal Detected"]
                    sheet.append_row(row)
                    st.toast(f"✅ บันทึกสัญญาณ {res['Symbol']} ลง Cloud แล้ว!")
                except:
                    pass

# แสดงตารางประวัติจาก Google Sheets
st.divider()
st.subheader("📋 ประวัติการตรวจพบสัญญาณ (จาก Cloud Database)")
if sheet:
    try:
        history = sheet.get_all_records()
        if history:
            st.dataframe(pd.DataFrame(history).iloc[::-1], use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลประวัติใน Google Sheets")
    except:
        st.warning("ไม่สามารถดึงข้อมูลประวัติได้ในขณะนี้")


