import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันวิเคราะห์ข่าว ---
def get_sentiment_simple(symbol):
    try:
        time.sleep(random.uniform(0.5, 1.2))
        ticker = yf.Ticker(symbol)
        news = ticker.get_news() 
        if not news: return 0, "No recent news"
        
        pos_words = ['bullish', 'partnership', 'buy', 'gain', 'growth', 'upgrade', 'success', 'listing', 'launch', 'ai', 'pump', 'moon', 'breakout', 'ath', 'approved', 'integration', 'investment']
        neg_words = ['bearish', 'hack', 'scam', 'fud', 'ban', 'drop', 'decline', 'investigation', 'risk', 'sell', 'dump', 'crash', 'liquidated', 'whale sell', 'reject', 'exploit', 'warning']
        
        score, latest_headline = 0, "No headline found"
        for i, item in enumerate(news[:3]):
            headline = item.get('title')
            if headline:
                if i == 0: latest_headline = headline
                text = headline.lower()
                for word in pos_words:
                    if word in text: score += 5
                for word in neg_words:
                    if word in text: score -= 7
        return score, latest_headline
    except: return 0, "News Sync Error"

# --- 3. ฟังก์ชันวิเคราะห์กราฟแบบ Professional (EMA 50) ---
def analyze_coin_ai(symbol, df):
    try:
        if len(df) < 100: return None 
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        
        # อินดิเคเตอร์
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=50, append=True) # เส้นตัดสินใจหลัก
        df.ta.ema(length=200, append=True) # เส้นคุมเทรนด์ใหญ่
        df = df.dropna()
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        ema50 = float(last_row['EMA_50'].iloc[0])
        ema200 = float(last_row['EMA_200'].iloc[0])
        rsi_now = float(last_row['RSI_14'].iloc[0])
        
        score = 0
        # กรองขาลง: ต้องยืนเหนือ EMA 50 เท่านั้น
        if cur_p > ema50:
            score += 40
            if cur_p > ema200: score += 20 # คะแนนโบนัสถ้าเป็นขาขึ้นชัดเจนทั้งสั้นและยาว
        else:
            # ถ้าอยู่ใต้เส้น 50 ให้แสดงสถานะเสี่ยง
            return {"Symbol": symbol, "Price_USD": cur_p, "Score": 10, "News_Score": 0, "Headline": "Under EMA 50 (Wait)", "Last_Update": "Now"}

        if 40 < rsi_now < 65: score += 20
            
        n_score, n_headline = get_sentiment_simple(symbol)
        if n_score < 0: return None # ข่าวลบไม่เข้าเด็ดขาด
        
        score += n_score
        return {
            "Symbol": symbol, "Price_USD": cur_p, "Score": score, 
            "News_Score": n_score, "Headline": n_headline,
            "Last_Update": datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        }
    except: return None

# --- 4. เชื่อมต่อระบบข้อมูล ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

sheet = init_gsheet()
live_rate = 35.5 
df_perf, current_bal, hunting_symbol = pd.DataFrame(), 1000.0, None

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        last_row_data = df_perf.iloc[-1]
        current_bal = float(last_row_data['Balance'])
        # ตรวจสอบสถานะการถือครอง (เช็คจากแถวสุดท้ายเท่านั้น)
        if last_row_data['สถานะ'] == 'HUNTING':
            hunting_symbol = last_row_data['เหรียญ']
            entry_p_thb = float(last_row_data['ราคาซื้อ(฿)'])
            current_qty = float(last_row_data['จำนวน'])

# --- 5. UI & Radar Table ---
st.title("🦔 Pepper Hunter")
st.write(f"💰 Balance: {current_bal:,.2f} ฿ | **Strategy: Profit Only (No Stop Loss)**")

tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
status_area = st.empty()
status_area.info("📡 กำลังสอยข้อมูลตลาด...")

try:
    data = yf.download(tickers, period="7d", interval="1h", group_by='ticker', progress=False)
    for sym in tickers:
        df_h = data[sym].dropna()
        res = analyze_coin_ai(sym, df_h)
        if res: all_results.append(res)
    status_area.success(f"🔍 สแกนเสร็จสิ้นเมื่อ {datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S')}")
except: st.error("❌ การสอยข้อมูลขัดข้อง")

if all_results:
    st.subheader("📊 Radar Table")
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    st.table(scan_df[['Symbol', 'Score', 'News_Score', 'Headline', 'Last_Update']])

# --- 6. ตัดสินใจซื้อ/ขาย (Pro Logic) ---
now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

if not hunting_symbol:
    # เงื่อนไขการซื้อ: คะแนนต้อง 85 ขึ้นไป (เข้มงวดแบบมือโปร)
    best_pick = next((r for r in sorted(all_results, key=lambda x: x['Score'], reverse=True) if r['Score'] >= 85), None)
    if best_pick:
        buy_p_thb = best_pick['Price_USD'] * live_rate
        qty = current_bal / buy_p_thb
        row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], 
               current_bal, qty, "Pro EMA 50 Entry", "ON", best_pick['News_Score'], best_pick['Headline']]
        sheet.append_row(row)
        st.success(f"🎯 สอยเข้าพอร์ต: {best_pick['Symbol']}")
        time.sleep(2)
        st.rerun()
else:
    # กรณีถือเหรียญ: เช็คกำไร
    current_data = yf.download(hunting_symbol, period="1d", interval="1m", progress=False).iloc[-1]
    cur_p_thb = float(current_data['Close']) * live_rate
    profit_pct = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
    
    st.warning(f"📍 ถืออยู่: {hunting_symbol} | กำไรปัจจุบัน: {profit_pct:.2f}%")
    
    sell_trigger, sell_reason = False, ""
    
    # 1. ขายทำกำไรเมื่อถึงเป้า (Take Profit)
    if profit_pct >= 8.0: 
        sell_trigger, sell_reason = True, "Take Profit (Success) 🚀"
    
    # 2. ขายล็อคกำไร (Protect Profit) 
    # ถ้ากำไรเคยขึ้นไป > 2% แล้วตกลงมาเหลือ 0.5% ให้รีบขายเอาทุนคืน + กำไรนิดหน่อย (ห้ามขาดทุน)
    elif 0.5 < profit_pct < 1.0:
        current_score = next((r['Score'] for r in all_results if r['Symbol'] == hunting_symbol), 100)
        if current_score < 40: # สัญญาณอ่อนแรงลง
            sell_trigger, sell_reason = True, "Protect Capital (Small Profit) 🛡️"

    # หมายเหตุ: ลบเงื่อนไข Stop Loss ออกตามโจทย์ "ห้ามขาดทุน"

    if sell_trigger:
        new_bal = current_qty * cur_p_thb
        row = [now_str, hunting_symbol, "SOLD", entry_p_thb, cur_p_thb, f"{profit_pct:.2f}%", 0, new_bal, 0, sell_reason, "ON"]
        sheet.append_row(row)
        st.balloons()
        st.success(f"✅ ปิดงาน: {sell_reason}")
        time.sleep(5)
        st.rerun()

# --- 7. กราฟและการแสดงผล ---
st.divider()
if not df_perf.empty:
    st.subheader("📈 Balance Growth")
    st.line_chart(df_perf.set_index(df_perf.columns[0])['Balance'])

st.write("⏱️ รอสแกนรอบถัดไป (5 นาที)...")
time.sleep(300)
st.rerun()
