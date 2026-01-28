import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. CONFIG
# ------------------------
REFRESH_SEC = 60
st.set_page_config(page_title="👛 Budget-Bets Fix", layout="wide")

# 1. ดึงเรทเงินบาท (ใช้ requests ดึงจาก API ภายนอก)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        res = requests.get(url, timeout=5).json()
        return res['rates']['THB']
    except:
        return 35.0

# 2. คำนวณ RSI
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

# 3. ดึงข้อมูล Crypto แบบกลุ่ม (เร็วกว่าดึงทีละตัว)
@st.cache_data(ttl=60)
def get_all_crypto_data(symbols):
    try:
        tickers = [f"{s}-USD" for s in symbols]
        # ดึงข้อมูลรวดเดียว
        data = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
        return data
    except:
        return None

# ------------------------
# UI & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=100000, step=1000)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    
    if st.button("🔄 ล้าง Cache & สแกนใหม่", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets (Cloud Optimized)")
st.write(f"💵 เรทปัจจุบัน: **{usd_thb:.2f} THB/USD** | {datetime.now().strftime('%H:%M:%S')}")

# รายชื่อเหรียญ (ลองใส่เหรียญที่ชัวร์ๆ ก่อน)
symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX', 'LINK', 'NEAR']

# --- PROCESSING ---
raw_data = get_all_crypto_data(symbols)

display_items = []
if raw_data is not None:
    for s in symbols:
        try:
            # ดึงข้อมูลของแต่ละเหรียญจากข้อมูลก้อนใหญ่
            s_data = raw_data[f"{s}-USD"] if len(symbols) > 1 else raw_data
            if s_data.empty: continue
            
            last_price_usd = float(s_data['Close'].iloc[-1])
            price_thb = last_price_usd * usd_thb
            
            # ตรวจสอบเงื่อนไขงบประมาณ
            if budget == 0 or price_thb <= budget:
                rsi_series = calculate_rsi(s_data['Close'])
                display_items.append({
                    'symbol': s,
                    'price_thb': price_thb,
                    'df': s_data,
                    'rsi': rsi_series.iloc[-1]
                })
        except:
            continue

# --- DISPLAY ---
if not display_items:
    st.error("❌ ไม่สามารถดึงข้อมูลได้ หรือไม่มีเหรียญที่ตรงเงื่อนไข")
    st.info("ลองตรวจสอบว่าคุณใส่ 'yfinance' ในไฟล์ requirements.txt หรือยัง?")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคา (บาท)", f"{item['price_thb']:,.2f}")
                
                rsi_val = item['rsi']
                rsi_color = "green" if rsi_val <= 40 else "red" if rsi_val >= 70 else "white"
                st.markdown(f"RSI (1h): <span style='color:{rsi_color}; font-size: 20px;'>{rsi_val:.2f}</span>", unsafe_allow_html=True)
                
                # กราฟ Plotly แบบง่าย
                fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(24), mode='lines', line=dict(color='#00ffcc'))])
                fig.update_layout(height=100, margin=dict(l=0, r=0, t=0, b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                # ทุน
                cost = st.number_input(f"ทุน {item['symbol']} (฿):", key=f"c_{item['symbol']}", value=0.0)
                if cost > 0:
                    diff = ((item['price_thb'] - cost) / cost) * 100
                    if diff >= target_pct: st.success(f"กำไร {diff:.2f}%")
                    elif diff <= -stop_loss: st.error(f"ขาดทุน {diff:.2f}%")
                    else: st.info(f"พอร์ต {diff:.2f}%")

st.divider()
st.caption("Auto-refreshing in 60s...")
time.sleep(REFRESH_SEC)
st.rerun()
