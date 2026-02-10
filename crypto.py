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
AUTO_SYNC_INTERVAL = 900 

st.set_page_config(page_title="Budget-bet Pro (One-Shot)", layout="wide")

if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'last_sync' not in st.session_state: st.session_state.last_sync = 0
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'rb') as f: st.session_state.master_data = pickle.load(f)
        except: st.session_state.master_data = {}
    else: st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. CORE LOGIC
# ---------------------------------------------------------

def get_ai_advice(df_single):
    """คำนวณ Indicator จาก DataFrame ของเหรียญเดียว"""
    try:
        if df_single is None or len(df_single) < 30: return "ข้อมูลไม่พอ", "#808495", 0, 0
        
        close = df_single['Close'].astype(float)
        volume = df_single['Volume'].astype(float)
        current_p = close.iloc[-1]
        
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        avg_vol = volume.rolling(window=20).mean().iloc[-1]
        vol_spike = volume.iloc[-1] > avg_vol
        
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
    except:
        return "วิเคราะห์ไม่ได้", "#808495", 0, 0

def sync_data_one_shot():
    """ดึงข้อมูลเหรียญทั้งหมดใน Request เดียว"""
    with st.status("🧹 เมดกำลังทำความสะอาดข้อมูลและดึงตลาดรอบเดียวจบ...") as status:
        # 1. รับ List เหรียญท็อปๆ
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
            symbols = [c['symbol'].upper() for c in requests.get(url, timeout=5).json()]
        except:
            symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX']

        # 2. เตรียม Tickers
        tickers = [f"{s}-USD" for s in symbols]
        
        # 3. ดึง One-Shot (ใช้ period 1 เดือนเพื่อความเร็วและแม่นยำ)
        # นี่คือจุดที่จะส่งไปหา Yahoo แค่ 'ครั้งเดียว'
        all_data = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False)
        
        # 4. อัตราแลกเปลี่ยน
        try:
            usd_thb = yf.Ticker("THB=X").fast_info['last_price']
        except:
            usd_thb = st.session_state.master_data.get('EXCHANGE_RATE', 35.0)

        new_data = {'EXCHANGE_RATE': usd_thb}
        sheet_data = []

        # 5. วนลูปกรองข้อมูลที่ดึงมาแล้วใน Memory (ไม่ยิง API เพิ่มแล้ว)
        for s in symbols:
            try:
                ticker_key = f"{s}-USD"
                if ticker_key not in all_data.columns.get_level_values(0): continue
                
                df = all_data[ticker_key].copy().ffill()
                
                # กรองเหรียญที่ไม่มีราคา หรือ Delisted
                if df.empty or pd.isna(df['Close'].iloc[-1]): continue
                
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                advice, color, rsi, ema20_val = get_ai_advice(df)
                
                new_data[s] = {
                    'price': price_thb,
                    'base_price': float(df['Close'].iloc[0]) * usd_thb,
                    'df': df,
                    'advice': advice,
                    'color': color
                }
                
                # เตรียมข้อมูลสำหรับ Google Sheet (Column Names ตามมาสเตอร์ขอ)
                sheet_data.append({
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Symbol": s,
                    "Price_THB": round(price_thb, 2),
                    "Advice": advice,
                    "RSI": round(rsi, 2),
                    "EMA20": round(ema20_val * usd_thb, 2),
                    "Trend": "Up" if price_thb > (ema20_val * usd_thb) else "Down"
                })
            except: continue

        st.session_state.master_data = new_data
        st.session_state.last_sync = time.time()
        with open(DB_FILE, 'wb') as f: pickle.dump(new_data, f)
        status.update(label="Sync เสร็จสิ้นในรอบเดียว! ปลอดภัยแน่นอนค่ะ", state="complete")
        
    return pd.DataFrame(sheet_data)

# ---------------------------------------------------------
# 3. AUTO SYNC & UI RENDER
# ---------------------------------------------------------
if time.time() - st.session_state.last_sync > AUTO_SYNC_INTERVAL:
    sync_data_one_shot()
    st.rerun()

st.title("🪙 Budget-bet Pro (One-Shot Mode)")
# ... (ส่วนการแสดงผล Sidebar และ Main UI เหมือนเดิม)
