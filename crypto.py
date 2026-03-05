import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import gspread
from sklearn.ensemble import RandomForestRegressor
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- 1. INITIAL SETUP & SECRETS ---
st.set_page_config(page_title="Gold Bet", layout="wide")

def init_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            creds_dict, 
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("gold-bet").worksheet("data_storage")
    except:
        return None

# --- 2. DATA ENGINE (AI LEARNING) ---
@st.cache_data(ttl=3600)
def get_ai_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    
    # ดึงข้อมูลปัจจัยโลก
    tickers = {"gold_spot": "GC=F", "dxy": "DX-Y.NYB", "inflation_etf": "TIP", "thb": "THB=X"}
    df_list = []
    for name, sym in tickers.items():
        data = yf.download(sym, start=start_date, end=end_date, progress=False)['Close']
        if isinstance(data, pd.DataFrame): data = data.iloc[:, 0]
        df_list.append(pd.DataFrame({name: data}))
    
    df = pd.concat(df_list, axis=1).dropna()
    
    # --- จุดที่ทำให้ AI แม่นขึ้น (Feature Engineering) ---
    df['day_index'] = np.arange(len(df))
    df['gold_lag1'] = df['gold_spot'].shift(1)
    df['momentum'] = df['gold_spot'].diff(10) # แรงเหวี่ยง 10 วัน
    df['ma20'] = df['gold_spot'].rolling(window=20).mean() # แนวโน้ม 20 วัน
    return df.dropna()

# --- 3. PROCESSING ---
df_data = get_ai_data()
thb_rate = float(df_data['thb'].iloc[-1])
current_spot = float(df_data['gold_spot'].iloc[-1])
# คำนวณราคาทองไทย (96.5%)
current_thai_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495

# --- 4. DASHBOARD UI ---
st.title("Gold Bet")
st.write(f"อัปเดตล่าสุด: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

m1, m2, m3 = st.columns(3)
m1.metric("ทองไทย (ประมาณ)", f"{current_thai_price:,.0f} ฿")
m2.metric("Gold Spot", f"${current_spot:,.2f}")
m3.metric("ค่าเงินบาท", f"{thb_rate:.2f} ฿/$")

# --- 5. BACKTESTING GRAPH ---
st.subheader("📊 ตรวจสอบสมอง AI (Backtesting)")
test_size = 100
train_df = df_data[:-test_size]
test_df = df_data[-test_size:].copy()

features = ['day_index', 'gold_lag1', 'dxy', 'inflation_etf', 'momentum', 'ma20']
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(train_df[features], train_df['gold_spot'])

test_df['pred_spot'] = model.predict(test_df[features])
test_df['actual_thb'] = (test_df['gold_spot'] * 0.473 * thb_rate) * 32.148 / 28.3495
test_df['pred_thb'] = (test_df['pred_spot'] * 0.473 * thb_rate) * 32.148 / 28.3495

fig = go.Figure()
fig.add_trace(go.Scatter(x=test_df.index, y=test_df['actual_thb'], name="ราคาจริง", line=dict(color='gold')))
fig.add_trace(go.Scatter(x=test_df.index, y=test_df['pred_thb'], name="AI ทำนาย", line=dict(color='cyan', dash='dash')))
st.plotly_chart(fig, use_container_width=True)

# --- 6. SIDEBAR: RECORD & PREDICT ---
with st.sidebar:
    st.header("📥 บันทึกการซื้อ & พยากรณ์")
    
    # ส่วนพยากรณ์
    st.subheader("🔮 AI Predictor")
    years = st.slider("อีกกี่ปีจะขาย?", 1, 10, 3)
    future_idx = df_data['day_index'].iloc[-1] + (years * 252)
    # จำลองอนาคต (เพิ่ม Momentum และ MA เข้าไปในอนาคต)
    future_X = pd.DataFrame([[
        future_idx, current_spot, df_data['dxy'].iloc[-1]*0.98, 
        df_data['inflation_etf'].iloc[-1]*1.05, 0, current_spot
    ]], columns=features)
    
    pred_future = model.predict(future_X)[0]
    pred_thb_future = (pred_future * 0.473 * thb_rate) * 32.148 / 28.3495
    st.write(f"คาดการณ์ราคาใน {years} ปี:")
    st.title(f"{pred_thb_future:,.0f} ฿")
    
    st.divider()
    
    # ส่วนบันทึก Google Sheet
    st.subheader("💾 บันทึกพอร์ต")
    buy_price = st.number_input("ราคาที่ซื้อจริง", value=int(current_thai_price))
    baht = st.number_input("กี่บาททอง", min_value=1)
    if st.button("บันทึกลง Google Sheet"):
        sheet = init_gsheet()
        if sheet:
            # เตรียมข้อมูลลง Sheet
            row = [datetime.now().strftime("%Y-%m-%d"), buy_price, "96.5%", current_spot, "Bar", baht, 0, 0, baht*15.244, buy_price*baht, "AI Predicted"]
            sheet.append_row(row)
            st.success("บันทึกเรียบร้อย!")
        else:
            st.error("เชื่อมต่อ Google Sheet ไม่ได้")

# --- 7. PORTFOLIO VIEW ---
sheet = init_gsheet()
if sheet:
    st.subheader("📜 ประวัติการลงทุนของคุณ")
    data = pd.DataFrame(sheet.get_all_records())
    if not data.empty:
        data['Current_Val'] = (data['Total_Gram'] / 15.244) * current_thai_price
        data['PnL'] = data['Current_Val'] - data['Total_Cost']
        st.dataframe(data.style.format({"PnL": "{:,.2f}"}), use_container_width=True)
        st.metric("กำไร/ขาดทุนรวม", f"{data['PnL'].sum():,.2f} ฿")
