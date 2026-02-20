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
    try:
        # สุ่มรอเล็กน้อยลดการโดน Detect
        time.sleep(random.uniform(0.5, 1.5))
        
        ticker = yf.Ticker(symbol)
        news = ticker.get_news() 
        
        if not news or len(news) == 0:
            return 0, "No recent news"
        
        pos_words = ['bullish', 'partnership', 'buy', 'gain', 'growth', 'upgrade', 'success', 'listing', 'launch', 'ai']
        neg_words = ['bearish', 'hack', 'scam', 'fud', 'ban', 'drop', 'decline', 'investigation', 'risk', 'sell']
        
        score = 0
        latest_headline = "No headline found"
        
        # วนลูปเช็คข้อมูลข่าวอย่างปลอดภัย
        found_headlines = 0
        for item in news:
            # ใช้ .get('title') เพื่อไม่ให้ Error ถ้าไม่มี Key นี้
            headline = item.get('title')
            
            if headline:
                if found_headlines == 0:
                    latest_headline = headline # เก็บหัวข้อแรกสุดไว้โชว์
                
                text = headline.lower()
                for word in pos_words:
                    if word in text: score += 5
                for word in neg_words:
                    if word in text: score -= 7
                
                found_headlines += 1
                if found_headlines >= 3: break # เอาแค่ 3 ข่าวพอ
                
        return score, latest_headline
    except Exception as e:
        # ถ้าพังจริงๆ ให้บอก Error สั้นๆ
        return 0, f"Sync Error: {str(e)[:15]}"

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

    # --- กรณีขาย (ปรับปรุงใหม่เพื่อป้องกันการบันทึกซ้ำ) ---
    else:
        # เช็คก่อนว่าในรอบนี้ บอทยังถือเหรียญเดิมอยู่จริงไหม (กัน Error กรณีเพิ่งขายไปในพริบตา)
        current_coin = next((r for r in all_results if r['Symbol'] == hunting_symbol), None)
        
        if current_coin:
            cur_p_thb = current_coin['Price_USD'] * live_rate
            profit_pct = ((cur_p_thb - entry_p) / entry_p) * 100
            st.warning(f"📍 ถืออยู่: {hunting_symbol} | กำไร: {profit_pct:.2f}%")

            sell_trigger, headline = False, ""
            if profit_pct >= 8.0: sell_trigger, headline = True, "Take Profit 🚀"
            elif profit_pct <= -4.0: sell_trigger, headline = True, "Stop Loss 🛡️"
            elif profit_pct > 0.5 and current_coin['Score'] < 50: sell_trigger, headline = True, "Exit (Low Score) 📉"

            # *** จุดสำคัญ: ตรวจสอบสถานะล่าสุดจาก Sheet อีกครั้งก่อนบันทึก ***
            recs_check = sheet.get_all_records()
            last_status = recs_check[-1]['สถานะ'] if recs_check else "SOLD"

            if sell_trigger and last_status == 'HUNTING': # ต้องถืออยู่เท่านั้นถึงจะขายได้
                new_bal = current_qty * cur_p_thb
                row = [now_str, hunting_symbol, "SOLD", entry_p, cur_p_thb, f"{profit_pct:.2f}%", current_coin['Score'], new_bal, 0, headline, "ON"]
                if sheet:
                    sheet.append_row(row)
                    st.success(f"✅ ขายสำเร็จ: {headline}")
                    st.balloons()
                    time.sleep(5) # ให้เวลาระบบ Google Sheet อัปเดตหน่อย
                    st.rerun()

st.divider()
# --- ส่วนแสดงกราฟ (ปรับปรุงใหม่ให้ดูง่าย) ---
st.divider()
if not df_perf.empty and 'Balance' in df_perf.columns:
    st.subheader("📈 พอร์ตการลงทุน (Balance Growth)")
    
    # เตรียมข้อมูลสำหรับกราฟ
    chart_data = df_perf[['วันที่', 'Balance']].copy()
    
    # แปลง Timestamp ให้เป็นรูปแบบวันที่ที่อ่านง่าย
    chart_data['วันที่'] = pd.to_datetime(chart_data['วันที่'], dayfirst=True)
    chart_data = chart_data.set_index('วันที่')
    
    # แสดงกราฟเส้นพร้อมจุด Markers
    st.line_chart(chart_data, y="Balance", width='stretch')
    
    # คำนวณกำไรสะสมเป็น %
    initial_fund = 1000.0
    total_profit_pct = ((current_bal - initial_fund) / initial_fund) * 100
    
    # แสดงสถิติสรุปใต้กราฟ
    c1, c2, c3 = st.columns(3)
    c1.metric("งบปัจจุบัน", f"{current_bal:,.2f} ฿")
    c2.metric("กำไรสะสม", f"{total_profit_pct:.2f} %", delta=f"{current_bal - initial_fund:,.2f} ฿")
    c3.metric("สถานะบอท", "ACTIVE ✅")
else:
    st.info("📊 กราฟจะแสดงผลเมื่อมีการบันทึกประวัติการซื้อ-ขายลงใน Sheet")

if st.button("🔄 Force Refresh Now"):
    st.rerun()

st.write("⏱️ ระบบความปลอดภัย (5 Min Cooldown)...")
countdown_placeholder = st.empty()
wait_time = 300
for i in range(wait_time, 0, -10):
    countdown_placeholder.write(f"⏳ จะเริ่มสแกนใหม่ในอีก {i} วินาที...")
    time.sleep(10) 
st.rerun()






