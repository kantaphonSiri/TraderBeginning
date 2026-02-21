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

# --- CSS ปรับแต่งความสวยงาม ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border-radius: 10px; padding: 15px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- ฟังก์ชันช่วยดึงข้อมูล ---
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

def analyze_coin_ai(symbol, df, live_rate, invest_amount):
    try:
        if len(df) < 50: return None
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=50, append=True)
        last = df.tail(1)
        price = float(last['Close'].iloc[0]) * live_rate
        ema = float(last['EMA_50'].iloc[0]) * live_rate
        rsi = float(last['RSI_14'].iloc[0])
        
        score = 60 if price > ema else 0
        if 40 < rsi < 65: score += 20
        n_score, n_head = get_sentiment_pro(symbol)
        score += n_score

        return {"Symbol": symbol, "Price_THB": price, "Score": score, "RSI": rsi, "News": n_head}
    except: return None

# --- ดึงข้อมูลพอร์ต ---
def init_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- Logic หลัก ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
last_update = now_th.strftime("%H:%M:%S")

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
    st.caption(f"Last Sync: {last_update}")
    st.divider()
    st.write("⚙️ **System Status**")
    st.success("AI Sniper: Online")
    st.info(f"THB/USD: {live_rate:.2f}")
    if st.button("🔄 Force Update"): st.rerun()

# --- 6. MAIN CONTENT ---
st.title("🛡️ Pepper Hunter Dashboard")

if hunting_symbol:
    # ดึงข้อมูลกราฟเหรียญที่ถือ
    hist = yf.download(hunting_symbol, period="1d", interval="5m", progress=False)
    hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
    cur_p = float(hist['Close'].iloc[-1]) * live_rate
    profit = ((cur_p - entry_p_thb) / entry_p_thb) * 100
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Current Asset")
        st.metric(hunting_symbol, f"{cur_p:,.2f} ฿", delta=f"{profit:.2f}%")
        st.write(f"**Entry:** {entry_p_thb:,.2f} ฿")
    
    with col2:
        st.subheader("Price Movement (24h)")
        st.line_chart(hist['Close'] * live_rate)

st.divider()

# --- 7. MARKET RADAR TABLE ---
st.subheader(f"🔍 Market Radar Table")
st.caption(f"ข้อมูล ณ เวลา {now_th.strftime('%d %b %Y - %H:%M:%S')}")

tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD"]
all_data = []

with st.spinner("🕵️ Scanning Markets..."):
    raw_data = yf.download(tickers, period="2d", interval="1h", group_by='ticker', progress=False)
    for sym in tickers:
        df_h = raw_data[sym].dropna()
        res = analyze_coin_ai(sym, df_h, live_rate, 1000.0)
        if res:
            res['Update'] = last_update
            res['Action'] = "⭐ HOLDING" if sym == hunting_symbol else "🔍 Scanning"
            all_data.append(res)

if all_data:
    df_show = pd.DataFrame(all_data).sort_values('Score', ascending=False)
    
    # ปรับแต่งตารางให้สวยงาม
    def color_status(val):
        color = '#2ecc71' if val == "⭐ HOLDING" else '#8e9aaf'
        return f'color: {color}; font-weight: bold'

    st.dataframe(df_show.style.applymap(color_status, subset=['Action'])
                 .format({"Price_THB": "{:,.2f}", "RSI": "{:.1f}", "Score": "{:.0f}"}), 
                 width='stretch')

# --- 8. LOGIC ซื้อ/ขาย ---
# (ใช้ Logic เดิมที่คุยกันไว้)

# --- 9. Countdown ---
st.write("---")
st.caption("Next automatic scan in 5 minutes...")
progress_bar = st.progress(0)
for i in range(100):
    time.sleep(0.1) # จำลองการนับ
    progress_bar.progress(i + 1)
time.sleep(290)
st.rerun()
