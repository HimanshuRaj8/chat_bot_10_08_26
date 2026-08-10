"""
Backend V3 — Authorization Scope Boundary Tests
"""
import pytest
from models.user import CurrentUser, UserRole
from models.query import QueryPlan, SubjectScope, QueryIntent
from auth.authorization import AuthorizationService, AuthorizationError


def test_employee_scope_is_forced(auth_gate, employee_user):
    # Employee tries to request ALL_EMPLOYEES scope
    plan = QueryPlan(intent=QueryIntent.LIST_REQUISITIONS, subject_scope=SubjectScope.ALL_EMPLOYEES)
    
    # Auth validation should inject/force CURRENT_USER scope
    auth_gate.validate(employee_user, plan)
    assert plan.subject_scope == SubjectScope.CURRENT_USER
    assert plan.target_employee_id == employee_user.employee_id


def test_employee_cannot_query_another_employee_by_id(auth_gate, employee_user):
    # Rahul Karn tries to request Ajay Tomar's ID
    plan = QueryPlan(
        intent=QueryIntent.LIST_REQUISITIONS,
        subject_scope=SubjectScope.SPECIFIC_EMPLOYEE,
        target_employee_id="MI0004",  # Ajay Tomar
    )
    with pytest.raises(AuthorizationError) as exc_info:
        auth_gate.validate(employee_user, plan)
    assert "not authorized" in str(exc_info.value)


def test_employee_cannot_query_another_employee_by_name(auth_gate, employee_user):
    # Rahul Karn tries to search for 'Ajay Tomar'
    plan = QueryPlan(
        intent=QueryIntent.LIST_REQUISITIONS,
        subject_scope=SubjectScope.SPECIFIC_EMPLOYEE,
        target_employee_name="Ajay Tomar",
    )
    with pytest.raises(AuthorizationError) as exc_info:
        auth_gate.validate(employee_user, plan)
    assert "not authorized" in str(exc_info.value)


def test_finance_can_query_specific_employee(auth_gate, finance_user):
    # Finance user asks for Ajay Tomar's claims
    plan = QueryPlan(
        intent=QueryIntent.LIST_REQUISITIONS,
        subject_scope=SubjectScope.SPECIFIC_EMPLOYEE,
        target_employee_id="MI0004",
        target_employee_name="Ajay Tomar",
    )
    # Should not raise AuthorizationError
    auth_gate.validate(finance_user, plan)
    assert plan.subject_scope == SubjectScope.SPECIFIC_EMPLOYEE
    assert plan.target_employee_id == "MI0004"


def test_finance_can_query_all_employees(auth_gate, finance_user):
    # Finance queries organization-wide totals
    plan = QueryPlan(
        intent=QueryIntent.ANALYTICS,
        subject_scope=SubjectScope.ALL_EMPLOYEES,
        aggregation="SUM",
    )
    auth_gate.validate(finance_user, plan)
    assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES
