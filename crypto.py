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
st.set_page_config(page_title="Blue-Chip bet", layout="wide")
st_autorefresh(interval=600 * 1000, key="auto_trade_refresh")

# --- 2. ฟังก์ชันวิเคราะห์อารมณ์ข่าว (News Sentiment) ---
def get_news_sentiment(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news: return 0
        sentiment_score = 0
        for item in news[:3]: # วิเคราะห์ 3 ข่าวล่าสุด
            analysis = TextBlob(item['title'])
            sentiment_score += analysis.sentiment.polarity
        return sentiment_score / 3
    except:
        return 0

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
        st.error("❌ ไม่สามารถเชื่อมต่อ Google Sheets ได้ กรุณาตรวจสอบชื่อไฟล์และแท็บ")
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
        
        # Scoring Logic
        score = 0
        if cur_price > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < df.iloc[-1]['RSI_14'] < 65: score += 30
        if pred_price > cur_price: score += 30
        
        # เพิ่มระบบ Sentiment ข่าว
        sentiment = get_news_sentiment(symbol)
        if sentiment < -0.1: score -= 20 # ข่าวลบ หักคะแนน
        elif sentiment > 0.1: score += 10 # ข่าวดี เพิ่มคะแนน
        
        return {"Symbol": symbol, "Price": cur_price, "Score": score, "Sentiment": sentiment}
    except: return None

# --- 5. ระบบ Trading Logic (Money Management & Reset Logic) ---
def run_auto_trade(res, sheet, current_balance):
    if not sheet or current_balance < 100: 
        return
    
    data = sheet.get_all_records()
    df_trade = pd.DataFrame(data)
    
    is_holding = False
    if not df_trade.empty:
        is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD'))
    
    # 🔵 ซื้อ: ใช้เงิน 20% ของ Balance ที่มี
    if res['Score'] >= 80 and not is_holding:
        investment = current_balance * 0.20
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # คอลัมน์: วันเวลา, เหรียญ, สถานะ, ราคาซื้อ, ราคาขาย, กำไร(%), AI_Score, Balance
        row = [now, res['Symbol'], "HOLD", res['Price'], 0, 0, res['Score'], round(current_balance, 2)]
        sheet.append_row(row)
        st.toast(f"🚀 AI เปิดไม้ {res['Symbol']} ด้วยเงิน ฿{investment:.2f}")

    # 🔴 ขาย: Take Profit / Stop Loss
    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_price = float(df_trade.loc[idx, 'ราคาซื้อ'])
        hist_bal = float(df_trade.loc[idx, 'Balance'])
        investment_val = hist_bal * 0.20 # คำนวณทุนไม้เดิม
        
        profit_pct = ((res['Price'] - entry_price) / entry_price) * 100
        
        if profit_pct >= 3.0 or profit_pct <= -2.0 or res['Score'] < 50:
            return_cash = investment_val * (1 + (profit_pct/100))
            # อัปเดต Balance ใหม่ = เงินเดิมที่เหลือ + ทุนคืนพร้อมกำไร/ขาดทุน
            new_balance = (current_balance - investment_val) + return_cash
            
            row_num = int(idx) + 2
            sheet.update_cell(row_num, 3, "SOLD")
            sheet.update_cell(row_num, 5, res['Price'])
            sheet.update_cell(row_num, 6, f"{profit_pct:.2f}%")
            sheet.update_cell(row_num, 8, round(new_balance, 2))
            st.toast(f"💰 ขาย {res['Symbol']} สรุปกำไร {profit_pct:.2f}%")

# --- 6. UI Dashboard ---
st.title("🤖Blue-chip Bet")
sheet = init_gsheet()
watch_list = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD", "DOT-USD", "LINK-USD"]

# ดึง Balance ล่าสุด
current_bal = 500.0
if sheet:
    all_records = sheet.get_all_records()
    if all_records:
        current_bal = float(all_records[-1].get('Balance', 500.0))

c1, c2 = st.columns(2)
c1.metric("เงินสดคงเหลือ (Cash)", f"฿{current_bal:,.2f}")
c2.metric("สถานะระบบ", "Running ✅" if current_bal >= 100 else "Stopped 🛑")

if current_bal < 100:
    st.error("🚨 Balance ต่ำกว่า 100 บาท ระบบหยุดเทรดอัตโนมัติ กรุณาเติมเงินใน Sheets")

# รันระบบ
progress = st.progress(0)
for idx, ticker in enumerate(watch_list):
    result = analyze_coin_ai(ticker)
    if result:
        run_auto_trade(result, sheet, current_bal)
    progress.progress((idx + 1) / len(watch_list))

st.divider()
st.subheader("📚 บันทึกการเทรดและเรียนรู้ (Trade Log)")
if sheet:
    hist = pd.DataFrame(sheet.get_all_records())
    if not hist.empty:
        st.dataframe(hist.iloc[::-1], use_container_width=True)
