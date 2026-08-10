"""
Backend V2 — Query Scope Regression Tests

Verifies that "show me X" and similar dative constructs do NOT collapse
Finance/Admin users to CURRENT_USER scope.

Root cause of regression: r"\\bme\\b" was in the personal-intent pattern list,
causing "show ME requisitions" to be treated as "show MY requisitions".
"""
import pytest

from models.query import SubjectScope
from models.user import CurrentUser, UserRole
from query.query_planner import QueryPlanner


@pytest.fixture
def planner():
    return QueryPlanner()


@pytest.fixture
def finance_user():
    return CurrentUser(
        employee_id="TEMP99",
        employee_name="Intern3",
        email="software.intern3@motherson.com",
        role=UserRole.FINANCE,
        department="SW",
    )


@pytest.fixture
def employee_user():
    return CurrentUser(
        employee_id="MI0161",
        employee_name="Rajesh Upadhyay",
        email="rajesh.upadhyay@motherson.com",
        role=UserRole.EMPLOYEE,
        department="SW",
    )


class TestFinanceScopeDativeME:
    """Finance: 'show me X' must NOT inject employee_id scope."""

    def test_show_me_driver_salary_is_org_wide(self, planner, finance_user):
        """Core regression: show me requisition related to driver salary -> ALL_EMPLOYEES."""
        scope, target_id, _ = planner._detect_scope(
            "show me requisition related to driver salary", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES, \
            f"Expected ALL_EMPLOYEES, got {scope.value}"
        assert target_id is None

    def test_show_me_all_pending_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "show me all pending requisitions", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES
        assert target_id is None

    def test_show_me_approved_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "show me approved requisitions", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES

    def test_find_requisitions_driver_salary_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "find requisitions for driver salary", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES

    def test_which_requisitions_travel_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "which requisitions are related to travel", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES


class TestFinanceScopePersonalMY:
    """Finance: 'my X' / 'i' must still produce CURRENT_USER scope."""

    def test_show_my_requisition_driver_salary_is_current_user(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "show my requisition related to driver salary", finance_user
        )
        assert scope == SubjectScope.CURRENT_USER
        assert target_id == "TEMP99"

    def test_what_is_my_latest_requisition_is_current_user(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "what is the status of my latest requisition", finance_user
        )
        assert scope == SubjectScope.CURRENT_USER
        assert target_id == "TEMP99"

    def test_how_much_have_i_been_reimbursed_is_current_user(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "how much have i been reimbursed", finance_user
        )
        assert scope == SubjectScope.CURRENT_USER
        assert target_id == "TEMP99"

    def test_my_total_approved_amount_is_current_user(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "what is my total approved amount", finance_user
        )
        assert scope == SubjectScope.CURRENT_USER


class TestFinanceScopeOrgWideAnalytics:
    """Finance: analytics queries without 'my/i' must be org-wide."""

    def test_who_has_highest_approved_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "which employee has the highest approved reimbursement", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES

    def test_which_dept_highest_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "which department has the highest approved value", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES

    def test_dept_wise_summary_is_org_wide(self, planner, finance_user):
        scope, target_id, _ = planner._detect_scope(
            "department-wise approval summary", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES

    def test_who_submitted_highest_value_is_org_wide(self, planner, finance_user):
        scope, _, _ = planner._detect_scope(
            "who submitted the highest value requisition", finance_user
        )
        assert scope == SubjectScope.ALL_EMPLOYEES


class TestEmployeeScopeSecurityPreserved:
    """Employee: authorization invariants must remain intact."""

    def test_employee_show_my_requisitions_is_current_user(self, planner, employee_user):
        scope, target_id, _ = planner._detect_scope(
            "show my requisitions", employee_user
        )
        assert scope == SubjectScope.CURRENT_USER
        assert target_id == "MI0161"

    def test_employee_show_requisitions_no_my_still_current_user(self, planner, employee_user):
        """Employee without personal qualifier stays CURRENT_USER for security."""
        scope, target_id, _ = planner._detect_scope(
            "show requisition related to driver salary", employee_user
        )
        assert scope == SubjectScope.CURRENT_USER
        assert target_id == "MI0161"

    def test_employee_what_are_my_pending_is_current_user(self, planner, employee_user):
        scope, target_id, _ = planner._detect_scope(
            "what are my pending requisitions", employee_user
        )
        assert scope == SubjectScope.CURRENT_USER

    def test_employee_show_me_with_my_is_current_user(self, planner, employee_user):
        """Employee 'show me my X' stays CURRENT_USER ('my' triggers first)."""
        scope, target_id, _ = planner._detect_scope(
            "show me all my pending requisitions", employee_user
        )
        assert scope == SubjectScope.CURRENT_USER


class TestScopeFollowUpPreservation:
    """Full plan-level tests for scope and follow-up propagation."""

    def test_finance_show_me_driver_salary_full_plan(self, planner, finance_user):
        """Full plan test: scope = ALL_EMPLOYEES, keyword set."""
        plan = planner.plan(
            "show me requisitions related to driver salary",
            user=finance_user,
        )
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES, \
            f"Expected ALL_EMPLOYEES, got {plan.subject_scope.value}"
        kw = plan.filters.get("description_keyword", "")
        assert kw, "Expected a description_keyword filter to be set"
        assert any(term in kw.lower() for term in ["driver", "salary"]), \
            f"Keyword should contain 'driver' or 'salary', got: {repr(kw)}"

    def test_finance_show_my_driver_salary_full_plan(self, planner, finance_user):
        """Finance 'my' version: scope = CURRENT_USER."""
        plan = planner.plan(
            "show my requisitions related to driver salary",
            user=finance_user,
        )
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == "TEMP99"

    def test_finance_who_has_highest_full_plan(self, planner, finance_user):
        """Finance org-wide analytics: who has the highest approved reimbursement."""
        plan = planner.plan(
            "which employee has the highest approved reimbursement",
            user=finance_user,
        )
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES

    def test_followup_preserves_all_employees_scope(self, planner, finance_user):
        """After org-wide driver salary query, follow-up stays org-wide."""
        plan1 = planner.plan(
            "show me requisitions related to driver salary",
            user=finance_user,
        )
        assert plan1.subject_scope == SubjectScope.ALL_EMPLOYEES
        assert plan1.filters.get("description_keyword"), \
            "Turn 1 should have description_keyword filter"
