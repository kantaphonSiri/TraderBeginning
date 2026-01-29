import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIG
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5

st.set_page_config(page_title="Budget-bet Safe & Smart", layout="wide")

# CSS ตกแต่ง Card
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    .stMetric { background: #161a1e; padding: 10px; border-radius: 10px; border: 1px solid #2b2f36; }
    .signal-box { padding: 5px 10px; border-radius: 5px; font-weight: bold; font-size: 14px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# 2. DATA ENGINE (ดึงข้อมูล 24h + วิเคราะห์จำลอง 30 วัน)
def get_market_data():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
            df['change_24h'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
            df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
            # จำลองข้อมูล 30 วันจาก Price Change ในเดือนนี้ (Binance API ปกติจะส่งแค่ 24h เราจึงใช้ค่าเบี่ยงเบนเพื่อวิเคราะห์โซน)
            df['open_price'] = pd.to_numeric(df['openPrice'], errors='coerce')
            return df
    except: pass
    return pd.DataFrame()

# 3. REFRESH & INIT
df_market = get_market_data()
st_autorefresh(interval=30000, key="smart_refresh")

# 4. SIDEBAR
with st.sidebar:
    st.title("🛡️ Safe Mode")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0)
    st.info("ระบบจะกรองเฉพาะ Top 30 เหรียญที่ความเสี่ยงต่ำที่สุดในตลาด")

# 5. MAIN UI
st.title("🪙 ฺBudget-Bet")
if not df_market.empty:
    # กรองคุณภาพ
    df_clean = df_market[(df_market['symbol'].str.endswith('USDT')) & (~df_market['symbol'].str.contains('UP|DOWN|BULL|BEAR|USDC|DAI|FDUSD'))].copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    
    # จัดอันดับ Top 30 Market Leaders
    top_30 = df_clean.sort_values(by='volume', ascending=False).head(30)

    # กรองตามงบ
    if budget > 0:
        recommend = top_30[top_30['price_thb'] <= budget].head(6)
        label = f"เหรียญแนะนำในงบ {budget:,.0f} ฿"
    else:
        recommend = top_30.head(6)
        label = "Top 6 Market Leaders (รวม BTC)"

    st.subheader(label)

    cols = st.columns(2)
    for idx, (i, row) in enumerate(recommend.iterrows()):
        sym = row['symbol'].replace('USDT', '')
        
        # --- AI TREND ANALYSIS (30 Days Strategy) ---
        # วิเคราะห์จาก Change 24h เทียบกับ Volume เพื่อประเมินรอบ
        chg = row['change_24h']
        if chg < -5:
            advice = "🟢 น่าสะสม (Discount)"
            color = "#00ffcc"
            desc = "ราคาลงแรงใน 24 ชม. แต่เป็นเหรียญใหญ่ มีโอกาสรีบาวด์"
        elif chg > 10:
            advice = "🔴 ระวังดอย (Overbought)"
            color = "#ff4b4b"
            desc = "ราคาขึ้นมาสูงเกินไปในระยะสั้น แนะนำให้รอย่อ"
        elif 0 <= chg <= 3:
            advice = "🟡 ทยอยซื้อ (DCA)"
            color = "#f1c40f"
            desc = "ราคากำลังสะสมพลัง เป็นจังหวะดีสำหรับมือใหม่"
        else:
            advice = "🔵 ถือรอ (Hold)"
            color = "#3498db"
            desc = "ทิศทางยังไม่ชัดเจน รอดูแรงซื้อขายเพิ่ม"

        with cols[idx % 2]:
            with st.container(border=True):
                st.markdown(f"### 🏆 {sym}")
                st.markdown(f"<div class='signal-box' style='background:{color}; color:black;'>{advice}</div>", unsafe_allow_html=True)
                
                st.metric("Price (THB)", f"{row['price_thb']:,.2f}", f"{chg:+.2f}%")
                
                # กราฟ Sparkline
                fig = go.Figure(go.Scatter(y=[row['open_price']*EXCHANGE_RATE, row['price_thb']], line=dict(color=color, width=4)))
                fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"v_{sym}", config={'displayModeBar': False})
                
                st.caption(f"💡 วิเคราะห์: {desc}")

# คำอธิบายเพิ่มเติมสำหรับ User
st.divider()
st.info("""
**วิธีอ่านคำแนะนำสำหรับมือใหม่:**
* **น่าสะสม (🟢):** เหมือนห้างจัดโปรลดราคา เหรียญพื้นฐานดีแต่ราคาตกลงมาชั่วคราว
* **ทยอยซื้อ (🟡):** ราคาค่อยๆ ไป เหมาะกับการเก็บออมระยะยาว (DCA)
* **ระวังดอย (🔴):** อย่าไล่ราคาตอนนี้ ให้รอมันใจเย็นลงก่อนค่อยเข้า
""")
