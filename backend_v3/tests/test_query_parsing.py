"""
Backend V3 — Query Parsing, Validation, and Entity Resolution Tests
"""
import pytest
from models.query import QueryPlan, QueryIntent, QueryEntity, SubjectScope, ResponseType
from models.user import CurrentUser, UserRole


def test_parse_my_latest_requisition(query_parser, employee_user):
    plan = query_parser.parse_query("show my latest requisition", employee_user)
    assert plan.intent == QueryIntent.GET_LATEST_REQUISITION
    assert plan.subject_scope == SubjectScope.CURRENT_USER
    assert plan.target_employee_id == employee_user.employee_id


def test_parse_pending_status(query_parser, employee_user):
    plan = query_parser.parse_query("show my pending claims", employee_user)
    assert plan.intent == QueryIntent.LIST_REQUISITIONS
    assert plan.filters.get("status") == "pending"


def test_parse_exact_requisition(query_parser, employee_user):
    plan = query_parser.parse_query("what is the status of G-2026-1024?", employee_user)
    assert plan.intent == QueryIntent.GET_REQUISITION
    assert plan.exact_req_no == "G-2026-1024"


def test_parse_date_phrase_april(query_parser, employee_user):
    plan = query_parser.parse_query("show my requisitions in April 2026", employee_user)
    assert plan.intent == QueryIntent.LIST_REQUISITIONS
    assert plan.date_range.label == "April 2026"
    assert plan.date_range.start is not None
    assert plan.date_range.end is not None


def test_entity_resolver_exact_match(entity_resolver):
    # Ajay Tomar is in directory (unique match)
    plan = QueryPlan(target_employee_name="Ajay Tomar")
    res = entity_resolver.resolve_entities(plan)
    assert res is None  # no short-circuit
    assert plan.target_employee_id == "MI0095"


def test_entity_resolver_ambiguous_clarification(entity_resolver):
    # 'Singh' matches multiple employees in the directory
    plan = QueryPlan(target_employee_name="Singh")
    res = entity_resolver.resolve_entities(plan)
    assert res is not None
    assert res.response_type == ResponseType.CLARIFICATION
    assert len(res.data["matches"]) > 1


def test_entity_resolver_no_data(entity_resolver):
    # Non-existent name
    plan = QueryPlan(target_employee_name="Hacker Name")
    res = entity_resolver.resolve_entities(plan)
    assert res is not None
    assert res.response_type == ResponseType.NO_DATA
    assert "couldn't find" in res.message
