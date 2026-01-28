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
DB_FILE = "crypto_v6_analyst.pkl"
st.set_page_config(page_title="AI Crypto Strategist", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            st.session_state.master_data = pickle.load(f)
    else:
        st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. AI ANALYSIS ENGINE (ระบบวิเคราะห์)
# ---------------------------------------------------------
def get_ai_advice(df):
    """วิเคราะห์สัญญาณซื้อขายด้วย RSI และ EMA"""
    if df is None or len(df) < 20: 
        return "รอข้อมูล...", "#808495"
    
    close = df['Close'].astype(float)
    current_p = close.iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    
    # คำนวณ RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs)).iloc[-1]

    # Logic การวิเคราะห์
    if current_p > ema20 and 40 < rsi < 65:
        return "✅ น่าตาม (Strong Trend)", "#00ffcc"
    elif rsi < 30:
        return "💎 ของถูก (Oversold)", "#ffcc00"
    elif rsi > 75:
        return "⚠️ แพงไป (Overbought)", "#ff4b4b"
    elif current_p < ema20:
        return "📉 ขาลง (Wait)", "#ff4b4b"
    else:
        return "⏳ รอดูจังหวะ", "#808495"

# ---------------------------------------------------------
# 3. CORE FUNCTIONS (SYNC)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_top_100_symbols():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        data = requests.get(url, timeout=10).json()
        return [c['symbol'].upper() for c in data]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

def sync_data_safe():
    symbols = get_top_100_symbols()
    try:
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
    except:
        usd_thb = 35.0 
    
    new_data = st.session_state.master_data.copy()
    success_count, fail_count = 0, 0
    batch_size = 20 
    
    with st.status("📡 AI Scanning & Analyzing Market...") as status:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tickers = [f"{s}-USD" for s in batch]
            try:
                data_group = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False, timeout=20)
                for s in batch:
                    try:
                        df = data_group[f"{s}-USD"] if len(tickers) > 1 else data_group
                        if not df.empty and not pd.isna(df['Close'].iloc[-1]):
                            df = df.ffill()
                            new_data[s] = {
                                'price': float(df['Close'].iloc[-1]) * usd_thb,
                                'base_price': float(df['Close'].mean()) * usd_thb,
                                'df': df,
                                'rank': symbols.index(s) + 1
                            }
                            success_count += 1
                            print(f"✅ [SUCCESS] {s}")
                        else:
                            fail_count += 1
                    except:
                        fail_count += 1
                time.sleep(1.2) 
            except:
                continue
        
        st.session_state.master_data = new_data
        with open(DB_FILE, 'wb') as f:
            pickle.dump(new_data, f)
        status.update(label=f"Analysis Complete: OK {success_count}", state="complete")
    st.toast("วิเคราะห์ตลาดเรียบร้อย!", icon="🧠")

# ---------------------------------------------------------
# 4. UI SIDEBAR & MAIN
# ---------------------------------------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if st.session_state.portfolio:
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}", expanded=True):
                st.write(f"ทุน: **{m['cost']:,.2f}**")
                if st.button(f"นำออก", key=f"del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    st.divider()
    budget = st.number_input("งบประมาณ (บาท):", min_value=0.0, step=1000.0)
    if st.button("🔄 Force Update & Analyze"):
        sync_data_safe()
        st.rerun()

st.title("🛡️ Crypto AI Strategist 2026")

if not st.session_state.master_data:
    sync_data_safe()
    st.rerun()

display_list = [s for s, d in st.session_state.master_data.items() if budget == 0 or d['price'] <= budget]
display_list = display_list[:100] if budget > 0 else display_list[:6]

cols = st.columns(2)
for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    icon = "🔵" if data.get('rank', 100) <= 30 else "🪙"
    
    # ดึงคำแนะนำจาก AI
    advice, color = get_ai_advice(data['df'])
    
    with cols[idx % 2]:
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.subheader(f"{icon} {s}")
            if h2.button("📍" if is_pinned else "📌", key=f"btn_p_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15.0, 'stop': 7.0}
                st.rerun()
            
            # แสดงแถบสถานะ AI
            st.markdown(f"<div style='background:{color}; color:black; padding:3px 10px; border-radius:15px; display:inline-block; font-weight:bold; font-size:12px; margin-bottom:10px;'>AI Suggestion: {advice}</div>", unsafe_allow_html=True)
            
            # Metric ราคาและการเติบโต
            growth = ((data['price'] - data['base_price']) / data['base_price']) * 100
            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿", f"{growth:+.2f}% (เทียบ 30 วัน)")
            
            if is_pinned:
                m = st.session_state.portfolio[s]
                new_cost = st.number_input(f"ทุน {s} (กด Enter):", value=float(m['cost']), format="%.2f", key=f"in_{s}")
                if new_cost != m['cost']:
                    st.session_state.portfolio[s]['cost'] = new_cost
                    st.rerun()
                
                c1, c2 = st.columns(2)
                st.session_state.portfolio[s]['target'] = c1.slider("เป้า %", 5, 100, int(m['target']), key=f"t_{s}")
                st.session_state.portfolio[s]['stop'] = c2.slider("คัด %", 3, 50, int(m['stop']), key=f"s_{s}")
                
                # คำนวณกำไรจริงจากทุนที่กรอก
                real_p = ((data['price'] - new_cost) / new_cost) * 100
                st.caption(f"กำไรปัจจุบันจากทุนของคุณ: {real_p:+.2f}%")

            # กราฟ (2026 Syntax)
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(50).values, mode='lines', line=dict(color=color, width=2))])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, width='stretch', key=f"g_{s}", config={'displayModeBar': False})
