import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Ultimate", layout="wide")

# CSS: ตกแต่ง UI
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE (ดึงข้อมูลพร้อมดัก Error)
def get_data():
    try:
        # ลองดึงข้อมูลจาก Binance API 
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=7)
        if res.status_code == 200:
            data = res.json()
            if not data: return pd.DataFrame()
            df = pd.DataFrame(data)
            df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
            df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
            df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna()
    except Exception as e:
        print(f"Error fetching data: {e}")
    return pd.DataFrame()

# 3. REFRESH CONTROL (30 วินาที)
st_autorefresh(interval=30000, key="v5_refresh")

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Safe Mode")
    # งบเริ่มต้นเป็น 0
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.info("ระบบกรองเฉพาะเหรียญ Top 30/100 เพื่อลดความเสี่ยงสำหรับมือใหม่")
    
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        if not df_port.empty:
            for _, row in df_port.iterrows():
                st.write(f"📌 {str(row['symbol']).upper()}")
    except:
        st.caption("เชื่อมต่อ Google Sheets เพื่อดูพอร์ต")

# 5. MAIN UI
st.title("🪙 Smart Safe Selection")

# --- จุดสำคัญ: ประกาศตัวแปรไว้ก่อนเพื่อป้องกัน Error บรรทัด 55 ---
df_market = get_data()

# ตรวจสอบว่ามีข้อมูลจริงไหม
if df_market is not None and not df_market.empty:
    # --- กรองเหรียญคุณภาพ (ตัด Stablecoin และเหรียญปั่นออก) ---
    df_clean = df_market.copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    df_clean = df_clean[
        (df_clean['symbol'].str.endswith('USDT')) & 
        (~df_clean['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ].copy()

    # --- การจัดอันดับ (Ranking) ตาม Volume ---
    # เรียงตามความนิยม (Volume) เพื่อหาเหรียญที่เสถียร Top 30
    top_active = df_clean.sort_values(by='volume', ascending=False).head(30)

    # --- Logic เลือกเหรียญโชว์ 6 ตัว ---
    if budget > 0:
        # กรองเอาเฉพาะที่ราคาอยู่ในงบ
        recommend = top_active[top_active['price_thb'] <= budget].head(6)
        # ถ้าใน Top 30 ไม่มีตัวไหนราคาต่ำพอกับงบ ให้ขยายไป Top 100 (เหรียญเล็กแต่ยังปลอดภัย)
        if recommend.empty:
            top_100 = df_clean.sort_values(by='volume', ascending=False).head(100)
            recommend = top_100[top_100['price_thb'] <= budget].head(6)
            label = f"💎 Gem Picks (Top 100) | งบ {budget:,.0f} ฿"
        else:
            label = f"🛡️ Safe Picks (Top 30) | งบ {budget:,.0f} ฿"
    else:
        # ถ้าเงินเป็น 0 ให้โชว์ผู้นำตลาด (BTC, ETH, ...)
        recommend = top_active.head(6)
        label = "🏆 Global Market Leaders (Most Active)"

    st.subheader(label)
    
    # --- เริ่มวาดการ์ดเหรียญ ---
    if not recommend.empty:
        col1, col2 = st.columns(2)
        items = recommend.to_dict('records')
        
        for idx, row in enumerate(items):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            with target_col:
                with st.container(border=True):
                    # วิเคราะห์สัญญาณจากราคาปัจจุบันเทียบราคาเปิด (Trend Analysis)
                    chg = row['change']
                    if chg < -4:
                        status, color, advice = "🟢 น่าซื้อสะสม", "#00ffcc", "ราคาย่อตัว เป็นจังหวะเข้าซื้อของดีราคาถูก"
                    elif chg > 8:
                        status, color, advice = "🔴 อย่าเพิ่งตาม", "#ff4b4b", "ราคาขึ้นแรงเกินไป เสี่ยงติดดอย รอย่อค่อยเข้า"
                    else:
                        status, color, advice = "🟡 ทยอยเก็บ", "#f1c40f", "ราคานิ่งสม่ำเสมอ เหมาะกับการออมระยะยาว"

                    # แสดงชื่อเหรียญและป้ายสถานะ
                    st.markdown(f"### {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # กราฟ Sparkline แสดงทิศทางสั้นๆ
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}_{idx}", config={'displayModeBar': False})
                    
                    st.info(f"💡 {advice}")
    else:
        st.warning(f"❌ ไม่พบเหรียญที่ราคาต่ำกว่า {budget:,.2f} ฿ ในกลุ่มเหรียญแนะนำ")
else:
    # กรณี API ล่ม หรือเน็ตมีปัญหา
    st.error("📡 ไม่สามารถดึงข้อมูลจากตลาดได้ในขณะนี้ กรุณารอ 30 วินาทีเพื่อให้ระบบโหลดใหม่")

# 6. คู่มือท้ายหน้า
st.divider()
with st.expander("📖 วิธีใช้งานสำหรับมือใหม่"):
    st.write("""
    1. **งบประมาณ:** กรอกจำนวนเงินที่คุณต้องการซื้อต่อ 1 เหรียญ ระบบจะคัดเหรียญที่คุณภาพดีที่สุดในราคานั้นมาให้
    2. **สัญญาณไฟจราจร:** - สีเขียว 🟢 = ของลดราคา (น่าซื้อ)
        - สีเหลือง 🟡 = ราคาปกติ (ซื้อเก็บเรื่อยๆ)
        - สีแดง 🔴 = ราคาสูง (รอไปก่อน)
    3. **ความปลอดภัย:** ระบบจะเลือกเฉพาะเหรียญที่มีมูลค่าการซื้อขายสูง (Top 30/100) เพื่อป้องกันการถูกปั่นราคา
    """)
