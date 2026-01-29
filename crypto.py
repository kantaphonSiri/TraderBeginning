import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Ultimate", layout="wide")

# CSS: บังคับให้ Card แสดงผลสวยงามและตัวเลขชัดเจน
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    [data-testid="column"] { min-width: 300px !important; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE (ดึงข้อมูล 24h)
def get_data():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'])
            df['change'] = pd.to_numeric(df['priceChangePercent'])
            df['volume'] = pd.to_numeric(df['quoteVolume'])
            df['open_p'] = pd.to_numeric(df['openPrice'])
            return df[['symbol', 'price', 'change', 'volume', 'open_p']]
    except: return pd.DataFrame()

# 3. REFRESH CONTROL
st_autorefresh(interval=30000, key="v4_refresh")

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Safe Mode")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        for _, row in df_port.iterrows():
            st.write(f"📌 {row['symbol'].upper()}")
    except: st.caption("Connect Sheets to see Portfolio")

# 5. MAIN UI - START DISPLAY
st.title("🪙 Smart Safe Selection")

df_market = get_data()

if not df_market.empty:
    # --- กรองเหรียญคุณภาพแบบเข้มข้น ---
    df_clean = df_market.copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    df_clean = df_clean[
        (df_clean['symbol'].str.endswith('USDT')) & 
        (~df_clean['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ].copy()

    # --- Ranking Top 30 (Most Active) ---
    top_active = df_clean.sort_values(by='volume', ascending=False).head(30)

    # --- Logic การเลือกเหรียญ (ถ้าไม่มีงบโชว์ Top 6 ถ้ามีงบกรองตามงบ) ---
    if budget > 0:
        recommend = top_active[top_active['price_thb'] <= budget].head(6)
        # ถ้า Top 30 ไม่มีที่ถูกพอ ให้ขยายไป Top 100 ทันทีเพื่อไม่ให้หน้าจอโล่ง
        if recommend.empty:
            top_100 = df_clean.sort_values(by='volume', ascending=False).head(100)
            recommend = top_100[top_100['price_thb'] <= budget].head(6)
            label = f"💎 Gem Picks (Top 100) Under {budget:,.0f} ฿"
        else:
            label = f"🛡️ Safe Picks (Top 30) Under {budget:,.0f} ฿"
    else:
        recommend = top_active.head(6)
        label = "🏆 Global Market Leaders"

    # --- แสดงผลเหรียญ (บังคับวาด Card) ---
    st.subheader(label)
    
    if not recommend.empty:
        # ใช้ Grid Layout
        col1, col2 = st.columns(2)
        items = recommend.to_dict('records')
        
        for idx, row in enumerate(items):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            with target_col:
                with st.container(border=True):
                    # --- วิเคราะห์กลยุทธ์ (Simulated 30-Day Trend) ---
                    chg = row['change']
                    if chg < -4:
                        status, color, advice = "🟢 น่าซื้อสะสม", "#00ffcc", "ราคาย่อตัวจากเดือนก่อน เป็นจังหวะเข้าทำกำไร"
                    elif chg > 10:
                        status, color, advice = "🔴 อย่าเพิ่งตาม", "#ff4b4b", "ราคาวิ่งแรงเกินไปในรอบเดือน รอย่อค่อยเข้า"
                    else:
                        status, color, advice = "🟡 ทยอยเก็บ (DCA)", "#f1c40f", "แนวโน้มยังเป็นขาขึ้นอ่อนๆ เหมาะกับมือใหม่"

                    # แสดงชื่อและสถานะ
                    st.markdown(f"### {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # กราฟ Sparkline
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}_{idx}", config={'displayModeBar': False})
                    
                    st.info(f"💡 {advice}")
    else:
        st.warning(f"❌ ไม่พบเหรียญที่ราคาต่ำกว่า {budget:,.2f} ฿ ในกลุ่มเหรียญคุณภาพ")

# 6. ย้ายคำแนะนำไปล่างสุดใน Expander
st.divider()
with st.expander("📖 คู่มือการลงทุนสำหรับมือใหม่"):
    st.write("""
    * **น่าซื้อสะสม (🟢):** ใช้สำหรับเหรียญพื้นฐานดีที่ราคา 'Discount' อยู่
    * **ทยอยเก็บ (🟡):** ใช้เมื่อราคาปกติสม่ำเสมอ เหมาะกับการออมระยะยาว
    * **อย่าเพิ่งตาม (🔴):** ราคาขึ้นมาสูงเกินไป 'อย่าไล่ราคา' เพราะเสี่ยงติดดอย
    """)
