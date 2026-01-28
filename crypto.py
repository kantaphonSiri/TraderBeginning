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
st.set_page_config(page_title="Budget-Bets Dynamic Analyst", layout="wide")

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

def add_indicators(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df['Close'].astype(float)
    df['RSI'] = 100 - (100 / (1 + (close.diff().where(close.diff() > 0, 0).rolling(14).mean() / 
                                  close.diff().where(close.diff() < 0, 0).abs().rolling(14).mean().replace(0, 0.001))))
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    return df

def analyze_coin(row):
    score = 0
    reasons = []
    if row['RSI'] <= 35: score += 4; reasons.append("ราคาถูก (Oversold)")
    elif row['RSI'] >= 70: score -= 3; reasons.append("ราคาแพง (Overbought)")
    if row['Close'] > row['EMA20']: score += 3; reasons.append("เทรนด์ขาขึ้นระยะสั้น")
    else: score -= 2; reasons.append("เทรนด์ขาลง")
    if row['MACD'] > row['Signal']: score += 3; reasons.append("แรงซื้อสะสม (MACD Bullish)")
    
    if score >= 7: return "🔥 น่าซื้อสะสม", "success", reasons
    if score >= 4: return "⚖️ รอจังหวะย่อ", "info", reasons
    return "⚠️ เสี่ยง/รอไปก่อน", "warning", reasons

# ------------------------
# UI & SIDEBAR
# ------------------------
with st.sidebar:
    st.title("🎯 Custom Scanner")
    
    # --- เปลี่ยนจาก Hardcode เป็น Dynamic Selection ---
    default_coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT']
    selected_symbols = st.multiselect(
        "เลือกเหรียญที่ต้องการสแกน:", 
        options=['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX', 'LINK', 'NEAR', 'SUI', 'OP', 'ARB', 'DOGE', 'MATIC', 'PEPE'],
        default=default_coins
    )
    
    budget = st.number_input("งบต่อ 1 เหรียญ (บาท):", min_value=0.0, value=None)
    target_pct = st.slider("เป้าหมายกำไร (%)", 5, 100, 15)
    stop_loss_pct = st.slider("จุดตัดขาดทุน (%)", 3, 50, 7)

usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets AI Analyst")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

# --- PROCESSING ---
scanned_items = []
if not selected_symbols:
    st.warning("👈 กรุณาเลือกเหรียญที่แถบด้านข้างเพื่อเริ่มการวิเคราะห์")
else:
    with st.spinner("🤖 ระบบกำลังเรียก API และวิเคราะห์กราฟ..."):
        for s in selected_symbols:
            try:
                df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
                if not df.empty:
                    df = add_indicators(df)
                    price_thb = float(df['Close'].iloc[-1]) * usd_thb
                    
                    # กรองตามงบ (ถ้ามีการกรอก)
                    if budget is None or budget == 0 or price_thb <= budget:
                        advice, color, reasons = analyze_coin(df.iloc[-1])
                        scanned_items.append({'symbol': s, 'price_thb': price_thb, 'df': df, 'advice': advice, 'color': color, 'reasons': reasons})
            except: continue

# --- DISPLAY ---
if scanned_items:
    cols = st.columns(2)
    for idx, item in enumerate(scanned_items):
        with cols[idx % 2]:
            with st.container(border=True):
                c1, c2 = st.columns([1, 1.2])
                with c1:
                    st.subheader(f"🪙 {item['symbol']}")
                    st.metric("ราคา", f"{item['price_thb']:,.2f} ฿")
                with c2:
                    if item['color'] == "success": st.success(item['advice'])
                    elif item['color'] == "info": st.info(item['advice'])
                    else: st.warning(item['advice'])
                
                # กราฟและระบบคำนวณกำไร (เหมือนเดิม)
                fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
                fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                
                entry_price = st.number_input(f"ทุน {item['symbol']} (บาท):", key=f"c_{item['symbol']}", value=0.0)
                if entry_price > 0:
                    diff = ((item['price_thb'] - entry_price) / entry_price) * 100
                    if diff >= target_pct: st.success(f"🚀 ขาย!: {diff:+.2f}%")
                    elif diff <= -stop_loss_pct: st.error(f"🛑 คัด!: {diff:+.2f}%")

time.sleep(REFRESH_SEC)
st.rerun()
