"""
Backend V2 — Flask Application (Port 8001)

THIN ROUTE LAYER ONLY — No business logic here.
All logic is delegated to ChatService, AdminService, AuthService.

Exposes the SAME API endpoints as the original backend/app.py
so the existing frontend works without any JavaScript changes.
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify
from flask_cors import CORS

import config
from data.excel_provider import ExcelDataProvider
from auth.authentication import AuthService
from auth.session_store import SessionStore
from security.authorization import AuthorizationService
from query.query_planner import QueryPlanner
from query.query_executor import QueryExecutor
from ai.llm_service import LLMService
from ai.response_generator import ResponseGenerator
from services.profile_service import ProfileService
from services.chat_service import ChatService
from services.admin_service import AdminService
from utils.chat_history import ChatHistoryManager
from models.user import UserRole

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("V2")

from security.authorization import AuthorizationService, AuthorizationError

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=config.FRONTEND_FOLDER, static_url_path="")
CORS(app)


@app.errorhandler(AuthorizationError)
def handle_authorization_error(e):
    return jsonify({"success": False, "error": str(e)}), 403


@app.route("/")
def serve_frontend():
    return app.send_static_file("index.html")


# ── Component Initialization ──────────────────────────────────────────────────
logger.info("Initializing Backend V2 components...")

# Data layer
excel_provider = ExcelDataProvider(
    requisition_path=config.DEFAULT_REQUISITION_EXCEL,
    employee_path=config.DEFAULT_EMPLOYEE_EXCEL,
    finance_path=config.DEFAULT_FINANCE_EXCEL,
)

# Auth layer
session_store = SessionStore()
auth_service = AuthService(data_provider=excel_provider, session_store=session_store)

# Security layer
authorization = AuthorizationService()

# Query layer
query_planner = QueryPlanner()
query_executor = QueryExecutor(data_provider=excel_provider)

# AI layer
llm_service = LLMService(
    ollama_url=config.OLLAMA_URL,
    model=config.OLLAMA_MODEL,
    max_tokens=config.LLM_MAX_TOKENS,
    temperature=config.LLM_TEMPERATURE,
    timeout_sec=config.LLM_TIMEOUT_SEC,
)
response_gen = ResponseGenerator(llm_service=llm_service, max_table_rows=config.MAX_TABLE_ROWS)

# Services
profile_service = ProfileService()
chat_history = ChatHistoryManager(history_file=config.CHAT_HISTORY_FILE)
chat_service = ChatService(
    query_planner=query_planner,
    query_executor=query_executor,
    response_generator=response_gen,
    authorization=authorization,
    profile_service=profile_service,
    chat_history=chat_history,
)
admin_service = AdminService(
    data_provider=excel_provider,
    auth_service=auth_service,
    authorization=authorization,
    upload_folder=config.UPLOAD_FOLDER,
    ollama_url=config.OLLAMA_URL,
    ollama_model=config.OLLAMA_MODEL,
    data_provider_type=config.DATA_PROVIDER_TYPE,
)

logger.info(
    f"V2 ready | model={config.OLLAMA_MODEL} | "
    f"port={config.FLASK_PORT} | provider=excel"
)


# ── Helper ────────────────────────────────────────────────────────────────────
def _resolve_user(req_data: dict):
    """Resolves CurrentUser from session token or email."""
    token = req_data.get("session_token")
    if token:
        user = auth_service.get_user_from_session(token)
        if user:
            return user
    email = req_data.get("username") or req_data.get("email")
    if email:
        return excel_provider.get_user_by_email(email)
    return None


# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["POST"])
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or data.get("email") or "").strip()
    if not username:
        return jsonify({"success": False, "error": "Email address is required."}), 400
    if not username.endswith("@motherson.com"):
        return jsonify({"success": False, "error": "Only @motherson.com accounts are authorized."}), 403

    success, user, token = auth_service.authenticate_email(username)
    if success and user:
        return jsonify({"success": True, "session_token": token, "user": user.to_api_dict()})
    return jsonify({"success": False, "error": "Authentication failed."}), 401


@app.route("/api/auth/entra_login", methods=["POST"])
def entra_login():
    data = request.get_json() or {}
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"success": False, "error": "Entra ID token is required."}), 400
    success, user, session_token = auth_service.verify_entra_token(token)
    if success and user:
        return jsonify({"success": True, "session_token": session_token, "user": user.to_api_dict()})
    return jsonify({"success": False, "error": "Entra ID authentication failed."}), 401


# ── Chat Routes ───────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    chat_id = data.get("chat_id", "")
    page = data.get("page")
    page_size = data.get("page_size")

    if not question:
        return jsonify({"error": "Question parameter is required"}), 400

    user = _resolve_user(data)
    if not user:
        return jsonify({"error": "Unauthorized session. Please login."}), 401

    if page is not None:
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
    if page_size is not None:
        try:
            page_size = int(page_size)
        except (ValueError, TypeError):
            page_size = 20

    try:
        response = chat_service.handle_message(
            question=question, user=user, chat_id=chat_id, page=page, page_size=page_size
        )
    except Exception as e:
        logger.error(f"ChatService error: {e}", exc_info=True)
        return jsonify({
            "answer": "⚠️ An internal error occurred. Please try again.",
            "sources": [],
            "unauthorized": False,
            "user_context": user.to_api_dict(),
        })

    res_data = {
        "answer": response.answer,
        "sources": response.sources,
        "unauthorized": response.unauthorized,
        "user_context": response.user_context,
        "response_type": response.response_type,
    }
    if response.pagination:
        res_data["pagination"] = response.pagination
    return jsonify(res_data)


@app.route("/new_chat", methods=["POST"])
def new_chat():
    data = request.get_json() or {}
    user = _resolve_user(data)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    user_key = f"{user.employee_id}_{user.email}"
    chat_id = chat_history.create_new_chat(user_key)
    return jsonify({"chat_id": chat_id})


@app.route("/get_history", methods=["POST"])
def get_history():
    data = request.get_json() or {}
    user = _resolve_user(data)
    if not user:
        return jsonify({})
    user_key = f"{user.employee_id}_{user.email}"
    return jsonify(chat_history.get_user_history(user_key))


@app.route("/get_chat/<chat_id>", methods=["POST"])
def get_chat(chat_id):
    data = request.get_json() or {}
    user = _resolve_user(data)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    user_key = f"{user.employee_id}_{user.email}"
    session = chat_history.get_chat(user_key, chat_id)
    if session:
        return jsonify(session)
    return jsonify({"error": "Chat session not found."}), 404


@app.route("/delete_chat/<chat_id>", methods=["POST"])
def delete_chat(chat_id):
    data = request.get_json() or {}
    user = _resolve_user(data)
    if not user:
        return jsonify({"success": False}), 401
    user_key = f"{user.employee_id}_{user.email}"
    success = chat_history.delete_chat(user_key, chat_id)
    return jsonify({"success": success})


@app.route("/reset", methods=["POST"])
def reset():
    return jsonify({"success": True})


# ── Admin Routes ──────────────────────────────────────────────────────────────

@app.route("/admin_login", methods=["POST"])
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    username = (data.get("username") or data.get("email") or "").strip()
    if not username:
        return jsonify({"success": False, "error": "Username is required."}), 400
    try:
        user = excel_provider.get_user_by_email(username)
    except Exception:
        return jsonify({"success": False, "error": "User not found."}), 404
    if user.role != UserRole.ADMIN:
        return jsonify({"success": False, "error": "Admin authorization required."}), 403
    success, user_obj, token = auth_service.authenticate_email(username)
    return jsonify({"success": True, "session_token": token, "user": user_obj.to_api_dict()})


@app.route("/admin/upload_excels", methods=["POST"])
@app.route("/api/admin/upload_excels", methods=["POST"])
def upload_excels():
    email = request.form.get("email") or request.headers.get("X-User-Email", "")
    if not email:
        return jsonify({"success": False, "error": "Admin email is required."}), 403

    try:
        user = excel_provider.get_user_by_email(email)
    except Exception:
        return jsonify({"success": False, "error": "User authentication failed."}), 403

    req_file = request.files.get("requisition_file")
    emp_file = request.files.get("employee_file")
    fin_file = request.files.get("finance_file")

    if not any([req_file, emp_file, fin_file]):
        return jsonify({"success": False, "error": "Select at least one Excel file."}), 400

    req_path = config.DEFAULT_REQUISITION_EXCEL
    emp_path = config.DEFAULT_EMPLOYEE_EXCEL
    fin_path = config.DEFAULT_FINANCE_EXCEL

    if req_file:
        req_path = os.path.join(config.UPLOAD_FOLDER, "Requisitions_Latest.xlsx")
        req_file.save(req_path)
    if emp_file:
        emp_path = os.path.join(config.UPLOAD_FOLDER, "Employees_Latest.xlsx")
        emp_file.save(emp_path)
    if fin_file:
        fin_path = os.path.join(config.UPLOAD_FOLDER, "Finance_Latest.xlsx")
        fin_file.save(fin_path)

    result = admin_service.upload_excels(user, req_path, emp_path, fin_path)
    return jsonify(result)


@app.route("/admin/status", methods=["GET"])
@app.route("/api/admin/status", methods=["GET"])
def admin_status():
    return jsonify(admin_service.get_system_status())


@app.route("/admin/api_config", methods=["GET", "POST"])
@app.route("/api/admin/api_config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json() or {}
        result = admin_service.save_api_config(
            endpoint_url=data.get("endpoint_url", "").strip(),
            api_key=data.get("api_key", "").strip(),
            active_provider=data.get("active_provider", "excel"),
        )
        return jsonify(result)
    return jsonify(admin_service.get_api_config())


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"Starting Backend V2 on port {config.FLASK_PORT}...")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False)
