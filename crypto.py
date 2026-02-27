import streamlit as st
import pandas as pd
import gspread
import requests
import time
import yfinance as yf
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. DATA FETCHING ---
def get_market_prices():
    # ค่าเริ่มต้นเผื่อกรณีดึงไม่ได้เลย
    prices = {"gta_sell": 76250.0, "gta_buy": 76050.0, "intl_sell": 78948.0, "intl_buy": 79018.0, "update": "Fallback Mode", "spot": 0.0, "thb": 0.0}
    
    # Header เพื่อหลอกเว็บไซต์ว่าเป็นคนเข้าชม
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # 1. พยายามดึงสมาคมฯ ด้วย Header
        res = requests.get("https://www.goldtraders.or.th/", headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            prices["gta_sell"] = float(soup.find(id="DetailPlace_uc_goldprices1_lblBLSell").text.replace(",", ""))
            prices["gta_buy"] = float(soup.find(id="DetailPlace_uc_goldprices1_lblBLBuy").text.replace(",", ""))
            prices["update"] = soup.find(id="DetailPlace_uc_goldprices1_lblLastUpdate").text
        
        # 2. ดึงตลาดโลก (ซึ่งเสถียรกว่ามาก) มาเป็นตัวเปรียบเทียบ
        gold_spot_obj = yf.Ticker("GC=F")
        thb_obj = yf.Ticker("THB=X")
        
        # ใช้ .info['regularMarketPrice'] หรือ .fast_info['last_price']
        spot = gold_spot_obj.fast_info['last_price']
        thb = thb_obj.fast_info['last_price']
        
        prices["spot"] = spot
        prices["thb"] = thb
        
        # คำนวณราคาสากล (99.99%) และราคาไทยทางเลือก (96.5% Calculated)
        # สูตร: (Spot * 0.473 * THB) * 32.148 / 28.3495 (มาตรฐานสมาคม)
        prices["intl_sell"] = round((spot / 31.1035) * 15.16 * thb, -1)
        prices["intl_buy"] = prices["intl_sell"] - 100
        
    except Exception as e:
        # หาก Scraping พลาด ให้ใช้สูตรคำนวณจาก Spot แทน เพื่อให้แอปยังมีราคา Real-time
        if prices["spot"] > 0:
            calculated_thai = round((prices["spot"] * 0.473 * prices["thb"]) * 32.148 / 28.3495, -1)
            prices["gta_sell"] = calculated_thai
            prices["gta_buy"] = calculated_thai - 100
            prices["update"] = "Calculated from Spot"
            
    return prices

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
st.set_page_config(page_title="Gold Hunter Pro 2026", layout="wide")
prices = get_market_prices()

st.title("Gold Intelligence")
st.caption(f"อัปเดต: {prices['update']} | Spot: ${prices['spot']:,.2f} | THB: {prices['thb']:.2f}")

# --- 3. DASHBOARD ---
col_thai, col_intl = st.columns(2)
with col_thai:
    st.info("🇹🇭 ทองไทย (96.5%)")
    c1, c2 = st.columns(2)
    c1.metric("ขายออก", f"{prices['gta_sell']:,.0f} ฿")
    c2.metric("รับซื้อคืน", f"{prices['gta_buy']:,.0f} ฿")

with col_intl:
    st.success("🌐 ทองสากล (99.99%)")
    c3, c4 = st.columns(2)
    c3.metric("ราคาประเมินขาย", f"{prices['intl_sell']:,.0f} ฿")
    c4.metric("ราคาประเมินซื้อ", f"{prices['intl_buy']:,.0f} ฿")

st.divider()

# --- 4. SIDEBAR (Input Section) ---
with st.sidebar:
    st.header("📥 บันทึกการลงทุน")
    purity = st.selectbox("ความบริสุทธิ์", ["96.5%", "99.99%"])
    base_weight = 15.244 if purity == "96.5%" else 15.16
    g_type = st.selectbox("ประเภททอง", ["ทองคำแท่ง", "ทองรูปพรรณ"])
    
    col_w1, col_w2, col_w3 = st.columns(3)
    in_baht = col_w1.number_input("บาท", min_value=0)
    in_salung = col_w2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = col_w3.number_input("สตางค์", min_value=0, max_value=99)
    
    total_cost = st.number_input("เงินที่จ่ายจริง (฿)", min_value=0.0)
    calc_gram = (in_baht * base_weight) + (in_salung * (base_weight/4)) + (in_satang * (base_weight/100))
    st.code(f"น้ำหนัก: {calc_gram:.4f} กรัม (ฐาน {base_weight})")

    # อัปเดตใช้ width='stretch' แทน use_container_width=True
    if st.button("💾 บันทึกลง Google Sheet", width='stretch'):
        sheet = init_gsheet("data_storage")
        if sheet and total_cost > 0:
            market_now = prices['gta_sell'] if purity == "96.5%" else prices['intl_sell']
            row = [
                datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S"),
                market_now, purity, prices['spot'], g_type,
                in_baht, in_salung, in_satang, round(calc_gram, 4), total_cost, 0
            ]
            sheet.append_row(row)
            st.success("บันทึกสำเร็จ!")
            time.sleep(1)
            st.rerun()

# --- 5. PORTFOLIO ANALYSIS ---
sheet = init_gsheet("data_storage")
if sheet:
    data = sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        def get_current_val(row):
            p_type = str(row.get('Gold_Price', '96.5%'))
            divisor = 15.16 if "99.99" in p_type else 15.244
            ref_price = prices['intl_buy'] if "99.99" in p_type else prices['gta_buy']
            return (row['Total_Gram'] / divisor) * ref_price

        df['Current_Value'] = df.apply(get_current_val, axis=1)
        t_invest = df['Total_Cost'].sum()
        t_value = df['Current_Value'].sum()
        t_pnl = t_value - t_invest
        
        st.subheader("📊 พอร์ตการลงทุน")
        m1, m2, m3 = st.columns(3)
        m1.metric("ต้นทุนทั้งหมด", f"{t_invest:,.2f} ฿")
        m2.metric("มูลค่าคืนรวม", f"{t_value:,.2f} ฿")
        m3.metric("กำไรสุทธิ", f"{t_pnl:,.2f} ฿", f"{(t_pnl/t_invest*100):.2f}%" if t_invest > 0 else "0%")

        # อัปเดตตารางให้ใช้ width='stretch'
        st.dataframe(df.sort_index(ascending=False), width='stretch')
    else:
        st.info("👋 เริ่มบันทึกข้อมูลแรกที่แถบด้านซ้าย")

