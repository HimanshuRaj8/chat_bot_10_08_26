"""
Enterprise Approval System AI Assistant — Main Entrypoint (Backend V2)
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_V2_DIR = os.path.join(BASE_DIR, "backend_v2")

if BACKEND_V2_DIR not in sys.path:
    sys.path.insert(0, BACKEND_V2_DIR)

from backend_v2.app import app, config

if __name__ == "__main__":
    port = getattr(config, "FLASK_PORT", 8001)
    print(f"[*] Starting Enterprise Approval System (Backend V2) on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
