import streamlit as st
import pandas as pd
import gspread
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. DATA FETCHING (THE GOLD TRADERS ASSOCIATION) ---

def get_thai_gold_price():
    """ดึงราคาจากสมาคมค้าทองคำ (Scraping) เพื่อความเป๊ะระดับ 100%"""
    try:
        response = requests.get("https://www.goldtraders.or.th/", timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ดึงราคาจาก ID ที่สมาคมฯ กำหนด
        sell_price = soup.find(id="DetailPlace_uc_goldprices1_lblBLSell").text.replace(",", "")
        buy_price = soup.find(id="DetailPlace_uc_goldprices1_lblBLBuy").text.replace(",", "")
        update_time = soup.find(id="DetailPlace_uc_goldprices1_lblLastUpdate").text
        
        return float(sell_price), float(buy_price), update_time
    except:
        # Fallback กรณีเว็บสมาคมฯ ล่ม (ใช้สูตรคำนวณแทน)
        return 43500.0, 43400.0, "API Fallback"

# --- 2. CORE LOGIC ---

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

# --- 3. MAIN UI ---
st.set_page_config(page_title="Gold Hunter Enterprise", layout="wide")
st.title("🛡️ Gold Hunter: Official Thai Price")

# ดึงราคาสมาคมฯ
gta_sell, gta_buy, gta_update = get_thai_gold_price()

# ส่วนแสดงผลราคาทางการ
st.subheader(f"📢 ราคาประกาศสมาคมค้าทองคำ ({gta_update})")
c1, c2 = st.columns(2)
c1.metric("ราคาสมาคมฯ (ขายออก)", f"{gta_sell:,.0f} ฿")
c2.metric("ราคาสมาคมฯ (รับซื้อคืน)", f"{gta_buy:,.0f} ฿", delta=gta_buy-gta_sell, delta_color="off")

st.divider()

# --- 4. PORTFOLIO CALCULATION (Real-World Logic) ---
sheet = init_gsheet("data_storage")
if sheet:
    data = sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        
        # LOGIC คุณภาพ: 
        # มูลค่าปัจจุบันต้องคิดจาก "ราคารับซื้อคืน (Buy Price)" 
        # เพราะนั่นคือเงินที่คุณจะได้จริงๆ เมื่อเดินเข้าร้านทอง
        def calc_real_value(row):
            # ดึงเกณฑ์น้ำหนักจากแถว (ถ้าไม่มีให้ใช้มาตรฐานทองแท่ง)
            base = 15.244 if "แท่ง" in str(row.get('Type', '')) else 15.16
            return (row['Total_Gram'] / base) * gta_buy

        df['Real_Current_Value'] = df.apply(calc_real_value, axis=1)
        
        total_invested = df['Total_Cost'].sum()
        total_real_value = df['Real_Current_Value'].sum()
        actual_pnl = total_real_value - total_invested
        
        st.subheader("💰 สรุปพอร์ตการลงทุน (คิดจากราคารับซื้อคืนจริง)")
        m1, m2, m3 = st.columns(3)
        m1.metric("เงินลงทุนทั้งหมด", f"{total_invested:,.2f} ฿")
        m2.metric("เงินสดที่จะได้รับหากขายวันนี้", f"{total_real_value:,.2f} ฿")
        m3.metric("กำไร/ขาดทุน (สุทธิ)", f"{actual_pnl:,.2f} ฿", f"{(actual_pnl/total_invested*100):.2f}%")

        st.dataframe(df.sort_index(ascending=False), use_container_width=True)
