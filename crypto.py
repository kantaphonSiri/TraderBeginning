import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. CONFIG & SETTINGS
# ---------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"
EXCHANGE_RATE = 35.5  # อัตราแลกเปลี่ยนโดยประมาณ

st.set_page_config(page_title="Budget-bet Yahoo Edition", layout="wide")

# CSS ตกแต่งให้เหมือน Dashboard มือโปร
st.markdown("""
    <style>
    [data-testid="column"] { width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
    [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.5rem !important; }
    .stMetric { background: #161a1e; padding: 10px; border-radius: 10px; border: 1px solid #2b2f36; }
    .vol-rank { color: #888; font-size: 12px; font-weight: bold; }
    @media (max-width: 640px) { h3 { font-size: 14px !important; } .stMetric div { font-size: 14px !important; } }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. HYBRID DATA ENGINE (Yahoo Style Quality Control)
# ---------------------------------------------------------
def get_market_data():
    # แผน A: Binance
    urls = ["https://api.binance.com/api/v3/ticker/24hr", "https://api3.binance.com/api/v3/ticker/24hr"]
    for url in urls:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                df['price'] = pd.to_numeric(df['lastPrice'], errors='coerce')
                df['change'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
                df['volume'] = pd.to_numeric(df['quoteVolume'], errors='coerce')
                return df[['symbol', 'price', 'change', 'volume']]
        except: continue
    
    # แผน B: Gate.io (สำรอง)
    try:
        res = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=5)
        df = pd.DataFrame(res.json())
        df['symbol'] = df['currency_pair'].str.replace('_', '')
        df['price'] = pd.to_numeric(df['last'], errors='coerce')
        df['change'] = pd.to_numeric(df['change_percentage'], errors='coerce')
        df['volume'] = pd.to_numeric(df['quote_volume'], errors='coerce')
        return df[['symbol', 'price', 'change', 'volume']]
    except: return pd.DataFrame()

# ---------------------------------------------------------
# 3. LOGIC & ADAPTIVE REFRESH
# ---------------------------------------------------------
df_market = get_market_data()
refresh_ms = 30000 

if not df_market.empty:
    btc = df_market[df_market['symbol'] == 'BTCUSDT']
    if not btc.empty:
        btc_voldetail = abs(btc['change'].values[0])
        # ปรับตามคติ: ตลาดเดือด 10s, ปกติ 30s, นิ่ง 60s
        refresh_ms = 10000 if btc_voldetail > 4 else (30000 if btc_voldetail > 1.5 else 60000)

st_autorefresh(interval=refresh_ms, key="yahoo_adaptive_ref")

# ---------------------------------------------------------
# 4. SIDEBAR - SETTINGS & PORTFOLIO
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Yahoo Filter")
    budget = st.number_input("💵 งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=500.0)
    st.caption("💡 ใส่ 0 เพื่อดู Most Active ทั้งตลาด")
    
    st.divider()
    st.subheader("📋 My Portfolio")
    try:
        df_port = pd.read_csv(SHEET_URL)
        df_port.columns = df_port.columns.str.strip().str.lower()
        if not df_port.empty and not df_market.empty:
            for _, row in df_port.iterrows():
                s = str(row['symbol']).upper()
                m = df_market[df_market['symbol'] == f"{s}USDT"]
                if not m.empty:
                    p_thb = m['price'].values[0] * EXCHANGE_RATE
                    diff = ((p_thb - row['cost']) / row['cost']) * 100
                    st.write(f"**{s}**: {p_thb:,.2f} ฿ ({diff:+.2f}%)")
    except: st.caption("รอเชื่อมต่อ Google Sheets...")

# ---------------------------------------------------------
# 5. MAIN UI - MOST ACTIVE SELECTION (Yahoo Style)
# ---------------------------------------------------------
st.title("🪙 Budget-bet Pro")
status_emoji = "🔥" if refresh_ms == 10000 else "🟢"
st.caption(f"{status_emoji} Refresh: {refresh_ms/1000}s | 🇹🇭 1 USD ≈ {EXCHANGE_RATE} THB")

if not df_market.empty:
    # --- Yahoo Screening Logic ---
    df_clean = df_market.copy()
    df_clean['price_thb'] = df_clean['price'] * EXCHANGE_RATE
    
    # 1. กรองเหรียญคุณภาพ (ต้องมีโวลุ่ม > 1 ล้าน USD และเป็นคู่ USDT)
    df_clean = df_clean[
        (df_clean['symbol'].str.endswith('USDT')) & 
        (df_clean['volume'] > 1000000) & 
        (~df_clean['symbol'].str.contains('UP|DOWN|BULL|BEAR|USDC|DAI|FDUSD'))
    ].copy()

    # 2. จัดอันดับ Most Active (ตาม Volume)
    df_clean['rank_vol'] = df_clean['volume'].rank(ascending=False)
    top_30_list = df_clean[df_clean['rank_vol'] <= 30]['symbol'].tolist()

    # 3. เลือก 6 ตัวที่จะโชว์
    if budget > 0:
        # กรองตามงบ แล้วเลือกตัวที่ Change สูงสุด (Top Gainer in Budget)
        recommend = df_clean[df_clean['price_thb'] <= budget].sort_values(by='change', ascending=False).head(6)
        mode_label = f"Most Active Under {budget:,.0f} ฿"
    else:
        # โชว์ Most Active Top Gainer ของตลาด
        recommend = df_clean.sort_values(by='change', ascending=False).head(6)
        mode_label = "Yahoo Finance: Most Active Today"

    st.subheader(f"🔍 {mode_label}")

    # --- Grid Display ---
    if recommend.empty:
        st.warning("⚠️ ไม่พบเหรียญที่เข้าเงื่อนไข ลองปรับงบดูครับ")
    else:
        cols = st.columns(2)
        for idx, (i, row) in enumerate(recommend.iterrows()):
            sym_display = row['symbol'].replace('USDT', '')
            v_rank = int(row['rank_vol'])
            is_popular = row['symbol'] in top_30_list
            badge = "🏆" if is_popular else "💎"
            
            with cols[idx % 2]:
                with st.container(border=True):
                    # Header: ชื่อเหรียญ + อันดับโวลุ่ม
                    st.markdown(f"### {badge} {sym_display} <span class='vol-rank'>#Rank {v_rank}</span>", unsafe_allow_html=True)
                    
                    # Metric: ราคา และ % เปลี่ยนแปลง
                    st.metric("Price (THB)", f"{row['price_thb']:,.2f}", f"{row['change']:+.2f}%")
                    
                    # Sparkline: กราฟเส้นแบบ Yahoo
                    fig = go.Figure(go.Scatter(
                        y=[row['price_thb']/(1+row['change']/100), row['price_thb']], 
                        line=dict(color="#00ffcc" if row['change'] > 0 else "#ff4b4b", width=4)
                    ))
                    fig.update_layout(height=45, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, 
                                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{row['symbol']}", config={'displayModeBar': False})
                    
                    # AI Insight
                    insight = "📈 Bullish" if row['change'] > 2 else ("📉 Oversold" if row['change'] < -2 else "⏳ Neutral")
                    st.caption(f"Status: {insight} | Type: {'Most Active' if is_popular else 'High Potential'}")
else:
    st.error("📡 Connecting to Market Data...")
