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

# 1. ระบบดึงข้อมูลพื้นฐาน
@st.cache_data(ttl=3600)
def get_top_symbols(limit=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# ------------------------
# 2. DATA PROCESSING
# ------------------------
usd_thb = get_exchange_rate()
top_symbols = get_top_symbols(30)
scanned_results = {}

with st.spinner("🤖 อัปเดตราคาล่าสุด..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty:
                scanned_results[s] = {'price': float(df['Close'].iloc[-1]) * usd_thb, 'df': df}
        except: continue

# ------------------------
# 3. UI SIDEBAR
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.info("พอร์ตว่างเปล่า")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            if sym in scanned_results:
                current_p = scanned_results[sym]['price']
                diff = ((current_p - m['cost']) / m['cost']) * 100
                with st.expander(f"📌 {sym}: {diff:+.2f}%", expanded=True):
                    st.write(f"ทุน: {m['cost']:,.2f} | ตลาด: {current_p:,.2f}")
                    # เมื่อลบจากที่นี่ สั่ง rerun เพื่อล้าง Toggle หน้าหลักด้วย
                    if st.button(f"นำออก", key=f"side_del_{sym}"):
                        del st.session_state.portfolio[sym]
                        st.rerun()
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=0.0)

# ------------------------
# 4. MAIN APP DISPLAY
# ------------------------
st.title("👛 Smart Trading Dashboard")

display_symbols = [s for s, d in scanned_results.items() if budget == 0 or d['price'] <= budget]
if not budget: display_symbols = display_symbols[:6]

cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    with cols[idx % 2]:
        with st.container(border=True):
            # --- แก้ Bug Toggle ค้าง ---
            head_l, head_r = st.columns([3, 1])
            head_l.subheader(f"🪙 {s}")
            
            # เช็คสถานะจริงจาก Portfolio ทุกครั้งที่วาด UI
            is_in_port = s in st.session_state.portfolio
            
            # ใช้ Toggle โดยผูกสถานะกับพอร์ต
            add_to_port = head_r.toggle("📌 Save", value=is_in_port, key=f"tg_save_{s}")
            
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # Chart (วาดเส้นต่อเนื่อง)
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48).values, line=dict(color='#00ffcc'))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # ดึงข้อมูลเดิมมาโชว์ (ถ้ามี)
            m = st.session_state.portfolio.get(s, {'cost': item['price'], 'target': 15, 'stop': 7})
            
            # ส่วน Slide กรอกข้อมูลจะโผล่ตาม Toggle
            if add_to_port:
                st.divider()
                entry_p = st.number_input(f"ทุน {s}:", value=float(m['cost']), key=f"in_cost_{s}")
                ca, cb = st.columns(2)
                tgt = ca.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"sl_tgt_{s}")
                stp = cb.slider(f"จุดคัด (%)", 3, 50, int(m['stop']), key=f"sl_stp_{s}")
                
                # บันทึก/อัปเดตข้อมูลเมื่อมีการเปลี่ยนแปลง
                new_entry = {'cost': entry_p, 'target': tgt, 'stop': stp}
                if st.session_state.portfolio.get(s) != new_entry:
                    st.session_state.portfolio[s] = new_entry
                    # ไม่ใช้ st.rerun() ตรงนี้เพื่อป้องกันการขัดจังหวะขณะพิมพ์เลข
            
            # กรณี User ปิด Toggle หน้าหลักเอง
            elif not add_to_port and is_in_port:
                del st.session_state.portfolio[s]
                st.rerun()

            # แสดงกำไร/ขาดทุน Real-time
            if is_in_port:
                diff = ((item['price'] - m['cost']) / m['cost']) * 100
                if diff >= m['target']: st.success(f"🚀 SELL: {diff:+.2f}%")
                elif diff <= -m['stop']: st.error(f"🛑 STOP: {diff:+.2f}%")
                else: st.info(f"📊 Profit: {diff:+.2f}%")

time.sleep(REFRESH_SEC)
st.rerun()
