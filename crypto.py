import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from textblob import TextBlob
from datetime import datetime, timedelta, timezone

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="Pepper Hunter - Full Dashboard", layout="wide")

# --- 2. Shared Global State ---
@st.cache_resource
def get_global_state():
    return {
        "bot_active": False,
        "last_scan": "รอกระบวนการสแกน...",
        "current_score": 0,
        "current_ticker": "N/A",
        "status_msg": "พร้อมทำงาน"
    }

global_state = get_global_state()

# --- 3. ฟังก์ชันสนับสนุน ---

def get_top_30_tickers():
    return [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "LINK-USD", "AVAX-USD",
        "POL-USD", "TRX-USD", "SHIB-USD", "LTC-USD", "BCH-USD", "UNI-USD", "NEAR-USD", "APT-USD", "DAI-USD",
        "STX-USD", "FIL-USD", "ARB-USD", "ETC-USD", "IMX-USD", "FTM-USD", "RENDER-USD", "SUI-USD", "OP-USD", "PEPE-USD", "HBAR-USD"
    ]

def init_gsheet(sheet_name="trade_learning"):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet(sheet_name)
    except Exception as e:
        st.error(f"❌ เชื่อมต่อ Sheet ไม่ได้: {e}")
        return None

def analyze_coin_ai(symbol, df_history):
    try:
        df = df_history.copy()
        if len(df) < 30: return None
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42).fit(X, y)
        cur_p = float(df.iloc[-1]['Close'])
        pred_p = model.predict(df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[[-1]])[0]
        score = 0
        if cur_p > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < df.iloc[-1]['RSI_14'] < 65: score += 30
        if pred_p > cur_p: score += 30
        
        # ดึงข่าวสั้นๆ
        ticker = yf.Ticker(symbol)
        news = ticker.news
        sent, head = (0, "ไม่มีข่าว")
        if news:
            sent = sum(TextBlob(n['title']).sentiment.polarity for n in news[:3]) / 3
            head = news[0]['title']
        
        score += 10 if sent > 0.1 else -20 if sent < -0.1 else 0
        return {"Symbol": symbol, "Price_USD": cur_p, "Score": max(0, min(100, score)), "Headline": head}
    except: return None

def run_auto_trade(res, sheet, total_balance, live_rate):
    if not sheet: return
    try:
        data = sheet.get_all_records()
        df_trade = pd.DataFrame(data)
        is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')) if not df_trade.empty else False
        price_thb = float(res['Price_USD'] * live_rate)
        now_th = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime("%H:%M:%S %d-%m-%Y")

        if res['Score'] >= 80 and not is_holding and len(df_trade[df_trade['สถานะ'] == 'HOLD']) < 3:
            inv = total_balance * 0.20
            row = [now_th, res['Symbol'], "HOLD", round(price_thb, 4), 0, 0, res['Score'], round(total_balance, 2), round(inv/price_thb, 6), res['Headline']]
            sheet.append_row(row)
            st.toast(f"🚀 ซื้อ {res['Symbol']}")
            
        elif is_holding:
            idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
            entry_p = float(df_trade.loc[idx, 'ราคาซื้อ(฿)'])
            p_pct = ((price_thb - entry_p) / entry_p) * 100
            if p_pct >= 3.0 or p_pct <= -2.0 or res['Score'] < 50:
                new_bal = (total_balance - (float(df_trade.loc[idx, 'Balance']) * 0.20)) + (float(df_trade.loc[idx, 'Balance']) * 0.20 * (1 + (p_pct/100)))
                sheet.update_cell(int(idx)+2, 3, "SOLD")
                sheet.update_cell(int(idx)+2, 5, round(price_thb, 4))
                sheet.update_cell(int(idx)+2, 6, f"{p_pct:.2f}%")
                sheet.update_cell(int(idx)+2, 8, round(new_bal, 2))
                st.toast(f"💰 ขาย {res['Symbol']}")
    except Exception as e:
        st.warning(f"⚠️ API Error: {e}")

