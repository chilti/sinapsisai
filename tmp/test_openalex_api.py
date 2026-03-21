import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ingestion.openalex_utils import get_work

doi = "https://doi.org/10.1103/PhysRevD.107.074027"

print(f"🔍 Testing OpenAlex lookup for: {doi}")
work = get_work(doi=doi)

if work:
    print("\n✅ WORK FOUND!")
    print(f"   Name:  {work.get('title')}")
    print(f"   DOI:   {work.get('doi')}")
    print(f"   Score: {work.get('cited_by_count')} citations")
    print(f"   ID:    {work.get('id')}")
else:
    print("\n❌ WORK NOT FOUND.")
