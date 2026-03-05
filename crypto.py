import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Gold Bet", layout="wide")

# ฟังก์ชันเชื่อมต่อ Google Sheet
def init_gsheet():
    try:
        # ดึงข้อมูลจาก Streamlit Secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        # แก้ไขปัญหาเครื่องหมายขึ้นบรรทัดใหม่ใน Private Key
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # เปิดไฟล์ชื่อ gold-bet และแถบชื่อ data_storage
        return client.open("gold-bet").worksheet("data_storage")
    except Exception as e:
        st.error(f"การเชื่อมต่อ Google Sheet ล้มเหลว: {e}")
        return None

def get_exchange_rate():
    data = yf.download("THB=X", period="1d", progress=False)['Close']
    return float(data.values.flatten()[0])

def convert_to_gram(purity, baht, salung, satang):
    base_weight = 15.244 if purity == "96.5%" else 15.16
    total_baht = baht + (salung * 0.25) + (satang * 0.01)
    return total_baht * base_weight

# --- 2. AI ENGINE (ปรับปรุงให้แม่นยำขึ้น) ---
@st.cache_data(ttl=3600)
def get_ai_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    tickers = {"gold_spot": "GC=F", "dxy": "DX-Y.NYB", "inflation_etf": "TIP"}
    df_list = []
    for name, sym in tickers.items():
        data = yf.download(sym, start=start_date, end=end_date, progress=False)['Close']
        if isinstance(data, pd.DataFrame): data = data.iloc[:, 0]
        df_list.append(pd.DataFrame({name: data}))
    df = pd.concat(df_list, axis=1).dropna()
    
    # เพิ่ม Features เพื่อให้ AI ทายได้แม่นยำขึ้น (ไม่แบนราบ)
    df['day_index'] = np.arange(len(df))
    df['gold_lag1'] = df['gold_spot'].shift(1)
    df['momentum'] = df['gold_spot'].diff(10) # ดูแรงเหวี่ยง 10 วัน
    df['ma20'] = df['gold_spot'].rolling(window=20).mean() # เส้นค่าเฉลี่ย 20 วัน
    return df.dropna()

# --- 3. UI & INPUT ---
df_data = get_ai_data()
thb_rate = get_exchange_rate()
current_spot = float(df_data['gold_spot'].iloc[-1])

st.title("🏆 Gold Bet")

with st.sidebar:
    st.header("📥 บันทึกการซื้อ")
    purity = st.selectbox("ความบริสุทธิ์", ["96.5%", "99.99%"])
    
    st.write("ระบุน้ำหนักทอง")
    c1, c2, c3 = st.columns(3)
    in_baht = c1.number_input("บาท", min_value=0, step=1)
    in_salung = c2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = c3.number_input("สตางค์", min_value=0, max_value=99)
    
    total_cost = st.number_input("ราคาที่ซื้อจริง (บาทรวม)", value=0)
    note = st.text_input("หมายเหตุ", "ซื้อสะสม")
    
    gram_weight = convert_to_gram(purity, in_baht, in_salung, in_satang)
    st.info(f"น้ำหนักรวม: {gram_weight:.4f} กรัม")
    
    if st.button("💾 บันทึกลง Google Sheet"):
        sheet = init_gsheet()
        if sheet:
            # เตรียมข้อมูลตามหัวตารางในภาพของคุณ
            # Date, Market_Price, Purity, Spot, Type, Bath, Salung, Satang, Total_Gram, Total_Cost, Note
            # คำนวณราคาทองไทย ณ วันที่บันทึก
            if purity == "96.5%":
                m_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495
            else:
                m_price = (current_spot / 31.1035) * 15.16 * thb_rate
            
            new_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                round(m_price, 2),
                purity,
                current_spot,
                "Gold Bar",
                in_baht,
                in_salung,
                in_satang,
                round(gram_weight, 4),
                total_cost,
                note
            ]
            sheet.append_row(new_row)
            st.success("บันทึกข้อมูลสำเร็จแล้ว!")
            st.balloons()

# --- 4. PREDICTION & PORTFOLIO ---
st.subheader("🔮 AI Prediction (ทำนายราคาต่อ 1 บาททอง)")

if purity == "96.5%":
    price_per_baht = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495
else:
    price_per_baht = (current_spot / 31.1035) * 15.16 * thb_rate

st.metric(f"ราคาทอง {purity} วันนี้ (ต่อบาท)", f"{price_per_baht:,.0f} ฿", f"Spot: ${current_spot}")

features = ['day_index', 'gold_lag1', 'dxy', 'inflation_etf', 'momentum', 'ma20']
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(df_data[features], df_data['gold_spot'])

years = st.slider("ระยะเวลาถือครอง (ปี)", 1, 10, 3)
future_idx = df_data['day_index'].iloc[-1] + (years * 252)

# สร้างข้อมูลอนาคตแบบ Dynamic (เลียนแบบ Momentum ขาขึ้น)
future_X = pd.DataFrame([[
    future_idx, current_spot, df_data['dxy'].iloc[-1]*0.98, 
    df_data['inflation_etf'].iloc[-1]*1.05, 0, current_spot
]], columns=features)

pred_spot = model.predict(future_X)[0]

if purity == "96.5%":
    pred_future_baht = (pred_spot * 0.473 * thb_rate) * 32.148 / 28.3495
else:
    pred_future_baht = (pred_spot / 31.1035) * 15.16 * thb_rate

st.markdown(f"### ราคาคาดการณ์ในอีก {years} ปี: **{pred_future_baht:,.0f} ฿**")

# สรุปกำไรตามน้ำหนักที่กำลังบันทึก
total_future_value = (gram_weight / (15.244 if purity == "96.5%" else 15.16)) * pred_future_baht
total_profit = total_future_value - total_cost

if total_cost > 0:
    st.subheader(f"💰 กำไรคาดการณ์ของคุณ: :green[{total_profit:,.0f} ฿] ({ (total_profit/total_cost)*100:.2f}%)")

# แสดงประวัติจาก Google Sheet
st.divider()
st.subheader("📜 ประวัติการลงทุนล่าสุด")
sheet = init_gsheet()
if sheet:
    data = pd.DataFrame(sheet.get_all_records())
    if not data.empty:
        st.dataframe(data.tail(10), use_container_width=True)

