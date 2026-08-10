"""
Backend V2 — Modular EASY API Data Provider Interface (Future Extension)

When connecting directly to the Approval System EASY APIs,
only this class needs to be configured. The rest of the AI chatbot logic,
authorization pipeline, query planner, response generator, and UI remain unchanged.
"""
import logging
import pandas as pd
from typing import Dict, Optional
from data.base_provider import BaseDataProvider
from models.user import CurrentUser, UserRole

logger = logging.getLogger(__name__)


class EasyApiDataProvider(BaseDataProvider):
    """
    Data Provider interface for direct EASY API integration.
    """
    def __init__(self, api_endpoint: str = "", api_key: str = ""):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self._cached_df: Optional[pd.DataFrame] = None
        self._employees: Dict[str, CurrentUser] = {}

    def get_requisitions_df(self) -> pd.DataFrame:
        if self._cached_df is not None:
            return self._cached_df
        logger.info("EasyApiDataProvider: Fetching requisitions from EASY API endpoint...")
        # TODO: Implement API HTTP GET call to EASY API endpoint when credentials are provided
        self._cached_df = pd.DataFrame()
        return self._cached_df

    def get_user_by_email(self, email: str) -> CurrentUser:
        logger.info(f"EasyApiDataProvider: Resolving user {email} via EASY API...")
        if email in self._employees:
            return self._employees[email]
        
        name = email.split("@")[0].replace(".", " ").title()
        emp_id = email.split("@")[0].upper()
        user = CurrentUser(
            employee_id=emp_id,
            employee_name=name,
            email=email,
            department="General",
            role=UserRole.EMPLOYEE,
        )
        return user

    def reload(self):
        self._cached_df = None
        self._employees.clear()
        logger.info("EasyApiDataProvider cache cleared.")
