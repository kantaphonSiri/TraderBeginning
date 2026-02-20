import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันวิเคราะห์ข่าว (RSS Feed) ---
def get_sentiment_pro(symbol):
    try:
        coin_name = symbol.split('-')[0].lower()
        feed_url = f"https://www.newsbtc.com/search/{coin_name}/feed/"
        feed = feedparser.parse(feed_url)
        if not feed.entries: return 0, "No live news"
        pos_words = ['bullish', 'breakout', 'gain', 'support', 'surge', 'rally', 'buy']
        neg_words = ['bearish', 'drop', 'decline', 'risk', 'sell', 'crash']
        score, latest_headline = 0, feed.entries[0].title
        for entry in feed.entries[:3]:
            text = entry.title.lower()
            for word in pos_words:
                if word in text: score += 10
            for word in neg_words:
                if word in text: score -= 15
        return score, latest_headline
    except: return 0, "News Offline"

# --- 3. ฟังก์ชันวิเคราะห์กราฟ + ความน่าจะเป็นในการทำกำไร ---
def analyze_coin_ai(symbol, df, live_rate, current_bal):
    try:
        if len(df) < 100: return None 
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        last_row = df.iloc[[-1]]
        cur_p_usd = float(last_row['Close'].iloc[0])
        cur_p_thb = cur_p_usd * live_rate
        ema50_thb = float(last_row['EMA_50'].iloc[0]) * live_rate
        rsi_now = float(last_row['RSI_14'].iloc[0])
        vol_now = float(last_row['Volume'].iloc[0]) # เช็คแรงซื้อขาย
        
        score = 0
        if cur_p_thb > ema50_thb:
            score += 60 # เทรนด์ขาขึ้นแรงๆ
        else: return None

        if 40 < rsi_now < 65: score += 20 # โซนกำลังดี ไม่ดอย
        
        # เพิ่มคะแนนพิเศษสำหรับเหรียญที่มี Volume หนาแน่น (มีแนวโน้มวิ่งแรง)
        if vol_now > df['Volume'].mean(): score += 5 

        n_score, n_headline = get_sentiment_pro(symbol)
        score += n_score

        # คำนวณจำนวนที่จะได้รับจากงบที่มี
        est_qty = current_bal / cur_p_thb

        return {
            "Symbol": symbol,
            "Market Price (฿)": cur_p_thb,
            "Your Investment (฿)": current_bal,
            "You will Get (Qty)": est_qty,
            "Score": score,
            "Trend": "🟢 Bullish",
            "News": n_headline
        }
    except: return None

# --- 4. ดึงข้อมูลพอร์ต ---
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
current_bal, goal_bal = 1000.0, 10000.0
hunting_symbol, df_perf = None, pd.DataFrame()

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        last_row = df_perf.iloc[-1]
        current_bal = float(last_row['Balance'])
        if last_row['สถานะ'] == 'HUNTING':
            hunting_symbol = last_row['เหรียญ']
            entry_p_thb = float(last_row['ราคาซื้อ(฿)'])
            current_qty = float(last_row['จำนวน'])

# --- 5. UI: Dashboard ---
st.title("🦔 Pepper Hunter")
c1, c2 = st.columns([1, 3])
with c1: st.metric("เงินในมือ", f"{current_bal:,.2f} ฿")
with c2:
    prog = min(current_bal / goal_bal, 1.0)
    st.write(f"🎯 **เป้าหมาย: 10,000 ฿** ({prog*100:.1f}%)")
    st.progress(prog)

st.divider()

# --- 6. สแกน & ตารางวิเคราะห์ (Table) ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
with st.spinner("🕵️ Pepper กำลังวิเคราะห์หาตัวทำกำไร..."):
    data = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
    for sym in tickers:
        df_h = data[sym].dropna()
        res = analyze_coin_ai(sym, df_h, live_rate, current_bal)
        if res: all_results.append(res)

if all_results:
    st.subheader("📊 ตารางวิเคราะห์โอกาสทำกำไร")
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    
    # แสดงตารางให้ User เข้าใจง่าย
    st.dataframe(scan_df.style.format({
        "Market Price (฿)": "{:,.2f}",
        "Your Investment (฿)": "{:,.2f}",
        "You will Get (Qty)": "{:.6f}",
        "Score": "{:.0f}"
    }), use_container_width=True)

# --- 7. การตัดสินใจซื้อ (เลือกตัวที่ Best ที่สุด) ---
# --- 7. การตัดสินใจซื้อ (ฉบับแก้ไข Error JSON) ---
now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

if not hunting_symbol and all_results:
    best_coin = scan_df.iloc[0] 
    if best_coin['Score'] >= 80:
        # บังคับแปลงค่าทุกอย่างให้เป็น Type พื้นฐานที่ Google Sheet รับได้
        row = [
            str(now_str),                               # วันเวลา (String)
            str(best_coin['Symbol']),                  # ชื่อเหรียญ (String)
            "HUNTING",                                  # สถานะ (String)
            float(best_coin['Market Price (฿)']),     # ราคาซื้อ (Float)
            0.0,                                        # ราคาขายเริ่มต้น (Float)
            "0%",                                       # กำไร (String)
            int(best_coin['Score']),                   # คะแนน (Int)
            float(current_bal),                         # ยอดเงิน (Float)
            float(best_coin['You will Get (Qty)']),    # จำนวนเหรียญ (Float)
            "v3 RSS Entry",                             # หมายเหตุ (String)
            "ON",                                       # Switch (String)
            0,                                          # ลำดับ (Int)
            str(best_coin['News'])                     # ข่าว (String)
        ]
        
        try:
            sheet.append_row(row)
            st.success(f"🎯 Pepper สอยแล้ว: {best_coin['Symbol']} ({best_coin['Market Price (฿)']:,.2f} ฿)")
            st.rerun()
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดตอนบันทึกข้อมูล: {e}")

# --- 8. กราฟ ---
if not df_perf.empty:
    st.divider()
    st.subheader("📈 เส้นทางเงินหลักหมื่น")
    chart_data = df_perf[['วันที่', 'Balance']].set_index('วันที่')
    st.line_chart(chart_data)

time.sleep(300)
st.rerun()

