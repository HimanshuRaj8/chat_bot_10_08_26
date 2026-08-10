"""
Test: QueryPlanner V2.1
Verifies intent, scope, entity, aggregation, metric, and status filter detection across all 10 standard queries.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from query.query_planner import QueryPlanner
from models.query import QueryIntent, SubjectScope, QueryEntity, QueryMetric, OutputType


@pytest.fixture
def planner():
    return QueryPlanner()


class TestProfileQueryPlans:
    def test_what_department_am_i_in(self, planner, employee_user):
        plan = planner.plan("What department am I in?", employee_user)
        assert plan.intent == QueryIntent.PROFILE
        assert plan.profile_metric == QueryMetric.DEPARTMENT
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.output_type == OutputType.NATURAL_TEXT

    def test_which_department_am_i_in(self, planner, employee_user):
        plan = planner.plan("Which department am I in?", employee_user)
        assert plan.intent == QueryIntent.PROFILE
        assert plan.profile_metric == QueryMetric.DEPARTMENT

    def test_what_location_am_i_in(self, planner, employee_user):
        plan = planner.plan("What location am I in?", employee_user)
        assert plan.intent == QueryIntent.PROFILE
        assert plan.profile_metric == QueryMetric.LOCATION

    def test_what_is_my_id(self, planner, employee_user):
        plan = planner.plan("What is my ID?", employee_user)
        assert plan.intent == QueryIntent.PROFILE
        assert plan.profile_metric == QueryMetric.EMPLOYEE_ID

    def test_what_is_my_name(self, planner, employee_user):
        plan = planner.plan("What is my name?", employee_user)
        assert plan.intent == QueryIntent.PROFILE
        assert plan.profile_metric == QueryMetric.NAME

    def test_who_am_i(self, planner, employee_user):
        plan = planner.plan("Who am I?", employee_user)
        assert plan.intent == QueryIntent.PROFILE
        assert plan.profile_metric == QueryMetric.FULL_PROFILE


class TestRequisitionAndAnalyticsQueryPlans:
    def test_what_is_my_highest_approved_reimbursement(self, planner, employee_user):
        plan = planner.plan("What is my highest approved reimbursement?", employee_user)
        assert plan.intent == QueryIntent.RANKING
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == "TEMP99"
        assert plan.entity == QueryEntity.REQUISITION
        assert plan.group_by is None
        assert plan.metric == "Approved Value in INR"
        assert plan.aggregation == "MAX"
        assert plan.limit == 1
        # Crucial bug fix: "approved reimbursement" should NOT trigger a status filter
        assert plan.filters.get("status") is None

    def test_who_has_the_highest_approved_reimbursement(self, planner, finance_user):
        plan = planner.plan("Who has the highest approved reimbursement?", finance_user)
        assert plan.intent == QueryIntent.RANKING
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES
        assert plan.entity == QueryEntity.EMPLOYEE
        assert plan.group_by == "employee_name"
        assert plan.metric == "Approved Value in INR"
        assert plan.aggregation == "SUM"
        assert plan.limit == 1
        assert plan.output_type == OutputType.NATURAL_TEXT

    def test_which_employee_has_highest_total_approved_value(self, planner, finance_user):
        plan = planner.plan("Which employee has the highest total approved value?", finance_user)
        assert plan.intent == QueryIntent.RANKING
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES
        assert plan.entity == QueryEntity.EMPLOYEE
        assert plan.group_by == "employee_name"
        assert plan.metric == "Approved Value in INR"
        assert plan.aggregation == "SUM"
        assert plan.limit == 1

    def test_which_requisition_has_highest_approved_value(self, planner, finance_user):
        plan = planner.plan("Which requisition has the highest approved value?", finance_user)
        assert plan.intent == QueryIntent.RANKING
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES
        assert plan.entity == QueryEntity.REQUISITION
        assert plan.group_by is None
        assert plan.metric == "Approved Value in INR"
        assert plan.aggregation == "MAX"
        assert plan.limit == 1

    def test_which_department_has_highest_total_approved_value(self, planner, finance_user):
        plan = planner.plan("Which department has the highest total approved value?", finance_user)
        assert plan.intent == QueryIntent.RANKING
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES
        assert plan.entity == QueryEntity.DEPARTMENT
        assert plan.group_by == "Department"
        assert plan.metric == "Approved Value in INR"
        assert plan.aggregation == "SUM"
        assert plan.limit == 1

    def test_show_my_approved_requisitions(self, planner, employee_user):
        plan = planner.plan("Show my approved requisitions", employee_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == "TEMP99"
        assert plan.filters.get("status") == "approved"

    def test_show_all_approved_requisitions(self, planner, finance_user):
        plan = planner.plan("Show all approved requisitions", finance_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.subject_scope == SubjectScope.ALL_EMPLOYEES
        assert plan.filters.get("status") == "approved"
