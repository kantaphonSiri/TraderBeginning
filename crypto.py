import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time

# 1. SETUP - ใส่ URL CSV จาก Google Sheets ของคุณ
# URL สำหรับ Tab 'users'
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=936509889&single=true&output=csv"
# URL สำหรับ Tab 'portfolio' (เปลี่ยน GID ให้ตรงกับแท็บที่สอง)
SHEET_PORT_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=820979573&single=true&output=csv"

EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Yahoo Precision", layout="wide")

# --- INITIALIZE SESSION STATE ---
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []

# 2. DATA ENGINE (ดึงข้อมูลตลาด)
def get_data():
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api.gateio.ws/api/v4/spot/tickers"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                if 'lastPrice' in df.columns:
                    df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                    df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                    df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
                    source = "Binance"
                else:
                    df['symbol'] = df['currency_pair'].str.replace('_', '')
                    df['price'] = pd.to_numeric(df['last'], errors='coerce')
                    df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
                    df['open_p'] = df['price'] / (1 + (df['change'] / 100))
                    source = "Gate.io"
                return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), source
        except: continue
    return pd.DataFrame(), "Offline"

# 3. SIDEBAR (Login & Portfolio Sync)
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login to Pin")
        with st.form("login_form"):
            u_name = st.text_input("Username")
            u_pin = st.text_input("PIN", type="password")
            if st.form_submit_button("Login"):
                try:
                    df_users = pd.read_csv(SHEET_USERS_URL)
                    # ตรวจสอบชื่อและ PIN
                    match = df_users[(df_users['username'].astype(str) == str(u_name)) & 
                                     (df_users['pin'].astype(str) == str(u_pin))]
                    if not match.empty:
                        st.session_state.user = u_name
                        st.session_state.budget = float(match.iloc[0]['budget'])
                        
                        # --- ดึงเหรียญที่เคย Pin ไว้จาก Sheet Portfolio ---
                        try:
                            df_port = pd.read_csv(SHEET_PORT_URL)
                            user_coins = df_port[df_port['owner'] == u_name]['symbol'].tolist()
                            st.session_state.pinned_list = user_coins
                        except:
                            st.session_state.pinned_list = []
                            
                        st.success("Login Success!")
                        st.rerun()
                    else: st.error("Username หรือ PIN ผิด")
                except Exception as e:
                    st.error("เชื่อมต่อฐานข้อมูล User ไม่ได้")
                    st.caption(f"Debug: {e}")
    else:
        st.title(f"👤 {st.session_state.user}")
        st.metric("Budget", f"{st.session_state.budget:,.0f} ฿")
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.budget = 0.0
            st.session_state.pinned_list = []
            st.rerun()
        
        st.divider()
        st.subheader("📌 Pinned Coins")
        if st.session_state.pinned_list:
            for coin in st.session_state.pinned_list:
                st.write(f"✅ {coin}")
        else:
            st.caption("ยังไม่มีเหรียญที่บันทึก")

# 4. MAIN UI
st_autorefresh(interval=30000, key="api_refresh")
df_raw, source = get_data()

st.title("🪙 Budget-Bet")

if not df_raw.empty:
    # --- YAHOO PRECISION LOGIC ---
    df_global = df_raw.copy()
    df_global = df_global[df_global['symbol'].str.endswith('USDT')]
    df_global = df_global.sort_values('volume', ascending=False).head(200)
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE

    # กรองตามงบถ้า Login แล้ว
    display_df = df_global.head(6)
    if st.session_state.user and st.session_state.budget > 0:
        display_df = df_global[df_global['price_thb'] <= st.session_state.budget].head(6)

    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                sym = row['symbol'].replace('USDT','')
                c1.markdown(f"### {row['stamp']} {sym}")
                
                # ปุ่ม Pin (จะทำงานใน Session ก่อน)
                if st.session_state.user:
                    if c2.button("📌", key=f"p_{sym}_{i}"):
                        if sym not in st.session_state.pinned_list:
                            st.session_state.pinned_list.append(sym)
                            st.toast(f"Saved {sym}!")
                
                color = "#00ffcc" if row['change'] < -4 else "#f1c40f"
                st.metric("Price", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                
                # Chart
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=3)))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"gr_{sym}_{i}", config={'displayModeBar': False})
else:
    st.warning("📡 เชื่อมต่อข้อมูลตลาดไม่ได้ กรุณารอสักครู่...")
