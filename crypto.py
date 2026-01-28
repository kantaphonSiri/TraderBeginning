import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import os
import pickle
import plotly.graph_objects as go

# ---------------------------------------------------------
# 1. CONFIG & DATABASE (ตั้งค่าเบื้องต้นและฐานข้อมูล)
# ---------------------------------------------------------
DB_FILE = "crypto_v5_stable.pkl"
st.set_page_config(page_title="Crypto AI Strategist", layout="wide")

# เตรียม Session State สำหรับเก็บข้อมูล
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'master_data' not in st.session_state:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            st.session_state.master_data = pickle.load(f)
    else:
        st.session_state.master_data = {}

# ---------------------------------------------------------
# 2. CORE FUNCTIONS (หัวใจการทำงาน)
# ---------------------------------------------------------

@st.cache_data(ttl=3600)
def get_top_100_symbols():
    """ดึงรายชื่อเหรียญ Top 100 ตาม Market Cap จาก Coingecko"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        data = requests.get(url, timeout=10).json()
        return [c['symbol'].upper() for c in data]
    except:
        return ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE']

def sync_data_safe():
    """ดึงราคาจาก Yahoo Finance แบบกลุ่ม พร้อมโชว์ Log สำเร็จ/ล้มเหลว"""
    symbols = get_top_100_symbols()
    try:
        usd_thb = yf.Ticker("THB=X").fast_info['last_price']
    except:
        usd_thb = 35.0 
    
    new_data = st.session_state.master_data.copy()
    success_count, fail_count = 0, 0
    batch_size = 20 
    
    with st.status("📡 AI Scanning Market (Batch Mode)...") as status:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tickers = [f"{s}-USD" for s in batch]
            
            try:
                # ดึงข้อมูลแบบเงียบๆ ไม่พ่น Progress Bar ลง Log
                data_group = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False, timeout=20)
                
                for s in batch:
                    try:
                        df = data_group[f"{s}-USD"] if len(tickers) > 1 else data_group
                        if not df.empty and not pd.isna(df['Close'].iloc[-1]):
                            df = df.ffill()
                            new_data[s] = {
                                'price': float(df['Close'].iloc[-1]) * usd_thb,
                                'base_price': float(df['Close'].mean()) * usd_thb,
                                'df': df,
                                'rank': symbols.index(s) + 1
                            }
                            success_count += 1
                            print(f"✅ [SUCCESS] {s}") 
                        else:
                            fail_count += 1
                            print(f"❌ [FAILED] {s}: No Data")
                    except:
                        fail_count += 1
                        print(f"❌ [FAILED] {s}: Error")
                        continue
                time.sleep(1.2) 
            except Exception as e:
                print(f"⚠️ [BATCH ERROR] Group {i//batch_size + 1}")
                continue
        
        st.session_state.master_data = new_data
        with open(DB_FILE, 'wb') as f:
            pickle.dump(new_data, f)
        status.update(label=f"Scan Complete: OK {success_count} | Fail {fail_count}", state="complete")
    
    st.toast(f"อัปเดต {success_count} เหรียญสำเร็จ", icon="✅")

# ---------------------------------------------------------
# 3. SIDEBAR (เมนูด้านข้าง)
# ---------------------------------------------------------
with st.sidebar:
    st.title("💼 My Portfolio")
    if st.session_state.portfolio:
        for sym, m in list(st.session_state.portfolio.items()):
            with st.expander(f"📌 {sym}", expanded=True):
                st.write(f"ทุน: **{m['cost']:,.2f}**")
                if st.button(f"นำ {sym} ออก", key=f"side_del_{sym}"):
                    del st.session_state.portfolio[sym]
                    st.rerun()
    else:
        st.caption("ยังไม่มีเหรียญที่ปักหมุด")
        
    st.divider()
    budget = st.number_input("งบประมาณ (บาท):", min_value=0.0, step=1000.0)
    if st.button("🔄 อัปเดตราคาตลาดใหม่"):
        sync_data_safe()
        st.rerun()

# ---------------------------------------------------------
# 4. MAIN UI (หน้าจอหลัก)
# ---------------------------------------------------------
st.title("🛡️ Crypto Strategist Pro")

if not st.session_state.master_data:
    sync_data_safe()
    st.rerun()

# กรองเหรียญตามงบ
display_list = [s for s, d in st.session_state.master_data.items() if budget == 0 or d['price'] <= budget]
display_list = display_list[:100] if budget > 0 else display_list[:6] 

cols = st.columns(2)
for idx, s in enumerate(display_list):
    data = st.session_state.master_data[s]
    is_pinned = s in st.session_state.portfolio
    icon = "🔵" if data.get('rank', 100) <= 30 else "🪙"
    
    with cols[idx % 2]:
        with st.container(border=True):
            h1, h2 = st.columns([4, 1])
            h1.subheader(f"{icon} {s}")
            if h2.button("📍" if is_pinned else "📌", key=f"btn_p_{s}"):
                if is_pinned: del st.session_state.portfolio[s]
                else: st.session_state.portfolio[s] = {'cost': data['price'], 'target': 15.0, 'stop': 7.0}
                st.rerun()
            
            st.metric("ราคาตลาด", f"{data['price']:,.2f} ฿")
            
            if is_pinned:
                m = st.session_state.portfolio[s]
                new_cost = st.number_input(
                    f"ระบุราคาทุน {s} (กด Enter):",
                    value=float(m['cost']),
                    format="%.2f",
                    key=f"cost_in_{s}"
                )
                if new_cost != m['cost']:
                    st.session_state.portfolio[s]['cost'] = new_cost
                    st.rerun()
                
                c1, c2 = st.columns(2)
                st.session_state.portfolio[s]['target'] = c1.slider("เป้า %", 5, 100, int(m['target']), key=f"t_{s}")
                st.session_state.portfolio[s]['stop'] = c2.slider("คัด %", 3, 50, int(m['stop']), key=f"s_{s}")
            
            # กราฟ (อัปเดตเป็น Syntax ใหม่ปี 2026)
            fig = go.Figure(data=[go.Scatter(y=data['df']['Close'].tail(50).values, mode='lines', line=dict(color='#00ffcc', width=2))])
            fig.update_layout(height=100, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            
            # แก้ไขตรงนี้ให้รองรับ Streamlit เวอร์ชันใหม่
            st.plotly_chart(fig, width='stretch', key=f"g_{s}", config={'displayModeBar': False})
