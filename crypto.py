import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIG & SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5

st.set_page_config(page_title="Budget-bet Safe & Smart", layout="wide")

# CSS ตกแต่ง Card และ Layout
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    .stMetric { background: #161a1e; padding: 10px; border-radius: 10px; border: 1px solid #2b2f36; }
    .signal-tag { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 10px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE
def get_market_data():
    urls = ["https://api.binance.com/api/v3/ticker/24hr", "https://api3.binance.com/api/v3/ticker/24hr"]
    for url in urls:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['change_24h'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
                return df[['symbol', 'price', 'change_24h', 'volume', 'open_p']]
        except: continue
    return pd.DataFrame()

# 3. INITIALIZE & REFRESH
df_market = get_market_data()
refresh_ms = 30000

if not df_market.empty:
    btc_row = df_market[df_market['symbol'] == 'BTCUSDT']
    if not btc_row.empty:
        btc_chg = abs(btc_row['change_24h'].values[0])
        refresh_ms = 10000 if btc_chg > 4 else (30000 if btc_chg > 1.5 else 60000)

st_autorefresh(interval=refresh_ms, key="smart_safe_refresh")

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Safe Mode")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=500.0)
    st.info("ระบบจะกรองเฉพาะ Top 30 เหรียญมหาชน (Blue Chip) เพื่อความปลอดภัยสูงสุด")
    
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        df_port.columns = df_port.columns.str.strip().str.lower()
        if not df_port.empty and not df_market.empty:
            for _, row in df_port.iterrows():
                s = str(row['symbol']).upper()
                m = df_market[df_market['symbol'] == f"{s}USDT"]
                if not m.empty:
                    p_thb = m['price'].values[0] * EXCHANGE_RATE
                    st.write(f"**{s}**: {p_thb:,.2f} ฿")
    except: st.caption("รอเชื่อมต่อ Sheets...")

# 5. MAIN UI (DISPLAY DATA FIRST)
st.title("🪙 Smart Safe Selection")
st.caption(f"Status: 🟢 Market Online | Refresh: {refresh_ms/1000}s")

if not df_market.empty:
    # กรองเหรียญคุณภาพ
    df_clean = df_market.copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    df_clean = df_clean[
        (df_clean['symbol'].str.endswith('USDT')) & 
        (~df_clean['symbol'].str.contains('UP|DOWN|BULL|BEAR|USDC|DAI|FDUSD'))
    ].copy()

    # เลือก Most Active Top 30
    top_30 = df_clean.sort_values(by='volume', ascending=False).head(30)

    # กรองตามงบ (Logic: ถ้าไม่มีใน Top 30 ให้ขยายไป Top 100 เพื่อไม่ให้หน้าจอโล่ง)
    recommend = top_30[top_30['price_thb'] <= budget].head(6) if budget > 0 else top_30.head(6)
    
    if recommend.empty and budget > 0:
        top_100 = df_clean.sort_values(by='volume', ascending=False).head(100)
        recommend = top_100[top_100['price_thb'] <= budget].head(6)
        label = f"💎 Gem (Top 100) Under {budget:,.0f} ฿"
    else:
        label = f"🛡️ Safe Mode (Top 30) Under {budget:,.0f} ฿" if budget > 0 else "🏆 Global Leaders (Top 30)"

    st.subheader(label)

    # แสดงผล Card เหรียญ
    if not recommend.empty:
        cols = st.columns(2)
        for idx, (i, row) in enumerate(recommend.iterrows()):
            sym = row['symbol'].replace('USDT', '')
            chg = row['change_24h']
            
            # Logic วิเคราะห์คำแนะนำ (1 Month Trend Simulation)
            if chg < -4:
                adv, color, desc = "🟢 น่าช้อน", "#00ffcc", "ราคาย่อตัว เป็นจังหวะสะสม"
            elif chg > 8:
                adv, color, desc = "🔴 รอย่อ", "#ff4b4b", "ราคาพุ่งแรงเกินไป เสี่ยงดอย"
            else:
                adv, color, desc = "🟡 ทยอยซื้อ", "#f1c40f", "ราคานิ่ง เหมาะกับการออม (DCA)"

            with cols[idx % 2]:
                with st.container(border=True):
                    st.markdown(f"### {sym} <span class='signal-tag' style='background:{color}; color:black;'>{adv}</span>", unsafe_allow_html=True)
                    st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Sparkline Graph
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=45, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"c_{sym}", config={'displayModeBar': False})
                    st.caption(f"💡 AI Advice: {desc}")
    else:
        st.warning("⚠️ ไม่พบเหรียญที่อยู่ในงบประมาณนี้ ลองขยับงบขึ้นนิดนึงครับ")

# 6. ย้ายคำแนะนำการใช้งานมาไว้ท้ายสุด
st.divider()
with st.expander("📖 คู่มือการอ่านคำแนะนำ (สำหรับมือใหม่)", expanded=False):
    st.write("""
    1. **น่าช้อน (🟢):** ใช้สำหรับเหรียญพื้นฐานดีที่ราคาตกชั่วคราว เป็นโอกาสซื้อของถูก
    2. **ทยอยซื้อ (🟡):** ใช้เมื่อราคาปกติ ไม่พุ่ง ไม่ดิ่ง เหมาะกับคนค่อยๆ เก็บออม
    3. **รอย่อ (🔴):** อย่าเพิ่งรีบซื้อตอนนี้ เพราะราคาวิ่งมาไกลแล้ว มีโอกาสโดนขายใส่
    """)
