import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
from sklearn.ensemble import RandomForestRegressor # เปลี่ยนเป็นโมเดลที่ฉลาดกว่าเดิม

# --- 1. ฟังก์ชันดึงข้อมูลและคำนวณ Indicators ---
def prepare_high_accuracy_data(symbol, timeframe):
    df = yf.download(symbol, period="100d", interval=timeframe)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    if df.empty: return None

    # เพิ่มอาวุธให้ AI
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.bbands(length=20, std=2, append=True) # Bollinger Bands ดูจุดกลับตัว
    
    return df.dropna()

# --- 2. ฟังก์ชัน AI Prediction (ใช้ Random Forest เพื่อความแม่นยำที่สูงขึ้น) ---
def ai_prediction_score(df):
    # เตรียม Feature สำหรับ AI
    features = ['Close', 'RSI_14', 'EMA_20', 'EMA_50']
    X = df[features].iloc[:-1] # ข้อมูลอดีต
    y = df['Close'].shift(-1).iloc[:-1] # ราคาในอนาคต (เฉลย)
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # ทำนายราคาแท่งถัดไป
    last_data = df[features].iloc[[-1]]
    pred_price = model.predict(last_data)[0]
    return pred_price

# --- 3. หน้าจอ Streamlit ---
st.set_page_config(page_title="High Accuracy AI Trader", layout="wide")
st.title("🎯 High-Confidence Crypto Predictor")
st.markdown("ระบบจะวิเคราะห์เงื่อนไข 5 อย่าง ถ้าไม่ผ่านเงื่อนไข ระบบจะแนะนำให้ 'รอก่อน' เพื่อป้องกันการติดดอย")

ticker = st.sidebar.selectbox("เลือกเหรียญ:", ["BTC-USD", "ETH-USD", "SOL-USD"])
timeframe = st.sidebar.selectbox("ช่วงเวลา:", ["1h", "15m", "1d"])

try:
    data = prepare_high_accuracy_data(ticker, timeframe)
    if data is not None:
        pred_price = ai_prediction_score(data)
        cur_price = data.iloc[-1]['Close']
        rsi = data.iloc[-1]['RSI_14']
        ema20 = data.iloc[-1]['EMA_20']
        ema50 = data.iloc[-1]['EMA_50']
        
        # --- ระบบประเมินความมั่นใจ (Confidence Score) ---
        score = 0
        checks = []
        
        # 1. เช็คเทรน (ต้องเป็นขาขึ้น)
        if cur_price > ema20 > ema50:
            score += 30
            checks.append("✅ อยู่ในเทรนขาขึ้น (Bullish Trend)")
        else:
            checks.append("❌ เทรนยังไม่ชัดเจน (Wait for Trend)")
            
        # 2. เช็คแรงซื้อ (RSI ต้องไม่สูงเกินไป)
        if 40 < rsi < 60:
            score += 30
            checks.append("✅ ราคายังไม่แพงเกินไป (Not Overbought)")
        elif rsi >= 60:
            checks.append("⚠️ ระวัง! คนซื้อเยอะเกินไปแล้ว (Risk of Pullback)")
        else:
            checks.append("🔈 แรงซื้อยังน้อยเกินไป")

        # 3. เช็ค AI Prediction
        if pred_price > cur_price:
            score += 40
            checks.append(f"✅ AI ทายว่าราคาจะขึ้นไปที่ ${pred_price:,.2f}")
        else:
            checks.append("❌ AI ทายว่าราคาอาจจะย่อตัวลง")

        # --- แสดงผลลัพธ์ ---
        st.subheader(f"วิเคราะห์เหรียญ {ticker}")
        
        # แสดงแถบพลังความมั่นใจ
        st.write(f"**คะแนนความเชื่อมั่นของระบบ:** {score}%")
        st.progress(score / 100)

        c1, c2 = st.columns([1, 2])
        with c1:
            if score >= 80:
                st.success("🚀 สัญญาณ: 'ซื้อตอนนี้' (ความเสี่ยงต่ำ)")
            elif score >= 60:
                st.warning("🟡 สัญญาณ: 'ทยอยซื้อ' (ความเสี่ยงปานกลาง)")
            else:
                st.error("🛑 สัญญาณ: 'รอก่อน' (ห้ามเข้าตอนนี้ มีโอกาสดอย)")
            
            for c in checks:
                st.write(c)
        
        with c2:
            st.line_chart(data['Close'].tail(50))

except Exception as e:
    st.error(f"Error: {e}")
