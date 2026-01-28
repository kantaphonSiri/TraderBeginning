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

def add_indicators(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    close = df['Close'].astype(float)
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    return df

# --- ดึงราคาและอัตราแลกเปลี่ยนเบื้องต้น ---
usd_thb = get_exchange_rate()
top_symbols = get_top_symbols(30)
scanned_results = {} # เก็บข้อมูลชั่วคราวเพื่อใช้แสดงใน Sidebar

# ------------------------
# 2. MAIN PROCESSING (ดึงข้อมูลก่อนเพื่อใช้ทั้งหน้าจอและ Sidebar)
# ------------------------
with st.spinner("🤖 ระบบกำลังอัปเดตราคาล่าสุด..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty:
                df = add_indicators(df)
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                scanned_results[s] = {'price': price_thb, 'df': df}
        except: continue

# ------------------------
# 3. UI SIDEBAR (Advanced Portfolio Dashboard)
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    
    if not st.session_state.portfolio:
        st.write("ยังไม่มีเหรียญในพอร์ต")
    else:
        # สรุปภาพรวมพอร์ต
        total_pnl = 0
        for sym, m in list(st.session_state.portfolio.items()):
            if sym in scanned_results:
                current_p = scanned_results[sym]['price']
                diff = ((current_p - m['cost']) / m['cost']) * 100
                
                # กำหนดสถานะและสี
                if diff >= m['target']: 
                    status_text = "ถึงเป้า 🚀"
                    status_color = "green"
                elif diff <= -m['stop']: 
                    status_text = "คัดด่วน 🛑"
                    status_color = "red"
                else: 
                    status_text = "รันเทรนด์ 📊"
                    status_color = "white"
                
                # แสดงผลในการ์ดเล็กๆ ใน Sidebar
                with st.expander(f"📌 {sym}: {diff:+.2f}%", expanded=True):
                    c1, c2 = st.columns(2)
                    c1.caption("ราคาทุน")
                    c1.write(f"{m['cost']:,.2f}")
                    c2.caption("ราคาปัจจุบัน")
                    c2.write(f"{current_p:,.2f}")
                    
                    st.markdown(f"สถานะ: <span style='color:{status_color}'>{status_text}</span>", unsafe_allow_html=True)
                    
                    if st.button(f"ลบ {sym}", key=f"side_del_{sym}"):
                        del st.session_state.portfolio[sym]
                        st.rerun()
    
    st.divider()
    st.subheader("⚙️ Settings")
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=None, placeholder="กรอกเพื่อกรองราคา...")

# ------------------------
# 4. MAIN APP DISPLAY
# ------------------------
st.title("👛 Budget-Bets Alpha Dashboard")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

# กรองเหรียญที่จะแสดงหน้าจอหลัก
display_symbols = []
for s, data in scanned_results.items():
    if budget is None or budget == 0 or data['price'] <= budget:
        display_symbols.append(s)

if not budget:
    display_symbols = display_symbols[:6]
    st.info("💡 แสดง 6 เหรียญแนะนำ (กรอกงบประมาณเพื่อดูตามจริง)")

cols = st.columns(2)
for idx, s in enumerate(display_symbols):
    item = scanned_results[s]
    with cols[idx % 2]:
        with st.container(border=True):
            st.subheader(f"🪙 {s}")
            st.metric("ราคาตลาด", f"{item['price']:,.2f} ฿")
            
            # Chart
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # --- Individual Strategy ---
            st.divider()
            m = st.session_state.portfolio.get(s, {'cost': 0.0, 'target': 15, 'stop': 7})
            
            entry_p = st.number_input(f"ราคาทุน {s} (บาท):", value=float(m['cost']), key=f"main_cost_{s}")
            ca, cb = st.columns(2)
            tgt = ca.slider(f"เป้ากำไร (%)", 5, 100, int(m['target']), key=f"main_tgt_{s}")
            stp = cb.slider(f"จุดคัด (%)", 3, 50, int(m['stop']), key=f"main_stp_{s}")
            
            if entry_p > 0:
                st.session_state.portfolio[s] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                diff = ((item['price'] - entry_p) / entry_p) * 100
                
                # แสดงผลสถานะใต้ Slider
                if diff >= tgt:
                    st.success(f"🚀 **SELL ALERT:** กำไร {diff:+.2f}%")
                elif diff <= -stp:
                    st.error(f"🛑 **STOP LOSS:** ขาดทุน {diff:+.2f}%")
                else:
                    st.info(f"📊 กำไรปัจจุบัน: {diff:+.2f}%")
                    st.progress(min(max((diff / tgt), 0.0), 1.0))

time.sleep(REFRESH_SEC)
st.rerun()
