import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def kill_mutations():
    print(f"Connecting to ClickHouse {CH_HOST} to stop mutations...")
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASS,
            database=CH_DATABASE
        )
        
        # Primero listamos las mutaciones activas
        print("Listing active mutations...")
        res = client.query("SELECT mutation_id, command FROM system.mutations WHERE table = 'works' AND is_done = 0")
        mutations = res.result_rows
        
        if not mutations:
            print("No active mutations found to kill.")
            return

        print(f"Found {len(mutations)} active mutations. Killing them...")
        
        # Matar todas las mutaciones activas para la tabla works
        kill_query = "KILL MUTATION WHERE table = 'works' AND is_done = 0"
        client.command(kill_query)
        print("✅ Kill command sent successfully.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    kill_mutations()
