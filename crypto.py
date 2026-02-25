import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS & PROFESSIONAL DARK UI ---
st.set_page_config(page_title="Pepper Hunter AI", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background: #0e1117; color: #e9eaeb; }
    .trade-card {
        background: #1c2128;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .status-hunting { color: #ff4b4b; font-weight: bold; }
    .status-scanning { color: #00ff88; font-weight: bold; }
    .ai-box {
        background: #1e293b;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #38bdf8;
    }
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00ff88 !important; }
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

def calculate_kelly_size(win_rate_pct, avg_win_pct, avg_loss_pct):
    p = win_rate_pct / 100
    q = 1 - p
    if avg_loss_pct == 0: return 0.1
    b = abs(avg_win_pct / avg_loss_pct)
    if b == 0: return 0.01
    kelly_f = (b * p - q) / b
    return max(0.01, min(kelly_f / 2, 0.25)) # Conservative Half-Kelly

# --- 3. DATA PROCESSING ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))

# Init variables
current_total_bal = 1000.0
hunting_symbol, entry_p_thb = None, 0.0
next_invest = 1000.0
df_all = pd.DataFrame()
win_rate = 0.0
avg_win, avg_loss = 0.0, 0.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            df_all.columns = df_all.columns.str.strip()
            
            last_row = df_all.iloc[-1]
            current_total_bal = float(last_row.get('Balance', 1000))
            status = last_row.get('สถานะ')
            
            if status == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
                entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
            
            # AI & Stats Calculation
            closed_trades = df_all[df_all['สถานะ'] == 'CLOSED'].copy()
            if not closed_trades.empty:
                # Clean Profit/Loss column
                closed_trades['pnl_num'] = closed_trades['กำไร%'].replace('%','', regex=True).astype(float)
                wins = closed_trades[closed_trades['pnl_num'] > 0]
                losses = closed_trades[closed_trades['pnl_num'] < 0]
                
                win_rate = (len(wins) / len(closed_trades)) * 100
                avg_win = wins['pnl_num'].mean() if not wins.empty else 0
                avg_loss = losses['pnl_num'].mean() if not losses.empty else 0
                
            # Auto-Exit Logic
            if status == 'HUNTING' and hunting_symbol:
                ticker = yf.download(hunting_symbol, period="1d", interval="1m", progress=False)
                if not ticker.empty:
                    cur_p = float(ticker['Close'].values[-1]) * live_rate
                    pnl = ((cur_p - entry_p_thb) / entry_p_thb) * 100
                    if pnl >= 5.0 or pnl <= -3.0:
                        new_bal = current_total_bal * (1 + (pnl / 100))
                        sheet.append_row([now_th.strftime("%Y-%m-%d %H:%M"), hunting_symbol, "CLOSED", entry_p_thb, next_invest, cur_p, f"{pnl:.2f}%", 0, new_bal, 0, "AUTO_EXIT", "DONE", "N/A", "System Close"])
                        st.rerun()
    except Exception as e:
        st.error(f"Data Error: {e}")

# --- 4. DASHBOARD UI ---
st.title("🦔 Pepper Hunter AI")

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Total Balance", f"{current_total_bal:,.2f} ฿")
with c2: st.metric("Win Rate", f"{win_rate:.1f}%")
with c3: st.metric("Live USD/THB", f"฿{live_rate:.2f}")
with c4:
    status_html = f'<span class="status-hunting">HUNTING {hunting_symbol}</span>' if hunting_symbol else '<span class="status-scanning">SCANNING</span>'
    st.markdown(f'<div class="trade-card"><small>SYSTEM STATUS</small><br>{status_html}</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([2, 1])

with col_left:
    if hunting_symbol:
        st.subheader(f"🚀 Active Mission: {hunting_symbol}")
        hist = yf.download(hunting_symbol, period="1d", interval="15m", progress=False)
        if not hist.empty:
            hist.columns = [col[0] if isinstance(col, tuple) else col for col in hist.columns]
            cur_p_thb = float(hist['Close'].values[-1]) * live_rate
            units = next_invest / (entry_p_thb if entry_p_thb > 0 else 1)
            asset_value_series = hist['Close'] * live_rate * units
            st.area_chart(asset_value_series, height=250, color="#00ff88" if cur_p_thb >= entry_p_thb else "#ff4b4b")
    else:
        st.subheader("📈 Portfolio Equity Curve")
        if not df_all.empty:
            try:
                df_chart = df_all[['วันที่', 'Balance']].copy()
                df_chart['Balance'] = pd.to_numeric(df_chart['Balance'], errors='coerce')
                df_chart['วันที่'] = pd.to_datetime(df_chart['วันที่'], errors='coerce', dayfirst=True)
                df_chart = df_chart.dropna().sort_values('วันที่').set_index('วันที่')
                if len(df_chart) >= 2:
                    st.line_chart(df_chart['Balance'], height=250, color="#38bdf8")
                else: st.info("Waiting for more trade history to plot...")
            except: st.error("Chart Rendering Error")

    st.write("#### 🔍 Market Intelligence Radar")
    # Quick Market Scan
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD"]
    radar_df = []
    for t in tickers:
        p = yf.download(t, period="1d", interval="1m", progress=False)['Close'].iloc[-1] * live_rate
        radar_df.append({"Symbol": t, "Price (฿)": f"{p:,.2f}"})
    st.table(pd.DataFrame(radar_df))

with col_right:
    st.subheader("🤖 AI Strategist")
    
    # Target Forecasting
    target_date = datetime(2026, 3, 31).date() 
    days_left = (target_date - now_th.date()).days
    target_amount = 10000.0
    
    daily_rate_needed = ((target_amount / current_total_bal) ** (1/max(days_left, 1))) - 1
    
    st.markdown(f"""
    <div class="ai-box">
        <small style="color: #38bdf8;">TARGET ANALYTICS</small><br>
        <b>เป้าหมาย:</b> {target_amount:,.0f} ฿<br>
        <b>เหลือเวลา:</b> {days_left} วัน<br>
        <b>Growth Needed:</b> <span style="color:#00ff88;">{daily_rate_needed*100:.2f}% / วัน</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # Kelly Management
    if win_rate > 0:
        kelly_perc = calculate_kelly_size(win_rate, avg_win, avg_loss)
        ai_invest = current_total_bal * kelly_perc
        
        st.write("#### 🧠 Risk Management")
        st.write(f" Win Rate จริง: **{win_rate:.1f}%**")
        st.info(f"AI แนะนำลงทุนไม้ถัดไป: **{ai_invest:,.2f} ฿**")
        st.caption(f"Calculated by Kelly Criterion (Half-Kelly)")
        
        # Pattern Recognition (Simple)
        if not closed_trades.empty:
            best_asset = closed_trades.groupby('เหรียญ').size().idxmax()
            st.success(f"💡 AI Hint: คุณเทรด {best_asset} บ่อยที่สุด โฟกัสความถนัดเดิมเพื่อกำไรที่เสถียร")
    else:
        st.warning("กำลังสะสมข้อมูลเพื่อเริ่มวิเคราะห์แผน...")

# --- FOOTER ---
st.divider()
if st.button("🔄 Force Manual Sync"):
    st.rerun()

st.progress(0, text=f"Update Cycle Active | Last Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
