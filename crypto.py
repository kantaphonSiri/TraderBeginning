import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# --- SETUP ---
st.set_page_config(page_title="Budget-Bets Fix", layout="wide")

# 1. ดึงเรทเงินบาท (ใช้ yfinance ดึงตรงจากตลาดโลก ไม่ต้องใช้ API Key)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        # ดึงราคา USDTHB=X (เรททางการ)
        ticker = yf.Ticker("THB=X")
        data = ticker.fast_info['last_price']
        return data if data > 30 else 35.0 # ป้องกันค่าเพี้ยน
    except:
        return 35.0

# 2. คำนวณ RSI
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

# 3. ดึงข้อมูล Crypto (ดึงทีละตัวผ่าน yfinance เพื่อความเสถียรบน Cloud)
def get_coin_data(symbol):
    try:
        ticker = f"{symbol}-USD"
        df = yf.download(ticker, period="5d", interval="1h", progress=False)
        if not df.empty:
            price = float(df['Close'].iloc[-1])
            return price, df
        return None, None
    except:
        return None, None

# --- UI SIDEBAR ---
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=1000000) # ตั้งค่าเผื่อไว้ก่อน
    if st.button("🔄 สแกนใหม่"):
        st.cache_data.clear()
        st.rerun()

# --- MAIN ---
usd_thb = get_exchange_rate()
st.header(f"💰 เรทบาทวันนี้: {usd_thb:.2f} THB/USD")

# รายชื่อเหรียญ (ลองเริ่มจาก 5 ตัวหลัก)
symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
display_items = []

with st.spinner("⏳ กำลังดึงข้อมูลจาก Yahoo Finance..."):
    for s in symbols:
        price_usd, df = get_coin_data(s)
        if price_usd:
            price_thb = price_usd * usd_thb
            if price_thb <= budget:
                rsi_s = calculate_rsi(df['Close'])
                display_items.append({'sym': s, 'p': price_thb, 'df': df, 'rsi': rsi_s.iloc[-1]})

# --- DISPLAY ---
if not display_items:
    st.error("❌ ไม่พบข้อมูลเหรียญ! กรุณากดปุ่ม 'สแกนใหม่' ที่แถบด้านข้าง")
else:
    cols = st.columns(len(display_items))
    for i, item in enumerate(display_items):
        with cols[i]:
            with st.container(border=True):
                st.subheader(item['sym'])
                st.metric("ราคา (฿)", f"{item['p']:,.0f}")
                st.write(f"RSI: {item['rsi']:.2f}")
                
                # กราฟย่อ
                fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(24), mode='lines')])
                fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False)
                st.plotly_chart(fig, use_container_width=True)

# Auto Refresh
time.sleep(60)
st.rerun()
