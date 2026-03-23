
import requests
import json
orcid_id = '0000-0001-9783-8587'
url = f'https://pub.orcid.org/v3.0/{orcid_id}/works'
headers = {'Accept': 'application/json'}
try:
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        data = response.json()
        groups = data.get('group', [])
        print(f'Total groups found: {len(groups)}')
        for i, group in enumerate(groups[:5]):
             summary = group.get('work-summary', [{}])[0]
             title = summary.get("title", {}).get("title", {}).get("value", "No title")
             print(f'  {i+1}. {title}')
    else:
        print(f'Error {response.status_code}')
except Exception as e:
    print(f'Error: {e}')
