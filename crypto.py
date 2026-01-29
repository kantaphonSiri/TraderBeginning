import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time

# --- [ส่วนที่ต้องแก้] ---
# 1. สร้าง Google Form ที่มี 3 ข้อ: owner, symbol, buy_price
# 2. ก๊อปปี้ลิงก์ "Get pre-filled link" มาใส่ที่นี่ และเปลี่ยนคำว่า 'viewform' เป็น 'formResponse'
FORM_URL = "https://docs.google.com/forms/d/14X89ttm-kAPOD6mJP3RWSP8pntPOHDcURi8W7UjN7jc/formResponse"

# ลิงก์อ่านข้อมูล (อันเดิมของคุณ)
SHEET_USERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=936509889&single=true&output=csv"
SHEET_PORT_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=820979573&single=true&output=csv"

# ฟังก์ชันส่งข้อมูลเข้า Google Sheets
def save_to_cloud(owner, symbol, price):
    # เปลี่ยน entry.xxxx ให้ตรงกับ ID ที่ได้จาก Pre-filled link ของคุณ
    payload = {
        "entry.1050662295": owner,
        "entry.42438203": symbol,
        "entry.1637597791": price
    }
    try:
        requests.post(FORM_URL, data=payload)
        return True
    except:
        return False

# --- [SETUP & INITIALIZE เดิม] ---
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Yahoo Precision Pro", layout="wide")
if 'user' not in st.session_state: st.session_state.user = None
if 'budget' not in st.session_state: st.session_state.budget = 0.0
if 'pinned_list' not in st.session_state: st.session_state.pinned_list = []
if 'buy_prices' not in st.session_state: st.session_state.buy_prices = {}

def get_sheet_data(url):
    try:
        nocache_url = f"{url}&nocache={time.time()}"
        df = pd.read_csv(nocache_url)
        return df.dropna(subset=['username']) if 'username' in df.columns else df.dropna()
    except: return pd.DataFrame()

def get_market_data():
    urls = ["https://api.binance.com/api/v3/ticker/24hr", "https://api.gateio.ws/api/v4/spot/tickers"]
    for url in urls:
        try:
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                if 'lastPrice' in df.columns:
                    df['price'] = pd.to_numeric(df['lastPrice']); df['change'] = pd.to_numeric(df['priceChangePercent'])
                    df['volume'] = pd.to_numeric(df['quoteVolume']); df['open_p'] = pd.to_numeric(df['openPrice'])
                else:
                    df['symbol'] = df['currency_pair'].str.replace('_', ''); df['price'] = pd.to_numeric(df['last'])
                    df['change'] = pd.to_numeric(df['change_percentage']); df['volume'] = pd.to_numeric(df['quote_volume'])
                    df['open_p'] = df['price'] / (1 + (df['change'] / 100))
                return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Active"
        except: continue
    return pd.DataFrame(), "Offline"

# --- [SIDEBAR] ---
with st.sidebar:
    if st.session_state.user is None:
        st.title("🔐 Login")
        with st.form("login"):
            u = st.text_input("Username").strip(); p = st.text_input("PIN", type="password").strip()
            if st.form_submit_button("เข้าสู่ระบบ"):
                df_users = get_sheet_data(SHEET_USERS_URL)
                if not df_users.empty:
                    match = df_users[(df_users['username'].astype(str) == u) & (df_users['pin'].astype(str) == p)]
                    if not match.empty:
                        st.session_state.user = u
                        st.session_state.budget = float(match.iloc[0]['budget'])
                        df_port = get_sheet_data(SHEET_PORT_URL)
                        if not df_port.empty and 'owner' in df_port.columns:
                            user_coins = df_port[df_port['owner'] == u]['symbol'].dropna().astype(str).tolist()
                            st.session_state.pinned_list = user_coins
                        st.rerun()
                    else: st.error("ข้อมูลไม่ถูกต้อง")
    else:
        st.title(f"👤 {st.session_state.user}")
        
        # ปุ่มบันทึกข้อมูลลง Cloud
        if st.button("💾 บันทึกราคาลง Google Sheet"):
            with st.spinner("กำลังบันทึก..."):
                for coin in st.session_state.pinned_list:
                    p = st.session_state.buy_prices.get(coin, 0)
                    save_to_cloud(st.session_state.user, coin, p)
                st.success("บันทึกเรียบร้อย! ข้อมูลจะถูกดึงมาใหม่เมื่อ Login ครั้งหน้า")
                time.sleep(2); st.rerun()

        st.divider()
        st.subheader("📊 My Portfolio Analysis")
        total_pnl = 0.0
        for coin in list(st.session_state.pinned_list):
            coin_label = str(coin).replace('USDT','')
            with st.expander(f"📦 {coin_label}", expanded=True):
                c1, c2 = st.columns([3, 1])
                if c2.button("🗑️", key=f"del_{coin}"):
                    st.session_state.pinned_list.remove(coin); st.rerun()
                
                b_p = st.number_input(f"ต้นทุนซื้อ (฿)", key=f"bp_{coin}", value=st.session_state.buy_prices.get(coin, 0.0))
                st.session_state.buy_prices[coin] = b_p
                sim = st.slider(f"จำลองกำไร %", -50, 100, 0, key=f"sim_{coin}")
                
                if b_p > 0:
                    net_profit = (b_p * sim) / 100
                    total_val = b_p + net_profit
                    total_pnl += net_profit
                    st.write(f"💵 เงินรวม: **{total_val:,.2f} ฿**")
                    st.markdown(f"<small style='color:{'green' if sim >= 0 else 'red'};'>กำไรสุทธิ: {net_profit:+.2f} ฿</small>", unsafe_allow_html=True)

        if st.session_state.pinned_list:
            st.divider()
            st.markdown(f"### 📈 กำไรรวมสุทธิ\n<h2 style='color:{'#00ffcc' if total_pnl >= 0 else '#ff4b4b'};'>{total_pnl:,.2f} ฿</h2>", unsafe_allow_html=True)
        if st.button("Logout"): st.session_state.user = None; st.rerun()

# --- [MAIN UI เดิม] ---
st_autorefresh(interval=30000, key="v23_refresh")
df_raw, source = get_market_data()
st.title("🪙 Budget-Bet Precision")
if not df_raw.empty:
    df = df_raw.copy()
    df = df[df['symbol'].str.endswith('USDT')].sort_values('volume', ascending=False).head(200)
    df['rank'] = range(1, len(df) + 1)
    df['stamp'] = df['rank'].apply(lambda x: "🔵 (Blue Chip)" if x <= 30 else "🪙 (Trending)")
    df['price_thb'] = df['price'] * EXCHANGE_RATE
    display_df = df[df['price_thb'] <= st.session_state.budget].head(6) if st.session_state.user and st.session_state.budget > 0 else df.head(6)
    
    cols = st.columns(2)
    for i, row in enumerate(display_df.to_dict('records')):
        with cols[i % 2]:
            with st.container(border=True):
                h1, h2 = st.columns([4,1]); sym_c = row['symbol'].replace('USDT','')
                h1.markdown(f"#### {row['stamp']}\n## {sym_c}")
                if st.session_state.user and h2.button("📌", key=f"p_{row['symbol']}"):
                    if row['symbol'] not in st.session_state.pinned_list:
                        st.session_state.pinned_list.append(row['symbol']); st.rerun()
                st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color="#f1c40f", width=3)))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"gr_{row['symbol']}", config={'displayModeBar': False})

