import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Yahoo Edition", layout="wide")

# CSS: ตกแต่ง UI
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    [data-testid="stExpander"] { border: 1px solid #2b2f36; background: #0e1117; }
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
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Gate.io (Backup)"
    except: pass
    
    return pd.DataFrame(), "Disconnected"

# 3. REFRESH & STATE
st_autorefresh(interval=30000, key="v7_refresh")
df_market, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Yahoo Filter")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.info(f"📡 Data Source: {source}")
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        if not df_port.empty:
            for _, row in df_port.iterrows():
                st.write(f"📌 {str(row['symbol']).upper()}")
    except: st.caption("รอเชื่อมต่อ Sheets...")

# 5. MAIN UI
st.title("🪙 Smart Safe Selection")
st.caption(f"Source: {source} | Yahoo Style Screening: Active Assets Only")

if not df_market.empty:
    # --- STEP 1: Yahoo-style Quality Screening ---
    df_clean = df_market.copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    
    # กรองเฉพาะเหรียญที่มีสภาพคล่องสูง (Volume > 1 ล้าน USD) และไม่ใช่เหรียญขยะ
    df_clean = df_clean[
        (df_clean['symbol'].str.endswith('USDT')) & 
        (df_clean['volume'] > 1000000) & 
        (~df_clean['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ].copy()

    # --- STEP 2: Ranking & Emoji Assignment ---
    # เรียงลำดับตามโวลุ่มเพื่อหาเหรียญมหาชน
    df_clean = df_clean.sort_values(by='volume', ascending=False)
    df_clean['rank'] = range(1, len(df_clean) + 1)
    
    # ฟังก์ชันติด Emoji
    def assign_emoji(rank):
        if rank <= 30: return "🔵" # Top 30 Blue Chip
        return "🪙" # Top 31-100 หรือเหรียญคุณภาพรองลงมา

    df_clean['emoji'] = df_clean['rank'].apply(assign_emoji)

    # --- STEP 3: Logic การแนะนำ ---
    top_30 = df_clean[df_clean['rank'] <= 30]
    top_100 = df_clean[df_clean['rank'] <= 100]

    if budget > 0:
        # พยายามหาใน Top 30 ก่อน ถ้าไม่มีค่อยไป Top 100
        recommend = top_30[top_30['price_thb'] <= budget].head(6)
        if recommend.empty:
            recommend = top_100[top_100['price_thb'] <= budget].head(6)
            label = f"🔍 เหรียญทางเลือกความเสี่ยงต่ำ ในงบ {budget:,.0f} ฿"
        else:
            label = f"🛡️ เหรียญมหาชน (Blue Chip) ในงบ {budget:,.0f} ฿"
    else:
        # ถ้ายังไม่กรอกงบ โชว์ตัวท็อป 6 ของตลาด
        recommend = top_30.head(6)
        label = "🔥 Yahoo Most Active: ผู้นำตลาดวันนี้"

    st.subheader(label)
    
    # --- STEP 4: วาด Card แสดงผล ---
    if not recommend.empty:
        col1, col2 = st.columns(2)
        items = recommend.to_dict('records')
        
        for idx, row in enumerate(items):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            emoji = row['emoji']
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    # วิเคราะห์สัญญาณความปลอดภัย (Safe Analysis)
                    if chg < -4:
                        status, color, advice = "🟢 น่าซื้อสะสม", "#00ffcc", "ราคาย่อตัวลงมา เป็นโอกาสช้อนของดีราคาถูก"
                    elif chg > 8:
                        status, color, advice = "🔴 อย่าเพิ่งตาม", "#ff4b4b", "ราคาวิ่งแรงเกินไป ระวังติดดอย รอย่อค่อยเข้า"
                    else:
                        status, color, advice = "🟡 ทยอยเก็บ", "#f1c40f", "ราคาเคลื่อนไหวปกติ เหมาะกับการออมระยะยาว (DCA)"

                    st.markdown(f"### {emoji} {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Sparkline
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}_{idx}", config={'displayModeBar': False})
                    
                    st.caption(f"Rank: #{row['rank']} | {advice}")
    else:
        st.warning(f"❌ ไม่พบเหรียญคุณภาพที่ราคาต่ำกว่า {budget:,.2f} ฿")
else:
    st.error("📡 ระบบกำลังพยายามเชื่อมต่อ API ตลาดใหม่...")

# 6. คู่มือท้ายหน้า
st.divider()
with st.expander("📖 ความหมายของสัญลักษณ์"):
    st.markdown("""
    - **🔵 (Blue Chip):** เหรียญระดับ Top 30 ของโลก มีความน่าเชื่อถือสูงและสภาพคล่องมหาศาล (ความเสี่ยงต่ำสุด)
    - **🪙 (Potential Gem):** เหรียญระดับ Top 31-100 ที่ผ่านการคัดกรองโวลุ่มแล้ว มีพื้นฐานดีแต่อาจผันผวนกว่า Blue Chip
    - **การกรองแบบ Yahoo:** เราตัดเหรียญที่ไม่มีคนเทรด (Volume ต่ำ) ออกทั้งหมด เพื่อป้องกันไม่ให้คุณไปซื้อเหรียญที่ซื้อง่ายแต่ขายยาก
    """)
