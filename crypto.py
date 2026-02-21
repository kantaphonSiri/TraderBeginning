import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & LUXURY STYLES ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* Global Look */
    .stApp { background: linear-gradient(135deg, #0b0e11 0%, #161b22 100%); color: #e9eaeb; }
    
    /* Card Style */
    .trade-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 15px;
        backdrop-filter: blur(10px);
    }
    
    /* Metrics for Mobile */
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00ff88 !important; }
    
    /* Hide specific elements on mobile if needed via CSS Media Queries */
    @media (max-width: 640px) {
        .stMetric { margin-bottom: 10px; }
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }

    /* Style for the Table */
    .stDataFrame { border-radius: 12px; overflow: hidden; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNCTIONS ---
@st.cache_data(ttl=60)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1])
    except: return 35.50

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- 3. DATA LOAD ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

# Default Values
current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
next_invest = 1000.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            df_perf.columns = df_perf.columns.str.strip()
            last_row = df_perf.iloc[-1]
            current_total_bal = float(last_row.get('Balance', 1000))
            if last_row.get('สถานะ') == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
                entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
            # Logic: Dynamic Invest
            last_pnl = str(last_row.get('กำไร%', '0'))
            if '-' not in last_pnl and last_pnl not in ['0', '0%', '']:
                next_invest = 1200.0
    except: pass

# --- 4. NAVIGATION / SIDEBAR ---
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.metric("My Portfolio", f"{current_total_bal:,.2f} ฿")
    st.write(f"💵 Rate: {live_rate:.2f}")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

# --- 5. MOBILE-FIRST LAYOUT ---
st.markdown(f"### 🦔 Pepper Hunter <small style='font-size:12px; color:#888;'>v3.5 Mobile-Ready</small>", unsafe_allow_html=True)

# Top Info Cards (จะกลายเป็น 1 คอลัมน์ในมือถือ)
m1, m2 = st.columns(2)
with m1:
    st.markdown(f'''<div class="trade-card">
        <small>BOT STATUS</small><br>
        <b style="color:{'#ff4b4b' if hunting_symbol else '#00ff88'}">
            {"🔴 BUSY (Holding)" if hunting_symbol else "🟢 IDLE (Scanning)"}
        </b>
    </div>''', unsafe_allow_html=True)
with m2:
    st.markdown(f'''<div class="trade-card">
        <small>NEXT INVESTMENT</small><br>
        <b style="color:#00ff88">{next_invest:,.2f} ฿</b>
    </div>''', unsafe_allow_html=True)

# --- 6. ACTIVE POSITION ---
if hunting_symbol:
    with st.container():
        st.markdown('<div class="trade-card">', unsafe_allow_html=True)
        st.write(f"**Current Asset:** {hunting_symbol}")
        hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
        hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
        cur_p = float(hist['Close'].iloc[-1]) * live_rate
        pnl = ((cur_p - entry_p_thb) / entry_p_thb) * 100
        
        c1, c2 = st.columns([1, 1])
        c1.metric("Price", f"{cur_p:,.2f} ฿", f"{pnl:.2f}%")
        c2.area_chart(hist['Close'], height=120, color="#00ff88" if pnl >=0 else "#ff4b4b")
        st.markdown('</div>', unsafe_allow_html=True)

# --- 7. MARKET TABLE (COMPACT) ---
st.write("#### 🔍 Market Radar")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]

radar_list = []
with st.spinner("Scanning..."):
    raw_data = yf.download(tickers, period="2d", interval="1h", group_by='ticker', progress=False)
    for t in tickers:
        try:
            df = raw_data[t].dropna()
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
            df.ta.rsi(length=14, append=True)
            last = df.tail(1)
            p_thb = float(last['Close'].iloc[0]) * live_rate
            rsi = float(last['RSI_14'].iloc[0])
            
            radar_list.append({
                "Coin": t.replace("-USD", ""),
                "Price": f"{p_thb:,.0f}",
                "RSI": round(rsi, 1),
                "Score": int(80 if rsi < 30 else (60 if rsi < 50 else 40)),
                "Updated": update_time
            })
        except: continue

df_radar = pd.DataFrame(radar_list).sort_values("Score", ascending=False)

# ใช้ st.table หรือ st.dataframe ที่ปรับแต่งให้ดูง่ายในมือถือ
st.dataframe(
    df_radar,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d"),
        "Coin": st.column_config.TextColumn("Asset"),
    }
)

# --- 8. FOOTER REFRESH ---
st.markdown(f"<div style='text-align:center; color:#555; font-size:10px;'>Last Update: {update_time}</div>", unsafe_allow_html=True)
time.sleep(300)
st.rerun()
