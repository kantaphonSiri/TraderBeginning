import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Multi-User", layout="wide")

# 2. DATA ENGINE
@st.cache_data(ttl=30)
def get_market_data():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'])
            df['change'] = pd.to_numeric(df['priceChangePercent'])
            df['volume'] = pd.to_numeric(df['quoteVolume'])
            df['open_p'] = pd.to_numeric(df['openPrice'])
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna()
    except: return pd.DataFrame()

# 3. REFRESH
st_autorefresh(interval=30000, key="v12_refresh")

# 4. SIDEBAR - ระบบแยก User
with st.sidebar:
    st.title("👤 User Access")
    # เพิ่มกล่องเลือกชื่อคนใช้งาน
    current_user = st.selectbox("เลือกผู้ใช้งาน:", ["Admin (ผู้สร้าง)", "User_A", "User_B"])
    
    st.divider()
    st.subheader(f"💵 งบของ {current_user}")
    budget = st.number_input("งบซื้อต่อหน่วย (บาท):", min_value=0.0, value=0.0, step=1000.0)
    
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        # --- กรองข้อมูลเฉพาะของคนที่เลือก ---
        if 'owner' in df_port.columns:
            user_data = df_port[df_port['owner'] == current_user]
            if not user_data.empty:
                for _, row in user_data.iterrows():
                    st.write(f"📌 {row['symbol'].upper()}")
            else:
                st.caption("ยังไม่มีเหรียญในพอร์ต")
        else:
            st.error("กรุณาเพิ่ม Column 'owner' ใน Sheets")
    except:
        st.caption("กำลังเชื่อมต่อ Sheets...")

# 5. MAIN UI (ยังคงใช้ Precision Logic เหมือนเดิม)
df_raw = get_market_data()
st.title(f"🪙 Smart Terminal: {current_user}")

if not df_raw.empty:
    # --- Precision Waterfall Logic ---
    df_global = df_raw.copy()
    df_global = df_global[(df_global['symbol'].str.endswith('USDT')) & (~df_global['symbol'].str.contains('UP|DOWN|USDC|DAI'))]
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    
    # Pre-Stamp
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    
    # Filter by User Budget
    recommend = df_global[df_global['price_thb'] <= budget].head(6) if budget > 0 else df_global.head(6)

    st.subheader(f"🚀 แนะนำสำหรับ {current_user} (งบ {budget:,.0f} ฿)")
    
    # การแสดงผล Card
    col1, col2 = st.columns(2)
    for idx, row in enumerate(recommend.to_dict('records')):
        with (col1 if idx % 2 == 0 else col2):
            with st.container(border=True):
                color = "#00ffcc" if row['change'] < -4 else ("#ff4b4b" if row['change'] > 10 else "#f1c40f")
                st.markdown(f"### {row['stamp']} {row['symbol'].replace('USDT','')} <span style='color:{color}'>{row['change']:+.2f}%</span>", unsafe_allow_html=True)
                st.metric("Price", f"{row['price_thb']:,.2f} ฿")
else:
    st.warning("📡 กำลังรอข้อมูลตลาด...")
