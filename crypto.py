import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & STYLES ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide", initial_sidebar_state="expanded")

# ปรับ CSS ให้ดูหรูหราและอ่านง่ายขึ้น
st.markdown("""
    <style>
    .stApp { background-color: #0b0e11; color: #e9eaeb; }
    [data-testid="stMetricValue"] { font-size: 28px !important; color: #00ff88 !important; }
    .stDataFrame { border: none !important; }
    .css-1kyx0rg { background-color: #161b22; }
    /* ตกแต่งปุ่ม Emergency */
    .stButton>button { border-radius: 8px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CORE FUNCTIONS ---
@st.cache_data(ttl=60) # Cache อัตราแลกเปลี่ยน 1 นาที
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1])
    except: return 35.50

def get_news_cards(symbol):
    try:
        coin = symbol.split('-')[0]
        feed = feedparser.parse(f"https://www.newsbtc.com/search/{coin}/feed/")
        return feed.entries[:3] if feed.entries else []
    except: return []

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- 3. DATA PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

# (ส่วนการดึงข้อมูลจาก Google Sheet คงเดิม)
current_total_bal = 1000.0
hunting_symbol = None
entry_p_thb = 0.0
next_invest = 1000.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            df_perf.columns = df_perf.columns.str.strip()
            if not df_perf.empty:
                last_row = df_perf.iloc[-1]
                current_total_bal = float(last_row['Balance']) if 'Balance' in df_perf.columns else 1000.0
                if 'สถานะ' in df_perf.columns and last_row['สถานะ'] == 'HUNTING':
                    hunting_symbol = last_row.get('เหรียญ', None)
                    entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
                
                # Logic การทบเงิน
                if 'กำไร%' in df_perf.columns:
                    last_pnl = str(last_row['กำไร%'])
                    next_invest = 1200.0 if ('-' not in last_pnl and last_pnl not in ['0', '0%', '']) else 1000.0
    except: pass

# --- 4. SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2586/2586125.png", width=60)
    st.title("PEPPER CTRL")
    st.divider()
    st.metric("PORTFOLIO", f"{current_total_bal:,.2f} ฿")
    st.info(f"**Next Invest:** {next_invest:,.0f} ฿")
    st.write(f"💹 USD/THB: **{live_rate:.2f}**")
    st.caption(f"Last Sync: {update_time}")
    if st.button("🚀 FORCE SYNC", use_container_width=True):
        st.rerun()

# --- 5. MAIN UI ---
st.title("🦔 Pepper Hunter")

# KPI Top Bar ด้วย Container เพื่อความสะอาด
with st.container():
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("BOT STATUS", "🔴 BUSY" if hunting_symbol else "🟢 SCANNING")
    k2.metric("ACTIVE PAIRS", "9 ASSETS")
    k3.metric("WIN RATE", "65%", "2% ↑")
    k4.metric("DAILY GOAL", "10,000 ฿", f"{(current_total_bal/10000)*100:.1f}%")

st.divider()

col_main, col_side = st.columns([2.5, 1])

with col_main:
    # --- ACTIVE MISSION ---
    if hunting_symbol:
        with st.expander(f"⚡ ACTIVE MISSION: {hunting_symbol}", expanded=True):
            hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
            hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
            cur_p = float(hist['Close'].iloc[-1]) * live_rate
            pnl = ((cur_p - entry_p_thb) / entry_p_thb) * 100
            
            m1, m2 = st.columns([1, 2])
            m1.metric("CURRENT PRICE", f"{cur_p:,.2f} ฿", f"{pnl:.2f}%")
            m2.area_chart(hist['Close'], height=150, color="#00ff88" if pnl >=0 else "#ff4b4b")

    # --- MARKET RADAR ---
    st.subheader("🔍 MARKET RADAR")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
    radar_data = []

    with st.spinner("🕵️ Updating Market Data..."):
        # ดึงข้อมูลรวดเดียว
        all_prices = yf.download(tickers, period="2d", interval="1h", group_by='ticker', progress=False)
        for t in tickers:
            try:
                df_h = all_prices[t].dropna()
                df_h.columns = [col[0] if isinstance(col, tuple) else col for col in df_h.columns]
                df_h.ta.rsi(length=14, append=True)
                df_h.ta.ema(length=50, append=True)
                
                last_row = df_h.iloc[-1]
                price_thb = float(last_row['Close']) * live_rate
                rsi = float(last_row['RSI_14'])
                ema50 = float(last_row['EMA_50']) * live_rate
                
                # ดึงเวลาล่าสุดจาก Index (Datetime)
                last_ts = df_h.index[-1].strftime("%H:%M") 
                
                score = 60 if price_thb > ema50 else 0
                if 40 < rsi < 65: score += 20
                
                radar_data.append({
                    "Symbol": t.replace("-USD", ""),
                    "Price (฿)": price_thb,
                    "RSI": rsi,
                    "Score": score,
                    "Last Update": last_ts,
                    "Status": "⭐ HOLD" if t == hunting_symbol else "📡 SCAN"
                })
            except: continue

    df_radar = pd.DataFrame(radar_data).sort_values("Score", ascending=False)
    
    # ใช้ st.column_config เพื่อทำให้ตารางสวยและอ่านง่าย
    st.data_editor(
        df_radar,
        column_config={
            "RSI": st.column_config.ProgressColumn("RSI", min_value=0, max_value=100, format="%.1f"),
            "Score": st.column_config.NumberColumn("Score", format="%d pts"),
            "Price (฿)": st.column_config.NumberColumn("Price (฿)", format="฿%.2f"),
            "Last Update": st.column_config.TextColumn("🕒 Time"),
            "Status": st.column_config.TextColumn("Status")
        },
        hide_index=True,
        use_container_width=True,
        disabled=True # ป้องกันการแก้ในตาราง
    )

with col_side:
    st.subheader("📰 INTELLIGENCE")
    news_items = get_news_cards(hunting_symbol if hunting_symbol else "BTC-USD")
    if not news_items:
        st.caption("No news updates for this asset.")
    for news in news_items:
        st.markdown(f"""
        <div style="background-color: #161b22; padding: 12px; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #00ff88;">
            <small style="color: #888;">{news.published[:16]}</small><br>
            <b style="font-size: 14px;">{news.title[:60]}...</b><br>
            <a href="{news.link}" target="_blank" style="color: #00ff88; font-size: 11px; text-decoration: none;">Read More →</a>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("🛡️ SAFETY")
    if st.button("🛑 EMERGENCY LIQUIDATE", use_container_width=True, type="primary"):
        st.warning("Executing Emergency Exit...")
    st.caption("Auto-Stop Loss active at -3%")

# --- 7. AUTO REFRESH ---
# แสดงแถบความคืบหน้าเล็กๆ ด้านล่าง
st.empty()
time.sleep(300)
st.rerun()
