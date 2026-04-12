import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pyalex
import os
from dotenv import load_dotenv

load_dotenv()
pyalex.config.email = os.getenv("EMAIL_FOR_OPENALEX", "test@example.com")
# pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

dois = ["10.1093/database/baaf085", "10.1002/cjce.70273"]

for doi in dois:
    print(f"Checking DOI: {doi}")
    try:
        results = pyalex.Works().filter(doi=doi).get()
        print(f"  Results found: {len(results)}")
        if results:
            print(f"  Title: {results[0].get('title')}")
    except Exception as e:
        print(f"  Error: {e}")
