import streamlit as st
import pandas as pd
import gspread
import requests
import time
import yfinance as yf
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
from prophet import Prophet

# --- 1. SETTINGS & CONFIG ---
st.set_page_config(page_title="Predict Gold", layout="wide")

# --- 2. CORE CONNECTIVITY (GOOGLE SHEETS) ---
def init_gsheet(sheet_name):
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            creds_dict, 
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("gold-bet").worksheet(sheet_name)
    except Exception as e:
        st.error(f"❌ Connection Error ({sheet_name}): {e}")
        return None

def get_weight_standards():
    """ดึงเกณฑ์น้ำหนักจาก Sheet 'settings'"""
    sheet = init_gsheet("settings")
    if sheet:
        try:
            data = sheet.get_all_records()
            return {str(row['Type']).strip(): float(row['Base_Weight']) for row in data if 'Type' in row}
        except: pass
    return {"ทองคำแท่ง": 15.244, "ทองรูปพรรณ": 15.16}

# --- 3. MARKET DATA & AI ENGINE ---

@st.cache_data(ttl=3600)
def fetch_market_ai_data():
    """ดึงข้อมูลตลาดโลกย้อนหลัง 6 เดือนเพื่อสร้างโมเดลทำนาย"""
    try:
        # ดึง Gold Futures (GC=F) และ USD/THB (THB=X)
        gold = yf.download("GC=F", period="6mo", interval="1d")
        thb = yf.download("THB=X", period="6mo", interval="1d")
        
        # เตรียมข้อมูลสำหรับ Prophet
        df = pd.DataFrame()
        df['ds'] = gold.index
        # สูตรแปลงราคาทองไทย: (Spot * 0.473 * THB) * 32.148 / 28.3495
        # ffill() เพื่อเติมค่าว่างกรณีวันหยุดตลาดไม่ตรงกัน
        gold_c = gold['Close'].ffill()
        thb_c = thb['Close'].ffill()
        
        df['y'] = (gold_c.values * 0.473 * thb_c.values) * 32.148 / 28.3495
        df['y'] = df['y'].ffill().round(-1)
        
        # สอน AI (Prophet)
        model = Prophet(daily_seasonality=True, changepoint_prior_scale=0.05)
        model.fit(df[['ds', 'y']])
        
        # ทำนายอนาคต 1 วัน
        future = model.make_future_dataframe(periods=1)
        forecast = model.predict(future)
        
        return df['y'].iloc[-1], round(forecast['yhat'].iloc[-1], -1), df
    except Exception as e:
        st.warning(f"⚠️ AI Data Fetching issue: {e}")
        return 43000.0, 43050.0, None

# --- 4. MAIN UI ---
st.title("🛡️ Predict Gold")

# ดึงข้อมูลทันทีที่เปิดแอป
with st.spinner('Analyzing Market Data...'):
    market_price, pred_price, hist_df = fetch_market_ai_data()
    weight_map = get_weight_standards()

# ส่วนแสดงผลราคาและคำแนะนำ
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("ราคาตลาดไทยวันนี้ (โดยประมาณ)", f"{market_price:,.2f} ฿")
with c2:
    diff = pred_price - market_price
    st.metric("AI ทำนายราคาพรุ่งนี้", f"{pred_price:,.2f} ฿", f"{diff:,.2f} ฿")
with c3:
    sentiment = "📈 แนวโน้มขาขึ้น" if diff > 0 else "📉 แนวโน้มขาลง"
    st.subheader(f"Strategy: {sentiment}")



st.divider()

# --- 5. SIDEBAR: DATA INPUT (Dynamic) ---
with st.sidebar:
    st.header("📥 บันทึกรายการใหม่")
    g_type = st.selectbox("เลือกประเภททอง", list(weight_map.keys()))
    base = weight_map.get(g_type, 15.244)
    st.caption(f"มาตรฐาน {g_type}: {base} กรัม/บาท")
    
    col1, col2, col3 = st.columns(3)
    b_baht = col1.number_input("บาท", min_value=0, step=1)
    b_salung = col2.number_input("สลึง", min_value=0, max_value=3)
    b_satang = col3.number_input("สตางค์", min_value=0, max_value=99)
    
    in_cost = st.number_input("ราคาที่จ่ายจริงทั้งหมด (฿)", min_value=0.0)
    
    # คำนวณน้ำหนักกรัมอัตโนมัติ
    total_g = (b_baht * base) + (b_salung * (base/4)) + (b_satang * (base/100))
    st.info(f"⚖️ น้ำหนักกรัมรวม: {total_g:.4f} g")

    if st.button("🚀 บันทึกธุรกรรมลง Sheet", use_container_width=True):
        sheet = init_gsheet("data_storage")
        if sheet and in_cost > 0:
            row = [
                datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S"),
                market_price, 35.0, 2000.0, g_type, 
                b_baht, b_salung, b_satang, round(total_g, 4), in_cost, pred_price
            ]
            sheet.append_row(row)
            st.success("บันทึกสำเร็จ!")
            time.sleep(1)
            st.rerun()

# --- 6. DASHBOARD: PORTFOLIO & HISTORY ---
sheet = init_gsheet("data_storage")
if sheet:
    raw_data = sheet.get_all_records()
    if raw_data:
        df = pd.DataFrame(raw_data)
        st.subheader("📊 My Portfolio Performance")
        
        # คำนวณ Market Value รายแถวตามประเภททอง
        def calc_current_value(row):
            b = weight_map.get(row['Type'], 15.244)
            return (row['Total_Gram'] / b) * market_price

        df['Current_Value'] = df.apply(calc_current_value, axis=1)
        
        total_inv = df['Total_Cost'].sum()
        total_val = df['Current_Value'].sum()
        total_pnl = total_val - total_inv
        
        m1, m2 = st.columns(2)
        m1.metric("มูลค่ารวมในพอร์ต", f"{total_val:,.2f} ฿")
        m2.metric("กำไร/ขาดทุนสุทธิ", f"{total_pnl:,.2f} ฿", f"{(total_pnl/total_inv*100):.2f}%" if total_inv > 0 else "0%")

        st.dataframe(df.sort_index(ascending=False), use_container_width=True)
        
        # กราฟราคาตลาดที่ AI ใช้
        if hist_df is not None:
            st.subheader("📉 Market Trends (Reference)")
            st.line_chart(hist_df.set_index('ds'))
    else:
        st.info("เริ่มบันทึกรายการซื้อที่แถบด้านซ้ายเพื่อดูการวิเคราะห์พอร์ต")
