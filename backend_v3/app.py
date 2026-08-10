"""
Backend V3 — Flask Application Server
"""
import os
import sys
import uuid
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, request, jsonify, session
from flask_cors import CORS

import config
from auth.authentication import AuthService
from auth.session_store import SessionStore
from auth.credentials import CredentialsManager
from auth.authorization import AuthorizationService
from context.conversation import ConversationManager
from data.excel_provider import ExcelDataProvider
from data.employee_repository import EmployeeRepository
from data.requisition_repository import RequisitionRepository
from query.parser import QueryParser
from query.validator import QueryPlanValidator
from query.entity_resolver import EntityResolver
from query.query_executor import QueryExecutor
from llm.client import LLMClient
from llm.response_generator import ResponseGenerator
from services.chat_service import ChatService
from utils.chat_history import ChatHistoryManager
from models.query import SubjectScope

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (V3) %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── App & CORS Setup ──────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=config.FRONTEND_FOLDER, static_url_path="")
app.secret_key = config.SECRET_KEY
CORS(app, supports_credentials=True, origins=["*"])


@app.route("/")
def serve_frontend():
    return app.send_static_file("index.html")

# ── Dependency Injection ──────────────────────────────────────────────────────
data_provider = ExcelDataProvider(
    requisition_path=config.DEFAULT_REQUISITION_EXCEL,
    employee_path=config.DEFAULT_EMPLOYEE_EXCEL,
    finance_path=config.DEFAULT_FINANCE_EXCEL,
)

employee_repo = EmployeeRepository(data_provider)
requisition_repo = RequisitionRepository(data_provider)
session_store = SessionStore()
credentials_manager = CredentialsManager(
    data_file=os.path.join(config.BASE_DIR, "backend_v3", "data", "user_credentials.json"),
    data_provider=data_provider
)

auth_service = AuthService(data_provider, session_store, credentials_manager=credentials_manager)
authorization_service = AuthorizationService()
conversation_manager = ConversationManager()
history_manager = ChatHistoryManager(os.path.join(config.BASE_DIR, "chat_history.json"))

# Ollama Integration
llm_client = LLMClient(
    ollama_url=config.OLLAMA_URL,
    model=config.OLLAMA_MODEL,
    max_tokens=config.LLM_MAX_TOKENS,
    temperature=config.LLM_TEMPERATURE,
    timeout_sec=config.LLM_TIMEOUT_SEC,
)

query_parser = QueryParser(llm_client)
query_validator = QueryPlanValidator()
entity_resolver = EntityResolver(employee_repo, requisition_repo)
query_executor = QueryExecutor(requisition_repo, employee_repo)
response_generator = ResponseGenerator(llm_client)

chat_service = ChatService(
    query_parser=query_parser,
    query_validator=query_validator,
    authorization_service=authorization_service,
    entity_resolver=entity_resolver,
    query_executor=query_executor,
    response_generator=response_generator,
    conversation_manager=conversation_manager,
)


def get_authenticated_user() -> tuple:
    """Helper to retrieve user object from headers, JSON body, or session cookies."""
    token = request.headers.get("Authorization")
    if not token:
        # Check JSON payload
        try:
            req_data = request.get_json(silent=True) or {}
            token = req_data.get("session_token")
        except Exception:
            token = None
            
    if not token and "session_token" in session:
        token = session["session_token"]

    if not token:
        return None, "Unauthorized: Session token missing."

    # Strip Bearer if present
    if token.startswith("Bearer "):
        token = token[7:]

    user = auth_service.get_user_from_session(token)
    if not user:
        return None, "Unauthorized: Invalid or expired session."

    return user, None


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "version": "3.0.0",
        "ollama_connected": llm_client.is_available(),
        "active_sessions": session_store.count(),
    })


