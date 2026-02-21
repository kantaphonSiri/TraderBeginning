import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & LUXURY STYLES ---
st.set_page_config(page_title="Pepper Hunter", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0b0e11 0%, #1c2128 100%); color: #e9eaeb; }
    .trade-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    [data-testid="stMetricValue"] { font-size: 26px !important; color: #00ff88 !important; font-weight: 700; }
    @media (max-width: 640px) {
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CORE FUNCTIONS ---
@st.cache_data(ttl=60)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1])
    except: return 35.50

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- 3. DATA LOAD & AUTO-EXIT SYSTEM ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
update_time = now_th.strftime("%H:%M:%S")

current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
next_invest = 1000.0

TP_PCT = 5.0
SL_PCT = -3.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            df_perf.columns = df_perf.columns.str.strip()
            last_row = df_perf.iloc[-1]
            
            current_total_bal = float(last_row.get('Balance', 1000))
            status = last_row.get('สถานะ')
            hunting_symbol = last_row.get('เหรียญ')
            entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
            
            last_pnl_str = str(last_row.get('กำไร%', '0'))
            if '-' not in last_pnl_str and last_pnl_str not in ['0', '0%', '']:
                next_invest = 1200.0

            if status == 'HUNTING' and hunting_symbol:
                ticker = yf.download(hunting_symbol, period="1d", interval="1m", progress=False)
                if not ticker.empty:
                    cur_p_thb = float(ticker['Close'].iloc[-1]) * live_rate
                    pnl_now = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
                    
                    if pnl_now >= TP_PCT or pnl_now <= SL_PCT:
                        new_bal = current_total_bal * (1 + (pnl_now / 100))
                        exit_row = [
                            now_th.strftime("%Y-%m-%d %H:%M"), 
                            hunting_symbol, "CLOSED", entry_p_thb, 
                            cur_p_thb, f"{pnl_now:.2f}%", 0, new_bal, 
                            0, "ALGO_AUTO_EXIT", "DONE", "N/A", 
                            f"System Exit at {pnl_now:.2f}%"
                        ]
                        sheet.append_row(exit_row)
                        st.balloons()
                        st.success(f"🤖 AUTO-CLOSED: {hunting_symbol} at {pnl_now:.2f}%")
                        time.sleep(5)
                        st.rerun()
    except Exception as e:
        st.error(f"Sync Error: {e}")

# --- 4. NAVIGATION / SIDEBAR ---
with st.sidebar:
    st.markdown("### ⚙️ Pepper Control")
    st.metric("Total Balance", f"{current_total_bal:,.2f} ฿")
    st.info(f"💰 Next Invest: {next_invest:,.0f} ฿")
    st.divider()
    if st.button("🔄 Manual Sync", width='stretch'):
        st.rerun()

# --- 5. DASHBOARD HEADER ---
st.markdown(f"## 🦔 Pepper Hunter <small style='font-size:14px; color:#555;'>PRO v2026</small>", unsafe_allow_html=True)

m1, m2, m3 = st.columns([1.2, 1, 1])
with m1:
    status_color = "#ff4b4b" if hunting_symbol else "#00ff88"
    st.markdown(f'''<div class="trade-card">
        <small style="color:#888;">BOT STATUS</small><br>
        <b style="color:{status_color}; font-size:20px;">
            {"🔴 BUSY (HUNTING)" if hunting_symbol else "🟢 IDLE (SCANNING)"}
        </b>
    </div>''', unsafe_allow_html=True)
with m2:
    st.markdown(f'''<div class="trade-card">
        <small style="color:#888;">USD/THB</small><br>
        <b style="color:#e9eaeb; font-size:20px;">฿ {live_rate:.2f}</b>
    </div>''', unsafe_allow_html=True)
with m3:
    st.markdown(f'''<div class="trade-card">
        <small style="color:#888;">LAST SYNC</small><br>
        <b style="color:#e9eaeb; font-size:20px;">{update_time}</b>
    </div>''', unsafe_allow_html=True)

# --- 6. ACTIVE TRADE DISPLAY (GRAPH SYNCED WITH ASSET VALUE) ---
if hunting_symbol:
    st.write(f"#### ⚡ Current Mission: {hunting_symbol}")
    # ดึงข้อมูลย้อนหลังเพื่อทำกราฟ
    hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
    hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
    
    # คำนวณค่าสำคัญ
    market_price_thb = float(hist['Close'].iloc[-1]) * live_rate
    pnl_pct = ((market_price_thb - entry_p_thb) / entry_p_thb) * 100
    units_held = next_invest / entry_p_thb
    current_asset_value = units_held * market_price_thb
    real_profit_baht = current_asset_value - next_invest

    # --- หัวใจสำคัญ: ปรับเส้นกราฟให้เป็นมูลค่าเงินบาทในกระเป๋า ---
    # เอาประวัติราคาปิด x อัตราแลกเปลี่ยน x จำนวนหน่วยที่ถือ
    asset_value_graph = hist['Close'] * live_rate * units_held

    col_chart, col_stat = st.columns([2, 1])
    with col_chart:
        # กราฟตอนนี้จะแสดงเลข 1,000 +/- แล้วครับ ไม่ใช่ 60,000
        st.area_chart(asset_value_graph, height=200, color="#00ff88" if pnl_pct >=0 else "#ff4b4b")
        st.caption(f"📈 Portfolio Value Tracking (Baht) - Units: {units_held:.6f}")
    
    with col_stat:
        st.metric("My Asset Value", f"{current_asset_value:,.2f} ฿", f"{real_profit_baht:,.2f} ฿")
        
        st.markdown(f"""
        <div style="background: rgba(0,255,136,0.1); padding: 12px; border-radius: 10px; border: 1px solid rgba(0,255,136,0.3); text-align: center;">
            <small style="color: #888;">INVESTMENT</small><br>
            <b style="font-size: 20px; color: #e9eaeb;">{next_invest:,.0f} ฿</b>
        </div>
        """, unsafe_allow_html=True)
        
        st.caption(f"Entry Price: {entry_p_thb:,.0f} ฿")
        st.caption(f"Market Price: {market_price_thb:,.0f} ฿")

# --- 7. MARKET RADAR (TABLE) ---
st.write("#### 🔍 Intelligence Radar")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]

