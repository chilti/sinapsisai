import clickhouse_connect
import os
from dotenv import load_dotenv

# Configuración proporcionada por el usuario
CH_HOST = "10.90.0.87"
CH_PORT = 8123
CH_USER = "admin"  # Asumiendo admin basado en docker-compose anterior
CH_PASSWORD = "admin" # Asumiendo admin basado en docker-compose anterior
CH_DATABASE = "openalex"

try:
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE
    )
    print(f"Conectado a {CH_HOST}")
    
    # Describir la tabla works
    res = client.query("DESCRIBE works")
    for row in res.result_rows:
        print(f"{row[0]}: {row[1]}")
        
except Exception as e:
    print(f"Error conectando a ClickHouse: {e}")
