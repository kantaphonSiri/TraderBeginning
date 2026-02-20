import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="🦔 Pepper Hunter", layout="wide")

# --- 2. ฟังก์ชันวิเคราะห์ข่าว (NLP แบบเบาเพื่อให้เสถียร) ---
def get_sentiment_simple(symbol):
    try:
        time.sleep(random.uniform(0.5, 1.5))
        ticker = yf.Ticker(symbol)
        news = ticker.get_news() 
        
        if not news or len(news) == 0:
            return 0, "No recent news"
        
        pos_words = ['bullish', 'partnership', 'buy', 'gain', 'growth', 'upgrade', 'success', 'listing', 'launch', 'ai', 'pump', 'moon', 'breakout', 'ath', 'approved', 'integration', 'investment']
        neg_words = ['bearish', 'hack', 'scam', 'fud', 'ban', 'drop', 'decline', 'investigation', 'risk', 'sell', 'dump', 'crash', 'liquidated', 'whale sell', 'reject', 'exploit', 'warning']
        
        score = 0
        latest_headline = "No headline found"
        found_headlines = 0
        for item in news:
            headline = item.get('title')
            if headline:
                if found_headlines == 0:
                    latest_headline = headline
                text = headline.lower()
                for word in pos_words:
                    if word in text: score += 5
                for word in neg_words:
                    if word in text: score -= 7
                found_headlines += 1
                if found_headlines >= 3: break
        return score, latest_headline
    except Exception as e:
        return 0, f"Sync Error: {str(e)[:15]}"

def analyze_coin_ai(symbol, df):
    try:
        if len(df) < 200: return None 
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        
        # อินดิเคเตอร์ Sniper
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True) 
        df = df.dropna()
        
        last_row = df.iloc[[-1]]
        cur_p = float(last_row['Close'].iloc[0])
        rsi_now = float(last_row['RSI_14'].iloc[0])
        ema20 = float(last_row['EMA_20'].iloc[0])
        ema50 = float(last_row['EMA_50'].iloc[0])
        ema200 = float(last_row['EMA_200'].iloc[0])
        
        score = 0
        # กรองขาลง (ถ้าต่ำกว่าเส้น 200 วัน ไม่เอาเลย)
        if cur_p < ema200: return None
        score += 30
        
        if cur_p > ema20 > ema50: score += 30
        if 45 < rsi_now < 65: score += 20
            
        news_score, news_headline = get_sentiment_simple(symbol)
        if news_score < 0: return None # ข่าวลบไม่ซื้อ
        
        score += news_score
        return {
            "Symbol": symbol, "Price_USD": cur_p, "Score": score, 
            "News_Score": news_score, "Headline": news_headline,
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

# --- 5. สแกนแบบ Sniper ---
tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "NEAR-USD", "RENDER-USD", "FET-USD", "LINK-USD", "AKT-USD"]
all_results = []
status_area = st.empty()
status_area.info("📡 Radar กำลังวิเคราะห์ข้อมูลตลาดและข่าวล่าสุด...")

try:
    # ดึงข้อมูลรวดเดียวแบบ Bulk
    data = yf.download(tickers, period="7d", interval="1h", group_by='ticker', progress=False)
    if not data.empty:
        for sym in tickers:
            df_h = data[sym].dropna()
            # ส่งไปวิเคราะห์ (ถ้าไม่ผ่านเกณฑ์ EMA 200 จะได้คะแนนน้อย แต่เราจะให้แสดงผลออกมา)
            res = analyze_coin_ai(sym, df_h)
            if res:
                all_results.append(res)
            else:
                # กรณีเหรียญไม่ผ่านเกณฑ์เบื้องต้น (เช่น อยู่ใต้เส้น 200) ให้แสดงสถานะเบื้องต้น
                all_results.append({
                    "Symbol": sym, "Price_USD": 0, "Score": 0, 
                    "News_Score": 0, "Headline": "Under EMA 200 (Risk)",
                    "Last_Update": datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
                })
        status_area.success(f"🔍 สแกนเสร็จสิ้น! ข้อมูลอัปเดตเมื่อ: {datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S')}")
except Exception as e:
    st.error(f"❌ การสแกนขัดข้อง: {str(e)}")

# --- 🎯 ส่วนแสดงตาราง Radar ให้ User ดู ---
if all_results:
    st.subheader("📊 Radar Table")
    # สร้าง DataFrame และเรียงคะแนนจากมากไปน้อย
    scan_df = pd.DataFrame(all_results).sort_values('Score', ascending=False)
    
    # ตกแต่งตารางให้ดูง่าย
    st.table(scan_df[['Symbol', 'Score', 'News_Score', 'Headline', 'Last_Update']])
    
    # แจ้งเตือนเงื่อนไขการซื้อ
    st.caption("💡 เงื่อนไขการซื้อ: Score ต้อง >= 80 (ขาขึ้นชัดเจน + ข่าวดี) และต้องไม่มีเหรียญอื่นถืออยู่")
    
