import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import requests
from streamlit_autorefresh import st_autorefresh # ต้องติดตั้งเพิ่ม

# 1. ตั้งค่า Auto Refresh ทุกๆ 10 นาที (600,000 มิลลิวินาที)
# การไม่ Refresh ถี่เกินไปช่วยให้ไม่โดนแบน และลดภาระ CPU
count = st_autorefresh(interval=600 * 1000, key="fngcounter")

# 2. ฟังก์ชันดึงรายชื่อเหรียญ (จำไว้ 1 ชม.)
@st.cache_data(ttl=3600)
def get_dynamic_blue_chips(limit=10):
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": limit, "page": 1}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        return [f"{c['symbol'].upper()}-USD" for c in data if c['symbol'] not in ['usdt', 'usdc']]
    except:
        return ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]

# 3. ฟังก์ชันวิเคราะห์ (จำไว้ 5 นาที เพื่อความแม่นยำแต่ประหยัด API)
@st.cache_data(ttl=300)
def analyze_coin_smart(symbol, timeframe):
    try:
        # ดึงข้อมูลผ่าน yfinance
        df = yf.download(symbol, period="100d", interval=timeframe, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty or len(df) < 50: return None

        # Technical Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        # AI Logic
        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X, y = df[features].iloc[:-1], df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        
        pred_price = model.predict(df[features].iloc[[-1]])[0]
        cur_price = df.iloc[-1]['Close']
        rsi = df.iloc[-1]['RSI_14']
        ema20, ema50 = df.iloc[-1]['EMA_20'], df.iloc[-1]['EMA_50']

        # Scoring System
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
st.caption(f"อัปเดตข้อมูลอัตโนมัติทุก 10 นาที | จำนวนครั้งที่อัปเดตในรอบนี้: {count}")

budget = st.sidebar.number_input("Budget (USD)", value=1000.0)
tf = st.sidebar.selectbox("Timeframe", ["1h", "1d", "15m"])

# ดึงรายชื่อเหรียญและเริ่มวิเคราะห์ทันที (ไม่ต้องกดปุ่ม)
blue_chips = get_dynamic_blue_chips(limit=8)

# ส่วนแสดงผลสรุป (Dashboard)
st.subheader(f"💎 ข้อมูลวิเคราะห์ ณ เวลา: {pd.Timestamp.now().strftime('%H:%M:%S')}")

results = []
cols = st.columns(4) # แบ่งเป็น 4 คอลัมน์สำหรับหน้าจอ

for i, coin in enumerate(blue_chips):
    res = analyze_coin_smart(coin, tf)
    if res:
        results.append(res)
        with cols[i % 4]:
            # กำหนดสีตามความแม่นยำ
            status_color = "green" if res['score'] >= 80 else "orange" if res['score'] >= 60 else "gray"
            
            st.markdown(f"""
            <div style="border: 1px solid #ddd; padding: 15px; border-radius: 10px; border-left: 5px solid {status_color};">
                <h4>{res['symbol']}</h4>
                <p style="font-size: 20px; font-weight: bold;">${res['price']:,.2f}</p>
                <p>Confidence: {res['score']}%</p>
                <p>AI Target: ${res['pred']:,.2f}</p>
            </div>
            """, unsafe_allow_value=True)

# ตารางเปรียบเทียบเชิงลึก
if results:
    st.divider()
    df_final = pd.DataFrame(results)
    st.write("### 📊 ตารางสรุปโอกาสการลงทุน")
    st.dataframe(df_final.sort_values(by="score", ascending=False), use_container_width=True)
