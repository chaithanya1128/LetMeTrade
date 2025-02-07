import sqlite3
import time

DB_FILE = "your_database.db"

def match_orders():
    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    while True:
        start_time = time.time()
        matched_count = 0

        cursor.execute("SELECT * FROM orders WHERE status='open' AND order_type='buy' ORDER BY price DESC, created_at ASC")
        buy_orders = cursor.fetchall()

        cursor.execute("SELECT * FROM orders WHERE status='open' AND order_type='sell' ORDER BY price ASC, created_at ASC")
        sell_orders = cursor.fetchall()

        for buy_order in buy_orders:
            for sell_order in sell_orders:
                if buy_order[2] >= sell_order[2]:
                    match_quantity = min(buy_order[3], sell_order[3])
                    matched_count += 1

                    cursor.execute("UPDATE orders SET quantity = quantity - ?, status = CASE WHEN quantity = 0 THEN 'matched' ELSE 'open' END WHERE id = ?", (match_quantity, buy_order[0]))
                    cursor.execute("UPDATE orders SET quantity = quantity - ?, status = CASE WHEN quantity = 0 THEN 'matched' ELSE 'open' END WHERE id = ?", (match_quantity, sell_order[0]))

                    connection.commit()

        end_time = time.time()
        elapsed_time = end_time - start_time

        if elapsed_time > 0:
            print(f"Orders Matched Per Second: {matched_count / elapsed_time:.2f}")

        time.sleep(1)

if __name__ == "__main__":
    match_orders()
