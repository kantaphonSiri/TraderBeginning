import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------
# 0. CONFIG & INITIAL SETUP
# ------------------------
REFRESH_SEC = 60 
st.set_page_config(page_title="👛 budget-bets (MEXC Feed)", layout="wide")

# 1. ดึงเรทเงินบาท (ดึงจาก ExchangeRate API)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5).json()
        return res['rates']['THB']
    except:
        return 35.0  # ค่าสำรองกรณี API เงินบาทล่ม

# 2. คำนวณ RSI
def calculate_rsi(prices, window=14):
    if len(prices) < window + 1: return 50
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, 0.001) # ป้องกันหารศูนย์
    return (100 - (100 / (1 + rs))).iloc[-1]

# 3. ดึงข้อมูลจาก MEXC (ใช้แทน Binance เพื่อให้รันบน Cloud ได้)
def get_mexc_data(symbol):
    sym = symbol.upper() + "USDT"
    try:
        # ดึงราคาล่าสุด
        p_res = requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={sym}", timeout=5).json()
        price_usd = float(p_res['price'])
        
        # ดึงกราฟ 1h (K-lines)
        # interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d
        k_res = requests.get(f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval=1h&limit=50", timeout=5).json()
        
        df = pd.DataFrame(k_res, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime', 'QuoteAssetVolume'])
        df['Close'] = df['Close'].astype(float)
        
        return symbol, price_usd, df
    except:
        return symbol, None, pd.DataFrame()

# 4. สแกนเหรียญ (เน้นเหรียญหลักเพื่อความเร็ว)
@st.cache_data(ttl=300)
def fetch_smart_picks(budget_thb, usd_thb, is_filtering=False):
    # รายชื่อเหรียญตัวอย่าง (MEXC มีเกือบทุกเหรียญเหมือน Binance)
    candidates = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX', 'DOGE', 'LINK', 'MATIC', 'OP', 'ARB', 'NEAR', 'SUI']
    
    picks = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_sym = {executor.submit(get_mexc_data, s): s for s in candidates}
        
        for future in as_completed(future_to_sym):
            sym, price_usd, df = future.result()
            if price_usd and not df.empty:
                p_thb = price_usd * usd_thb
                
                # ถ้ามีการตั้งงบ ให้กรองตามงบ
                if not is_filtering or p_thb <= budget_thb:
                    rsi_val = calculate_rsi(df['Close'])
                    picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': df, 'rsi': rsi_val})
            
            if len(picks) >= 9: break # แสดงสูงสุด 9 เหรียญ
    return picks

# ------------------------
# UI & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อ 1 เหรียญ (บาท):", min_value=0, value=50000, step=1000)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    
    if st.button("🔄 ล้าง Cache & สแกนใหม่"):
        st.cache_data.clear()
        st.rerun()

usd_thb = get_exchange_rate()
st.header(f"💱 เรทบาท: {usd_thb:.2f} THB/USD (Data from MEXC)")

is_filtering = budget > 0

with st.spinner("⚡ กำลังวิเคราะห์กราฟจาก MEXC..."):
    display_items = fetch_smart_picks(budget, usd_thb, is_filtering)

# --- DISPLAY ---
if not display_items:
    st.warning("⚠️ ไม่พบเหรียญที่ตรงเงื่อนไข ลองเพิ่มงบประมาณ")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคาปัจจุบัน", f"{item['price_thb']:,.2f} ฿")
                
                rsi_now = item['rsi']
                # ไฮไลท์ RSI ถ้าอยู่ในจุดน่าซื้อ (30-40)
                color = "#00FF00" if rsi_now <= 40 else "#FFFFFF"
                st.markdown(f"RSI (1h): <span style='color:{color}; font-size:20px;'>{rsi_now:.2f}</span>", unsafe_allow_html=True)
                
                # แสดงกราฟเส้น
                st.line_chart(item['hist']['Close'].tail(24), height=150)
                
                # ส่วนคำนวณกำไร/ขาดทุน
                cost = st.number_input(f"ราคาที่ซื้อ {item['symbol']} (฿):", key=f"c_{item['symbol']}", value=0.0)
                if cost > 0:
                    profit = ((item['price_thb'] - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร: {profit:.2f}%")
                    elif profit <= -stop_loss:
                        st.error(f"🛑 ขาดทุน: {profit:.2f}%")
                    else:
                        st.info(f"📊 ผลตอบแทน: {profit:.2f}%")

st.divider()
st.caption(f"Update ทุก {REFRESH_SEC} วินาที | ข้อมูลราคาจาก MEXC Global")

# --- AUTO REFRESH ---
time.sleep(REFRESH_SEC)
st.rerun()
