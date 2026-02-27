import streamlit as st
import pandas as pd
import gspread
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# --- 1. CONFIG & REAL-TIME DATA FETCHING ---

def get_market_prices():
    """ดึงข้อมูลราคาสมาคมฯ (96.5%) และคำนวณราคา 99.99% จากตลาดโลก"""
    prices = {
        "gta_sell": 76250.0, "gta_buy": 76050.0,  # 96.5%
        "intl_sell": 78948.0, "intl_buy": 79018.0, # 99.99%
        "update": "Loading...", "spot": 0.0, "thb": 0.0
    }
    try:
        # 1. ดึงราคาสมาคมฯ (96.5%)
        res = requests.get("https://www.goldtraders.or.th/", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        prices["gta_sell"] = float(soup.find(id="DetailPlace_uc_goldprices1_lblBLSell").text.replace(",", ""))
        prices["gta_buy"] = float(soup.find(id="DetailPlace_uc_goldprices1_lblBLBuy").text.replace(",", ""))
        prices["update"] = soup.find(id="DetailPlace_uc_goldprices1_lblLastUpdate").text
        
        # 2. ดึงตลาดโลก (99.99%) ผ่าน yfinance
        gold_spot = yf.Ticker("GC=F").fast_info['last_price']
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
        
        # สูตรคำนวณทอง 99.99%: (Spot / 31.1035) * 15.16 * THB
        # (อ้างอิงมาตรฐาน 1 บาททอง 99.99% = 15.16 กรัม)
        prices["intl_sell"] = round((gold_spot / 31.1035) * 15.16 * usd_thb, -1)
        prices["intl_buy"] = prices["intl_sell"] - 100 # Spread โดยประมาณ
        prices["spot"] = gold_spot
        prices["thb"] = usd_thb
        
    except Exception as e:
        st.warning(f"⚠️ การดึงข้อมูลขัดข้อง: ใช้ราคาตลาดล่าสุดโดยประมาณ")
    
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

# --- 2. APP LAYOUT ---
st.set_page_config(page_title="Gold Hunter Pro", layout="wide")
prices = get_market_prices()

st.title("🛡️ Gold Analysis")
st.caption(f"อัปเดตล่าสุด: {prices['update']} | Spot: ${prices['spot']:,.2f} | THB: {prices['thb']:.2f}")

# --- 3. DASHBOARD: REAL PRICES ---
col_thai, col_intl = st.columns(2)

with col_thai:
    st.info("🇹🇭 มาตรฐานไทย (96.5%)")
    c1, c2 = st.columns(2)
    c1.metric("ขายออก", f"{prices['gta_sell']:,.0f} ฿")
    c2.metric("รับซื้อคืน", f"{prices['gta_buy']:,.0f} ฿")

with col_intl:
    st.success("🌐 มาตรฐานสากล (99.99%)")
    c3, c4 = st.columns(2)
    c3.metric("ราคาประเมินขาย", f"{prices['intl_sell']:,.0f} ฿")
    c4.metric("ราคาประเมินซื้อคืน", f"{prices['intl_buy']:,.0f} ฿")

st.divider()

# --- 4. SIDEBAR: DATA INPUT ---
with st.sidebar:
    st.header("📥 บันทึกการลงทุน")
    
    # 1. เลือกความบริสุทธิ์ (เพื่อให้คำนวณถูก)
    purity = st.selectbox("ความบริสุทธิ์", ["96.5%", "99.99%"])
    
    # 2. เลือกประเภท (เพื่อดึงน้ำหนักมาตรฐาน)
    # 96.5% -> 15.244g | 99.99% -> 15.16g
    base_weight = 15.244 if purity == "96.5%" else 15.16
    
    g_type = st.selectbox("ประเภททอง", ["ทองคำแท่ง", "ทองรูปพรรณ"])
    
    col_w1, col_w2, col_w3 = st.columns(3)
    in_baht = col_w1.number_input("บาท", min_value=0)
    in_salung = col_w2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = col_w3.number_input("สตางค์", min_value=0, max_value=99)
    
    total_cost = st.number_input("เงินที่จ่ายจริง (฿)", min_value=0.0)
    
    # คำนวณกรัมอัตโนมัติ
    calc_gram = (in_baht * base_weight) + (in_salung * (base_weight/4)) + (in_satang * (base_weight/100))
    st.code(f"น้ำหนักรวม: {calc_gram:.4f} กรัม\n(อ้างอิงฐาน {base_weight} กรัม/บาท)")

    if st.button("💾 บันทึกลง Google Sheet", use_container_width=True):
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
        
        # ฟังก์ชันคำนวณมูลค่าปัจจุบันตามประเภททองที่ User บันทึกไว้
        def get_current_val(row):
            # ตรวจสอบว่าแถวนั้นเป็น 96.5 หรือ 99.99
            p_type = str(row.get('Gold_Price', '96.5%')) # สมมติเก็บ Purity ใน Col B
            if "99.99" in p_type:
                return (row['Total_Gram'] / 15.16) * prices['intl_buy']
            else:
                return (row['Total_Gram'] / 15.244) * prices['gta_buy']

        df['Current_Value'] = df.apply(get_current_val, axis=1)
        
        t_invest = df['Total_Cost'].sum()
        t_value = df['Current_Value'].sum()
        t_pnl = t_value - t_invest
        
        st.subheader("📊 วิเคราะห์กำไร/ขาดทุนในพอร์ต")
        m1, m2, m3 = st.columns(3)
        m1.metric("ต้นทุนทั้งหมด", f"{t_invest:,.2f} ฿")
        m2.metric("มูลค่าขายคืนรวม", f"{t_value:,.2f} ฿")
        m3.metric("กำไรสุทธิ", f"{t_pnl:,.2f} ฿", f"{(t_pnl/t_invest*100):.2f}%" if t_invest > 0 else "0%")

        st.dataframe(df.sort_index(ascending=False), use_container_width=True)
    else:
        st.info("บันทึกข้อมูลแรกเพื่อเริ่มใช้งาน")
