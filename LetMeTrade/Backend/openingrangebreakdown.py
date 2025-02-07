import sqlite3
from datetime import datetime
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame

from main import strategy
from db import config
from helpers import calc_qty
from timezone import is_dst

# Connect to database
connection = sqlite3.connect(config.DB_FILE)
connection.row_factory = sqlite3.Row
cursor = connection.cursor()

# Get strategy ID
cursor.execute("SELECT id FROM strategy WHERE name = 'opening_range_breakout'")
strategy_id = cursor.fetchone()["id"]

# Get stock symbols for the strategy
cursor.execute("""
    SELECT symbol, name
    FROM stock
    JOIN stock_strategy ON stock_strategy.stock_id = stock.id
    WHERE stock_strategy.strategy_id = ?
""", (strategy_id,))
stocks = cursor.fetchall()
symbols = [stock["symbol"] for stock in stocks]
print(f"Tracking symbols: {symbols}")

# Initialize Alpaca API
api = tradeapi.REST(config.API_KEY, config.SECRET_KEY, config.API_URL, api_version="v2")

# Get the current date in UTC format
current_date = datetime.utcnow().strftime("%Y-%m-%d")

# Define opening range times
if is_dst():
    start_minute_bar = f"{current_date}T09:30:00-04:00"
    end_minute_bar = f"{current_date}T09:45:00-04:00"
else:
    start_minute_bar = f"{current_date}T09:30:00-05:00"
    end_minute_bar = f"{current_date}T09:45:00-05:00"

# Fetch existing orders
orders = api.list_orders(status="all", limit=500, after=f"{current_date}T09:30:00Z")
existing_order_symbols = [order.symbol for order in orders if order.status != "canceled"]

# Process each symbol
for symbol in symbols:
    print(f"\nChecking stock: {symbol}")

    try:
        # Fetch minute bars for the symbol
        minute_bars = api.get_bars(symbol, TimeFrame.Minute, start=current_date, end=current_date).df

        if minute_bars.empty:
            print(f"No data for {symbol} - skipping.")
            continue

        # Extract opening range data
        opening_range_mask = (minute_bars.index >= start_minute_bar) & (minute_bars.index < end_minute_bar)
        opening_range_bars = minute_bars.loc[opening_range_mask]

        if opening_range_bars.empty:
            print(f"No opening range data for {symbol} - skipping.")
            continue

        opening_range_low = opening_range_bars["low"].min()
        opening_range_high = opening_range_bars["high"].max()
        opening_range = opening_range_high - opening_range_low

        # Check price movement after the opening range
        after_opening_range_mask = minute_bars.index >= end_minute_bar
        after_opening_range_bars = minute_bars.loc[after_opening_range_mask]

        if after_opening_range_bars.empty:
            print(f"No after-range data for {symbol} - skipping.")
            continue

        after_opening_range_breakdown = after_opening_range_bars[
            after_opening_range_bars["close"] > opening_range_low
        ]

        if not after_opening_range_breakdown.empty and symbol not in existing_order_symbols:
            limit_price = after_opening_range_breakdown.iloc[0]["close"]

            print(f"Placing SELL order for {symbol} at {limit_price}")

            try:
                # Submit short selling order
                api.submit_order(
                    symbol=symbol,
                    side="sell",
                    type="limit",
                    qty=calc_qty(limit_price),
                    time_in_force="day",
                    order_class="bracket",
                    take_profit={"limit_price": limit_price - opening_range},
                    stop_loss={"stop_price": limit_price + opening_range, "limit_price": limit_price},
                )
                print(f"Order placed for {symbol}.")
            except Exception as e:
                print(f"Error placing order for {symbol}: {e}")
        else:
            print(f"Sell order for {symbol} already exists or no valid breakdown detected.")
    except Exception as e:
        print(f"Error processing {symbol}: {e}")

print("Script execution complete.")
