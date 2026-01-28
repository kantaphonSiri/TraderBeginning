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
st.set_page_config(page_title="Budget-Bets AI Analysis", layout="wide")

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        if rate and 30 < rate < 45: return float(rate)
    except: pass
    return 35.0

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
    
    # EMA & MACD
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    df['EMA50'] = close.ewm(span=50, adjust=False).mean()
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    return df

# --- ฟังก์ชัน "สมอง" วิเคราะห์ข้อมูล ---
def analyze_coin(row):
    score = 0
    reasons = []
    
    # 1. วิเคราะห์ RSI
    if row['RSI'] <= 35:
        score += 4
        reasons.append("ราคาถูกมาก (Oversold)")
    elif row['RSI'] >= 70:
        score -= 3
        reasons.append("ราคาแพงเกินไป (Overbought)")
        
    # 2. วิเคราะห์ Trend (EMA)
    if row['Close'] > row['EMA20']:
        score += 3
        reasons.append("เป็นเทรนด์ขาขึ้นระยะสั้น")
    else:
        score -= 2
        reasons.append("เทรนด์ยังเป็นขาลง")
        
    # 3. วิเคราะห์ Momentum (MACD)
    if row['MACD'] > row['Signal']:
        score += 3
        reasons.append("แรงซื้อกำลังมา (Bullish Momentum)")
        
    # สรุปผล
    if score >= 7: return "🔥 น่าซื้อสะสม", "success", score, reasons
    if score >= 4: return "⚖️ รอจังหวะย่อ", "info", score, reasons
    return "⚠️ เสี่ยง/รอไปก่อน", "warning", score, reasons

def get_coin_data(symbol):
    try:
        ticker_sym = f"{symbol}-USD"
        df = yf.download(ticker_sym, period="1mo", interval="1h", progress=False)
        if not df.empty:
            df = add_indicators(df)
            return float(df['Close'].iloc[-1]), df
    except: pass
    return None, None

# ------------------------
# UI & SIDEBAR
# ------------------------
with st.sidebar:
    st.title("🎯 Strategy Settings")
    budget = st.number_input("งบต่อ 1 เหรียญ (บาท):", min_value=0.0, value=None, placeholder="ว่างไว้เพื่อดูแนะนำ...")
    
    st.divider()
    target_pct = st.slider("เป้าหมายกำไร (%)", 5, 100, 15)
    stop_loss_pct = st.slider("จุดตัดขาดทุน (%)", 3, 50, 7)
    
    if st.button("🔄 Force Re-Scan", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets AI Analyst")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX', 'LINK', 'NEAR', 'SUI', 'OP', 'ARB']

# --- PROCESSING ---
scanned_items = []
with st.spinner("🤖 ระบบ AI กำลังวิเคราะห์กราฟเทคนิค..."):
    for s in symbols:
        price_usd, df = get_coin_data(s)
        if price_usd and df is not None:
            price_thb = price_usd * usd_thb
            last_row = df.iloc[-1]
            advice, color, score, reasons = analyze_coin(last_row)

            scanned_items.append({
                'symbol': s, 'price_thb': price_thb, 'df': df,
                'rsi': last_row['RSI'], 'advice': advice, 'color': color,
                'score': score, 'reasons': reasons
            })

# Filtering
if budget is None or budget == 0:
    display_items = scanned_items[:6]
    st.info("💡 ระบบเลือกเหรียญยอดนิยมมาวิเคราะห์ให้คุณ 6 ตัวแรก")
else:
    display_items = [item for item in scanned_items if item['price_thb'] <= budget]

# --- DISPLAY ---
if not display_items:
    st.warning("⚠️ ไม่พบเหรียญที่ตรงงบประมาณ")
else:
    cols = st.columns(2) # ปรับเป็น 2 คอลัมน์เพื่อให้เห็นบทวิเคราะห์ชัดๆ
    for idx, item in enumerate(display_items):
        with cols[idx % 2]:
            with st.container(border=True):
                # ส่วนหัว: ชื่อเหรียญและความเห็น AI
                c1, c2 = st.columns([1, 1.2])
                with c1:
                    st.subheader(f"🪙 {item['symbol']}")
                    st.metric("ราคา", f"{item['price_thb']:,.2f} ฿")
                with c2:
                    st.markdown(f"**AI วิเคราะห์ว่า:**")
                    if item['color'] == "success": st.success(item['advice'])
                    elif item['color'] == "info": st.info(item['advice'])
                    else: st.warning(item['advice'])

                # แสดงเหตุผลประกอบ
                with st.expander("📝 ดูเหตุผลวิเคราะห์"):
                    for r in item['reasons']:
                        st.write(f"- {r}")
                
                # กราฟย่อ
                fig = go.Figure()
                hist_df = item['df'].tail(48)
                fig.add_trace(go.Scatter(x=hist_df.index, y=hist_df['Close'], name='Price', line=dict(color='#00ffcc')))
                fig.add_trace(go.Scatter(x=hist_df.index, y=hist_df['EMA20'], name='EMA20', line=dict(color='orange', width=1)))
                fig.update_layout(height=150, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                # ระบบคำนวณกำไร
                entry_price = st.number_input(f"ทุน {item['symbol']} (บาท):", key=f"cost_{item['symbol']}", value=0.0)
                if entry_price > 0:
                    diff_pct = ((item['price_thb'] - entry_price) / entry_price) * 100
                    if diff_pct >= target_pct: st.success(f"🚀 เป้าขาย: {diff_pct:+.2f}%")
                    elif diff_pct <= -stop_loss_pct: st.error(f"🛑 คัดขาดทุน: {diff_pct:+.2f}%")
                    else: st.write(f"กำไรปัจจุบัน: {diff_pct:+.2f}%")

time.sleep(REFRESH_SEC)
st.rerun()
