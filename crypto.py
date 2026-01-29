import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. CONFIG & CONNECTION
# ---------------------------------------------------------
# นำ Link CSV จาก Google Sheets (Publish to Web) มาวางที่นี่
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"

st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# Auto Refresh ทุก 1 นาที (60,000 ms) - Binance API ทนทานมาก รันถี่ได้
st_autorefresh(interval=60000, key="binance_refresh")

# CSS บังคับ 2 คอลัมน์บนมือถือ
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    @media (max-width: 640px) { .stMarkdown div p, .stMetric div { font-size: 12px !important; } h3 { font-size: 16px !important; } }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. CORE FUNCTIONS (BINANCE & GOOGLE SHEETS)
# ---------------------------------------------------------
def get_thb_rate():
    try:
        # ดึงราคา USDT/THB จาก Binance P2P หรือใช้ API อ้างอิง (ตัวอย่างใช้ค่ากลางคงที่หรือดึงจาก API อื่น)
        return 35.5 # ปรับให้ดึงจาก API อัตราแลกเปลี่ยนได้
    except: return 35.0

def get_binance_data(symbols):
    results = {}
    try:
        # ดึงราคาทั้งหมดในครั้งเดียวเพื่อความเร็ว
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
        df_all = pd.DataFrame(res)
        rate = get_thb_rate()
        
        for s in symbols:
            pair = f"{s}USDT"
            row = df_all[df_all['symbol'] == pair]
            if not row.empty:
                results[s] = {
                    'price': float(row['lastPrice'].values[0]) * rate,
                    'change': float(row['priceChangePercent'].values[0]),
                    'high': float(row['highPrice'].values[0]) * rate,
                    'low': float(row['lowPrice'].values[0]) * rate
                }
    except Exception as e:
        st.error(f"Binance Error: {e}")
    return results, rate

def load_portfolio():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip().str.lower()
        return df.to_dict('records')
    except: return []

# ---------------------------------------------------------
# 3. UI - SIDEBAR PORTFOLIO
# ---------------------------------------------------------
portfolio_data = load_portfolio()
pinned_symbols = [str(item['symbol']).upper() for item in portfolio_data]
market_data, usd_thb = get_binance_data(pinned_symbols if pinned_symbols else ['BTC', 'ETH', 'SOL'])

with st.sidebar:
    st.title("💼 My Portfolio")
    if portfolio_data:
        total_cost, total_value = 0, 0
        for item in portfolio_data:
            sym = str(item['symbol']).upper()
            if sym in market_data:
                current_p = market_data[sym]['price']
                val = current_p # สมมติว่าใน Sheets คือราคาทุนต่อ 1 หน่วย
                total_cost += item['cost']
                total_value += current_p 
        
        diff = total_value - total_cost
        pct = (diff / total_cost * 100) if total_cost > 0 else 0
        
        st.metric("กำไร/ขาดทุนรวม", f"{diff:,.2f} ฿", f"{pct:+.2f}%")
        
        # รายชื่อเหรียญที่ Pin ไว้
        for item in portfolio_data:
            sym = item['symbol'].upper()
            if sym in market_data:
                p = market_data[sym]
                st.write(f"**{sym}**: {p['price']:,.2f} ({p['change']:+.2f}%)")
    
    if st.button("🔄 Force Sync Sheets", use_container_width=True):
        st.rerun()

# ---------------------------------------------------------
# 4. MAIN UI - MARKET MONITOR
# ---------------------------------------------------------
st.title("🪙 Budget-bet")
st.caption(f"🚀 ข้อมูล Real-time จาก Binance API | Rate: 1 USD = {usd_thb} THB")

cols = st.columns(2)
display_coins = pinned_symbols if pinned_symbols else ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']

for idx, sym in enumerate(display_coins[:10]):
    if sym in market_data:
        data = market_data[sym]
        with cols[idx % 2]:
            with st.container(border=True):
                st.subheader(sym)
                st.metric("ราคา (บาท)", f"{data['price']:,.2f}", f"{data['change']:+.2f}%")
                st.caption(f"High: {data['high']:,.0f} | Low: {data['low']:,.0f}")
                
                # ถ้าถึงเป้าใน Sheets ให้ขึ้นเตือน
                if pinned_symbols and sym in pinned_symbols:
                    target = next(i['target'] for i in portfolio_data if i['symbol'].upper() == sym)
                    cost = next(i['cost'] for i in portfolio_data if i['symbol'].upper() == sym)
                    profit_now = ((data['price'] - cost) / cost) * 100
                    if profit_now >= target:
                        st.success(f"🎯 ถึงเป้ากำไร! ({profit_now:.1f}%)")
