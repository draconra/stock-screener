"""
Vercel Serverless Entry Point.

Vercel's @vercel/python runtime natively supports ASGI (FastAPI).
It auto-detects the `app` variable. No adapter library needed.

All /api/* requests are routed here via vercel.json routes.
"""
import sys
import os
import importlib

# Add the backend directory to Python path so its internal imports
# (e.g., 'from services.indicators import ...') resolve correctly.
_backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
_backend_dir = os.path.abspath(_backend_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# We can't do `from api import app` because 'api' would resolve to
# this very directory (api/). Instead, load backend/api.py directly
# using importlib with the full file path.
_api_path = os.path.join(_backend_dir, 'api.py')
_spec = importlib.util.spec_from_file_location("backend_api", _api_path)
_module = importlib.util.module_from_spec(_spec)

# Register the module so sub-imports within api.py work correctly
sys.modules["backend_api"] = _module
_spec.loader.exec_module(_module)

# Expose the FastAPI app — Vercel looks for this variable
app = _module.app
