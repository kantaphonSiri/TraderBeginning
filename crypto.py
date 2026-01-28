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
# 2. UI SIDEBAR
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.write("ยังไม่มีเหรียญที่ติดตาม")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            # ตรวจสอบว่ามีข้อมูลเหรียญนั้นในรอบนี้ไหม
            with st.expander(f"📌 {sym}"):
                st.write(f"ทุน: {m['cost']:,.2f}")
                if st.button(f"นำออกจากพอร์ต", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=None)

# ------------------------
# 3. MAIN APP
# ------------------------
usd_thb = get_exchange_rate()
st.title("👛 Smart Trading Panel")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

# ดึงข้อมูลเหรียญ
top_symbols = get_top_symbols(30)
scanned_results = {}
with st.spinner("🤖 อัปเดตราคาตลาด..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty:
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                scanned_results[s] = {'price': price_thb, 'df': df}
        except: continue

# กรองเหรียญ
display_symbols = [s for s, d in scanned_results.items() if budget is None or budget == 0 or d['price'] <= budget]
if not budget: display_symbols = display_symbols[:6]

# --- DISPLAY ---
cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    with cols[idx % 2]:
        with st.container(border=True):
            # ส่วนบน: ข้อมูลเหรียญ
            st.subheader(f"🪙 {s}")
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # กราฟ
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # --- 💡 ลูกเล่นใหม่: Click to Expand Strategy ---
            # เช็คว่าเหรียญนี้เคยมีข้อมูลในพอร์ตไหม
            in_port = s in st.session_state.portfolio
            
            # ใช้ Toggle เป็นสวิตช์เปิดแผงควบคุม (สวยกว่า checkbox)
            show_panel = st.toggle(f"วางแผนเทรด {s}", value=in_port, key=f"toggle_{s}")
            
            if show_panel:
                with st.expander("🛠 แผงควบคุมกลยุทธ์", expanded=True):
                    m = st.session_state.portfolio.get(s, {'cost': item['price'], 'target': 15, 'stop': 7})
                    
                    # 1. ช่องกรอกราคาทุน (Slide ลงมาเป็นอันแรก)
                    entry_p = st.number_input(f"ราคาทุนที่ซื้อ (บาท):", value=float(m['cost']), key=f"cost_{s}")
                    
                    # 2. Sliders เป้าหมายและจุดขาดทุน
                    ca, cb = st.columns(2)
                    tgt = ca.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"tgt_{s}")
                    stp = cb.slider(f"จุดตัดขาดทุน (%)", 3, 50, int(m['stop']), key=f"stp_{s}")
                    
                    # บันทึกข้อมูล
                    if entry_p > 0:
                        st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                        diff = ((item['price'] - entry_p) / entry_p) * 100
                        
                        # แสดงผลลัพธ์
                        st.divider()
                        if diff >= tgt:
                            st.success(f"🚀 **SELL ALERT:** {diff:+.2f}%")
                        elif diff <= -stp:
                            st.error(f"🛑 **STOP LOSS:** {diff:+.2f}%")
                        else:
                            st.info(f"📊 กำไรปัจจุบัน: {diff:+.2f}%")
                            st.progress(min(max((diff / tgt), 0.0), 1.0))
            else:
                # ถ้าปิด Toggle และเคยมีในพอร์ต ให้ถามว่ายังจะเก็บไว้ไหม หรือถ้าไม่มีก็แสดง Guide
                if in_port:
                    st.caption("⚠️ แผงถูกปิด แต่ระบบยังเฝ้าพอร์ตให้คุณใน Sidebar")

time.sleep(REFRESH_SEC)
st.rerun()
