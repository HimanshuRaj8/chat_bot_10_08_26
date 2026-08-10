"""
Backend V2 — User and Role Models
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    EMPLOYEE = "Employee"
    FINANCE = "Finance"
    ADMIN = "Admin"


@dataclass
class CurrentUser:
    """
    Canonical authenticated user object. Set once from the verified session.
    This is the ONLY source of truth for identity — never inferred from data.
    """
    employee_id: str
    employee_name: str
    email: str
    role: UserRole = UserRole.EMPLOYEE
    department: Optional[str] = None
    location: Optional[str] = None
    teams_name: Optional[str] = None

    @property
    def is_finance(self) -> bool:
        return self.role in (UserRole.FINANCE, UserRole.ADMIN)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def to_api_dict(self) -> dict:
        return {
            "name": self.employee_name,
            "email": self.email,
            "employee_id": self.employee_id,
            "role": self.role.value,
            "department": self.department or "N/A",
        }
