import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------
# 0. CONFIG
# ------------------------
REFRESH_SEC = 60 
st.set_page_config(page_title="👛 budget-bets", layout="wide")

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5).json()
        return res['rates']['THB']
    except Exception as e:
        st.error(f"Error fetching rate: {e}")
        return 34.5

# ปรับปรุงการดึงข้อมูล Binance ให้รองรับการตรวจสอบ Error
def get_binance_data(symbol):
    sym = symbol.upper() + "USDT"
    base_url = "https://api.binance.com/api/v3"
    try:
        # ดึงราคา
        p_res = requests.get(f"{base_url}/ticker/price?symbol={sym}", timeout=5)
        if p_res.status_code != 200:
            return symbol, None, None
        
        price_usd = float(p_res.json()['price'])
        
        # ดึงกราฟ
        k_res = requests.get(f"{base_url}/klines?symbol={sym}&interval=1h&limit=50", timeout=5)
        if k_res.status_code != 200:
            return symbol, price_usd, pd.DataFrame()
            
        df = pd.DataFrame(k_res.json(), columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime', 'QuoteAssetVolume', 'NumTrades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'])
        df['Close'] = df['Close'].astype(float)
        return symbol, price_usd, df
    except:
        return symbol, None, None

def calculate_rsi(prices, window=14):
    if prices is None or len(prices) < window + 1: return 50
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    # ป้องกันหารด้วยศูนย์
    rs = gain / loss.replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

@st.cache_data(ttl=300)
def fetch_smart_picks(budget_thb, usd_thb, is_filtering=False):
    # เปลี่ยนมาใช้เหรียญยอดนิยมแทนการดึงจาก DefiLlama ทั้งหมดเพื่อความเสถียรบน Cloud
    common_symbols = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOT', 'AVAX', 'DOGE', 'LINK', 'MATIC', 'OP', 'ARB']
    
    picks = []
    # ลด Workers ลงเพื่อไม่ให้โดน Binance แบน IP
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_sym = {executor.submit(get_binance_data, s): s for s in common_symbols}
        
        for future in as_completed(future_to_sym):
            sym, price_usd, df = future.result()
            if price_usd and df is not None and not df.empty:
                p_thb = price_usd * usd_thb
                
                # เงื่อนไขตัวกรอง
                if not is_filtering or p_thb <= budget_thb:
                    rsi_val = calculate_rsi(df['Close'])
                    picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': df, 'rsi': rsi_val})
            
            if len(picks) >= 9: break # จำกัดจำนวนการแสดงผล
    return picks

# --- UI ---
usd_thb = get_exchange_rate()
st.header(f"💱 เรทบาทวันนี้: {usd_thb:.2f} THB/USD")

with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=50000, step=1000)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    if st.button("🔄 สแกนใหม่"):
        st.cache_data.clear()
        st.rerun()

is_filtering = budget > 0

with st.spinner("🔍 กำลังค้นหาเหรียญจาก Binance..."):
    display_items = fetch_smart_picks(budget, usd_thb, is_filtering)

if not display_items:
    st.error("❌ ดึงข้อมูลจาก Binance ไม่ได้ (อาจโดนจำกัดการเข้าถึงจาก Cloud)")
    st.info("แนะนำ: ลองกด 'สแกนใหม่' หรือรอ 1-2 นาทีเพื่อให้ IP คลายล็อค")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคา", f"{item['price_thb']:,.2f} ฿")
                rsi_val = item['rsi']
                st.write(f"RSI (1h): {rsi_val:.2f}")
                st.line_chart(item['hist']['Close'].tail(24), height=100)

# --- REFRESH ---
st.divider()
st.caption("Auto-refreshing in 60s...")
time.sleep(REFRESH_SEC)
st.rerun()
