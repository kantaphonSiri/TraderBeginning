import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
import feedparser # ต้องมั่นใจว่าติดตั้งตัวนี้แล้ว (pip install feedparser)
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันวิเคราะห์ข่าว (อัปเกรดเป็น RSS Feed) ---
def get_sentiment_pro(symbol):
    try:
        # ดึงข่าวจาก RSS Feed ของ NewsBTC เจาะจงรายเหรียญ
        coin_name = symbol.split('-')[0].lower()
        feed_url = f"https://www.newsbtc.com/search/{coin_name}/feed/"
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            return 0, "No live news found"
            
        pos_words = ['bullish', 'breakout', 'gain', 'support', 'surge', 'rally', 'buy', 'growth', 'upgrade']
        neg_words = ['bearish', 'drop', 'decline', 'risk', 'sell', 'crash', 'hack', 'scam', 'ban']
        
        score = 0
        latest_headline = feed.entries[0].title
        
        # วิเคราะห์ 3 หัวข้อข่าวล่าสุด
        for entry in feed.entries[:3]:
            text = entry.title.lower()
            for word in pos_words:
                if word in text: score += 10 # ให้คะแนนข่าวที่มีผลต่อราคา
            for word in neg_words:
                if word in text: score -= 15 # ข่าวลบหักคะแนนหนักกว่า
                
        return score, latest_headline
    except:
        return 0, "News Feed Offline"

# --- 3. ฟังก์ชันวิเคราะห์กราฟ (EMA 50 + RSI เป็นหลัก) ---
def analyze_coin_ai(symbol, df, live_rate):
    try:
        if len(df) < 100: return None 
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        last_row = df.iloc[[-1]]
        cur_p_thb = float(last_row['Close'].iloc[0]) * live_rate
        ema50_thb = float(last_row['EMA_50'].iloc[0]) * live_rate
        rsi_now = float(last_row['RSI_14'].iloc[0])
        
        score = 0
        status = "🟢 Bullish" if cur_p_thb > ema50_thb else "🔴 Bearish"
        
        # กฎมือโปร: กราฟยืนเหนือ EMA 50 ให้ไปเลย 60 แต้ม
        if cur_p_thb > ema50_thb:
            score += 60
        else:
            return {"Symbol": symbol, "Price (THB)": cur_p_thb, "Score": 10, "RSI": round(rsi_now, 2), "Trend": "Bearish", "Headline": "Wait for Trend"}

        # กฎมือโปร: RSI โซนเก็บของ ให้เพิ่มอีก 20 แต้ม (รวมเป็น 80 พร้อมซื้อ!)
        if 40 < rsi_now < 68: 
            score += 20
            
        # เสริมพลังด้วยข่าว (วิธีที่ 3)
        n_score, n_headline = get_sentiment_pro(symbol)
        score += n_score # ถ้ามีข่าวบวก คะแนนจะทะลุ 90-100

        return {
            "Symbol": symbol, "Price (THB)": cur_p_thb, "Score": score, 
            "RSI": round(rsi_now, 2), "Trend": status, "Headline": n_headline
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

# --- 5. UI: Dashboard & Goal ---
st.title("🦔 Pepper Hunter")
col_g1, col_g2 = st.columns([1, 3])
with col_g1:
    st.metric("Current Balance", f"{current_bal:,.2f} ฿")
with col_g2:
    progress = min(current_bal / goal_bal, 1.0)
    st.write(f"🎯 **Goal: 10,000 ฿** (Progress: {progress*100:.2f}%)")
    st.progress(progress)

st.divider()

# --- 6. สแกน & Table ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
with st.spinner("📡 Radar scanning with Pro News..."):
    data = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
    for sym in tickers:
        df_h = data[sym].dropna()
        res = analyze_coin_ai(sym, df_h, live_rate)
        if res: all_results.append(res)

if all_results:
    st.subheader("📊 Radar Table")
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    st.dataframe(scan_df.style.format({"Price (THB)": "{:,.2f}"}), use_container_width=True)

# --- 7. การตัดสินใจ ---
now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

if not hunting_symbol:
    # ซื้อเมื่อ 80 คะแนน (กราฟสมบูรณ์)
    best_pick = next((r for r in all_results if r['Score'] >= 80), None)
    if best_pick:
        buy_p_thb = best_pick['Price (THB)']
        qty = current_bal / buy_p_thb
        row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], 
               current_bal, qty, "v3 RSS Entry", "ON", 0, best_pick['Headline']]
        sheet.append_row(row)
        st.success(f"🎯 Pepper ซื้อแล้ว: {best_pick['Symbol']} ({buy_p_thb:,.2f} ฿)")
        st.rerun()
else:
    # Logic ขาย (เหมือนเดิมแต่แม่นยำขึ้น)
    curr_data = yf.download(hunting_symbol, period="1d", interval="1m", progress=False).iloc[-1]
    cur_p_thb = float(curr_data['Close']) * live_rate
    profit_pct = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
    st.warning(f"📍 ถืออยู่: {hunting_symbol} | กำไร: {profit_pct:.2f}%")
    
    sell_trigger, sell_reason = False, ""
    if profit_pct >= 5.0: sell_trigger, sell_reason = True, "Take Profit 🚀"
    elif 0.5 < profit_pct < 1.5:
        score_now = next((r['Score'] for r in all_results if r['Symbol'] == hunting_symbol), 100)
        if score_now < 40: sell_trigger, sell_reason = True, "Trend Exit 🛡️"

    if sell_trigger:
        new_bal = current_qty * cur_p_thb
        row = [now_str, hunting_symbol, "SOLD", entry_p_thb, cur_p_thb, f"{profit_pct:.2f}%", 0, new_bal, 0, sell_reason, "ON"]
        sheet.append_row(row)
        st.balloons()
        st.rerun()

# --- 8. กราฟพอร์ตโฟลิโอ ---
st.divider()
if not df_perf.empty:
    st.subheader("📈 Portfolio Growth Path")
    try:
        # ใช้ Column วันที่จาก Sheet ของคุณ
        chart_data = df_perf[['วันที่', 'Balance']].copy()
        chart_data['Goal'] = 10000
        chart_data = chart_data.set_index('วันที่')
        st.line_chart(chart_data)
    except:
        st.info("📊 กำลังรอข้อมูลประวัติเพื่อแสดงกราฟ...")

time.sleep(300)
st.rerun()
