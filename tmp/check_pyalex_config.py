
import pyalex
import pprint

print(f"Pyalex version: {pyalex.__version__}")

# Default
print(f"Default openalex_url: {pyalex.config.openalex_url}")

# Try to use Works with a fake URL
try:
    pyalex.config.openalex_url = "http://127.0.0.1:9999"
    print(f"Set openalex_url to: {pyalex.config.openalex_url}")
    # This should fail if it tries to connect
    pyalex.Works().filter(ror="https://ror.org/03s5v5320").count()
except Exception as e:
    print(f"Expected error with fake openalex_url: {e}")

# Try to use Works with api_url (setting it)
try:
    pyalex.config.api_url = "http://127.0.0.1:8888"
    print(f"Set api_url to: {pyalex.config.api_url}")
    # Does this affect the query? 
    # If pyalex internally uses openalex_url, setting api_url won't change where it goes (unless it's an alias)
except Exception as e:
    print(f"Error setting api_url: {e}")
