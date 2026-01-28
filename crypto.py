import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ------------------------
# 0. SETUP & MEMORY
# ------------------------
st.set_page_config(page_title="Smooth Trading Dashboard", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {} # เก็บข้อมูลแผนการเทรด

# ฟังก์ชันดึงราคาและทำความสะอาดข้อมูล (Data Cleaning)
def get_clean_data(symbol):
    try:
        # ดึงข้อมูล 7 วันล่าสุดเพื่อให้เห็นเทรนด์ต่อเนื่อง
        df = yf.download(f"{symbol}-USD", period="7d", interval="15m", progress=False)
        if df.empty: return None
        
        # ลบข้อมูลที่ซ้ำกัน (Drop Duplicates)
        df = df[~df.index.duplicated(keep='last')]
        
        # เช็คและเติมค่า Null (Forward Fill) เพื่อให้กราฟต่อเนื่องไม่ขาดตอน
        df = df.ffill()
        
        # Flatten MultiIndex Columns (ถ้ามี)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        return df
    except:
        return None

# ------------------------
# 1. UI: SIDEBAR (Portfolio Summary)
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    for sym, m in list(st.session_state.portfolio.items()):
        with st.expander(f"📌 {sym}"):
            st.write(f"ต้นทุน: {m['cost']:,.2f} ฿")
            if st.button(f"ลบ {sym}", key=f"del_{sym}"):
                del st.session_state.portfolio[sym]
                st.rerun()
    st.divider()
    budget = st.number_input("งบประมาณ (บาท):", value=5000.0)

# ------------------------
# 2. MAIN APP: DYNAMIC OBJECTS
# ------------------------
usd_thb = 35.0 # สามารถใช้ API ดึงค่าจริงได้
st.title("👛 Smart Trading Panel")
st.write(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")

symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']
cols = st.columns(2)

for idx, s in enumerate(symbols):
    df = get_clean_data(s)
    if df is not None:
        price_thb = float(df['Close'].iloc[-1]) * usd_thb
        
        # แสดงเฉพาะเหรียญที่ราคาอยู่ในงบ
        if price_thb <= budget:
            with cols[idx % 2]:
                with st.container(border=True):
                    # ส่วนหัวเหรียญ
                    st.subheader(f"🪙 {s}")
                    st.metric("ราคาปัจจุบัน", f"{price_thb:,.2f} ฿")
                    
                    # กราฟต่อเนื่อง (Continuous Chart)
                    fig = go.Figure(data=[go.Scatter(
                        y=df['Close'].values, 
                        mode='lines',
                        line=dict(color='#00ffcc', width=2),
                        fill='tozeroy',
                        fillcolor='rgba(0, 255, 204, 0.1)'
                    )])
                    fig.update_layout(height=150, margin=dict(l=0,r=0,t=0,b=0), 
                                    xaxis_visible=False, yaxis_visible=False,
                                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                    # --- Smooth Slide Interaction ---
                    # เช็คสถานะการ Active จาก session_state หรือ toggle
                    active = st.toggle(f"เปิดโหมดวางแผน {s}", key=f"active_{s}", value=(s in st.session_state.portfolio))
                    
                    if active:
                        # เมื่อ Active จะ "Slide" ส่วนควบคุมออกมา
                        st.write("---")
                        m = st.session_state.portfolio.get(s, {'cost': price_thb, 'target': 10, 'stop': 5})
                        
                        # ช่องกรอกทุน
                        new_cost = st.number_input(f"ระบุราคาทุน {s} (฿):", value=float(m['cost']), key=f"cost_{s}")
                        
                        # Sliders สำหรับเป้าหมาย
                        c1, c2 = st.columns(2)
                        new_target = c1.slider("เป้ากำไร (%)", 1, 100, int(m['target']), key=f"tgt_{s}")
                        new_stop = c2.slider("จุดตัดขาดทุน (%)", 1, 50, int(m['stop']), key=f"stop_{s}")
                        
                        # บันทึกค่าลงพอร์ตทันที
                        st.session_state.portfolio[s] = {'cost': new_cost, 'target': new_target, 'stop': new_stop}
                        
                        # แสดงผลสถานะกำไร/ขาดทุน
                        pnl = ((price_thb - new_cost) / new_cost) * 100
                        if pnl >= new_target: st.success(f"🚀 SELL NOW: {pnl:+.2f}%")
                        elif pnl <= -new_stop: st.error(f"🛑 STOP LOSS: {pnl:+.2f}%")
                        else: st.info(f"📈 กำไรปัจจุบัน: {pnl:+.2f}%")

# ระบบ Auto-Refresh
time.sleep(60)
st.rerun()
