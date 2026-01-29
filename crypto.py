import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Precision Pro", layout="wide")

# CSS ตกแต่ง Card
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DUAL-ENGINE DATA FETCHING
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
st_autorefresh(interval=30000, key="v9_refresh")
df_raw, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Precision Mode")
    budget = st.number_input("💵 งบซื้อเหรียญต่อหน่วย (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.caption(f"Connected: {source.upper()}")

# 5. MAIN UI - PRECISION LOGIC
st.title("🪙 Yahoo-Style Precision Filter")

if not df_raw.empty:
    # --- STEP 1: ดึงเหรียญคุณภาพ 200 ตัวแรกของโลก (ตาม Volume) ---
    df_global = df_raw.copy()
    df_global = df_global[
        (df_global['symbol'].str.endswith('USDT')) & 
        (~df_global['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ]
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    df_global['global_rank'] = range(1, len(df_global) + 1)
    
    # --- STEP 2: บันทึกรายชื่อ Top 30 ของโลก ---
    top_30_world_list = df_global[df_global['global_rank'] <= 30]['symbol'].tolist()
    
    # --- STEP 3: กรองตามงบ (Budget First) ---
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    if budget > 0:
        affordable_df = df_global[df_global['price_thb'] <= budget].copy()
    else:
        affordable_df = df_global.copy()

    # --- STEP 4: เลือกตัวที่ดังที่สุดในกลุ่มนั้น (Yahoo Rank) ---
    recommend = affordable_df.head(6)

    st.subheader(f"🚀 Top Active Assets Under {budget:,.0f} THB" if budget > 0 else "🏆 Global Market Leaders")

    # วาด Card และแปะ Stamp (🔵 หรือ 🪙)
    if not recommend.empty:
        col1, col2 = st.columns(2)
        for idx, row in enumerate(recommend.to_dict('records')):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            # แปะตราตามอันดับโลก
            stamp = "🔵" if row['symbol'] in top_30_world_list else "🪙"
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    if chg < -4: status, color = "🟢 น่าช้อน (Dip)", "#00ffcc"
                    elif chg > 10: status, color = "🔴 อย่าเพิ่งตาม", "#ff4b4b"
                    else: status, color = "🟡 ทยอยเก็บ (DCA)", "#f1c40f"

                    st.markdown(f"### {stamp} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Sparkline
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}", config={'displayModeBar': False})
                    st.caption(f"Global Rank: #{row['global_rank']} | Vol: ${row['volume']/1e6:,.1f}M")
    else:
        st.warning("❌ ไม่พบเหรียญที่ดังพอในงบนี้ ลองเพิ่มงบดูครับ")
else:
    st.error("📡 ไม่สามารถเชื่อมต่อข้อมูลได้...")

# 6. EXPLANATION
st.divider()

with st.expander("📖 ทำความเข้าใจระบบ Yahoo Precision"):
    st.markdown("""
    1. **Blue Chip (🔵):** เหรียญที่ติดอันดับความนิยม 30 อันดับแรกของโลก (ความเสี่ยงต่ำสุด)
    2. **Market Gems (🪙):** เหรียญคุณภาพอันดับ 31-200 ของโลกที่ราคาย่อมเยากว่า
    3. **Ranking Logic:** ระบบจะมองหางบที่คุณจ่ายไหวก่อน แล้วจึงเลือกตัวที่มีการซื้อขายสูงสุด (ดังที่สุด) มาให้คุณตัดสินใจ
    """)
