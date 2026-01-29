import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Precision Pro", layout="wide")

# CSS: Custom Styling
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE (ปรับปรุงให้ปลอดภัย 100%)
def get_data():
    providers = [
        {"url": "https://api.binance.com/api/v3/ticker/24hr", "type": "binance"},
        {"url": "https://api.gateio.ws/api/v4/spot/tickers", "type": "gateio"}
    ]
    
    for p in providers:
        try:
            res = requests.get(p["url"], timeout=5)
            if res.status_code == 200:
                data = res.json()
                df = pd.DataFrame(data)
                
                if df.empty: continue

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
        except Exception as e:
            continue
            
    # หากล่มทุกทาง ให้ส่ง DataFrame เปล่ากลับไปแทน None เพื่อกัน AttributeError
    return pd.DataFrame(columns=['symbol', 'price', 'change', 'volume', 'open_p']), "Disconnected"

# 3. REFRESH & STATE
st_autorefresh(interval=30000, key="v12_refresh")
df_raw, source = get_data() # รับค่ามา 2 ตัวเสมอ

# 4. SIDEBAR - Multi-User Logic
with st.sidebar:
    st.title("👤 User Access")
    # 3 คนใช้งาน แยกชื่อชัดเจน
    current_user = st.selectbox("เลือกผู้ใช้งาน:", ["Admin (ผู้สร้าง)", "User_A", "User_B"])
    
    st.divider()
    st.subheader(f"💵 งบของ {current_user}")
    budget = st.number_input("งบซื้อต่อหน่วย (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.caption(f"Connected: {source.upper()}")
    
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        if 'owner' in df_port.columns:
            user_data = df_port[df_port['owner'] == current_user]
            if not user_data.empty:
                for _, row in user_data.iterrows():
                    st.write(f"📌 {str(row['symbol']).upper()}")
            else:
                st.caption("ไม่มีเหรียญในพอร์ต")
        else:
            st.warning("Sheets ต้องมีคอลัมน์ 'owner'")
    except:
        st.caption("รอเชื่อมต่อ Sheets...")

# 5. MAIN UI - Yahoo Precision Waterfall
st.title(f"🪙 Smart Terminal: {current_user}")

# แก้ไขจุดล่ม: เช็คว่า df_raw ไม่เป็น None และไม่ว่าง
if df_raw is not None and not df_raw.empty:
    # --- STEP 1: Global Scan 200 ตัวแรก ---
    df_global = df_raw.copy()
    df_global = df_global[
        (df_global['symbol'].str.endswith('USDT')) & 
        (~df_global['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ]
    df_global = df_global.sort_values(by='volume', ascending=False).head(200)
    
    # --- STEP 2: Pre-Stamp (🔵/🪙) ---
    df_global['rank'] = range(1, len(df_global) + 1)
    df_global['stamp'] = df_global['rank'].apply(lambda x: "🔵" if x <= 30 else "🪙")
    
    # --- STEP 3: กรองตามงบ ---
    df_global['price_thb'] = df_global['price'] * EXCHANGE_RATE
    if budget > 0:
        affordable_df = df_global[df_global['price_thb'] <= budget].copy()
    else:
        affordable_df = df_global.copy()

    # --- STEP 4: แสดงผล 6 ตัวที่ดังที่สุดในกลุ่มนั้น ---
    recommend = affordable_df.head(6)

    st.subheader(f"🚀 Top Assets Under {budget:,.0f} THB" if budget > 0 else "🏆 Market Leaders")

    if not recommend.empty:
        col1, col2 = st.columns(2)
        for idx, row in enumerate(recommend.to_dict('records')):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    if chg < -4: status, color = "🟢 น่าซื้อ", "#00ffcc"
                    elif chg > 10: status, color = "🔴 ระวังดอย", "#ff4b4b"
                    else: status, color = "🟡 ทยอยเก็บ", "#f1c40f"

                    st.markdown(f"### {row['stamp']} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}_{idx}", config={'displayModeBar': False})
    else:
        st.warning("❌ ไม่พบเหรียญที่ดังพอในงบนี้")
else:
    st.error("📡 ไม่สามารถเชื่อมต่อ API ได้ในขณะนี้ ระบบจะลองใหม่ใน 30 วินาที")
