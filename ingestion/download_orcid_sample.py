# download_orcid_sample.py
import paramiko
import os
import tarfile
import io

HOSTNAME = "dinamica1.fciencias.unam.mx"
USERNAME = "jlja"
PASSWORD = "T3mporal123+-"
REMOTE_PATH = "/mnt/expansion/30375589_orcid2025.zip"

def debug_server_deployment():
    print(f"Connecting to {HOSTNAME} to debug deployment...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOSTNAME, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # Check what is using port 9000 with lsof
        print("--- Process using Port 9000 ---")
        stdin, stdout, stderr = client.exec_command("sudo -S lsof -i :9000")
        stdin.write(PASSWORD + '\n')
        stdin.flush()
        print(stdout.read().decode('utf-8'))
        
        # Check fuser as fallback
        print("--- Fuser Port 9000 ---")
        stdin, stdout, stderr = client.exec_command(f"sudo -S fuser 9000/tcp")
        stdin.write(PASSWORD + '\n')
        stdin.flush()
        print(stdout.read().decode('utf-8'))
        
        # Check if clickhouse-server is installed via apt
        print("--- Apt Policy Clickhouse ---")
        stdin, stdout, stderr = client.exec_command("apt policy clickhouse-server")
        print(stdout.read().decode('utf-8'))
                
    finally:
        client.close()

if __name__ == "__main__":
    debug_server_deployment()
