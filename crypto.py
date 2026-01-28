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

# 1. ระบบดึงรายชื่อเหรียญ
@st.cache_data(ttl=3600)
def get_top_symbols(limit):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']

# 2. อัตราแลกเปลี่ยน
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# ------------------------
# 3. SIDEBAR
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.info("พอร์ตว่างเปล่า")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}", expanded=False):
                st.write(f"ทุน: {m['cost']:,.2f}")
                # ใช้ key ที่ไม่ซ้ำ
                if st.button(f"นำออก", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    
    st.divider()
    st.subheader("⚙️ Settings")
    limit_choice = st.selectbox("สแกนกี่เหรียญ:", [30, 50, 100], index=0, key="limit_box")
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=0.0, key="budget_input")

# ------------------------
# 4. DATA FETCHING
# ------------------------
usd_thb = get_exchange_rate()
top_symbols = get_top_symbols(limit_choice)
scanned_results = {}

with st.spinner(f"🤖 กำลังโหลดข้อมูล {limit_choice} เหรียญ..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="7d", interval="15m", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.ffill()
                scanned_results[s] = {'price': float(df['Close'].iloc[-1]) * usd_thb, 'df': df}
        except: continue

# ------------------------
# 5. MAIN APP
# ------------------------
st.title("👛 Smart Trading Dashboard")

display_symbols = [s for s, d in scanned_results.items() if budget == 0 or d['price'] <= budget]
if budget == 0: display_symbols = display_symbols[:6]

cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    is_pinned = s in st.session_state.portfolio
    
    with cols[idx % 2]:
        with st.container(border=True):
            h_l, h_r = st.columns([4, 1])
            h_l.subheader(f"🪙 {s}")
            
            # ปุ่ม Pin
            pin_icon = "📍 Pinned" if is_pinned else "📌"
            if h_r.button(pin_icon, key=f"btn_pin_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': item['price'], 'target': 15, 'stop': 7}
                st.rerun()
            
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # --- กราฟ (ใส่ KEY เพื่อแก้ Error) ---
            fig = go.Figure(data=[go.Scatter(
                y=item['df']['Close'].tail(100).values, 
                mode='lines',
                line=dict(color='#00ffcc', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 204, 0.1)'
            )])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            
            # จุดสำคัญ: เพิ่ม key=f"chart_{s}" เพื่อป้องกัน ID ซ้ำ
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=f"chart_{s}")
            
            if is_pinned:
                st.divider()
                m = st.session_state.portfolio[s]
                entry_p = st.number_input(f"ทุน {s}:", value=float(m['cost']), key=f"in_cost_{s}")
                c1, c2 = st.columns(2)
                tgt = c1.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"sl_tgt_{s}")
                stp = c2.slider(f"จุดคัด (%)", 3, 50, int(m['stop']), key=f"sl_stp_{s}")
                
                st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                diff = ((item['price'] - entry_p) / entry_p) * 100
                if diff >= tgt: st.success(f"🚀 SELL: {diff:+.2f}%")
                elif diff <= -stp: st.error(f"🛑 STOP: {diff:+.2f}%")
                else: st.info(f"📊 Profit: {diff:+.2f}%")

time.sleep(REFRESH_SEC)
st.rerun()
