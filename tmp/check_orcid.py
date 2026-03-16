from SNII.match_snii_orcid import get_client
client = get_client()
res = client.query("SELECT given_names, family_name, last_affiliation FROM openalex.orcid_records WHERE orcid = '0000-0001-8993-4923'").result_rows
print(res)
