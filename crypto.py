import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time

# 1. SETUP
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/YOUR_ID/pub?gid=0&output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Yahoo Precision", layout="wide")

# --- INITIALIZE SESSION STATE ---
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []

# 2. ROBUST DATA ENGINE (With Retry Logic)
def get_data():
    # ลองดึงจาก Binance เป็นอันดับแรก
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr", # Backup Endpoint
        "https://api.gateio.ws/api/v4/spot/tickers"
    ]
    
    for url in urls:
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                
                # ตรวจสอบรูปแบบข้อมูลว่าเป็น Binance หรือ Gate.io
                if 'lastPrice' in df.columns: # Binance Style
                    df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                    df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                    df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
                    source = "Binance"
                else: # Gate.io Style
                    df['symbol'] = df['currency_pair'].str.replace('_', '')
                    df['price'] = pd.to_numeric(df['last'], errors='coerce')
                    df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
                    df['open_p'] = df['price'] / (1 + (df['change'] / 100))
                    source = "Gate.io"
                
                return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), source
        except Exception as e:
            continue
    return pd.DataFrame(), "Offline"

# 3. SIDEBAR (Login & Port)
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login to Pin")
        with st.form("login_form"):
            u_name = st.text_input("Username")
            u_pin = st.text_input("PIN", type="password")
            if st.form_submit_button("Login"):
                try:
                    df_users = pd.read_csv(SHEET_USERS_URL)
                    match = df_users[(df_users['username'] == u_name) & (df_users['pin'].astype(str) == u_pin)]
                    if not match.empty:
                        st.session_state.user = u_name
                        st.session_state.budget = float(match.iloc[0]['budget'])
                        st.rerun()
                    else: st.error("Invalid Credentials")
                except: st.error("Sheet Connection Failed")
    else:
        st.title(f"👤 {st.session_state.user}")
        st.metric("Budget", f"{st.session_state.budget:,.0f} ฿")
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()
        st.divider()
        st.subheader("📌 Pinned")
        for coin in st.session_state.pinned_list:
            st.write(f"✅ {coin}")

# 4. MAIN UI
st_autorefresh(interval=30000, key="api_fix_refresh")
df_raw, source = get_data()

st.title("🪙 Yahoo-Style Market Explorer")

if not df_raw.empty:
    # --- YAHOO PRECISION PROCESS ---
    df_global = df_raw.copy()
    df_global = df_global[df_global['symbol'].str.endswith('USDT')]
    df_global = df_global.sort_values('volume', ascending=False).head(200)
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE

    # Filter by budget if logged in
    if st.session_state.user and st.session_state.budget > 0:
        display_df = df_global[df_global['price_thb'] <= st.session_state.budget].head(6)
    else:
        display_df = df_global.head(6)

    # Grid Display
    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                sym = row['symbol'].replace('USDT','')
                c1.markdown(f"### {row['stamp']} {sym}")
                if st.session_state.user and c2.button("📌", key=f"p_{sym}"):
                    if sym not in st.session_state.pinned_list:
                        st.session_state.pinned_list.append(sym)
                
                color = "#00ffcc" if row['change'] < -4 else "#f1c40f"
                st.metric("Price", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                
                # Mini Chart
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=3)))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"gr_{sym}", config={'displayModeBar': False})
else:
    st.warning("⚠️ API Connection Issue. Retrying in 30s...")
    
    st.info(f"ขณะนี้เซิร์ฟเวอร์อาจมีการจำกัดการเข้าถึง (Rate Limit) หรือเครือข่ายขัดข้อง ระบบจะพยายามเชื่อมต่อผ่าน Endpoint สำรองโดยอัตโนมัติ")
