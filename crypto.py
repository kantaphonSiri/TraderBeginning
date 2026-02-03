import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# --- 1. การตั้งค่าหน้าจอและระบบ Auto-refresh ---
st.set_page_config(page_title="Blue-chip Bet Pro", layout="wide")
# ปรับ Refresh เป็น 10 นาที เพื่อความปลอดภัยของ API
count = st_autorefresh(interval=600 * 1000, key="crypto_live_update")

# --- 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน (พร้อมระบบ Cache) ---
@st.cache_data(ttl=3600)
def get_usd_thb():
    try:
        ticker = yf.Ticker("THB=X")
        price = ticker.fast_info.last_price
        return price if price > 0 else 35.0
    except:
        return 35.0

# --- 3. ฟังก์ชันเชื่อมต่อ Google Sheets ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Blue-chip Bet").sheet1 
        return sheet
    except Exception as e:
        st.sidebar.error(f"⚠️ Sheets Connection Error: {e}")
        return None

# --- 4. ฟังก์ชันวิเคราะห์เหรียญ (Anti-Bot & AI) ---
@st.cache_data(ttl=300)
def analyze_coin_ai(symbol, timeframe):
    try:
        # Anti-bot: สุ่มเวลาหน่วง 0.5 - 2 วินาที ก่อนเรียก API
        time.sleep(random.uniform(0.5, 2.0))
        
        # ดึงข้อมูลย้อนหลัง
        df = yf.download(symbol, period="60d", interval=timeframe, progress=False, timeout=15)
        
        if df.empty or len(df) < 30: return None
        
        # จัดการ Multi-index columns ของ yfinance เวอร์ชั่นใหม่
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # คำนวณ Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        # สร้าง Model AI แบบลดความซับซ้อนเพื่อให้รันไวและเสถียร
        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X = df[features].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        
        model = RandomForestRegressor(n_estimators=30, random_state=42)
        model.fit(X, y)
        
        last_row = df[features].iloc[[-1]]
        pred_price = model.predict(last_row)[0]
        cur_price = float(df.iloc[-1]['Close'])
        rsi = float(df.iloc[-1]['RSI_14'])

        # Scoring Logic
        score = 0
        if cur_price > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < rsi < 65: score += 30
        if pred_price > cur_price: score += 30

        return {
            "Symbol": symbol,
            "Price_USD": cur_price,
            "Target_USD": float(pred_price),
            "Score": score
        }
    except Exception as e:
        return None

# --- 5. UI และส่วนควบคุม ---
st.title("💎 Blue-chip Bet (Smart & Stable)")
thb_rate = get_usd_thb()
st.caption(f"อัปเดตอัตโนมัติรอบที่: {count} | เรทเงินบาท: 1 USD = {thb_rate:.2f} THB")

# Sidebar: No Hard Code - ให้ User เลือกเหรียญเองได้
st.sidebar.header("🛠 การตั้งค่า")
coin_input = st.sidebar.text_area("ใส่รายชื่อเหรียญ (คั่นด้วยคอมม่า):", 
                                 value="BTC-USD, ETH-USD, SOL-USD, BNB-USD, XRP-USD, ADA-USD")
watch_list = [c.strip().upper() for c in coin_input.split(",")]

budget_thb = st.sidebar.number_input("งบประมาณของคุณ (บาท):", value=1000.0, step=500.0)
tf = st.sidebar.selectbox("Timeframe:", ["1h", "15m", "1d"])

sheet = init_gsheet()

# --- 6. ประมวลผลและกรองตามงบประมาณ ---
available_coins = []
progress_bar = st.progress(0)

for idx, ticker in enumerate(watch_list):
    res = analyze_coin_ai(ticker, tf)
    if res:
        price_thb = res['Price_USD'] * thb_rate
        # กรองเฉพาะเหรียญที่งบถึง (ซื้อได้ 1 เหรียญเต็ม)
        if budget_thb >= price_thb:
            res['Price_THB'] = price_thb
            res['Target_THB'] = res['Target_USD'] * thb_rate
            available_coins.append(res)
    progress_bar.progress((idx + 1) / len(watch_list))

# --- 7. แสดงผลลัพธ์ ---
st.subheader("🚀 โอกาสลงทุนที่เหมาะสมกับงบของคุณ")

if not available_coins:
    st.warning(f"❌ ไม่พบเหรียญที่ราคาต่ำกว่า ฿{budget_thb:,.2f} ในรายการสแกนของคุณ")
else:
    # แบ่งแถวละ 3-4 เหรียญเพื่อให้สวยงาม
    cols = st.columns(len(available_coins)) if len(available_coins) <= 4 else st.columns(3)
    
    for i, res in enumerate(available_coins):
        target_col = cols[i % len(cols)]
        with target_col:
            color = "#28a745" if res['Score'] >= 80 else "#ffc107" if res['Score'] >= 60 else "#dc3545"
            st.markdown(f"""
                <div style="border: 1px solid #444; padding: 15px; border-radius: 12px; border-left: 8px solid {color}; background-color: #1e1e1e; margin-bottom: 10px;">
                    <h3 style="color:white; margin:0;">{res['Symbol'].replace('-USD','')}</h3>
                    <h2 style="color:{color}; margin:10px 0;">฿{res['Price_THB']:,.2f}</h2>
                    <p style="color:#ccc; margin:0; font-size:14px;">ความเชื่อมั่น AI: <b>{res['Score']}%</b></p>
                    <hr style="margin:10px 0; border:0.5px solid #333;">
                    <p style="color:#00ffcc; font-size:13px; margin:0;">งบ ฿{budget_thb:,.0f} ซื้อได้:</p>
                    <p style="color:white; font-size:18px; font-weight:bold; margin:0;">{(budget_thb/res['Price_THB']):.4f} เหรียญ</p>
                </div>
            """, unsafe_allow_html=True)

            # บันทึกเฉพาะตัวที่มั่นใจสูงลง Google Sheets
            if res['Score'] >= 80 and sheet:
                try:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row = [now, res['Symbol'], round(res['Price_THB'],2), round(res['Target_THB'],2), f"{res['Score']}%", tf]
                    sheet.append_row(row)
                    st.toast(f"✅ บันทึก {res['Symbol']} เรียบร้อย")
                except: pass

st.divider()
st.subheader("📋 ประวัติสัญญาณล่าสุด")
if sheet:
    try:
        data = sheet.get_all_records()
        if data:
            st.dataframe(pd.DataFrame(data).iloc[::-1], use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลในฐานข้อมูล")
    except:
        st.error("ไม่สามารถดึงข้อมูลจาก Sheets ได้")
