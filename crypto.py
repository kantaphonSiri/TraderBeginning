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
st.set_page_config(page_title="Budget-Bets Alpha Pro", layout="wide")

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
# 1. UI SIDEBAR (Smart Portfolio)
# ------------------------
with st.sidebar:
    st.title("💼 Active Portfolio")
    if not st.session_state.portfolio:
        st.info("ยังไม่มีเหรียญที่ติดตาม กรุณากรอกราคาทุนในเหรียญที่สนใจ")
    else:
        # สรุปภาพรวมแบบสั้นๆ ใน Sidebar
        for sym, m in list(st.session_state.portfolio.items()):
            # เราจะไปคำนวณกำไรในส่วน Main และมาแสดงผลที่นี่
            st.markdown(f"**{sym}** | ทุน: {m['cost']:,.0f}")
            if st.button(f"ยกเลิกการติดตาม {sym}", key=f"del_{sym}"):
                del st.session_state.portfolio[sym]
                st.rerun()
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=None, placeholder="กรองราคา...")

# ------------------------
# 2. DATA PROCESSING
# ------------------------
usd_thb = get_exchange_rate()
top_symbols = get_top_symbols(30)
scanned_results = {}

with st.spinner("🤖 กำลังอัปเดตข้อมูลตลาดสด..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty:
                scanned_results[s] = {'price': float(df['Close'].iloc[-1]) * usd_thb, 'df': df}
        except: continue

# ------------------------
# 3. MAIN DISPLAY (Conditional UI)
# ------------------------
st.title("👛 Budget-Bets Alpha Pro")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

# กรองเหรียญ
display_symbols = [s for s, d in scanned_results.items() if budget is None or budget == 0 or d['price'] <= budget]
if not budget: display_symbols = display_symbols[:6]

cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    with cols[idx % 2]:
        with st.container(border=True):
            # ส่วนบน: ข้อมูลทั่วไป
            st.subheader(f"🪙 {s}")
            st.metric("ราคาตลาดตอนนี้", f"{item['price']:,.2f} ฿")
            
            # กราฟจิ๋ว
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # --- จุดตัดสินใจ (Conditional UI) ---
            m = st.session_state.portfolio.get(s, {'cost': 0.0, 'target': 15, 'stop': 7})
            
            # ช่องกรอกทุน (เสมอ)
            entry_p = st.number_input(f"ซื้อ {s} มาที่ราคาเท่าไหร่? (บาท):", value=float(m['cost']), key=f"c_{s}", help="กรอกเลข 0 เพื่อหยุดติดตามเหรียญนี้")
            
            # ถ้ามีการกรอกทุน (ค่า > 0) ถึงจะโชว์ Slider และ Alert
            if entry_p > 0:
                st.markdown("---")
                st.write("🎯 **ตั้งค่าแผนทำกำไรของคุณ:**")
                
                ca, cb = st.columns(2)
                tgt = ca.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"t_{s}")
                stp = cb.slider(f"จุดตัดขาดทุน (%)", 3, 50, int(m['stop']), key=f"s_{s}")
                
                # บันทึกค่า
                st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                
                # คำนวณกำไร/ขาดทุน
                diff = ((item['price'] - entry_p) / entry_p) * 100
                
                # แสดงผลสถานะ
                if diff >= tgt:
                    st.success(f"🚀 **SELL ALERT:** กำไรพุ่งไปถึง {diff:+.2f}% แล้ว! (เป้า {tgt}%)")
                elif diff <= -stp:
                    st.error(f"🛑 **STOP LOSS:** ขาดทุนถึงจุดคัด {diff:+.2f}% แล้ว! (จุดตัด {stp}%)")
                else:
                    st.info(f"📊 กำไรปัจจุบัน: {diff:+.2f}% | สถานะ: กำลังรันเทรนด์")
                    st.progress(min(max((diff / tgt), 0.0), 1.0))
            else:
                # ถ้าเป็น 0 ให้ลบออกจากพอร์ตใน Memory ด้วย
                if s in st.session_state.portfolio:
                    del st.session_state.portfolio[s]
                st.caption("💡 กรอกราคาทุนเพื่อวางแผนจุดขายและระบบแจ้งเตือน")

# Auto Refresh
time.sleep(REFRESH_SEC)
st.rerun()
