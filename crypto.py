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

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Gold Bet", layout="wide")

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("gold-bet").worksheet("data_storage")
    except Exception as e:
        return None

# --- 2. REAL-TIME THAI GOLD SCRAPER ---
def get_real_thai_gold():
    try:
        url = "https://www.goldtraders.or.th/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # เจาะจงดึงราคาทองแท่งขายออก (96.5%) จาก ID ของสมาคมฯ
        sell_price_text = soup.find(id="DetailPlace_uc_goldprices1_lblBLSell").text
        return float(sell_price_text.replace(',', ''))
    except Exception as e:
        # หากดึงไม่ได้ ให้คำนวณจาก Spot เป็นแผนสำรอง
        return 0.0

def get_exchange_rate():
    data = yf.download("THB=X", period="1d", progress=False)['Close']
    return float(data.values.flatten()[0])

def convert_to_gram(purity, baht, salung, satang):
    base_weight = 15.244 if purity == "96.5%" else 15.16
    total_baht = baht + (salung * 0.25) + (satang * 0.01)
    return total_baht * base_weight

# --- 3. AI & DATA ENGINE ---
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
    df['day_index'] = np.arange(len(df))
    df['gold_lag1'] = df['gold_spot'].shift(1)
    df['momentum'] = df['gold_spot'].diff(10)
    df['ma20'] = df['gold_spot'].rolling(window=20).mean()
    return df.dropna()

# ดึงข้อมูลเริ่มต้น
df_data = get_ai_data()
thb_rate = get_exchange_rate()
current_spot = float(df_data['gold_spot'].iloc[-1])
thai_market_price = get_real_thai_gold()

# กรณี Scraper ดึงค่าไม่ได้ ให้ใช้การคำนวณแทน
if thai_market_price == 0.0:
    thai_market_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495

# --- 4. UI DISPLAY ---
st.title("Gold Bet")

col1, col2, col3 = st.columns(3)
col1.metric("ราคาสมาคมฯ (ทองแท่ง)", f"{thai_market_price:,.0f} ฿")
col2.metric("Gold Spot (World)", f"${current_spot:,.2f}")
col3.metric("ค่าเงินบาท", f"{thb_rate:.2f} ฿/$")

# --- 5. SIDEBAR: RECORD ---
with st.sidebar:
    st.header("📥 บันทึกการซื้อ")
    purity = st.selectbox("ความบริสุทธิ์", ["96.5%", "99.99%"])
    
    st.write("ระบุน้ำหนักทอง")
    c1, c2, c3 = st.columns(3)
    in_baht = c1.number_input("บาท", min_value=0, step=1)
    in_salung = c2.number_input("สลึง", min_value=0, max_value=3)
    in_satang = c3.number_input("สตางค์", min_value=0, max_value=99)
    
    actual_cost = st.number_input("ราคาที่ซื้อจริง (บาทรวม)", value=0)
    note = st.text_input("หมายเหตุ", "ซื้อสะสม")
    
    gram_weight = convert_to_gram(purity, in_baht, in_salung, in_satang)
    st.info(f"น้ำหนักรวม: {gram_weight:.4f} กรัม")
    
    if st.button("💾 บันทึกลง Google Sheet"):
        sheet = init_gsheet()
        if sheet:
            new_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                thai_market_price, purity, current_spot, "Gold Bar",
                in_baht, in_salung, in_satang, round(gram_weight, 4),
                actual_cost, note
            ]
            sheet.append_row(new_row)
            st.success("บันทึกสำเร็จ!")
            st.balloons()

# --- 6. AI PREDICTION ---
st.divider()
st.subheader("🔮 AI Prediction")

features = ['day_index', 'gold_lag1', 'dxy', 'inflation_etf', 'momentum', 'ma20']
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(df_data[features], df_data['gold_spot'])

years = st.slider("ระยะเวลาถือครอง (ปี)", 1, 10, 3)
future_idx = df_data['day_index'].iloc[-1] + (years * 252)
future_X = pd.DataFrame([[future_idx, current_spot, df_data['dxy'].iloc[-1]*0.98, df_data['inflation_etf'].iloc[-1]*1.05, 0, current_spot]], columns=features)

pred_spot = model.predict(future_X)[0]

# แปลงผลทำนายเป็นราคาไทย 96.5%
pred_future_baht = (pred_spot * 0.473 * thb_rate) * 32.148 / 28.3495
st.markdown(f"### ราคาคาดการณ์ในอีก {years} ปี: **{pred_future_baht:,.0f} ฿**")

# สรุปกำไรจากน้ำหนักที่กรอก
total_future_value = (gram_weight / (15.244 if purity == "96.5%" else 15.16)) * pred_future_baht
total_profit = total_future_value - actual_cost

if actual_cost > 0:
    st.subheader(f"💰 กำไรคาดการณ์ของคุณ: :green[{total_profit:,.0f} ฿]")

# --- 7. HISTORY ---
sheet = init_gsheet()
if sheet:
    st.divider()
    st.subheader("📜 ประวัติการลงทุนของคุณ")
    data = pd.DataFrame(sheet.get_all_records())
    if not data.empty:
        st.dataframe(data.tail(10), use_container_width=True)
