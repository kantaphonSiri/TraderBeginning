import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIG & CONNECTION
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"

st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# 2. DATA FUNCTIONS (With Safety Check)
def get_market_data():
    # แผน A: ดึงจาก Binance (ลอง 2 Endpoints)
    binance_urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api3.binance.com/api/v3/ticker/24hr"
    ]
    
    for url in binance_urls:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['lastPrice'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                return df
        except:
            continue

    # แผน B: ถ้า Binance พังหมด ให้ใช้ Gate.io (เสถียรมากและไม่ค่อยโดนแบน IP)
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=5)
        if res.status_code == 200:
            data = res.json()
            # แปลง Format ให้เหมือนกับ Binance เพื่อให้โค้ดส่วนอื่นทำงานต่อได้
            gate_df = pd.DataFrame(data)
            gate_df['symbol'] = gate_df['currency_pair'].str.replace('_', '')
            gate_df['lastPrice'] = pd.to_numeric(gate_df['last'], errors='coerce')
            # คำนวณ % เปลี่ยนแปลงคร่าวๆ (Gate.io ใช้ change_percentage)
            gate_df['priceChangePercent'] = pd.to_numeric(gate_df['change_percentage'], errors='coerce')
            return gate_df
    except:
        pass

    return pd.DataFrame()

def load_portfolio():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

# 3. INITIALIZE DATA
df_market = get_market_data()
df_port = load_portfolio()
rate = 35.5

# 4. ADAPTIVE REFRESH LOGIC
refresh_ms = 30000 # ค่าเริ่มต้น 30 วิ
status_msg = "⚙️ กำลังเตรียมระบบ..."

if not df_market.empty and 'symbol' in df_market.columns:
    btc_row = df_market[df_market['symbol'] == 'BTCUSDT']
    if not btc_row.empty:
        btc_change = abs(btc_row['priceChangePercent'].values[0])
        if btc_change > 4.0:
            refresh_ms = 10000
            status_msg = "🔥 ตลาดผันผวนสูง (Refresh: 10s)"
        elif btc_change > 1.5:
            refresh_ms = 30000
            status_msg = "⚡ ตลาดปกติ (Refresh: 30s)"
        else:
            refresh_ms = 60000
            status_msg = "💤 ตลาดนิ่ง (Refresh: 60s)"
else:
    st.warning("⚠️ ไม่สามารถดึงข้อมูลจาก Binance ได้ในขณะนี้ ระบบจะลองใหม่ใน 10 วินาที")
    refresh_ms = 10000

st_autorefresh(interval=refresh_ms, key="adaptive_ref")

# 5. UI - SIDEBAR
with st.sidebar:
    st.title("💼 Portfolio")
    st.info(status_msg)
    if not df_port.empty and not df_market.empty:
        for _, row in df_port.iterrows():
            sym = str(row['symbol']).upper()
            m_row = df_market[df_market['symbol'] == f"{sym}USDT"]
            if not m_row.empty:
                curr_p = m_row['lastPrice'].values[0] * rate
                diff = ((curr_p - row['cost']) / row['cost']) * 100
                st.write(f"**{sym}**: {curr_p:,.2f} ฿ ({diff:+.2f}%)")

# 6. MAIN UI (แสดงแค่ 6 ตัว)
st.title("🪙 Budget-bet Pro")
st.caption(f"Binance Engine | {status_msg}")

if not df_market.empty:
    # เลือกเหรียญที่จะแสดง (จาก Portfolio หรือ Top 6)
    if not df_port.empty:
        display_symbols = df_port['symbol'].str.upper().tolist()[:6]
    else:
        display_symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']

    cols = st.columns(2)
    for idx, sym in enumerate(display_symbols):
        pair = f"{sym}USDT"
        m_row = df_market[df_market['symbol'] == pair]
        
        if not m_row.empty:
            p = m_row['lastPrice'].values[0] * rate
            chg = m_row['priceChangePercent'].values[0]
            
            with cols[idx % 2]:
                with st.container(border=True):
                    st.subheader(f"{sym}")
                    st.metric("ราคาปัจจุบัน", f"{p:,.2f} ฿", f"{chg:+.2f}%")
                    
                    # Mini Chart
                    fig = go.Figure(go.Scatter(y=[p * (1 - chg/100), p], 
                                             line=dict(color='#00ffcc' if chg >= 0 else '#ff4b4b', width=3)))
                    fig.update_layout(height=60, margin=dict(l=0,r=0,t=0,b=0), 
                                     xaxis_visible=False, yaxis_visible=False, 
                                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{sym}", config={'displayModeBar': False})
else:
    st.error("📡 รอการเชื่อมต่อกับ Binance...")


