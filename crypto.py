import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go

# ------------------------
# 0. CONFIG & DB
# ------------------------
DB_FILE = "crypto_v5_stable.pkl"
st.set_page_config(page_title="Crypto AI Strategist", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            st.session_state.master_data = pickle.load(f)
    else:
        st.session_state.master_data = {}

# 1. ฟังก์ชันดึงรายชื่อ Top 100
@st.cache_data(ttl=3600)
def get_top_100_symbols():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        data = requests.get(url, timeout=10).json()
        return [c['symbol'].upper() for c in data]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE']

# 2. ฟังก์ชันดึงราคาแบบกลุ่ม (ลดการโดน Rate Limit)
def sync_data_safe():
    symbols = get_top_100_symbols()
    usd_thb = yf.Ticker("THB=X").fast_info['last_price']
    
    # แบ่งกลุ่มสแกนทีละ 20 เหรียญเพื่อความปลอดภัย
    batch_size = 20
    with st.status("📡 กำลังดึงข้อมูลแบบปลอดภัย (Batch Mode)...") as status:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tickers = [f"{s}-USD" for s in batch]
            
            try:
                # ดึงข้อมูลรวดเดียว 20 ตัว
                data_group = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False, timeout=20)
                
                for s in batch:
                    try:
                        df = data_group[f"{s}-USD"] if len(tickers) > 1 else data_group
                        if not df.empty and df['Close'].iloc[-1] > 0:
                            df = df.ffill()
                            st.session_state.master_data[s] = {
                                'price': float(df['Close'].iloc[-1]) * usd_thb,
                                'base_price': float(df['Close'].mean()) * usd_thb,
                                'df': df,
                                'rank': symbols.index(s) + 1
                            }
                    except: continue
                
                time.sleep(1) # พัก 1 วินาทีกันโดนแบน
            except: continue
        
        with open(DB_FILE, 'wb') as f:
            pickle.dump(st.session_state.master_data, f)
        status.update(label="✅ ซิงค์สำเร็จ!", state="complete")

# ------------------------
# 3. SIDEBAR (Real-time Enter Sync)
# ------------------------
with st.sidebar:
    st.header("💼 My Portfolio")
    if st.session_state.portfolio:
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}", expanded=True):
                st.write(f"ทุน: **{m['cost']:,.2f}**")
                if st.button(f"นำออก", key=f"del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    st.divider()
    budget = st.number_input("งบประมาณ (บาท):", min_value=0.0, step=1000.0)
    if st.button("🔄 อัปเดตราคาใหม่ทั้งหมด"):
        sync_data_safe()
        st.rerun()

# ------------------------
# 4. MAIN UI
# ------------------------
st.title("🛡️ Crypto Strategist Pro")

if not st.session_state.master_data:
    sync_data_safe()
    st.rerun()

# กรองตามงบ
display_list = [s for s, d in st.session_state.master_data.items() if budget == 0 or d['price'] <= budget]
display_list = display_list[:100] if budget > 0 else display_list[:6]

cols = st.columns(2)
for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    icon = "🔵" if data.get('rank', 100) <= 30 else "🪙"
    
    with cols[idx % 2]:
        with st.container(border=True):
            h1, h2 = st.columns([4, 1])
            h1.subheader(f"{icon} {s}")
            if h2.button("📍" if is_pinned else "📌", key=f"p_btn_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15.0, 'stop': 7.0}
                st.rerun()
            
            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿")
            
            # --- ช่องกรอกราคาทุน (Enter to Update) ---
            if is_pinned:
                m = st.session_state.portfolio[s]
                # ใช้ key เพื่อผูกกับ session และกด Enter เพื่อบันทึก
                new_cost = st.number_input(
                    f"ระบุราคาทุน {s} (กด Enter):",
                    value=float(m['cost']),
                    format="%.2f",
                    key=f"cost_input_{s}"
                )
                
                # ถ้ามีการเปลี่ยนค่า (จาก Enter) ให้บันทึกและ rerun ทันที
                if new_cost != m['cost']:
                    st.session_state.portfolio[s]['cost'] = new_cost
                    st.rerun()
                
                c1, c2 = st.columns(2)
                st.session_state.portfolio[s]['target'] = c1.slider("เป้า %", 5, 100, int(m['target']), key=f"t_{s}")
                st.session_state.portfolio[s]['stop'] = c2.slider("คัด %", 3, 50, int(m['stop']), key=f"s_{s}")
                
                profit = ((data['price'] - new_cost) / new_cost) * 100
                st.info(f"📊 กำไรปัจจุบัน: {profit:+.2f}%")
            
            # กราฟ
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(50).values, mode='lines', line=dict(color='#00ffcc'))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"g_{s}", config={'displayModeBar': False})
