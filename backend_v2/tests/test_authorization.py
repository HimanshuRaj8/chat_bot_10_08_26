"""
Test: Authorization Service
Verifies role-based access control rules.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from security.authorization import AuthorizationService, AuthorizationError
from models.query import QueryPlan, SubjectScope


@pytest.fixture
def auth():
    return AuthorizationService()


def _plan_with_scope(scope: SubjectScope, target_id=None) -> QueryPlan:
    p = QueryPlan()
    p.subject_scope = scope
    p.target_employee_id = target_id
    return p


class TestCurrentUserScope:
    def test_employee_can_query_self(self, auth, employee_user):
        plan = _plan_with_scope(SubjectScope.CURRENT_USER)
        # Should not raise
        auth.validate(employee_user, plan)

    def test_finance_can_query_self(self, auth, finance_user):
        plan = _plan_with_scope(SubjectScope.CURRENT_USER)
        auth.validate(finance_user, plan)


class TestSpecificEmployeeScope:
    def test_employee_blocked_from_other_employee(self, auth, employee_user):
        plan = _plan_with_scope(SubjectScope.SPECIFIC_EMPLOYEE, "MI0168")
        with pytest.raises(AuthorizationError) as exc_info:
            auth.validate(employee_user, plan)
        assert "Access denied" in str(exc_info.value)

    def test_finance_can_query_specific_employee(self, auth, finance_user):
        plan = _plan_with_scope(SubjectScope.SPECIFIC_EMPLOYEE, "MI0168")
        # Should not raise
        auth.validate(finance_user, plan)

    def test_admin_can_query_specific_employee(self, auth, admin_user):
        plan = _plan_with_scope(SubjectScope.SPECIFIC_EMPLOYEE, "MI0168")
        auth.validate(admin_user, plan)


class TestAllEmployeesScope:
    def test_employee_blocked_from_all(self, auth, employee_user):
        plan = _plan_with_scope(SubjectScope.ALL_EMPLOYEES)
        with pytest.raises(AuthorizationError):
            auth.validate(employee_user, plan)

    def test_finance_can_query_all(self, auth, finance_user):
        plan = _plan_with_scope(SubjectScope.ALL_EMPLOYEES)
        auth.validate(finance_user, plan)

    def test_admin_can_query_all(self, auth, admin_user):
        plan = _plan_with_scope(SubjectScope.ALL_EMPLOYEES)
        auth.validate(admin_user, plan)


class TestAdminOnlyActions:
    def test_non_admin_blocked_from_admin_action(self, auth, employee_user):
        with pytest.raises(AuthorizationError) as exc_info:
            auth.require_admin(employee_user, "Excel upload")
        assert "Admin" in str(exc_info.value)

    def test_finance_blocked_from_admin_action(self, auth, finance_user):
        with pytest.raises(AuthorizationError):
            auth.require_admin(finance_user, "Excel upload")

    def test_admin_can_do_admin_action(self, auth, admin_user):
        auth.require_admin(admin_user, "Excel upload")  # Should not raise
