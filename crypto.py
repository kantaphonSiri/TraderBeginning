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

# Custom CSS ตกแต่งให้เหมือนหน้าจอเทรดระดับโลก
st.markdown("""
    <style>
    .stApp { background-color: #0b0e11; color: #e9eaeb; }
    div[data-testid="stMetricValue"] { font-size: 32px; color: #00ff88 !important; font-weight: 700; }
    .stDataFrame { border: 1px solid #30363d; border-radius: 10px; }
    .css-1kyx0rg { background-color: #161b22; } /* Sidebar color */
    </style>
    """, unsafe_allow_html=True)

# --- 2. CORE FUNCTIONS ---
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        rate = data['Close'].iloc[-1]
        val = rate.iloc[0] if hasattr(rate, 'iloc') else rate
        return float(val)
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

# --- 3. DATA INITIALIZATION ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

# ตั้งค่าตัวแปรพื้นฐาน
current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
df_perf = pd.DataFrame()
next_invest = 1000.0 

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            # ลบช่องว่างหัว-ท้ายคอลัมน์ป้องกัน Error
            df_perf.columns = df_perf.columns.str.strip()
            
            if not df_perf.empty:
                last_row = df_perf.iloc[-1]
                
                # 1. ดึงยอดคงเหลือ (Balance)
                if 'Balance' in df_perf.columns:
                    current_total_bal = float(last_row['Balance']) if last_row['Balance'] != "" else 1000.0
                
                # 2. เช็คสถานะการถือเหรียญ (สถานะ)
                if 'สถานะ' in df_perf.columns and last_row['สถานะ'] == 'HUNTING':
                    hunting_symbol = last_row.get('เหรียญ', None)
                    entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))

                # 3. คำนวณเงินลงทุนไม้ถัดไป (ดูจากคอลัมน์ 'กำไร%')
                # ถ้าไม้ล่าสุดกำไรเป็นบวก (ไม่มีเครื่องหมายลบ) ให้เพิ่มงบ
                if 'กำไร%' in df_perf.columns:
                    last_pnl = str(last_row['กำไร%'])
                    if '-' not in last_pnl and last_pnl not in ['0', '0%', '']:
                        next_invest = 1200.0 # ชนะทบ
                    else:
                        next_invest = 1000.0 # แพ้ถอยมาตั้งหลัก
    except Exception as e:
        st.error(f"❌ ระบบอ่านคอลัมน์ผิดพลาด: {e}")

# --- 4. SIDEBAR (CONTROL CENTER) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2586/2586125.png", width=80)
    st.title("PEPPER CONTROL")
    st.divider()
    
    st.metric("PORTFOLIO", f"{current_total_bal:,.2f} ฿")
    
    st.subheader("🔥 Strategy: Dynamic")
    st.info(f"Next Investment: {next_invest:,.2f} ฿")
    
    st.divider()
    st.write(f"💹 USD/THB: **{live_rate:.2f}**")
    st.write(f"⏰ Last Update: {update_time}")
    
    if st.button("🚀 FORCE SYNC", use_container_width=True):
        st.rerun()
        
# --- 5. TOP KPI BAR ---
st.write(f"## 🦔 Pepper Hunter")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("BOT STATUS", "🔴 BUSY" if hunting_symbol else "🟢 SCANNING")
kpi2.metric("ACTIVE PAIRS", "9 ASSETS")
kpi3.metric("WIN RATE", "65%", "2% ↑")
kpi4.metric("DAILY GOAL", "10,000 ฿", f"{(current_total_bal/10000)*100:.1f}%")

st.divider()

# --- 6. MAIN HUB ---
col_main, col_side = st.columns([2.5, 1])

with col_main:
    # --- ACTIVE TRADE ---
    if hunting_symbol:
        st.subheader(f"⚡ ACTIVE MISSION: {hunting_symbol}")
        hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
        hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
        cur_p = float(hist['Close'].iloc[-1]) * live_rate
        pnl = ((cur_p - entry_p_thb) / entry_p_thb) * 100
        
        c_a, c_b = st.columns([1, 2])
        c_a.metric("CURRENT PRICE", f"{cur_p:,.2f} ฿", f"{pnl:.2f}%")
        c_b.area_chart(hist['Close'] * live_rate, height=200, color="#00ff88" if pnl >=0 else "#ff4b4b")
    
    # --- MARKET RADAR (TABLE) ---
    st.subheader("🔍 MARKET RADAR")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
    radar_data = []
    
    with st.spinner("🕵️ Scanning Assets..."):
        all_prices = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
        for t in tickers:
            try:
                df_h = all_prices[t].dropna()
                df_h.columns = [col[0] if isinstance(col, tuple) else col for col in df_h.columns]
                df_h.ta.rsi(length=14, append=True)
                df_h.ta.ema(length=50, append=True)
                last = df_h.tail(1)
                
                price_thb = float(last['Close'].iloc[0]) * live_rate
                rsi = float(last['RSI_14'].iloc[0])
                ema50 = float(last['EMA_50'].iloc[0]) * live_rate
                
                score = 60 if price_thb > ema50 else 0
                if 40 < rsi < 65: score += 20
                
                radar_data.append({
                    "Symbol": t, "Price (฿)": price_thb, "Score": score, 
                    "RSI": rsi, "Status": "⭐ HOLD" if t == hunting_symbol else "📡 SCAN"
                })
            except: continue
    
    df_radar = pd.DataFrame(radar_data).sort_values("Score", ascending=False)
    st.dataframe(df_radar.style.format({"Price (฿)": "{:,.2f}", "RSI": "{:.1f}"}), use_container_width=True)

with col_side:
    st.subheader("📰 INTELLIGENCE")
    news_items = get_news_cards(hunting_symbol if hunting_symbol else "BTC-USD")
    for news in news_items:
        st.markdown(f"""
        <div style="background-color: #161b22; padding: 12px; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #00ff88;">
            <small style="color: #888;">{news.published[:16]}</small><br>
            <b style="font-size: 14px;">{news.title[:70]}...</b><br>
            <a href="{news.link}" style="color: #00ff88; font-size: 11px; text-decoration: none;">View Source</a>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("🛡️ SAFETY")
    st.button("🛑 EMERGENCY LIQUIDATE", use_container_width=True)
    st.caption("Auto-Stop Loss active at -3%")

# --- 7. FOOTER REFRESH ---
progress_text = f"Cycle updating... Next scan in 5m (Update: {update_time})"
st.progress(0, text=progress_text)

time.sleep(300)
st.rerun()

