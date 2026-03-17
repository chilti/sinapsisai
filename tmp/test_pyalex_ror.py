import pyalex
import os
from dotenv import load_dotenv

load_dotenv()
pyalex.config.email = os.getenv("EMAIL_ADDRESS", "test@example.com")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

ror_url = "https://ror.org/02xp9d883" # Banco de Mexico
print(f"Testing ROR URL: {ror_url}")
try:
    works_query = pyalex.Works().filter(institutions={"ror": ror_url})
    total = works_query.count()
    print(f"Total works found: {total}")
except Exception as e:
    print(f"Error: {e}")
