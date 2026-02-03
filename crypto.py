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
st.set_page_config(page_title="Blue-Chip Bet", layout="wide")

# --- 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน Real-time ---
def get_live_thb_rate():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        if not data.empty:
            return float(data['Close'].iloc[-1])
        return 35.5
    except:
        return 35.5

# --- 3. ฟังก์ชันวิเคราะห์ข่าว ---
def get_news_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news: return 0, "ไม่มีข่าวใหม่"
        sentiment_score = 0
        headline = news[0]['title']
        for item in news[:3]:
            analysis = TextBlob(item['title'])
            sentiment_score += analysis.sentiment.polarity
        return (sentiment_score / 3), headline
    except:
        return 0, "ดึงข้อมูลข่าวไม่ได้"

# --- 4. ฟังก์ชันเชื่อมต่อ Google Sheets ---
def init_gsheet(sheet_name="trade_learning"):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet(sheet_name)
    except:
        return None

# --- 5. ฟังก์ชัน AI วิเคราะห์กราฟ ---
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

# --- 6. ระบบ Trading Logic ---
# --- แก้ไขในส่วนระบบ Trading Logic ---

def run_auto_trade(res, sheet, total_balance, live_rate):
    if not sheet or total_balance < 100: return
    
    data = sheet.get_all_records()
    df_trade = pd.DataFrame(data)
    
    # 1. เช็คสถานะการถือครองของเหรียญนี้
    is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')) if not df_trade.empty else False
    
    # 2. นับจำนวนเหรียญทั้งหมดที่กำลังถืออยู่ (NEW!)
    current_holding_count = len(df_trade[df_trade['สถานะ'] == 'HOLD']) if not df_trade.empty else 0
    
    price_thb = res['Price_USD'] * live_rate

    # 🔵 LOGIC ซื้อ (เพิ่มเงื่อนไข: ต้องถือไม่เกิน 3 ตัว)
    if res['Score'] >= 80 and not is_holding:
        if current_holding_count < 3: # <--- ปิดจุดอ่อนข้อ A: จำกัดแค่ 3 ตัว
            investment_thb = total_balance * 0.20
            coin_amount = investment_thb / price_thb
            now = (datetime.utcnow() + timedelta(hours=7)).strftime("%H:%M:%S %d-%m-%Y")
            
            row = [now, res['Symbol'], "HOLD", round(price_thb, 4), 0, 0, 
                   res['Score'], round(total_balance, 2), round(coin_amount, 6), res['Headline']]
            sheet.append_row(row)
            st.toast(f"🚀 ซื้อ {res['Symbol']} ตัวที่ {current_holding_count + 1}")
        else:
            # ถ้าครบ 3 ตัวแล้ว จะไม่ซื้อเพิ่มแม้ Score จะสูง
            pass 

    # 🔴 LOGIC ขาย (เหมือนเดิม)
    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_price_thb = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
        hist_bal = float(df_trade.loc[idx, 'Balance'])
        
        profit_pct = ((price_thb - entry_price_thb) / entry_price_thb) * 100
        
        # ขายเมื่อ: กำไร 3%, ขาดทุน 2%, หรือ AI บอกว่าไม่น่ารอด (Score < 50)
        if profit_pct >= 3.0 or profit_pct <= -2.0 or res['Score'] < 50:
            investment_val = hist_bal * 0.20
            return_cash = investment_val * (1 + (profit_pct/100))
            new_balance = (total_balance - investment_val) + return_cash
            
            row_num = int(idx) + 2
            sheet.update_cell(row_num, 3, "SOLD")
            sheet.update_cell(row_num, 5, round(price_thb, 4))
            sheet.update_cell(row_num, 6, f"{profit_pct:.2f}%")
            sheet.update_cell(row_num, 8, round(new_balance, 2))
            st.toast(f"💰 ขาย {res['Symbol']} คืน Slot ให้ว่าง")

# --- 7. UI Dashboard & Background Loop ---
st.title("🦔 ต้าว Pepper จัดหั้ยย")

# สร้างที่สำหรับวางปุ่มเปิด/ปิดบอท
if "bot_active" not in st.session_state:
    st.session_state.bot_active = False

col_btn1, col_btn2 = st.columns(2)
if col_btn1.button("▶️ เริ่มการทำงาน (Start Bot)"):
    st.session_state.bot_active = True
if col_btn2.button("🛑 หยุดการทำงาน (Stop Bot)"):
    st.session_state.bot_active = False

# ส่วนแสดงผล Dashboard
sheet = init_gsheet()
live_thb = get_live_thb_rate()
watch_list = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD", "DOT-USD", "LINK-USD"]

# ดึงยอดล่าสุดมาโชว์บน UI
total_bal = 500.0
locked_money = 0.0
if sheet:
    all_recs = sheet.get_all_records()
    if all_recs:
        df_log = pd.DataFrame(all_recs)
        total_bal = float(df_log.iloc[-1]['Balance'])
        hold_trades = df_log[df_log['สถานะ'] == 'HOLD']
        for _, row in hold_trades.iterrows():
            locked_money += float(row['Balance']) * 0.20

c1, c2, c3 = st.columns(3)
c1.metric("เงินสดใช้ได้ (Cash)", f"฿{total_bal - locked_money:,.2f}")
c2.metric("เงินลงทุนอยู่ (In Trade)", f"฿{locked_money:,.2f}")
c3.metric("พอร์ตสุทธิ (Equity)", f"฿{total_bal:,.2f}")

# --- ส่วนของการทำงาน Background ---
if st.session_state.bot_active:
    st.success("🦔 ต้าว Pepper กำลังสแกนหาจังหวะเทรดอยู่...")
    
    # รัน Loop การทำงาน
    while st.session_state.bot_active:
        for ticker in watch_list:
            result = analyze_coin_ai(ticker)
            if result:
                run_auto_trade(result, sheet, total_bal, live_thb)
        
        # อัปเดต UI หลังจากสแกนครบทุกตัว
        now = (datetime.utcnow() + timedelta(hours=7)).strftime("%H:%M:%S %d-%m-%Y")
        st.write(f"✅ สแกนเสร็จสิ้นเมื่อ: {now} (กำลังรอรอบถัดไปใน 10 นาที)")
        
        # สั่งหยุดรอ 10 นาที (600 วินาที)
        time.sleep(600)
        st.rerun() # สั่งให้ Streamlit Refresh หน้าจอเพื่อดึงยอดเงินล่าสุด
else:
    st.warning("💤 บอทปิดอยู่ กดปุ่ม Start เพื่อเริ่มการทำงาน")

st.divider()
st.subheader("📚 บันทึกการเทรดล่าสุด")
if sheet:
    hist = pd.DataFrame(sheet.get_all_records())
    if not hist.empty:
        st.dataframe(hist.iloc[::-1], use_container_width=True)




