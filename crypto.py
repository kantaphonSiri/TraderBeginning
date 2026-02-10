import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go
import numpy as np
import random
from datetime import datetime

# ---------------------------------------------------------
# 1. CONFIG & DATABASE
# ---------------------------------------------------------
DB_FILE = "crypto_v11_responsive.pkl"
AUTO_SYNC_INTERVAL = 900 # 15 นาที (หน่วยเป็นวินาที)

st.set_page_config(page_title="Budget-bet Pro v2 (Auto)", layout="wide")

# CSS บังคับให้ Columns ไม่ยุบตัวบนมือถือ
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    </style>
""", unsafe_allow_html=True)

# Initialize Session States
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'last_sync' not in st.session_state: st.session_state.last_sync = 0
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'rb') as f: st.session_state.master_data = pickle.load(f)
        except: st.session_state.master_data = {}
    else: st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. CORE FUNCTIONS
# ---------------------------------------------------------
def get_ai_advice(df):
    if df is None or len(df) < 30: return "รอข้อมูล...", "#808495", 0, 0
    close = df['Close'].astype(float)
    volume = df['Volume'].astype(float)
    current_p = close.iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    rsi = (100 - (100 / (1 + rs))).iloc[-1]
    
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_spike = volume.iloc[-1] > avg_vol
    
    # Logic & Color
    if current_p > ema20.iloc[-1] > ema50.iloc[-1] and 50 < rsi < 70 and vol_spike:
        return "🔥 ขาขึ้นแรง (Buy Build)", "#00ffcc", rsi, ema20.iloc[-1]
    elif rsi < 30:
        return "💎 โซนสะสม (Oversold)", "#ffcc00", rsi, ema20.iloc[-1]
    elif rsi > 75:
        return "⚠️ ระวังดอย (Overbought)", "#ff4b4b", rsi, ema20.iloc[-1]
    elif current_p < ema20.iloc[-1]:
        return "📉 ขาลง (Wait/Sell)", "#ff4b4b", rsi, ema20.iloc[-1]
    else:
        return "⏳ ไซด์เวย์ (Neutral)", "#808495", rsi, ema20.iloc[-1]

def sync_data_safe():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=30&page=1"
        symbols = [c['symbol'].upper() for c in requests.get(url, timeout=5).json()]
    except:
        symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']
    
    try:
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
    except:
        usd_thb = st.session_state.master_data.get('EXCHANGE_RATE', 35.0)
        
    st.session_state.master_data['EXCHANGE_RATE'] = usd_thb
    new_data = st.session_state.master_data.copy()
    
    # เตรียม List สำหรับเก็บข้อมูลลง Sheet
    sheet_data = []
    
    with st.status("📡 ระบบเมดอัตโนมัติกำลังทำงาน...") as status:
        batch_size = 5
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tickers = [f"{s}-USD" for s in batch]
            try:
                data_group = yf.download(tickers, period="2mo", interval="1h", group_by='ticker', progress=False)
                for s in batch:
                    df = data_group[f"{s}-USD"] if len(tickers) > 1 else data_group
                    if not df.empty and not pd.isna(df['Close'].iloc[-1]):
                        price_thb = float(df['Close'].iloc[-1]) * usd_thb
                        advice, color, rsi, ema20_val = get_ai_advice(df)
                        
                        new_data[s] = {
                            'price': price_thb,
                            'base_price': float(df['Close'].iloc[0]) * usd_thb,
                            'df': df.ffill(),
                            'advice': advice,
                            'color': color
                        }
                        
                        # เก็บข้อมูลตามโครงสร้าง Google Sheets
                        sheet_data.append({
                            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Symbol": s,
                            "Price_THB": round(price_thb, 2),
                            "Advice": advice,
                            "RSI": round(rsi, 2),
                            "EMA20": round(ema20_val * usd_thb, 2),
                            "Trend": "Up" if price_thb > (ema20_val * usd_thb) else "Down"
                        })
                time.sleep(random.uniform(2, 4))
            except: continue
            
        st.session_state.master_data = new_data
        st.session_state.last_sync = time.time()
        with open(DB_FILE, 'wb') as f: pickle.dump(new_data, f)
        status.update(label="อัปเดตอัตโนมัติเรียบร้อยค่ะ!", state="complete")
    
    return pd.DataFrame(sheet_data)

# ---------------------------------------------------------
# 3. AUTO SYNC LOGIC & UI
# ---------------------------------------------------------
current_time = time.time()
if current_time - st.session_state.last_sync > AUTO_SYNC_INTERVAL:
    df_for_sheet = sync_data_safe()
    # ตรงนี้มาสเตอร์สามารถเพิ่ม Code เชื่อมต่อ Google Sheet API (gspread) เพื่อส่ง df_for_sheet ไปได้เลยค่ะ
    st.rerun()

# --- ส่วน UI แสดงผล (เหมือนเดิม) ---
st.title("🪙 Budget-bet Pro (Auto Sync)")
st.caption(f"🔄 อัปเดตล่าสุด: {datetime.fromtimestamp(st.session_state.last_sync).strftime('%H:%M:%S')}")

# (เรียกใช้ Loop แสดงการ์ดเหรียญจาก Master Data ตามโค้ดเดิม)
# ... [ส่วนที่เหลือเหมือนโค้ดล่าสุดที่คุณส่งมา]
