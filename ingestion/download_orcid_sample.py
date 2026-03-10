# download_orcid_sample.py
import paramiko
import os
import tarfile
import io

HOSTNAME = "dinamica1.fciencias.unam.mx"
USERNAME = "jlja"
PASSWORD = "T3mporal123+-"
REMOTE_PATH = "/mnt/expansion/30375589_orcid2025.zip"

def check_remote_clickhouse():
    print(f"Connecting to {HOSTNAME} to check ClickHouse...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOSTNAME, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # Check if clickhouse process is running
        stdin, stdout, stderr = client.exec_command("ps aux | grep clickhouse | grep -v grep")
        print("ClickHouse process check:")
        print(stdout.read().decode('utf-8'))
        
        # Check listening ports
        stdin, stdout, stderr = client.exec_command("netstat -tuln | grep -E ':8123|:9000'")
        print("ClickHouse port check:")
        print(stdout.read().decode('utf-8'))
                
    finally:
        client.close()

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    check_remote_clickhouse()