@app.route("/login", methods=["POST"])
def login():
    try:
        req_data = request.get_json() or {}
        email = (req_data.get("email") or req_data.get("username") or "").strip()
        password = req_data.get("password")

        if not app.config.get("TESTING") and not password:
            return jsonify({"success": False, "error": "Password is required."}), 400

        success, user, token = auth_service.authenticate_email(email, password=password)
        if not success:
            return jsonify({"success": False, "error": token}), 401

        session["session_token"] = token
        return jsonify({
            "success": True,
            "session_token": token,
            "profile": user.to_api_dict(),
            "user": user.to_api_dict(),
        })
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return jsonify({"success": False, "error": "Internal authentication error."}), 500


@app.route("/chat", methods=["POST"])
def chat():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"success": False, "error": err}), 401

    try:
        req_data = request.get_json() or {}
        message = (req_data.get("message") or req_data.get("question") or "").strip()
        chat_id = req_data.get("chat_id", "").strip()
        page = int(req_data.get("page", 1))
        page_size = int(req_data.get("page_size", config.DEFAULT_PAGE_SIZE))

        if not message:
            return jsonify({"success": False, "error": "Message content is required."}), 400
        if not chat_id:
            chat_id = "default_chat_session"

        # Log User query to history manager
        user_key = f"{user.employee_id}_{user.email}"
        history_manager.add_message(user_key, chat_id, "user", message)

        # Execute Chat Orchestrator
        result = chat_service.handle_message(
            message=message,
            user=user,
            chat_id=chat_id,
            page=page,
            page_size=page_size,
        )

        # Log Assistant response to history manager
        if result.success:
            history_manager.add_message(user_key, chat_id, "assistant", result.message)

        # Build response compatible with V2 and V3 frontend expectations
        res_dict = result.to_dict()
        res_dict["answer"] = result.message
        res_dict["unauthorized"] = not result.success and result.response_type.value == "ERROR"
        res_dict["user_context"] = user.to_api_dict()
        
        return jsonify(res_dict)

    except Exception as e:
        logger.error(f"Chat execution failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "I couldn't process your request due to a server error.",
            "answer": "⚠️ I couldn't process your request due to a server error.",
        }), 500


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"success": False, "error": err}), 401

    # Verify Admin status
    try:
        authorization_service.require_admin(user, "dataset upload")
    except Exception as ae:
        return jsonify({"success": False, "error": str(ae)}), 403

    try:
        file_type = request.form.get("file_type")
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file payload."}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "error": "Empty filename."}), 400

        filename = secure_filename(file.filename)
        os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
        save_path = os.path.join(config.UPLOAD_FOLDER, filename)
        file.save(save_path)

        # Swaps data structures atomically
        if file_type == "requisitions":
            count = data_provider.refresh(requisition_path=save_path, employee_path="", finance_path="")
        elif file_type == "employees":
            count = data_provider.refresh(requisition_path="", employee_path=save_path, finance_path="")
        elif file_type == "finance":
            count = data_provider.refresh(requisition_path="", employee_path="", finance_path=save_path)
        else:
            return jsonify({"success": False, "error": "Invalid file_type identifier."}), 400

        return jsonify({
            "success": True,
            "message": f"Successfully reloaded dataset. {count} active requisition records loaded.",
        })

    except Exception as e:
        logger.error(f"Admin file upload failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Failed to refresh dataset: {e}",
        }), 500

@app.route("/admin_login", methods=["POST"])
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    try:
        req_data = request.get_json() or {}
        email = (req_data.get("username") or req_data.get("email") or "").strip()
        password = req_data.get("password")

        if not email:
            return jsonify({"success": False, "error": "Username/Email is required."}), 400

        if not app.config.get("TESTING") and not password:
            return jsonify({"success": False, "error": "Password is required."}), 400

        success, user, token = auth_service.authenticate_email(email, password=password)
        if not success:
            return jsonify({"success": False, "error": token}), 401

        if not user.is_admin:
            return jsonify({"success": False, "error": "Admin authorization required."}), 403

        session["session_token"] = token
        return jsonify({
            "success": True,
            "session_token": token,
            "user": user.to_api_dict(),
        })
    except Exception as e:
        logger.error(f"Admin login failed: {e}")
        return jsonify({"success": False, "error": "Internal admin authentication error."}), 500


