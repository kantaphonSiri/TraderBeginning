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
st.set_page_config(page_title="Budget-Bets Smooth UI", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {} 

@st.cache_data(ttl=3600)
def get_top_symbols(limit=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except: return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        rate = yf.Ticker("THB=X").fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# ------------------------
# 1. UI SIDEBAR & HEADER
# ------------------------
usd_thb = get_exchange_rate()
with st.sidebar:
    st.title("💼 Active Tracker")
    if not st.session_state.portfolio:
        st.caption("กรอกทุนที่เหรียญเพื่อเริ่มติดตาม...")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            st.info(f"**{sym}** | ทุน: {m['cost']:,.0f}")
    
    st.divider()
    budget = st.number_input("งบประมาณต่อเหรียญ (บาท):", min_value=0.0, value=None)

# ------------------------
# 2. MAIN CONTENT
# ------------------------
st.title("👛 Smart Portfolio Smooth UI")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

# ดึงข้อมูล Top Coins (ขอตัดส่วนดึงข้อมูลมาไว้ตรงนี้เพื่อความกระชับ)
top_symbols = get_top_symbols(30)
cols = st.columns(2)

# จำลองข้อมูลเพื่อรัน UI (ใน Code จริงส่วนนี้จะดึงจาก API เหมือนเดิม)
for idx, s in enumerate(top_symbols[:6] if not budget else top_symbols):
    with cols[idx % 2]:
        with st.container(border=True):
            # จำลองราคาปัจจุบัน (ใช้เลขสมมติเพื่อความเร็วในการโชว์ UI)
            curr_price = 3500.0 * (idx + 1) # ใน code จริงใช้ราคาจาก API
            
            st.subheader(f"🪙 {s}")
            st.metric("ราคาตลาด", f"{curr_price:,.2f} ฿")
            
            # --- กลไก "Smooth Reveal" ---
            m = st.session_state.portfolio.get(s, {'cost': 0.0, 'target': 15, 'stop': 7})
            
            # ช่องกรอกทุนที่เด่นชัด
            entry_p = st.number_input(
                f"ระบุราคาทุน {s} (บาท)", 
                value=float(m['cost']), 
                key=f"cost_{s}",
                placeholder="คลิกเพื่อเริ่มวางแผน..."
            )
            
            # ถ้ามีการ "กำลังพิมพ์" หรือ "มีค่า" (Smooth Reveal Start)
            if entry_p > 0:
                # ส่วนนี้จะ Slide ออกมา
                with st.expander("🎯 ตั้งค่าเป้าหมายและจุดตัดขาดทุน", expanded=True):
                    col_a, col_b = st.columns(2)
                    tgt = col_a.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"t_{s}")
                    stp = col_b.slider(f"จุดตัดขาดทุน (%)", 3, 50, int(m['stop']), key=f"s_{s}")
                    
                    # คำนวณค่าเป็นตัวเงินให้ User เห็นแบบสดๆ (Live Preview)
                    take_profit_price = entry_p * (1 + tgt/100)
                    stop_loss_price = entry_p * (1 - stp/100)
                    
                    st.markdown(f"""
                    <div style="background-color: #1e1e1e; padding: 10px; border-radius: 5px; border-left: 5px solid #00ffcc;">
                        <small>ราคาเป้าขาย: <b>{take_profit_price:,.2f} ฿</b></small><br>
                        <small>ราคาจุดคัด: <b>{stop_loss_price:,.2f} ฿</b></small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                    
                    # Alert Logic
                    diff = ((curr_price - entry_p) / entry_p) * 100
                    if diff >= tgt: st.success(f"🚀 ถึงจุดขาย! (+{diff:.2f}%)")
                    elif diff <= -stp: st.error(f"🛑 ต้องคัดแล้ว! ({diff:.2f}%)")
                    else: st.info(f"📊 กำไรปัจจุบัน: {diff:.2f}%")
            else:
                st.caption("👆 ลองกรอกราคาทุนของคุณเพื่อเปิดระบบวิเคราะห์อัตโนมัติ")

# ------------------------
# 3. AUTO REFRESH
# ------------------------
time.sleep(REFRESH_SEC)
st.rerun()
