import numpy
import tulipy
from datetime import datetime, timedelta
import sqlite3
import config
import alpaca_trade_api as tradeapi

api = tradeapi.REST(config.API_KEY, config.SECRET_KEY, base_url=config.API_URL)

connection = sqlite3.connect(config.DB_FILE)
connection.row_factory = sqlite3.Row
cursor = connection.cursor()

cursor.execute("""
    SELECT id, symbol, name FROM stock
""")

rows = cursor.fetchall()

symbols = []
stock_dict = {}
for row in rows:
    symbol = row['symbol']
    symbols.append(symbol)
    stock_dict[symbol] = row['id']

start_date = (datetime.today() - timedelta(days=7)).strftime('%Y-%m-%d')

chunk_size = 200
for i in range(0, len(symbols), chunk_size):
    symbol_chunk = symbols[i:i+chunk_size]
    
    bars = {symbol: api.get_bars(symbol, timeframe='1Day', start=start_date) for symbol in symbol_chunk}

    for symbol, symbol_bars in bars.items():
        print(f"processing symbol {symbol}")

        # Use .c for close, .o for open, etc.
        recent_closes = [bar.c for bar in symbol_bars]

        for bar in symbol_bars:
            stock_id = stock_dict[symbol]

            if len(recent_closes) >= 50 and datetime.today().date() == bar.t.date():
                sma_20 = tulipy.sma(numpy.array(recent_closes), period=20)[-1]
                sma_50 = tulipy.sma(numpy.array(recent_closes), period=50)[-1]
                rsi_14 = tulipy.rsi(numpy.array(recent_closes), period=14)[-1]
            else:
                sma_20, sma_50, rsi_14 = None, None, None
            
            cursor.execute("""
                INSERT INTO stock_price (stock_id, date, open, high, low, close, volume, sma_20, sma_50, rsi_14)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (stock_id, bar.t.date(), bar.o, bar.h, bar.l, bar.c, bar.v, sma_20, sma_50, rsi_14))

connection.commit()