import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go

# ------------------------
# 0. CONFIG & DATABASE
# ------------------------
DB_FILE = "crypto_stable_v4.pkl"
st.set_page_config(page_title="Crypto Strategist Pro", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}

def save_data(data):
    with open(DB_FILE, 'wb') as f:
        pickle.dump(data, f)

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            return pickle.load(f)
    return {}

if 'master_data' not in st.session_state:
    st.session_state.master_data = load_data()

# ------------------------
# 1. SIDEBAR (Real-time View)
# ------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if not st.session_state.portfolio:
        st.info("ยังไม่มีเหรียญในพอร์ต")
    else:
        # สรุปภาพรวมพอร์ต
        total_profit = 0
        for sym, m in list(st.session_state.portfolio.items()):
            if sym in st.session_state.master_data:
                curr_p = st.session_state.master_data[sym]['price']
                diff = ((curr_p - m['cost']) / m['cost']) * 100
                total_profit += diff
                
                with st.expander(f"📌 {sym} | {diff:+.2f}%", expanded=True):
                    st.write(f"ทุนปัจจุบัน: **{m['cost']:,.2f}**")
                    st.write(f"ตลาด: {curr_p:,.2f}")
                    if st.button(f"นำ {sym} ออก", key=f"side_del_{sym}"):
                        del st.session_state.portfolio[sym]
                        st.rerun()
        st.divider()
        st.write(f"📈 ภาพรวมพอร์ต: {total_profit:+.2f}%")

    st.divider()
    budget = st.number_input("กรองงบ (บาท):", min_value=0.0, step=1000.0)

# ------------------------
# 2. MAIN DISPLAY LOGIC
# ------------------------
st.title("🛡️ AI Crypto Strategist")

# (สมมติว่า sync_market_data ทำงานอยู่เบื้องหลังเหมือนเดิม)
# ดึงข้อมูลมาแสดงผล
display_list = [s for s, d in st.session_state.master_data.items() if budget == 0 or d['price'] <= budget]
if budget == 0: display_list = display_list[:6]

cols = st.columns(2)
for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    icon = "🔵" if data.get('rank', 100) <= 30 else "🪙"
    
    with cols[idx % 2]:
        with st.container(border=True):
            h1, h2 = st.columns([4, 1])
            h1.subheader(f"{icon} {s}")
            
            # ปุ่ม Pin
            if h2.button("📍" if is_pinned else "📌", key=f"btn_p_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15.0, 'stop': 7.0}
                st.rerun()

            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿")
            
            # กราฟ
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(50).values, mode='lines', line=dict(color='#00ffcc'))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"gr_{s}", config={'displayModeBar': False})

            # --- ส่วนกรอกราคาทุนแบบ "Enter to Update" ---
            if is_pinned:
                st.divider()
                m = st.session_state.portfolio[s]
                
                # เปลี่ยนเป็นปุ่ม Enter โดยการระบุ format และไม่ใช้ step เล็กๆ
                # เมื่อผู้ใช้พิมพ์เลขแล้วกด Enter, Streamlit จะ rerun และ Sidebar จะเห็นค่าใหม่ทันที
                new_cost = st.number_input(
                    f"ระบุต้นทุน {s} (กด Enter เพื่อบันทึก):", 
                    value=float(m['cost']), 
                    format="%.2f",
                    key=f"cost_in_{s}"
                )
                
                c1, c2 = st.columns(2)
                new_tgt = c1.slider("เป้า %", 5, 100, int(m['target']), key=f"t_{s}")
                new_stp = c2.slider("คัด %", 3, 50, int(m['stop']), key=f"p_{s}")
                
                # บันทึกค่าที่เปลี่ยนลง Session State
                if new_cost != m['cost'] or new_tgt != m['target'] or new_stp != m['stop']:
                    st.session_state.portfolio[s] = {'cost': new_cost, 'target': new_tgt, 'stop': new_stp}
                    # การทำ st.rerun() ตรงนี้จะทำให้ Sidebar อัปเดตทันทีที่ค่าเปลี่ยน
                    st.rerun()
            else:
                st.caption("💡 ปักหมุดเพื่อคำนวณกำไรในพอร์ต")
