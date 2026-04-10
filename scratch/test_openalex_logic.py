import sys
import os
import json

# Mocking the path to include the script directory
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'SNII')))

import match_snii_openalex

# Mock Author Data
mock_author = {
    "display_name": "Humberto Andres Carrillo Calvet",
    "affiliations": [
        {
            "institution": {"display_name": "UNAM"},
            "years": [2010, 2015, 2022] # Has year in 2021-2025
        },
        {
            "institution": {"display_name": "Other"},
            "years": [2000, 2005] # No year in range
        }
    ]
}

mock_author_old = {
    "display_name": "Old Researcher",
    "affiliations": [
        {
            "institution": {"display_name": "UNAM"},
            "years": [2010, 2015, 2020] # No year in 2021-2025
        }
    ]
}

print("Testing filter_by_recent_affiliation...")

is_recent, inst = match_snii_openalex.filter_by_recent_affiliation(mock_author)
print(f"Author 1 (Recent): {is_recent}, Institution: {inst}")

is_recent_old, inst_old = match_snii_openalex.filter_by_recent_affiliation(mock_author_old)
print(f"Author 2 (Old): {is_recent_old}, Institution: {inst_old}")

assert is_recent == True
assert inst == "UNAM"
assert is_recent_old == False

print("\nTesting scoring...")
score = match_snii_openalex.jaro_winkler(
    match_snii_openalex.get_token_sorted_name("CARRILLO CALVET, HUMBERTO ANDRES"),
    match_snii_openalex.get_token_sorted_name("Humberto Andres Carrillo Calvet")
)
print(f"Name Score: {score:.4f}")
assert score > 0.95

print("\n✅ All logic tests passed!")
