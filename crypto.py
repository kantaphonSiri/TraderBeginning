import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ------------------------
# 0. CONFIG & PERSISTENT DB
# ------------------------
DB_FILE = "crypto_brain_100.pkl"
REFRESH_SEC = 60
st.set_page_config(page_title="AI Crypto Strategist", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}

# โหลด/บันทึก ข้อมูลลง Disk
def save_data(data):
    with open(DB_FILE, 'wb') as f:
        pickle.dump(data, f)

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            return pickle.load(f)
    return {}

if 'master_data' not in st.session_state:
    st.session_state.master_data = load_data()

# ------------------------
# 1. AI ANALYTICS ENGINE
# ------------------------
def get_ai_advice(df):
    if len(df) < 30: return "รอข้อมูล...", "gray"
    
    close = df['Close'].astype(float)
    current_p = close.iloc[-1]
    avg_30d = close.mean() # ราคาเฉลี่ย 30 วัน (Base Price สำหรับเทียบโต)
    
    # คำนวณ RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]

    # วิเคราะห์
    if current_p > avg_30d * 1.05 and rsi < 65:
        return "🔥 ขาขึ้นแข็งแกร่ง (น่าตาม)", "#00ffcc"
    elif rsi < 35:
        return "💎 ของดีราคาถูก (น่าช้อน)", "#ffcc00"
    elif rsi > 75:
        return "⚠️ ระวัง! แพงเกินไป", "#ff4b4b"
    else:
        return "⏳ รอจังหวะ (Neutral)", "#808495"

# ------------------------
# 2. AUTO-SCANNER (100 COINS)
# ------------------------
@st.cache_data(ttl=3600)
def get_top_100_symbols():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        return [c['symbol'].upper() for c in requests.get(url).json()]
    except: return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

def sync_market_data():
    symbols = get_top_100_symbols()
    usd_thb = yf.Ticker("THB=X").fast_info['last_price']
    
    new_data = st.session_state.master_data.copy()
    
    with st.status("🤖 AI กำลังสแกนตลาด 100 เหรียญและวิเคราะห์ย้อนหลัง 30 วัน...") as status:
        for s in symbols:
            # สแกนเฉพาะตัวที่ยังไม่มีข้อมูล หรือข้อมูลเก่าเกิน 1 ชม.
            if s not in new_data or (time.time() - new_data[s].get('ts', 0) > 3600):
                try:
                    # ดึงข้อมูล 1 เดือน (1mo) เพื่อความแม่นยำในการเทียบการเติบโต
                    df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
                    if not df.empty:
                        df = df.ffill()
                        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                        
                        price_now = float(df['Close'].iloc[-1]) * usd_thb
                        # เก็บราคาเฉลี่ยเดือนนี้ไว้เป็น Base
                        avg_p = float(df['Close'].mean()) * usd_thb
                        
                        new_data[s] = {
                            'price': price_now,
                            'base_price': avg_p,
                            'df': df,
                            'ts': time.time()
                        }
                except: continue
        
        st.session_state.master_data = new_data
        save_data(new_data)
        status.update(label="✅ ซิงค์ฐานข้อมูลและวิเคราะห์เสร็จสิ้น!", state="complete")

# ------------------------
# 3. MAIN UI
# ------------------------
st.title("🛡️ AI Crypto Strategist Pro")
st.caption("ระบบวิเคราะห์อัตโนมัติอ้างอิงฐานข้อมูลเฉลี่ย 30 วัน เพื่อการเติบโตที่ยั่งยืน")

if not st.session_state.master_data:
    sync_market_data()
    st.rerun()

# Sidebar: กรองข้อมูล
with st.sidebar:
    st.title("💼 Portfolio")
    # ... (ส่วนจัดการ Portfolio เหมือนเดิม) ...
    st.divider()
    budget = st.number_input("งบประมาณ (บาท):", min_value=0.0, value=0.0)

# แสดงผลการ์ดเหรียญ
display_list = [s for s, d in st.session_state.master_data.items() if budget == 0 or d['price'] <= budget]
cols = st.columns(2)

for idx, s in enumerate(display_list[:6] if budget == 0 else display_list):
    data = st.session_state.master_data[s]
    advice, color = get_ai_advice(data['df'])
    
    with cols[idx % 2]:
        with st.container(border=True):
            # ส่วนหัวและการวิเคราะห์ AI
            h1, h2 = st.columns([3, 2])
            h1.subheader(f"🪙 {s}")
            h2.markdown(f"<div style='background:{color}; color:black; padding:4px; border-radius:5px; text-align:center; font-weight:bold; font-size:12px;'>{advice}</div>", unsafe_allow_html=True)
            
            # การเติบโตเทียบกับราคาเฉลี่ย 30 วัน (Base Price)
            growth = ((data['price'] - data['base_price']) / data['base_price']) * 100
            st.metric("ราคาปัจจุบัน", f"{data['price']:,.2f} ฿", f"{growth:+.2f}% เทียบเฉลี่ย 30 วัน")
            
            # กราฟ
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(100).values, line=dict(color=color))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{s}", config={'displayModeBar': False})
            
            # ปุ่ม Pin
            if st.button(f"📌 วางแผนเทรด {s}", key=f"pin_{s}"):
                st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15, 'stop': 7}
                st.rerun()

# ปุ่มบังคับอัปเดตข้อมูล
if st.button("🔄 อัปเดตข้อมูล 100 เหรียญเดี๋ยวนี้"):
    sync_market_data()
    st.rerun()

time.sleep(REFRESH_SEC)
st.rerun()
