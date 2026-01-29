import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go

# ---------------------------------------------------------
# 1. CONFIG & GOOGLE SHEETS CONNECTION
# ---------------------------------------------------------
# ใส่ Link CSV ที่ได้จาก Google Sheets ของคุณที่นี่
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-dUIeddHO02aYPCD4f8Wk3_-lMBhz6dJpU8Yi4HjKvl60oEmt_hagssc8FJORHwSb2BaAMBzPRBkg/pub?output=csv"

st.set_page_config(page_title="Budget-bet Pro", layout="wide")

# ฟังก์ชันโหลดข้อมูลจาก Google Sheets
def load_portfolio_from_sheets():
    try:
        df = pd.read_csv(SHEET_URL)
        # แปลงข้อมูลเป็น Dictionary เหมือนที่ code เดิมใช้
        portfolio = {}
        for _, row in df.iterrows():
            portfolio[row['symbol']] = {
                'cost': row['cost'],
                'target': row['target'],
                'stop': row['stop']
            }
        return portfolio
    except:
        return {}

# โหลด Portfolio ทันทีเมื่อเปิดแอป
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio_from_sheets()

# ---------------------------------------------------------
# 2. CORE FUNCTIONS (ปรับปรุงป้องกันการแบน)
# ---------------------------------------------------------
def sync_data_safe():
    # ดึงราคาเหรียญหลักๆ เพื่อลดการเรียก API ทีละตัว
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
        res = requests.get(url, timeout=10).json()
        symbols = [c['symbol'].upper() for c in res]
    except:
        symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

    try:
        # ใช้ดึงค่าเงินบาทครั้งเดียว
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
        st.session_state.master_data['EXCHANGE_RATE'] = usd_thb
    except:
        usd_thb = 35.0

    new_data = {}
    with st.status("📡 กำลังดึงข้อมูลตลาดอย่างปลอดภัย...") as status:
        # แบ่งกลุ่มดึงข้อมูล (Batch Download) เพื่อไม่ให้ API ของ Yahoo สงสัย
        # ดึงครั้งละหลายๆ ตัวในคำสั่งเดียว ช่วยลดความเสี่ยงโดนแบนได้ดีที่สุด
        tickers = [f"{s}-USD" for s in symbols]
        try:
            # ดึงข้อมูลรวดเดียว
            all_data = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False)
            
            for s in symbols:
                try:
                    df = all_data[f"{s}-USD"]
                    if not df.empty:
                        last_p = float(df['Close'].iloc[-1])
                        new_data[s] = {
                            'price': last_p * usd_thb,
                            'base_price': float(df['Close'].mean()) * usd_thb,
                            'df': df.ffill(),
                            'rank': symbols.index(s) + 1
                        }
                except: continue
        except Exception as e:
            st.error(f"Error fetching data: {e}")
        
        st.session_state.master_data = new_data
        status.update(label="Sync สำเร็จ!", state="complete")

# ---------------------------------------------------------
# 3. กลไกการ Alert (เบื้องต้นในหน้าจอ)
# ---------------------------------------------------------
def check_alerts(symbol, current_price, m):
    # คำนวณ % ปัจจุบัน
    profit_pct = ((current_price - m['cost']) / m['cost']) * 100
    
    # แจ้งเตือนในหน้าจอ
    if profit_pct >= m['target']:
        st.toast(f"🚀 {symbol} ถึงเป้ากำไรแล้ว! (+{profit_pct:.2f}%)", icon="🔥")
    elif profit_pct <= -m['stop']:
        st.toast(f"⚠️ {symbol} ถึงจุดคัดขาดทุน! ({profit_pct:.2f}%)", icon="🛑")

# (ส่วนที่เหลือของ Main UI คุณสามารถใช้โค้ดเดิมได้เลย)
