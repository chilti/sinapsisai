"""
api/__init__.py - SinapsisAI / SNII Info TlachIA API Package
Garantiza que python_packages locales se encuentren en sys.path.
"""
import sys
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PACKAGES_DIR = os.path.join(BASE_DIR, 'python_packages')

if os.path.isdir(PACKAGES_DIR) and PACKAGES_DIR not in sys.path:
    sys.path.insert(0, PACKAGES_DIR)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
