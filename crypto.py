import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIG
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# 2. HYBRID API (ป้องกันแถบเหลือง)
def get_market_data():
    # ลอง Binance ก่อน
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://api3.binance.com/api/v3/ticker/24hr"]:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                return df[['symbol', 'price', 'change']]
        except: continue
    # ถ้า Binance พัง ใช้ Gate.io สำรอง
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=5)
        df = pd.DataFrame(res.json())
        df['symbol'] = df['currency_pair'].str.replace('_', '')
        df['price'] = pd.to_numeric(df['last'], errors='coerce')
        df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
        return df[['symbol', 'price', 'change']]
    except: return pd.DataFrame()

# 3. INITIALIZE & ADAPTIVE REFRESH
df_market = get_market_data()
rate = 35.5
refresh_ms = 30000

if not df_market.empty:
    btc_chg = abs(df_market[df_market['symbol'] == 'BTCUSDT']['change'].values[0])
    refresh_ms = 10000 if btc_chg > 4 else (30000 if btc_chg > 1.5 else 60000)

st_autorefresh(interval=refresh_ms, key="adaptive_refresh")

# 4. SIDEBAR - PORTFOLIO & BUDGET
with st.sidebar:
    st.title("💼 Portfolio & Budget")
    budget = st.number_input("💰 งบซื้อเหรียญ (บาท):", min_value=0.0, value=5000.0, step=500.0)
    
    st.divider()
    # แสดงเหรียญที่ถืออยู่ (จาก Sheets)
    try:
        df_port = pd.read_csv(SHEET_URL)
        df_port.columns = df_port.columns.str.strip().str.lower()
        if not df_port.empty:
            st.subheader("📌 ปักหมุดไว้")
            for _, row in df_port.iterrows():
                sym = row['symbol'].upper()
                m_data = df_market[df_market['symbol'] == f"{sym}USDT"]
                if not m_data.empty:
                    p = m_data['price'].values[0] * rate
                    st.write(f"**{sym}**: {p:,.2f} ฿")
    except: st.info("ยังไม่มีเหรียญใน Sheets")

# 5. MAIN UI - TOP 6 BUDGET RECOMMENDATION
st.title("🪙 Budget-bet AI")
st.caption(f"Refresh ทุก {refresh_ms/1000} วินาที | กรองเหรียญราคาไม่เกิน {budget:,.2f} ฿")

if not df_market.empty:
    # กรองเหรียญที่ราคา (บาท) <= งบ และไม่ใช่เหรียญ Stablecoin (USD)
    df_filtered = df_market.copy()
    df_filtered['price_thb'] = df_filtered['price'] * rate
    
    # เงื่อนไข: ราคาอยู่ในงบ, เป็นคู่ USDT, และไม่ใช่เหรียญประหลาด
    recommend = df_filtered[
        (df_filtered['price_thb'] <= budget) & 
        (df_filtered['symbol'].str.endswith('USDT')) & 
        (~df_filtered['symbol'].str.contains('UP|DOWN|BEAR|BULL'))
    ].sort_values(by='change', ascending=False).head(6)

    if recommend.empty:
        st.warning("❌ ไมพบเหรียญที่อยู่ในงบของคุณ ลองเพิ่มงบประมาณดูครับ")
    else:
        cols = st.columns(2)
        for idx, (i, row) in enumerate(recommend.iterrows()):
            sym = row['symbol'].replace('USDT', '')
            with cols[idx % 2]:
                with st.container(border=True):
                    # AI Advice ง่ายๆ
                    color = "#00ffcc" if row['change'] > 0 else "#ff4b4b"
                    advice = "📈 น่าตาม" if row['change'] > 2 else ("📉 รอช้อน" if row['change'] < -2 else "⏳ รอดู")
                    
                    st.subheader(f"{sym}")
                    st.markdown(f"<small>{advice}</small>", unsafe_allow_html=True)
                    st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                    
                    # Mini Chart
                    fig = go.Figure(go.Scatter(y=[row['price_thb'] * (1 - row['change']/100), row['price_thb']], 
                                             line=dict(color=color, width=3)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, 
                                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}", config={'displayModeBar': False})
else:
    st.error("📡 ระบบกำลังสลับไปใช้ API สำรอง... กรุณารอสักครู่")
