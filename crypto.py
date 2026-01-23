import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time

# ------------------------
# 0. CONFIG & INITIAL SETUP
# ------------------------
LINE_TOKEN = st.secrets["LINE_TOKEN"]
REFRESH_SEC = 60 

st.set_page_config(page_title="🚀 Smart Portfolio Builder", layout="wide")

# ------------------------
# 1. CORE ENGINE (ระบบหลังบ้าน)
# ------------------------

@st.cache_data(ttl=3600) # ดึงค่าเงินบาทชั่วโมงละครั้งพอ
def get_exchange_rate():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.info.get('regularMarketPrice') or ticker.info.get('previousClose')
        return rate if rate else 35.0
    except: return 35.0

def calculate_rsi(data, window=14):
    if len(data) < window: return 50 # ค่ากลางถ้าข้อมูลไม่พอ
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).iloc[-1]

def send_line_notification(message):
    if not LINE_TOKEN or LINE_TOKEN == "ใส่_TOKEN_ของคุณที่นี่": return
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {LINE_TOKEN}'}
    data = {'message': message}
    try: requests.post(url, headers=headers, data=data)
    except: pass

def get_market_data(symbol, is_crypto=True):
    ticker_sym = f"{symbol}-USD" if is_crypto else symbol
    try:
        t = yf.Ticker(ticker_sym)
        p = t.info.get('regularMarketPrice') or t.info.get('currentPrice')
        h = t.history(period="1mo", interval="1h")
        if p and not h.empty:
            return p, h
    except: pass
    return None, pd.DataFrame()

# ------------------------
# 2. SMART FILTER LOGIC (ระบบกรองเทพ)
# ------------------------

@st.cache_data(ttl=300) # จำรายชื่อเหรียญไว้ 5 นาที
def fetch_smart_picks(budget_thb, usd_thb):
    try:
        # ดึง Top 50 จาก DeFiLlama เพื่อความหลากหลาย
        res = requests.get("https://api.llama.fi/protocols").json()
        candidates = [p for p in res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']]
        candidates = sorted(candidates, key=lambda x: x.get('tvl', 0), reverse=True)[:40]
        
        picks = []
        for c in candidates:
            sym = c.get('symbol').upper()
            price_usd, hist = get_market_data(sym)
            
            if price_usd:
                p_thb = price_usd * usd_thb
                # กรอง 1: งบประมาณ (Budget)
                if p_thb <= budget_thb:
                    rsi_val = calculate_rsi(hist)
                    # กรอง 2: RSI (ต้นน้ำ/พักตัว 30-58)
                    if 30 <= rsi_val <= 58:
                        picks.append({'symbol': sym, 'price_thb': p_thb, 'rsi': rsi_val})
            
            if len(picks) >= 6: break
        return picks
    except: return []

# ------------------------
# 3. SIDEBAR & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Strategy Control")
    budget = st.number_input("งบต่อไม้ (บาท):", min_value=100, value=2000, step=500)
    target_pct = st.slider("เป้ากำไร (%)", 5, 100, 15)
    stop_loss = st.slider("จุดตัดขาดทุน (%)", 3, 30, 7)
    
    st.divider()
    if st.button("🔄 ล้างข้อมูลการแจ้งเตือน"):
        st.session_state.clear()
        st.rerun()

# ------------------------
# 4. DASHBOARD UI
# ------------------------
usd_thb = get_exchange_rate()
st.header(f"💱 เรทเงินบาทวันนี้: {usd_thb:.2f} THB/USD")

# ดึงเหรียญที่ Pinned (มีต้นทุน)
pinned_symbols = [k.split("_")[1] for k, v in st.session_state.items() if k.startswith("c_") and v > 0]

# ดึงเหรียญแนะนำจากระบบ
with st.spinner("ระบบกำลังสแกนหาเหรียญที่ 'งบพอดี + กราฟสวย'..."):
    smart_items = fetch_smart_picks(budget, usd_thb)
    smart_symbols = [item['symbol'] for item in smart_items]

# รวมรายการ (Pinned ขึ้นก่อน)
final_list = list(dict.fromkeys(pinned_symbols + smart_symbols))[:6]

# แสดงผลในรูปแบบ Grid
cols = st.columns(3)
for idx, sym in enumerate(final_list):
    price_usd, hist = get_market_data(sym)
    with cols[idx % 3]:
        with st.container(border=True):
            if price_usd:
                p_thb = price_usd * usd_thb
                rsi_now = calculate_rsi(hist)
                
                # หัวข้อและป้ายสถานะ
                status_emoji = "📌" if sym in pinned_symbols else "🔎"
                st.subheader(f"{status_emoji} {sym}")
                st.metric("ราคาปัจจุบัน", f"{p_thb:,.2f} ฿")
                
                # วิเคราะห์ RSI
                rsi_col = "green" if rsi_now < 40 else "orange" if rsi_now < 60 else "red"
                st.markdown(f"RSI (1h): <span style='color:{rsi_col}'>{rsi_now:.2f}</span>", unsafe_allow_html=True)

                # กรอกต้นทุน
                cost = st.number_input(f"ทุน {sym} (฿):", key=f"c_{sym}", value=0.0)
                
                if cost > 0:
                    profit = ((p_thb - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร {profit:.2f}% (ถึงเป้า!)")
                        send_line_notification(f"\n💰 [{sym}] ถึงเป้าขาย!\nกำไร: {profit:.2f}%\nราคา: {p_thb:,.2f} ฿")
                    elif profit <= -stop_loss:
                        st.error(f"🛑 ขาดทุน {profit:.2f}% (จุดตัดใจ)")
                    else:
                        st.info(f"📊 กำไร: {profit:.2f}%")
                
                st.line_chart(hist['Close'].tail(30), height=100)
            else:
                st.warning(f"⚠️ {sym}: โหลดข้อมูลไม่สำเร็จ")

# ------------------------
# 5. FOOTER & AUTO-REFRESH
# ------------------------
st.divider()
st.caption(f"ระบบอัปเดตอัตโนมัติทุก {REFRESH_SEC} วินาที | เหรียญที่แสดงกรองจาก งบ <= {budget:,.0f} ฿ และ RSI 30-58")

time.sleep(REFRESH_SEC)

st.rerun()
