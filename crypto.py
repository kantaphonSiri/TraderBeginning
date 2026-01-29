import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Precision V2", layout="wide")

# CSS: ตกแต่ง UI
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE
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
    return pd.DataFrame(), "Disconnected"

# REFRESH & STATE
st_autorefresh(interval=30000, key="v9_refresh")
df_raw, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Precision Filter")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=5000.0, step=1000.0)
    st.info(f"📡 Data Source: {source}")

# 5. MAIN LOGIC (ตามลำดับที่คุณต้องการ)
st.title("🪙 Precision Selection")

if not df_raw.empty:
    # --- STEP 1: ดึงข้อมูลและคัดเหรียญคุณภาพ (เหรียญหลักๆ ที่มี Volume) ---
    df_quality = df_raw.copy()
    df_quality = df_quality[
        (df_quality['symbol'].str.endswith('USDT')) & 
        (~df_quality['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ].copy()
    
    # --- STEP 2: กรองความดังระดับโลก (Global Rank) ---
    # เรียงลำดับตาม Volume ทั้งตลาดเพื่อหาเบอร์ 1-30 ของโลกจริงๆ
    df_quality = df_quality.sort_values(by='volume', ascending=False).reset_index(drop=True)
    df_quality['rank'] = range(1, len(df_quality) + 1)
    
    # สร้าง List ของ Top 30 ไว้สำหรับแปะตรา
    top_30_world = df_quality[df_quality['rank'] <= 30]['symbol'].tolist()

    # --- STEP 3: กรองตามงบ (Budget First) ---
    # คำนวณราคาก่อนกรอง
    df_quality['price_thb'] = df_quality['price'] * EXCHANGE_RATE
    
    if budget > 0:
        # เลือกเฉพาะเหรียญที่ราคาต่ำกว่าหรือเท่ากับงบ
        affordable_df = df_quality[df_quality['price_thb'] <= budget].copy()
        # ในกลุ่มที่ซื้อไหว ให้เลือกตัวที่ Rank ดีที่สุด (ดังที่สุด) 6 อันดับแรก
        recommend = affordable_df.head(6) 
        label = f"🔍 เหรียญที่ 'ดังที่สุด' ในงบไม่เกิน {budget:,.0f} ฿"
    else:
        recommend = df_quality.head(6)
        label = "🔥 Most Active Leaders (No Budget Limit)"

    st.subheader(label)
    
    # --- STEP 4: แปะตรา (Stamp) และแสดงผล ---
    if not recommend.empty:
        col1, col2 = st.columns(2)
        items = recommend.to_dict('records')
        
        for idx, row in enumerate(items):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            # ตรวจสอบเงื่อนไขตราสแตมป์ 🔵 ถ้าติด Top 30 ของโลก
            stamp = "🔵" if row['symbol'] in top_30_world else "🪙"
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    # วิเคราะห์สัญญาณการซื้อ
                    if chg < -4: status, color = "🟢 น่าซื้อสะสม", "#00ffcc"
                    elif chg > 8: status, color = "🔴 อย่าเพิ่งตาม", "#ff4b4b"
                    else: status, color = "🟡 ทยอยเก็บ", "#f1c40f"

                    st.markdown(f"### {stamp} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Mini Chart
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}_{idx}", config={'displayModeBar': False})
                    
                    st.caption(f"🏆 ความดังอันดับ: {row['rank']} | โวลุ่ม: ${row['volume']/1e6:,.1f}M")
    else:
        st.warning(f"❌ ไม่พบเหรียญที่ราคาต่ำกว่า {budget:,.2f} ฿ ในระบบ")

# 6. คู่มือ
st.divider()
with st.expander("📖 วิธีการคำนวณแบบ Precision"):
    st.markdown(f"""
    1. **Global Scan:** ระบบดึงข้อมูลเหรียญทั้งหมดที่มีการซื้อขายสูงสุดในตลาด
    2. **Ranking:** จัดลำดับความนิยม (Volume) ทั่วโลกจาก 1 ไปถึงหลักร้อย
    3. **Budget Filter:** คัดเฉพาะเหรียญที่คุณมีเงินพอซื้อได้ 1 เหรียญ (ราคาเหรียญ <= {budget} ฿)
    4. **Top Selection:** ในบรรดาเหรียญที่งบคุณถึง ระบบจะหยิบตัวที่ **'อันดับโลกดีที่สุด'** มาโชว์
    5. **Stamp:** - **🔵 Blue Chip:** คือเหรียญที่ติดอันดับความนิยม Top 30 ของโลก
        - **🪙 Market Gem:** คือเหรียญที่งบคุณซื้อได้ และดังที่สุดในกลุ่มนั้น แต่อยู่นอกอันดับ 30
    """)
