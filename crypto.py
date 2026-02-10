import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
import numpy as np
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from textblob import TextBlob
from datetime import datetime, timedelta, timezone

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="Pepper Hunter - Pro AI", layout="wide")

# --- 2. Shared Global State ---
if "bot_active" not in st.session_state:
    st.session_state.bot_active = False
if "last_scan" not in st.session_state:
    st.session_state.last_scan = "ยังไม่มีการสแกน"

# --- 3. ฟังก์ชันสนับสนุน ---

def get_top_30_tickers():
    return [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "LINK-USD", "AVAX-USD",
        "POL-USD", "TRX-USD", "SHIB-USD", "LTC-USD", "BCH-USD", "UNI-USD", "NEAR-USD", "APT-USD", "DAI-USD",
        "STX-USD", "FIL-USD", "ARB-USD", "ETC-USD", "IMX-USD", "FTM-USD", "RENDER-USD", "SUI-USD", "OP-USD", "PEPE-USD", "HBAR-USD"
    ]

def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet("trade_learning")
    except Exception as e:
        st.error(f"❌ เชื่อมต่อ Sheet ไม่ได้: {e}")
        return None

def calculate_daily_target(current_bal, goal_bal, days_left):
    if days_left <= 0 or current_bal >= goal_bal: return 0
    # สูตรดอกเบี้ยทบต้น: r = (Goal/Current)^(1/n) - 1
    daily_rate = (pow(goal_bal / current_bal, 1 / days_left) - 1)
    return daily_rate

def get_news_sentiment(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news: return 0, "No news available"
        sentiment = sum(TextBlob(n['title']).sentiment.polarity for n in news[:3]) / 3
        return sentiment, news[0]['title']
    except: return 0, "News error"

def analyze_coin_ai(symbol, df_history):
    try:
        df = df_history.copy()
        if len(df) < 50: return None
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X.values, y.values)
        
        last_row = df.iloc[[-1]]
        cur_p, rsi_val = float(last_row['Close'].iloc[0]), float(last_row['RSI_14'].iloc[0])
        ema20, ema50 = float(last_row['EMA_20'].iloc[0]), float(last_row['EMA_50'].iloc[0])
        pred_p = model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0]
        
        score = 0
        if cur_p > ema20 > ema50: score += 40
        if 40 < rsi_val < 65: score += 30
        if pred_p > cur_p: score += 20
        sent, head = get_news_sentiment(symbol)
        score += 10 if sent > 0.05 else -10 if sent < -0.05 else 0
        
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": max(0, min(100, score)), "Headline": head}
    except: return None

def run_auto_trade(res, sheet, total_balance, live_rate):
    if not sheet: return
    try:
        data = sheet.get_all_records()
        df_trade = pd.DataFrame(data)
        price_thb = res['Price_USD'] * live_rate
        now_th = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S %d-%m-%Y")
        
        is_holding = False
        if not df_trade.empty and 'สถานะ' in df_trade.columns:
            is_holding = any((df_trade['เหรีย่ง'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD'))

        if res['Score'] >= 85 and not is_holding:
            investment = total_balance * 0.2
            row = [now_th, res['Symbol'], "HOLD", round(price_thb, 2), 0, "0%", res['Score'], round(total_balance, 2), round(investment/price_thb, 6), res['Headline']]
            sheet.append_row(row)
            st.toast(f"🚀 BUY: {res['Symbol']}", icon="✅")

        elif is_holding:
            idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
            entry_p = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
            p_pct = ((price_thb - entry_p) / entry_p) * 100
            
            if p_pct >= 3.0 or p_pct <= -2.0 or res['Score'] < 45:
                row_num = int(idx) + 2
                current_bal_at_trade = float(df_trade.loc[idx, 'Balance'])
                new_balance = current_bal_at_trade * (1 + (p_pct/100))
                sheet.update_cell(row_num, 3, "SOLD")
                sheet.update_cell(row_num, 5, round(price_thb, 2))
                sheet.update_cell(row_num, 6, f"{p_pct:.2f}%")
                sheet.update_cell(row_num, 8, round(new_balance, 2))
                st.toast(f"💰 SELL: {res['Symbol']} {p_pct:.2f}%", icon="💵")
    except Exception as e: st.warning(f"⚠️ GSheet Error: {e}")

# --- 4. Main UI ---
sheet = init_gsheet()
current_bal = 1000.0
df_perf = pd.DataFrame()

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            if not df_perf.empty and 'Balance' in df_perf.columns:
                current_bal = float(df_perf.iloc[-1]['Balance'])
    except: pass

# Sidebar: Goal Settings
st.sidebar.title("🎯 Investment Goal")
target_bal = st.sidebar.number_input("Target Balance (THB)", value=5000.0, step=500.0)
target_date = st.sidebar.date_input("Target Date", datetime.now() + timedelta(days=30))
live_rate = st.sidebar.number_input("USD/THB", value=35.0, step=0.1)

days_left = (target_date - datetime.now().date()).days
daily_rate_req = calculate_daily_target(current_bal, target_bal, days_left)

st.sidebar.divider()
st.session_state.bot_active = st.sidebar.toggle("Start Pepper Bot", value=st.session_state.bot_active)

# Main Dashboard
st.title("🌶️ Pepper Hunter Pro AI")

# Metric Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current Balance", f"{current_bal:,.2f} ฿")
c2.metric("Target", f"{target_bal:,.2f} ฿")
c3.metric("Daily Need (%)", f"{daily_rate_req*100:.2f}%")
c4.metric("Days Left", f"{days_left} Days")

# Graph Section
if not df_perf.empty and 'Balance' in df_perf.columns:
    st.subheader("📈 Portfolio Performance")
    st.area_chart(df_perf['Balance'])

# Bot Logic
if st.session_state.bot_active:
    if current_bal >= target_bal:
        st.balloons()
        st.success("🏆 Goal Reached! บอทหยุดทำงานเพื่อรักษาผลกำไร")
        st.session_state.bot_active = False
    else:
        st.info(f"🔄 Scanning Market... เป้าหมายวันนี้: +{current_bal * daily_rate_req:.2f} THB")
        tickers = get_top_30_tickers()
        sample = random.sample(tickers, 5)
        
        for symbol in sample:
            with st.status(f"Analyzing {symbol}...", expanded=False) as s:
                df_h = yf.download(symbol, period="60d", interval="1d", progress=False)
                if not df_h.empty:
                    res = analyze_coin_ai(symbol, df_h)
                    if res:
                        run_auto_trade(res, sheet, current_bal, live_rate)
                        st.write(f"🪙 {symbol} | Score: {res['Score']} | Price: ${res['Price_USD']}")
                s.update(label=f"Completed {symbol}", state="complete")
        
        st.session_state.last_scan = datetime.now().strftime("%H:%M:%S")
        time.sleep(15)
        st.rerun()

# Trade History
if not df_perf.empty:
    with st.expander("📊 View Full Trade History"):
        st.dataframe(df_perf.tail(20), use_container_width=True)
