import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

CH_HOST = "10.90.0.87"
CH_PORT = 8124

def try_kill():
    # Intento 1: admin/admin
    print("Trying KILL as admin/admin...")
    try:
        client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username='admin', password='admin', database='rag')
        client.command("KILL MUTATION WHERE table = 'works' AND is_done = 0")
        print("Success as admin/admin!")
        return
    except Exception as e:
        print(f"Failed as admin: {e}")

    # Intento 2: rag_user (aunque ya vimos que falló el SELECT)
    print("\nTrying KILL as rag_user...")
    try:
        client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASS, database=CH_DATABASE)
        client.command("KILL MUTATION WHERE table = 'works' AND is_done = 0")
        print("Success as rag_user!")
        return
    except Exception as e:
        print(f"Failed as rag_user: {e}")

if __name__ == "__main__":
    try_kill()
