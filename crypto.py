import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------
# 0. CONFIG & INITIAL SETUP
# ------------------------
REFRESH_SEC = 60 
st.set_page_config(page_title="👛 budget-bets", layout="wide")

# 1. ดึงเรทเงินบาท (จำไว้ 1 ชม.)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return res['rates']['THB']
    except:
        return 34.5

# 2. คำนวณ RSI
def calculate_rsi(prices, window=14):
    if len(prices) < window + 1: return 50
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).iloc[-1]

# 3. ดึงข้อมูลจาก Binance (ราคาปัจจุบัน + กราฟ 1h)
def get_binance_data(symbol):
    try:
        sym = symbol.upper() + "USDT"
        p_res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=3).json()
        price_usd = float(p_res['price'])
        
        k_res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&limit=100", timeout=3).json()
        df = pd.DataFrame(k_res, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime', 'QuoteAssetVolume', 'NumTrades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'])
        df['Close'] = df['Close'].astype(float)
        
        return symbol, price_usd, df
    except:
        return symbol, None, pd.DataFrame()

# 4. ฟังก์ชันสแกนหลัก (ใส่ CACHE เพื่อไม่ให้รีเฟรชแล้วต้องเริ่มใหม่)
@st.cache_data(ttl=300) # จำรายชื่อเหรียญที่ผ่านการกรองไว้ 5 นาที
def fetch_smart_picks(budget_thb, usd_thb, is_filtering=False):
    try:
        llama_res = requests.get("https://api.llama.fi/protocols").json()
        candidates = [p.get('symbol').upper() for p in llama_res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']][:50]
        
        picks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_sym = {executor.submit(get_binance_data, s): s for s in candidates}
            
            for future in as_completed(future_to_sym):
                sym, price_usd, df = future.result()
                if price_usd and not df.empty:
                    p_thb = price_usd * usd_thb
                    if not is_filtering:
                        picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': df})
                    else:
                        if p_thb <= budget_thb:
                            rsi_val = calculate_rsi(df['Close'])
                            # if 30 <= rsi_val <= 58:
                            if 0 <= rsi_val <= 100:
                                picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': df, 'rsi': rsi_val})
                if len(picks) >= 6: break
        return picks
    except:
        return []

# ------------------------
# UI & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=2000, step=500)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    
    # ปุ่มล้าง Cache กรณีอยากสแกนสดๆ ทันที
    if st.button("🔄 ล้างความจำและสแกนใหม่"):
        st.cache_data.clear()
        st.rerun()

usd_thb = get_exchange_rate()
st.header(f"💱 เรทบาทวันนี้: {usd_thb:.2f} THB/USD")

is_filtering = budget > 0

# ใช้ Spinner บอกสถานะ
with st.spinner("⚡ กำลังวิเคราะห์ข้อมูล (ใช้ระบบจำค่าล่าสุดเพื่อให้แอปไหลลื่น)..."):
    # หมายเหตุ: Streamlit จะจำค่า budget และ is_filtering ไว้ใน Cache Key
    display_items = fetch_smart_picks(budget, usd_thb, is_filtering)

# --- DISPLAY ---
if not display_items:
    st.warning("⚠️ ไม่พบเหรียญที่ตรงเงื่อนไข ลองเพิ่มงบหรือกด 'สแกนใหม่' ที่ Sidebar")
else:
    st.subheader("🔍 ผลการสแกน" if is_filtering else "🔥 เหรียญยอดฮิต")
    
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคา", f"{item['price_thb']:,.2f} ฿")
                
                rsi_now = calculate_rsi(item['hist']['Close'])
                rsi_col = "green" if 30 <= rsi_now <= 58 else "white"
                st.markdown(f"RSI (1h): <span style='color:{rsi_col}'>{rsi_now:.2f}</span>", unsafe_allow_html=True)
                
                st.line_chart(item['hist']['Close'].tail(24), height=100)
                
                # ระบบคำนวณกำไร (ใช้ Session State เพื่อให้ค่าไม่หายตอนรีเฟรช)
                cost = st.number_input(f"ทุน {item['symbol']} (฿):", key=f"c_{item['symbol']}", value=0.0)
                if cost > 0:
                    profit = ((item['price_thb'] - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร {profit:.2f}%")
                    elif profit <= -stop_loss:
                        st.error(f"🛑 ขาดทุน {profit:.2f}%")
                    else:
                        st.info(f"📊 {profit:.2f}%")

st.divider()
st.caption(f"หน้านี้จะอัปเดตราคา/กราฟใน 60 วิ | รายชื่อเหรียญจะเปลี่ยนใหม่ทุก 5 นาที")

# --- AUTO REFRESH ---
time.sleep(REFRESH_SEC)
st.rerun()


