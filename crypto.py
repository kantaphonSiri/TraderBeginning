import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Precision", layout="wide")

# CSS: ตกแต่ง UI
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DUAL-ENGINE DATA FETCHING
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

    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['symbol'] = df['currency_pair'].str.replace('_', '')
            df['price'] = pd.to_numeric(df['last'], errors='coerce')
            df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
            df['open_p'] = df['price'] / (1 + (df['change'] / 100))
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Gate.io"
    except: pass
    return pd.DataFrame(), "Disconnected"

# 3. REFRESH & STATE
st_autorefresh(interval=30000, key="v8_refresh")
df_market, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Precision Filter")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.info(f"📡 Data Source: {source}")

# 5. MAIN UI
st.title("🪙 Precision Selection")
st.caption(f"Strategy: Budget First, Rank Stamp Second")

if not df_market.empty:
    # --- STEP 1: ดึงข้อมูลและคัดเหรียญคุณภาพ (Volume > 1M) ---
    df_all = df_market.copy()
    df_all['price_thb'] = df_all['price'] * EXCHANGE_RATE
    df_all = df_all[
        (df_all['symbol'].str.endswith('USDT')) & 
        (df_all['volume'] > 1000000) & 
        (~df_all['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ].copy()

    # --- STEP 2: จัดอันดับความดังระดับโลก (Global Rank) ---
    df_all = df_all.sort_values(by='volume', ascending=False)
    df_all['rank'] = range(1, len(df_all) + 1)
    
    # เก็บรายชื่อ Top 30 ของโลกไว้ในลิสต์
    top_30_world = df_all[df_all['rank'] <= 30]['symbol'].tolist()

    # --- STEP 3 & 4: กรองตามงบ และเลือกเหรียญที่ดังที่สุดในกลุ่มนั้น ---
    if budget > 0:
        # เลือกเฉพาะเหรียญที่ User ซื้อไหว
        affordable_df = df_all[df_all['price_thb'] <= budget].copy()
        # ในบรรดางบที่พอ ให้เลือกตัวที่ "ดังที่สุด" (Rank ดีที่สุด) 6 อันดับแรก
        recommend = affordable_df.head(6)
        label = f"🔍 เหรียญที่คุ้มค่าที่สุดในงบ {budget:,.0f} ฿"
    else:
        # ถ้าไม่กรอกงบ โชว์ตัวท็อปสุดของตลาด
        recommend = df_all.head(6)
        label = "🔥 Most Active Leaders"

    st.subheader(label)
    
    # --- STEP 5: แปะตรา (Stamp) และวาด Card ---
    if not recommend.empty:
        col1, col2 = st.columns(2)
        items = recommend.to_dict('records')
        
        for idx, row in enumerate(items):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            # ตรวจสอบตราสแตมป์
            is_top_30 = row['symbol'] in top_30_world
            stamp = "🔵" if is_top_30 else "🪙"
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    # วิเคราะห์สัญญาณ
                    if chg < -4:
                        status, color = "🟢 น่าซื้อสะสม", "#00ffcc"
                    elif chg > 8:
                        status, color = "🔴 อย่าเพิ่งตาม", "#ff4b4b"
                    else:
                        status, color = "🟡 ทยอยเก็บ", "#f1c40f"

                    st.markdown(f"### {stamp} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคา", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Graph
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}_{idx}", config={'displayModeBar': False})
                    
                    st.caption(f"Global Rank: #{row['rank']} | Volume: ${row['volume']/1e6:,.1f}M")
    else:
        st.warning(f"❌ ไม่พบเหรียญแนะนำที่ราคาต่ำกว่า {budget:,.2f} ฿")
else:
    st.error("📡 ไม่สามารถเชื่อมต่อข้อมูลได้ กรุณารอครู่...")

# 6. คู่มือ
st.divider()
with st.expander("📖 ความหมายของสัญลักษณ์ Precision"):
    st.markdown(f"""
    - **🔵 (Blue Chip):** ติดอันดับ Top 30 ของโลกในขณะนี้ (ความปลอดภัยสูงสุด)
    - **🪙 (Market Gems):** อยู่นอกอันดับ 30 ของโลก แต่มี Volume สูงและคุณภาพดี
    - **ลำดับการเลือก:** ระบบคัดจากงบประมาณของคุณก่อน แล้วจึงเลือกเหรียญที่ 'ดังที่สุด' ในช่วงราคานั้นมาให้
    """)
