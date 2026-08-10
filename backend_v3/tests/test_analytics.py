"""
Backend V3 — Deterministic Analytics and Aggregation Tests
"""
import pytest
from models.query import QueryPlan, QueryIntent, QueryEntity, SubjectScope, ResponseType
from models.user import CurrentUser, UserRole


def test_employee_total_approved_sum(chat_svc, employee_user):
    # Rahul Karn (MI0168) total approved reimbursement sum
    resp = chat_svc.handle_message("what is my total approved reimbursement?", employee_user, "test_chat")
    assert resp.success is True
    assert resp.response_type == ResponseType.SUMMARY
    assert resp.analytics["value"] > 0.0
    assert resp.to_dict()["pagination"] is None  # pagination must be absent on summary


def test_finance_organization_wide_sum(chat_svc, finance_user):
    resp = chat_svc.handle_message("what is the total approved reimbursement?", finance_user, "test_chat")
    assert resp.success is True
    assert resp.response_type == ResponseType.SUMMARY
    assert resp.analytics["value"] > 100000.0  # org total is large
    assert resp.to_dict()["pagination"] is None


def test_department_ranking_analytics(chat_svc, finance_user):
    # Which department has highest approved value
    resp = chat_svc.handle_message("which department has the highest approved value?", finance_user, "test_chat")
    assert resp.success is True
    assert resp.response_type == ResponseType.ANALYTICS
    assert resp.data["analytics_data"] is not None
    # First item is highest
    first = resp.data["analytics_data"][0]
    assert "group" in first
    assert "value" in first
    assert resp.to_dict()["pagination"] is None


def test_employee_ranking_analytics(chat_svc, finance_user):
    # Who has highest approved reimbursement
    resp = chat_svc.handle_message("who has the highest approved reimbursement?", finance_user, "test_chat")
    assert resp.success is True
    assert resp.response_type == ResponseType.ANALYTICS
    assert len(resp.data["analytics_data"]) > 0
    assert resp.to_dict()["pagination"] is None


def test_monthly_trend_analytics(chat_svc, finance_user):
    # April approval summary
    resp = chat_svc.handle_message("April month requisition", finance_user, "test_chat")
    assert resp.success is True
    assert resp.response_type == ResponseType.ANALYTICS
    # Should format a nice month aggregate table
    assert "Month" in resp.message
    assert "Approved Value" in resp.message
    assert resp.to_dict()["pagination"] is None
