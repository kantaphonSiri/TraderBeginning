import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from streamlit_gsheets import GSheetsConnection  # ตัวเชื่อมต่อ Google Sheets โดยตรง
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# --- 1. ตั้งค่าการเชื่อมต่อ Google Sheets ---
# คุณต้องนำ URL ของ Google Sheet มาใส่ใน Streamlit Secrets หรือ .streamlit/secrets.toml
# [connections.gsheets]
# spreadsheet = "https://docs.google.com/spreadsheets/d/your-id/edit"

conn = st.connection("gsheets", type=GSheetsConnection)

def save_to_gsheets(symbol, price, pred, score):
    # อ่านข้อมูลเดิม
    existing_data = conn.read(ttl=0) # ttl=0 เพื่อให้อ่านค่าสดใหม่เสมอ
    new_entry = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Symbol": symbol,
        "Price": price,
        "AI_Target": pred,
        "Confidence": f"{score}%"
    }])
    # ต่อข้อมูลใหม่เข้ากับข้อมูลเดิม
    updated_df = pd.concat([existing_data, new_entry], ignore_index=True)
    # อัปเดตกลับไปยัง Google Sheets
    conn.update(data=updated_df)

# --- 2. ฟังก์ชันวิเคราะห์ AI (เหมือนเดิมแต่ปรับปรุงความนิ่ง) ---
@st.cache_data(ttl=300)
def analyze_coin_ai(symbol, timeframe):
    try:
        df = yf.download(symbol, period="100d", interval=timeframe, progress=False)
        if df.empty or len(df) < 50: return None
        # ... (ส่วนการคำนวณ Technical & AI เหมือนโค้ดก่อนหน้า) ...
        # (สมมติว่าคืนค่าเป็น dict: symbol, price, pred, score)
        return {"symbol": symbol, "price": df.iloc[-1]['Close'], "pred": 0, "score": 85} # ตัวอย่าง
    except: return None

# --- 3. UI และระบบ Auto-refresh ---
st_autorefresh(interval=600 * 1000, key="gsheet_refresh")
st.title("📈 AI Trader Pro: Cloud Sync Edition")

# สแกนและบันทึก
if st.button("สแกนและบันทึกลงคลาวด์"):
    # ในการทำงานจริงจะรันอัตโนมัติตามรอบ Auto-refresh
    res = analyze_coin_ai("BTC-USD", "1h")
    if res and res['score'] >= 80:
        save_to_gsheets(res['symbol'], res['price'], res['pred'], res['score'])
        st.success(f"บันทึกสัญญาณ {res['symbol']} ลง Google Sheets สำเร็จ!")

# แสดงตารางประวัติจาก Google Sheets
st.subheader("📋 ประวัติการตรวจพบสัญญาณ (จาก Google Sheets)")
history_df = conn.read(ttl="1m") # แคชข้อมูลไว้ 1 นาทีเพื่อประหยัด API
st.dataframe(history_df, use_container_width=True)
