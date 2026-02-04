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
from datetime import datetime, timedelta, timezone

# --- 1. การตั้งค่าหน้าจอ (Update Streamlit 2026 Syntax) ---
st.set_page_config(page_title="Pepper Hunter - 2026 Ready", layout="wide")

# --- 2. Shared Global State ---
@st.cache_resource
def get_global_state():
    return {
        "bot_active": False,
        "last_scan": "รอกระบวนการสแกนรอบแรก...",
        "current_score": 0,
        "current_ticker": "N/A",
        "status_msg": "พร้อมทำงาน"
    }

global_state = get_global_state()

# --- 3. ฟังก์ชันสนับสนุน (Updated Tickers & UTC) ---

def get_top_30_tickers():
    # แก้ไขตัวที่โดนเปลี่ยนชื่อ: MATIC -> POL, RNDR -> RENDER
    return [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "LINK-USD", "AVAX-USD",
        "POL-USD", "TRX-USD", "SHIB-USD", "LTC-USD", "BCH-USD", "UNI-USD", "NEAR-USD", "APT-USD", "DAI-USD",
        "STX-USD", "FIL-USD", "ARB-USD", "ETC-USD", "IMX-USD", "FTM-USD", "RENDER-USD", "SUI-USD", "OP-USD", "PEPE-USD", "HBAR-USD"
    ]

@st.cache_data(ttl=60)
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

def analyze_coin_ai(symbol, df_history):
    try:
        if df_history.empty or len(df_history) < 30: return None
        df = df_history.copy()
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        if df.empty: return None
        
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42).fit(X, y)
        
        cur_price_usd = float(df.iloc[-1]['Close'])
        last_features = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[[-1]]
        pred_price_usd = model.predict(last_features)[0]
        
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
    
    # Update to timezone-aware UTC
    now_th = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime("%H:%M:%S %d-%m-%Y")
    
    if res['Score'] >= 80 and not is_holding and current_count < 3:
        inv = total_balance * 0.20
        row = [now_th, res['Symbol'], "HOLD", round(price_thb, 4), 0, 0, res['Score'], round(total_balance, 2), round(inv/price_thb, 6), res['Headline']]
        sheet.append_row(row)
        st.toast(f"🚀 ซื้อ {res['Symbol']}")
    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_p = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
        p_pct = ((price_thb - entry_p) / entry_p) * 100
        if p_pct >= 3.0 or p_pct <= -2.0 or res['Score'] < 50:
            new_bal = (total_balance - (float(df_trade.loc[idx, 'Balance']) * 0.20)) + (float(df_trade.loc[idx, 'Balance']) * 0.20 * (1 + (p_pct/100)))
            sheet.update_cell(int(idx)+2, 3, "SOLD")
            sheet.update_cell(int(idx)+2, 5, round(price_thb, 4))
            sheet.update_cell(int(idx)+2, 6, f"{p_pct:.2f}%")
            sheet.update_cell(int(idx)+2, 8, round(new_bal, 2))
            st.toast(f"💰 ขาย {res['Symbol']}")

# --- 4. UI Setup ---
sheet = init_gsheet()
df_perf = pd.DataFrame()
sheet_bal = 0.0

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        sheet_bal = float(df_perf.iloc[-1]['Balance'])

with st.sidebar:
    st.header("⚙️ ตั้งค่า Pepper")
    init_val = sheet_bal if sheet_bal > 0 else 500.0
    user_capital = st.number_input("💰 ทุนที่ต้องการใช้ (บาท)", value=init_val, step=100.0)
    user_target = st.number_input("🎯 เป้าหมายกำไร (บาท)", value=10000.0, step=1000.0)
    st.divider()
    if st.button("♻️ รีเฟรชข้อมูล (Sync)"): st.rerun()

total_bal = user_capital
st.title("🦔 Pepper Hunter")

c_b1, c_b2 = st.columns(2)
if c_b1.button("▶️ เริ่มการทำงาน (Global Start)"):
    global_state["bot_active"] = True
    global_state["status_msg"] = "กำลังเริ่มดึงข้อมูลตลาด..."
if c_b2.button("🛑 หยุดการทำงาน (Global Stop)"):
    global_state["bot_active"] = False

if global_state["bot_active"]:
    st.success(f"🔥 {global_state['status_msg']} | รอบล่าสุด: {global_state['last_scan']}")
else:
    st.warning("💤 บอทปิดอยู่")

# --- Dashboard Metrics ---
locked_money = 0.0
if not df_perf.empty:
    locked_money = sum(df_perf[df_perf['สถานะ'] == 'HOLD']['Balance'].astype(float) * 0.20)

m1, m2, m3 = st.columns(3)
m1.metric("เงินสดใช้ได้", f"฿{total_bal - locked_money:,.2f}")
m2.metric("เงินที่ลงทุนอยู่", f"฿{locked_money:,.2f}")
m3.metric("พอร์ตสุทธิ", f"฿{total_bal:,.2f}", delta=f"{total_bal - sheet_bal:,.2f}" if sheet_bal > 0 else None)

# --- 5. Visualizations ---
st.divider()
col_g1, col_g2 = st.columns([1, 2])
with col_g1:
    st.subheader("🦔 Pepper Confidence")
    fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=global_state["current_score"],
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#00FFCC"}},
        title={'text': f"LATEST: {global_state['current_ticker']}"}))
    st.plotly_chart(fig_gauge, width='stretch')
with col_g2:
    st.subheader("📈 Equity Curve")
    if not df_perf.empty:
        fig_line = px.line(df_perf, x=df_perf.index, y='Balance', template="plotly_dark")
        fig_line.update_traces(line_color='#00FFCC', line_width=3)
        st.plotly_chart(fig_line, width='stretch')

# --- 6. Background Loop (Updated Syntax) ---
if global_state["bot_active"]:
    live_thb = get_live_thb_rate()
    all_tickers = get_top_30_tickers()
    status_placeholder = st.empty()
    
    try:
        # Batch Download พร้อมจัดการ error ถ้าบางตัวไม่มีข้อมูล
        raw_data = yf.download(all_tickers, period="60d", interval="1h", progress=False, group_by='ticker')
        
        for ticker in all_tickers:
            status_placeholder.write(f"🧠 วิเคราะห์: {ticker}")
            try:
                # ดึงข้อมูลแบบรายตัวจากก้อน Batch
                ticker_df = raw_data[ticker].copy()
                if ticker_df.empty or 'Close' not in ticker_df.columns:
                    continue
                
                res = analyze_coin_ai(ticker, ticker_df)
                if res:
                    global_state["current_score"] = res['Score']
                    global_state["current_ticker"] = res['Symbol']
                    if res['Price_USD'] * live_thb <= total_bal:
                        run_auto_trade(res, sheet, total_bal, live_thb)
            except:
                continue
                
        global_state["last_scan"] = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        global_state["status_msg"] = "สแกนครบถ้วน พักเครื่อง 10 นาที"
        time.sleep(600)
        st.rerun()
        
    except Exception as e:
        st.error(f"System Error: {e}")
        time.sleep(60)
        st.rerun()

st.divider()
if not df_perf.empty: st.dataframe(df_perf.iloc[::-1], width='stretch')
