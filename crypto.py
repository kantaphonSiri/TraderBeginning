import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=936509889&single=true&output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Budget-Bet Pro", layout="wide")

# --- INITIALIZE SESSION STATE ---
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []
if 'buy_prices' not in st.session_state: st.session_state.buy_prices = {}

# 2. ROBUST DATA ENGINE (Multi-Endpoint)
def get_data():
    # รายชื่อ API สำรองกรณีตัวหลักล่ม
    endpoints = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api2.binance.com/api/v3/ticker/24hr"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
                return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Active"
        except:
            continue
    return pd.DataFrame(), "Offline"

# 3. SIDEBAR (Login & Portfolio)
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login")
        with st.form("login_form"):
            u_name = st.text_input("Username")
            u_pin = st.text_input("PIN", type="password")
            if st.form_submit_button("Login"):
                try:
                    df_users = pd.read_csv(SHEET_USERS_URL)
                    match = df_users[(df_users['username'].astype(str) == str(u_name)) & 
                                     (df_users['pin'].astype(str) == str(u_pin))]
                    if not match.empty:
                        st.session_state.user = u_name
                        st.session_state.budget = float(match.iloc[0]['budget'])
                        st.rerun()
                    else: st.error("ข้อมูลไม่ถูกต้อง")
                except: st.error("เชื่อมต่อฐานข้อมูลไม่ได้")
    else:
        st.title(f"👤 {st.session_state.user}")
        st.session_state.budget = st.number_input("💵 งบกรองเหรียญ (บาท):", value=st.session_state.budget)
        
        if st.button("Log out"):
            st.session_state.user = None
            st.rerun()

        st.divider()
        st.subheader("📌 พอร์ตจำลองวิเคราะห์")
        
        total_profit_loss = 0.0
        if st.session_state.pinned_list:
            for coin in st.session_state.pinned_list:
                with st.expander(f"📉 {coin.replace('USDT','')}", expanded=True):
                    # กรอกต้นทุน
                    buy_p = st.number_input(f"ต้นทุน ({coin})", key=f"buy_{coin}", value=st.session_state.buy_prices.get(coin, 0.0))
                    st.session_state.buy_prices[coin] = buy_p
                    
                    # แถบเลื่อนปรับกำไร/ขาดทุน
                    sim_pct = st.slider(f"ปรับ % ({coin})", -100, 200, 0, key=f"sim_{coin}")
                    
                    if buy_p > 0:
                        profit_val = (buy_p * sim_pct) / 100
                        total_profit_loss += profit_val
                        st.write(f"กำไร/ขาดทุน: **{profit_val:,.2f} ฿**")
            
            # สรุปยอดรวมด้านล่าง Sidebar
            st.divider()
            st.markdown("### 💰 สรุปรวมทุกเหรียญ")
            color = "green" if total_profit_loss >= 0 else "red"
            st.markdown(f"<h2 style='color:{color};'>{total_profit_loss:,.2f} ฿</h2>", unsafe_allow_html=True)
        else:
            st.caption("ยังไม่มีเหรียญที่ Pin")

# 4. MAIN UI
st_autorefresh(interval=30000, key="v16_refresh")
df_raw, api_status = get_data()

st.title("🪙 Budget-Bet Analyzer")
st.caption(f"API Status: {api_status} | User: {st.session_state.user if st.session_state.user else 'Guest'}")

if not df_raw.empty:
    df_global = df_raw.copy()
    df_global = df_global[df_global['symbol'].str.endswith('USDT')]
    df_global = df_global.sort_values('volume', ascending=False).head(200)
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    
    # การกรอง
    display_df = df_global.head(6)
    if st.session_state.user and st.session_state.budget > 0:
        display_df = df_global[df_global['price_thb'] <= st.session_state.budget].head(6)

    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                sym = row['symbol']
                c1.subheader(f"{sym.replace('USDT','')}")
                
                if st.session_state.user:
                    if c2.button("📌", key=f"btn_{sym}"):
                        if sym not in st.session_state.pinned_list:
                            st.session_state.pinned_list.append(sym)
                            st.rerun()
                
                st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
else:
    st.error("📡 ระบบกำลังพยายามเชื่อมต่อ API สำรอง... กรุณารอ 30 วินาที")
