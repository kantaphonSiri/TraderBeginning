import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="Gold Bet", layout="wide")

def init_gsheet():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("❌ ไม่พบ gcp_service_account ใน Secrets")
            return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("gold-bet").worksheet("data_storage")
    except Exception as e:
        st.error(f"⚠️ เชื่อมต่อ Google Sheet ไม่ได้: {e}")
        return None

# --- 2. DATA RETRIEVAL (SAFE MODE) ---
def get_real_thai_gold():
    """ดึงราคาทองแท่งขายออกจากสมาคมค้าทองคำ"""
    try:
        url = "https://www.goldtraders.or.th/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        sell_price_text = soup.find(id="DetailPlace_uc_goldprices1_lblBLSell").text
        return float(sell_price_text.replace(',', ''))
    except:
        return 0.0

def get_exchange_rate():
    """ดึงค่าเงินบาท (USD/THB)"""
    try:
        data = yf.download("THB=X", period="1d", progress=False)['Close']
        if not data.empty:
            return float(data.iloc[-1])
        return 35.0 # ค่าสำรอง
    except:
        return 35.0

@st.cache_data(ttl=3600)
def get_ai_data():
    """ดึงข้อมูลเศรษฐกิจเพื่อ Train AI"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5*365)
        # ใช้ Tickers ที่เสถียรที่สุด
        tickers = {"gold_spot": "GC=F", "dxy": "DX-Y.NYB", "inflation_etf": "TIP"}
        df_list = []
        for name, sym in tickers.items():
            data = yf.download(sym, start=start_date, end=end_date, progress=False)['Close']
            if not data.empty:
                df_list.append(pd.DataFrame({name: data}))
        
        if not df_list: return pd.DataFrame()
        
        df = pd.concat(df_list, axis=1).dropna()
        if not df.empty:
            df['day_index'] = np.arange(len(df))
            df['gold_lag1'] = df['gold_spot'].shift(1)
            df['momentum'] = df['gold_spot'].diff(10)
            df['ma20'] = df['gold_spot'].rolling(window=20).mean()
            return df.dropna()
    except:
        return pd.DataFrame()
    return pd.DataFrame()

# --- 3. PROCESSING ---
df_data = get_ai_data()
thb_rate = get_exchange_rate()
thai_market_price = get_real_thai_gold()

# ตรวจสอบว่ามีข้อมูลสำหรับคำนวณไหม (ป้องกัน IndexError)
if not df_data.empty:
    current_spot = float(df_data['gold_spot'].iloc[-1])
else:
    # ถ้าดึง AI Data ไม่ได้ ให้พยายามดึง Spot ล่าสุดตัวเดียว
    try:
        current_spot = float(yf.download("GC=F", period="1d")['Close'].iloc[-1])
    except:
        current_spot = 2000.0 # ค่าสมมติฐานกรณีล่มจริง

# ถ้า Scraper ราคาสมาคมล่ม ให้ใช้สูตรคำนวณไทย 96.5% แทน
if thai_market_price == 0.0:
    thai_market_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495

# --- 4. UI DISPLAY ---
st.title("🏆 Gold Bet")
st.write(f"อัปเดต: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

m1, m2, m3 = st.columns(3)
m1.metric("ราคาสมาคมฯ (แท่ง)", f"{thai_market_price:,.0f} ฿")
m2.metric("Gold Spot (World)", f"${current_spot:,.2f}")
m3.metric("ค่าเงินบาท", f"{thb_rate:.2f} ฿/$")

# --- 5. SIDEBAR: INPUT & SAVE ---
with st.sidebar:
    st.header("📥 บันทึกรายการซื้อ")
    purity = st.selectbox("ความบริสุทธิ์", ["96.5%", "99.99%"])
    
    st.write("ระบุน้ำหนักทอง")
    c1, c2, c3 = st.columns(3)
    in_baht = c1.number_input("บาท", min_value=0, step=1)
    in_salung = c2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = c3.number_input("สตางค์", min_value=0, max_value=99)
    
    actual_cost = st.number_input("ราคารวมที่จ่ายจริง (บาท)", value=0)
    note = st.text_input("หมายเหตุ", "ซื้อสะสม")
    
    # คำนวณน้ำหนักกรัม
    unit_w = 15.244 if purity == "96.5%" else 15.16
    gram_weight = (in_baht + (in_salung * 0.25) + (in_satang * 0.01)) * unit_w
    st.info(f"น้ำหนักรวม: {gram_weight:.4f} กรัม")
    
    if st.button("💾 บันทึกลง Google Sheet"):
        sheet = init_gsheet()
        if sheet:
            # ใช้ราคาตลาด ณ ขณะนั้น (อิงตามประเภททองที่เลือก)
            current_val_per_baht = thai_market_price if purity == "96.5%" else (current_spot / 31.1035 * 15.16 * thb_rate)
            new_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                round(current_val_per_baht, 2), purity, current_spot, "Bar",
                in_baht, in_salung, in_satang, round(gram_weight, 4),
                actual_cost, note
            ]
            sheet.append_row(new_row)
            st.success("บันทึกสำเร็จ!")
            st.balloons()

# --- 6. AI PREDICTION ---
st.divider()
st.subheader("🔮 AI Future Price Prediction")

if not df_data.empty:
    features = ['day_index', 'gold_lag1', 'dxy', 'inflation_etf', 'momentum', 'ma20']
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(df_data[features], df_data['gold_spot'])

    years = st.slider("ระยะเวลาถือครอง (ปี)", 1, 10, 3)
    future_idx = df_data['day_index'].iloc[-1] + (years * 252)
    # จำลอง Scenario อนาคต
    future_X = pd.DataFrame([[
        future_idx, current_spot, df_data['dxy'].iloc[-1]*0.98, 
        df_data['inflation_etf'].iloc[-1]*1.05, 0, current_spot
    ]], columns=features)

    pred_spot = model.predict(future_X)[0]
    # แปลงเป็นราคาทองไทย 96.5%
    pred_thb = (pred_spot * 0.473 * thb_rate) * 32.148 / 28.3495
    
    st.markdown(f"### คาดการณ์ราคาใน {years} ปี: **{pred_thb:,.0f} ฿ ต่อบาททอง**")
    
    # คำนวณกำไรคาดการณ์
    if actual_cost > 0:
        total_future_value = (gram_weight / unit_w) * pred_thb
        profit = total_future_value - actual_cost
        st.write(f"💰 กำไรที่คุณจะได้: :green[{profit:,.0f} ฿] ({ (profit/actual_cost)*100:.2f}%)")
else:
    st.warning("⚠️ ข้อมูลเศรษฐกิจไม่เพียงพอสำหรับ AI Prediction ในขณะนี้")

# --- 7. PORTFOLIO HISTORY ---
sheet = init_gsheet()
if sheet:
    st.divider()
    st.subheader("📜 ประวัติการลงทุน (Google Sheet)")
    try:
        data_list = sheet.get_all_records()
        if data_list:
            df_hist = pd.DataFrame(data_list)
            st.dataframe(df_hist.tail(10), use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลในระบบ")
    except:
        st.info("กรุณาตรวจสอบหัวตารางใน Google Sheet")
