import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. CONFIG & ADAPTIVE LOGIC
# ---------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"

st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# CSS: บังคับ 2 คอลัมน์บนมือถือ + ตกแต่ง Card
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    .stMetric { background: #1e1e1e; padding: 10px; border-radius: 10px; border: 1px solid #333; }
    @media (max-width: 640px) { .stMarkdown div p, .stMetric div { font-size: 12px !important; } h3 { font-size: 16px !important; } }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA FUNCTIONS
# ---------------------------------------------------------
def get_market_data():
    try:
        # ดึงราคาจาก Binance (ตัวเบาที่สุด)
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
        df = pd.DataFrame(res)
        df['lastPrice'] = df['lastPrice'].astype(float)
        df['priceChangePercent'] = df['priceChangePercent'].astype(float)
        return df
    except: return pd.DataFrame()

def load_portfolio():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip().str.lower()
        return df
    except: return pd.DataFrame()

# ---------------------------------------------------------
# 3. ADAPTIVE REFRESH LOGIC (หัวใจของระบบ)
# ---------------------------------------------------------
df_market = get_market_data()
btc_change = 0
if not df_market.empty:
    btc_row = df_market[df_market['symbol'] == 'BTCUSDT']
    btc_change = abs(btc_row['priceChangePercent'].values[0])

# คำนวณความเร็วในการ Refresh
if btc_change > 4.0:
    refresh_ms = 10000 # 10 วิ (ตลาดเดือด)
    status_msg = "🔥 ตลาดผันผวนสูง (Refresh: 10s)"
elif btc_change > 1.5:
    refresh_ms = 30000 # 30 วิ (ตลาดขยับ)
    status_msg = "⚡ ตลาดปกติ (Refresh: 30s)"
else:
    refresh_ms = 60000 # 60 วิ (ตลาดนิ่ง)
    status_msg = "💤 ตลาดนิ่ง (Refresh: 60s)"

st_autorefresh(interval=refresh_ms, key="adaptive_ref")

# ---------------------------------------------------------
# 4. UI - SIDEBAR
# ---------------------------------------------------------
df_port = load_portfolio()
rate = 35.5 # สามารถปรับให้ดึง API อัตราแลกเปลี่ยนได้

with st.sidebar:
    st.title("💼 Portfolio")
    st.info(status_msg)
    
    if not df_port.empty:
        total_profit = 0
        for _, row in df_port.iterrows():
            sym = row['symbol'].upper()
            m_row = df_market[df_market['symbol'] == f"{sym}USDT"]
            if not m_row.empty:
                curr_p = m_row['lastPrice'].values[0] * rate
                diff = ((curr_p - row['cost']) / row['cost']) * 100
                st.write(f"**{sym}**: {curr_p:,.2f} ฿ ({diff:+.2f}%)")
                # ระบบแจ้งเตือนในแอป
                if diff >= row['target']: st.toast(f"🚀 {sym} ถึงเป้า!", icon="🔥")
                if diff <= -row['stop']: st.toast(f"🛑 {sym} หลุดจุดคัด!", icon="⚠️")

# ---------------------------------------------------------
# 5. MAIN UI (แสดงแค่ 6 ตัว)
# ---------------------------------------------------------
st.title("🪙 Budget-bet Pro")
st.caption(f"Binance Engine | Adaptive Mode: {status_msg}")

# เลือกแสดง 6 ตัวแรกจาก Portfolio หรือเหรียญหลัก
if not df_port.empty:
    display_symbols = df_port['symbol'].str.upper().tolist()[:6]
else:
    display_symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']

cols = st.columns(2)

for idx, sym in enumerate(display_symbols):
    m_row = df_market[df_market['symbol'] == f"{sym}USDT"]
    if not m_row.empty:
        p = m_row['lastPrice'].values[0] * rate
        chg = m_row['priceChangePercent'].values[0]
        
        with cols[idx % 2]:
            with st.container(border=True):
                st.subheader(f"{sym}")
                st.metric("ราคาปัจจุบัน", f"{p:,.2f} ฿", f"{chg:+.2f}%")
                
                # กราฟ Sparkline แบบง่าย
                fig = go.Figure(go.Scatter(y=[float(m_row['openPrice'].values[0]), p], 
                                         line=dict(color='#00ffcc' if chg >= 0 else '#ff4b4b', width=3)))
                fig.update_layout(height=60, margin=dict(l=0,r=0,t=0,b=0), 
                                 xaxis_visible=False, yaxis_visible=False, 
                                 paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
