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

st.set_page_config(page_title="Budget-bet Pro (Final Stable)", layout="wide")

# CSS เมดจัดให้ดูสวยบนมือถือและคอม
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    @media (max-width: 640px) { .stMetric div { font-size: 14px !important; } }
    </style>
""", unsafe_allow_html=True)

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
    try:
        if df_single is None or len(df_single) < 20: return "ข้อมูลไม่พอ", "#808495", 0, 0
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
        
        if current_p > ema20.iloc[-1] > ema50.iloc[-1] and 50 < rsi < 70: return "🔥 ขาขึ้นแรง (Buy Build)", "#00ffcc", rsi, ema20.iloc[-1]
        elif rsi < 30: return "💎 โซนสะสม (Oversold)", "#ffcc00", rsi, ema20.iloc[-1]
        elif rsi > 75: return "⚠️ ระวังดอย (Overbought)", "#ff4b4b", rsi, ema20.iloc[-1]
        elif current_p < ema20.iloc[-1]: return "📉 ขาลง (Wait/Sell)", "#ff4b4b", rsi, ema20.iloc[-1]
        else: return "⏳ ไซด์เวย์ (Neutral)", "#808495", rsi, ema20.iloc[-1]
    except: return "วิเคราะห์ไม่ได้", "#808495", 0, 0

def sync_data_robust():
    with st.status("🧹 เมดกำลังกรองข้อมูลและทำความสะอาดตลาด...") as status:
        # 1. รายชื่อเหรียญ (เน้นตัวหลักที่ Yahoo มีข้อมูลชัวร์ๆ)
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=40&page=1"
            symbols = [c['symbol'].upper() for c in requests.get(url, timeout=5).json()]
        except:
            symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX']

        # กรองตัวแสบที่ Yahoo มักจะหาไม่เจอ
        blacklist = ['USDS', 'USDE', 'USD1', 'FIGR', 'HYPE', 'CC', 'BUIDL', 'ASTER', 'WLFI', 'USYC']
        symbols = [s for s in symbols if s not in blacklist]
        
        # 2. ดึงค่าเงินบาท
        try:
            usd_thb = yf.Ticker("THB=X").fast_info['last_price']
        except:
            usd_thb = st.session_state.master_data.get('EXCHANGE_RATE', 35.0)

        new_data = {'EXCHANGE_RATE': usd_thb}
        sheet_data = []

        # 3. ดึงข้อมูลแบบ Small Batches (กลุ่มละ 15 ตัว) เพื่อเลี่ยง Rate Limit
        batch_size = 15
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tickers = [f"{s}-USD" for s in batch]
            try:
                # ลดช่วงเวลาลงเหลือ 1 เดือน และไม่เอา Metadata เยอะเกินไป
                all_batch_data = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False, threads=False)
                
                for s in batch:
                    ticker_key = f"{s}-USD"
                    try:
                        # ตรวจสอบว่ามีข้อมูลเหรียญนี้ในผลลัพธ์ไหม
                        if ticker_key not in all_batch_data.columns.get_level_values(0): continue
                        df = all_batch_data[ticker_key].copy().ffill()
                        
                        if df.empty or len(df) < 5 or pd.isna(df['Close'].iloc[-1]): continue
                        
                        price_thb = float(df['Close'].iloc[-1]) * usd_thb
                        advice, color, rsi, ema20_val = get_ai_advice(df)
                        
                        new_data[s] = {
                            'price': price_thb,
                            'base_price': float(df['Close'].iloc[0]) * usd_thb,
                            'df': df.tail(50), # เก็บแค่ที่จำเป็นประหยัด Memory
                            'advice': advice,
                            'color': color
                        }
                        
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
                # พักสั้นๆ ระหว่าง Batch
                time.sleep(random.uniform(2, 4))
            except: continue

        st.session_state.master_data = new_data
        st.session_state.last_sync = time.time()
        with open(DB_FILE, 'wb') as f: pickle.dump(new_data, f)
        status.update(label="Sync สำเร็จ! กรองตัวที่มีปัญหาออกให้แล้วค่ะ", state="complete")
        
    return pd.DataFrame(sheet_data)

# ---------------------------------------------------------
# 3. AUTO SYNC & UI
# ---------------------------------------------------------
if time.time() - st.session_state.last_sync > AUTO_SYNC_INTERVAL:
    sync_data_robust()
    st.rerun()

# --- HEADER ---
st.title("🪙 Budget-bet Pro (Stable Mode)")
rate = st.session_state.master_data.get('EXCHANGE_RATE', 0)
st.caption(f"💵 1 USD = {rate:.2f} THB | 🔄 อัปเดตล่าสุด: {datetime.fromtimestamp(st.session_state.last_sync).strftime('%H:%M:%S')}")

# --- SIDEBAR PORTFOLIO ---
with st.sidebar:
    st.header("💼 พอร์ตของมาสเตอร์")
    if st.session_state.portfolio:
        t_cost, t_market = 0, 0
        for sym, m in st.session_state.portfolio.items():
            if sym in st.session_state.master_data:
                cp = st.session_state.master_data[sym]['price']
                t_cost += m['cost']
                t_market += cp
        
        t_diff = t_market - t_cost
        t_pct = (t_diff / t_cost * 100) if t_cost > 0 else 0
        st.metric("กำไร/ขาดทุนรวม", f"{t_diff:,.2f} ฿", f"{t_pct:+.2f}%")
        
    if st.button("🔄 อัปเดตทันที", use_container_width=True):
        sync_data_robust()
        st.rerun()

# --- MAIN DISPLAY ---
display_list = [s for s, d in st.session_state.master_data.items() if s != 'EXCHANGE_RATE']
cols = st.columns(2)

for idx, s in enumerate(display_list[:40]):
    data = st.session_state.master_data[s]
    advice = data.get('advice', 'รอดูจังหวะ')
    color = data.get('color', '#808495')
    
    with cols[idx % 2]:
        with st.container(border=True):
            st.subheader(f"{s}")
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>{advice}</span>", unsafe_allow_html=True)
            
            # คำนวณ % เปลี่ยนแปลง
            change = ((data['price'] - data['base_price']) / data['base_price']) * 100
            st.metric("ราคาปัจจุบัน", f"{data['price']:,.2f} ฿", f"{change:+.2f}%")
            
            # Sparkline
            prices = data['df']['Close'].values
            fig = go.Figure(data=[go.Scatter(y=prices, mode='lines', line=dict(color=color, width=2))])
            fig.update_layout(height=80, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{s}", config={'displayModeBar': False})
