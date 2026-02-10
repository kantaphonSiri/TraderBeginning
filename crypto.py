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
        
        # คำนวณ Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        # เตรียม Data สำหรับ RF
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X.values, y.values)
        
        # ดึงค่าล่าสุดเป็น Scalar (แก้ปัญหา Ambiguous Error)
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        rsi_val = float(last_row['RSI_14'].iloc[0])
        ema20 = float(last_row['EMA_20'].iloc[0])
        ema50 = float(last_row['EMA_50'].iloc[0])
        
        pred_p = model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0]
        
        # การให้คะแนน (Score Logic)
        score = 0
        if cur_p > ema20 > ema50: score += 40
        if 40 < rsi_val < 65: score += 30
        if pred_p > cur_p: score += 20
        
        sent, head = get_news_sentiment(symbol)
        score += 10 if sent > 0.05 else -10 if sent < -0.05 else 0
        
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": max(0, min(100, score)), "Headline": head}
    except Exception as e:
        return None

def run_auto_trade(res, sheet, total_balance, live_rate):
    if not sheet: return
    try:
        data = sheet.get_all_records()
        df_trade = pd.DataFrame(data)
        
        # ปรับสกุลเงิน
        price_thb = res['Price_USD'] * live_rate
        now_th = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S %d-%m-%Y")
        
        # เช็คสถานะการถือครอง
        is_holding = False
        if not df_trade.empty and 'สถานะ' in df_trade.columns:
            is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD'))

        # LOGIC: BUY
        if res['Score'] >= 85 and not is_holding:
            investment = total_balance * 0.2
            row = [now_th, res['Symbol'], "HOLD", round(price_thb, 2), 0, "0%", res['Score'], round(total_balance, 2), round(investment/price_thb, 6), res['Headline']]
            sheet.append_row(row)
            st.toast(f"🚀 BUY: {res['Symbol']} @ {price_thb:,.2f} THB", icon="✅")

        # LOGIC: SELL
        elif is_holding:
            idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
            entry_p = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
            p_pct = ((price_thb - entry_p) / entry_p) * 100
            
            # เงื่อนไขขาย: กำไร 3%, ขาดทุน 2%, หรือ AI บอกว่าไม่น่าถือแล้ว
            if p_pct >= 3.0 or p_pct <= -2.0 or res['Score'] < 45:
                # Update row ใน Google Sheet (Index + 2 เพราะ Sheet เริ่มที่ 1 และมี Header)
                row_num = int(idx) + 2
                new_balance = float(df_trade.loc[idx, 'Balance']) * (1 + (p_pct/100))
                
                sheet.update_cell(row_num, 3, "SOLD")
                sheet.update_cell(row_num, 5, round(price_thb, 2))
                sheet.update_cell(row_num, 6, f"{p_pct:.2f}%")
                sheet.update_cell(row_num, 8, round(new_balance, 2))
                st.toast(f"💰 SELL: {res['Symbol']} Profit: {p_pct:.2f}%", icon="💵")
                
    except Exception as e:
        st.warning(f"⚠️ GSheet Update Delay: {e}")

# --- 4. Main UI ---
sheet = init_gsheet()
df_perf = pd.DataFrame()
current_bal = 1000.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            current_bal = float(df_perf.iloc
