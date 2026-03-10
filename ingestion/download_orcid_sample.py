# download_orcid_sample.py
import paramiko
import os
import tarfile
import io

HOSTNAME = "dinamica1.fciencias.unam.mx"
USERNAME = "jlja"
PASSWORD = "T3mporal123+-"
REMOTE_PATH = "/mnt/expansion/30375589_orcid2025.zip"

def debug_server_permissions():
    print(f"Connecting to {HOSTNAME}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOSTNAME, username=USERNAME, password=PASSWORD)
        
        stdin, stdout, stderr = client.exec_command("id; ls -ld /mnt/expansion/dockers_drives/clickhouse")
        print("Command output:")
        print(stdout.read().decode('utf-8'))
        print("Error output:")
        print(stderr.read().decode('utf-8'))
                
    finally:
        client.close()

if __name__ == "__main__":
    debug_server_permissions()
