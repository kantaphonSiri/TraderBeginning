import streamlit as st
import pandas as pd
import requests
import time

# --- ตั้งค่า URL สำหรับบันทึกข้อมูล (ใช้ Google Form Webhook) ---
# ให้คุณเอา URL จาก Google Form ที่ทำเป็น 'Get pre-filled link' มาประยุกต์ใส่ตรงนี้
FORM_URL = "https://docs.google.com/forms/d/e/YOUR_FORM_ID/formResponse"

# URL ดึงข้อมูล (อันเดิมของคุณ)
SHEET_PORT_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?gid=820979573&single=true&output=csv"

# ฟังก์ชันส่งข้อมูลเข้า Google Sheets ผ่าน Google Form
def save_to_cloud(user, symbol, price):
    # payload ต้องตรงกับ entry id ใน Google Form ของคุณ
    payload = {
        "entry.123456789": user,    # แก้ ID ให้ตรงกับช่อง 'owner'
        "entry.987654321": symbol,  # แก้ ID ให้ตรงกับช่อง 'symbol'
        "entry.112233445": price    # แก้ ID ให้ตรงกับช่อง 'buy_price'
    }
    try:
        requests.post(FORM_URL, data=payload)
        return True
    except:
        return False

# --- ส่วนของการเพิ่มปุ่มใน Sidebar ---
with st.sidebar:
    if st.session_state.user:
        st.title(f"👤 {st.session_state.user}")
        
        # เพิ่มปุ่มบันทึกข้อมูลทั้งหมดลง Cloud
        if st.button("💾 Save All to Cloud"):
            with st.spinner("กำลังบันทึกลง Google Sheets..."):
                success_count = 0
                for coin in st.session_state.pinned_list:
                    price = st.session_state.buy_prices.get(coin, 0)
                    if save_to_cloud(st.session_state.user, coin, price):
                        success_count += 1
                st.success(f"บันทึกสำเร็จ {success_count} รายการ!")
                time.sleep(2)
                st.rerun()

        st.divider()
        # (ส่วนการแสดงผล Portfolio และ Slider เหมือนเดิม...)
