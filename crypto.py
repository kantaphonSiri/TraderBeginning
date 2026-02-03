import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from textblob import TextBlob

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="Blue-Chip Bet", layout="wide")
st_autorefresh(interval=600 * 1000, key="auto_trade_refresh")

# --- 2. ฟังก์ชันวิเคราะห์อารมณ์ข่าว ---
def get_news_sentiment(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news: return 0
        sentiment_score = 0
        for item in news[:3]:
            analysis = TextBlob(item['title'])
            sentiment_score += analysis.sentiment.polarity
        return sentiment_score / 3
    except: return 0

# --- 3. ฟังก์ชันเชื่อมต่อ Google Sheets ---
def init_gsheet(sheet_name="trade_learning"):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet(sheet_name)
    except:
        st.error("❌ เชื่อมต่อ Google Sheets ไม่ได้")
        return None

# --- 4. ฟังก์ชัน AI วิเคราะห์กราฟ + ข่าว ---
@st.cache_data(ttl=300)
def analyze_coin_ai(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.ta.rsi(length=14, append=True); df.ta.ema(length=20, append=True); df.ta.ema(length=50, append=True)
        df = df.dropna()
        X, y = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1], df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42).fit(X, y)
        cur_price = float(df.iloc[-1]['Close'])
        pred_price = model.predict(df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[[-1]])[0]
        score = 0
        if cur_price > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < df.iloc[-1]['RSI_14'] < 65: score += 30
        if pred_price > cur_price: score += 30
        sentiment = get_news_sentiment(symbol)
        if sentiment < -0.1: score -= 20
        elif sentiment > 0.1: score += 10
        return {"Symbol": symbol, "Price": cur_price, "Score": score, "Sentiment": sentiment}
    except: return None

# --- 5. ระบบ Trading Logic ---
def run_auto_trade(res, sheet, current_balance):
    if not sheet or current_balance < 100: return
    data = sheet.get_all_records()
    df_trade = pd.DataFrame(data)
    is_holding = False
    if not df_trade.empty:
        is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD'))
    
    if res['Score'] >= 80 and not is_holding:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # บันทึก Balance ปัจจุบันลงไปในแถวที่ซื้อ
        row = [now, res['Symbol'], "HOLD", res['Price'], 0, 0, res['Score'], round(current_balance, 2)]
        sheet.append_row(row)
        st.toast(f"🚀 AI ซื้อ {res['Symbol']} เรียบร้อย")

    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_price = float(df_trade.loc[idx, 'ราคาซื้อ'])
        hist_bal = float(df_trade.loc[idx, 'Balance'])
        investment_val = hist_bal * 0.20 
        profit_pct = ((res['Price'] - entry_price) / entry_price) * 100
        
        if profit_pct >= 3.0 or profit_pct <= -2.0 or res['Score'] < 50:
            return_cash = investment_val * (1 + (profit_pct/100))
            new_balance = (current_balance - investment_val) + return_cash
            row_num = int(idx) + 2
            sheet.update_cell(row_num, 3, "SOLD")
            sheet.update_cell(row_num, 5, res['Price'])
            sheet.update_cell(row_num, 6, f"{profit_pct:.2f}%")
            sheet.update_cell(row_num, 8, round(new_balance, 2))
            st.toast(f"💰 ขาย {res['Symbol']} กำไร {profit_pct:.2f}%")

# --- 6. UI Dashboard (แก้ไขส่วนการคำนวณเงินสด) ---
st.title("🤖 ต้าว Pepper จัดหั้ยย ")
sheet = init_gsheet()
watch_list = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD", "DOT-USD", "LINK-USD"]

# คำนวณเงินสดที่เหลือใช้จริง
total_balance = 500.0
available_cash = 500.0

if sheet:
    all_records = sheet.get_all_records()
    if all_records:
        df_log = pd.DataFrame(all_records)
        # 1. ดึงยอด Balance ล่าสุดที่มีในระบบ
        total_balance = float(df_log.iloc[-1]['Balance'])
        
        # 2. คำนวณเงินที่ถูกล็อคไว้ในสถานะ HOLD (ไม้ละ 20%)
        hold_trades = df_log[df_log['สถานะ'] == 'HOLD']
        locked_money = 0
        for _, row in hold_trades.iterrows():
            locked_money += float(row['Balance']) * 0.20
            
        # 3. เงินสดที่เหลือ = Balance ล่าสุด - เงินที่ล็อคไว้
        available_cash = total_balance - locked_money

c1, c2, c3 = st.columns(3)
c1.metric("เงินสดที่ใช้ได้ (Cash)", f"฿{available_cash:,.2f}")
c2.metric("เงินที่ลงทุนอยู่ (In Trade)", f"฿{locked_money:,.2f}" if sheet else "฿0.00")
c3.metric("สถานะระบบ", "Running ✅" if total_balance >= 100 else "Stopped 🛑")

if total_balance < 100:
    st.error("🚨 Balance ต่ำกว่า 100 บาท ระบบหยุดเทรด")

# รันระบบ
progress = st.progress(0)
for idx, ticker in enumerate(watch_list):
    result = analyze_coin_ai(ticker)
    if result:
        # ส่งยอด available_cash เข้าไปเพื่อให้ AI รู้ว่าเหลือเงินจริงเท่าไหร่
        run_auto_trade(result, sheet, total_balance)
    progress.progress((idx + 1) / len(watch_list))

st.divider()
st.subheader("📚 บันทึกการเทรดและเรียนรู้ (Trade Log)")
if sheet:
    hist = pd.DataFrame(sheet.get_all_records())
    if not hist.empty:
        st.dataframe(hist.iloc[::-1], use_container_width=True)
