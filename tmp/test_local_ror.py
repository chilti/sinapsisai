
import httpx

LOCAL_BASE = "http://localhost:5009"
ROR_ID = "015v43a21" # Example from logs

url = f"{LOCAL_BASE}/institutions/ror:{ROR_ID}"
print(f"Testing URL: {url}")

try:
    with httpx.Client(verify=False, timeout=10) as client:
        resp = client.get(url)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            import json
            print(json.dumps(resp.json(), indent=2)[:1000])
except Exception as e:
    print(f"Error: {e}")
