import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go

# ---------------------------------------------------------
# 1. CONFIG & DATABASE
# ---------------------------------------------------------
DB_FILE = "crypto_v8_exchange.pkl"
st.set_page_config(page_title="AI Crypto Strategist Pro", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            st.session_state.master_data = pickle.load(f)
    else:
        st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. CORE FUNCTIONS
# ---------------------------------------------------------
def get_ai_advice(df):
    if df is None or len(df) < 20: return "รอข้อมูล...", "#808495"
    close = df['Close'].astype(float)
    current_p = close.iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    if current_p > ema20 and 40 < rsi < 65: return "✅ น่าตาม (Trend)", "#00ffcc"
    elif rsi < 30: return "💎 ของถูก (ช้อน)", "#ffcc00"
    elif rsi > 75: return "⚠️ แพงไป (ระวัง)", "#ff4b4b"
    elif current_p < ema20: return "📉 ขาลง (เลี่ยง)", "#ff4b4b"
    else: return "⏳ รอดูจังหวะ", "#808495"

def sync_data_safe():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        symbols = [c['symbol'].upper() for c in requests.get(url, timeout=10).json()]
    except:
        symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
    
    try:
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
        st.session_state.master_data['EXCHANGE_RATE'] = usd_thb
    except:
        usd_thb = st.session_state.master_data.get('EXCHANGE_RATE', 35.0)
    
    new_data = st.session_state.master_data.copy()
    batch_size = 20 
    with st.status("📡 AI Scanning & Syncing...") as status:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tickers = [f"{s}-USD" for s in batch]
            try:
                data_group = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False)
                for s in batch:
                    try:
                        df = data_group[f"{s}-USD"] if len(tickers) > 1 else data_group
                        if not df.empty and not pd.isna(df['Close'].iloc[-1]):
                            new_data[s] = {
                                'price': float(df['Close'].iloc[-1]) * usd_thb,
                                'base_price': float(df['Close'].mean()) * usd_thb,
                                'df': df.ffill(),
                                'rank': symbols.index(s) + 1
                            }
                    except: continue
                time.sleep(1.2)
            except: continue
        st.session_state.master_data = new_data
        with open(DB_FILE, 'wb') as f:
            pickle.dump(new_data, f)
        status.update(label="Sync Completed!", state="complete")

# ---------------------------------------------------------
# 3. SIDEBAR
# ---------------------------------------------------------
with st.sidebar:
    st.title("💼 Dashboard")
    if st.session_state.portfolio:
        t_cost = 0
        t_market = 0
        for sym, m in st.session_state.portfolio.items():
            if sym in st.session_state.master_data:
                curr_price = st.session_state.master_data[sym]['price']
                t_cost += m['cost']
                t_market += curr_price
        t_diff = t_market - t_cost
        t_pct = (t_diff / t_cost * 100) if t_cost > 0 else 0
        st.markdown(f"""
        <div style="background:#1e1e1e; padding:15px; border-radius:10px; border-left: 5px solid {'#00ffcc' if t_diff >= 0 else '#ff4b4b'}">
            <p style="margin:0; font-size:12px; color:#888;">กำไร/ขาดทุนรวม</p>
            <h2 style="margin:0; color:{'#00ffcc' if t_diff >= 0 else '#ff4b4b'}">{t_diff:,.2f} ฿</h2>
            <p style="margin:0; font-size:14px;">{t_pct:+.2f}%</p>
        </div>
        """, unsafe_allow_html=True)
        st.divider()
        st.subheader("📌 เหรียญที่ปักหมุด")
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"{sym}"):
                st.write(f"ทุน: {m['cost']:,.2f}")
                if st.button(f"นำ {sym} ออก", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    st.divider()
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, step=1000.0)
    if st.button("🔄 อัปเดตข้อมูล"):
        sync_data_safe()
        st.rerun()

# ---------------------------------------------------------
# 4. MAIN UI
# ---------------------------------------------------------
st.title("👛 Budget-Bet")

# --- โชว์ค่าเงินบาทตรงนี้ ---
rate = st.session_state.master_data.get('EXCHANGE_RATE', 0)
if rate > 0:
    st.markdown(f"💵 **อัตราแลกเปลี่ยน:** `1 USD = {rate:.2f} THB`", help="ราคาจาก Yahoo Finance")
else:
    st.caption("⚠️ กรุณากดปุ่ม Sync เพื่อโหลดข้อมูลค่าเงิน")
st.divider()

if not st.session_state.master_data or len(st.session_state.master_data) < 2:
    sync_data_safe()
    st.rerun()

display_list = [s for s, d in st.session_state.master_data.items() if s != 'EXCHANGE_RATE' and (budget == 0 or d['price'] <= budget)]
display_list = display_list[:100] if budget > 0 else display_list[:6]

cols = st.columns(2)
for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    advice, color = get_ai_advice(data['df'])
    icon = "🔵" if data.get('rank', 100) <= 30 else "🪙"
    
    with cols[idx % 2]:
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.subheader(f"{icon} {s}")
            if h2.button("📍" if is_pinned else "📌", key=f"btn_p_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15.0, 'stop': 7.0}
                st.rerun()
            st.markdown(f"<span style='background:{color}; color:black; padding:2px 8px; border-radius:10px; font-weight:bold; font-size:10px;'>AI: {advice}</span>", unsafe_allow_html=True)
            growth = ((data['price'] - data['base_price']) / data['base_price']) * 100
            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿", f"{growth:+.2f}% (30d)")
            if is_pinned:
                m = st.session_state.portfolio[s]
                new_cost = st.number_input(f"ทุน {s}:", value=float(m['cost']), format="%.2f", key=f"in_{s}")
                if new_cost != m['cost']:
                    st.session_state.portfolio[s]['cost'] = new_cost
                    st.rerun()
                c1, c2 = st.columns(2)
                st.session_state.portfolio[s]['target'] = c1.slider("เป้า %", 5, 100, int(m['target']), key=f"t_{s}")
                st.session_state.portfolio[s]['stop'] = c2.slider("คัด %", 3, 50, int(m['stop']), key=f"s_{s}")
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(50).values, mode='lines', line=dict(color=color, width=2))])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, width='stretch', key=f"g_{s}", config={'displayModeBar': False})
