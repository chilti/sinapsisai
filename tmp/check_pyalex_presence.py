import sys
import os
try:
    import pyalex
    print("pyalex is installed and can be imported.")
    print(f"pyalex file: {pyalex.__file__}")
except ImportError:
    print("pyalex is not installed.")

# Check what's in sys.modules
if 'pyalex' in sys.modules:
    print("pyalex is in sys.modules")
else:
    print("pyalex is NOT in sys.modules")
