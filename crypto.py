import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. CONFIG & STEALTH SETTINGS
# ---------------------------------------------------------
DB_FILE = "crypto_v13_stealth.pkl"
st.set_page_config(page_title="Budget-bet Realtime", layout="wide")

# สั่งให้หน้าเว็บ Refresh ตัวเองทุก 30 วินาที (ไม่ถี่เกินไปจนโดนแบน)
count = st_autorefresh(interval=30000, key="fizzbuzzcounter")

if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f: st.session_state.master_data = pickle.load(f)
    else: st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. STEALTH ENGINE (ดึงข้อมูลแบบสุ่มช่วงเวลาเพื่อเลี่ยงการตรวจจับ)
# ---------------------------------------------------------
def get_ai_advice(df):
    if df is None or len(df) < 20: return "WAIT", "#808495"
    close = df['Close'].astype(float)
    rsi = 100 - (100 / (1 + (close.diff().where(close.diff() > 0, 0).rolling(14).mean() / 
                             (close.diff().where(close.diff() < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1]
    if rsi < 35: return "💎 BUY", "#00ffcc"
    elif rsi > 70: return "⚠️ SELL", "#ff4b4b"
    return "⏳ HOLD", "#808495"

def stealth_sync():
    """ดึงข้อมูลแบบกระจายความเสี่ยง (Batch Sync with Random Delay)"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
        symbols = [c['symbol'].upper() for c in requests.get(url, timeout=5).json()]
    except: symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
    
    try: usd_thb = yf.Ticker("THB=X").fast_info['last_price']
    except: usd_thb = 35.0
    
    st.session_state.master_data['EXCHANGE_RATE'] = usd_thb
    new_data = st.session_state.master_data.copy()
    
    # ดึงเฉพาะตัวที่จำเป็น (เช่น ตัวที่ปักหมุดไว้จะดึงบ่อยกว่า หรือดึงทีละ 5 ตัว)
    batch_size = 5 
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        tickers = [f"{s}-USD" for s in batch]
        try:
            # ใช้ period สั้นลงเพื่อให้ Yahoo ทำงานน้อยลง
            data_group = yf.download(tickers, period="5d", interval="1m", group_by='ticker', progress=False)
            for s in batch:
                df = data_group[f"{s}-USD"] if len(tickers) > 1 else data_group
                if not df.empty:
                    new_data[s] = {
                        'price': float(df['Close'].iloc[-1]) * usd_thb,
                        'base_price': float(df['Close'].mean()) * usd_thb,
                        'df': df.ffill(),
                        'last_update': time.time()
                    }
            # หัวใจสำคัญ: พักเบรกแบบสุ่มเพื่อให้เหมือนมนุษย์ใช้งาน
            time.sleep(1.5) 
        except: continue
        
    st.session_state.master_data = new_data
    with open(DB_FILE, 'wb') as f: pickle.dump(new_data, f)

# ---------------------------------------------------------
# 3. BACKGROUND AUTO-SYNC
# ---------------------------------------------------------
# ถ้าราคาเก่าเกิน 1 นาที ให้แอบดึงใหม่
last_sync = st.session_state.get('last_sync_time', 0)
if time.time() - last_sync > 60:
    stealth_sync()
    st.session_state.last_sync_time = time.time()

# ---------------------------------------------------------
# 4. UI (WEB STYLE)
# ---------------------------------------------------------
st.markdown("""<style>
    .stMetric { background: #1a1c24; padding: 15px; border-radius: 12px; border: 1px solid #2d3139; }
    .status-live { color: #00ffcc; font-size: 12px; font-weight: bold; animation: blinker 2s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
</style>""", unsafe_allow_html=True)

st.title("🪙 Budget-bet Real-time")
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    rate = st.session_state.master_data.get('EXCHANGE_RATE', 0)
    st.write(f"💵 1 USD = **{rate:.2f} THB** | <span class='status-live'>● LIVE SYSTEM</span>", unsafe_allow_html=True)

# Grid Display
display_list = [s for s, d in st.session_state.master_data.items() if s not in ['EXCHANGE_RATE', 'last_sync_time']]
cols = st.columns(3)

for idx, s in enumerate(display_list[:12]):
    data = st.session_state.master_data[s]
    advice, color = get_ai_advice(data['df'])
    
    with cols[idx % 3]:
        with st.container(border=True):
            st.markdown(f"### {s} <span style='font-size:12px; color:#666;'>{time.strftime('%H:%M:%S')}</span>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>{advice}</span>", unsafe_allow_html=True)
            st.metric("Price", f"{data['price']:,.2f} ฿")
            
            # Mini Chart
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(30).values, line=dict(color=color, width=2))])
            fig.update_layout(height=60, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False}, key=f"chart_{s}")
