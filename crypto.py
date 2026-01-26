import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time

# ------------------------
# 0. CONFIG & INITIAL SETUP
# ------------------------
REFRESH_SEC = 60 
st.set_page_config(page_title="👛 budget-bets", layout="wide")

# 1. ฟังก์ชันดึงเรทเงินบาท (ใช้ API สำรองที่เสถียรกว่า)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return res['rates']['THB']
    except:
        return 34.5

# 2. ดึงราคาจาก Binance (เร็ว) และประวัติจาก Yahoo (สำหรับ RSI)
def get_market_data(symbol):
    try:
        # ดึงราคาปัจจุบันจาก Binance
        res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT", timeout=2).json()
        price_usd = float(res['price'])
        
        # ดึงข้อมูลย้อนหลัง 1 เดือน (1h interval) เพื่อคำนวณ RSI
        t = yf.Ticker(f"{symbol}-USD")
        hist = t.history(period="1mo", interval="1h")
        return price_usd, hist
    except:
        return None, pd.DataFrame()

def calculate_rsi(data, window=14):
    if data.empty or len(data) < window: return 50
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).iloc[-1]

# 3. ฟังก์ชันสแกนเหรียญ (ดึง Top 50 มากรอง)
def fetch_smart_picks(budget_thb, usd_thb, is_filtering=False):
    try:
        res = requests.get("https://api.llama.fi/protocols").json()
        # กรอง Stablecoins ออก
        candidates = [p for p in res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']]
        # เอาตัวที่มี TVL สูงสุด 50 ตัวแรก
        candidates = sorted(candidates, key=lambda x: x.get('tvl', 0), reverse=True)[:50]
        
        picks = []
        for c in candidates:
            sym = c.get('symbol').upper()
            
            # ถ้ายังไม่ได้กรอกงบ (budget_thb เป็น None หรือ 0) ให้เอาแค่ 6 ตัวแรกไปโชว์เลย
            if not is_filtering:
                price_usd, hist = get_market_data(sym)
                if price_usd:
                    picks.append({'symbol': sym, 'price_thb': price_usd * usd_thb, 'hist': hist})
                if len(picks) >= 6: break
            else:
                # ถ้ามีการกรอกงบแล้ว ให้เริ่มกรองตามเงื่อนไข RSI และ Budget
                price_usd, hist = get_market_data(sym)
                if price_usd:
                    p_thb = price_usd * usd_thb
                    if p_thb <= budget_thb:
                        rsi_val = calculate_rsi(hist)
                        if 30 <= rsi_val <= 58:
                            picks.append({'symbol': sym, 'price_thb': p_thb, 'hist': hist, 'rsi': rsi_val})
                if len(picks) >= 6: break
        return picks
    except: return []

# ------------------------
# 3. SIDEBAR & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Personal Settings")
    user_line_id = st.text_input("ระบุ LINE User ID", type="password")
    
    st.divider()
    st.subheader("⚙️ Strategy Control")
    # ปรับ Budget เริ่มต้นเป็น 0 เพื่อเช็คว่า User กรอกหรือยัง
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=0, value=0, step=500, help="กรอกงบเพื่อเริ่มระบบกรองละเอียด")
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)

# ------------------------
# 4. DASHBOARD UI
# ------------------------
usd_thb = get_exchange_rate()
st.header(f"💱 เรทเงินบาทวันนี้: {usd_thb:.2f} THB/USD")

# ตรวจสอบว่า User กรอกงบหรือยัง
is_filtering = budget > 0

with st.spinner("🎯 " + ("กำลังกรองเหรียญ RSI สวยๆ..." if is_filtering else "กำลังโหลดเหรียญยอดฮิต...")):
    display_items = fetch_smart_picks(budget, usd_thb, is_filtering=is_filtering)

if is_filtering:
    st.subheader(f"🔍 ผลการกรอง (งบ {budget:,.0f} ฿ + RSI 30-58)")
else:
    st.subheader("🔥 Top 6 Market Cap (รอคุณกรอกงบเพื่อกรองละเอียด)")

if not display_items:
    st.info("ไม่พบเหรียญที่ตรงเงื่อนไขในขณะนี้")
else:
    cols = st.columns(3)
    for idx, item in enumerate(display_items):
        sym = item['symbol']
        p_thb = item['price_thb']
        hist = item['hist']
        
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(f"🪙 {sym}")
                st.metric("ราคาปัจจุบัน", f"{p_thb:,.2f} ฿")
                
                # คำนวณ RSI โชว์
                rsi_now = calculate_rsi(hist)
                rsi_col = "green" if rsi_now < 45 else "orange" if rsi_now < 60 else "red"
                st.markdown(f"RSI (1h): <span style='color:{rsi_col}'>{rsi_now:.2f}</span>", unsafe_allow_html=True)

                # ช่องใส่ต้นทุน
                cost = st.number_input(f"ทุน {sym} (฿):", key=f"c_{sym}", value=0.0)
                if cost > 0:
                    profit = ((p_thb - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร {profit:.2f}% (ถึงเป้า!)")
                    elif profit <= -stop_loss:
                        st.error(f"🛑 ขาดทุน {profit:.2f}%")
                    else:
                        st.info(f"📊 กำไร: {profit:.2f}%")
                
                st.line_chart(hist['Close'].tail(30), height=100)

# ------------------------
# 5. FOOTER & AUTO-REFRESH
# ------------------------
st.divider()
st.caption(f"อัปเดตทุก {REFRESH_SEC} วินาที | กรอง Top 50 ลำดับแรกจาก DeFiLlama")

time.sleep(REFRESH_SEC)
st.rerun()
