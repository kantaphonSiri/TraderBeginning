import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. CONFIG & SESSION STATE
# ------------------------
REFRESH_SEC = 60
st.set_page_config(page_title="Budget-Bets Alpha: Auto-Scanner", layout="wide")

# คลังเก็บข้อมูลเหรียญ
if 'scanned_data' not in st.session_state:
    st.session_state.scanned_data = {}
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'scan_target' not in st.session_state:
    st.session_state.scan_target = 30 # เริ่มที่ 30 เสมอ

# 1. ฟังก์ชันดึงรายชื่อเหรียญ (ดึงรอไว้ 100 อันดับแรก)
@st.cache_data(ttl=3600)
def get_master_symbols():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'DOT', 'MATIC', 'LTC']

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        rate = yf.Ticker("THB=X").fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# ------------------------
# 2. SIDEBAR
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.caption("ยังไม่มีเหรียญในพอร์ต")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}", expanded=False):
                st.write(f"ทุน: {m['cost']:,.2f} ฿")
                if st.button(f"นำออก", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=0.0)
    
    # แสดงความคืบหน้าการสแกนใน Sidebar เล็กๆ
    st.caption(f"ความคืบหน้าการสแกน: {len(st.session_state.scanned_data)} / 100")
    if len(st.session_state.scanned_data) < 100:
        st.progress(len(st.session_state.scanned_data) / 100)

# ------------------------
# 3. AUTO-SEQUENTIAL SCANNING ENGINE
# ------------------------
usd_thb = get_exchange_rate()
master_symbols = get_master_symbols()

# คัดเลือกเหรียญที่จะสแกนในรอบนี้ (30 -> 50 -> 100)
current_batch = master_symbols[:st.session_state.scan_target]
pending_symbols = [s for s in current_batch if s not in st.session_state.scanned_data]

if pending_symbols:
    with st.status(f"⏳ กำลังสแกนข้อมูลเหรียญเพิ่ม ({len(st.session_state.scanned_data)}/100)...") as status:
        for s in pending_symbols:
            try:
                df = yf.download(f"{s}-USD", period="7d", interval="15m", progress=False)
                if not df.empty:
                    df = df.ffill()
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    st.session_state.scanned_data[s] = {
                        'price': float(df['Close'].iloc[-1]) * usd_thb,
                        'df': df
                    }
            except: continue
        
        # เมื่อสแกนรอบนี้เสร็จ ขยับเป้าหมายไปขั้นถัดไป
        if st.session_state.scan_target == 30: st.session_state.scan_target = 50
        elif st.session_state.scan_target == 50: st.session_state.scan_target = 100
        
        status.update(label="✅ อัปเดตข้อมูลเสร็จสิ้น!", state="complete")
        time.sleep(0.5)
        st.rerun()

# ------------------------
# 4. MAIN DISPLAY
# ------------------------
st.title("👛 Smart Trading Panel")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | ข้อมูลในระบบ: {len(st.session_state.scanned_data)} เหรียญ")

# กรองตามงบ (ถ้าไม่กรองงบ โชว์แค่ 6 ตัวแรกเพื่อให้ลื่นไหล)
display_list = [s for s, d in st.session_state.scanned_data.items() if budget == 0 or d['price'] <= budget]
if budget == 0:
    display_list = display_list[:6]
    st.info("💡 แสดง 6 อันดับแรก (ระบุงบเพื่อกรองดูเหรียญอื่นๆ ในระบบ)")

cols = st.columns(2)
for idx, s in enumerate(display_list):
    item = st.session_state.scanned_data[s]
    is_pinned = s in st.session_state.portfolio
    
    with cols[idx % 2]:
        with st.container(border=True):
            h1, h2 = st.columns([4,1])
            h1.subheader(f"🪙 {s}")
            
            # ปุ่ม Icon Pin
            if h2.button("📍" if is_pinned else "📌", key=f"btn_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': item['price'], 'target': 15, 'stop': 7}
                st.rerun()
            
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # กราฟสมูท
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(100).values, mode='lines', line=dict(color='#00ffcc', width=2))])
            fig.update_layout(height=110, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{s}", config={'displayModeBar': False})

            if is_pinned:
                st.divider()
                m = st.session_state.portfolio[s]
                new_cost = st.number_input(f"ทุน {s}:", value=float(m['cost']), key=f"cost_{s}")
                c1, c2 = st.columns(2)
                new_tgt = c1.slider("เป้า %", 5, 100, int(m['target']), key=f"tg_{s}")
                new_stp = c2.slider("คัด %", 3, 50, int(m['stop']), key=f"st_{s}")
                st.session_state.portfolio[s] = {'cost': new_cost, 'target': new_tgt, 'stop': new_stp}
                
                diff = ((item['price'] - new_cost) / new_cost) * 100
                if diff >= new_tgt: st.success(f"🚀 SELL: {diff:+.2f}%")
                elif diff <= -new_stp: st.error(f"🛑 STOP: {diff:+.2f}%")
                else: st.info(f"📊 Profit: {diff:+.2f}%")

# Auto-Refresh ราคาทุก 1 นาที
time.sleep(REFRESH_SEC)
st.rerun()
