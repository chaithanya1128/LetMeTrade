import config
import sqlite3
import pandas
import csv
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
from datetime import datetime, timedelta

connection = sqlite3.connect(config.DB_FILE)
connection.row_factory = sqlite3.Row

cursor = connection.cursor()

api = tradeapi.REST(config.API_KEY, config.SECRET_KEY, config.API_URL)
symbols = []
stock_ids = {}

with open('./db/qqq.csv') as f:
    reader = csv.reader(f)

    for line in reader:
        symbols.append(line[1])

cursor.execute("""
    SELECT * FROM stock
""")

stocks = cursor.fetchall()

for stock in stocks:
    symbol = stock['symbol']
    stock_ids[symbol] = stock['id']
    
for symbol in symbols:
    # Skip if symbol not in stock_ids
    if symbol not in stock_ids:
        print(f"Warning: Symbol {symbol} not found in stock table. Skipping.")
        continue

    start_date = datetime(2020, 1, 6).date()
    end_date_range = datetime(2021, 5, 28).date()

    while start_date < end_date_range:
        end_date = start_date + timedelta(days=4)

        print(f"== Fetching minute bars for {symbol} {start_date} - {end_date} ==")
        try:
            minutes = api.get_bars(symbol, TimeFrame.Minute, start_date, end_date).df
            minutes = minutes.resample('1min').ffill()

            for index, row in minutes.iterrows():
                cursor.execute("""
                    INSERT INTO stock_price_minute (stock_id, datetime, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (stock_ids[symbol], index.tz_localize(None).isoformat(), row['open'], row['high'], row['low'], row['close'], row['volume']))

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

        start_date = start_date + timedelta(days=7)

connection.commit()