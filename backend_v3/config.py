"""
Backend V3 — Configuration
"""
import os

# ── Directory Layout ─────────────────────────────────────────────────────────
BACKEND_V3_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR       = os.path.dirname(BACKEND_V3_DIR)

SAMPLE_FOLDER  = os.path.join(BASE_DIR, "Sample")
UPLOAD_FOLDER  = os.path.join(BASE_DIR, "uploads")
FRONTEND_FOLDER = os.path.join(BASE_DIR, "frontend")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Excel Data Files ──────────────────────────────────────────────────────────
def _pick(upload_name: str, sample_name: str) -> str:
    upload_path = os.path.join(UPLOAD_FOLDER, upload_name)
    sample_path = os.path.join(SAMPLE_FOLDER, sample_name)
    return upload_path if os.path.exists(upload_path) else sample_path

DEFAULT_REQUISITION_EXCEL = _pick("Requisitions_Latest.xlsx", "Requisitions.xlsx")
DEFAULT_EMPLOYEE_EXCEL    = _pick("Employees_Latest.xlsx",    "Employees.xlsx")
DEFAULT_FINANCE_EXCEL     = _pick("Finance_Latest.xlsx",      "Finance.xlsx")

# ── LLM Configuration ─────────────────────────────────────────────────────────
OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

# ── Server ────────────────────────────────────────────────────────────────────
# Run on port 8002 for V3 as approved by user
FLASK_PORT  = int(os.environ.get("FLASK_PORT_V3", 8002))
SECRET_KEY  = os.environ.get("SECRET_KEY", "motherson-approval-system-v3-2026")

# ── Chat History ──────────────────────────────────────────────────────────────
CHAT_HISTORY_FILE = os.path.join(BASE_DIR, "chat_history_v3.json")

# ── LLM Generation Config ─────────────────────────────────────────────────────
LLM_MAX_TOKENS   = int(os.environ.get("LLM_MAX_TOKENS",   512))
LLM_TEMPERATURE  = float(os.environ.get("LLM_TEMPERATURE", 0.1))
LLM_TIMEOUT_SEC  = int(os.environ.get("LLM_TIMEOUT_SEC",  60))

# ── Table & Pagination Formatting ─────────────────────────────────────────────
MAX_TABLE_ROWS    = int(os.environ.get("MAX_TABLE_ROWS", 20))
DEFAULT_PAGE_SIZE = int(os.environ.get("DEFAULT_PAGE_SIZE", 20))
MAX_PAGE_SIZE     = int(os.environ.get("MAX_PAGE_SIZE", 50))
