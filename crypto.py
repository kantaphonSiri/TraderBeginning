import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=936509889&single=true&output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Analyzer Pro", layout="wide")

# --- INITIALIZE SESSION STATE ---
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []
if 'buy_prices' not in st.session_state: st.session_state.buy_prices = {}

# 2. ULTRA-STABLE DATA ENGINE (Binance + Gate.io Fallback)
def get_market_data():
    # แผน A: Binance
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=3)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'])
            df['change'] = pd.to_numeric(df['priceChangePercent'])
            df['volume'] = pd.to_numeric(df['quoteVolume'])
            return df[['symbol', 'price', 'change', 'volume']].dropna(), "Binance (Main)"
    except: pass

    # แผน B: Gate.io (เสถียรมากสำหรับ Cloud)
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=3)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['symbol'] = df['currency_pair'].str.replace('_', '')
            df['price'] = pd.to_numeric(df['last'])
            df['change'] = pd.to_numeric(df['change_percentage'])
            df['volume'] = pd.to_numeric(df['quote_volume'])
            return df[['symbol', 'price', 'change', 'volume']].dropna(), "Gate.io (Backup)"
    except: pass
    
    return pd.DataFrame(), "Offline"

# 3. SIDEBAR: LOGIN & PORTFOLIO ANALYSIS
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 เข้าสู่ระบบ")
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("PIN", type="password")
            if st.form_submit_button("ตกลง"):
                try:
                    users = pd.read_csv(SHEET_USERS_URL)
                    match = users[(users['username'].astype(str) == str(u)) & (users['pin'].astype(str) == str(p))]
                    if not match.empty:
                        st.session_state.user = u
                        st.session_state.budget = float(match.iloc[0]['budget'])
                        st.rerun()
                    else: st.error("ข้อมูลไม่ถูกต้อง")
                except: st.error("เชื่อมต่อฐานข้อมูลไม่ได้")
    else:
        st.title(f"👤 {st.session_state.user}")
        st.session_state.budget = st.number_input("💰 งบกรองเหรียญ (฿):", value=st.session_state.budget)
        if st.button("ออกจากระบบ"):
            st.session_state.user = None
            st.rerun()

        st.divider()
        st.subheader("📊 วิเคราะห์พอร์ตส่วนตัว")
        
        total_pnl = 0.0
        for coin in st.session_state.pinned_list:
            with st.expander(f"💎 {coin.replace('USDT','')}", expanded=True):
                # ช่องกรอกราคาที่ซื้อมาจริง
                b_p = st.number_input(f"ราคาที่ซื้อ ({coin})", key=f"bp_{coin}", value=st.session_state.buy_prices.get(coin, 0.0))
                st.session_state.buy_prices[coin] = b_p
                
                # Slider จำลอง % กำไร/ขาดทุน
                sim = st.slider(f"จำลองกำไร/ขาดทุน %", -50, 100, 0, key=f"sim_{coin}")
                
                if b_p > 0:
                    current_pnl = (b_p * sim) / 100
                    total_pnl += current_pnl
                    st.write(f"กำไรคงเหลือ: **{current_pnl:,.2f} ฿**")
        
        if st.session_state.pinned_list:
            st.divider()
            st.markdown("### 📈 ยอดกำไรรวมทั้งหมด")
            pnl_color = "#00ffcc" if total_pnl >= 0 else "#ff4b4b"
            st.markdown(f"<h2 style='color:{pnl_color}; text-align:center;'>{total_pnl:,.2f} ฿</h2>", unsafe_allow_html=True)

# 4. MAIN UI
st_autorefresh(interval=30000, key="v17_refresh")
df_raw, source_name = get_market_data()

st.title("🪙 Budget-Bet")
st.caption(f"Source: {source_name} | Exchange Rate: {EXCHANGE_RATE} ฿/USD")

if not df_raw.empty:
    df = df_raw.copy()
    df = df[df['symbol'].str.endswith('USDT')]
    df['price_thb'] = df['price'] * EXCHANGE_RATE
    df = df.sort_values('volume', ascending=False)

    # กรองตามงบ
    if st.session_state.user and st.session_state.budget > 0:
        display_df = df[df['price_thb'] <= st.session_state.budget].head(6)
        st.subheader(f"🚀 เหรียญแนะนำในงบ {st.session_state.budget:,.0f} ฿")
    else:
        display_df = df.head(6)
        st.subheader("🏆 เหรียญยอดนิยมในตลาด")

    # แสดงผล Card
    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                s_name = row['symbol'].replace('USDT','')
                c1.markdown(f"### {s_name}")
                
                if st.session_state.user:
                    if c2.button("📌", key=f"pin_{s_name}"):
                        if row['symbol'] not in st.session_state.pinned_list:
                            st.session_state.pinned_list.append(row['symbol'])
                            st.rerun()

                st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
else:
    st.error("⚠️ ไม่สามารถเชื่อมต่อ API ได้ในขณะนี้ ระบบจะพยายามใหม่ทุก 30 วินาที")
