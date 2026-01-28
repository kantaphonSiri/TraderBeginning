import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. CONFIG & SESSION STATE
# ------------------------
REFRESH_SEC = 60
st.set_page_config(page_title="Budget-Bets Portfolio Pro", layout="wide")

# สร้างตัวจำข้อมูล (Memory) สำหรับพอร์ต
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {} # เก็บในรูปแบบ {'BTC': 2100000, 'SOL': 3500}

# 1. ระบบดึงข้อมูลพื้นฐาน (Top 30 + Exchange Rate)
@st.cache_data(ttl=3600)
def get_top_symbols(limit=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        data = requests.get(url, timeout=5).json()
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'PYUSD']
        return [coin['symbol'].upper() for coin in data if coin['symbol'].upper() not in exclude]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'LINK', 'DOT']

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return float(rate) if 30 < rate < 45 else 35.0
    except: return 35.0

# 2. Indicators & AI Logic
def add_indicators(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    close = df['Close'].astype(float)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).abs().rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.001))))
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    return df

def analyze_logic(row):
    score = 0
    if row['RSI'] <= 35: score += 4
    if row['Close'] > row['EMA20']: score += 3
    if score >= 7: return "🔥 น่าซื้อ", "success"
    if score >= 4: return "⚖️ รอจังหวะ", "info"
    return "⚠️ เลี่ยง", "warning"

# ------------------------
# UI SIDEBAR (Portfolio Management)
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    
    # แสดงเหรียญที่ซื้อแล้วใน Sidebar
    if not st.session_state.portfolio:
        st.write("ยังไม่มีเหรียญในพอร์ต")
    else:
        for sym, cost in list(st.session_state.portfolio.items()):
            col_s1, col_s2 = st.columns([3, 1])
            col_s1.write(f"**{sym}** (ทุน: {cost:,.0f})")
            if col_s2.button("❌", key=f"del_{sym}"):
                del st.session_state.portfolio[sym]
                st.rerun()
    
    st.divider()
    st.subheader("⚙️ Settings")
    budget = st.number_input("งบต่อเหรียญ (บาท):", min_value=0.0, value=None)
    target_pct = st.slider("เป้าหมายกำไร (%)", 5, 100, 15)
    stop_loss_pct = st.slider("จุดตัดขาดทุน (%)", 3, 50, 7)

# --- MAIN APP ---
usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets Alpha Pro")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | {datetime.now().strftime('%H:%M:%S')}")

top_symbols = get_top_symbols(30)
scanned_items = []

with st.spinner("🤖 AI กำลังกวาดสแกนตลาด..."):
    for s in top_symbols:
        try:
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty:
                df = add_indicators(df)
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                if budget is None or budget == 0 or price_thb <= budget:
                    advice, color = analyze_logic(df.iloc[-1])
                    scanned_items.append({'symbol': s, 'price_thb': price_thb, 'df': df, 'advice': advice, 'color': color})
        except: continue

# --- DISPLAY ---
display_items = scanned_items if budget else scanned_items[:6]
cols = st.columns(2)

for idx, item in enumerate(display_items):
    with cols[idx % 2]:
        with st.container(border=True):
            # Header
            c1, c2 = st.columns([1, 1])
            c1.subheader(f"🪙 {item['symbol']}")
            c1.metric("ราคา", f"{item['price_thb']:,.2f} ฿")
            
            # AI Advice (ย้ายมาข้างบนเพื่อเป็นด่านหน้า)
            if item['color'] == "success": c2.success(item['advice'])
            elif item['color'] == "info": c2.info(item['advice'])
            else: c2.warning(item['advice'])

            # Chart
            fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
            fig.update_layout(height=120, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            # --- ระบบกรอกราคาและ Alert ---
            # ดึงค่าจาก session_state มาใส่ในช่อง Input ถ้ามี
            saved_cost = st.session_state.portfolio.get(item['symbol'], 0.0)
            entry_price = st.number_input(f"ระบุทุน {item['symbol']} (บาท):", value=float(saved_cost), key=f"in_{item['symbol']}")
            
            if entry_price > 0:
                # บันทึกลง Sidebar ทันที
                st.session_state.portfolio[item['symbol']] = entry_price
                
                # คำนวณกำไร/ขาดทุน
                diff = ((item['price_thb'] - entry_price) / entry_price) * 100
                
                # แสดงผลการวิเคราะห์ใต้ช่องกรอก
                if diff >= target_pct:
                    st.success(f"🚀 **SELL ALERT:** กำไรพุ่ง {diff:+.2f}% (ถึงเป้า {target_pct}%)")
                elif diff <= -stop_loss_pct:
                    st.error(f"🛑 **STOP LOSS:** ขาดทุน {diff:+.2f}% (ถึงจุดตัด {stop_loss_pct}%)")
                else:
                    st.info(f"📊 **Status:** กำไร {diff:+.2f}% (รันเทรนด์ต่อ)")

# Auto Refresh
time.sleep(REFRESH_SEC)
st.rerun()
