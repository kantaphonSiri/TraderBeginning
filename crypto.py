import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import requests
import numpy as np

# --- 1. ฟังก์ชันดึงข้อมูล Sentiment ---
def get_market_sentiment():
    try:
        url = "https://api.alternative.me/fng/"
        r = requests.get(url, timeout=10).json()
        return int(r['data'][0]['value'])
    except:
        return 50  # หากดึงไม่ได้ ให้ค่าเป็นกลางไว้ก่อน (Neutral)

# --- 2. ฟังก์ชันเตรียมข้อมูล (Data Pipeline) ---
def prepare_data(symbol="BTC-USD"):
    # ดึงข้อมูลจาก Yahoo Finance
    df = yf.download(symbol, period="60d", interval="1h")
    
    # แก้ไขปัญหา MultiIndex (สาเหตุของ AttributeError)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    if df.empty:
        return None

    # คำนวณ Technical Indicators ด้วย pandas_ta
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.macd(append=True)
    
    # เพิ่มค่า Sentiment
    df['sentiment'] = get_market_sentiment()
    
    return df.dropna()

# --- 3. ส่วนการแสดงผลบน Streamlit ---
st.set_page_config(page_title="Crypto AI Trader", layout="wide")
st.title("🤖 Crypto Prediction Pipeline")

try:
    ticker = st.sidebar.text_input("ใส่ชื่อเหรียญ (เช่น BTC-USD)", "BTC-USD")
    
    with st.spinner('กำลังดึงข้อมูลและคำนวณ AI...'):
        data = prepare_data(ticker)

    if data is not None and not data.empty:
        # แสดงผลข้อมูลล่าสุด
        col1, col2, col3 = st.columns(3)
        last_price = data['Close'].iloc[-1]
        last_rsi = data['RSI_14'].iloc[-1]
        sentiment = data['sentiment'].iloc[-1]

        col1.metric("ราคาปัจจุบัน", f"${last_price:,.2f}")
        col2.metric("RSI (14)", f"{last_rsi:.2f}")
        col3.metric("Market Sentiment", f"{sentiment}%")

        # แสดงกราฟราคา
        st.subheader(f"กราฟราคา {ticker}")
        st.line_chart(data['Close'])

        # แสดงตารางข้อมูลเบื้องหลัง
        with st.expander("ดูข้อมูลดิบ (Raw Data)"):
            st.write(data.tail(10))
            
    else:
        st.error("ไม่พบข้อมูลเหรียญที่ระบุ กรุณาตรวจสอบชื่อ Ticker อีกครั้ง")

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการรันแอป: {e}")
    st.info("คำแนะนำ: ลองกด Reboot App ที่เมนู Manage app มุมขวาล่าง")
