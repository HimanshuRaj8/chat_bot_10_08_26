"""
Backend V2 — Abstract DataProvider Interface

All data sources (Excel, Easy API) must implement this.
This enables zero-code migration when the API endpoint is available.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd
from models.user import CurrentUser
from models.requisition import RequisitionRecord


class DataProvider(ABC):

    @abstractmethod
    def get_requisitions_df(self) -> pd.DataFrame:
        """
        Returns the full normalized requisitions DataFrame.
        Called once per query execution by QueryExecutor.
        Must never be called per-message — cache at startup.
        """
        ...

    @abstractmethod
    def get_all_requisitions(self) -> List[RequisitionRecord]:
        """Returns list of all requisition records."""
        ...

    @abstractmethod
    def get_user_by_email(self, email: str) -> CurrentUser:
        """Resolves User object from corporate email. Raises ValueError if not found."""
        ...

    @abstractmethod
    def get_user_by_employee_id(self, employee_id: str) -> Optional[CurrentUser]:
        """Resolves User object from employee ID. Returns None if not found."""
        ...

    @abstractmethod
    def refresh(self, requisition_path: str, employee_path: str, finance_path: str) -> int:
        """
        Reloads all data from new files. Returns count of requisitions loaded.
        Called by AdminService after Excel upload.
        """
        ...
