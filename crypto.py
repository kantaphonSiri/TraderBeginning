import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go
from datetime import datetime
from streamlit_autorefresh import st_autorefresh # ต้องรัน: pip install streamlit-autorefresh

# ---------------------------------------------------------
# 1. CONFIG & DATABASE
# ---------------------------------------------------------
DB_FILE = "bot_v12_sim.pkl"
# รีเฟรชหน้าจออัตโนมัติทุก 5 นาที (300,000 ms) เพื่อติดตามบอท
st_autorefresh(interval=300000, key="bot_refresh")

st.set_page_config(page_title="AI Maid Trading Bot", layout="wide")

# โหลดข้อมูลสถานะบอท (เงินจำลอง, รายการที่ถืออยู่, ประวัติ)
if 'bot_state' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f: st.session_state.bot_state = pickle.load(f)
    else:
        st.session_state.bot_state = {
            'cash': 100000.0,  # เงินจำลองเริ่มต้น 1 แสนบาท
            'positions': {},    # เหรียญที่ถืออยู่ {SYMBOL: {buy_price, amount, time}}
            'history': [],      # ประวัติการขาย [{symbol, buy, sell, profit_pct, time}]
            'last_sync': 0
        }

def save_bot_state():
    with open(DB_FILE, 'wb') as f:
        pickle.dump(st.session_state.bot_state, f)

# ---------------------------------------------------------
# 2. TRADING ENGINE (The AI Logic)
# ---------------------------------------------------------
def run_trading_bot(master_data, target_pct, stop_pct, budget_per_trade):
    state = st.session_state.bot_state
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # --- 1. ตรวจสอบรายการที่ถืออยู่ (เพื่อขาย) ---
    for sym, pos in list(state['positions'].items()):
        if sym in master_data:
            current_price = master_data[sym]['price']
            profit_pct = ((current_price - pos['buy_price']) / pos['buy_price']) * 100
            
            # เงื่อนไขขาย: ถึงเป้ากำไร หรือ โดนจุดตัดขาดทุน
            if profit_pct >= target_pct or profit_pct <= -stop_pct:
                sell_val = current_price * pos['amount']
                state['cash'] += sell_val
                state['history'].append({
                    'Symbol': sym, 'Buy': pos['buy_price'], 'Sell': current_price,
                    'Profit%': round(profit_pct, 2), 'Time': current_time
                })
                del state['positions'][sym]
                st.toast(f"🔔 ขาย {sym} แล้ว! กำไร {profit_pct:.2f}%")

    # --- 2. ตรวจสอบโอกาสซื้อใหม่ ---
    for sym, data in master_data.items():
        if sym == 'EXCHANGE_RATE': continue
        # ถ้า AI แนะนำ "ขาขึ้นแรง" และเรายังไม่มีเหรียญนี้ และเงินสดพอ
        if data.get('advice') == "🔥 ขาขึ้นแรง (Buy Build)" and sym not in state['positions']:
            if state['cash'] >= budget_per_trade:
                buy_price = data['price']
                amount = budget_per_trade / buy_price
                state['cash'] -= budget_per_trade
                state['positions'][sym] = {
                    'buy_price': buy_price,
                    'amount': amount,
                    'time': current_time
                }
                st.toast(f"🚀 บอทเข้าซื้อ {sym} ที่ราคา {buy_price:,.2f}")
    
    save_bot_state()

# ---------------------------------------------------------
# 3. UI - DASHBOARD
# ---------------------------------------------------------
st.title("🤖 AI Maid Autonomous Bot")

# --- SIDEBAR: ตั้งค่ากลยุทธ์ ---
with st.sidebar:
    st.header("⚙️ Strategy Settings")
    target = st.number_input("เป้ากำไร (%)", 1, 100, 5)
    stoploss = st.number_input("ตัดขาดทุน (%)", 1, 50, 3)
    budget = st.number_input("เงินรันต่อไม้ (บาท)", 500, 50000, 5000)
    
    if st.button("💰 Reset Simulation", type="secondary"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()

# --- TOP METRICS ---
state = st.session_state.bot_state
total_asset = state['cash'] + sum([pos['amount'] * (st.session_state.master_data[s]['price'] if s in st.session_state.master_data else pos['buy_price']) for s, pos in state['positions'].items()])

c1, c2, c3 = st.columns(3)
c1.metric("เงินสดคงเหลือ", f"{state['cash']:,.2f} ฿")
c2.metric("มูลค่าพอร์ตรวม", f"{total_asset:,.2f} ฿", f"{(total_asset-100000)/1000:+.2f}%")
c3.metric("รายการที่ถือ", f"{len(state['positions'])} เหรียญ")

# --- LIVE MONITORING ---
t1, t2 = st.tabs(["📈 รายการที่ถืออยู่", "📜 ประวัติการเทรด"])

with t1:
    if state['positions']:
        pos_df = []
        for s, p in state['positions'].items():
            curr = st.session_state.master_data[s]['price'] if s in st.session_state.master_data else p['buy_price']
            diff = ((curr - p['buy_price']) / p['buy_price']) * 100
            pos_df.append({"เหรียญ": s, "ราคาทุน": p['buy_price'], "ราคาปัจจุบัน": curr, "กำไร/ขาดทุน (%)": round(diff, 2)})
        st.table(pos_df)
    else:
        st.write("😴 บอทกำลังรอจังหวะเข้าซื้อ...")

with t2:
    if state['history']:
        st.dataframe(pd.DataFrame(state['history']).sort_index(ascending=False), use_container_width=True)
    else:
        st.write("ยังไม่มีประวัติการขาย")

# --- AUTO SYNC & RUN BOT ---
# (ใช้ฟังก์ชัน sync_data_robust จากโค้ดก่อนหน้า)
if time.time() - state['last_sync'] > 600: # รันบอททุก 10 นาที
    # 1. Sync ข้อมูลตลาด
    # master_data = sync_data_robust() 
    # 2. สั่งบอททำงาน
    # run_trading_bot(master_data, target, stoploss, budget)
    st.session_state.bot_state['last_sync'] = time.time()
    save_bot_state()