@app.route("/admin/status", methods=["GET"])
@app.route("/api/admin/status", methods=["GET"])
def admin_status():
    try:
        _, req_count = requisition_repo.get_requisitions(
            scope=SubjectScope.ALL_EMPLOYEES,
            page=1,
            page_size=1,
        )
    except Exception:
        req_count = 0
    return jsonify({
        "status": "Online",
        "chroma_collection": "N/A (V3)",
        "indexed_records": req_count,
        "ollama_url": config.OLLAMA_URL,
        "ollama_model": config.OLLAMA_MODEL,
        "embedding_model": "N/A (V3)",
        "data_provider_type": "excel",
    })


@app.route("/admin/users", methods=["GET"])
@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"success": False, "error": err}), 401
    try:
        authorization_service.require_admin(user, "view users")
    except Exception as ae:
        return jsonify({"success": False, "error": str(ae)}), 403

    users = credentials_manager.list_users()
    return jsonify({"success": True, "users": users})


@app.route("/admin/users/create", methods=["POST"])
@app.route("/api/admin/users/create", methods=["POST"])
def admin_create_user():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"success": False, "error": err}), 401
    try:
        authorization_service.require_admin(user, "create user")
    except Exception as ae:
        return jsonify({"success": False, "error": str(ae)}), 403

    req_data = request.get_json() or {}
    email = req_data.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": "Email is required."}), 400
    if not email.endswith(AuthService.ALLOWED_DOMAIN):
        return jsonify({"success": False, "error": f"Only {AuthService.ALLOWED_DOMAIN} emails allowed."}), 400

    password = credentials_manager.add_user(email)
    return jsonify({"success": True, "email": email, "password": password})


@app.route("/admin/users/change_password", methods=["POST"])
@app.route("/api/admin/users/change_password", methods=["POST"])
def admin_change_password():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"success": False, "error": err}), 401
    try:
        authorization_service.require_admin(user, "change password")
    except Exception as ae:
        return jsonify({"success": False, "error": str(ae)}), 403

    req_data = request.get_json() or {}
    email = req_data.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": "Email is required."}), 400

    # Prevent changing admin password
    try:
        target_user = data_provider.get_user_by_email(email)
        if target_user and target_user.is_admin:
            return jsonify({"success": False, "error": "🔒 Access denied. Admin passwords cannot be modified."}), 403
    except Exception:
        pass
    if email == "admin@motherson.com":
        return jsonify({"success": False, "error": "🔒 Access denied. Admin passwords cannot be modified."}), 403

    if email not in credentials_manager.credentials:
        return jsonify({"success": False, "error": "User not found."}), 404

    password = credentials_manager.change_password(email)
    return jsonify({"success": True, "email": email, "password": password})


@app.route("/admin/users/delete", methods=["POST"])
@app.route("/api/admin/users/delete", methods=["POST"])
def admin_delete_user():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"success": False, "error": err}), 401
    try:
        authorization_service.require_admin(user, "delete user")
    except Exception as ae:
        return jsonify({"success": False, "error": str(ae)}), 403

    req_data = request.get_json() or {}
    email = req_data.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": "Email is required."}), 400

    # Prevent deleting admin users
    try:
        target_user = data_provider.get_user_by_email(email)
        if target_user and target_user.is_admin:
            return jsonify({"success": False, "error": "🔒 Access denied. Admin accounts cannot be deleted."}), 403
    except Exception:
        pass
    if email == "admin@motherson.com":
        return jsonify({"success": False, "error": "🔒 Access denied. Admin accounts cannot be deleted."}), 403

    deleted = credentials_manager.delete_user(email)
    if not deleted:
        return jsonify({"success": False, "error": "User not found."}), 404

    return jsonify({"success": True, "message": "User deleted successfully."})


