import pandas as pd
import pandas_ta as ta # ต้องติดตั้งเพิ่ม: pip install pandas_ta
import yfinance as yf
import requests

def get_market_sentiment():
    # ดึงค่า Fear & Greed Index จาก API ฟรี
    url = "https://api.alternative.me/fng/"
    r = requests.get(url).json()
    return int(r['data'][0]['value'])

def prepare_data(symbol="BTC-USD"):
    # 1. ดึงราคาย้อนหลัง
    df = yf.download(symbol, period="60d", interval="1h")
    
    # 2. คำนวณ Technical Indicators (ใส่สมองให้ AI)
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.macd(append=True)
    
    # 3. ใส่ข้อมูล Sentiment ลงไปในทุกแถว
    df['sentiment'] = get_market_sentiment()
    
    return df.dropna()

# ทดสอบรัน
data = prepare_data()
print(data.tail())
