"""
Backend V3 — Employee Repository
"""
from typing import List, Optional
from models.user import CurrentUser
from .excel_provider import ExcelDataProvider


class EmployeeRepository:

    def __init__(self, data_provider: ExcelDataProvider):
        self.data_provider = data_provider

    def get_by_id(self, employee_id: str) -> Optional[CurrentUser]:
        """Resolves a user by employee ID."""
        return self.data_provider.get_user_by_employee_id(employee_id)

    def get_by_email(self, email: str) -> CurrentUser:
        """Resolves a user by corporate email address."""
        return self.data_provider.get_user_by_email(email)

    def resolve_by_name(self, name_query: str) -> List[CurrentUser]:
        """
        Resolves an employee name against the employee directory.
        Returns a list of all matching users for case-insensitive partial names.
        """
        query_clean = name_query.strip().lower()
        if not query_clean:
            return []

        matches = []
        employees = self.data_provider.get_all_employees()
        
        # Exact match check first
        for emp_id, user in employees.items():
            if user.employee_name.strip().lower() == query_clean:
                matches.append(self.data_provider.get_user_by_employee_id(emp_id))
        
        if matches:
            return matches

        # Token-based match (all words in query must be in name)
        query_words = query_clean.split()
        for emp_id, user in employees.items():
            emp_name_lower = user.employee_name.strip().lower()
            teams_name_lower = user.teams_name.strip().lower() if user.teams_name else ""
            
            # Check if all query words exist in employee name or teams name
            match_found = True
            for word in query_words:
                if (word not in emp_name_lower) and (word not in teams_name_lower):
                    match_found = False
                    break
            
            if match_found:
                matches.append(self.data_provider.get_user_by_employee_id(emp_id))

        return matches
