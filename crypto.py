import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. CONFIG & SETUP
# ------------------------
REFRESH_SEC = 60
st.set_page_config(page_title="👛 Budget-Bets Fix v3", layout="wide")

# 1. ดึงเรทเงินบาท (ดึงตรงจาก yfinance เพื่อความเสถียรบน Cloud)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        data = ticker.fast_info['last_price']
        return data if (data and data > 30) else 35.0
    except:
        return 35.0

# 2. คำนวณ RSI พร้อมระบบป้องกันค่า Error
def calculate_rsi(data, window=14):
    if len(data) < window + 1:
        return pd.Series([50.0] * len(data))
    
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    
    rs = gain / loss.replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

# 3. ดึงข้อมูล Crypto (ดึงผ่าน yfinance)
def get_coin_data(symbol):
    try:
        ticker_sym = f"{symbol}-USD"
        # ใช้ 1mo เพื่อให้มีข้อมูลพอคำนวณ RSI 14 วัน
        df = yf.download(ticker_sym, period="1mo", interval="1h", progress=False)
        if not df.empty:
            # ดึงราคาล่าสุดแบบ Scalar
            price_usd = df['Close'].iloc[-1]
            if isinstance(price_usd, pd.Series):
                price_usd = price_usd.iloc[-1]
            return float(price_usd), df
        return None, None
    except:
        return None, None

# ------------------------
# UI & SIDEBAR
# ------------------------
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อ 1 เหรียญ (บาท):", min_value=0, value=1000000, step=1000)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    
    st.divider()
    if st.button("🔄 ล้างความจำ & สแกนใหม่", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- ส่วนหัว ---
usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets (Final Cloud Version)")
st.write(f"💵 เรทปัจจุบัน: **{usd_thb:.2f} THB/USD** | อัปเดตล่าสุด: {datetime.now().strftime('%H:%M:%S')}")

# รายชื่อเหรียญ
symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX', 'LINK', 'NEAR', 'SUI', 'OP', 'ARB']

# --- การประมวลผล ---
display_items = []
with st.spinner("⏳ กำลังวิเคราะห์ข้อมูลตลาด..."):
    for s in symbols:
        price_usd, df = get_coin_data(s)
        if price_usd:
            price_thb = price_usd * usd_thb
            if budget == 0 or price_thb <= budget:
                rsi_series = calculate_rsi(df['Close'])
                # ดึงค่าสุดท้ายและจัดการให้เป็นค่าเดี่ยว (Scalar)
                last_rsi = rsi_series.iloc[-1]
                if isinstance(last_rsi, pd.Series):
                    last_rsi = last_rsi.iloc[-1]
                
                display_items.append({
                    'symbol': s,
                    'price_thb': price_thb,
                    'df': df,
                    'rsi': float(last_rsi)
                })

# --- การแสดงผล ---
if not display_items:
    st.warning("⚠️ ไม่พบข้อมูลเหรียญในขณะนี้")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคา (บาท)", f"{item['price_thb']:,.2f} ฿")
                
                # แสดง RSI พร้อมป้องกัน ValueError
                rsi_val = item['rsi']
                
                # เช็ค NaN อีกครั้งก่อนแสดงผล
                if pd.isna(rsi_val):
                    st.write("RSI (1h): N/A")
                else:
                    rsi_color = "green" if rsi_val <= 40 else "red" if rsi_val >= 70 else "white"
                    st.markdown(f"RSI (1h): <span style='color:{rsi_color}; font-size:22px; font-weight:bold;'>{rsi_val:.2f}</span>", unsafe_allow_html=True)
                
                # กราฟย่อ
                fig = go.Figure(data=[go.Scatter(
                    y=item['df']['Close'].tail(48), 
                    mode='lines', 
                    line=dict(color='#00ffcc', width=2)
                )])
                fig.update_layout(
                    height=120, margin=dict(l=0, r=0, t=0, b=0),
                    xaxis_visible=False, yaxis_visible=False,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                # ระบบคำนวณกำไร
                cost = st.number_input(f"ทุน {item['symbol']} (฿):", key=f"cost_{item['symbol']}", value=0.0)
                if cost > 0:
                    profit = ((item['price_thb'] - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร {profit:.2f}%")
                    elif profit <= -stop_loss:
                        st.error(f"🛑 ขาดทุน {profit:.2f}%")
                    else:
                        st.info(f"📊 พอร์ต {profit:.2f}%")

st.divider()
st.caption(f"Update: {REFRESH_SEC}s | Data: Yahoo Finance")

# --- Auto Refresh ---
time.sleep(REFRESH_SEC)
st.rerun()
