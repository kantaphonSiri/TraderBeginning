import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from textblob import TextBlob
from datetime import datetime, timedelta

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

# --- [ฟังก์ชัน 2-7 เหมือนเดิมที่พี่มี แต่แนะนำให้คงไว้ตามนี้เพื่อความเสถียร] ---

def get_blue_chip_list(max_price_thb=500):
    try:
        seed_tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "LINK-USD", "AVAX-USD"]
        data = yf.download(seed_tickers, period="1d", interval="1m", progress=False)['Close']
        live_rate = get_live_thb_rate()
        budget_friendly_list = []
        for ticker in seed_tickers:
            if ticker in data.columns:
                price_thb = data[ticker].iloc[-1] * live_rate
                if price_thb <= max_price_thb:
                    budget_friendly_list.append(ticker)
        return budget_friendly_list
    except: return ["XRP-USD", "ADA-USD", "DOGE-USD"]

def get_live_thb_rate():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1]) if not data.empty else 35.5
    except: return 35.5

def get_news_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news: return 0, "ไม่มีข่าวใหม่"
        sentiment_score = 0
        headline = news[0]['title']
        for item in news[:3]:
            sentiment_score += TextBlob(item['title']).sentiment.polarity
        return (sentiment_score / 3), headline
    except: return 0, "ดึงข่าวไม่ได้"

def init_gsheet(sheet_name="trade_learning"):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet(sheet_name)
    except: return None

@st.cache_data(ttl=600)
def analyze_coin_ai(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.ta.rsi(length=14, append=True); df.ta.ema(length=20, append=True); df.ta.ema(length=50, append=True)
        df = df.dropna()
        X, y = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1], df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42).fit(X, y)
        cur_price_usd = float(df.iloc[-1]['Close'])
        pred_price_usd = model.predict(df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[[-1]])[0]
        score = 0
        if cur_price_usd > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < df.iloc[-1]['RSI_14'] < 65: score += 30
        if pred_price_usd > cur_price_usd: score += 30
        sent, head = get_news_data(symbol)
        if sent < -0.1: score -= 20
        elif sent > 0.1: score += 10
        return {"Symbol": symbol, "Price_USD": cur_price_usd, "Score": score, "Headline": head}
    except: return None

def run_auto_trade(res, sheet, total_balance, live_rate):
    if not sheet or total_balance < 100: return
    data = sheet.get_all_records()
    df_trade = pd.DataFrame(data)
    is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')) if not df_trade.empty else False
    current_count = len(df_trade[df_trade['สถานะ'] == 'HOLD']) if not df_trade.empty else 0
    price_thb = res['Price_USD'] * live_rate
    if res['Score'] >= 80 and not is_holding and current_count < 3:
        inv = total_balance * 0.20
        row = [(datetime.utcnow() + timedelta(hours=7)).strftime("%H:%M:%S %d-%m-%Y"), res['Symbol'], "HOLD", round(price_thb, 4), 0, 0, res['Score'], round(total_balance, 2), round(inv/price_thb, 6), res['Headline']]
        sheet.append_row(row)
        st.toast(f"🚀 ซื้อ {res['Symbol']}")
    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_p = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
        p_pct = ((price_thb - entry_p) / entry_p) * 100
        if p_pct >= 3.0 or p_pct <= -2.0 or res['Score'] < 50:
            new_bal = (total_balance - (float(df_trade.loc[idx, 'Balance']) * 0.20)) + (float(df_trade.loc[idx, 'Balance']) * 0.20 * (1 + (p_pct/100)))
            sheet.update_cell(int(idx)+2, 3, "SOLD"); sheet.update_cell(int(idx)+2, 5, round(price_thb, 4))
            sheet.update_cell(int(idx)+2, 6, f"{p_pct:.2f}%"); sheet.update_cell(int(idx)+2, 8, round(new_bal, 2))
            st.toast(f"💰 ขาย {res['Symbol']}")

# --- 8. UI & Sidebar ---
with st.sidebar:
    st.header("⚙️ ตั้งค่า Pepper")
    user_capital = st.number_input("💰 ทุนเริ่มต้น (บาท)", value=500.0, step=100.0)
    user_target = st.number_input("🎯 เป้าหมายกำไร (บาท)", value=1000.0, step=100.0)
    if st.button("♻️ รีเฟรชหน้าจอ"): st.rerun()

st.title("🦔 Pepper Hunter")

if "bot_active" not in st.session_state: st.session_state.bot_active = False
c_b1, c_b2 = st.columns(2)
if c_b1.button("▶️ Start Bot"): st.session_state.bot_active = True
if c_b2.button("🛑 Stop Bot"): st.session_state.bot_active = False

sheet = init_gsheet()
live_thb = get_live_thb_rate()
watch_list = get_blue_chip_list(max_price_thb=user_capital)

# --- 9. Visualizations & Metrics ---
total_bal, locked_money = user_capital, 0.0
df_perf = pd.DataFrame()

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        total_bal = float(df_perf.iloc[-1]['Balance'])
        locked_money = sum(df_perf[df_perf['สถานะ'] == 'HOLD']['Balance'].astype(float) * 0.20)

m1, m2, m3 = st.columns(3)
m1.metric("Cash", f"฿{total_bal - locked_money:,.2f}")
m2.metric("In Trade", f"฿{locked_money:,.2f}")
m3.metric("Equity", f"฿{total_bal:,.2f}", delta=f"{total_bal - user_capital:,.2f}")

st.progress(min((total_bal / user_target), 1.0))

# --- กราฟวิเคราะห์ความมั่นใจ (Confidence & Equity) ---
st.divider()
col_g1, col_g2 = st.columns([1, 2])

with col_g1:
    st.subheader("🦔 Pepper Confidence")
    # แสดงมาตรวัดความมั่นใจล่าสุด (ถ้าบอทรันอยู่)
    if st.session_state.bot_active:
        # สมมติเอาค่าเฉลี่ยความมั่นใจในพอร์ตหรือตัวล่าสุดมาโชว์
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = 80, # Placeholder
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#00FFCC"}},
            title = {'text': "Confidence Level"}
        ))
        fig_gauge.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

with col_g2:
    st.subheader("📈 Equity Curve")
    if not df_perf.empty:
        fig_line = px.line(df_perf, x=df_perf.index, y='Balance', template="plotly_dark")
        fig_line.update_traces(line_color='#00FFCC', line_width=3)
        st.plotly_chart(fig_line, use_container_width=True)

# --- 10. Background Loop ---
if st.session_state.bot_active:
    st.success("🔥 Pepper Is Hunting...")
    while st.session_state.bot_active:
        for ticker in watch_list:
            res = analyze_coin_ai(ticker)
            if res:
                run_auto_trade(res, sheet, total_bal, live_thb)
                # โชว์ความมั่นใจเรียลไทม์บนหน้าจอ
                st.toast(f"Analyzing {ticker}: Confidence {res['Score']}%")
            time.sleep(2)
        time.sleep(600)
        st.rerun()

st.divider()
st.subheader("📚 Trade History")
if not df_perf.empty: st.dataframe(df_perf.iloc[::-1], use_container_width=True)

