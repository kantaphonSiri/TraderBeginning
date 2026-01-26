import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor

# ------------------------
# 0. CONFIG & INITIAL SETUP
# ------------------------
REFRESH_SEC = 60 
st.set_page_config(page_title="👛 budget-bets", layout="wide")

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return res['rates']['THB']
    except:
        return 34.5

def calculate_rsi(prices, window=14):
    if len(prices) < window + 1: return 50
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).iloc[-1]

# 1. ฟังก์ชันดึงราคาเดี่ยวจาก Binance (ใช้ Thread ช่วยให้เร็วขึ้น)
def fetch_binance_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        res = requests.get(url, timeout=2).json()
        return symbol, float(res['price'])
    except:
        return symbol, None

# 2. ฟังก์ชันหลัก: ดึงข้อมูลแบบขนาน (Parallel)
def fetch_fast_data(budget_thb, usd_thb, is_filtering=False):
    try:
        # ดึงรายชื่อจาก DeFiLlama (Top 50)
        res = requests.get("https://api.llama.fi/protocols").json()
        candidates = [p.get('symbol').upper() for p in res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']][:50]
        
        # --- ขั้นตอนที่ 1: ดึงราคาทั้งหมดจาก Binance พร้อมกัน ---
        prices_dict = {}
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = executor.map(fetch_binance_price, candidates)
            prices_dict = {sym: price for sym, price in results if price is None or price > 0}

        # --- ขั้นตอนที่ 2: ดึงประวัติจาก Yahoo รอบเดียว (Batch Download) ---
        # การดึงแบบ Batch เร็วกว่าเรียกทีละตัว 10-20 เท่า
        yf_symbols = [f"{s}-USD" for s in candidates]
        all_hist = yf.download(yf_symbols, period="5d", interval="1h", group_by='ticker', progress=False)

        picks = []
        for sym in candidates:
            price_usd = prices_dict.get(sym)
            if not price_usd: continue
            
            p_thb = price_usd * usd_thb
            
            # ดึงประวัติราคาจากก้อนใหญ่ที่โหลดมาแล้ว
            try:
                hist = all_hist[f"{sym}-USD"]
            except:
                hist = pd.DataFrame()

            if not is_filtering:
                picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': hist})
            else:
                if p_thb <= budget_thb:
                    rsi_val = calculate_rsi(hist['Close'])
                    if 30 <= rsi_val <= 58:
                        picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': hist, 'rsi': rsi_val})
            
            if len(picks) >= 6: break
        return picks
    except Exception as e:
        st.error(f"Error: {e}")
        return []

# ------------------------
# 3. UI & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=0, step=500)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)

usd_thb = get_exchange_rate()
st.header(f"💱 เรท: {usd_thb:.2f} THB/USD")

is_filtering = budget > 0

with st.spinner("⚡ กำลังประมวลผลด้วยความเร็วสูง..."):
    display_items = fetch_fast_data(budget, usd_thb, is_filtering)

# --- DISPLAY ---
if not display_items:
    st.info("ไม่พบเหรียญที่ตรงเงื่อนไข")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคาปัจจุบัน", f"{item['price_thb']:,.2f} ฿")
                
                rsi_now = calculate_rsi(item['hist']['Close'])
                st.write(f"RSI: {rsi_now:.2f}")
                
                cost = st.number_input(f"ทุน {item['symbol']}:", key=f"c_{item['symbol']}", value=0.0)
                # ... (ส่วนคำนวณกำไรเหมือนเดิม) ...
                st.line_chart(item['hist']['Close'].tail(20), height=100)

st.divider()
time.sleep(REFRESH_SEC)
st.rerun()