# --- 4. UI Setup ---
sheet = init_gsheet()
df_perf = pd.DataFrame()
sheet_bal = 0.0

if sheet:
    try:
        recs = sheet.get_all_records()
        if recs:
            df_perf = pd.DataFrame(recs)
            sheet_bal = float(df_perf.iloc[-1]['Balance'])
    except: pass

with st.sidebar:
    st.header("⚙️ ตั้งค่า Pepper")
    user_capital = st.number_input("💰 ทุนเริ่มต้น (บาท)", value=sheet_bal if sheet_bal > 0 else 1000.0)
    # 🔥 คืนชีพเป้าหมายกำไร
    user_target = st.number_input("🎯 เป้าหมายกำไร (บาท)", value=10000.0, step=1000.0)
    st.divider()
    if st.button("♻️ Sync Data"): st.rerun()

st.title("🦔 Pepper Hunter")

# 🔥 Progress Bar แสดงความคืบหน้าสู่เป้าหมาย
profit_pct = min(100, int((user_capital / user_target) * 100)) if user_target > 0 else 0
st.write(f"📈 ความคืบหน้าสู่เป้าหมาย: {user_capital:,.2f} / {user_target:,.2f} บาท")
st.progress(profit_pct / 100)

c1, c2 = st.columns(2)
if c1.button("▶️ Global Start", use_container_width=True): global_state["bot_active"] = True
if c2.button("🛑 Global Stop", use_container_width=True): global_state["bot_active"] = False

# --- 5. Visuals ---
col_v1, col_v2 = st.columns([1, 2])

with col_v1:
    st.subheader("🦔 Pepper Confidence")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=global_state["current_score"],
        title={'text': f"Scanning: {global_state['current_ticker']}"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "#00FFCC"},
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 80}
        }
    ))
    fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_v2:
    st.subheader("📈 Equity Curve")
    if not df_perf.empty:
        fig_line = px.line(df_perf, y='Balance', title="Portfolio Growth", template="plotly_dark")
        fig_line.update_traces(line_color='#00FFCC', line_width=3)
        fig_line.update_layout(height=280, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("รอข้อมูลประวัติการเทรด...")

# --- Metrics ---
m1, m2, m3 = st.columns(3)
m1.metric("Current Balance", f"฿{user_capital:,.2f}")
m2.metric("Target", f"฿{user_target:,.2f}")
m3.metric("Last Scan", global_state["last_scan"])

# --- 6. Background Loop ---
if global_state["bot_active"]:
    try:
        tickers = get_top_30_tickers()
        raw_data = yf.download(tickers, period="60d", interval="1h", progress=False, group_by='ticker')
        df_thb = yf.download("THB=X", period="1d", interval="1m", progress=False)
        live_rate = float(df_thb['Close'].iloc[-1]) if not df_thb.empty else 35.5
        
        status_box = st.empty()
        for t in tickers:
            status_box.info(f"🧠 Pepper กำลังวิเคราะห์: {t}")
            if t not in raw_data.columns.get_level_values(0): continue
            t_df = raw_data[t].copy().dropna()
            if len(t_df) < 30: continue
                
            res = analyze_coin_ai(t, t_df)
            if res:
                global_state["current_score"] = res['Score']
                global_state["current_ticker"] = res['Symbol']
                if res['Price_USD'] * live_rate <= user_capital:
                    run_auto_trade(res, sheet, user_capital, live_rate)
            time.sleep(1)
            
        global_state["last_scan"] = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        st.rerun()
    except Exception as e:
        st.error(f"⚠️ Loop Error: {e}")
        time.sleep(30); st.rerun()

st.divider()
if not df_perf.empty:
    st.subheader("📚 ประวัติการเทรดล่าสุด")
    st.dataframe(df_perf.iloc[::-1], use_container_width=True)
