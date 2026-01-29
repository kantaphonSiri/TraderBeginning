import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. CONFIG & SETTINGS
# ---------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
# ใส่ Line Token ของคุณที่นี่ (ถ้ามี)
LINE_TOKEN = "" 

st.set_page_config(page_title="Budget-bet Ultimate", layout="wide")

# CSS ตกแต่ง Card ให้ดู Pro และรองรับมือถือ
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    .stMetric { background: #161a1e; padding: 10px; border-radius: 10px; border: 1px solid #2b2f36; }
    @media (max-width: 640px) { h3 { font-size: 14px !important; } .stMetric div { font-size: 14px !important; } }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE (Binance + Gate.io Hybrid)
# ---------------------------------------------------------
def get_market_data():
    # แผน A: Binance
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://api3.binance.com/api/v3/ticker/24hr"]:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                return df
        except: continue
    # แผน B: Gate.io
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=5)
        df = pd.DataFrame(res.json())
        df['symbol'] = df['currency_pair'].str.replace('_', '')
        df['price'] = pd.to_numeric(df['last'], errors='coerce')
        df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
        df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
        return df
    except: return pd.DataFrame()

# ---------------------------------------------------------
# 3. INITIALIZE & ADAPTIVE REFRESH
# ---------------------------------------------------------
df_market = get_market_data()
rate = 35.5
refresh_ms = 30000 # Default 30s

if not df_market.empty:
    btc_row = df_market[df_market['symbol'] == 'BTCUSDT']
    if not btc_row.empty:
        btc_chg = abs(btc_row['change'].values[0])
        refresh_ms = 10000 if btc_chg > 4 else (30000 if btc_chg > 1.5 else 60000)

st_autorefresh(interval=refresh_ms, key="adaptive_ref")

# ---------------------------------------------------------
# 4. SIDEBAR - BUDGET & PORTFOLIO
# ---------------------------------------------------------
with st.sidebar:
    st.title("💰 Settings")
    # งบเริ่มต้นเป็น 0 ตามต้องการ
    budget = st.number_input("งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=500.0)
    st.caption("💡 ใส่ 0 เพื่อดูเหรียญมาแรงทั้งตลาด")
    
    st.divider()
    st.subheader("📋 Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        df_port.columns = df_port.columns.str.strip().str.lower()
        if not df_port.empty and not df_market.empty:
            for _, row in df_port.iterrows():
                s = str(row['symbol']).upper()
                m = df_market[df_market['symbol'] == f"{s}USDT"]
                if not m.empty:
                    p = m['price'].values[0] * rate
                    st.write(f"**{s}**: {p:,.2f} ฿")
    except: st.caption("เชื่อมต่อ Sheets เพื่อดูข้อมูล")

# ---------------------------------------------------------
# 5. MAIN UI - TOP 6 RECOMMENDATION
# ---------------------------------------------------------
st.title("🪙 Budget-bet Pro")
status_icon = "🔥" if refresh_ms == 10000 else "🟢"
st.caption(f"{status_icon} Refresh: {refresh_ms/1000}s | Rate: {rate} THB")

if not df_market.empty:
    # ระบุ Top 30 ตามโวลุ่ม (ความนิยม)
    top_30 = df_market.sort_values(by='volume', ascending=False).head(30)['symbol'].tolist()
    
    # เตรียมข้อมูลสำหรับแสดงผล
    df_show = df_market.copy()
    df_show['price_thb'] = df_show['price'] * rate
    # กรองเฉพาะ USDT และไม่ใช่เหรียญ Stable
    df_show = df_show[
        (df_show['symbol'].str.endswith('USDT')) & 
        (~df_show['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD'))
    ]

    # Logic การกรอง
    if budget > 0:
        recommend = df_show[df_show['price_thb'] <= budget].sort_values(by='change', ascending=False).head(6)
        label = f"เหรียญในงบ {budget:,.0f} ฿"
    else:
        recommend = df_show.sort_values(by='change', ascending=False).head(6)
        label = "Top Gainers (ไม่จำกัดงบ)"

    st.subheader(f"🔍 {label}")
    
    if recommend.empty:
        st.warning("⚠️ ไม่พบเหรียญที่อยู่ในงบ")
    else:
        cols = st.columns(2)
        for idx, (i, row) in enumerate(recommend.iterrows()):
            sym = row['symbol'].replace('USDT', '')
            is_popular = row['symbol'] in top_30
            icon = "🏆" if is_popular else "💎"
            
            with cols[idx % 2]:
                with st.container(border=True):
                    # AI Advice
                    adv = "📈 น่าตาม" if row['change'] > 3 else ("📉 รอช้อน" if row['change'] < -3 else "✅ ทรงตัว")
                    
                    st.subheader(f"{icon} {sym}")
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                    
                    # Sparkline
                    fig = go.Figure(go.Scatter(y=[row['price_thb']/(1+row['change']/100), row['price_thb']], 
                                             line=dict(color="#00ffcc" if row['change'] > 0 else "#ff4b4b", width=4)))
                    fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, 
                                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}", config={'displayModeBar': False})
                    st.caption(f"💡 {adv} | {'Popular' if is_popular else 'Gem'}")
else:
    st.error("📡 กำลังพยายามเชื่อมต่อ API...")
