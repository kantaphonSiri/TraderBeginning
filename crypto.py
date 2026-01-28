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

# ระบบความจำของพอร์ต
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {} 

# 1. ฟังก์ชันดึงรายชื่อเหรียญ (API Coingecko)
@st.cache_data(ttl=3600)
def get_top_symbols(limit=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except:
        # สำรองข้อมูลกรณี API ล่ม
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'DOT']

# 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน (API Yahoo Finance)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# ------------------------
# 3. DATA FETCHING (ดึงข้อมูลตลาด)
# ------------------------
usd_thb = get_exchange_rate()
top_symbols = get_top_symbols(30)
scanned_results = {}

with st.spinner("🤖 กำลังอัปเดตราคาและกราฟจาก API..."):
    for s in top_symbols:
        try:
            # ดึงข้อมูล 7 วัน ความละเอียด 15 นาที เพื่อให้กราฟ "ไม่เป็นจุด"
            df = yf.download(f"{s}-USD", period="7d", interval="15m", progress=False)
            if not df.empty:
                # แก้ปัญหา MultiIndex Columns
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # --- แก้ Bug กราฟเป็นจุด (Data Cleaning) ---
                df = df.ffill() # เติมค่าว่างด้วยค่าก่อนหน้า
                
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                scanned_results[s] = {'price': price_thb, 'df': df}
        except: continue

# ------------------------
# 4. UI SIDEBAR (พอร์ตของคุณ)
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.info("ยังไม่มีเหรียญที่ปักหมุด")
    else:
        for sym, m in list(st.session_state.portfolio.items()):
            if sym in scanned_results:
                current_p = scanned_results[sym]['price']
                diff = ((current_p - m['cost']) / m['cost']) * 100
                with st.expander(f"📌 {sym}: {diff:+.2f}%", expanded=True):
                    st.write(f"ทุน: {m['cost']:,.2f} | ตลาด: {current_p:,.2f}")
                    if st.button(f"นำออก", key=f"side_del_{sym}"):
                        del st.session_state.portfolio[sym]
                        st.rerun()
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=0.0, help="ถ้าใส่ 0 จะแสดงทุกเหรียญ")

# ------------------------
# 5. MAIN DASHBOARD
# ------------------------
st.title("👛 Smart Trading Dashboard")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | อัปเดตล่าสุด: {datetime.now().strftime('%H:%M:%S')}")

# กรองเหรียญตามงบประมาณ
display_symbols = [s for s, d in scanned_results.items() if budget == 0 or d['price'] <= budget]
if not budget: display_symbols = display_symbols[:6]

cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    is_pinned = s in st.session_state.portfolio
    
    with cols[idx % 2]:
        with st.container(border=True):
            # --- ส่วนหัว: ชื่อเหรียญ + ปุ่ม Icon Pin ---
            h_left, h_right = st.columns([4, 1])
            h_left.subheader(f"🪙 {s}")
            
            # ปุ่ม Pin/Pinned (เปลี่ยนสีและไอคอนตามสถานะ)
            pin_icon = "📍 Pinned" if is_pinned else "📌"
            if h_right.button(pin_icon, key=f"btn_{s}"):
                if is_pinned:
                    del st.session_state.portfolio[s]
                else:
                    st.session_state.portfolio[s] = {'cost': item['price'], 'target': 15, 'stop': 7}
                st.rerun()
            
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # --- กราฟเส้น (Smooth Area Chart) ---
            # ใช้ข้อมูล 100 จุดล่าสุดเพื่อให้เห็นความเคลื่อนไหวชัดๆ
            plot_df = item['df']['Close'].tail(100)
            fig = go.Figure(data=[go.Scatter(
                y=plot_df.values, 
                mode='lines',
                line=dict(color='#00ffcc', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 204, 0.1)'
            )])
            fig.update_layout(
                height=120, 
                margin=dict(l=0,r=0,t=0,b=0), 
                xaxis_visible=False, 
                yaxis_visible=False, 
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # --- ส่วนจัดการกลยุทธ์ (จะโผล่เมื่อ Pin เท่านั้น) ---
            if is_pinned:
                st.divider()
                m = st.session_state.portfolio[s]
                
                # ช่องกรอกทุนและ Slider ปรับเป้า
                entry_p = st.number_input(f"ต้นทุน {s} (บาท):", value=float(m['cost']), key=f"cost_{s}")
                c1, c2 = st.columns(2)
                tgt = c1.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"tgt_{s}")
                stp = c2.slider(f"จุดคัด (%)", 3, 50, int(m['stop']), key=f"stp_{s}")
                
                # อัปเดตค่าเข้าหน่วยความจำ
                st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                
                # แสดงผลกำไร/ขาดทุน
                diff = ((item['price'] - entry_p) / entry_p) * 100
                if diff >= tgt:
                    st.success(f"🚀 **ถึงเป้าขาย:** {diff:+.2f}%")
                elif diff <= -stp:
                    st.error(f"🛑 **ต้องตัดขาดทุน:** {diff:+.2f}%")
                else:
                    st.info(f"📊 กำไรปัจจุบัน: {diff:+.2f}%")
                    st.progress(min(max((diff / tgt), 0.0), 1.0))
            else:
                st.caption("💡 กดปุ่ม 📌 Pin เพื่อเริ่มวางแผนและบันทึกเข้าพอร์ต")

# Auto-Refresh ทุก 1 นาที
time.sleep(REFRESH_SEC)
st.rerun()
