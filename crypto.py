import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP & CONFIG
# เปลี่ยนเป็น URL ของแท็บพอร์ต (CSV)
SHEET_PORTFOLIO_URL = "https://docs.google.com/spreadsheets/d/e/YOUR_ID/pub?gid=0&output=csv" 
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Crypto Login & Pin", layout="wide")

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

# 3. LOGIN SESSION STATE
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = ""

# 4. LOGIN UI
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 Crypto Terminal Login")
        with st.form("login_form"):
            user_input = st.text_input("Username")
            pin_input = st.text_input("PIN (4 หลัก)", type="password")
            submit = st.form_submit_button("เข้าสู่ระบบ")
            
            if submit:
                # ในที่นี้ตัวอย่างเป็นการเช็ค Hardcode หรือคุณจะดึงจาก Sheets มาเทียบก็ได้
                # สมมติ Admin PIN คือ 1234
                if (user_input == "Admin" and pin_input == "1234") or \
                   (user_input == "User_A" and pin_input == "0000"):
                    st.session_state.logged_in = True
                    st.session_state.user = user_input
                    st.rerun()
                else:
                    st.error("Username หรือ PIN ไม่ถูกต้อง")
    st.stop()

# 5. MAIN APP (After Login)
st_autorefresh(interval=30000, key="v13_refresh")
df_raw, source = get_data()

# SIDEBAR: ข้อมูลผู้ใช้และเหรียญที่ Pin ไว้
with st.sidebar:
    st.title(f"👤 {st.session_state.user}")
    if st.button("Log out"):
        st.session_state.logged_in = False
        st.rerun()
    
    st.divider()
    st.subheader("📌 Pinned Coins")
    # ดึงรายการเหรียญที่ Pin จาก Sheets (จำลองการดึง)
    try:
        # ในแอปจริง คุณจะใช้ระบบส่งข้อมูลกลับไปที่ Sheets ผ่าน Form/API
        # ตอนนี้แสดงเป็นรายการที่ User สนใจ
        st.info("เหรียญที่คุณบันทึกไว้จะแสดงที่นี่")
        # ตัวอย่าง: st.write("✅ BTC")
    except: pass

# 6. YAHOO PRECISION LOGIC
st.title(f"🪙 Smart Selection for {st.session_state.user}")

if not df_raw.empty:
    df_global = df_raw.copy()
    df_global = df_global[(df_global['symbol'].str.endswith('USDT')) & (~df_global['symbol'].str.contains('UP|DOWN|USDC'))]
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    
    # Pre-Stamp
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    
    # แสดงเหรียญแนะนำ
    recommend = df_global.head(6)
    
    col1, col2 = st.columns(2)
    for idx, row in enumerate(recommend.to_dict('records')):
        target_col = col1 if idx % 2 == 0 else col2
        sym = row['symbol'].replace('USDT', '')
        
        with target_col:
            with st.container(border=True):
                # ส่วนหัว: ชื่อเหรียญ + ปุ่ม Pin (จำลอง)
                head1, head2 = st.columns([3, 1])
                with head1:
                    st.markdown(f"### {row['stamp']} {sym}")
                with head2:
                    if st.button("📌 Pin", key=f"pin_{sym}"):
                        st.toast(f"บันทึก {sym} ลงในพอร์ตแล้ว!")
                
                chg = row['change']
                st.metric("ราคา", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                
                # Graph
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(width=4)))
                fig.update_layout(height=60, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{sym}")
else:
    st.error("📡 ไม่สามารถดึงข้อมูลตลาดได้")
