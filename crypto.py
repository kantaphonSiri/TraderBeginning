import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
from sklearn.ensemble import RandomForestRegressor

# --- 1. ฟังก์ชันดึงข้อมูลและวิเคราะห์ความแม่นยำสูง ---
def analyze_coin(symbol, timeframe="1h"):
    try:
        # ดึงข้อมูลย้อนหลัง (ใช้ period มากขึ้นเพื่อให้ EMA นิ่ง)
        df = yf.download(symbol, period="100d", interval=timeframe, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 50: return None

        # คำนวณเทคนิคอล
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()

        # AI Prediction (Random Forest)
        features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
        X = df[features].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        
        # ทำนายราคา
        last_data = df[features].iloc[[-1]]
        pred_price = model.predict(last_data)[0]

        # ข้อมูลปัจจุบัน
        cur_price = df.iloc[-1]['Close']
        rsi = df.iloc[-1]['RSI_14']
        ema20 = df.iloc[-1]['EMA_20']
        ema50 = df.iloc[-1]['EMA_50']

        # คำนวณ Confidence Score (0-100)
        score = 0
        if cur_price > ema20 > ema50: score += 40  # เทรนขาขึ้นชัดเจน
        if 40 < rsi < 65: score += 30             # ราคาไม่แพงเกินไป (ไม่ดอย)
        if pred_price > cur_price: score += 30     # AI คาดการณ์ว่ากำไร

        return {
            "symbol": symbol,
            "price": cur_price,
            "pred": pred_price,
            "score": score,
            "status": "🚀 น่าซื้อที่สุด" if score >= 80 else "🟡 รอดูจังหวะ" if score >= 60 else "🛑 ข้ามไปก่อน"
        }
    except Exception as e:
        return None

# --- 2. หน้าจอ Streamlit ---
st.set_page_config(page_title="Blue-chip AI Advisor", layout="wide")
st.title("💎 AI Blue-chip Portfolio Advisor")

# รับงบประมาณจากผู้ใช้
with st.sidebar:
    st.header("💰 Investment Setup")
    budget = st.number_input("ใส่เงินงบประมาณของคุณ (USD):", min_value=10.0, value=1000.0, step=50.0)
    timeframe = st.selectbox("เลือกช่วงเวลา (Timeframe):", ["1h", "1d", "15m"])
    st.info("ระบบสแกนเฉพาะ Blue-chip (BTC, ETH, SOL, BNB, XRP, ADA)")

# รายชื่อเหรียญเป้าหมาย
blue_chips = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD"]

if st.button("🔍 เริ่มสแกนหาโอกาสลงทุนที่แม่นยำที่สุด"):
    with st.spinner('AI กำลังวิเคราะห์ตลาด...'):
        results = []
        for coin in blue_chips:
            res = analyze_coin(coin, timeframe)
            if res:
                results.append(res)
        
        if results:
            df_res = pd.DataFrame(results)
            
            st.subheader(f"✅ ผลการวิเคราะห์สำหรับงบ ${budget:,.2f}")
            
            # กรองตัวที่แนะนำ
            recommend = df_res[df_res['score'] >= 80].sort_values(by="score", ascending=False)
            
            if not recommend.empty:
                cols = st.columns(len(recommend))
                for i, row in enumerate(recommend.itertuples()):
                    with cols[i]:
                        st.success(f"**{row.symbol}**")
                        st.metric("ราคาปัจจุบัน", f"${row.price:,.2f}")
                        st.write(f"💰 **ซื้อได้:** {(budget/row.price):.4f} units")
                        st.write(f"🎯 **เป้าหมาย:** ${row.pred:,.2f}")
                        st.write(f"📈 **ความมั่นใจ:** {row.score}%")
            else:
                st.warning("⚠️ ยังไม่มีเหรียญใดเข้าเงื่อนไขที่ปลอดภัยที่สุดในขณะนี้ แนะนำให้ถือเงินสด (Wait for Signal)")

            st.divider()
            st.subheader("📊 ตารางเปรียบเทียบภาพรวม")
            st.dataframe(df_res, use_container_width=True)

# --- ส่วนคำอธิบายวิธีอ่านผล (วางไว้นอก Code Block ของ Logic) ---
st.markdown("""
---
### 💡 วิธีใช้งานให้ได้กำไร (ไม่ติดดอย)
* **🚀 น่าซื้อที่สุด:** ผ่านเกณฑ์ครบ (เทรนขาขึ้น + RSI ไม่สูง + AI เชียร์) **จุดนี้ความแม่นยำสูงสุด**
* **🟡 รอดูจังหวะ:** กราฟยังก้ำกึ่ง หรือราคาเพิ่งเริ่มขยับ
* **🛑 ข้ามไปก่อน:** เสี่ยงติดดอยสูง เพราะราคาสูงเกินไป (RSI Overbought) หรือเป็นเทรนขาลง
""")
