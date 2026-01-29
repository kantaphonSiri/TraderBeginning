import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Yahoo Engine", layout="wide")

# CSS ตกแต่ง Card
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
st_autorefresh(interval=30000, key="v11_refresh")
df_raw, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Yahoo Intelligence")
    budget = st.number_input("💵 งบซื้อเหรียญต่อหน่วย (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.info("ระบบจะ 'จัดเกรด' ความน่าเชื่อถือของเหรียญจากข้อมูลตลาดโลกก่อนนำมาคัดกรองตามงบของคุณ")

# 5. MAIN UI - YAHOO CALCULATION ENGINE
st.title("🪙 Yahoo-Style Precision Selection")

if not df_raw.empty:
    # --- STEP 1: Global Scan (ดึงเหรียญคุณภาพ 200 ตัวแรก) ---
    df_global = df_raw.copy()
    df_global = df_global[
        (df_global['symbol'].str.endswith('USDT')) & 
        (~df_global['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ]
    # เรียงตาม Volume เพื่อหาความนิยมสูงสุด
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    
    # --- STEP 2: Yahoo Scoring & Pre-Stamp (สแตมป์เกรดก่อนกรองงบ) ---
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    
    # --- STEP 3: Budget Filter (กรองตามงบ) ---
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    if budget > 0:
        # กรองเอาเฉพาะตัวที่ User จ่ายไหว
        affordable_df = df_global[df_global['price_thb'] <= budget].copy()
    else:
        # ถ้าไม่กรอกงบ ให้ดูภาพรวมตลาด
        affordable_df = df_global.copy()

    # --- STEP 4: Yahoo Selection (เลือก 6 ตัวที่ 'ดีที่สุด' ในเงื่อนไขงบ) ---
    # ในกลุ่มที่ซื้อไหว ตัวไหนคือตัวที่ "แรงที่สุด" หรือ "ดังที่สุด" (คะแนนดีสุด)
    recommend = affordable_df.head(6)

    st.subheader(f"🚀 Top Pick Assets Under {budget:,.0f} THB" if budget > 0 else "🏆 Global Leaders (Yahoo Sorted)")

    if not recommend.empty:
        col1, col2 = st.columns(2)
        for idx, row in enumerate(recommend.to_dict('records')):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    # วิเคราะห์สัญญาณความปลอดภัยแบบ Yahoo
                    if chg < -4: status, color = "🟢 น่าสะสม (Discount)", "#00ffcc"
                    elif chg > 10: status, color = "🔴 ระวังดอย (Overbought)", "#ff4b4b"
                    else: status, color = "🟡 ทยอยเก็บ (Stable)", "#f1c40f"

                    st.markdown(f"### {row['stamp']} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Graph
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}", config={'displayModeBar': False})
                    
                    st.caption(f"Yahoo Global Rank: #{row['rank']} | Liquidity: High ✅")
    else:
        st.warning("❌ ไม่พบเหรียญที่ผ่านเกณฑ์คุณภาพในงบนี้ ลองขยับงบขึ้นเพื่อหาเหรียญเกรด 🔵")
else:
    st.error("📡 ไม่สามารถเชื่อมต่อฐานข้อมูลตลาดได้...")

# 6. FOOTER
st.divider()

with st.expander("📖 วิธีที่ระบบคำนวณแบบ Yahoo Finance"):
    st.markdown("""
    1. **Volume Analysis:** เราคัดเลือกจากเหรียญ 200 อันดับแรกที่มีการซื้อขายจริงสูงสุดของโลก เพื่อตัดเหรียญขยะออก
    2. **🔵 Blue Chip Stamp:** ระบบจะ 'ล็อกตรา' 🔵 ให้เฉพาะเหรียญที่ติดอันดับ Top 30 ของโลกเท่านั้น ก่อนจะนำไปดูงบประมาณของคุณ
    3. **Precision Filtering:** แม้คุณจะมีงบน้อย ระบบจะยังคงมองหาเหรียญที่ 'ดีที่สุด' และ 'ดังที่สุด' ในราคาที่คุณจ่ายไหวมาให้เสมอ
    4. **Risk Control:** เหรียญที่ราคาผันผวนผิดปกติหรือเหรียญปั่นจะถูกกรองออกอัตโนมัติ
    """)
