import pandas as pd
import requests

LINE_TOKEN = "ใส่_TOKEN_ของคุณ"
SHEET_URL = "ใส่_LINK_CSV_ของคุณ"

def send_line(msg):
    url = "https://notify-api.line.me/api/notify"
    headers = {'Authorization': f'Bearer {LINE_TOKEN}'}
    requests.post(url, data={'message': msg}, headers=headers)

def check_market():
    # 1. โหลดข้อมูลจาก Sheets
    df_port = pd.read_csv(SHEET_URL)
    df_port.columns = df_port.columns.str.strip().str.lower()
    
    # 2. ดึงราคาจาก Binance (ตัวอย่างดึงแบบรวดเดียว)
    res = requests.get("https://api.binance.com/api/v3/ticker/price").json()
    prices = {item['symbol']: float(item['price']) for item in res}
    
    rate = 35.5 # ตั้งค่าเงินบาท

    for _, row in df_port.iterrows():
        sym = row['symbol'].upper()
        pair = f"{sym}USDT"
        if pair in prices:
            curr_p = prices[pair] * rate
            profit_pct = ((curr_p - row['cost']) / row['cost']) * 100
            
            if profit_pct >= row['target']:
                send_line(f"\n🚀 {sym} ขายด่วน!\nกำไร: {profit_pct:.2f}%\nราคา: {curr_p:,.2f} ฿")
            elif profit_pct <= -row['stop']:
                send_line(f"\n🛑 {sym} คัดด่วน!\nขาดทุน: {profit_pct:.2f}%\nราคา: {curr_p:,.2f} ฿")

if __name__ == "__main__":
    check_market()
