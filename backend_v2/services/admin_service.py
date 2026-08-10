"""
Backend V2 — Admin Service

Handles Excel uploads, data refresh, and system status reporting.
All admin actions require the Admin role — enforced via AuthorizationService.
"""
import logging
from typing import Dict, Any

from data.base_provider import DataProvider
from security.authorization import AuthorizationService
from models.user import CurrentUser

logger = logging.getLogger(__name__)


class AdminService:

    def __init__(
        self,
        data_provider: DataProvider,
        auth_service: "AuthService",
        authorization: AuthorizationService,
        upload_folder: str,
        ollama_url: str,
        ollama_model: str,
        data_provider_type: str,
    ):
        self.data_provider = data_provider
        self.auth_service = auth_service
        self.authorization = authorization
        self.upload_folder = upload_folder
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.data_provider_type = data_provider_type

        # Mutable API config (for EASY API migration)
        self.api_config: Dict[str, str] = {
            "endpoint_url": "",
            "api_key": "",
            "active_provider": data_provider_type,
        }

    def get_system_status(self) -> Dict[str, Any]:
        """Returns current system status for the admin dashboard."""
        try:
            req_count = len(self.data_provider.get_all_requisitions())
        except Exception:
            req_count = 0
        return {
            "status": "Online",
            "chroma_collection": "N/A (V2 - No ChromaDB)",
            "indexed_records": req_count,
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "embedding_model": "N/A (V2 - No Embeddings)",
            "data_provider_type": self.api_config["active_provider"],
        }

    def upload_excels(
        self,
        user: CurrentUser,
        req_path: str,
        emp_path: str,
        fin_path: str,
    ) -> Dict[str, Any]:
        """
        Reloads all data from new Excel file paths.
        Admin-only. Returns count of records loaded.
        """
        self.authorization.require_admin(user, "Excel upload")
        try:
            count = self.data_provider.refresh(req_path, emp_path, fin_path)
            logger.info(f"Admin {user.employee_id} uploaded new datasets: {count} requisitions loaded.")
            return {
                "success": True,
                "message": f"Dataset reloaded successfully. {count} requisition records available.",
                "indexed_chunks": count,
            }
        except Exception as e:
            logger.error(f"Excel upload failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_api_config(self) -> Dict[str, str]:
        return dict(self.api_config)

    def save_api_config(self, endpoint_url: str, api_key: str, active_provider: str) -> Dict[str, Any]:
        self.api_config["endpoint_url"] = endpoint_url
        self.api_config["api_key"] = api_key
        self.api_config["active_provider"] = active_provider
        return {"success": True, "config": self.api_config}
