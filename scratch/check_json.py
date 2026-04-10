import json
from collections import Counter

file_path = r'data\snii_llm_verified_matches.json'

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Total records: {len(data)}")
    
    author_counts = Counter(r['snii_author'] for r in data)
    duplicates = {author: count for author, count in author_counts.items() if count > 1}
    
    if duplicates:
        print(f"Found {len(duplicates)} duplicate authors:")
        for author, count in list(duplicates.items())[:10]: # Print first 10
            print(f"  - {author}: {count} times")
    else:
        print("No duplicates found by 'snii_author'.")

    # Check for records with empty discarded_candidates
    empty_discarded = [r for r in data if not r.get('discarded_candidates') and r.get('match') is False]
    print(f"Records with match=False and missing/empty discarded_candidates: {len(empty_discarded)}")

except Exception as e:
    print(f"Error: {e}")
