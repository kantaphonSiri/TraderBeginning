import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

# --- 1. CONFIG & SETTINGS ---
st.set_page_config(page_title="Gold Bet", layout="wide")

# ฟังก์ชันดึงอัตราแลกเปลี่ยนปัจจุบัน
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        thb_data = yf.download("THB=X", period="1d")
        return thb_data['Close'].iloc[-1]
    except:
        return 35.5 # Fallback

# --- 2. DATA FETCHING (AI & ECONOMIC) ---
@st.cache_data(ttl=3600)
def get_combined_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    
    # ดัชนี: ทองคำ, ดอลลาร์ (DXY), เงินเฟ้อ (TIP)
    tickers = {"gold_spot": "GC=F", "dxy": "DX-Y.NYB", "inflation_etf": "TIP"}
    df_list = []
    
    for name, sym in tickers.items():
        d = yf.download(sym, start=start_date, end=end_date)['Close']
        df_list.append(pd.DataFrame({name: d}))
    
    df = pd.concat(df_list, axis=1).dropna()
    df['day_index'] = np.arange(len(df))
    df['gold_lag1'] = df['gold_spot'].shift(1)
    return df.dropna()

# --- 3. UI: HEADER & CURRENT PRICE ---
thb_rate = get_exchange_rate()
df_data = get_combined_data()
current_spot = df_data['gold_spot'].iloc[-1]

# สูตรแปลง Spot เป็นทองไทย 96.5% (โดยประมาณ)
# (Spot * 0.473 * THB) * 32.148 / 28.3495 
current_thai_price = round((current_spot * 0.473 * thb_rate) * 32.148 / 28.3495, -1)

st.title("Gold Bet")
st.write(f"วิเคราะห์โดยอิงจาก: **ค่าเงินดอลลาร์ (DXY)** และ **อัตราเงินเฟ้อสหรัฐฯ**")

col_p1, col_p2, col_p3 = st.columns(3)
col_p1.metric("ราคาทองไทยปัจจุบัน (ประมาณ)", f"{current_thai_price:,.0f} ฿")
col_p2.metric("Gold Spot", f"${current_spot:,.2f}")
col_p3.metric("ค่าเงินบาท", f"{thb_rate:.2f} ฿/$")

# --- 4. BACKTESTING (ตรวจสอบความแม่นยำ) ---
st.divider()
st.subheader("📊 ส่วนตรวจสอบความแม่นยำของ AI (Backtesting)")
st.write("ลองให้ AI ทายราคาย้อนหลัง 6 เดือนที่ผ่านมา เพื่อดูว่าทายแม่นแค่ไหน")

# เตรียมข้อมูล Backtest
test_size = 120
train_df = df_data[:-test_size]
test_df = df_data[-test_size:].copy()

back_model = RandomForestRegressor(n_estimators=100, random_state=42)
back_model.fit(train_df[['day_index', 'gold_lag1', 'dxy', 'inflation_etf']], train_df['gold_spot'])

# ทำนายและแปลงเป็นเงินบาท
test_df['actual_thb'] = (test_df['gold_spot'] * 0.473 * thb_rate) * 32.148 / 28.3495
test_df['pred_thb'] = (back_model.predict(test_df[['day_index', 'gold_lag1', 'dxy', 'inflation_etf']]) * 0.473 * thb_rate) * 32.148 / 28.3495

# คำนวณความแม่นยำ
mape = np.mean(np.abs((test_df['actual_thb'] - test_df['pred_thb']) / test_df['actual_thb'])) * 100
accuracy = 100 - mape

fig = go.Figure()
fig.add_trace(go.Scatter(x=test_df.index, y=test_df['actual_thb'], name="ราคาจริง (บาท)", line=dict(color='#FFD700')))
fig.add_trace(go.Scatter(x=test_df.index, y=test_df['pred_thb'], name="AI ทำนาย (บาท)", line=dict(color='#00FFFF', dash='dash')))
fig.update_layout(template="plotly_dark", height=400)
st.plotly_chart(fig, use_container_width=True)

st.success(f"🎯 ความแม่นยำของระบบปัจจุบัน: **{accuracy:.2f}%** (คลาดเคลื่อนประมาณ {mape:.2f}%)")

# --- 5. PREDICTION (พยากรณ์อนาคต) ---
st.divider()
st.subheader("🔮 คำนวณโอกาสทำกำไรในอนาคต")

col_in1, col_in2 = st.columns(2)
with col_in1:
    user_buy_price = st.number_input("คุณซื้อมาในราคาเท่าไหร่? (บาทละ)", value=int(current_thai_price))
    hold_years = st.slider("อีกกี่ปีถึงจะขาย?", 1, 10, 3)

# วิเคราะห์อนาคต
full_model = RandomForestRegressor(n_estimators=100, random_state=42)
full_model.fit(df_data[['day_index', 'gold_lag1', 'dxy', 'inflation_etf']], df_data['gold_spot'])

# สมมติฐานอนาคต (เงินเฟ้อโตขึ้น ดอลลาร์อ่อนลงเล็กน้อย)
future_idx = df_data['day_index'].iloc[-1] + (hold_years * 252)
future_X = pd.DataFrame([[future_idx, current_spot, df_data['dxy'].iloc[-1]*0.95, df_data['inflation_etf'].iloc[-1]*1.06]], 
                        columns=['day_index', 'gold_lag1', 'dxy', 'inflation_etf'])

pred_spot_future = full_model.predict(future_X)[0]
pred_thb_future = round((pred_spot_future * 0.473 * thb_rate) * 32.148 / 28.3495, -1)
profit = pred_thb_future - user_buy_price

with col_in2:
    st.write("### 📜 ผลพยากรณ์")
    st.write(f"ในอีก **{hold_years} ปี** ข้างหน้า AI คาดว่าราคาทองจะเป็น:")
    st.title(f"{pred_thb_future:,.0f} ฿")
    if profit > 0:
        st.write(f"กำไรคาดการณ์: :green[{profit:,.0f} บาท] ({ (profit/user_buy_price)*100:.2f}%)")
    else:
        st.write(f"ขาดทุนคาดการณ์: :red[{profit:,.0f} บาท]")

# --- 6. ADVICE ---
st.divider()
st.info(f"""
💡 **คำแนะนำจาก AI:** - ทองคำมักชนะเงินเฟ้อในระยะยาว (3 ปีขึ้นไป) 
- หากดัชนีดอลลาร์ (DXY) ลดลง จะเป็นแรงส่งให้ราคาทองในพอร์ตคุณพุ่งสูงขึ้น 
- ความแม่นยำ {accuracy:.2f}% หมายความว่า AI ตัวนี้เข้าใจทิศทางเศรษฐกิจไทยและโลกได้ค่อนข้างดีครับ
""")
