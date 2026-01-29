import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time

# 1. SETUP
# เคล็ดลับ: เพิ่มสุ่มเลขต่อท้าย URL เพื่อป้องกันการจำค่าเก่า (Cache Busting)
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=936509889&single=true&output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Yahoo Precision Pro", layout="wide")

# INITIALIZE STATE
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []
if 'buy_prices' not in st.session_state: st.session_state.buy_prices = {}

# 2. FUNCTION: ดึง User แบบไม่ติด Cache
def get_user_database():
    try:
        # ใส่ตัวแปรสุ่มเพื่อให้ Google ส่งข้อมูลล่าสุดมาให้ (Cache Busting)
        nocache_url = f"{SHEET_USERS_URL}&nocache={time.time()}"
        return pd.read_csv(nocache_url)
    except:
        return pd.DataFrame()

# 3. DATA ENGINE (Binance + Gate.io)
def get_market_data():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=3)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'])
            df['change'] = pd.to_numeric(df['priceChangePercent'])
            df['volume'] = pd.to_numeric(df['quoteVolume'])
            df['open_p'] = pd.to_numeric(df['openPrice'])
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Binance"
    except: pass
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=3)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['symbol'] = df['currency_pair'].str.replace('_', '')
            df['price'] = pd.to_numeric(df['last'])
            df['change'] = pd.to_numeric(df['change_percentage'])
            df['volume'] = pd.to_numeric(df['quote_volume'])
            df['open_p'] = df['price'] / (1 + (df['change'] / 100))
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Gate.io"
    except: pass
    return pd.DataFrame(), "Offline"

# 4. SIDEBAR
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login")
        with st.form("login"):
            u = st.text_input("Username").strip() # ตัดช่องว่างทิ้ง
            p = st.text_input("PIN", type="password").strip()
            if st.form_submit_button("เข้าสู่ระบบ"):
                with st.spinner("กำลังตรวจสอบข้อมูลล่าสุด..."):
                    users = get_user_database()
                    if not users.empty:
                        # ตรวจสอบชื่อและ PIN
                        match = users[(users['username'].astype(str) == str(u)) & 
                                         (users['pin'].astype(str) == str(p))]
                        if not match.empty:
                            st.session_state.user = u
                            st.session_state.budget = float(match.iloc[0]['budget'])
                            st.success("สำเร็จ!")
                            st.rerun()
                        else: st.error("ข้อมูลไม่ถูกต้อง")
                    else: st.error("ไม่สามารถดึงข้อมูลจาก Google Sheets ได้")
    else:
        st.title(f"👤 {st.session_state.user}")
        st.session_state.budget = st.number_input("💰 ปรับงบกรอง (฿):", value=st.session_state.budget)
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()

        st.divider()
        st.subheader("📊 My Portfolio")
        total_pnl = 0.0
        for coin in list(st.session_state.pinned_list):
            with st.expander(f"📦 {coin.replace('USDT','')}", expanded=True):
                col_name, col_del = st.columns([3, 1])
                if col_del.button("🗑️", key=f"del_{coin}"):
                    st.session_state.pinned_list.remove(coin)
                    st.rerun()
                
                b_p = st.number_input(f"ต้นทุนซื้อ (฿)", key=f"bp_{coin}", value=st.session_state.buy_prices.get(coin, 0.0))
                st.session_state.buy_prices[coin] = b_p
                sim = st.slider(f"จำลองกำไร %", -50, 100, 0, key=f"sim_{coin}")
                if b_p > 0:
                    pnl = (b_p * sim) / 100
                    total_pnl += pnl
                    st.write(f"กำไรคาดการณ์: **{pnl:,.2f} ฿**")

        if st.session_state.pinned_list:
            st.divider()
            st.markdown(f"### 📈 กำไรรวมสุทธิ\n<h2 style='color:#00ffcc;'>{total_pnl:,.2f} ฿</h2>", unsafe_allow_html=True)

# 5. MAIN UI (Yahoo Precision)
st_autorefresh(interval=30000, key="v19_refresh")
df_raw, source = get_market_data()

st.title("🪙 Budget-Bet")
st.caption(f"Connected via: {source}")

if not df_raw.empty:
    df = df_raw.copy()
    df = df[df['symbol'].str.endswith('USDT')]
    df = df.sort_values('volume', ascending=False).head(200)
    df['rank'] = range(1, len(df) + 1)
    df['stamp'] = df['rank'].apply(lambda x: "🔵 (Blue Chip)" if x <= 30 else "🪙 (Trending)")
    df['price_thb'] = df['price'] * EXCHANGE_RATE

    if st.session_state.user and st.session_state.budget > 0:
        display_df = df[df['price_thb'] <= st.session_state.budget].head(6)
    else:
        display_df = df.head(6)

    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                head1, head2 = st.columns([4,1])
                sym_clean = row['symbol'].replace('USDT','')
                head1.markdown(f"#### {row['stamp']}\n## {sym_clean}")
                if st.session_state.user:
                    if head2.button("📌", key=f"pin_{row['symbol']}"):
                        if row['symbol'] not in st.session_state.pinned_list:
                            st.session_state.pinned_list.append(row['symbol'])
                            st.rerun()
                st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color="#f1c40f", width=3)))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"gr_{row['symbol']}", config={'displayModeBar': False})
else:
    st.warning("📡 กำลังเชื่อมต่อข้อมูลตลาด... (Binance อาจตอบสนองช้าในขณะนี้)")
