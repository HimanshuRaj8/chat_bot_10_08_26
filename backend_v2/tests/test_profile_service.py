"""
Test: ProfileService
Verifies that identity queries return authenticated session data — never database data.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from models.query import QueryPlan, QueryIntent, SubjectScope
from services.profile_service import ProfileService


@pytest.fixture
def profile_svc():
    return ProfileService()


def _plan(metric: str) -> QueryPlan:
    p = QueryPlan()
    p.intent = QueryIntent.PROFILE
    p.subject_scope = SubjectScope.CURRENT_USER
    p.profile_metric = metric
    return p


class TestProfileService:

    def test_employee_id_returns_session_id(self, profile_svc, employee_user):
        answer = profile_svc.answer(_plan("EmployeeID"), employee_user)
        assert "TEMP99" in answer
        # Must NOT contain another employee's ID
        assert "MI0161" not in answer
        assert "MI0168" not in answer

    def test_name_returns_session_name(self, profile_svc, employee_user):
        answer = profile_svc.answer(_plan("Name"), employee_user)
        assert "Intern3" in answer
        assert "Prashant" not in answer
        assert "Rahul" not in answer

    def test_role_returns_session_role(self, profile_svc, employee_user):
        answer = profile_svc.answer(_plan("Role"), employee_user)
        assert "Employee" in answer

    def test_department_returns_session_dept(self, profile_svc, employee_user):
        answer = profile_svc.answer(_plan("Department"), employee_user)
        assert "SW" in answer

    def test_email_returns_session_email(self, profile_svc, employee_user):
        answer = profile_svc.answer(_plan("Email"), employee_user)
        assert "intern3@motherson.com" in answer

    def test_full_profile_contains_all_fields(self, profile_svc, employee_user):
        answer = profile_svc.answer(_plan("FullProfile"), employee_user)
        assert "TEMP99" in answer
        assert "Intern3" in answer
        assert "SW" in answer
        assert "Employee" in answer

    def test_finance_user_profile(self, profile_svc, finance_user):
        answer = profile_svc.answer(_plan("EmployeeID"), finance_user)
        assert "FIN001" in answer
        assert "TEMP99" not in answer

    def test_admin_user_profile(self, profile_svc, admin_user):
        answer = profile_svc.answer(_plan("Role"), admin_user)
        assert "Admin" in answer
