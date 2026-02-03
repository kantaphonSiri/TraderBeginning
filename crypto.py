import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import requests
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 1. ฟังก์ชันดึงข้อมูล Sentiment ---
def get_market_sentiment():
    try:
        url = "https://api.alternative.me/fng/"
        r = requests.get(url, timeout=10).json()
        return int(r['data'][0]['value'])
    except:
        return 50

# --- 2. ฟังก์ชันทำนายราคา (Linear Regression) ---
def predict_next_price(df):
    lookback = 10
    if len(df) < lookback: return 0
    y = df['Close'].values[-lookback:]
    X = np.arange(lookback).reshape(-1, 1)
    
    model = LinearRegression()
    model.fit(X, y)
    
    next_index = np.array([[lookback]])
    prediction = model.predict(next_index)
    return prediction[0]

# --- 3. ฟังก์ชันเตรียมข้อมูล ---
def prepare_data(symbol, timeframe):
    df = yf.download(symbol, period="60d", interval=timeframe)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty: return None, 0

    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=20, append=True)
    df['sentiment'] = get_market_sentiment()
    df = df.dropna()
    pred_price = predict_next_price(df)
    return df, pred_price

# --- 4. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="AI Trader Pro with Win Rate", layout="wide")
st.title("📈 AI Crypto Trader: Win Rate Analytics")

# Session State สำหรับเก็บข้อมูล Journal
if 'journal_list' not in st.session_state:
    st.session_state.journal_list = []

# --- Sidebar ---
st.sidebar.header("⚙️ Strategy Settings")
asset_list = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
ticker = st.sidebar.selectbox("🎯 Select Asset:", asset_list)
tf_options = {"1 Hour (Day Trade)": "1h", "15 Min (Scalping)": "15m", "1 Day (Swing)": "1d"}
timeframe = tf_options[st.sidebar.selectbox("⏰ Timeframe:", list(tf_options.keys()))]

try:
    data, pred_price = prepare_data(ticker, timeframe)
    
    if data is not None:
        last_row = data.iloc[-1]
        cur_price = last_row['Close']
        rsi = last_row['RSI_14']
        
        # Decision Logic
        price_diff = ((pred_price - cur_price) / cur_price) * 100
        if price_diff > 0.5 and rsi < 65:
            action, color = "✅ BUY", "green"
        elif price_diff < -0.5 or rsi > 70:
            action, color = "🚨 SELL", "red"
        else:
            action, color = "🟡 HOLD", "orange"

        # --- ส่วนแสดงผล Win Rate (ถ้ามีข้อมูล) ---
        if st.session_state.journal_list:
            df_journal = pd.DataFrame(st.session_state.journal_list)
            total_trades = len(df_journal)
            wins = len(df_journal[df_journal['Result'] == 'Win'])
            win_rate = (wins / total_trades) * 100
            
            st.subheader("📊 Performance Statistics")
            c1, c2, c3 = st.columns(3)
            c1.metric("Win Rate", f"{win_rate:.2f}%")
            c2.metric("Total Trades", total_trades)
            c3.metric("Total Wins", wins)
            st.divider()

        # Dashboard ข้อมูลปัจจุบัน
        st.subheader(f"Current Analysis: {ticker}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Price", f"${cur_price:,.2f}")
        m2.metric("Target", f"${pred_price:,.2f}", f"{price_diff:.2f}%")
        m3.metric("RSI", f"{rsi:.2f}")
        m4.metric("Signal", action)

        st.line_chart(data['Close'])

        # --- 5. ระบบ Journal & Win Rate Calculation ---
        st.subheader("📝 Trading Journal & Win Rate Record")
        with st.form("trade_record"):
            col1, col2, col3, col4 = st.columns(4)
            entry_price = col1.number_input("Entry Price", value=float(cur_price))
            exit_price = col2.number_input("Exit Price (ราคาที่ปิดทำกำไร/ขาดทุน)", value=float(cur_price))
            trade_result = col3.selectbox("Result", ["Win", "Loss"])
            note = col4.text_input("Note")
            
            if st.form_submit_button("Record Trade"):
                st.session_state.journal_list.append({
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Symbol": ticker,
                    "Entry": entry_price,
                    "Exit": exit_price,
                    "Result": trade_result,
                    "Profit %": ((exit_price - entry_price) / entry_price) * 100,
                    "Note": note
                })
                st.rerun()

        if st.session_state.journal_list:
            st.dataframe(pd.DataFrame(st.session_state.journal_list), use_container_width=True)
            if st.button("Clear All Data"):
                st.session_state.journal_list = []
                st.rerun()

except Exception as e:
    st.error(f"Error: {e}")
