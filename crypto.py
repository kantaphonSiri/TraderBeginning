import streamlit as st
import pandas as pd
import gspread
import requests
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
from prophet import Prophet

# --- 1. CORE FUNCTIONS & CONNECTIVITY ---

def init_gsheet(sheet_name):
    """เชื่อมต่อกับ Google Sheet ตามชื่อ Worksheet ที่กำหนด"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            creds_dict, 
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("gold-bet").worksheet(sheet_name)
    except:
        return None

def get_weight_standards():
    """ดึงค่ามาตรฐานน้ำหนักจาก Sheet 'settings' แทนการ Fix ใน Code"""
    sheet = init_gsheet("settings")
    if sheet:
        data = sheet.get_all_records()
        # แปลงเป็น Dict { "ชื่อประเภท": น้ำหนักบาทละ }
        return {row['Type']: float(row['Base_Weight']) for row in data}
    # Fallback กรณีดึงไม่ได้จริงๆ (เพื่อไม่ให้ระบบพัง)
    return {"ทองคำแท่ง": 15.244}

@st.cache_data(ttl=1800)
def get_market_api():
    """ดึงราคาตลาด Real-time (แนะนำให้ใช้ API Key จริงเพื่อคุณภาพสูงสุด)"""
    try:
        # ดึงค่าเงินบาท
        res = requests.get("https://open.er-api.com/v6/latest/USD").json()
        thb_rate = float(res['rates']['THB'])
        
        # ตัวอย่างดึงราคา Spot (ในระบบจริงควรใช้ GoldAPI.io หรือแหล่งที่เชื่อถือได้)
        # ตัวอย่างนี้ใช้ราคาจำลองที่ขยับตามเวลาเพื่อให้เห็นการทำงาน
        spot_price = 2100.0 + (datetime.now().minute / 10) 
        thai_price = round((spot_price * 0.473 * thb_rate) * 32.148 / 28.3495, -1)
        
        return thai_price, thb_rate, spot_price
    except:
        return 43000.0, 35.0, 2100.0

# --- 2. PREDICTION ENGINE ---

def run_ai_prediction(df):
    """ใช้ Prophet ทำนายโดยพิจารณาจากข้อมูลประวัติศาสตร์ใน Sheet"""
    if len(df) < 7: return None # ต้องการข้อมูลอย่างน้อย 7 วันเพื่อหา Trend
    try:
        pdf = df[['Date', 'Gold_Price']].copy()
        pdf['ds'] = pd.to_datetime(pdf['Date'], dayfirst=True)
        pdf = pdf.rename(columns={'Gold_Price': 'y'}).sort_values('ds')
        
        model = Prophet(daily_seasonality=True, changepoint_prior_scale=0.01)
        model.fit(pdf)
        
        future = model.make_future_dataframe(periods=1)
        forecast = model.predict(future)
        return round(forecast['yhat'].iloc[-1], 2)
    except:
        return None

# --- 3. MAIN UI APP ---

st.title("🛡️ Gold Hunter ")

# ดึง Config จาก Sheet 'settings'
weight_map = get_weight_standards()
thai_price_now, thb_now, spot_now = get_market_api()

# Display Live Ticker
st.write(f"🌐 **Market Connect:** Gold Spot ${spot_now:,.2f} | THB/USD {thb_now:.2f}")

# --- 4. DYNAMIC TRANSACTION FORM ---
with st.sidebar:
    st.header("📥 ซื้อทองคำใหม่")
    # ดึงตัวเลือกจาก Sheet 'settings' โดยตรง
    selected_type = st.selectbox("เลือกประเภททองคำ (จากระบบ)", list(weight_map.keys()))
    current_base = weight_map[selected_type]
    
    st.info(f"น้ำหนักอ้างอิง: {current_base} กรัม/บาท")
    
    # Input น้ำหนัก
    in_baht = st.number_input("บาท", min_value=0, step=1)
    in_salung = st.number_input("สลึง", min_value=0, max_value=3)
    in_satang = st.number_input("สตางค์", min_value=0, max_value=99)
    
    in_cost = st.number_input("ราคาซื้อรวม (บาท)", min_value=0.0)
    
    # คำนวณน้ำหนักกรัมจาก Config ใน Sheet
    total_gram = (in_baht * current_base) + (in_salung * (current_base/4)) + (in_satang * (current_base/100))
    st.warning(f"คำนวณน้ำหนักรวม: {total_gram:.4f} กรัม")
    
    if st.button("บันทึกธุรกรรมคุณภาพ", use_container_width=True):
        main_sheet = init_gsheet("data_storage")
        if main_sheet and in_cost > 0:
            hist_df = pd.DataFrame(main_sheet.get_all_records())
            pred_val = run_ai_prediction(hist_df) if not hist_df.empty else 0
            
            row = [
                datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S"),
                thai_price_now, thb_now, spot_now, selected_type,
                in_baht, in_salung, in_satang, round(total_gram, 4), in_cost, pred_val
            ]
            main_sheet.append_row(row)
            st.success("✅ บันทึกข้อมูลแบบ Dynamic เรียบร้อย!")
            st.rerun()

# --- 5. ANALYTICS DASHBOARD ---
main_sheet = init_gsheet("data_storage")
if main_sheet:
    data = main_sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        
        # Dashboard สรุปผล
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔮 Gold Prediction")
            next_price = run_ai_prediction(df)
            if next_price:
                diff = next_price - thai_price_now
                st.metric("ราคาพรุ่งนี้ที่คาดการณ์", f"{next_price:,.2f} ฿", f"{diff:,.2f}")
            else:
                st.write("ระบบกำลังรวบรวมข้อมูลเพื่อวิเคราะห์...")

        with col2:
            st.subheader("💰 Portfolio Performance")
            # คำนวณกำไร/ขาดทุนแบบ Dynamic (ใช้ฐานน้ำหนักตามแถวนั้นๆ)
            def calc_pnl(row):
                base = weight_map.get(row['Type'], 15.244)
                current_val = (row['Total_Gram'] / base) * thai_price_now
                return current_val

            df['Market_Value'] = df.apply(calc_pnl, axis=1)
            total_invest = df['Total_Cost'].sum()
            total_market = df['Market_Value'].sum()
            total_pnl = total_market - total_invest
            
            st.metric("กำไร/ขาดทุนสุทธิ", f"{total_pnl:,.2f} ฿", f"{(total_pnl/total_invest*100):.2f}%")

        st.divider()
        st.subheader("📜 ประวัติธุรกรรม")
        st.dataframe(df, use_container_width=True)
