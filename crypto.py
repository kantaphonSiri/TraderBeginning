import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from textblob import TextBlob
from datetime import datetime, timedelta

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันดึงรายชื่อเหรียญ Blue-chip แบบ Dynamic & Budget-Friendly (NO FIX CODE) ---
def get_blue_chip_list(max_price_thb=500):
    try:
        # ดึงรายชื่อกลุ่มผู้นำตลาดอัตโนมัติ (Seed List)
        seed_tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "LINK-USD", "AVAX-USD"]
        
        # ดึงราคาปัจจุบันมาเช็ค
        data = yf.download(seed_tickers, period="1d", interval="1m", progress=False)['Close']
        live_rate = get_live_thb_rate()
        
        budget_friendly_list = []
        for ticker in seed_tickers:
            if ticker in data.columns:
                price_thb = data[ticker].iloc[-1] * live_rate
                # เลือกเฉพาะเหรียญที่เงิน 500 บาทซื้อได้เป็นชิ้นเป็นอัน
                if price_thb <= max_price_thb:
                    budget_friendly_list.append(ticker)
        return budget_friendly_list
    except:
        return ["XRP-USD", "ADA-USD", "DOGE-USD"]

# --- 3. ฟังก์ชันดึงอัตราแลกเปลี่ยน ---
def get_live_thb_rate():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1]) if not data.empty else 35.5
    except: return 35.5

# --- 4. ฟังก์ชันวิเคราะห์ข่าว ---
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
    except: return 0, "ดึงข้อมูลข่าวไม่ได้"

# --- 5. ฟังก์ชันเชื่อมต่อ Google Sheets ---
def init_gsheet(sheet_name="trade_learning"):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet(sheet_name)
    except: return None

# --- 6. ฟังก์ชัน AI วิเคราะห์กราฟ (Anti-Ban Cache) ---
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
        sentiment, headline = get_news_data(symbol)
        if sentiment < -0.1: score -= 20
        elif sentiment > 0.1: score += 10
        return {"Symbol": symbol, "Price_USD": cur_price_usd, "Score": score, "Headline": headline}
    except: return None

# --- 7. ระบบ Trading Logic ---
def run_auto_trade(res, sheet, total_balance, live_rate):
    if not sheet or total_balance < 100: return
    data = sheet.get_all_records()
    df_trade = pd.DataFrame(data)
    is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')) if not df_trade.empty else False
    current_holding_count = len(df_trade[df_trade['สถานะ'] == 'HOLD']) if not df_trade.empty else 0
    price_thb = res['Price_USD'] * live_rate

    if res['Score'] >= 80 and not is_holding and current_holding_count < 3:
        investment_thb = total_balance * 0.20
        coin_amount = investment_thb / price_thb
        now = (datetime.utcnow() + timedelta(hours=7)).strftime("%H:%M:%S %d-%m-%Y")
        row = [now, res['Symbol'], "HOLD", round(price_thb, 4), 0, 0, res['Score'], round(total_balance, 2), round(coin_amount, 6), res['Headline']]
        sheet.append_row(row)
        st.toast(f"🚀 ซื้อ {res['Symbol']}")
    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_price_thb = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
        hist_bal = float(df_trade.loc[idx, 'Balance'])
        profit_pct = ((price_thb - entry_price_thb) / entry_price_thb) * 100
        if profit_pct >= 3.0 or profit_pct <= -2.0 or res['Score'] < 50:
            new_balance = (total_balance - (hist_bal * 0.20)) + (hist_bal * 0.20 * (1 + (profit_pct/100)))
            row_num = int(idx) + 2
            sheet.update_cell(row_num, 3, "SOLD"); sheet.update_cell(row_num, 5, round(price_thb, 4))
            sheet.update_cell(row_num, 6, f"{profit_pct:.2f}%"); sheet.update_cell(row_num, 8, round(new_balance, 2))
            st.toast(f"💰 ขาย {res['Symbol']}")

# --- 8. UI & Sidebar Setup ---
with st.sidebar:
    st.header("⚙️ ตั้งค่า Pepper")
    user_capital = st.number_input("💰 ทุนเริ่มต้น (บาท)", value=500.0, step=100.0)
    user_target = st.number_input("🎯 เป้าหมายกำไร (บาท)", value=1000.0, step=100.0)
    st.divider()
    if st.button("♻️ Refresh Dashboard"): st.rerun()

st.title("🦔 Pepper - The Persistent Hunter")

# บันทึกสถานะบอทใน Session State
if "bot_active" not in st.session_state: st.session_state.bot_active = False

c_btn1, c_btn2 = st.columns(2)
if c_btn1.button("▶️ เริ่มการทำงาน (Start Bot)"): st.session_state.bot_active = True
if c_btn2.button("🛑 หยุดการทำงาน (Stop Bot)"): st.session_state.bot_active = False

sheet = init_gsheet()
live_thb = get_live_thb_rate()
watch_list = get_blue_chip_list(max_price_thb=user_capital)

# แสดงเหรียญที่ระบบเลือก
st.info(f"🎯 Blue-chips ที่งบพี่ซื้อได้: {' | '.join(watch_list)}")

total_bal, locked_money = user_capital, 0.0
if sheet:
    all_recs = sheet.get_all_records()
    if all_recs:
        df_log = pd.DataFrame(all_recs)
        total_bal = float(df_log.iloc[-1]['Balance'])
        locked_money = sum(df_log[df_log['สถานะ'] == 'HOLD']['Balance'].astype(float) * 0.20)

c1, c2, c3 = st.columns(3)
c1.metric("Cash", f"฿{total_bal - locked_money:,.2f}")
c2.metric("In Trade", f"฿{locked_money:,.2f}")
c3.metric("Equity", f"฿{total_bal:,.2f}", delta=f"{total_bal - user_capital:,.2f}")

# Progress Bar ไปสู่เป้าหมาย
progress = min((total_bal / user_target), 1.0)
st.write(f"📈 ความคืบหน้าสู่เป้าหมาย {user_target}฿: {progress*100:.1f}%")
st.progress(progress)

if total_bal >= user_target:
    st.balloons(); st.success("🎉 ถึงเป้าหมายแล้ว!")

# --- 9. Background Loop ---
if st.session_state.bot_active:
    st.success("🔥 บอทกำลังรันต่อเนื่อง... (คุณสามารถปิดหน้าจอนี้ได้ ข้อมูลจะซิงค์ผ่าน Sheet)")
    while st.session_state.bot_active:
        ph = st.empty()
        for ticker in watch_list:
            ph.write(f"⏳ กำลังวิเคราะห์: {ticker}...")
            res = analyze_coin_ai(ticker)
            if res: run_auto_trade(res, sheet, total_bal, live_thb)
            time.sleep(2) # Anti-Ban delay
        time.sleep(600)
        st.rerun()
else:
    st.warning("💤 บอทปิดอยู่")

st.divider()
if sheet:
    hist = pd.DataFrame(sheet.get_all_records())
    if not hist.empty: st.dataframe(hist.iloc[::-1], use_container_width=True)
