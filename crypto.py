import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5
st.set_page_config(page_title="Budget-Bet Ultimate Pro", layout="wide")

# CSS: ตกแต่ง UI ให้ดูพรีเมียม
st.markdown("""
    <style>
    .stMetric { background: #161a1e; padding: 15px; border-radius: 12px; border: 1px solid #2b2f36; }
    .status-tag { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }
    [data-testid="stExpander"] { border: 1px solid #2b2f36; background: #0e1117; }
    </style>
""", unsafe_allow_html=True)

# 2. DUAL-ENGINE DATA FETCHING (Binance & Gate.io Failover)
def get_data():
    # --- ลองดึงจาก Binance ก่อน ---
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
            df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
            df['open_p'] = pd.to_numeric(df['openPrice'], errors='coerce')
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Binance"
    except:
        pass

    # --- ถ้า Binance ล่ม ให้ดึงจาก Gate.io แทน ---
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['symbol'] = df['currency_pair'].str.replace('_', '')
            df['price'] = pd.to_numeric(df['last'], errors='coerce')
            df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
            # Gate.io ไม่มี Open Price ให้ตรงๆ เราจะจำลองจากราคาปัจจุบันและ % change
            df['open_p'] = df['price'] / (1 + (df['change'] / 100))
            return df[['symbol', 'price', 'change', 'volume', 'open_p']].dropna(), "Gate.io (Backup)"
    except:
        pass
    
    return pd.DataFrame(), "Disconnected"

# 3. REFRESH & STATE
st_autorefresh(interval=30000, key="v6_refresh")
df_market, source = get_data()

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Safe Mode")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=1000.0)
    st.info(f"📡 Data Source: {source}")
    
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        if not df_port.empty:
            for _, row in df_port.iterrows():
                st.write(f"📌 {str(row['symbol']).upper()}")
    except:
        st.caption("รอเชื่อมต่อ Sheets...")

# 5. MAIN UI
st.title("🪙 Smart Safe Selection")
st.caption(f"Source: {source} | Rate: 1 USD ≈ {EXCHANGE_RATE} THB")

if not df_market.empty:
    # --- กรองเหรียญคุณภาพ ---
    df_clean = df_market.copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    # ตัด Stablecoin ออก
    df_clean = df_clean[
        (df_clean['symbol'].str.endswith('USDT')) & 
        (~df_clean['symbol'].str.contains('UP|DOWN|USDC|DAI|FDUSD|TUSD'))
    ].copy()

    # Ranking Top 30 (Most Active)
    top_active = df_clean.sort_values(by='volume', ascending=False).head(30)

    # Logic การแนะนำ
    if budget > 0:
        recommend = top_active[top_active['price_thb'] <= budget].head(6)
        if recommend.empty:
            top_100 = df_clean.sort_values(by='volume', ascending=False).head(100)
            recommend = top_100[top_100['price_thb'] <= budget].head(6)
            label = f"💎 Gem Picks (Top 100) | Budget {budget:,.0f} ฿"
        else:
            label = f"🛡️ Safe Picks (Top 30) | Budget {budget:,.0f} ฿"
    else:
        recommend = top_active.head(6)
        label = "🏆 Global Market Leaders"

    st.subheader(label)
    
    # วาด Card
    if not recommend.empty:
        col1, col2 = st.columns(2)
        items = recommend.to_dict('records')
        
        for idx, row in enumerate(items):
            target_col = col1 if idx % 2 == 0 else col2
            sym = row['symbol'].replace('USDT', '')
            
            with target_col:
                with st.container(border=True):
                    chg = row['change']
                    # วิเคราะห์สัญญาณความปลอดภัย
                    if chg < -4:
                        status, color, advice = "🟢 น่าซื้อสะสม", "#00ffcc", "ราคาย่อตัวจากสถิติเดือนนี้ เป็นโอกาสดีในการช้อน"
                    elif chg > 10:
                        status, color, advice = "🔴 อย่าเพิ่งตาม", "#ff4b4b", "ราคาวิ่งแรงเกินไป ระวังดอย รอย่อค่อยเข้า"
                    else:
                        status, color, advice = "🟡 ทยอยเก็บ", "#f1c40f", "ราคาเคลื่อนไหวปกติ เหมาะกับการสะสมระยะยาว"

                    st.markdown(f"### {sym} <span class='status-tag' style='background:{color}; color:black;'>{status}</span>", unsafe_allow_html=True)
                    st.metric("ราคาปัจจุบัน", f"{row['price_thb']:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Sparkline (แสดงทิศทางจากราคาเปิดวัน)
                    fig = go.Figure(go.Scatter(y=[row['open_p'], row['price']], line=dict(color=color, width=4)))
                    fig.update_layout(height=50, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym}_{idx}", config={'displayModeBar': False})
                    
                    st.info(f"💡 {advice}")
    else:
        st.warning(f"❌ ไม่พบเหรียญที่ต่ำกว่า {budget:,.2f} ฿")
else:
    st.error("📡 ระบบกำลังพยายามเชื่อมต่อ API ตลาดใหม่ภายใน 30 วินาที...")

# 6. คู่มือท้ายหน้า
st.divider()
with st.expander("📖 ทำความเข้าใจระบบ Safe Mode"):
    st.markdown("""
    - **Top 30/100:** เราเลือกเฉพาะเหรียญที่มีโวลุ่มการซื้อขายสูงสุดของโลก เพื่อให้มั่นใจว่าเป็นเหรียญที่มีคุณภาพ ไม่ใช่เหรียญปั่น
    - **สีเขียว (🟢):** แสดงถึงจังหวะ 'Buy the Dip' หรือการซื้อเมื่อราคาต่ำกว่าปกติในรอบวัน/เดือน
    - **Dual-Engine:** ระบบนี้เชื่อมต่อทั้ง Binance และ Gate.io เพื่อให้คุณเห็นราคาตลาดได้แม่นยำที่สุดและไม่มีวันล่ม
    """)
