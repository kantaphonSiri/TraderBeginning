import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันวิเคราะห์ข่าว (NLP แบบเบาเพื่อให้เสถียร) ---
def get_sentiment_simple(symbol):
    """วิเคราะห์อารมณ์ข่าวจากพาดหัวล่าสุดโดยไม่เพิ่ม Request API"""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news:
            return 0, "No news found"
        
        # คีย์เวิร์ดตัดสินคะแนน
        pos_words = ['bullish', 'partnership', 'buy', 'gain', 'growth', 'upgrade', 'success', 'listing', 'launch']
        neg_words = ['bearish', 'hack', 'scam', 'fud', 'ban', 'drop', 'decline', 'investigation', 'risk', 'sell']
        
        score = 0
        latest_headline = news[0]['title']
        
        # ตรวจสอบคีย์เวิร์ดใน 3 ข่าวล่าสุด
        for i in range(min(3, len(news))):
            headline = news[i]['title'].lower()
            for word in pos_words:
                if word in headline: score += 5
            for word in neg_words:
                if word in headline: score -= 7
                
        return score, latest_headline
    except:
        return 0, "News connection error"

def analyze_coin_ai(symbol, df):
    try:
        if len(df) < 50: return None
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        X = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1]
        y = df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42)
        model.fit(X.values, y.values)
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        
        # --- คำนวณคะแนนเทคนิค (80%) ---
        tech_score = 0
        if cur_p > float(last_row['EMA_20'].iloc[0]) > float(last_row['EMA_50'].iloc[0]): tech_score += 40
        if 40 < float(last_row['RSI_14'].iloc[0]) < 65: tech_score += 25
        if model.predict(last_row[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].values)[0] > cur_p: tech_score += 15
        
        # --- คำนวณคะแนนข่าว (20%) ---
        news_score, news_headline = get_sentiment_simple(symbol)
        
        total_score = tech_score + news_score
        total_score = max(0, min(100, total_score)) # คุมคะแนนไม่ให้เกิน 100
        
        return {
            "Symbol": symbol, 
            "Price_USD": cur_p, 
            "Score": total_score, 
            "News_Score": news_score,
            "Headline": news_headline,
            "Last_Update": datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        }
    except: return None

# --- 3. ดึงข้อมูลพอร์ต ---
def init_gsheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet("trade_learning")
    except Exception as e:
        st.error(f"GSheet Error: {e}")
        return None

sheet = init_gsheet()
live_rate = 35.5 
df_perf = pd.DataFrame()
current_bal = 1000.0
hunting_symbol = None

if sheet:
    recs = sheet.get_all_records()
    if recs:
        df_perf = pd.DataFrame(recs)
        current_bal = float(df_perf.iloc[-1]['Balance']) if 'Balance' in df_perf.columns else 1000.0
        h_rows = df_perf[df_perf['สถานะ'] == 'HUNTING']
        if not h_rows.empty:
            hunting_symbol = h_rows.iloc[-1]['เหรียญ']
            entry_p = float(h_rows.iloc[-1]['ราคาซื้อ(฿)'])
            current_qty = float(h_rows.iloc[-1]['จำนวน'])

# --- 4. หน้า UI ---
st.title("🦔 Pepper Hunter")
st.write(f"💰 Balance: {current_bal:,.2f} ฿ | Target: 10,000 ฿")

# --- 5. สแกนแบบ Bulk ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
status_area = st.empty()
status_area.info("📡 กำลังวิเคราะห์ กราฟ + AI + ข่าว...")

try:
    data = yf.download(tickers, period="7d", interval="1h", group_by='ticker', progress=False)
    if not data.empty:
        for sym in tickers:
            df_h = data[sym].dropna()
            if not df_h.empty and len(df_h) >= 50:
                res = analyze_coin_ai(sym, df_h)
                if res: all_results.append(res)
        status_area.success(f"🔍 สแกนเสร็จสิ้น (รวมระบบ Sentiment ข่าวแล้ว)")
except Exception as e:
    st.error(f"❌ Error: {str(e)}")

if all_results:
    st.subheader("📊 AI Sniper Radar (Technical + News)")
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    st.dataframe(scan_df[['Symbol', 'Price_USD', 'Score', 'News_Score', 'Headline']], width='stretch')

# --- 6. ตัดสินใจซื้อ-ขาย ---
if all_results:
    now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")
    scan_df_sorted = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    best_pick = all_results[0] if all_results[0]['Score'] >= 70 else None

    if not hunting_symbol:
        if best_pick:
            buy_p_thb = best_pick['Price_USD'] * live_rate
            qty = current_bal / buy_p_thb
            # บันทึกข้อมูลแบบมีข่าว (L, M)
            row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], 
                   current_bal, qty, "AI Sniper Buy", "ON", best_pick['News_Score'], best_pick['Headline']]
            if sheet:
                sheet.append_row(row)
                st.success(f"🎯 ตัดสินใจซื้อ: {best_pick['Symbol']}")
                time.sleep(2)
                st.rerun()

    else:
        current_coin = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
        if current_coin:
            cur_p_thb = current_coin['Price_USD'] * live_rate
            profit_pct = ((cur_p_thb - entry_p) / entry_p) * 100
            st.warning(f"📍 ถือ: {hunting_symbol} | กำไร: {profit_pct:.2f}% | ข่าวตอนนี้: {current_coin['News_Score']}")

            sell_trigger, headline = False, ""
            if profit_pct >= 8.0: sell_trigger, headline = True, "Take Profit 🚀"
            elif profit_pct <= -4.0: sell_trigger, headline = True, "Stop Loss 🛡️"
            elif profit_pct > 0.5 and current_coin['Score'] < 50: sell_trigger, headline = True, "Exit (Score Drop) 📉"

            if sell_trigger:
                new_bal = current_qty * cur_p_thb
                row = [now_str, hunting_symbol, "SOLD", entry_p, cur_p_thb, f"{profit_pct:.2f}%", 
                       current_coin['Score'], new_bal, 0, headline, "ON", current_coin['News_Score'], current_coin['Headline']]
                if sheet:
                    sheet.append_row(row)
                    st.balloons()
                    time.sleep(2)
                    st.rerun()

st.divider()
if not df_perf.empty and 'Balance' in df_perf.columns:
    st.line_chart(df_perf['Balance'])

if st.button("🔄 Force Refresh Now"):
    st.rerun()

st.write("⏱️ ระบบความปลอดภัย (5 Min Cooldown)...")
countdown_placeholder = st.empty()
wait_time = 300
for i in range(wait_time, 0, -10):
    countdown_placeholder.write(f"⏳ จะเริ่มสแกนใหม่ในอีก {i} วินาที...")
    time.sleep(10) 
st.rerun()