# --- 6. ตัดสินใจซื้อ-ขาย ---
now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")

if not hunting_symbol:
    # ถ้ามีเหรียญคะแนน 80+ ให้ซื้อ
    best_pick = next((r for r in sorted(all_results, key=lambda x: x['Score'], reverse=True) if r['Score'] >= 80), None)
    if best_pick:
        buy_p_thb = best_pick['Price_USD'] * live_rate
        qty = current_bal / buy_p_thb
        row = [now_str, best_pick['Symbol'], "HUNTING", buy_p_thb, 0, "0%", best_pick['Score'], 
               current_bal, qty, "Pepper Buy", "ON", best_pick['News_Score'], best_pick['Headline']]
        if sheet:
            sheet.append_row(row)
            st.success(f"🎯 Pepper สอยเหรียญ: {best_pick['Symbol']}")
            time.sleep(2)
            st.rerun()
else:
    # กรณีถือเหรียญอยู่ เช็คราคาขาย
    # ดึงข้อมูลราคาล่าสุดของเหรียญที่ถือ
    current_coin_data = yf.download(hunting_symbol, period="1d", interval="1m", progress=False).iloc[-1]
    cur_p_usd = float(current_coin_data['Close'])
    cur_p_thb = cur_p_usd * live_rate
    profit_pct = ((cur_p_thb - entry_p) / entry_p) * 100
    
    # ดึง Score ล่าสุดมาเช็ค Exit
    current_coin_res = next((r for r in all_results if r['Symbol'] == hunting_symbol), {'Score': 100})
    
    st.warning(f"📍 ถืออยู่: {hunting_symbol} | กำไร: {profit_pct:.2f}%")

    sell_trigger, sell_reason = False, ""
    if profit_pct >= 8.0: sell_trigger, sell_reason = True, "Take Profit 🚀"
    elif profit_pct <= -4.0: sell_trigger, sell_reason = True, "Stop Loss 🛡️"
    elif profit_pct > 0.5 and current_coin_res['Score'] < 50: sell_trigger, sell_reason = True, "Exit (Low Score) 📉"

    if sell_trigger:
        recs_check = sheet.get_all_records()
        if recs_check and recs_check[-1]['สถานะ'] == 'HUNTING':
            new_bal = current_qty * cur_p_thb
            row = [now_str, hunting_symbol, "SOLD", entry_p, cur_p_thb, f"{profit_pct:.2f}%", 
                   current_coin_res.get('Score', 0), new_bal, 0, sell_reason, "ON"]
            sheet.append_row(row)
            st.success(f"✅ ขายแล้ว: {sell_reason}")
            st.balloons()
            time.sleep(5)
            st.rerun()

# --- 7. ส่วนแสดงกราฟ ---
st.divider()
if not df_perf.empty:
    st.subheader("📈 พอร์ตการลงทุน (Balance Growth)")
    try:
        # พยายามหา Column วันที่และ Balance แบบยืดหยุ่น
        cols = df_perf.columns.tolist()
        time_col = next((c for c in ['วันที่/เวลา', 'วันที่', cols[0]] if c in cols), cols[0])
        balance_col = 'Balance' if 'Balance' in cols else cols[7]

        chart_data = df_perf[[time_col, balance_col]].dropna().copy()
        chart_data[time_col] = pd.to_datetime(chart_data[time_col], dayfirst=True, errors='coerce')
        chart_data = chart_data.dropna(subset=[time_col]).set_index(time_col)
        
        st.line_chart(chart_data[balance_col])
        
        # Metrics
        initial_fund = 1000.0
        total_profit_pct = ((current_bal - initial_fund) / initial_fund) * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("งบปัจจุบัน", f"{current_bal:,.2f} ฿")
        c2.metric("กำไรสะสม", f"{total_profit_pct:.2f} %", delta=f"{current_bal - initial_fund:,.2f} ฿")
        c3.metric("สถานะบอท", "ACTIVE ✅")
    except:
        st.info("📊 รอประวัติการเทรดที่สมบูรณ์เพื่อวาดกราฟ...")

# --- 8. ระบบวนลูป ---
if st.button("🔄 Force Refresh Now"):
    st.rerun()

st.write("⏱️ Pepper Cooldown (5 Min)...")
countdown_placeholder = st.empty()
for i in range(300, 0, -10):
    countdown_placeholder.write(f"⏳ จะเริ่มสแกนใหม่ในอีก {i} วินาที...")
    time.sleep(10) 
st.rerun()


