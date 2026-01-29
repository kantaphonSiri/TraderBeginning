import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go

# ---------------------------------------------------------
# 1. CONFIG & GOOGLE SHEETS
# ---------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"

st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# CSS บังคับ 2 คอลัมน์บนมือถือ
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    @media (max-width: 640px) { .stMarkdown div p, .stMetric div { font-size: 12px !important; } h3 { font-size: 16px !important; } }
    </style>
""", unsafe_allow_html=True)

# Initialize Session States
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'master_data' not in st.session_state: st.session_state.master_data = {}
if 'dash_mode' not in st.session_state: st.session_state.dash_mode = "วงกลม (Donut)"

def load_portfolio_from_sheets():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip().str.lower()
        portfolio = {}
        for _, row in df.iterrows():
            portfolio[str(row['symbol']).upper()] = {
                'cost': float(row['cost']),
                'target': float(row['target']),
                'stop': float(row['stop'])
            }
        return portfolio
    except: return {}

# โหลดข้อมูลจาก Sheets
if not st.session_state.portfolio:
    st.session_state.portfolio = load_portfolio_from_sheets()

# ---------------------------------------------------------
# 2. CORE FUNCTIONS
# ---------------------------------------------------------
def get_ai_advice(df):
    if df is None or len(df) < 20: return "รอข้อมูล...", "#808495"
    close = df['Close'].astype(float)
    rsi = 100 - (100 / (1 + (close.diff().where(lambda x: x>0, 0).rolling(14).mean() / ((-close.diff().where(lambda x: x<0, 0)).rolling(14).mean() + 1e-9)))).iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    curr = close.iloc[-1]
    if curr > ema20 and 40 < rsi < 65: return "✅ น่าตาม", "#00ffcc"
    elif rsi < 30: return "💎 ของถูก", "#ffcc00"
    elif rsi > 75: return "⚠️ ระวัง", "#ff4b4b"
    else: return "⏳ รอดู", "#808495"

def sync_data_safe():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
        res = requests.get(url, timeout=10).json()
        symbols = [c['symbol'].upper() for c in res]
    except: symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

    try: rate = yf.Ticker("THB=X").fast_info['last_price']
    except: rate = 35.0
    
    st.session_state.master_data['EXCHANGE_RATE'] = rate
    new_data = {'EXCHANGE_RATE': rate}
    
    with st.status("📡 กำลังดึงข้อมูลตลาด...") as status:
        tickers = [f"{s}-USD" for s in symbols]
        all_data = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False)
        for s in symbols:
            try:
                df = all_data[f"{s}-USD"] if len(symbols) > 1 else all_data
                if not df.empty:
                    new_data[s] = {'price': float(df['Close'].iloc[-1]) * rate, 'base_price': float(df['Close'].mean()) * rate, 'df': df.ffill(), 'rank': symbols.index(s)+1}
            except: continue
        st.session_state.master_data = new_data
        status.update(label="Sync สำเร็จ!", state="complete")

# ---------------------------------------------------------
# 3. SIDEBAR
# ---------------------------------------------------------
with st.sidebar:
    st.title("💼 Portfolio")
    if st.session_state.portfolio and st.session_state.master_data:
        t_cost, t_market = 0, 0
        chart_labels, chart_values = [], []
        for sym, m in st.session_state.portfolio.items():
            if sym in st.session_state.master_data:
                cp = st.session_state.master_data[sym]['price']
                t_cost += m['cost']
                t_market += cp
                chart_labels.append(sym)
                chart_values.append(cp)
                # เช็ค Alert
                profit_pct = ((cp - m['cost']) / m['cost']) * 100
                if profit_pct >= m['target']: st.toast(f"🚀 {sym} Profit!", icon="🔥")
                if profit_pct <= -m['stop']: st.toast(f"⚠️ {sym} Stop!", icon="🛑")
        
        t_diff = t_market - t_cost
        color = '#00ffcc' if t_diff >= 0 else '#ff4b4b'
        st.metric("กำไร/ขาดทุนรวม", f"{t_diff:,.2f} ฿", f"{(t_diff/t_cost*100 if t_cost>0 else 0):+.2f}%")
        
        fig = go.Figure(data=[go.Pie(labels=chart_labels, values=chart_values, hole=.5)])
        fig.update_layout(height=200, margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    if st.button("🔄 Sync Market", use_container_width=True):
        sync_data_safe()
        st.rerun()

# ---------------------------------------------------------
# 4. MAIN UI (จุดที่หายไป)
# ---------------------------------------------------------
st.title("🪙 Budget-bet Pro")

if not st.session_state.master_data:
    sync_data_safe()
    st.rerun()

rate = st.session_state.master_data.get('EXCHANGE_RATE', 35.0)
st.write(f"💵 1 USD = {rate:.2f} THB")

display_list = [s for s in st.session_state.master_data.keys() if s != 'EXCHANGE_RATE'][:10]
cols = st.columns(2)

for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    advice, color = get_ai_advice(data['df'])
    
    with cols[idx % 2]:
        with st.container(border=True):
            st.subheader(f"{s}")
            st.markdown(f"<span style='color:{color}'>{advice}</span>", unsafe_allow_html=True)
            st.metric("ราคา", f"{data['price']:,.2f} ฿")
            
            # Sparkline
            fig_p = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(30))])
            fig_p.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_p, use_container_width=True, key=f"chart_{s}")
