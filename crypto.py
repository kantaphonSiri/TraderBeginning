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
st.set_page_config(page_title="Budget-Bets Top 30 Scanner", layout="wide")

# 1. ดึงรายชื่อ Top 30 เหรียญตาม Market Cap จาก CoinGecko
@st.cache_data(ttl=3600)
def get_top_symbols(limit=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1&sparkline=false"
        response = requests.get(url, timeout=10)
        data = response.json()
        # แปลงชื่อ symbol ให้เป็นตัวใหญ่ (เช่น btc -> BTC)
        symbols = [coin['symbol'].upper() for coin in data]
        # กรองเหรียญ Stablecoins ที่เราไม่ต้องการเทรดออก (เช่น USDT, USDC)
        exclude = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USTC']
        return [s for s in symbols if s not in exclude]
    except Exception as e:
        # หาก API พัง ให้ใช้ลิสต์สำรอง
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'LINK', 'DOT', 'MATIC']

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
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).abs().rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.001))))
    # EMA & MACD
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
    else: score -= 2; reasons.append("เทรนด์ยังเป็นขาลง")
    if row['MACD'] > row['Signal']: score += 3; reasons.append("แรงซื้อสะสม (MACD Bullish)")
    
    if score >= 7: return "🔥 น่าซื้อสะสม", "success", reasons
    if score >= 4: return "⚖️ รอจังหวะย่อ", "info", reasons
    return "⚠️ เสี่ยง/รอไปก่อน", "warning", reasons

# ------------------------
# UI & SIDEBAR
# ------------------------
with st.sidebar:
    st.title("🎯 Smart Scanner")
    scan_limit = st.selectbox("เลือกจำนวนเหรียญที่ต้องการสแกน:", [30, 50, 100], index=0)
    budget = st.number_input("งบต่อ 1 เหรียญ (บาท):", min_value=0.0, value=None, placeholder="ว่างไว้เพื่อดูทั้งหมด...")
    st.divider()
    target_pct = st.slider("เป้าหมายกำไร (%)", 5, 100, 15)
    stop_loss_pct = st.slider("จุดตัดขาดทุน (%)", 3, 50, 7)
    
    if st.button("🔄 ล้างความจำ & โหลดใหม่", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

usd_thb = get_exchange_rate()
st.title("👛 Budget-Bets AI: Market Top Scanner")
st.write(f"💵 **Rate:** {usd_thb:.2f} THB/USD | อัปเดตล่าสุด: {datetime.now().strftime('%H:%M:%S')}")

# --- PROCESSING ---
top_symbols = get_top_symbols(limit=scan_limit)
scanned_items = []

with st.spinner(f"🤖 กำลังค้นหาเพชรในตมจาก Top {scan_limit} เหรียญ..."):
    progress_bar = st.progress(0)
    for idx, s in enumerate(top_symbols):
        try:
            # ดึงข้อมูลผ่าน yfinance
            df = yf.download(f"{s}-USD", period="1mo", interval="1h", progress=False)
            if not df.empty and len(df) > 20:
                df = add_indicators(df)
                price_thb = float(df['Close'].iloc[-1]) * usd_thb
                
                # กรองตามงบ (ถ้ามี)
                if budget is None or budget == 0 or price_thb <= budget:
                    advice, color, reasons = analyze_coin(df.iloc[-1])
                    scanned_items.append({
                        'symbol': s, 'price_thb': price_thb, 'df': df, 
                        'advice': advice, 'color': color, 'reasons': reasons
                    })
        except: continue
        progress_bar.progress((idx + 1) / len(top_symbols))

# --- DISPLAY ---
if not scanned_items:
    st.warning("⚠️ ไม่พบเหรียญที่ตรงตามเงื่อนไข ลองเพิ่มงบประมาณหรือปรับสแกน")
else:
    # แสดงเฉพาะเหรียญที่มีสัญญาณดี (Score สูง) ขึ้นก่อน
    st.subheader(f"📊 ผลการวิเคราะห์ ({len(scanned_items)} เหรียญที่ตรงงบ)")
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

                with st.expander("📝 รายละเอียดทางเทคนิค"):
                    for r in item['reasons']:
                        st.write(f"- {r}")

                fig = go.Figure(data=[go.Scatter(y=item['df']['Close'].tail(48), line=dict(color='#00ffcc'))])
                fig.update_layout(height=130, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                
                entry_p = st.number_input(f"ทุน {item['symbol']} (บาท):", key=f"c_{item['symbol']}", value=0.0)
                if entry_p > 0:
                    diff = ((item['price_thb'] - entry_p) / entry_p) * 100
                    if diff >= target_pct: st.success(f"🚀 ขายทำกำไร!: {diff:+.2f}%")
                    elif diff <= -stop_loss_pct: st.error(f"🛑 ตัดขาดทุน!: {diff:+.2f}%")

time.sleep(REFRESH_SEC)
st.rerun()
