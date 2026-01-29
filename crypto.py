# --- ส่วนที่ปรับปรุงใน SIDEBAR ---
with st.sidebar:
    st.title("💰 Setting")
    # ปรับ default เป็น 0.0
    budget = st.number_input("งบซื้อเหรียญ (บาท):", min_value=0.0, value=0.0, step=500.0)
    st.caption("💡 ใส่เป็น 0 เพื่อดู Top Gainers ทั้งตลาด")
    
    st.divider()
    # (ส่วน Portfolio เหมือนเดิม...)

# --- ส่วนที่ปรับปรุงใน MAIN UI ---
if not df_market.empty:
    # 1. จัดอันดับ Top 30 ตาม Volume ไว้สำหรับติด Emoji
    top_30_list = df_market.sort_values(by='volume', ascending=False).head(30)['symbol'].tolist()
    
    # 2. Logic การกรอง (Adaptive Filter)
    df_display = df_market.copy()
    df_display['price_thb'] = df_display['price'] * rate
    
    # ตัดเหรียญที่ไม่ต้องการ (Stablecoins / Leveraged tokens)
    df_display = df_display[
        (df_display['symbol'].str.endswith('USDT')) &
        (~df_display['symbol'].str.contains('UP|DOWN|BEAR|BULL|USDC|DAI|FDUSD'))
    ]

    if budget > 0:
        # โหมด: กรองตามงบ
        recommend = df_display[df_display['price_thb'] <= budget].sort_values(by='change', ascending=False).head(6)
        mode_text = f"กรองตามงบ: ไม่เกิน {budget:,.2f} ฿"
    else:
        # โหมด: Default (งบ=0) โชว์ตัวแรงที่สุดในตลาด
        recommend = df_display.sort_values(by='change', ascending=False).head(6)
        mode_text = "Top Gainers ทั่วทั้งกระดาน"

    # 3. การแสดงผล Card (ใช้ Logic เดิมที่สวยงาม)
    st.subheader(f"🔍 {mode_text}")
    
    if recommend.empty:
        st.warning("⚠️ ไม่พบเหรียญที่อยู่ในงบของคุณ")
    else:
        cols = st.columns(2)
        for idx, (i, row) in enumerate(recommend.iterrows()):
            sym_full = row['symbol']
            sym_name = sym_full.replace('USDT', '')
            is_top30 = sym_full in top_30_list
            emoji = "🏆" if is_top30 else "💎"
            
            with cols[idx % 2]:
                with st.container(border=True):
                    # AI Advice ตามความแรง
                    advice = "🔥 พุ่งแรง" if row['change'] > 5 else ("✅ ทรงดี" if row['change'] > 0 else "📉 ย่อตัว")
                    
                    st.subheader(f"{emoji} {sym_name}")
                    st.metric("ราคาตลาด", f"{row['price_thb']:,.2f} ฿", f"{row['change']:+.2f}%")
                    
                    # กราฟ Sparkline
                    fig = go.Figure(go.Scatter(y=[row['price_thb']/(1+row['change']/100), row['price_thb']], 
                                             line=dict(color="#00ffcc" if row['change'] > 0 else "#ff4b4b", width=4)))
                    fig.update_layout(height=40, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, 
                                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True, key=f"rec_{sym_full}", config={'displayModeBar': False})
                    st.caption(f"💡 {advice} | {'เหรียญยอดนิยม' if is_top30 else 'เหรียญซิ่ง'}")
