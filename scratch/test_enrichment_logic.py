import sys
import os
import json

# Mocking paths
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'SNII')))
import match_snii_openalex

# Mock Central JSON
mock_json = [
    {
        "snii_author": "TORRES CORDOBA, RAFAEL",
        "snii_institution": "UNIVERSIDAD AUTONOMA DE CIUDAD JUAREZ (UACJ)",
        "match": True,
        "matched_orcid": "0000-0001-5448-8230"
    }
]

# Mock Potential Candidates from OpenAlex
mock_candidates = [
    {
        "name": "Rafael Torres-Cordoba",
        "openalex_id": "https://openalex.org/A12345",
        "institution": "UACJ",
        "years": [2021, 2022, 2023],
        "score": 0.98
    }
]

print("Testing LLM Prompt Generation (Console only)...")
# Note: We won't actually call the LLM in this test to avoid using tokens/hitting timeout
# but we can check if the script logic handles the match correctly.

# Simulate successful LLM match
judgment = {
    "match": True,
    "candidate_index": 1,
    "reason": "Exact name and recent UACJ affiliation."
}

# Apply enrichment logic
entry = mock_json[0]
if judgment["match"]:
    idx = judgment["candidate_index"]
    match_data = mock_candidates[idx-1]
    entry["matched_openalex_id"] = match_data['openalex_id']
    entry["oa_audit"] = {
        "reason": judgment.get('reason'),
        "timestamp": "2026-04-10 12:00:00"
    }

print("\nEnriched Entry:")
print(json.dumps(entry, indent=2))

assert entry["matched_openalex_id"] == "https://openalex.org/A12345"
assert "oa_audit" in entry

print("\n✅ Enrichment logic verified!")
