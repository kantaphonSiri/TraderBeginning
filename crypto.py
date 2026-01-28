import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. CONFIG & SETUP
# ------------------------
REFRESH_SEC = 60
st.set_page_config(page_title="Budget-Bets Alpha Pro", layout="wide")

# 1. ระบบตรวจสอบค่าเงินบาทแบบหลายชั้น
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        if rate and 30 < rate < 45: return float(rate)
    except: pass
    
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5).json()
        return float(res['rates']['THB'])
    except:
        return 35.0

# 2. คำนวณ Advanced Indicators
def add_indicators(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    close = df['Close'].astype(float)
    
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, 0.001)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # EMA
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    
    # MACD
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    return df

# 3. ดึงข้อมูล Crypto
def get_coin_data(symbol):
    try:
        ticker_sym = f"{symbol}-USD"
        df = yf.download(ticker_sym, period="1mo", interval="1h", progress=False)
        if not df.empty:
            df = add_indicators(df)
            last_price = float(df['Close'].iloc[-1])
            return last_price, df
    except: pass
    return None, None

# ------------------------
# UI & SIDEBAR (ระบบตั้งเป้ากำไร/ขาดทุน)
# ------------------------
with st.sidebar:
    st.title("🎯 Strategy Settings")
    
    budget = st.number_input("งบต่อ 1 เหรียญ (บาท):", min_value=0.0, value=None, placeholder="กรอกงบเพื่อเริ่มกรอง...")
    
    st.divider()
    st.subheader("💰 Profit & Risk Management")
    target_pct = st.slider("เป้าหมายกำไร (%)", 5, 100, 15)
    stop_loss_pct = st.slider("จุดตัดขาดทุน (%)", 3, 50, 7)
    
    st.divider()
    st.subheader("🔍 Signal Filters")
    min_rsi = st.slider("RSI Oversold Level", 10, 40, 30)
    use_ema_filter = st.checkbox("ยืนยันเทรนด์ (Price > EMA20)", value=True)
    
    if st.button("🔄 Force Re-Scan", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets Alpha")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | **Refreshed:** {datetime.now().strftime('%H:%M:%S')}")

# รายชื่อเหรียญเป้าหมาย
symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX', 'LINK', 'NEAR', 'SUI', 'OP', 'ARB']

# --- PROCESSING ---
scanned_items = []
with st.spinner("🔍 กำลังวิเคราะห์ข้อมูลตลาด..."):
    for s in symbols:
        price_usd, df = get_coin_data(s)
        if price_usd and df is not None:
            price_thb = price_usd * usd_thb
            
            # ดึงค่า Indicators ล่าสุด
            last_close = float(df['Close'].iloc[-1])
            last_rsi = float(df['RSI'].iloc[-1])
            last_ema20 = float(df['EMA20'].iloc[-1])
            last_macd = float(df['MACD'].iloc[-1])
            last_signal = float(df['Signal'].iloc[-1])
            
            # Logic สัญญาณซื้อ
            is_oversold = last_rsi <= min_rsi
            is_bullish_ema = last_close > last_ema20 if use_ema_filter else True
            is_macd_cross = last_macd > last_signal

            scanned_items.append({
                'symbol': s, 'price_thb': price_thb, 'df': df,
                'rsi': last_rsi, 'macd': last_macd, 'signal': last_signal,
                'status': "BUY SIGNAL" if (is_oversold or (is_bullish_ema and is_macd_cross)) else "WATCHING"
            })

# --- FILTERING LOGIC ---
if budget is None or budget == 0:
    display_items = scanned_items[:6]
    st.info("💡 แสดง Top 6 เหรียญแนะนำ (กรอกงบที่ Sidebar เพื่อกรองตามราคาจริง)")
else:
    display_items = [item for item in scanned_items if item['price_thb'] <= budget]
    st.success(f"🔍 กรองเหรียญที่ราคาต่ำกว่า {budget:,.2f} บาท")

# --- DISPLAY ---
if not display_items:
    st.warning("⚠️ ไม่พบเหรียญที่ตรงตามเงื่อนไขงบประมาณ")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคาปัจจุบัน", f"{item['price_thb']:,.2f} ฿")
                
                # Indicators Info
                c1, c2 = st.columns(2)
                c1.write(f"**RSI:** {item['rsi']:.1f}")
                macd_status = "Bullish" if item['macd'] > item['signal'] else "Bearish"
                c2.write(f"**MACD:** {macd_status}")

                # Plotly Chart
                fig = go.Figure()
                hist_df = item['df'].tail(48)
                fig.add_trace(go.Scatter(x=hist_df.index, y=hist_df['Close'], name='Price', line=dict(color='#00ffcc')))
                fig.add_trace(go.Scatter(x=hist_df.index, y=hist_df['EMA20'], name='EMA20', line=dict(color='orange', width=1)))
                fig.update_layout(height=140, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                # --- ระบบคำนวณเป้าหมายกำไร/ขาดทุน (นี่คือส่วนที่เพิ่มกลับมาครับ) ---
                st.divider()
                entry_price = st.number_input(f"ทุน {item['symbol']} (บาท):", key=f"cost_{item['symbol']}", value=0.0, step=100.0)
                
                if entry_price > 0:
                    current_p = item['price_thb']
                    diff_pct = ((current_p - entry_price) / entry_price) * 100
                    
                    if diff_pct >= target_pct:
                        st.success(f"🚀 ถึงเป้ากำไร!: {diff_pct:+.2f}% (ควรพิจารณาขาย)")
                    elif diff_pct <= -stop_loss_pct:
                        st.error(f"🛑 หลุดจุดคัด!: {diff_pct:+.2f}% (ต้องตัดขาดทุน)")
                    else:
                        st.info(f"📊 ผลตอบแทนปัจจุบัน: {diff_pct:+.2f}%")
                
                # แสดงสถานะสัญญาณซื้อเบื้องต้น
                if item['status'] == "BUY SIGNAL":
                    st.markdown("🎯 **Signal:** <span style='color:green'>BUY NOW</span>", unsafe_allow_html=True)
                else:
                    st.markdown("🎯 **Signal:** <span style='color:gray'>WATCHING</span>", unsafe_allow_html=True)

# Auto Refresh
time.sleep(REFRESH_SEC)
st.rerun()
