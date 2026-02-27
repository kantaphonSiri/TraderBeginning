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
    """เชื่อมต่อกับ Google Sheet แบบ Dynamic Worksheet"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            creds_dict, 
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        # เปิดไฟล์ gold-bet และเลือก Worksheet ตามชื่อที่ส่งมา
        return gspread.authorize(creds).open("gold-bet").worksheet(sheet_name)
    except Exception as e:
        st.error(f"❌ ไม่สามารถเชื่อมต่อกับ Sheet '{sheet_name}': {e}")
        return None

def get_weight_standards():
    """ดึงค่ามาตรฐานน้ำหนักจาก Sheet 'settings' (Dynamic & No Hard-code)"""
    sheet = init_gsheet("settings")
    if sheet:
        try:
            data = sheet.get_all_records()
            # ใช้ .strip() เพื่อล้างช่องว่างที่อาจติดมาในชื่อประเภททอง
            standards = {str(row['Type']).strip(): float(row['Base_Weight']) for row in data if 'Type' in row}
            if standards:
                return standards
        except Exception as e:
            st.warning(f"⚠️ โครงสร้างข้อมูลใน settings ไม่ถูกต้อง: {e}")
    
    # Fallback กรณีดึงไม่ได้ เพื่อไม่ให้แอป Crash (KeyError)
    return {"ทองคำแท่ง": 15.244, "ทองรูปพรรณ": 15.16}

@st.cache_data(ttl=1800)
def get_market_api():
    """ดึงราคาตลาด Real-time"""
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10).json()
        thb_rate = float(res['rates']['THB'])
        # ราคาสมมติ (แนะนำให้เชื่อมต่อ GoldAPI.io เพื่อความแม่นยำสูงสุด)
        spot_price = 2100.0 + (datetime.now().minute / 10) 
        thai_price = round((spot_price * 0.473 * thb_rate) * 32.148 / 28.3495, -1)
        return thai_price, thb_rate, spot_price
    except:
        return 43000.0, 35.0, 2100.0

# --- 2. PREDICTION ENGINE ---

def run_ai_prediction(df):
    """วิเคราะห์แนวโน้มด้วย Facebook Prophet"""
    if len(df) < 7: return None 
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

st.title("🛡️ Gold Hunter AI: Enterprise")

# โหลดข้อมูลมาตรฐาน (ดึงจาก Sheet ทันทีที่เปิดแอป)
weight_map = get_weight_standards()
thai_price_now, thb_now, spot_now = get_market_api()

st.write(f"🌐 **สถานะตลาด:** Gold Spot ${spot_now:,.2f} | THB/USD {thb_now:.2f}")

# --- 4. SIDEBAR: TRANSACTION FORM ---
with st.sidebar:
    st.header("📥 เพิ่มข้อมูลการซื้อ")
    
    # ดึงตัวเลือกประเภททองจาก weight_map ที่ดึงมาจาก Sheet
    gold_options = list(weight_map.keys())
    selected_type = st.selectbox("เลือกประเภททองคำ", gold_options)
    
    # ใช้ .get เพื่อป้องกัน KeyError หากข้อมูลใน Sheet หายไปกะทันหัน
    current_base = weight_map.get(selected_type, 15.244)
    st.info(f"มาตรฐาน: {selected_type} ({current_base} กรัม/บาท)")
    
    c1, c2, c3 = st.columns(3)
    in_baht = c1.number_input("บาท", min_value=0, step=1)
    in_salung = c2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = c3.number_input("สตางค์", min_value=0, max_value=99)
    
    in_cost = st.number_input("ราคารวมที่จ่าย (฿)", min_value=0.0)
    
    # คำนวณน้ำหนักกรัม (Dynamic Calculation)
    total_gram = (in_baht * current_base) + (in_salung * (current_base/4)) + (in_satang * (current_base/100))
    st.warning(f"⚖️ น้ำหนักกรัมรวม: {total_gram:.4f} g")
    
    if st.button("🚀 บันทึกข้อมูลลง Google Sheet", use_container_width=True):
        main_sheet = init_gsheet("data_storage")
        if main_sheet and in_cost > 0:
            with st.spinner("กำลังวิเคราะห์และบันทึก..."):
                try:
                    # ดึงประวัติมาทำนาย
                    all_recs = main_sheet.get_all_records()
                    hist_df = pd.DataFrame(all_recs) if all_recs else pd.DataFrame()
                    pred_val = run_ai_prediction(hist_df) if not hist_df.empty else 0
                    
                    # เตรียม Row ข้อมูล
                    new_row = [
                        datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S"),
                        thai_price_now, thb_now, spot_now, selected_type,
                        in_baht, in_salung, in_satang, round(total_gram, 4), in_cost, pred_val
                    ]
                    
                    main_sheet.append_row(new_row)
                    st.success("✅ บันทึกสำเร็จ!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดขณะบันทึก: {e}")

# --- 5. DASHBOARD SECTION ---
main_sheet = init_gsheet("data_storage")
if main_sheet:
    data = main_sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔮 AI Predict")
            next_p = run_ai_prediction(df)
            if next_p:
                diff = next_p - thai_price_now
                st.metric("ทำนายราคาพรุ่งนี้", f"{next_p:,.2f} ฿", f"{diff:,.2f}")
            else:
                st.write("สะสมข้อมูลเพื่อเริ่มการวิเคราะห์...")

        with col2:
            st.subheader("💰 Performance")
            # คำนวณมูลค่าปัจจุบันแบบอ้างอิงรายแถว
            def get_market_val(row):
                base = weight_map.get(row['Type'], 15.244)
                return (row['Total_Gram'] / base) * thai_price_now

            df['Market_Value'] = df.apply(get_market_val, axis=1)
            total_invest = df['Total_Cost'].sum()
            total_market = df['Market_Value'].sum()
            pnl = total_market - total_invest
            
            st.metric("กำไร/ขาดทุนสะสม", f"{pnl:,.2f} ฿", f"{(pnl/total_invest*100):.2f}%" if total_invest > 0 else "0%")

        st.divider()
        st.subheader("📜 ประวัติธุรกรรม")
        st.dataframe(df.sort_index(ascending=False), use_container_width=True)
    else:
        st.info("👋 ยินดีต้อนรับ! เริ่มบันทึกรายการซื้อทองคำครั้งแรกที่แถบด้านซ้าย")
