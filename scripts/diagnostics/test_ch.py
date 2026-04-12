import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import clickhouse_connect

try:
    # Credenciales encontradas: admin / admin en la BD 'openalex'
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='admin', password='admin', database='openalex')
    result = client.command('SELECT version()')
    print(f"Connected to ClickHouse! Version: {result}")
    
    # Try to create the table
    with open('database/setup_orcid_db.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    # Execute commands
    for command in sql.split(';'):
        # Strip comments
        lines = [line for line in command.splitlines() if not line.strip().startswith('--')]
        cleaned = " ".join(lines).strip()
        if cleaned:
            print(f"Executing: {cleaned[:50]}...")
            client.command(cleaned)
            
    print("ORCID table setup complete.")
except Exception as e:
    print(f"Failed to connect or setup ClickHouse: {e}")
