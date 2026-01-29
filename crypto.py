import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
# สำคัญ: เปลี่ยนเป็น URL CSV ของคุณ
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/YOUR_ID/pub?gid=0&output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Yahoo Precision", layout="wide")

# --- [FIX] ป้องกัน AttributeError โดยการกำหนดค่าเริ่มต้นทันทีที่รันแอป ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'budget' not in st.session_state:
    st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state:
    st.session_state.pinned_list = []

# 2. DATA ENGINE
def get_data():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
            df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
            df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Binance"
    except: pass
    return pd.DataFrame(), "Disconnected"

# 3. SIDEBAR LOGIN SYSTEM
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login to Pin")
        with st.form("login_form"):
            u_name = st.text_input("Username")
            u_pin = st.text_input("PIN (4 Digits)", type="password")
            if st.form_submit_button("Login"):
                try:
                    df_users = pd.read_csv(SHEET_USERS_URL)
                    # ตรวจสอบ Match (User + PIN)
                    match = df_users[(df_users['username'] == u_name) & (df_users['pin'].astype(str) == u_pin)]
                    if not match.empty:
                        st.session_state.user = u_name
                        st.session_state.budget = float(match.iloc[0]['budget'])
                        st.success(f"ยินดีต้อนรับคุณ {u_name}")
                        st.rerun()
                    else:
                        st.error("ชื่อหรือ PIN ไม่ถูกต้อง")
                except Exception as e:
                    st.error("เชื่อมต่อฐานข้อมูลไม่ได้ (เช็ค URL Sheets)")
    else:
        st.title(f"👤 {st.session_state.user}")
        # บรรทัดเจ้าปัญหา (แก้ไขแล้วด้วยการ init ไว้ด้านบน)
        st.metric("My Budget", f"{st.session_state.budget:,.0f} ฿")
        
        if st.button("Log out"):
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

# 4. MAIN UI - YAHOO PRECISION
st_autorefresh(interval=30000, key="v14_refresh")
df_raw, source = get_data()

st.title("🪙 Yahoo-Style Precision Market")
status_text = f"Logged in as {st.session_state.user}" if st.session_state.user else "Guest Mode"
st.caption(f"Source: {source} | Status: {status_text}")

if not df_raw.empty:
    # --- STEP 1: Global Scan & Pre-Stamp ---
    df_global = df_raw.copy()
    df_global = df_global[(df_global['symbol'].str.endswith('USDT')) & (~df_global['symbol'].str.contains('UP|DOWN|USDC|DAI'))]
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE

    # --- STEP 2: Logic กรองเหรียญ ---
    if st.session_state.user and st.session_state.budget > 0:
        recommend = df_global[df_global['price_thb'] <= st.session_state.budget].head(6)
        label = f"🚀 Top Picks ในงบ {st.session_state.budget:,.0f} ฿"
    else:
        recommend = df_global.head(6)
        label = "🏆 Global Market Leaders"

    st.subheader(label)

    # --- STEP 3: Display Cards ---
    col1, col2 = st.columns(2)
    for idx, row in enumerate(recommend.to_dict('records')):
        target_col = col1 if idx % 2 == 0 else col2
        sym = row['symbol'].replace('USDT', '')
        
        with target_col:
            with st.container(border=True):
                h1, h2 = st.columns([4, 1])
                with h1:
                    st.markdown(f"### {row['stamp']} {sym}")
                with h2:
                    if st.session_state.user:
                        if st.button("📌", key=f"pin_{sym}_{idx}"):
                            if sym not in st.session_state.pinned_list:
                                st.session_state.pinned_list.append(sym)
                                st.toast(f"บันทึก {sym} แล้ว!")
                    else:
                        st.caption("🔒 Login")

                chg = row['change']
                color = "#00ffcc" if chg < -4 else ("#ff4b4b" if chg > 10 else "#f1c40f")
                st.metric("Price", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                
                # Sparkline
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}_{idx}", config={'displayModeBar': False})
else:
    st.error("📡 ไม่สามารถเชื่อมต่อ API ได้ในขณะนี้...")

st.divider()
