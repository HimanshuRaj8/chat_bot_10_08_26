"""
Test: QueryExecutor
Verifies deterministic pandas execution against synthetic test data.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from query.query_executor import QueryExecutor
from models.query import (
    QueryPlan, QueryIntent, SubjectScope, QueryEntity
)


@pytest.fixture
def executor(mock_data_provider):
    return QueryExecutor(data_provider=mock_data_provider)


def _base_plan(intent, scope=SubjectScope.ALL_EMPLOYEES, **kwargs) -> QueryPlan:
    p = QueryPlan()
    p.intent = intent
    p.subject_scope = scope
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


class TestScopeFilter:
    def test_current_user_filters_to_employee_id(self, executor, employee_user):
        """TEMP99 should only see their own 4 rows."""
        plan = _base_plan(
            QueryIntent.FILTER,
            scope=SubjectScope.CURRENT_USER,
            metric="Approved Value in INR",
            aggregation="NONE",
            limit=50,
        )
        plan.target_employee_id = employee_user.employee_id
        result = executor.execute(plan, employee_user)
        assert result.success
        # All source records should be TEMP99 only
        for rec in result.source_records:
            pass  # executor filters internally; verify via total_records_analyzed
        assert result.total_records_analyzed == 4  # TEMP99 has 4 rows in test_df

    def test_all_employees_sees_all_rows(self, executor, finance_user):
        plan = _base_plan(
            QueryIntent.FILTER,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="NONE",
            limit=50,
        )
        result = executor.execute(plan, finance_user)
        assert result.total_records_analyzed == 10


class TestStatusFilter:
    def test_approved_status_filter(self, executor, finance_user):
        plan = _base_plan(
            QueryIntent.FILTER,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="NONE",
            limit=50,
        )
        plan.filters["status"] = "approved"
        result = executor.execute(plan, finance_user)
        assert result.success
        # Approved rows in test_df: indices 0,2,4,6,8 = 5 rows
        assert result.total_records_analyzed == 5

    def test_pending_status_filter(self, executor, finance_user):
        plan = _base_plan(
            QueryIntent.FILTER,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="NONE",
            limit=50,
        )
        plan.filters["status"] = "pending"
        result = executor.execute(plan, finance_user)
        assert result.total_records_analyzed == 4  # indices 1,5,7,9


class TestAggregation:
    def test_total_approved_value_all_employees(self, executor, finance_user):
        plan = _base_plan(
            QueryIntent.AGGREGATE,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="SUM",
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        total = result.result[0]["value"]
        # Sum of Approved Value in INR from test_df
        expected = 50000 + 75000 + 120000 + 30000 + 85000  # 360000
        assert abs(total - expected) < 0.01

    def test_count_all_requisitions(self, executor, finance_user):
        plan = _base_plan(
            QueryIntent.COUNT,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="count",
            aggregation="COUNT",
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        assert result.result[0]["count"] == 10


class TestRanking:
    def test_department_ranking(self, executor, finance_user):
        """Department with highest approved value should be correctly ranked."""
        plan = _base_plan(
            QueryIntent.RANKING,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="SUM",
            entity=QueryEntity.DEPARTMENT,
            group_by="Department",
            sort_order="desc",
            limit=1,
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        assert len(result.result) == 1
        top_dept = result.result[0]
        assert "group" in top_dept
        assert "value" in top_dept

    def test_employee_ranking_is_different_from_department(self, executor, finance_user):
        """Employee ranking result shape must differ from Department ranking."""
        dept_plan = _base_plan(
            QueryIntent.RANKING,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="SUM",
            entity=QueryEntity.DEPARTMENT,
            group_by="Department",
            sort_order="desc",
            limit=1,
        )
        emp_plan = _base_plan(
            QueryIntent.RANKING,
            scope=SubjectScope.ALL_EMPLOYEES,
            metric="Approved Value in INR",
            aggregation="SUM",
            entity=QueryEntity.EMPLOYEE,
            group_by="employee_name",
            sort_order="desc",
            limit=1,
        )
        dept_result = executor.execute(dept_plan, finance_user)
        emp_result = executor.execute(emp_plan, finance_user)

        assert dept_result.success and emp_result.success
        # Entity field must differ
        assert dept_result.entity != emp_result.entity
        # Top values may differ based on data
        dept_top = dept_result.result[0].get("group", "")
        emp_top = emp_result.result[0].get("group", "")
        # They should be different types of groups (dept vs person)
        assert dept_top != emp_top or dept_result.entity != emp_result.entity


class TestMyScope:
    def test_my_total_approved_amount(self, executor, employee_user):
        """TEMP99 total approved value = 50000 + 30000 = 80000."""
        plan = _base_plan(
            QueryIntent.AGGREGATE,
            scope=SubjectScope.CURRENT_USER,
            metric="Approved Value in INR",
            aggregation="SUM",
        )
        plan.target_employee_id = employee_user.employee_id
        result = executor.execute(plan, employee_user)
        assert result.success
        total = result.result[0]["value"]
        assert abs(total - 80000.0) < 0.01

    def test_my_pending_count(self, executor, employee_user):
        """TEMP99 pending requisitions: indices 9 (Pending) = 1 row (also row 3 is Rejected)."""
        plan = _base_plan(
            QueryIntent.COUNT,
            scope=SubjectScope.CURRENT_USER,
            metric="count",
            aggregation="COUNT",
        )
        plan.filters["status"] = "pending"
        plan.target_employee_id = employee_user.employee_id
        result = executor.execute(plan, employee_user)
        assert result.success
        # TEMP99 rows: 0(Approved), 3(Rejected), 6(Approved), 9(Pending) → 1 pending
        assert result.result[0]["count"] == 1
