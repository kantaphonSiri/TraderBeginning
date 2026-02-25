import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. SETTINGS ---
st.set_page_config(page_title="Pepper Hunter", layout="wide")

# --- 2. AI & ML LOGIC ---
def analyze_coin_potential(symbol, budget):
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty: return None
        
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        last_rsi = df['RSI'].iloc[-1]
        last_price = df['Close'].iloc[-1].item() # ใช้ .item() กัน FutureWarning
        volatility = (df['ATR'].iloc[-1] / last_price) * 100
        
        score = 0
        if 30 <= last_rsi <= 45: score += 50
        elif last_rsi < 30: score += 80
        if volatility < 2.0: score += 20
        
        return {
            "Symbol": symbol,
            "Score": score,
            "RSI": round(last_rsi, 2),
            "Price": round(last_price, 4),
            "Risk": "Low" if volatility < 1.5 else "High",
            "Action": "Strong Buy" if score > 70 else "Wait"
        }
    except: return None

# --- 3. CORE FUNCTIONS ---
@st.cache_data(ttl=300)
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1].item()) if not data.empty else 35.50
    except: return 35.50

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, 
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- 4. DATA PROCESSING (Read & Auto-Update) ---
sheet = init_gsheet()
live_rate = get_live_thb()
now_th = datetime.now(timezone(timedelta(hours=7)))
current_total_bal = 1000.0
hunting_symbol = None
entry_p_thb = 0.0
df_all = pd.DataFrame()

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_all = pd.DataFrame(recs)
            df_all.columns = df_all.columns.str.strip()
            last_row = df_all.iloc[-1]
            
            # ดึงค่าจาก Sheet
            current_total_bal = float(last_row.get('Balance', 1000))
            status = last_row.get('สถานะ')
            
            if status == 'HUNTING':
                hunting_symbol = last_row.get('เหรียญ')
                entry_p_thb = float(last_row.get('ราคาซื้อ(฿)', 0))
                
                # --- AUTO EXIT LOGIC (เช็คเพื่อบันทึกปิดออเดอร์) ---
                ticker = yf.download(hunting_symbol, period="1d", interval="1m", progress=False)
                if not ticker.empty:
                    cur_p_usd = float(ticker['Close'].iloc[-1].item())
                    cur_p_thb = cur_p_usd * live_rate
                    pnl = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
                    
                    if pnl >= 5.0 or pnl <= -3.0:
                        new_bal = current_total_bal * (1 + (pnl/100))
                        # บันทึกบรรทัดใหม่ลง Sheet เมื่อปิดออเดอร์
                        sheet.append_row([
                            now_th.strftime("%d-%m-%Y %H:%M"), # Format วันที่
                            hunting_symbol, "CLOSED", entry_p_thb, 
                            current_total_bal, cur_p_thb, f"{pnl:.2f}%", 0, new_bal
                        ])
                        st.rerun()
    except Exception as e:
        st.error(f"Sheet Error: {e}")

# --- 5. DASHBOARD UI ---
st.title("🦔 Pepper Hunter")

c1, c2, c3 = st.columns(3)
with c1: st.metric("Portfolio Balance", f"{current_total_bal:,.2f} ฿")
with c2: st.metric("USD/THB", f"฿{live_rate:.2f}")
with c3: st.metric("Status", hunting_symbol if hunting_symbol else "Scanning...")

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🔍 AI Market Scanning")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "AVAX-USD", "LINK-USD", "DOT-USD"]
    
    with st.spinner('AI is analyzing coins...'):
        recommendations = []
        for t in tickers:
            analysis = analyze_coin_potential(t, current_total_bal)
            if analysis: recommendations.append(analysis)
    
    if recommendations:
        rec_df = pd.DataFrame(recommendations).sort_values(by="Score", ascending=False)
        st.dataframe(rec_df, use_container_width=True)
        
        best_coin = rec_df.iloc[0]
        if best_coin['Score'] > 60:
            st.success(f"🎯 AI Recommendation: **{best_coin['Symbol']}** (Score: {best_coin['Score']})")
            
            # เพิ่มปุ่มสำหรับบันทึกการซื้อลง Sheet
            if not hunting_symbol:
                if st.button(f"🚀 Start Hunting {best_coin['Symbol']}"):
                    thb_price = best_coin['Price'] * live_rate
                    sheet.append_row([
                        now_th.strftime("%d-%m-%Y %H:%M"),
                        best_coin['Symbol'], "HUNTING", thb_price, 
                        current_total_bal, 0, "0%", 0, current_total_bal
                    ])
                    st.rerun()

with col_right:
    st.subheader("📊 Trade History (Sheets)")
    if not df_all.empty:
        st.dataframe(df_all[['วันที่', 'เหรียญ', 'สถานะ', 'Balance']].tail(5))

st.divider()
st.info(f"Last AI Sync: {now_th.strftime('%H:%M:%S')}")
time.sleep(300)
st.rerun()
