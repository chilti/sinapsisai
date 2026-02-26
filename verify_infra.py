import requests
import time

SERVICES = {
    "Qdrant": "http://localhost:6333/healthz",
    "Neo4j": "http://localhost:7474",
    "Grobid": "http://localhost:8070/api/isalive",
    "Unstructured": "http://localhost:8000/general/v0/general"
}

def verify_services():
    print("🔍 Verificando estado de los servicios...")
    for name, url in SERVICES.items():
        try:
            # Unstructured general endpoint requires POST, but we can check if the server is up with a simple GET to /health or similar if exist
            # For now, we just check reachability
            if name == "Unstructured":
                 response = requests.get("http://localhost:8000/", timeout=5)
            else:
                 response = requests.get(url, timeout=5)
            
            if response.status_code in [200, 404, 405]: # some return 404 on root but are 'up'
                print(f"✅ {name}: En línea ({response.status_code})")
            else:
                print(f"⚠️ {name}: Respondió con status {response.status_code}")
        except Exception as e:
            print(f"❌ {name}: No disponible. {e}")

if __name__ == "__main__":
    verify_services()
