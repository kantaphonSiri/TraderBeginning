import pandas as pd
import yfinance as yf
import requests

# --- CONFIG ---
LINE_TOKEN = "ใส่_TOKEN_ของคุณที่นี่"
SHEET_URL = "ใส่_LINK_CSV_ของคุณที่นี่"

def send_line(msg):
    url = "https://notify-api.line.me/api/notify"
    headers = {'Authorization': f'Bearer {LINE_TOKEN}'}
    requests.post(url, headers={'message': msg}, headers=headers)

def check_market():
    # 1. โหลดข้อมูลเหรียญที่เราปักหมุดไว้จาก Sheets
    try:
        df_port = pd.read_csv(SHEET_URL)
        df_port.columns = df_port.columns.str.strip().str.lower()
    except: return print("Error loading sheets")

    # 2. ดึงราคาปัจจุบัน
    symbols = [f"{s.strip().upper()}-USD" for s in df_port['symbol']]
    data = yf.download(symbols, period="1d", interval="1m", group_by='ticker', progress=False)
    
    # 3. ดึงค่าเงินบาทล่าสุด
    rate = yf.Ticker("THB=X").fast_info['last_price']

    # 4. ตรวจสอบเงื่อนไข
    for _, row in df_port.iterrows():
        sym = row['symbol'].upper()
        ticker = f"{sym}-USD"
        curr_p = data[ticker]['Close'].iloc[-1] * rate
        
        profit_pct = ((curr_p - row['cost']) / row['cost']) * 100
        
        # ส่งแจ้งเตือนเมื่อถึงเป้ากำไร หรือ จุดตัดขาดทุน
        if profit_pct >= row['target']:
            send_line(f"\n🚀 {sym} ถึงเป้าขาย!\nราคา: {curr_p:,.2f} ฿\nกำไร: {profit_pct:.2f}%")
        elif profit_pct <= -row['stop']:
            send_line(f"\n🛑 {sym} หลุดจุดคัด!\nราคา: {curr_p:,.2f} ฿\nขาดทุน: {profit_pct:.2f}%")

if __name__ == "__main__":
    check_market()