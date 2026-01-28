import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. CONFIG & PERSISTENT DB
# ------------------------
DB_FILE = "crypto_eternal_v3.pkl"
REFRESH_SEC = 60
st.set_page_config(page_title="AI Crypto Strategist Pro", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}

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
# 1. AI ANALYTICS & LOGIC
# ------------------------
def get_ai_advice(df):
    if len(df) < 20: return "รอข้อมูล...", "gray"
    close = df['Close'].astype(float)
    current_p = close.iloc[-1]
    avg_30d = close.mean()
    
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]

    if current_p > avg_30d * 1.05 and rsi < 65: return "🔥 ขาขึ้นแข็งแกร่ง", "#00ffcc"
    elif rsi < 35: return "💎 ของถูกน่าช้อน", "#ffcc00"
    elif rsi > 75: return "⚠️ ระวัง! แพงไป", "#ff4b4b"
    else: return "⏳ รอจังหวะ", "#808495"

@st.cache_data(ttl=3600)
def get_top_100_symbols():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        return [c['symbol'].upper() for c in requests.get(url).json()]
    except: return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

# ------------------------
# 2. UI SIDEBAR
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.info("ยังไม่มีเหรียญที่ปักหมุด")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}", expanded=True):
                st.write(f"ทุน: {m['cost']:,.2f}")
                if st.button(f"นำออก", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=0.0)

# ------------------------
# 3. DATA SYNC
# ------------------------
usd_thb = yf.Ticker("THB=X").fast_info['last_price']
master_symbols = get_top_100_symbols()

# กรองเหรียญที่จะแสดง (ถ้าไม่มีงบ โชว์แค่ 6 ตัวแรก แต่ต้องสแกนเก็บไว้)
if not st.session_state.master_data or len(st.session_state.master_data) < 10:
    new_data = st.session_state.master_data.copy()
    with st.status("🤖 กำลังสแกนและแยกกลุ่มเหรียญ Blue Chip...") as status:
        for idx, s in enumerate(master_symbols):
            if s not in new_data:
                try:
                    df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
                    if not df.empty:
                        df = df.ffill()
                        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                        new_data[s] = {
                            'price': float(df['Close'].iloc[-1]) * usd_thb,
                            'base_price': float(df['Close'].mean()) * usd_thb,
                            'df': df,
                            'rank': idx + 1 # เก็บลำดับไว้เช็ค Blue Chip
                        }
                except: continue
        st.session_state.master_data = new_data
        save_data(new_data)
        status.update(label="✅ ซิงค์ข้อมูลสำเร็จ!", state="complete")

# ------------------------
# 4. MAIN DISPLAY
# ------------------------
st.title("🛡️ Crypto Eternal Strategist")
st.write(f"💵 อัตราแลกเปลี่ยน: {usd_thb:.2f} THB/USD")

display_list = [s for s, d in st.session_state.master_data.items() if budget == 0 or d['price'] <= budget]
if budget == 0: display_list = display_list[:6]

cols = st.columns(2)
for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    advice, color = get_ai_advice(data['df'])
    
    # เช็คว่าเป็น Blue Chip (Top 30) หรือไม่
    icon = "🔵" if data.get('rank', 100) <= 30 else "🪙"
    
    with cols[idx % 2]:
        with st.container(border=True):
            # ส่วนหัว: ชื่อเหรียญ + ปุ่ม Pin (📌/📍)
            h1, h2 = st.columns([4, 1])
            h1.subheader(f"{icon} {s}")
            
            # ปุ่ม Pin มุมขวา
            btn_label = "📍" if is_pinned else "📌"
            if h2.button(btn_label, key=f"pin_btn_{s}"):
                if is_pinned:
                    del st.session_state.portfolio[s]
                else:
                    st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15, 'stop': 7}
                st.rerun()
            
            # AI Advice Label
            st.markdown(f"<div style='background:{color}; color:black; padding:2px 8px; border-radius:5px; font-size:12px; font-weight:bold; display:inline-block;'>{advice}</div>", unsafe_allow_html=True)
            
            # Metric ราคา
            growth = ((data['price'] - data['base_price']) / data['base_price']) * 100
            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿", f"{growth:+.2f}% เทียบเฉลี่ย 30 วัน")
            
            # กราฟ
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(100).values, mode='lines', line=dict(color=color, width=2))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{s}", config={'displayModeBar': False})

            # --- ส่วนตั้งค่าราคาทุน (จะโผล่เมื่อ Pin เท่านั้น) ---
            if is_pinned:
                st.divider()
                m = st.session_state.portfolio[s]
                
                # ช่องกรอกราคาทุน
                new_cost = st.number_input(f"ระบุราคาทุนของ {s}:", value=float(m['cost']), key=f"input_cost_{s}")
                
                # Slider เป้าหมาย
                c1, c2 = st.columns(2)
                new_tgt = c1.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"input_tgt_{s}")
                new_stp = c2.slider(f"จุดคัด (%)", 3, 50, int(m['stop']), key=f"input_stp_{s}")
                
                # อัปเดตข้อมูลลง Portfolio
                st.session_state.portfolio[s] = {'cost': new_cost, 'target': new_tgt, 'stop': new_stp}
                
                # คำนวณกำไรปัจจุบันจากทุนที่กรอก
                profit_pct = ((data['price'] - new_cost) / new_cost) * 100
                if profit_pct >= new_tgt: st.success(f"🚀 พร้อมขาย! กำไร: {profit_pct:+.2f}%")
                elif profit_pct <= -new_stp: st.error(f"🛑 ต้องคัด! ขาดทุน: {profit_pct:+.2f}%")
                else: st.info(f"📊 กำไรปัจจุบันจากทุน: {profit_pct:+.2f}%")
            else:
                st.caption("💡 กดปุ่ม 📌 เพื่อวางแผนราคาทุนและเป้าหมาย")

# Auto-Refresh
time.sleep(REFRESH_SEC)
st.rerun()
