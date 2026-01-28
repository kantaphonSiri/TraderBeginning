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
st.set_page_config(page_title="Budget-Bets Pro Dashboard", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {} 

# 1. ฟังก์ชันดึงรายชื่อเหรียญตามจำนวนที่ระบุ
@st.cache_data(ttl=3600)
def get_top_symbols(limit):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'DOT']

# 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# ------------------------
# 3. SIDEBAR (Settings & Portfolio)
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.info("ยังไม่มีเหรียญที่ปักหมุด")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            # หมายเหตุ: ข้อมูลราคาตลาดจะถูกเรียกใช้จาก scanned_results ในส่วนถัดไป
            with st.expander(f"📌 {sym}", expanded=False):
                st.write(f"ทุน: {m['cost']:,.2f}")
                if st.button(f"นำออก", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    
    st.divider()
    st.subheader("⚙️ Settings")
    
    # --- กลับมาแล้ว! ตัวเลือกจำนวนเหรียญ ---
    limit_choice = st.selectbox("จำนวนเหรียญที่จะสแกน:", [30, 50, 100], index=0)
    
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=0.0, help="ถ้าใส่ 0 จะแสดงทุกเหรียญ")

# ------------------------
# 4. DATA PROCESSING
# ------------------------
usd_thb = get_exchange_rate()
top_symbols = get_top_symbols(limit_choice) # ดึงตามค่าที่เลือกใน Sidebar
scanned_results = {}

with st.spinner(f"🤖 กำลังสแกน {limit_choice} เหรียญจาก API..."):
    for s in top_symbols:
        try:
            # ดึง 7 วัน/15 นาที เพื่อให้กราฟสมูท
            df = yf.download(f"{s}-USD", period="7d", interval="15m", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                df = df.ffill() # เติมค่าว่างป้องกันกราฟเป็นจุด
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                scanned_results[s] = {'price': price_thb, 'df': df}
        except: continue

# ------------------------
# 5. MAIN DASHBOARD
# ------------------------
st.title("👛 Smart Trading Dashboard")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | จำนวนที่สแกน: {len(scanned_results)} เหรียญ")

# กรองตามงบ
display_symbols = [s for s, d in scanned_results.items() if budget == 0 or d['price'] <= budget]

# ถ้าไม่ระบุงบ ให้โชว์แค่ 6 ตัวแรกเพื่อไม่ให้หน้าโหลดนานเกินไป
if budget == 0:
    display_symbols = display_symbols[:6]
    st.info(f"💡 แสดง 6 อันดับแรกจาก {limit_choice} เหรียญ (กรอกงบประมาณเพื่อกรองดูทั้งหมด)")

cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    is_pinned = s in st.session_state.portfolio
    
    with cols[idx % 2]:
        with st.container(border=True):
            h_l, h_r = st.columns([4, 1])
            h_l.subheader(f"🪙 {s}")
            
            # Icon Pin Button
            pin_icon = "📍 Pinned" if is_pinned else "📌"
            if h_r.button(pin_icon, key=f"btn_{s}"):
                if is_pinned:
                    del st.session_state.portfolio[s]
                else:
                    st.session_state.portfolio[s] = {'cost': item['price'], 'target': 15, 'stop': 7}
                st.rerun()
            
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # กราฟสมูท (Mode: lines)
            fig = go.Figure(data=[go.Scatter(
                y=item['df']['Close'].tail(100).values, 
                mode='lines',
                line=dict(color='#00ffcc', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 204, 0.1)'
            )])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            if is_pinned:
                st.divider()
                m = st.session_state.portfolio[s]
                entry_p = st.number_input(f"ต้นทุน {s}:", value=float(m['cost']), key=f"cost_{s}")
                c1, c2 = st.columns(2)
                tgt = c1.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"tgt_{s}")
                stp = c2.slider(f"จุดคัด (%)", 3, 50, int(m['stop']), key=f"stp_{s}")
                
                st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                
                diff = ((item['price'] - entry_p) / entry_p) * 100
                if diff >= tgt: st.success(f"🚀 SELL: {diff:+.2f}%")
                elif diff <= -stp: st.error(f"🛑 STOP: {diff:+.2f}%")
                else: st.info(f"📊 Profit: {diff:+.2f}%")
            else:
                st.caption("📌")

time.sleep(REFRESH_SEC)
st.rerun()
