import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pyalex
import os
import requests
import json
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_original_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    kwargs['verify'] = False
    return _original_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

load_dotenv()
pyalex.config.email = os.getenv("EMAIL_FOR_OPENALEX", "test@example.com")

doi = "10.1002/cjce.70273"
print(f"Deep Search for DOI: {doi}")

# Metodo 1: URL Directa
print("  Method 1: Direct Work URL...")
try:
    w = pyalex.Works()[f"https://doi.org/{doi}"]
    print(f"    Found! Title: {w.get('title')}")
except Exception as e:
    print(f"    Failed: {e}")

# Metodo 2: Filter DOI
print("  Method 2: Filter DOI...")
try:
    res = pyalex.Works().filter(doi=doi).get()
    print(f"    Results count: {len(res)}")
    if res:
        print(f"    Found! Title: {res[0].get('title')}")
except Exception as e:
    print(f"    Failed: {e}")

# Metodo 3: Search Title
title = "A comprehensive morphological characterization of light and heavy Mexican crude oil"
print(f"  Method 3: Search Title: {title[:30]}...")
try:
    res = pyalex.Works().search(title).get()
    print(f"    Results count: {len(res)}")
    if res:
        print(f"    Found! Title: {res[0].get('title')}")
        print(f"    DOI found: {res[0].get('doi')}")
except Exception as e:
    print(f"    Failed: {e}")
