import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- CSS ตกแต่ง Dashboard ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1c2128; border-radius: 10px; padding: 15px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- ฟังก์ชันดึงข้อมูลพื้นฐาน ---
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        rate = data['Close'].iloc[-1]
        val = rate.iloc[0] if hasattr(rate, 'iloc') else rate
        return float(val)
    except: return 35.5

def get_sentiment_pro(symbol):
    try:
        coin_name = symbol.split('-')[0].lower()
        feed = feedparser.parse(f"https://www.newsbtc.com/search/{coin_name}/feed/")
        if not feed.entries: return 0, "No news"
        score = 0
        for entry in feed.entries[:3]:
            text = entry.title.lower()
            if any(w in text for w in ['bull', 'breakout', 'surge', 'buy']): score += 10
            if any(w in text for w in ['bear', 'drop', 'crash', 'sell']): score -= 15
        return score, feed.entries[0].title
    except: return 0, "News Offline"

# --- เชื่อมต่อ Google Sheets ---
def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- โหลดข้อมูลเบื้องต้น ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
df_perf = pd.DataFrame()

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        df_perf['Balance'] = pd.to_numeric(df_perf['Balance'], errors='coerce')
        last_row = df_perf.iloc[-1]
        current_total_bal = float(last_row['Balance'])
        if last_row['สถานะ'] == 'HUNTING':
            hunting_symbol = last_row['เหรียญ']
            entry_p_thb = float(last_row['ราคาซื้อ(฿)'])

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🦔 Pepper Hunter")
    st.metric("Total Balance", f"{current_total_bal:,.2f} ฿")
    st.write(f"🕒 **Last Sync:** {update_time}")
    st.divider()
    st.info(f"💵 1 USD = {live_rate:.2f} THB")
    if st.button("🔄 Force Update"): st.rerun()

# --- 6. MAIN CONTENT ---
st.title("🛡️ Pepper Hunter Pro Dashboard")

# ส่วนแสดงข้อมูลเหรียญที่ถืออยู่ พร้อมกราฟ
if hunting_symbol:
    hist = yf.download(hunting_symbol, period="1d", interval="5m", progress=False)
    hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
    cur_p = float(hist['Close'].iloc[-1]) * live_rate
    profit = ((cur_p - entry_p_thb) / entry_p_thb) * 100
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("🔥 Active Asset")
        st.metric(hunting_symbol, f"{cur_p:,.2f} ฿", delta=f"{profit:.2f}%")
        st.write(f"**Entry:** {entry_p_thb:,.2f} ฿")
        st.write(f"**Status:** 🚀 Hunting in progress...")
    
    with col2:
        st.line_chart(hist['Close'] * live_rate, color="#2ecc71")

st.divider()

# --- 7. MARKET RADAR TABLE (ตารางถาวร) ---
st.subheader("🔍 Market Radar & Analysis")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD"]
radar_list = []

with st.spinner("🕵️ Scanning Markets..."):
    # ดึงข้อมูลรวดเดียว
    raw_data = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
    
    for sym in tickers:
        try:
            df_h = raw_data[sym].dropna()
            df_h.columns = [col[0] if isinstance(col, tuple) else col for col in df_h.columns]
            
            # คำนวณ RSI & EMA แบบย่อ
            df_h.ta.rsi(length=14, append=True)
            df_h.ta.ema(length=50, append=True)
            last = df_h.tail(1)
            
            p_usd = float(last['Close'].iloc[0])
            p_thb = p_usd * live_rate
            ema_thb = float(last['EMA_50'].iloc[0]) * live_rate
            rsi = float(last['RSI_14'].iloc[0])
            
            # คำนวณ Score
            score = 60 if p_thb > ema_thb else 0
            if 40 < rsi < 65: score += 20
            n_score, n_head = get_sentiment_pro(sym)
            score += n_score
            
            radar_list.append({
                "Symbol": sym,
                "Price (฿)": p_thb,
                "Score": score,
                "RSI": rsi,
                "Status": "⭐ HOLDING" if sym == hunting_symbol else "🔍 SCANNING",
                "Last Update": update_time
            })
        except: continue

if radar_list:
    df_radar = pd.DataFrame(radar_list).sort_values('Score', ascending=False)
    
    # ใส่สีให้สถานะ
    def style_status(val):
        color = '#2ecc71' if val == "⭐ HOLDING" else '#8e9aaf'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_radar.style.applymap(style_status, subset=['Status'])
        .format({"Price (฿)": "{:,.2f}", "RSI": "{:.1f}", "Score": "{:.0f}"}),
        width="stretch"
    )

# --- 8. LOGIC การเทรด (Dynamic) ---
# ส่วนนี้จะทำงานเบื้องหลังเพื่อเช็คจุด TP/SL และการซื้อใหม่
# (ใส่โค้ด logic เดิมที่เจ้านายมีอยู่ได้เลย)

# --- 9. AUTO REFRESH ---
st.divider()
st.caption(f"System will auto-refresh every 5 minutes. Current time: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
