import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Pre-Stamp Pro", layout="wide")

# CSS ตกแต่ง UI
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE
def get_data():
    providers = [
        {"url": "https://api.binance.com/api/v3/ticker/24hr", "type": "binance"},
        {"url": "https://api.gateio.ws/api/v4/spot/tickers", "type": "gateio"}
    ]
    for p in providers:
        try:
            res = requests.get(p["url"], timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                if p["type"] == "binance":
                    df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                    df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                    df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
                else:
                    df['symbol'] = df['currency_pair'].str.replace('_', '')
                    df['price'] = pd.to_numeric(df['last'], errors='coerce')
                    df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
                    df['open_p'] = df['price'] / (1 + (df['change'] / 100))
                return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), p["type"]
        except: continue
    return pd.DataFrame(), "Disconnected"

# 3. REFRESH & STATE
st_autorefresh(interval=30000, key="v10_refresh")
df_raw, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Pre-Stamp Mode")
    budget = st.number_input("💵 งบซื้อเหรียญต่อหน่วย (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.caption(f"Connected: {source.upper()}")
    st.info("สแตมป์เกรดเหรียญตามอันดับโลกก่อนกรองงบ เพื่อความแม่นยำสูงสุด")

# 5. MAIN UI
st.title("🪙 Yahoo-Style Precision Filter")

if not df_raw.empty:
    # --- STEP 1: Global Scan (ดึงเหรียญคุณภาพ 200 ตัวแรก) ---
    df_global = df_raw.copy()
    df_global = df_global[
        (df_global['symbol'].str.endswith('USDT')) & 
        (~df_global['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ]
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    
    # --- STEP 2: Pre-Stamp (สแตมป์เกรดก่อนกรองงบ) ---
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    
    # --- STEP 3: Budget Filter (กรองตามงบ) ---
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    if budget > 0:
        affordable_df = df_global[df_global['price_thb'] <= budget].copy()
    else:
        affordable_df = df_global.copy()

    # --- STEP 4: Yahoo Selection (เลือก 6 ตัวที่ 'ดังที่สุด' ในกลุ่มที่ซื้อไหว) ---
    recommend = affordable_df.head(6)

    st.subheader(f"🚀 Top Assets Under {budget:,.0f} THB" if budget > 0 else "🏆 Global Leaders Today")

    if not recommend.empty:
        col1, col2 = st.columns(2)
        for idx, row in enumerate(recommend.to_dict('records')):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    if chg < -4: status, color = "🟢 น่าช้อน (Dip)", "#00ffcc"
                    elif chg > 10: status, color = "🔴 อย่าเพิ่งตาม", "#ff4b4b"
                    else: status, color = "🟡 ทยอยเก็บ (DCA)", "#f1c40f"

                    # แสดงผลพร้อม Stamp ที่ล็อกมาจากอันดับโลก
                    st.markdown(f"### {row['stamp']} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Sparkline
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}", config={'displayModeBar': False})
                    st.caption(f"Global Rank: #{row['rank']} | {advice if 'advice' in locals() else 'Market Active'}")
    else:
        st.warning("❌ ไม่พบเหรียญแนะนำในงบนี้ ลองขยับงบเพิ่มเพื่อดูเหรียญ 🔵 (Blue Chip)")
else:
    st.error("📡 ระบบกำลังเชื่อมต่อข้อมูลใหม่...")

# 6. EXPLANATION
st.divider()

with st.expander("📖 ความหมายของลำดับการกรอง (Pre-Stamp Logic)"):
    st.markdown("""
    1. **สแตมป์เกรดก่อน (Pre-Stamp):** ระบบจะจัดอันดับโลกก่อนว่าเหรียญไหนคือ 🔵 (Top 30) หรือ 🪙 (Top 200) เพื่อให้เกรดของเหรียญไม่เปลี่ยนไปตามงบประมาณ
    2. **กรองงบทีหลัง (Budget Filter):** เมื่อได้เหรียญที่แบ่งเกรดแล้ว ระบบจึงจะมาดูว่าคุณ 'ซื้อไหว' ที่ตัวไหนบ้าง
    3. **ความแม่นยำ:** วิธีนี้ทำให้คุณรู้ความจริงว่า ในงบของคุณ คุณกำลังซื้อเหรียญที่อยู่ระดับไหนของโลกจริงๆ
    """)
