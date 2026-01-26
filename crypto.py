import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time

# --- CONFIG ---
st.set_page_config(page_title="Crypto Smart Picker", layout="wide")

# 1. ฟังก์ชันดึงเรทเงินบาท (Cache 1 ชม.)
@st.cache_data(ttl=3600)
def get_usd_thb():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return res['rates']['THB']
    except:
        return 34.5

# 2. ฟังก์ชันดึงข้อมูลราคา/RSI
def get_market_data(symbol):
    try:
        # ดึงราคาปัจจุบัน (เร็ว)
        price_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT"
        res = requests.get(price_url, timeout=5).json()
        price_usd = float(res['price'])
        
        # ดึงประวัติมาทำ RSI (ดึงเมื่อจำเป็น)
        t = yf.Ticker(f"{symbol}-USD")
        hist = t.history(period="1mo", interval="1h")
        return price_usd, hist
    except:
        return None, pd.DataFrame()

def calculate_rsi(df, periods=14):
    if len(df) < periods: return 50
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs.iloc[-1]))

# 3. Cache รายชื่อเหรียญ Top 30 (ดึงครั้งเดียวใช้ยาว)
@st.cache_data(ttl=600)
def get_top_30_symbols():
    try:
        res = requests.get("https://api.llama.fi/protocols").json()
        symbols = [p.get('symbol').upper() for p in res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']]
        return symbols[:30]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'DOT', 'AVAX', 'LINK', 'UNI']

# --- UI SIDEBAR ---
st.sidebar.header("⚙️ ตั้งค่าบอท")
budget = st.sidebar.number_input("งบต่อไม้ (THB)", value=5000)
line_token = st.sidebar.text_input("LINE Notify Token", type="password")

# --- MAIN UI ---
usd_thb = get_usd_thb()
st.title("🚀 Crypto Smart Scanner")
st.subheader(f"เรทปัจจุบัน: {usd_thb:.2f} THB/USD")

# ดึงรายชื่อเหรียญ Top 30 มาเตรียมไว้
top_30 = get_top_30_symbols()

# --- ส่วนที่ 1: โชว์ด่วน Top 6 (Instant Show) ---
st.markdown("### 🔥 ตลาดตอนนี้ (Top 6 Cap)")
quick_cols = st.columns(6)
for i, sym in enumerate(top_30[:6]):
    price, _ = get_market_data(sym)
    if price:
        with quick_cols[i]:
            st.metric(sym, f"{price * usd_thb:,.2f} ฿")

st.divider()

# --- ส่วนที่ 2: สแกนละเอียด (Filter Top 30) ---
st.markdown("### 🎯 คัดเหรียญเข้าเงื่อนไข (RSI 30-58)")

if st.button("เริ่มสแกนละเอียด Top 30"):
    with st.spinner('🔍 กำลังไล่เช็ค RSI และราคาทีละตัว...'):
        results = []
        # สร้าง Placeholder สำหรับ Logs สั้นๆ ให้คนดูไม่เบื่อ
        log_status = st.empty()
        
        for sym in top_30:
            log_status.text(f"กำลังเช็ค: {sym}...")
            price_usd, hist = get_market_data(sym)
            if price_usd:
                p_thb = price_usd * usd_thb
                if p_thb <= budget:
                    rsi_val = calculate_rsi(hist)
                    if 30 <= rsi_val <= 58:
                        results.append({'เหรียญ': sym, 'ราคา (บาท)': f"{p_thb:,.2f}", 'RSI': f"{rsi_val:.2f}"})
        
        log_status.empty() # ลบข้อความ Log ออกเมื่อเสร็จ
        
        if results:
            st.success(f"พบ {len(results)} เหรียญที่น่าสนใจ!")
            st.table(pd.DataFrame(results))
        else:
            st.warning("ยังไม่พบเหรียญที่ RSI อยู่ในช่วง 30-58 ภายใต้งบของคุณ")

st.caption(f"อัปเดตข้อมูลล่าสุด: {time.strftime('%H:%M:%S')} | ดึงจาก DeFiLlama & Binance")
