import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="Gold Bet", layout="wide")

# ฟังก์ชันเชื่อมต่อ Google Sheet แบบปลอดภัย
def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # ค้นหาไฟล์ชื่อ gold-bet และแท็บชื่อ data_storage
        return client.open("gold-bet").worksheet("data_storage")
    except Exception as e:
        st.error(f"⚠️ การเชื่อมต่อล้มเหลว: {e}")
        return None

# ฟังก์ชันดึงค่าเงินบาทล่าสุด
def get_exchange_rate():
    try:
        data = yf.download("THB=X", period="1d", progress=False)['Close']
        val = float(data.values.flatten()[0])
        # ตรวจสอบค่าเงินบาทให้อยู่ในกรอบที่เป็นจริง (ป้องกันข้อมูลพุ่งผิดปกติ)
        return val if 30 < val < 40 else 35.0
    except:
        return 35.0

# ฟังก์ชันคำนวณน้ำหนักกรัม
def convert_to_gram(purity, baht, salung, satang):
    base_weight = 15.244 if purity == "96.5%" else 15.16
    total_baht = baht + (salung * 0.25) + (satang * 0.01)
    return total_baht * base_weight

# --- 2. AI ENGINE (ปรับจูน Feature ให้แม่นยำขึ้น) ---
@st.cache_data(ttl=3600)
def get_ai_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    tickers = {"gold_spot": "GC=F", "dxy": "DX-Y.NYB", "inflation_etf": "TIP"}
    df_list = []
    
    for name, sym in tickers.items():
        data = yf.download(sym, start=start_date, end=end_date, progress=False)['Close']
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]
        df_list.append(pd.DataFrame({name: data}))
    
    df = pd.concat(df_list, axis=1).dropna()
    
    # Feature Engineering สำหรับ AI
    df['day_index'] = np.arange(len(df))
    df['gold_lag1'] = df['gold_spot'].shift(1)
    df['momentum'] = df['gold_spot'].diff(10)
    df['ma20'] = df['gold_spot'].rolling(window=20).mean()
    return df.dropna()

# --- 3. UI & INPUT PROCESSING ---
df_data = get_ai_data()
thb_rate = get_exchange_rate()

# ป้องกันข้อมูล Spot ดีดสูงผิดปกติจาก yfinance
raw_spot = float(df_data['gold_spot'].iloc[-1])
current_spot = raw_spot if raw_spot < 3500 else float(df_data['gold_spot'].median())

st.title("Gold Bet")
st.write(f"ข้อมูลล่าสุดเมื่อ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Sidebar: บันทึกพอร์ต
with st.sidebar:
    st.header("📥 บันทึกการซื้อจริง")
    p_type = st.selectbox("ความบริสุทธิ์", ["96.5%", "99.99%"])
    
    st.write("ระบุน้ำหนักทอง")
    c1, c2, c3 = st.columns(3)
    in_baht = c1.number_input("บาท", min_value=0, step=1)
    in_salung = c2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = c3.number_input("สตางค์", min_value=0, max_value=99)
    
    actual_cost = st.number_input("ราคารวมที่จ่ายจริง (บาท)", value=0)
    user_note = st.text_input("หมายเหตุ", "ซื้อสะสม")
    
    gram_weight = convert_to_gram(p_type, in_baht, in_salung, in_satang)
    st.info(f"น้ำหนักรวม: {gram_weight:.4f} กรัม")
    
    if st.button("💾 บันทึก"):
        sheet = init_gsheet()
        if sheet:
            # คำนวณราคาตลาด ณ ขณะนั้น
            if p_type == "96.5%":
                m_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495
            else:
                m_price = (current_spot / 31.1035) * 15.244 * thb_rate
                
            new_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                round(m_price, 2),
                p_type,
                current_spot,
                "Gold Bar",
                in_baht,
                in_salung,
                in_satang,
                round(gram_weight, 4),
                actual_cost,
                user_note
            ]
            sheet.append_row(new_row)
            st.success("✅ บันทึกสำเร็จ!")
            st.balloons()

# --- 4. DASHBOARD DISPLAY ---
# คำนวณราคาไทยปัจจุบันเพื่อโชว์บนหน้าจอ
if p_type == "96.5%":
    market_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495
else:
    market_price = (current_spot / 31.1035) * 15.244 * thb_rate

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric(f"ทองคำแท่ง {p_type}", f"{market_price:,.0f} ฿")
col_m2.metric("Gold Spot", f"${current_spot:,.2f}")
col_m3.metric("ค่าเงินบาท", f"{thb_rate:.2f} ฿/$")

# --- 5. AI PREDICTION ---
st.divider()
st.subheader("🔮 AI Prediction (ทำนายอนาคตต่อ 1 บาททอง)")

features = ['day_index', 'gold_lag1', 'dxy', 'inflation_etf', 'momentum', 'ma20']
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(df_data[features], df_data['gold_spot'])

years_to_hold = st.slider("ระยะเวลาที่คาดว่าจะถือครอง (ปี)", 1, 10, 3)
future_days = years_to_hold * 252
last_idx = df_data['day_index'].iloc[-1]

# สร้างสภาพแวดล้อมจำลอง (Scenario)
future_X = pd.DataFrame([[
    last_idx + future_days, current_spot, 
    df_data['dxy'].iloc[-1] * 0.97, # จำลองดอลลาร์อ่อนค่า 3%
    df_data['inflation_etf'].iloc[-1] * 1.05, # จำลองเงินเฟ้อเพิ่ม 5%
    0, current_spot
]], columns=features)

pred_spot_future = model.predict(future_X)[0]

# แปลงผลการทำนายกลับเป็นราคาไทย
if p_type == "96.5%":
    pred_future_thb = (pred_spot_future * 0.473 * thb_rate) * 32.148 / 28.3495
else:
    pred_future_thb = (pred_spot_future / 31.1035) * 15.244 * thb_rate

st.markdown(f"### ราคาพยากรณ์ในอีก {years_to_hold} ปี: **{pred_future_thb:,.0f} ฿**")

# สรุปกำไรตามน้ำหนักที่ User ถืออยู่ปัจจุบัน
total_future_val = (gram_weight / (15.244 if p_type == "96.5%" else 15.16)) * pred_future_thb
profit_amt = total_future_val - actual_cost

if actual_cost > 0:
    st.subheader(f"💰 กำไรคาดการณ์: :green[{profit_amt:,.0f} ฿] ({ (profit_amt/actual_cost)*100:.2f}%)")

# --- 6. HISTORY VIEW (Google Sheet) ---
st.divider()
st.subheader("📜 ประวัติการลงทุน")
sheet = init_gsheet()
if sheet:
    data_list = sheet.get_all_records()
    if data_list:
        df_history = pd.DataFrame(data_list)
        st.dataframe(df_history.tail(10), use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลประวัติการลงทุน")
