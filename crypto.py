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
st.set_page_config(page_title="Blue-chip Bet", layout="wide")
count = st_autorefresh(interval=600 * 1000, key="crypto_live_update")

# --- 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน (Cache 1 ชม.) ---
@st.cache_data(ttl=3600)
def get_usd_thb():
    try:
        ticker = yf.Ticker("THB=X")
        price = ticker.fast_info.last_price
        return price if price > 0 else 35.0
    except:
        return 35.0

# --- 3. ฟังก์ชันเชื่อมต่อ Google Sheets (รองรับแท็บ daily) ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        # แก้ไข: ระบุชื่อ Worksheet เป็น 'daily' ตามภาพของคุณ
        sheet = client.open("Blue-chip Bet").worksheet("daily") 
        return sheet
    except Exception as e:
        st.sidebar.error(f"⚠️ Sheets Connection Error: {e}")
        return None

# --- 4. ฟังก์ชัน Get Blue-chip อัตโนมัติ (คัดกรองความเสี่ยง) ---
@st.cache_data(ttl=3600)
def get_safe_bluechips():
    potential_list = [
        "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", 
        "ADA-USD", "DOT-USD", "LINK-USD", "AVAX-USD", "NEAR-USD"
    ]
    verified = []
    for ticker in potential_list:
        try:
            t = yf.Ticker(ticker)
            # กรองเหรียญที่มี Trading Volume > 100 ล้าน USD (กันเหรียญชิ่ง)
            if t.fast_info.get('last_volume', 0) > 100_000_000:
                verified.append(ticker)
        except: continue
    return verified if verified else potential_list[:6]

# --- 5. ฟังก์ชันวิเคราะห์เหรียญด้วย AI (Anti-Bot) ---
@st.cache_data(ttl=300)
def analyze_coin_ai(symbol, timeframe):
    try:
        time.sleep(random.uniform(0.5, 1.5)) 
        df = yf.download(symbol, period="60d", interval=timeframe, progress=False, timeout=15)
        if df.empty or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X, y = df[features].iloc[:-1], df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42)
        model.fit(X, y)
        
        pred_price = model.predict(df[features].iloc[[-1]])[0]
        cur_price = float(df.iloc[-1]['Close'])
        rsi = float(df.iloc[-1]['RSI_14'])

        score = 0
        if cur_price > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < rsi < 65: score += 30
        if pred_price > cur_price: score += 30

        return {"Symbol": symbol, "Price_USD": cur_price, "Target_USD": float(pred_price), "Score": score}
    except: return None

# --- 6. UI และส่วนควบคุม ---
st.title("💎 Blue-chip Bet")
thb_rate = get_usd_thb()
st.caption(f"อัปเดตอัตโนมัติรอบที่: {count} | เรทเงินบาท: 1 USD = {thb_rate:.2f} THB")

st.sidebar.header("🛠 การตั้งค่า")
auto_mode = st.sidebar.toggle("ค้นหา Blue-chip อัตโนมัติ", value=True)

if auto_mode:
    watch_list = get_safe_bluechips()
    st.sidebar.info(f"ค้นพบ {len(watch_list)} เหรียญความเสี่ยงต่ำ")
else:
    coin_input = st.sidebar.text_area("ใส่รายชื่อเหรียญ (คั่นด้วยคอมม่า):", value="BTC-USD, ETH-USD, SOL-USD")
    watch_list = [c.strip().upper() for c in coin_input.split(",")]

budget_thb = st.sidebar.number_input("งบประมาณของคุณ (บาท):", value=1000.0, step=500.0)
tf = st.sidebar.selectbox("Timeframe:", ["1h", "15m", "1d"])
sheet = init_gsheet()

# --- 7. ประมวลผล ---
available_coins = []
progress_bar = st.progress(0)

for idx, ticker in enumerate(watch_list):
    res = analyze_coin_ai(ticker, tf)
    if res:
        price_thb = res['Price_USD'] * thb_rate
        # กรองเหรียญที่งบถึง (ซื้อได้อย่างน้อยเศษส่วนของเหรียญ)
        res['Price_THB'] = price_thb
        res['Target_THB'] = res['Target_USD'] * thb_rate
        available_coins.append(res)
    progress_bar.progress((idx + 1) / len(watch_list))

# --- 8. แสดงผลโอกาสการลงทุน ---
st.subheader("🚀 โอกาสลงทุนล่าสุด")
if not available_coins:
    st.warning("❌ ไม่พบข้อมูลเหรียญในขณะนี้")
else:
    cols = st.columns(min(len(available_coins), 4))
    for i, res in enumerate(available_coins):
        with cols[i % 4]:
            color = "#28a745" if res['Score'] >= 80 else "#ffc107" if res['Score'] >= 60 else "#dc3545"
            st.markdown(f"""
                <div style="border: 1px solid #444; padding: 15px; border-radius: 12px; border-left: 8px solid {color}; background-color: #1e1e1e; margin-bottom: 10px;">
                    <h3 style="margin:0;">{res['Symbol'].split('-')[0]}</h3>
                    <h2 style="color:{color}; margin:10px 0;">฿{res['Price_THB']:,.2f}</h2>
                    <p style="font-size:14px; margin:0;">ความเชื่อมั่น AI: <b>{res['Score']}%</b></p>
                    <hr style="margin:10px 0; border:0.1px solid #333;">
                    <p style="color:#00ffcc; font-size:13px; margin:0;">งบ ฿{budget_thb:,.0f} ซื้อได้:</p>
                    <p style="font-size:18px; font-weight:bold; margin:0;">{(budget_thb/res['Price_THB']):.4f} เหรียญ</p>
                </div>
            """, unsafe_allow_html=True)

            # บันทึกลง Sheets เฉพาะตัวที่มั่นใจสูง
            if res['Score'] >= 80 and sheet:
                try:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row = [now, res['Symbol'], round(res['Price_THB'],2), round(res['Target_THB'],2), f"{res['Score']}%", tf]
                    sheet.append_row(row)
                    st.toast(f"✅ บันทึก {res['Symbol']} ลงแท็บ daily เรียบร้อย")
                except: pass

# --- 9. ส่วนสรุปสถิติจากแท็บ daily (Summary Dashboard) ---
st.divider()
st.subheader("📋 สรุปสัญญาณรายวัน & ประวัติ (แท็บ daily)")

if sheet:
    try:
        data = sheet.get_all_records()
        if data:
            df_history = pd.DataFrame(data)
            # ตรวจสอบว่าคอลัมน์แรกคือเวลา เพื่อใช้กรองวันที่
            df_history['Date_Temp'] = pd.to_datetime(df_history.iloc[:, 0]).dt.date
            today = datetime.now().date()
            today_signals = df_history[df_history['Date_Temp'] == today]
            
            c1, c2 = st.columns(2)
            c1.metric("จำนวนสัญญาณวันนี้", f"{len(today_signals)} ตัว")
            if not today_signals.empty:
                unique_coins = today_signals.iloc[:, 1].unique()
                c2.info(f"เหรียญที่พบวันนี้: {', '.join(unique_coins)}")
            
            # แสดงตารางประวัติ (เอาตัวล่าสุดขึ้นบน)
            st.dataframe(df_history.drop(columns=['Date_Temp']).iloc[::-1], use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลบันทึกในแท็บ daily")
    except Exception as e:
        st.error(f"ไม่สามารถดึงประวัติได้: {e}")