radar_list = []
with st.spinner("🕵️ Scanning Markets..."):
    raw_data = yf.download(tickers, period="2d", interval="1h", group_by='ticker', progress=False)
    for t in tickers:
        try:
            df = raw_data[t].dropna()
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
            df.ta.rsi(length=14, append=True)
            last = df.tail(1)
            p_thb = float(last['Close'].iloc[-1]) * live_rate
            rsi = float(last['RSI_14'].iloc[-1])
            radar_list.append({
                "Asset": t.replace("-USD", ""),
                "Price (฿)": p_thb,
                "RSI": rsi,
                "Confidence": int(80 if rsi < 30 else (60 if rsi < 50 else 40)),
                "Updated": update_time
            })
        except: continue

df_radar = pd.DataFrame(radar_list).sort_values("Confidence", ascending=False)
st.dataframe(df_radar, width='stretch', hide_index=True,
    column_config={
        "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%"),
        "Price (฿)": st.column_config.NumberColumn("Price (฿)", format="%.0f"),
        "RSI": st.column_config.NumberColumn("RSI", format="%.1f")
    })

# --- 8. SAFETY & CONTROL ---
st.divider()
c1, c2 = st.columns(2)
with c1:
    if st.button("🚨 EMERGENCY SELL", width='stretch', type="primary"):
        st.warning("Manual override sell triggered...")
with c2:
    st.info(f"Auto-Exit: ON (TP +{TP_PCT}% / SL {SL_PCT}%)")

st.progress(0, text=f"Auto-refreshing in 5m... Status: Monitoring {hunting_symbol if hunting_symbol else 'Market'}")

time.sleep(300)
st.rerun()
