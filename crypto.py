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
count = st_autorefresh(interval=600 * 1000, key="crypto_live_update")

# --- 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน USD to THB ---
@st.cache_data(ttl=3600) # อัปเดตเรทเงินบาททุก 1 ชม.
def get_usd_thb():
    try:
        data = yf.Ticker("THB=X")
        price = data.fast_info.last_price
        return price if price > 0 else 35.0 # fallback ถ้าดึงไม่ได้
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
        st.error(f"เชื่อมต่อ Google Sheets ไม่ได้: {e}")
        return None

# --- 4. ฟังก์ชันวิเคราะห์เหรียญด้วย AI ---
@st.cache_data(ttl=300)
def analyze_coin_ai(symbol, timeframe):
    try:
        df = yf.download(symbol, period="100d", interval=timeframe, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 50: return None

        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X, y = df[features].iloc[:-1], df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        
        pred_price = model.predict(df[features].iloc[[-1]])[0]
        cur_price = df.iloc[-1]['Close']
        score = 0
        if cur_price > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < df.iloc[-1]['RSI_14'] < 65: score += 30
        if pred_price > cur_price: score += 30

        return {
            "Symbol": symbol,
            "Price_USD": float(cur_price),
            "Target_USD": float(pred_price),
            "Score": score
        }
    except: return None

# --- UI และการคำนวณ ---
st.title("💎 Blue-chip Bet (เวอร์ชันเงินบาท)")
thb_rate = get_usd_thb()
st.caption(f"อัปเดตอัตโนมัติรอบที่: {count} | เรทเงินบาทวันนี้: 1 USD = {thb_rate:.2f} THB")

# Sidebar
budget_thb = st.sidebar.number_input("งบประมาณของคุณ (บาท):", value=30000.0, step=1000.0)
budget_usd = budget_thb / thb_rate
tf = st.sidebar.selectbox("ช่วงเวลา (Timeframe):", ["1h", "15m", "1d"])

blue_chips = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD"]
sheet = init_gsheet()
cols = st.columns(len(blue_chips))

for i, ticker in enumerate(blue_chips):
    res = analyze_coin_ai(ticker, tf)
    if res:
        price_thb = res['Price_USD'] * thb_rate
        target_thb = res['Target_USD'] * thb_rate
        
        with cols[i]:
            color = "#28a745" if res['Score'] >= 80 else "#ffc107" if res['Score'] >= 60 else "#dc3545"
            st.markdown(f"""
                <div style="border: 1px solid #444; padding: 10px; border-radius: 10px; border-left: 8px solid {color}; background-color: #1e1e1e; min-height: 200px;">
                    <h3 style="color:white; margin:0;">{res['Symbol'].split('-')[0]}</h3>
                    <h2 style="color:{color}; margin:10px 0;">฿{price_thb:,.0f}</h2>
                    <p style="color:#ccc; margin:0; font-size:14px;">มั่นใจ: <b>{res['Score']}%</b></p>
                    <p style="color:#888; font-size:12px; margin:0;">เป้าหมาย: ฿{target_thb:,.0f}</p>
                    <hr style="margin:8px 0; border:0.5px solid #333;">
                    <p style="color:#00ffcc; font-size:13px; margin:0;">งบ ฿{budget_thb:,.0f} ซื้อได้:</p>
                    <p style="color:white; font-size:16px; font-weight:bold; margin:0;">{(budget_usd/res['Price_USD']):.4f} เหรียญ</p>
                </div>
            """, unsafe_allow_html=True)

            # บันทึกลง Sheets (แปลงเป็น THB ก่อนบันทึก)
            if res['Score'] >= 80 and sheet:
                try:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row = [now, res['Symbol'], f"{price_thb:,.2f}", f"{target_thb:,.2f}", f"{res['Score']}%", tf, "Signal (THB)"]
                    sheet.append_row(row)
                    st.toast(f"✅ บันทึก {res['Symbol']} (฿) เรียบร้อย")
                except: pass

st.divider()
st.subheader("📋 ประวัติสัญญาณในหน่วยเงินบาท")
if sheet:
    try:
        data = sheet.get_all_records()
        if data: st.dataframe(pd.DataFrame(data).iloc[::-1], use_container_width=True)
        else: st.info("ยังไม่มีข้อมูลใน Google Sheets")
    except: st.warning("ดึงข้อมูลไม่ได้")
