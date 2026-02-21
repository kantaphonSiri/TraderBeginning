import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & DYNAMIC THEMES ---
st.set_page_config(page_title="Pepper Hunter", layout="wide", initial_sidebar_state="expanded")

if 'pepper_theme' not in st.session_state:
    st.session_state.pepper_theme = 'Cyber Neon'

def apply_theme(theme_name):
    if theme_name == 'Cyber Neon':
        bg = "linear-gradient(135deg, #0b0e11 0%, #1c2128 100%)"
        card_bg = "rgba(255, 255, 255, 0.05)"
        accent = "#00ff88"
        text_color = "#e9eaeb"
        grid_color = "rgba(255,255,255,0.1)"
    elif theme_name == 'Bloomberg Pro':
        bg = "#001d3d"
        card_bg = "#003566"
        accent = "#ffc300"
        text_color = "#ffffff"
        grid_color = "#001d3d"
    else:  # Zen Minimal
        bg = "#f8f9fa"
        card_bg = "#ffffff"
        accent = "#212529"
        text_color = "#212529"
        grid_color = "#e9ecef"
        
    st.markdown(f"""
        <style>
        .stApp {{ background: {bg}; color: {text_color}; }}
        .trade-card {{
            background: {card_bg};
            border: 1px solid {grid_color};
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }}
        [data-testid="stMetricValue"] {{ 
            color: {accent} !important; 
            font-size: 26px !important;
            font-weight: 700;
            text-shadow: 0 0 10px {accent if theme_name == 'Cyber Neon' else 'transparent'};
        }}
        h1, h2, h3, h4, p, small, span {{ color: {text_color} !important; }}
        .stButton>button {{ width: 100%; border-radius: 8px; }}
        </style>
        """, unsafe_allow_html=True)

apply_theme(st.session_state.pepper_theme)

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

# Default Values
current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
next_invest = 1000.0
TP_PCT, SL_PCT = 5.0, -3.0

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
            next_invest = float(last_row.get('เงินลงทุน(฿)', 1000))
            
            last_pnl_str = str(last_row.get('กำไร%', '0'))
            if status == 'CLOSED' and '-' not in last_pnl_str and last_pnl_str not in ['0', '0%', '']:
                next_invest = 1200.0

            if status == 'HUNTING' and hunting_symbol:
                ticker = yf.download(hunting_symbol, period="1d", interval="1m", progress=False)
                if not ticker.empty:
                    cur_p_thb = float(ticker['Close'].iloc[-1]) * live_rate
                    pnl_now = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
                    
                    if pnl_now >= TP_PCT or pnl_now <= SL_PCT:
                        new_bal = current_total_bal * (1 + (pnl_now / 100))
                        exit_row = [
                            now_th.strftime("%Y-%m-%d %H:%M"), hunting_symbol, "CLOSED",
                            entry_p_thb, next_invest, cur_p_thb, f"{pnl_now:.2f}%",
                            0, new_bal, 0, "ALGO_AUTO_EXIT", "DONE", "N/A", f"System Exit at {pnl_now:.2f}%"
                        ]
                        sheet.append_row(exit_row)
                        st.balloons()
                        st.rerun()
    except Exception as e:
        st.error(f"Sync Error: {e}")

# --- 4. SIDEBAR CONTROL ---
with st.sidebar:
    st.markdown(f"### 🎨 Pepper Hunter UI")
    selected_theme = st.selectbox("Switch Theme", ['Cyber Neon', 'Bloomberg Pro', 'Zen Minimal'], 
                                 index=['Cyber Neon', 'Bloomberg Pro', 'Zen Minimal'].index(st.session_state.pepper_theme))
    if selected_theme != st.session_state.pepper_theme:
        st.session_state.pepper_theme = selected_theme
        st.rerun()

    st.divider()
    st.metric("Total Balance", f"{current_total_bal:,.2f} ฿")
    st.info(f"💰 Next Invest: {next_invest:,.0f} ฿")
    if st.button("🔄 Manual Sync"):
        st.rerun()

# --- 5. DASHBOARD HEADER ---
st.markdown(f"## 🦔 Pepper Hunter <small style='font-size:14px; opacity:0.6;'>PRO v2026</small>", unsafe_allow_html=True)

m1, m2, m3 = st.columns(3)
with m1:
    status_color = "#ff4b4b" if hunting_symbol else "#00ff88"
    st.markdown(f'<div class="trade-card"><small>STATUS</small><br><b style="color:{status_color}; font-size:20px;">{"🔴 HUNTING" if hunting_symbol else "🟢 SCANNING"}</b></div>', unsafe_allow_html=True)
with m2:
    st.markdown(f'<div class="trade-card"><small>USD/THB</small><br><b style="font-size:20px;">฿ {live_rate:.2f}</b></div>', unsafe_allow_html=True)
with m3:
    st.markdown(f'<div class="trade-card"><small>LAST SYNC</small><br><b style="font-size:20px;">{update_time}</b></div>', unsafe_allow_html=True)

# --- 6. ACTIVE TRADE DISPLAY ---
if hunting_symbol:
    st.write(f"#### ⚡ Active Mission: {hunting_symbol}")
    hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
    hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
    
    market_p = float(hist['Close'].iloc[-1]) * live_rate
    pnl_pct = ((market_p - entry_p_thb) / entry_p_thb) * 100
    units = next_invest / entry_p_thb
    asset_val = units * market_p
    
    col_chart, col_stat = st.columns([2, 1])
    with col_chart:
        chart_color = "#00ff88" if pnl_pct >= 0 else "#ff4b4b"
        st.area_chart(hist['Close'] * live_rate * units, height=200, color=chart_color)
    
    with col_stat:
        st.metric("My Asset Value", f"{asset_val:,.2f} ฿", f"{(asset_val-next_invest):,.2f} ฿")
        st.caption(f"Entry: {entry_p_thb:,.0f} | Market: {market_p:,.0f}")

# --- 7. MARKET RADAR ---
st.write("#### 🔍 Intelligence Radar")
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "LINK-USD"]
radar_list = []
with st.spinner("🕵️ Scanning..."):
    raw_data = yf.download(tickers, period="2d", interval="1h", group_by='ticker', progress=False)
    for t in tickers:
        try:
            df = raw_data[t].dropna()
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
            df.ta.rsi(length=14, append=True)
            p_thb = float(df['Close'].iloc[-1]) * live_rate
            rsi = float(df['RSI_14'].iloc[-1])
            radar_list.append({"Asset": t.split("-")[0], "Price (฿)": p_thb, "RSI": rsi, "Confidence": int(80 if rsi < 35 else 40)})
        except: continue

st.dataframe(pd.DataFrame(radar_list), use_container_width=True, hide_index=True)

# --- 8. FOOTER ---
st.divider()
st.progress(0, text=f"Monitoring {hunting_symbol if hunting_symbol else 'Markets'}...")
time.sleep(300)
st.rerun()
