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
st.set_page_config(page_title="Budget-Bets Alpha", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}

# ฟังก์ชันดึงข้อมูลแบบคลีน (เช็ค Null และ Forward Fill)
def get_clean_data(symbol):
    try:
        # ดึงข้อมูล 7 วัน ราย 15 นาที เพื่อความต่อเนื่อง
        df = yf.download(f"{symbol}-USD", period="7d", interval="15m", progress=False)
        if df.empty: return None
        
        # จัดการข้อมูลที่ซ้ำและเติมค่าว่าง (ป้องกันกราฟขาดตอน)
        df = df[~df.index.duplicated(keep='last')]
        df = df.ffill() 
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

# ------------------------
# 1. SIDEBAR
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    for sym, m in list(st.session_state.portfolio.items()):
        with st.expander(f"📌 {sym}"):
            st.write(f"ทุน: {m['cost']:,.2f} | เป้า: +{m['target']}%")
            if st.button(f"นำออก", key=f"del_{sym}"):
                del st.session_state.portfolio[sym]
                st.rerun()
    st.divider()
    # ปรับ Default เป็น 0 เพื่อให้เห็นทุกเหรียญตอนเริ่ม
    budget = st.number_input("งบประมาณต่อเหรียญ (บาท):", min_value=0.0, value=0.0, help="ถ้าใส่ 0 จะแสดงทุกเหรียญ")

# ------------------------
# 2. MAIN APP
# ------------------------
st.title("👛 Smart Trading Panel")
usd_thb = 35.0 # แนะนำให้ใช้ API ดึงค่าจริงในอนาคต

symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOT', 'AVAX']
cols = st.columns(2)
display_count = 0

for s in symbols:
    df = get_clean_data(s)
    if df is not None:
        price_thb = float(df['Close'].iloc[-1]) * usd_thb
        
        # --- LOGIC งบประมาณ ---
        # ถ้า budget เป็น 0 หรือ ราคาเหรียญ <= budget ให้แสดงผล
        if budget == 0 or price_thb <= budget:
            with cols[display_count % 2]:
                with st.container(border=True):
                    st.subheader(f"🪙 {s}")
                    st.metric("ราคาตลาด", f"{price_thb:,.2f} ฿")
                    
                    # กราฟต่อเนื่องแบบ Area Chart
                    fig = go.Figure(data=[go.Scatter(
                        y=df['Close'].values, 
                        mode='lines',
                        line=dict(color='#00ffcc', width=2),
                        fill='tozeroy',
                        fillcolor='rgba(0, 255, 204, 0.1)'
                    )])
                    fig.update_layout(height=130, margin=dict(l=0,r=0,t=0,b=0), 
                                    xaxis_visible=False, yaxis_visible=False,
                                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                    # --- Interactive Slide Panel ---
                    in_port = s in st.session_state.portfolio
                    # เมื่อกด Toggle แผงควบคุมจะ Slide ออกมา
                    active = st.toggle(f"วางแผนเทรด {s}", key=f"active_{s}", value=in_port)
                    
                    if active:
                        st.markdown("---")
                        m = st.session_state.portfolio.get(s, {'cost': price_thb, 'target': 10, 'stop': 5})
                        
                        # 1. กรอกทุน (Default เป็นราคาปัจจุบันเพื่อให้ใช้ง่าย)
                        new_cost = st.number_input(f"ราคาทุนที่ซื้อ {s}:", value=float(m['cost']), key=f"cost_{s}")
                        
                        # 2. Slide ปรับเป้าหมาย
                        c1, c2 = st.columns(2)
                        new_target = c1.slider("เป้ากำไร (%)", 1, 100, int(m['target']), key=f"tgt_{s}")
                        new_stop = c2.slider("จุดตัดขาดทุน (%)", 1, 50, int(m['stop']), key=f"stop_{s}")
                        
                        # บันทึกสถานะ
                        st.session_state.portfolio[s] = {'cost': new_cost, 'target': new_target, 'stop': new_stop}
                        
                        # คำนวณกำไร/ขาดทุน
                        pnl = ((price_thb - new_cost) / new_cost) * 100
                        if pnl >= new_target: st.success(f"🚀 ถึงเป้าขาย: {pnl:+.2f}%")
                        elif pnl <= -new_stop: st.error(f"🛑 จุดตัดขาดทุน: {pnl:+.2f}%")
                        else: st.info(f"📈 กำไรปัจจุบัน: {pnl:+.2f}%")
                    
            display_count += 1

# ระบบ Auto-Refresh ทุก 1 นาที
time.sleep(60)
st.rerun()
