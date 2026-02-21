import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import feedparser
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter Dynamic", layout="wide")

# --- 2. ฟังก์ชันวิเคราะห์ข่าว ---
def get_sentiment_pro(symbol):
    try:
        coin_name = symbol.split('-')[0].lower()
        feed_url = f"https://www.newsbtc.com/search/{coin_name}/feed/"
        feed = feedparser.parse(feed_url)
        if not feed.entries: return 0, "No live news"
        pos_words = ['bullish', 'breakout', 'gain', 'support', 'surge', 'rally', 'buy']
        neg_words = ['bearish', 'drop', 'decline', 'risk', 'sell', 'crash']
        score, latest_headline = 0, feed.entries[0].title
        for entry in feed.entries[:3]:
            text = entry.title.lower()
            for word in pos_words:
                if word in text: score += 10
            for word in neg_words:
                if word in text: score -= 15
        return score, latest_headline
    except: return 0, "News Offline"

# --- 3. ฟังก์ชันดึงค่าเงินบาทล่าสุด ---
def get_live_thb():
    try:
        data = yf.download("THB=X", period="1d", interval="1m", progress=False)
        rate_val = data['Close'].iloc[-1]
        actual_rate = rate_val.iloc[0] if hasattr(rate_val, 'iloc') else rate_val
        return float(actual_rate)
    except: return 35.5

# --- 4. สมองกล: คำนวณเงินลงทุนไม้ต่อไป (Dynamic Sizing) ---
def calculate_dynamic_investment(df_perf, base_money=1000.0):
    try:
        if df_perf.empty: return base_money
        
        # กรองเฉพาะแถวที่เป็นการขาย (SOLD)
        history = df_perf[df_perf['สถานะ'] == 'SOLD'].tail(3)
        if history.empty: return base_money
        
        # เช็คไม้ล่าสุด
        last_trade = history.iloc[-1]
        is_last_win = '-' not in str(last_trade['กำไร/ขาดทุน'])
        
        if not is_last_win:
            return base_money # ถ้าแพ้ ให้กลับมาเริ่มที่ทุนต่ำสุดทันที
        
        # นับจำนวนไม้ที่ชนะติดต่อกัน
        win_streak = 0
        for _, row in history[::-1].iterrows():
            if '-' not in str(row['กำไร/ขาดทุน']): win_streak += 1
            else: break
            
        if win_streak == 1: return base_money * 1.2 # ชนะ 1 ไม้ ลง 1,200
        if win_streak == 2: return base_money * 1.5 # ชนะ 2 ไม้ ลง 1,500
        return base_money # ชนะ 3 ไม้แล้ว หรืออื่นๆ ให้รีเซ็ตกลับมา 1,000 (ล็อคกำไร)
    except: return base_money

# --- 5. วิเคราะห์กราฟ ---
def analyze_coin_ai(symbol, df, live_rate, invest_amount):
    try:
        if len(df) < 100: return None 
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        last_row = df.tail(1)
        close_val = last_row['Close'].iloc[0]
        cur_p_thb = (float(close_val.iloc[0]) if hasattr(close_val, 'iloc') else float(close_val)) * live_rate
        
        ema_val = last_row['EMA_50'].iloc[0]
        ema50_thb = (float(ema_val.iloc[0]) if hasattr(ema_val, 'iloc') else float(ema_val)) * live_rate
        
        rsi_now = float(last_row['RSI_14'].iloc[0])
        
        score = 0
        if cur_p_thb > ema50_thb: score += 60
        else: return None

        if 40 < rsi_now < 65: score += 20
        n_score, n_headline = get_sentiment_pro(symbol)
        score += n_score

        return {
            "Symbol": symbol, "Market Price (฿)": cur_p_thb,
            "Score": score, "Trend": "🟢 Bullish", "News": n_headline,
            "Est. Qty": invest_amount / cur_p_thb
        }
    except: return None

# --- 6. เชื่อมต่อ Google Sheets ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open("Blue-chip Bet").worksheet("trade_learning")
    except: return None

# --- โหลดข้อมูลพอร์ต ---
sheet = init_gsheet()
live_rate = get_live_thb()
current_total_bal, goal_bal = 1000.0, 10000.0
hunting_symbol, entry_p_thb, current_qty = None, 0.0, 0.0
df_perf = pd.DataFrame()

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        df_perf['Balance'] = pd.to_numeric(df_perf['Balance'], errors='coerce')
        df_perf = df_perf.dropna(subset=['Balance'])
        if not df_perf.empty:
            last_row = df_perf.iloc[-1]
            current_total_bal = float(last_row['Balance'])
            if last_row['สถานะ'] == 'HUNTING':
                hunting_symbol = last_row['เหรียญ']
                entry_p_thb = float(last_row['ราคาซื้อ(฿)'])
                current_qty = float(last_row['จำนวน'])

