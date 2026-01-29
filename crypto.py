import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. CONFIG & SETTINGS
# ---------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
LINE_TOKEN = "YOUR_LINE_TOKEN_HERE" # ใส่ Token ของคุณที่นี่

st.set_page_config(page_title="Budget-bet Ultimate", layout="wide")

# CSS ตกแต่ง UI
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; }
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. PRO-LEVEL DATA ENGINE (Hybrid & Volumetric)
# ---------------------------------------------------------
def get_market_data():
    # แผน A: Binance (ดึงข้อมูล 24h + Volume)
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://api3.binance.com/api/v3/ticker/24hr"]:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce') # มูลค่าการซื้อขาย (USDT)
                return df
        except: continue
    # แผน B: Gate.io สำรอง
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
# 3. ANALYSIS LOGIC & REFRESH
# ---------------------------------------------------------
df_market = get_market_data()
rate = 35.5
refresh_ms = 30000

if not df_market.empty:
    btc_chg = abs(df_market[df_market['symbol'] == 'BTCUSDT']['change'].values[0])
    # Adaptive Refresh: เดือด 10s | ปกติ 30s | นิ่ง 60s
    refresh_ms = 10000 if btc_chg > 4 else (30000 if btc_chg > 1.5 else 60000)

st_autorefresh(interval=refresh_ms, key="ultimate_refresh")

# ---------------------------------------------------------
# 4. SIDEBAR - BUDGET & PORTFOLIO
# ---------------------------------------------------------
with st.sidebar:
    st.title("💰 Setting")
    budget = st.number_input("งบซื้อเหรียญ (บาท):", min_value=0.0, value=5000.0)
    
    st.divider()
    st.subheader("📋 Portfolio Alerts")
    try:
        df_port = pd.read_csv(SHEET_URL)
        df_port.columns = df_port.columns.str.strip().str.lower()
        for _, row in df_port.iterrows():
            sym = row['symbol'].upper()
            m_data = df_market[df_market['symbol'] == f"{sym}USDT"]
            if not m_data.empty:
                curr_p = m_data['price'].values[0] * rate
                diff = ((curr_p - row['cost']) / row['cost']) * 100
                st.write(f"**{sym}**: {curr_p:,.2f} ฿ ({diff:+.2f}%)")
                # เด้งเตือนหน้าจอ
                if diff >= row['target']: st.toast(f"🚀 {sym} Profit!", icon="💰")
    except: st.info("Connect Sheets to see Portfolio")

# ---------------------------------------------------------
# 5. MAIN UI - TOP 6 INTELLIGENT RECOMMENDATION
# ---------------------------------------------------------
st.title("🪙 Budget-bet")
status_color = "🔴" if refresh_ms == 10000 else ("🟡" if refresh_ms == 30000 else "🟢")
st.caption(f"{status_color} Adaptive Refresh: {refresh_ms/1000}s | Rate: {rate} THB")

if not df_market.empty:
    # 1. ระบุกลุ่ม Top 30 ตาม Volume (ความนิยมจริง)
    top_30_list = df_market.sort_values(by='volume', ascending=False).head(30)['symbol'].tolist()
    
    # 2. กรองตามงบและคัดเฉพาะ USDT
    df_filtered = df_market.copy()
    df_filtered['price_thb'] = df_filtered['price'] * rate
    recommend = df_filtered[
        (df_filtered['price_thb'] <= budget) & 
        (df_filtered['symbol'].str.endswith('USDT')) &
        (~df_filtered['symbol'].str.contains('UP|DOWN'))
    ].sort_values(by='change', ascending=False).head(6)

    cols = st.columns(2)
    for idx, (i, row) in enumerate(recommend.iterrows()):
        sym_full = row['symbol']
        sym_name = sym_full.replace('USDT', '')
        
        # 3. วิเคราะห์เชิงลึก (Volume + Change)
        is_top30 = sym_full in top_30_list
        emoji = "🔵" if is_top30 else "🪙"
        
        # Logic คำแนะนำ
        if row['change'] > 5 and is_top30: advice = "🔥 แรงดี (Leader)"
        elif row['change'] > 10: advice = "⚠️ ระวังย่อ (High)"
        elif row['change'] < -3: advice = "📉 รอช้อน (Dip)"
        else: advice = "✅ ทรงตัว (Steady)"

        with cols[idx % 2]:
            with st.container(border=True):
                st.subheader(f"{emoji} {sym_name}")
                st.write(f"Rank: {'Top 30' if is_top30 else 'Gem'}")
                st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                
                # Mini Sparkline (เปรียบเทียบราคาเปิดกับปัจจุบัน)
                fig = go.Figure(go.Scatter(y=[row['price_thb']/(1+row['change']/100), row['price_thb']], 
                                         line=dict(color="#00ffcc" if row['change'] > 0 else "#ff4b4b", width=4)))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, 
                                 paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"c_{sym_full}", config={'displayModeBar': False})
                st.caption(f"💡 AI Advice: {advice}")

else:
    st.error("📡 การเชื่อมต่อขัดข้อง กำลังพยายามใหม่...")
