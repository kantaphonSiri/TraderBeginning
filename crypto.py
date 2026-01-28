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
st.set_page_config(page_title="Budget-Bets Personal Strategy", layout="wide")

# ระบบจำพอร์ตและแผนการเทรดแยกเหรียญ
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {} 
    # โครงสร้าง: {'BTC': {'cost': 2100000, 'target': 15, 'stop': 7}, ...}

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
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).abs().rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.001))))
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    return df

# ------------------------
# UI SIDEBAR (Dashboard Summary)
# ------------------------
with st.sidebar:
    st.title("💼 Active Portfolio")
    if not st.session_state.portfolio:
        st.write("ยังไม่มีเหรียญที่ติดตาม")
    else:
        for sym, data in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}"):
                st.write(f"ทุน: {data['cost']:,.0f} ฿")
                st.write(f"เป้า: +{data['target']}% | คัด: -{data['stop']}%")
                if st.button(f"ลบ {sym}", key=f"del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=None, placeholder="กรองราคา...")

# --- MAIN APP ---
usd_thb = get_exchange_rate()
st.title("👛 Personal Strategy Scanner")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

top_symbols = get_top_symbols(30)
scanned_items = []

with st.spinner("🤖 ระบบกำลังวิเคราะห์ข้อมูล..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty:
                df = add_indicators(df)
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                if budget is None or budget == 0 or price_thb <= budget:
                    scanned_items.append({'symbol': s, 'price_thb': price_thb, 'df': df})
        except: continue

# --- DISPLAY ---
display_items = scanned_items if budget else scanned_items[:6]
cols = st.columns(2)

for idx, item in enumerate(display_items):
    with cols[idx % 2]:
        with st.container(border=True):
            st.subheader(f"🪙 {item['symbol']}")
            st.metric("ราคาปัจจุบัน", f"{item['price_thb']:,.2f} ฿")
            
            # Chart
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # --- ส่วนการตั้งค่าแผนการเทรดรายเหรียญ ---
            st.divider()
            st.write("📝 **วางแผนการเทรด:**")
            
            # ดึงค่าเดิมจาก Memory
            m = st.session_state.portfolio.get(item['symbol'], {'cost': 0.0, 'target': 15, 'stop': 7})
            
            c1, c2, c3 = st.columns(3)
            with c1:
                entry_p = st.number_input(f"ทุน (บาท)", value=float(m['cost']), key=f"cost_{item['symbol']}")
            with c2:
                tgt = st.number_input(f"เป้ากำไร (%)", value=int(m['target']), key=f"tgt_{item['symbol']}")
            with c3:
                stp = st.number_input(f"จุดคัด (%)", value=int(m['stop']), key=f"stp_{item['symbol']}")
            
            if entry_p > 0:
                # บันทึกค่าลง Memory
                st.session_state.portfolio[item['symbol']] = {'cost': entry_p, 'target': tgt, 'stop': stp}
                
                # คำนวณผลลัพธ์
                diff = ((item['price_thb'] - entry_p) / entry_p) * 100
                
                # แสดง Alert ตามแผนที่ตั้งไว้ข้างบน
                st.write("---")
                if diff >= tgt:
                    st.success(f"🚀 **SELL ALERT:** กำไร {diff:+.2f}% (ถึงเป้า {tgt}% แล้ว!)")
                elif diff <= -stp:
                    st.error(f"🛑 **STOP LOSS:** ขาดทุน {diff:+.2f}% (ถึงจุดคัด {stp}% แล้ว!)")
                else:
                    st.info(f"📊 **Status:** กำไรปัจจุบัน {diff:+.2f}% (รอถึงเป้า {tgt}%)")

# Auto Refresh
time.sleep(REFRESH_SEC)
st.rerun()