# คำนวณเงินลงทุนไม้ถัดไปแบบ Dynamic
DYNAMIC_INVEST = calculate_dynamic_investment(df_perf, 1000.0)

# --- 7. SIDEBAR ---
with st.sidebar:
    st.title("🦔 Pepper Hunter")
    st.metric("Balance", f"{current_total_bal:,.2f} ฿")
    st.subheader("🔥 Strategy: Dynamic Sizing")
    st.info(f"ไม้ถัดไป Pepper แนะนำลง: {DYNAMIC_INVEST:,.2f} ฿")
    prog = min(current_total_bal / goal_bal, 1.0)
    st.progress(prog)
    if st.button("🔄 Refresh Now"): st.rerun()

# --- 8. MAIN ---
st.title("🛡️ Dynamic Trading Dashboard")
if hunting_symbol:
    curr_data_raw = yf.download(hunting_symbol, period="1d", interval="1m", progress=False)
    lcv = curr_data_raw['Close'].iloc[-1]
    cur_p_thb = (float(lcv.iloc[0]) if hasattr(lcv, 'iloc') else float(lcv)) * live_rate
    profit_pct = ((cur_p_thb - entry_p_thb) / entry_p_thb) * 100
    
    st.success(f"📍 กำลังล่าเหรียญ: **{hunting_symbol}**")
    c1, c2, c3 = st.columns(3)
    c1.metric("ราคาซื้อ", f"{entry_p_thb:,.2f} ฿")
    c2.metric("ราคาตอนนี้", f"{cur_p_thb:,.2f} ฿")
    c3.metric("กำไร/ขาดทุน", f"{profit_pct:.2f}%", delta=f"{profit_pct:.2f}%")
else:
    st.warning(f"📡 บอทกำลังว่างงาน... เตรียมลงไม้ถัดไปที่ {DYNAMIC_INVEST:,.2f} ฿")

# --- 9. Market Radar ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
with st.expander("🔍 สแกนตลาด (ใช้ทุน Dynamic)", expanded=True):
    data = yf.download(tickers, period="5d", interval="1h", group_by='ticker', progress=False)
    for sym in tickers:
        try:
            df_h = data[sym].dropna()
            res = analyze_coin_ai(sym, df_h, live_rate, DYNAMIC_INVEST)
            if res is None:
                lp = df_h['Close'].iloc[-1]
                ap = lp.iloc[0] if hasattr(lp, 'iloc') else lp
                res = {"Symbol": sym, "Market Price (฿)": float(ap) * live_rate, "Score": 0, "Trend": "⚪ Waiting", "News": "-", "Est. Qty": 0}
            all_results.append(res)
        except: continue
    
    if all_results:
        scan_df = pd.DataFrame(all_results)
        scan_df['Status'] = scan_df['Symbol'].apply(lambda x: '⭐ HOLDING' if x == hunting_symbol else '🔍 Radar')
        st.dataframe(scan_df.sort_values(['Status', 'Score'], ascending=[True, False]), width='stretch')

# --- 10. ซื้อ/ขาย ---
now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

if not hunting_symbol and all_results:
    best = sorted([r for r in all_results if r['Score'] >= 80], key=lambda x: x['Score'], reverse=True)
    if best:
        best_coin = best[0]
        qty = DYNAMIC_INVEST / best_coin['Market Price (฿)']
        row = [now_str, best_coin['Symbol'], "HUNTING", best_coin['Market Price (฿)'], 0, "0%", best_coin['Score'], current_total_bal, qty, "Dynamic Entry", "ON", 0, best_coin['News']]
        sheet.append_row(row)
        st.rerun()

if hunting_symbol:
    if profit_pct >= 5.0 or profit_pct <= -3.0:
        # บันทึกยอดขาย (อิงจากทุนที่ลงไปจริงในไม้นั้น ซึ่งเก็บอยู่ใน Google Sheet แถวล่าสุด)
        # เพื่อความง่าย เราใช้ DYNAMIC_INVEST ณ ตอนนี้ (ซึ่งควรจะตรงกับตอนซื้อ)
        money_back = DYNAMIC_INVEST * (1 + (profit_pct/100))
        new_total_bal = current_total_bal - DYNAMIC_INVEST + money_back
        reason = "TP 🚀" if profit_pct >= 5.0 else "SL 🛡️"
        row = [now_str, hunting_symbol, "SOLD", entry_p_thb, cur_p_thb, f"{profit_pct:.2f}%", 0, new_total_bal, 0, reason, "ON"]
        sheet.append_row(row)
        st.balloons()
        time.sleep(2)
        st.rerun()

time.sleep(300)
st.rerun()
