import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import gspread
import time
import random
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# --- 1. การตั้งค่าหน้าจอ ---
st.set_page_config(page_title="AI Crypto Compounder", layout="wide")
st_autorefresh(interval=600 * 1000, key="auto_trade_refresh")

# --- 2. ฟังก์ชันเชื่อมต่อ Google Sheets (รองรับแท็บ trade_learning) ---
def init_gsheet(sheet_name="trade_learning"):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Blue-chip Bet").worksheet(sheet_name)
    except:
        return None

# --- 3. ฟังก์ชัน AI วิเคราะห์ (เหมือนเดิมแต่ดึงข้อมูลแม่นยำขึ้น) ---
@st.cache_data(ttl=300)
def analyze_coin_ai(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df.ta.rsi(length=14, append=True); df.ta.ema(length=20, append=True); df.ta.ema(length=50, append=True)
        df = df.dropna()
        
        X, y = df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[:-1], df['Close'].shift(-1).iloc[:-1]
        model = RandomForestRegressor(n_estimators=30, random_state=42).fit(X, y)
        
        cur_price = float(df.iloc[-1]['Close'])
        pred_price = model.predict(df[['Close', 'RSI_14', 'EMA_20', 'EMA_50']].iloc[[-1]])[0]
        
        score = 0
        if cur_price > df.iloc[-1]['EMA_20'] > df.iloc[-1]['EMA_50']: score += 40
        if 40 < df.iloc[-1]['RSI_14'] < 65: score += 30
        if pred_price > cur_price: score += 30
        return {"Symbol": symbol, "Price": cur_price, "Score": score}
    except: return None

# --- 4. หัวใจหลัก: ระบบ Trading Logic & Learning ---
def run_auto_trade(res, sheet, current_balance):
    if not sheet: return
    
    data = sheet.get_all_records()
    df_trade = pd.DataFrame(data)
    
    # เช็คว่ามีเหรียญนี้ถืออยู่ไหม
    is_holding = False
    if not df_trade.empty:
        is_holding = any((df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD'))
    
    # LOGIC ซื้อ: คะแนนสูง และ ยังไม่มีเหรียญนี้ในมือ
    if res['Score'] >= 85 and not is_holding:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # บันทึก: [วันเวลา, เหรียญ, สถานะ, ราคาซื้อ, ราคาขาย, กำไร%, AI_Score, Balance]
        row = [now, res['Symbol'], "HOLD", res['Price'], 0, 0, res['Score'], current_balance]
        sheet.append_row(row)
        st.toast(f"🚀 AI ซื้อ {res['Symbol']} ที่ราคา {res['Price']:.2f}")

    # LOGIC ขาย: กำไร > 3% หรือ ขาดทุน > 2% หรือ คะแนนตกต่ำกว่า 50
    elif is_holding:
        idx = df_trade[(df_trade['เหรียญ'] == res['Symbol']) & (df_trade['สถานะ'] == 'HOLD')].index[-1]
        entry_price = float(df_trade.loc[idx, 'ราคาซื้อ'])
        profit_pct = ((res['Price'] - entry_price) / entry_price) * 100
        
        if profit_pct >= 3.0 or profit_pct <= -2.0 or res['Score'] < 50:
            new_balance = current_balance * (1 + (profit_pct/100))
            # อัปเดตแถวใน Sheets (gspread index เริ่มที่ 1 และมี header จึงเป็น idx + 2)
            row_num = int(idx) + 2
            sheet.update_cell(row_num, 3, "SOLD")       # เปลี่ยนสถานะ
            sheet.update_cell(row_num, 5, res['Price']) # ราคาขาย
            sheet.update_cell(row_num, 6, f"{profit_pct:.2f}%")
            sheet.update_cell(row_num, 8, round(new_balance, 2))
            st.toast(f"💰 AI ขาย {res['Symbol']} กำไร {profit_pct:.2f}%")

# --- 5. หน้าจอ UI ---
st.title("🤖 AI Auto-Compounder (500 ➡️ 1,000)")
sheet = init_gsheet()
watch_list = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD", "DOT-USD"]

# ดึง Balance ล่าสุด
current_bal = 500.0
if sheet:
    all_data = sheet.get_all_records()
    if all_data:
        last_row = all_data[-1]
        current_bal = float(last_row.get('Balance', 500.0))

st.metric("พอร์ตจำลองปัจจุบัน (Equity)", f"฿{current_bal:,.2f}", f"{((current_bal-500)/500)*100:.2f}% จากเงินต้น")

# เริ่มสแกนและเทรด
for ticker in watch_list:
    result = analyze_coin_ai(ticker)
    if result:
        run_auto_trade(result, sheet, current_bal)

# โชว์ตารางการเรียนรู้
st.subheader("📚 บันทึกการเรียนรู้ของ AI (Trade Log)")
if sheet:
    hist = pd.DataFrame(sheet.get_all_records())
    if not hist.empty:
        st.dataframe(hist.iloc[::-1], use_container_width=True)
