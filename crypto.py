import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh # ต้องเพิ่มใน requirements.txt

# ---------------------------------------------------------
# 1. CONFIG & DATABASE
# ---------------------------------------------------------
# ใส่ Link CSV จาก Google Sheets ของคุณที่นี่
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pubhtml?gid=0&single=true"
DB_FILE = "crypto_v11_responsive.pkl"

st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# ตั้งค่า Auto Refresh ทุก 5 นาที (300,000 milliseconds) เพื่อความเสถียรและไม่โดนแบน API
st_autorefresh(interval=300000, key="datarefresh")

# CSS บังคับ 2 คอลัมน์บนมือถือ (คงเดิม)
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    @media (max-width: 640px) { .stMarkdown div p, .stMetric div { font-size: 12px !important; } h3 { font-size: 16px !important; } }
    </style>
""", unsafe_allow_html=True)

# ฟังก์ชันโหลด Portfolio จาก Sheets (เพิ่มความเสถียร)
def load_portfolio_sheets():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip().str.lower()
        port = {}
        for _, row in df.iterrows():
            port[str(row['symbol']).upper()] = {
                'cost': float(row['cost']),
                'target': float(row['target']),
                'stop': float(row['stop'])
            }
        return port
    except:
        return st.session_state.get('portfolio', {})

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio_sheets()
if 'dash_mode' not in st.session_state:
    st.session_state.dash_mode = "วงกลม (Donut)"
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f: st.session_state.master_data = pickle.load(f)
    else: st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. CORE FUNCTIONS (ปรับปรุง Batch Sync ป้องกันโดนแบน)
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
    # โหลด Portfolio ใหม่ทุกครั้งที่ Sync
    st.session_state.portfolio = load_portfolio_sheets()
    
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
        symbols = [c['symbol'].upper() for c in requests.get(url, timeout=10).json()]
    except:
        symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
        
    try:
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
        st.session_state.master_data['EXCHANGE_RATE'] = usd_thb
    except:
        usd_thb = st.session_state.master_data.get('EXCHANGE_RATE', 35.0)
    
    new_data = {'EXCHANGE_RATE': usd_thb}
    with st.status("📡 AI Scanning Market...") as status:
        tickers = [f"{s}-USD" for s in symbols]
        # Batch Download รวดเดียวเพื่อความปลอดภัย
        data_group = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False)
        for s in symbols:
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
        st.session_state.master_data = new_data
        with open(DB_FILE, 'wb') as f: pickle.dump(new_data, f)
        status.update(label="Sync Completed!", state="complete")

# ---------------------------------------------------------
# 3. SIDEBAR (RESPONSIVE DASHBOARD)
# ---------------------------------------------------------
with st.sidebar:
    st.title("💼 Portfolio Monitor")
    if st.session_state.portfolio:
        t_cost, t_market = 0, 0
        chart_labels, chart_values = [], []
        for sym, m in st.session_state.portfolio.items():
            if sym in st.session_state.master_data:
                cp = st.session_state.master_data[sym]['price']
                t_cost += m['cost']
                t_market += cp
                chart_labels.append(sym)
                chart_values.append(cp)
                
                # ระบบแจ้งเตือนในตัว (Check Alerts)
                profit_pct = ((cp - m['cost']) / m['cost']) * 100
                if profit_pct >= m['target']: st.toast(f"🚀 {sym} ถึงเป้าขาย! +{profit_pct:.1f}%", icon="🔥")
                if profit_pct <= -m['stop']: st.toast(f"⚠️ {sym} จุดคัด! {profit_pct:.1f}%", icon="🛑")
        
        t_diff = t_market - t_cost
        t_pct = (t_diff / t_cost * 100) if t_cost > 0 else 0
        
        st.markdown(f"""
            <div style="background:#1e1e1e; padding:15px; border-radius:10px; border-left: 5px solid {'#00ffcc' if t_diff >= 0 else '#ff4b4b'}; margin-bottom: 10px;">
                <p style="margin:0; font-size:12px; color:#888;">กำไร/ขาดทุนรวม</p>
                <h2 style="margin:0; color:{'#00ffcc' if t_diff >= 0 else '#ff4b4b'}">{t_diff:,.2f} ฿</h2>
                <p style="margin:0; font-size:14px;">{t_pct:+.2f}%</p>
            </div>
        """, unsafe_allow_html=True)
        
        # กราฟ (คงเดิม)
        fig = go.Figure(data=[go.Pie(labels=chart_labels, values=chart_values, hole=.5)])
        fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=10), height=220, paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, step=1000.0)
    if st.button("🔄 อัปเดตตลาด (Sync Now)", use_container_width=True):
        sync_data_safe()
        st.rerun()

# ---------------------------------------------------------
# 4. MAIN UI (คงเดิม)
# ---------------------------------------------------------
st.title("🪙 Budget-bet Pro")
rate = st.session_state.master_data.get('EXCHANGE_RATE', 0)
if not st.session_state.master_data or len(st.session_state.master_data) < 2:
    sync_data_safe()
    st.rerun()

st.markdown(f"💵 **Rate:** `1 USD = {rate:.2f} THB` | ⏱️ *Auto-refresh: 5 min*")

display_list = [s for s, d in st.session_state.master_data.items() if s != 'EXCHANGE_RATE' and (budget == 0 or d['price'] <= budget)]
display_list = display_list[:6]
cols = st.columns(2)

for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    advice, color = get_ai_advice(data['df'])
    
    with cols[idx % 2]:
        with st.container(border=True):
            st.subheader(f"{s}")
            st.markdown(f"<span style='background:{color}; color:black; padding:2px 8px; border-radius:10px; font-size:10px;'>{advice}</span>", unsafe_allow_html=True)
            
            growth = ((data['price'] - data['base_price']) / data['base_price']) * 100
            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿", f"{growth:+.2f}%")
            
            # Sparkline
            fig_p = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(50).values, mode='lines', line=dict(color=color, width=2))])
            fig_p.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_p, width='stretch', key=f"g_{s}", config={'displayModeBar': False})
