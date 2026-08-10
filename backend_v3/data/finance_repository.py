"""
Backend V3 — Finance Repository
"""
from typing import Dict
from models.user import UserRole
from .excel_provider import ExcelDataProvider


class FinanceRepository:

    def __init__(self, data_provider: ExcelDataProvider):
        self.data_provider = data_provider

    def get_finance_roles(self) -> Dict[str, UserRole]:
        """Returns the dictionary mapping employee_id/email -> UserRole."""
        return self.data_provider.get_finance_roles()
