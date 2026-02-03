import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import requests
from streamlit_autorefresh import st_autorefresh

# --- 1. ตั้งค่า Auto Refresh (ทุก 10 นาที) ---
# ช่วยให้ข้อมูลอัปเดตเองโดยไม่ต้องกดปุ่ม และอยู่ในเกณฑ์ที่ API ไม่แบน
count = st_autorefresh(interval=600 * 1000, key="crypto_auto_refresh")

# --- 2. ฟังก์ชันดึงรายชื่อเหรียญ (จำไว้ 1 ชม.) ---
@st.cache_data(ttl=3600)
def get_dynamic_blue_chips(limit=10):
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": limit, "page": 1}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        # กรอง Stablecoins ออก
        exclude = ['usdt', 'usdc', 'steth', 'usds', 'wbtc']
        return [f"{c['symbol'].upper()}-USD" for c in data if c['symbol'] not in exclude]
    except:
        return ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]

# --- 3. ฟังก์ชันวิเคราะห์ด้วย AI (จำไว้ 5 นาที) ---
@st.cache_data(ttl=300)
def analyze_coin_smart(symbol, timeframe):
    try:
        df = yf.download(symbol, period="100d", interval=timeframe, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty or len(df) < 50: return None

        # Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        # Simple AI Prediction
        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X = df[features].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        
        pred_price = model.predict(df[features].iloc[[-1]])[0]
        cur_price = df.iloc[-1]['Close']
        rsi = df.iloc[-1]['RSI_14']
        ema20, ema50 = df.iloc[-1]['EMA_20'], df.iloc[-1]['EMA_50']

        # Scoring
        score = 0
        if cur_price > ema20 > ema50: score += 40
        if 40 < rsi < 65: score += 30
        if pred_price > cur_price: score += 30

        return {"symbol": symbol, "price": cur_price, "pred": pred_price, "score": score}
    except:
        return None

# --- UI Layout ---
st.set_page_config(page_title="Auto AI Advisor", layout="wide")
st.title("🤖 Blue-chip Bet")
st.caption(f"อัปเดตอัตโนมัติรอบที่: {count} | เวลาปัจจุบัน: {pd.Timestamp.now().strftime('%H:%M:%S')}")

# Sidebar
budget = st.sidebar.number_input("งบประมาณของคุณ (USD)", value=1000.0)
tf = st.sidebar.selectbox("Timeframe", ["1h", "1d", "15m"])
num_coins = st.sidebar.slider("จำนวนเหรียญที่สแกน", 5, 15, 8)

# ดึงข้อมูล
blue_chips = get_dynamic_blue_chips(limit=num_coins)

# แสดงผล Card แบบ Dynamic
st.subheader("💎 สรุปโอกาสการลงทุนล่าสุด")
results = []
cols = st.columns(4)

for i, coin in enumerate(blue_chips):
    res = analyze_coin_smart(coin, tf)
    if res:
        results.append(res)
        with cols[i % 4]:
            status_color = "#28a745" if res['score'] >= 80 else "#ffc107" if res['score'] >= 60 else "#dc3545"
            
            # แก้ไขจาก unsafe_allow_value เป็น unsafe_allow_html
            st.markdown(f"""
            <div style="border: 1px solid #ddd; padding: 15px; border-radius: 10px; border-left: 8px solid {status_color}; margin-bottom: 10px;">
                <h3 style="margin:0;">{res['symbol']}</h3>
                <p style="font-size: 24px; font-weight: bold; margin:5px 0;">${res['price']:,.2f}</p>
                <p style="margin:0;">ความมั่นใจ: <b>{res['score']}%</b></p>
                <p style="margin:0; color: gray;">เป้าหมาย AI: ${res['pred']:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)

# ตารางสรุปภาพรวม
if results:
    st.divider()
    df_final = pd.DataFrame(results)
    st.write("### 📊 ตารางเปรียบเทียบ (เรียงตามคะแนนความมั่นใจ)")
    st.dataframe(df_final.sort_values(by="score", ascending=False), use_container_width=True)

st.info("💡 ระบบจะสแกนและอัปเดตคะแนนอัตโนมัติ ทุกตัวเลขถูกคำนวณจากความสอดคล้องของ Trend, RSI และ AI Prediction")
