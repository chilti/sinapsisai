import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import clickhouse_connect
import traceback

print("Testing ClickHouse connection...")
try:
    client = clickhouse_connect.get_client(host='127.0.0.1', username='default', password='', port=8123)
    print("Connected to 127.0.0.1:8123!")
    print(client.command("SELECT 1"))
except Exception:
    print("Failed on port 8123. Error:")
    traceback.print_exc()

try:
    client = clickhouse_connect.get_client(host='localhost', username='default', password='', port=9000)
    print("Connected to port 9000!")
    print(client.command("SELECT 1"))
except Exception:
    print("Failed on port 9000. Error:")
    traceback.print_exc()
