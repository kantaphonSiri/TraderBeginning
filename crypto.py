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
        pos_words = ['bullish', 'partnership', 'buy', 'gain', 'growth', 'upgrade', 'success', 'launch', 'ai', 'breakout']
        neg_words = ['bearish', 'hack', 'scam', 'fud', 'ban', 'drop', 'decline', 'risk', 'sell', 'crash']
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

# --- 3. ฟังก์ชันวิเคราะห์กราฟ ---
def analyze_coin_ai(symbol, df):
    try:
        if len(df) < 100: return None 
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        ema50 = float(last_row['EMA_50'].iloc[0])
        rsi_now = float(last_row['RSI_14'].iloc[0])
        
        score = 0
        status = "🟢 Bullish" if cur_p > ema50 else "🔴 Bearish"
        
        if cur_p > ema50:
            score += 50
        else:
            return {"Symbol": symbol, "Price": cur_p, "Score": 10, "RSI": round(rsi_now, 2), "Trend": "Under EMA 50", "Headline": "Wait for Trend"}

        if 40 < rsi_now < 65: score += 20
        n_score, n_headline = get_sentiment_simple(symbol)
        if n_score < 0: return None
        score += n_score

        return {
            "Symbol": symbol, "Price": round(cur_p, 4), "Score": score, 
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
current_bal, initial_bal, goal_bal = 1000.0, 1000.0, 10000.0
hunting_symbol = None

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

# ระบบเป้าหมาย (Goal)
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
with st.spinner("📡 Radar scanning..."):
    data = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
    for sym in tickers:
        df_h = data[sym].dropna()
        res = analyze_coin_ai(sym, df_h)
        if res: all_results.append(res)

if all_results:
    st.subheader("📊 Professional Radar Table")
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    # แสดงตารางให้ User ดู
    st.dataframe(scan_df, use_container_width=True)

# --- 7. การตัดสินใจ ---
now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

if not hunting_symbol:
    best_pick = next((r for r in all_results if r['Score'] >= 80), None)
    if best_pick:
        buy_p_thb = best_pick['Price'] * live_rate
        qty = current_bal / buy_p_thb
        row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], 
               current_bal, qty, "Pro Entry", "ON", 0, best_pick['Headline']]
        sheet.append_row(row)
        st.success(f"🎯 Sniper ซื้อแล้ว: {best_pick['Symbol']}")
        st.rerun()
else:
    # กรณีถือเหรียญ
    curr_data = yf.download(hunting_symbol, period="1d", interval="1m", progress=False).iloc[-1]
    cur_p_thb = float(curr_data['Close']) * live_rate
    profit_pct = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
    st.warning(f"📍 ถืออยู่: {hunting_symbol} | กำไร: {profit_pct:.2f}%")
    
    sell_trigger, sell_reason = False, ""
    if profit_pct >= 5.0: sell_trigger, sell_reason = True, "Take Profit 🚀"
    elif 0.5 < profit_pct < 1.5:
        # เช็ค Score ถ้าสัญญาณอ่อนให้รีบออก
        score_now = next((r['Score'] for r in all_results if r['Symbol'] == hunting_symbol), 100)
        if score_now < 40: sell_trigger, sell_reason = True, "Trail Stop 🛡️"

    if sell_trigger:
        new_bal = current_qty * cur_p_thb
        row = [now_str, hunting_symbol, "SOLD", entry_p_thb, cur_p_thb, f"{profit_pct:.2f}%", 0, new_bal, 0, sell_reason, "ON"]
        sheet.append_row(row)
        st.balloons()
        st.rerun()

time.sleep(300)
st.rerun()