@app.route("/admin/users/download_csv", methods=["GET"])
@app.route("/api/admin/users/download_csv", methods=["GET"])
def admin_download_csv():
    token = request.args.get("token") or request.headers.get("Authorization")
    if token and token.startswith("Bearer "):
        token = token[7:]
    
    if not token:
        user, err = get_authenticated_user()
    else:
        user = auth_service.get_user_from_session(token)
        err = None if user else "Unauthorized"

    if err or not user:
        return "Unauthorized", 401
        
    try:
        authorization_service.require_admin(user, "download CSV")
    except Exception as ae:
        return str(ae), 403

    import csv
    import io
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Password"])
    
    users = credentials_manager.list_users()
    for u in users:
        writer.writerow([u["email"], u["password"]])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=employees_passwords.csv"
    return response


@app.route("/admin/upload_excels", methods=["POST"])
@app.route("/api/admin/upload_excels", methods=["POST"])
def upload_excels():
    email = request.form.get("email") or request.headers.get("X-User-Email", "")
    if not email:
        return jsonify({"success": False, "error": "Admin email is required."}), 403

    try:
        user = employee_repo.get_by_email(email)
        if not user or not user.is_admin:
            return jsonify({"success": False, "error": "Admin authorization required."}), 403
    except Exception:
        return jsonify({"success": False, "error": "Admin authorization failed."}), 403

    req_file = request.files.get("requisition_file")
    emp_file = request.files.get("employee_file")
    fin_file = request.files.get("finance_file")

    if not any([req_file, emp_file, fin_file]):
        return jsonify({"success": False, "error": "Select at least one Excel file."}), 400

    try:
        os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
        req_path = ""
        emp_path = ""
        fin_path = ""

        if req_file:
            req_path = os.path.join(config.UPLOAD_FOLDER, "Requisitions_Latest.xlsx")
            req_file.save(req_path)
        if emp_file:
            emp_path = os.path.join(config.UPLOAD_FOLDER, "Employees_Latest.xlsx")
            emp_file.save(emp_path)
        if fin_file:
            fin_path = os.path.join(config.UPLOAD_FOLDER, "Finance_Latest.xlsx")
            fin_file.save(fin_path)

        count = data_provider.refresh(
            requisition_path=req_path,
            employee_path=emp_path,
            finance_path=fin_path
        )
        return jsonify({
            "success": True,
            "message": f"Successfully reloaded dataset. {count} active records loaded.",
        })
    except Exception as e:
        logger.error(f"Admin Excel upload failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Reload failed: {e}"}), 500
@app.route("/new_chat", methods=["POST"])
def new_chat():
    user, err = get_authenticated_user()
    if err:
        return jsonify({"error": "Unauthorized"}), 401
    user_key = f"{user.employee_id}_{user.email}"
    chat_id = history_manager.create_new_chat(user_key)
    return jsonify({"chat_id": chat_id})


@app.route("/get_history", methods=["POST"])
def get_history():
    user, err = get_authenticated_user()
    if err:
        return jsonify({})
    user_key = f"{user.employee_id}_{user.email}"
    history = history_manager.get_user_history(user_key)
    return jsonify(history)


@app.route("/get_chat/<chat_id>", methods=["POST"])
def get_chat(chat_id):
    user, err = get_authenticated_user()
    if err:
        return jsonify({"error": "Unauthorized"}), 401
    user_key = f"{user.employee_id}_{user.email}"
    chat = history_manager.get_chat(user_key, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    return jsonify(chat)


@app.route("/delete_chat", methods=["POST"])
@app.route("/delete_chat/<chat_id>", methods=["POST"])
def delete_chat(chat_id=None):
    user, err = get_authenticated_user()
    if err:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    chat_id = chat_id or data.get("chat_id")
    if not chat_id:
        return jsonify({"success": False, "error": "chat_id is required"}), 400
    user_key = f"{user.employee_id}_{user.email}"
    deleted = history_manager.delete_chat(user_key, chat_id)
    return jsonify({"success": deleted})



@app.route("/reset", methods=["POST"])
def reset():
    return jsonify({"success": True})


def secure_filename(filename: str) -> str:
    """Basic secure filename sanitizer."""
    return os.path.basename(filename).replace("..", "").replace("/", "")


if __name__ == "__main__":
    logger.info(f"Starting Backend V3 on port {config.FLASK_PORT}...")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False)
