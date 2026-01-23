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

# ------------------------
# 1. CORE ENGINE (ระบบหลังบ้าน)
# ------------------------

# 1. แก้ดึงเรทเงินบาท (ใช้ API ของ ExchangeRate-Host แทน)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        # ใช้ API ที่เสถียรกว่า Yahoo ในช่วงนี้
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return res['rates']['THB']
    except:
        return 34.5  # ใส่เลขปัจจุบันไปเลย ดีกว่า 35.00

def calculate_rsi(data, window=14):
    if len(data) < window: return 50 # ค่ากลางถ้าข้อมูลไม่พอ
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).iloc[-1]

def send_line_notification(message, target_user_id):
    # ตรวจสอบว่ามีข้อมูลครบไหม
    if not target_user_id:
        return
    
    # ดึงค่า TOKEN จาก Secrets (ตัวแม่ตัวเดียวใช้ทั้งแอป)
    try:
        CHANNEL_ACCESS_TOKEN = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]
    except:
        st.error("กรุณาตั้งค่า LINE_CHANNEL_ACCESS_TOKEN ใน Streamlit Secrets")
        return

    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    data = {
        "to": target_user_id,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        pass

def get_market_data(symbol):
    try:
        # ดึงราคาตรงจาก Binance (เร็วและไม่ค่อยโดนบล็อก)
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        res = requests.get(url).json()
        price_usd = float(res['price'])
        
        # สำหรับกราฟ RSI ยังใช้ Yahoo ได้ (เพราะดึงแค่ครั้งเดียว) 
        # หรือถ้าไม่อยากเสี่ยง ให้ข้ามการเช็ค RSI ไปก่อนเพื่อดูว่าเหรียญขึ้นไหม
        return price_usd, pd.DataFrame() 
    except:
        return None, pd.DataFrame()

# ------------------------
# 2. SMART FILTER LOGIC (ระบบกรองเทพ)
# ------------------------

@st.cache_data(ttl=300) # จำรายชื่อเหรียญไว้ 5 นาที
def fetch_smart_picks(budget_thb, usd_thb):
    try:
        res = requests.get("https://api.llama.fi/protocols").json()
        candidates = [p for p in res if p.get('symbol') and p.get('symbol').upper() not in ['USDT', 'USDC', 'DAI']]
        candidates = sorted(candidates, key=lambda x: x.get('tvl', 0), reverse=True)[:40]
        
        picks = []
        for c in candidates:
            sym = c.get('symbol').upper()
            price_usd, hist = get_market_data(sym)
            
            if price_usd:
                p_thb = price_usd * usd_thb
                if p_thb <= budget_thb:
                    rsi_val = calculate_rsi(hist)
                    if 30 <= rsi_val <= 58:
                    # if 0 <= rsi_val <= 100: #test_perfomance
                        picks.append({'symbol': sym, 'price_thb': p_thb, 'rsi': rsi_val})
            
            if len(picks) >= 6: break
        return picks
    except: return []

# ------------------------
# 3. SIDEBAR & CONTROL
# ------------------------
with st.sidebar:
    st.title("🎯 Personal Settings")
    
    # รับ USER ID แยกแต่ละคน
    user_line_id = st.text_input(
        "ระบุ LINE User ID เพื่อรับแจ้งเตือน", 
        type="password",
        help="หาได้จากหน้า Basic Settings ใน LINE Developers ของคุณ"
    )
    
    st.divider()
    st.subheader("⚙️ Strategy Control")
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

pinned_symbols = [k.split("_")[1] for k, v in st.session_state.items() if k.startswith("c_") and v > 0]

with st.spinner("ระบบกำลังสแกนหาเหรียญที่ 'งบพอดี + กราฟสวย'..."):
    smart_items = fetch_smart_picks(budget, usd_thb)
    smart_symbols = [item['symbol'] for item in smart_items]

final_list = list(dict.fromkeys(pinned_symbols + smart_symbols))[:6]

cols = st.columns(3)
for idx, sym in enumerate(final_list):
    price_usd, hist = get_market_data(sym)
    with cols[idx % 3]:
        with st.container(border=True):
            if price_usd:
                p_thb = price_usd * usd_thb
                rsi_now = calculate_rsi(hist)
                
                status_emoji = "📌" if sym in pinned_symbols else "🔎"
                st.subheader(f"{status_emoji} {sym}")
                st.metric("ราคาปัจจุบัน", f"{p_thb:,.2f} ฿")
                
                rsi_col = "green" if rsi_now < 40 else "orange" if rsi_now < 60 else "red"
                st.markdown(f"RSI (1h): <span style='color:{rsi_col}'>{rsi_now:.2f}</span>", unsafe_allow_html=True)

                cost = st.number_input(f"ทุน {sym} (฿):", key=f"c_{sym}", value=0.0)
                
                if cost > 0:
                    profit = ((p_thb - cost) / cost) * 100
                    if profit >= target_pct:
                        st.success(f"🚀 กำไร {profit:.2f}% (ถึงเป้า!)")
                        # ส่งแจ้งเตือนไปยัง ID ที่กรอกใน Sidebar
                        msg = f"\n💰 [{sym}] ถึงเป้าขาย!\nกำไร: {profit:.2f}%\nราคา: {p_thb:,.2f} ฿"
                        send_line_notification(msg, user_line_id)
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





