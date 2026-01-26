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

# 1. ดึงเรทเงินบาท (Cache ไว้เพื่อความเร็ว)
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
        # ดึงราคาปัจจุบัน
        p_res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=3).json()
        price_usd = float(p_res['price'])
        
        # ดึง Klines 100 แท่ง (1h) เพื่อทำ RSI
        k_res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&limit=100", timeout=3).json()
        df = pd.DataFrame(k_res, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime', 'QuoteAssetVolume', 'NumTrades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'])
        df['Close'] = df['Close'].astype(float)
        
        return symbol, price_usd, df
    except:
        return symbol, None, pd.DataFrame()

# 4. ฟังก์ชันสแกนแบบรวดเร็ว (Multi-threading)
def fetch_fast_data(budget_thb, usd_thb, is_filtering=False):
    try:
        # ดึง Top 50 จาก DeFiLlama
        llama_res = requests.get("https://api.llama.fi/protocols").json()
        candidates = [p.get('symbol').upper() for p in llama_res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']][:50]
        
        picks = []
        # ใช้ ThreadPool ช่วยดึงข้อมูล Binance พร้อมกัน 10 เหรียญ
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_sym = {executor.submit(get_binance_data, s): s for s in candidates}
            
            for future in as_completed(future_to_sym):
                sym, price_usd, df = future.result()
                
                if price_usd and not df.empty:
                    p_thb = price_usd * usd_thb
                    
                    if not is_filtering:
                        # โหมดเริ่มต้น: เก็บ 6 ตัวแรกที่หาเจอ
                        picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': df})
                    else:
                        # โหมดกรองละเอียด: เช็ค Budget และ RSI
                        if p_thb <= budget_thb:
                            rsi_val = calculate_rsi(df['Close'])
                            if 30 <= rsi_val <= 58:
                                picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': df, 'rsi': rsi_val})
                
                # ถ้าได้ครบ 6 ตัวแล้วให้หยุดเพื่อความเร็ว
                if len(picks) >= 6: break
        return picks
    except Exception as e:
        st.error(f"Llama API Error: {e}")
        return []

# ------------------------
# UI & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Settings")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=0, step=500)
    st.info("💡 กรอกงบ > 0 เพื่อเริ่มระบบสแกน RSI")
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    
    if st.button("🔄 Refresh Now"):
        st.rerun()

usd_thb = get_exchange_rate()
st.header(f"💱 เรทบาทวันนี้: {usd_thb:.2f} THB/USD")

is_filtering = budget > 0

with st.spinner("⚡ กำลังดึงข้อมูลจาก Binance แบบ Real-time..."):
    display_items = fetch_fast_data(budget, usd_thb, is_filtering)

# --- DISPLAY ---
if not display_items:
    st.warning("⚠️ ไม่พบเหรียญที่ตรงเงื่อนไข (ลองเพิ่มงบหรือรอ RSI เข้าโซน)")
else:
    if is_filtering:
        st.subheader(f"🔍 ผลการกรอง (งบ ≤ {budget:,.0f} ฿)")
    else:
        st.subheader("🔥 Top Market Cap (เปิดมาเจอเลย)")

    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {item['symbol']}")
                st.metric("ราคาปัจจุบัน", f"{item['price_thb']:,.2f} ฿")
                
                rsi_now = calculate_rsi(item['hist']['Close'])
                rsi_col = "green" if 30 <= rsi_now <= 58 else "white"
                st.markdown(f"RSI (1h): <span style='color:{rsi_col}'>{rsi_now:.2f}</span>", unsafe_allow_html=True)
                
                # กราฟย้อนหลัง 24 ชม. (24 แท่งล่าสุด)
                st.line_chart(item['hist']['Close'].tail(24), height=120)
                
                # ระบบคำนวณกำไร
                cost = st.number_input(f"ทุน {item['symbol']} (฿):", key=f"c_{item['symbol']}", value=0.0)
                if cost > 0:
                    profit = ((item['price_thb'] - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร {profit:.2f}% (ถึงเป้า!)")
                    elif profit <= -stop_loss:
                        st.error(f"🛑 ขาดทุน {profit:.2f}%")
                    else:
                        st.info(f"📊 กำไร: {profit:.2f}%")

st.divider()
st.caption(f"อัปเดตอัตโนมัติทุก {REFRESH_SEC} วินาที | ข้อมูลตรงจาก Binance API")

# Auto-refresh logic
time.sleep(REFRESH_SEC)
st.rerun()
