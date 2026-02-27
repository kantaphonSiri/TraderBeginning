import streamlit as st
import pandas as pd
import gspread
import requests
import time
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. CONFIG & DATA FETCHING ---

def get_thai_gold_price():
    """ดึงราคาจากสมาคมค้าทองคำ"""
    try:
        response = requests.get("https://www.goldtraders.or.th/", timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        sell = float(soup.find(id="DetailPlace_uc_goldprices1_lblBLSell").text.replace(",", ""))
        buy = float(soup.find(id="DetailPlace_uc_goldprices1_lblBLBuy").text.replace(",", ""))
        update = soup.find(id="DetailPlace_uc_goldprices1_lblLastUpdate").text
        return sell, buy, update
    except:
        return 43500.0, 43400.0, "API Fallback"

def init_gsheet(sheet_name):
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            creds_dict, 
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("gold-bet").worksheet(sheet_name)
    except: return None

# --- 2. UI SETUP ---
st.set_page_config(page_title="Gold Hunter Enterprise", layout="wide")
st.title("🛡️ Gold Hunter")

# ดึงข้อมูลจากสมาคมฯ และ Google Sheet Settings
gta_sell, gta_buy, gta_update = get_thai_gold_price()

# --- 3. SIDEBAR: INPUT FORM (ส่วนที่ User กรอก) ---
with st.sidebar:
    st.header("📥 บันทึกการซื้อใหม่")
    
    # ดึงค่ามาตรฐานจาก Sheet settings (คุณภาพ: ไม่ Fix ค่า)
    set_sheet = init_gsheet("settings")
    if set_sheet:
        settings_data = set_sheet.get_all_records()
        weight_map = {str(row['Type']): float(row['Base_Weight']) for row in settings_data}
    else:
        weight_map = {"ทองคำแท่ง": 15.244, "ทองรูปพรรณ": 15.16}

    selected_type = st.selectbox("เลือกประเภททอง", list(weight_map.keys()))
    base_w = weight_map.get(selected_type, 15.244)
    
    st.caption(f"มาตรฐาน {selected_type}: {base_w} กรัม/บาท")
    
    c1, c2, c3 = st.columns(3)
    in_baht = c1.number_input("บาท", min_value=0, step=1)
    in_salung = c2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = c3.number_input("สตางค์", min_value=0, max_value=99)
    
    in_cost = st.number_input("ราคาที่จ่ายจริง (รวมกำเหน็จ)", min_value=0.0)
    
    # คำนวณน้ำหนักกรัม
    total_gram = (in_baht * base_w) + (in_salung * (base_w/4)) + (in_satang * (base_w/100))
    st.warning(f"⚖️ น้ำหนักกรัมรวม: {total_gram:.4f} g")

    if st.button("บันทึกธุรกรรมลง Sheet", use_container_width=True):
        main_sheet = init_gsheet("data_storage")
        if main_sheet and in_cost > 0:
            row = [
                datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S"),
                gta_sell,  # เก็บราคาขายออกตอนนั้น
                "GTA_API", # Source
                0,         # Spot (Optional)
                selected_type,
                in_baht, in_salung, in_satang,
                round(total_gram, 4), in_cost, 0 # Prediction (Optional)
            ]
            main_sheet.append_row(row)
            st.success("✅ บันทึกสำเร็จ!")
            time.sleep(1)
            st.rerun()

# --- 4. MAIN DASHBOARD ---
st.subheader(f"📢 ราคาประกาศสมาคมค้าทองคำ ({gta_update})")
mc1, mc2 = st.columns(2)
mc1.metric("สมาคมฯ ขายออก (ใช้บันทึกต้นทุน)", f"{gta_sell:,.0f} ฿")
mc2.metric("สมาคมฯ รับซื้อคืน (ใช้คำนวณกำไร)", f"{gta_buy:,.0f} ฿", delta=gta_buy-gta_sell, delta_color="off")

st.divider()

# --- 5. PORTFOLIO CALCULATION ---
data_sheet = init_gsheet("data_storage")
if data_sheet:
    raw_data = data_sheet.get_all_records()
    if raw_data:
        df = pd.DataFrame(raw_data)
        
        # คำนวณกำไรจาก "ราคารับซื้อคืน"
        def calc_real_value(row):
            b = weight_map.get(row.get('Type'), 15.244)
            return (row['Total_Gram'] / b) * gta_buy

        df['Current_Value'] = df.apply(calc_real_value, axis=1)
        total_inv = df['Total_Cost'].sum()
        total_val = df['Current_Value'].sum()
        actual_pnl = total_val - total_inv
        
        st.subheader("💰 สรุปพอร์ตการลงทุน")
        m1, m2, m3 = st.columns(3)
        m1.metric("เงินลงทุนทั้งหมด", f"{total_inv:,.2f} ฿")
        m2.metric("มูลค่าที่จะได้รับถ้าขายจริง", f"{total_val:,.2f} ฿")
        m3.metric("กำไร/ขาดทุนสุทธิ", f"{actual_pnl:,.2f} ฿", f"{(actual_pnl/total_inv*100):.2f}%" if total_inv > 0 else "0%")

        st.dataframe(df.sort_index(ascending=False), use_container_width=True)
    else:
        st.info("👋 ยังไม่มีข้อมูลการลงทุน เริ่มบันทึกที่เมนูด้านซ้ายได้เลย")
