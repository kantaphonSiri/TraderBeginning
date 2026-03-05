import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

# --- 1. CONFIG & SETTINGS ---
st.set_page_config(page_title="Gold Bet", layout="wide")

# ฟังก์ชันดึงข้อมูลแบบปลอดภัย (ดึงเฉพาะตัวเลข)
def safe_get_value(data):
    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        return 0.0
    if isinstance(data, (pd.Series, pd.DataFrame)):
        return float(data.values.flatten()[0])
    return float(data)

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        data = yf.download("THB=X", period="1d", progress=False)['Close']
        return safe_get_value(data)
    except:
        return 35.5

@st.cache_data(ttl=3600)
def get_combined_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    
    tickers = {"gold_spot": "GC=F", "dxy": "DX-Y.NYB", "inflation_etf": "TIP"}
    df_list = []
    
    for name, sym in tickers.items():
        data = yf.download(sym, start=start_date, end=end_date, progress=False)
        if not data.empty:
            # ดึงคอลัมน์ Close โดยไม่สนว่าจะเป็น Multi-index หรือไม่
            close_col = data['Close']
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            df_list.append(pd.DataFrame({name: close_col}))
    
    if not df_list:
        return pd.DataFrame()

    df = pd.concat(df_list, axis=1).dropna()
    df['day_index'] = np.arange(len(df))
    df['gold_lag1'] = df['gold_spot'].shift(1)
    return df.dropna()

# --- 2. PREPARE DATA ---
thb_rate = get_exchange_rate()
df_data = get_combined_data()

if df_data.empty:
    st.error("ไม่สามารถดึงข้อมูลเศรษฐกิจได้ กรุณารีเฟรชหน้าจออีกครั้ง")
    st.stop()

current_spot = safe_get_value(df_data['gold_spot'].iloc[-1])
# สูตรแปลงราคาทองไทย 96.5%
current_thai_price = (current_spot * 0.473 * thb_rate) * 32.148 / 28.3495

# --- 3. UI: DASHBOARD ---
st.title("Gold Bet")
st.write("พยากรณ์ราคาทองคำด้วยปัจจัยเศรษฐกิจโลก (ดอลลาร์ & เงินเฟ้อ)")

col_p1, col_p2, col_p3 = st.columns(3)
col_p1.metric("ราคาทองไทยปัจจุบัน", f"{current_thai_price:,.0f} ฿")
col_p2.metric("Gold Spot (World)", f"${current_spot:,.2f}")
col_p3.metric("ค่าเงินบาท", f"{thb_rate:.2f} ฿/$")

# --- 4. BACKTESTING (ตรวจสอบความแม่นยำ) ---
st.divider()
st.subheader("📊 ตรวจสอบความแม่นยำ (Backtesting)")
st.caption("AI ลองทายราคาย้อนหลัง 6 เดือน เพื่อพิสูจน์ความแม่นยำ")

test_size = 120
train_df = df_data[:-test_size]
test_df = df_data[-test_size:].copy()

# ใช้ปัจจัยเศรษฐกิจในการฝึกสอน
features = ['day_index', 'gold_lag1', 'dxy', 'inflation_etf']
back_model = RandomForestRegressor(n_estimators=100, random_state=42)
back_model.fit(train_df[features], train_df['gold_spot'])

# ทำนายและแปลงเป็นเงินบาท
test_df['pred_spot'] = back_model.predict(test_df[features])
test_df['actual_thb'] = (test_df['gold_spot'] * 0.473 * thb_rate) * 32.148 / 28.3495
test_df['pred_thb'] = (test_df['pred_spot'] * 0.473 * thb_rate) * 32.148 / 28.3495

mape = np.mean(np.abs((test_df['actual_thb'] - test_df['pred_thb']) / test_df['actual_thb'])) * 100
accuracy = 100 - mape

fig = go.Figure()
fig.add_trace(go.Scatter(x=test_df.index, y=test_df['actual_thb'], name="ราคาจริง", line=dict(color='#FFD700', width=2)))
fig.add_trace(go.Scatter(x=test_df.index, y=test_df['pred_thb'], name="AI ทำนาย", line=dict(color='#00FFFF', dash='dash')))
fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(fig, use_container_width=True)

st.success(f"🎯 ความแม่นยำในการวิเคราะห์: **{accuracy:.2f}%**")

# --- 5. FUTURE PREDICTION ---
st.divider()
st.subheader("🔮 พยากรณ์กำไรในอนาคต")

c_in1, c_in2 = st.columns(2)
with c_in1:
    user_price = st.number_input("ราคาที่คุณซื้อมา (บาทละ)", value=int(current_thai_price))
    years = st.slider("ระยะเวลาที่ต้องการถือครอง (ปี)", 1, 10, 3)

# ฝึกสอนโมเดลด้วยข้อมูลทั้งหมด
full_model = RandomForestRegressor(n_estimators=100, random_state=42)
full_model.fit(df_data[features], df_data['gold_spot'])

# จำลองอนาคต: ดอลลาร์อ่อนค่า 5%, เงินเฟ้อสะสม 6% (ในระยะ 3 ปี)
future_idx = df_data['day_index'].iloc[-1] + (years * 252)
future_X = pd.DataFrame([[future_idx, current_spot, df_data['dxy'].iloc[-1]*0.95, df_data['inflation_etf'].iloc[-1]*1.06]], 
                        columns=features)

pred_future_spot = safe_get_value(full_model.predict(future_X))
pred_future_thb = (pred_future_spot * 0.473 * thb_rate) * 32.148 / 28.3495
profit = pred_future_thb - user_price

with c_in2:
    st.markdown(f"### ผลวิเคราะห์อีก {years} ปี")
    st.title(f"{pred_future_thb:,.0f} ฿")
    if profit > 0:
        st.subheader(f"📈 กำไร: :green[{profit:,.0f} ฿] ({ (profit/user_price)*100:.2f}%)")
    else:
        st.subheader(f"📉 ขาดทุน: :red[{profit:,.0f} ฿]")

st.info("💡 **กลยุทธ์:** หากค่าความแม่นยำสูงกว่า 90% คุณสามารถใช้ตัวเลขนี้วางแผนการออมทองในระยะยาวได้ดีขึ้นครับ")
