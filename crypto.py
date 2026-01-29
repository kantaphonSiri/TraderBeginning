import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time

# 1. SETUP
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=936509889&single=true&output=csv"
SHEET_PORT_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=820979573&single=true&output=csv"

EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Yahoo Precision", layout="wide")

# --- INITIALIZE SESSION STATE ---
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []
if 'buy_prices' not in st.session_state: st.session_state.buy_prices = {}

# 2. DATA ENGINE
def get_data():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
            df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
            df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Binance"
    except: pass
    return pd.DataFrame(), "Offline"

# 3. SIDEBAR (Login & Advanced Portfolio)
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login to Access")
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
                        try:
                            df_port = pd.read_csv(SHEET_PORT_URL)
                            st.session_state.pinned_list = df_port[df_port['owner'] == u_name]['symbol'].tolist()
                        except: st.session_state.pinned_list = []
                        st.rerun()
                    else: st.error("Wrong PIN")
                except: st.error("Database Error")
    else:
        st.title(f"👤 {st.session_state.user}")
        # ช่องกรอกงบแบบ Manual
        st.session_state.budget = st.number_input("💵 ปรับงบกรองเหรียญ (บาท):", value=st.session_state.budget)
        
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()
        
        st.divider()
        st.subheader("📌 My Portfolio Analysis")
        
        if st.session_state.pinned_list:
            for coin in st.session_state.pinned_list:
                with st.expander(f"📊 {coin.replace('USDT','')}", expanded=True):
                    # ช่องกรอกราคาซื้อ
                    buy_p = st.number_input(f"ราคาที่ซื้อ ({coin})", key=f"buy_{coin}", value=st.session_state.buy_prices.get(coin, 0.0))
                    st.session_state.buy_prices[coin] = buy_p
                    
                    # ตัวจำลองกำไร/ขาดทุน (Slider)
                    sim_change = st.slider("จำลอง % กำไร/ขาดทุน", -50, 100, 0, key=f"slide_{coin}")
                    
                    if buy_p > 0:
                        simulated_price = buy_p * (1 + (sim_change/100))
                        st.write(f"ราคาจำลอง: **{simulated_price:,.2f} ฿**")
                        if sim_change > 0: st.success(f"กำไรที่คาดการณ์: {sim_change}%")
                        elif sim_change < 0: st.error(f"ขาดทุนที่คาดการณ์: {sim_change}%")
        else:
            st.caption("กด 📌 ที่เหรียญเพื่อเริ่มวิเคราะห์")

# 4. MAIN UI
st_autorefresh(interval=30000, key="api_refresh")
df_raw, source = get_data()

st.title("🪙 Budget-Bet Analyzer")

if not df_raw.empty:
    df_global = df_raw.copy()
    df_global = df_global[df_global['symbol'].str.endswith('USDT')]
    df_global = df_global.sort_values('volume', ascending=False).head(200)
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE

    # กรองเหรียญตามงบที่กรอกใน Sidebar
    display_df = df_global.head(6)
    if st.session_state.user and st.session_state.budget > 0:
        display_df = df_global[df_global['price_thb'] <= st.session_state.budget].head(6)

    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                sym = row['symbol']
                c1.markdown(f"### {row['stamp']} {sym.replace('USDT','')}")
                
                if st.session_state.user:
                    if c2.button("📌", key=f"p_{sym}_{i}"):
                        if sym not in st.session_state.pinned_list:
                            st.session_state.pinned_list.append(sym)
                            st.rerun() # Refresh เพื่อให้โชว์ใน Sidebar ทันที
                
                st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                
                # Chart แสดงความเสถียร
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(width=3, color="#f1c40f")))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"gr_{sym}_{i}", config={'displayModeBar': False})
else:
    st.error("📡 API Connection Issue...")
