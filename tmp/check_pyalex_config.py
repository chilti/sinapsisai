
import pyalex

# Set to local
pyalex.config.openalex_url = "http://127.0.0.1:5009"
print(f"Set openalex_url to: {pyalex.config.openalex_url}")

# Create a Works query
query = pyalex.Works().filter(ror="https://ror.org/03s5v5320")

# Use a trick to see the URL without actually sending the request if possible, 
# or just look at the error message.
try:
    print("Calling count()...")
    query.count()
except Exception as e:
    print(f"Caught error: {e}")
    import traceback
    # traceback.print_exc()
