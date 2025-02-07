import smtplib
import ssl
import logging
from main import strategy
from db import config
import sqlite3
from datetime import datetime, timezone
from helpers import calc_qty
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Database Connection
connection = sqlite3.connect(config.DB_FILE)
connection.row_factory = sqlite3.Row
cursor = connection.cursor()

# Get Strategy ID
cursor.execute("""
   SELECT id FROM strategy WHERE name = 'opening_range_breakout'
""")
strategy_id = cursor.fetchone()['id']

# Get Stock Symbols for the Strategy
cursor.execute("""
   SELECT symbol, name
   FROM stock
   JOIN stock_strategy on stock_strategy.stock_id = stock.id
   WHERE stock_strategy.strategy_id = ?
""", (strategy_id,))
stocks = cursor.fetchall()
symbols = [stock['symbol'] for stock in stocks]

logging.info(f"Symbols to Trade: {symbols}")

# Alpaca API Connection
api = tradeapi.REST(config.API_KEY, config.SECRET_KEY, config.API_URL, api_version='v2')

# Define Trading Date
current_date = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")  
start_minute_bar = f"{current_date}T09:30:00Z"
end_minute_bar = f"{current_date}T09:45:00Z"


# Messages for email
messages = []

# Fetch Existing Orders
orders = api.list_orders(status='all', limit=500, after=start_minute_bar)
existing_order_symbols = [order.symbol for order in orders if order.status != 'canceled']

# Trading Logic for Each Symbol
for symbol in symbols:
   logging.info(f"Processing {symbol}...")

   # Fetch minute bars
   try:
       minute_bars = api.get_bars(symbol, TimeFrame.Minute, start=start_minute_bar, end=end_minute_bar).df
   except Exception as e:
       logging.error(f"Error fetching bars for {symbol}: {e}")
       continue  # Skip to next symbol

   if minute_bars.empty:
       logging.warning(f"No data available for {symbol}, skipping...")
       continue

   # Define Opening Range
   opening_range_mask = (minute_bars.index >= start_minute_bar) & (minute_bars.index < end_minute_bar)
   opening_range_bars = minute_bars.loc[opening_range_mask]

   if not opening_range_bars.empty:
       opening_range_low = opening_range_bars['low'].min()
       opening_range_high = opening_range_bars['high'].max()
       opening_range = opening_range_high - opening_range_low

       after_opening_range_mask = minute_bars.index >= end_minute_bar
       after_opening_range_bars = minute_bars.loc[after_opening_range_mask]

       after_opening_range_breakout = after_opening_range_bars[after_opening_range_bars['close'] > opening_range_high]

       if not after_opening_range_breakout.empty and symbol not in existing_order_symbols:
           limit_price = after_opening_range_breakout.iloc[0]['close']
           logging.info(f"Buying {symbol} at {limit_price}, breakout above {opening_range_high}")

           try:
               # Submit order
               order = api.submit_order(
                   symbol=symbol,
                   side='buy',
                   type='limit',
                   qty=calc_qty(limit_price),
                   time_in_force='day',
                   order_class='bracket',
                   take_profit=dict(
                       limit_price=limit_price + opening_range,
                   ),
                   stop_loss=dict(
                       stop_price=limit_price - opening_range,
                       limit_price=limit_price,
                   )
               )
               message = f"Order placed successfully for {symbol}. Order ID: {order.id}"
               logging.info(message)
               messages.append(message)
           except Exception as e:
               error_message = f"Could not submit order for {symbol}: {e}"
               logging.error(error_message)
               messages.append(error_message)
       else:
           logging.info(f"Buy order for {symbol} already exists or no breakout, skipping...")

# Email Notification
try:
   context = ssl.create_default_context()
   with smtplib.SMTP_SSL(config.EMAIL_HOST, config.EMAIL_PORT, context=context) as server:
       server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
       current_date = datetime.today().strftime('%Y-%m-%d')

       email_body = f"Subject: Trade Notifications for {current_date}\n\n"
       email_body += "\n\n".join(messages) if messages else "No breakout opportunities found."

       server.sendmail(
           config.EMAIL_ADDRESS,  # From
           config.EMAIL_ADDRESS,  # To
           email_body  # Email body
       )
   logging.info("Email sent successfully!")
except smtplib.SMTPAuthenticationError as e:
   logging.error("SMTP Authentication Error: %s", e)
except Exception as e:
   logging.error("Error sending email: %s", e)

# Close database connection
connection.close()