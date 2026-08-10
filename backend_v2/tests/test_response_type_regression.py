"""
Regression tests for response type and pagination formatting issues (Bugs 3, 4, 5).
"""
import pytest
from unittest.mock import MagicMock

from models.query import QueryIntent, SubjectScope, QueryPlan, DateRange, QueryEntity
from models.user import CurrentUser, UserRole
from query.query_planner import QueryPlanner
from query.query_executor import QueryExecutor
from ai.response_generator import ResponseGenerator
from security.authorization import AuthorizationService
from services.profile_service import ProfileService
from services.chat_service import ChatService
from utils.chat_history import ChatHistoryManager


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
def chat_svc(mock_data_provider, tmp_path):
    planner = QueryPlanner()
    executor = QueryExecutor(data_provider=mock_data_provider)
    llm_mock = MagicMock()
    llm_mock.generate.return_value = "Formatted LLM Response."
    response_gen = ResponseGenerator(llm_service=llm_mock)
    auth = AuthorizationService()
    profile_svc = ProfileService()
    history_file = str(tmp_path / "chat_history_v2_regression.json")
    chat_hist = ChatHistoryManager(history_file=history_file)

    return ChatService(
        query_planner=planner,
        query_executor=executor,
        response_generator=response_gen,
        authorization=auth,
        profile_service=profile_svc,
        chat_history=chat_hist,
    )


def test_april_month_requisition_intent_and_response_type(chat_svc, finance_user):
    """
    Bug 3/5: "April month requisition" should resolve to TREND intent,
    output a single-row aggregate table, and be categorised as "SUMMARY" with NO pagination.
    """
    resp = chat_svc.handle_message(
        question="April 2024 month requisition",
        user=finance_user,
        chat_id="test_reg_1",
    )

    assert not resp.unauthorized
    # Response type must be SUMMARY
    assert resp.response_type == "SUMMARY"
    # Pagination must be disabled (None) for summary responses even if total raw records > page_size
    assert resp.pagination is None
    # Check custom formatting in answer
    assert "I found" in resp.answer
    assert "requisition" in resp.answer
    assert "April 2024" in resp.answer
    assert "total approved value" in resp.answer


def test_show_me_april_requisitions_intent_and_response_type(chat_svc, finance_user):
    """
    Bug 3/5: "show me April requisitions" should resolve to FILTER intent,
    return a list of requisition records, and be categorised as "RECORD_LIST" with pagination enabled.
    """
    # Set page_size = 1 in the request so we force pagination even for a small dataset
    resp = chat_svc.handle_message(
        question="show me April 2024 requisitions",
        user=finance_user,
        chat_id="test_reg_2",
        page=1,
        page_size=1,
    )

    assert not resp.unauthorized
    # Response type must be RECORD_LIST
    assert resp.response_type == "RECORD_LIST"
    
    # pagination should be active
    assert resp.pagination is not None
    assert resp.pagination["total_records"] == 2  # REQ-2024-007, REQ-2024-008
    assert resp.pagination["page"] == 1
    # Check formatting: should display showing records header
    assert "Showing records" in resp.answer
    assert "|" in resp.answer  # contains markdown table


def test_exact_requisition_lookup_response_type(chat_svc, finance_user):
    """
    Bug 5: Exact requisition lookup should be SINGLE_RECORD and have no pagination.
    """
    resp = chat_svc.handle_message(
        question="show requisition REQ-2024-001",
        user=finance_user,
        chat_id="test_reg_3",
    )

    assert not resp.unauthorized
    assert resp.response_type == "SINGLE_RECORD"
    assert resp.pagination is None
