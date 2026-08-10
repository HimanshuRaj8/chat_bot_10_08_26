"""
Backend V3 — Conversational Context and Pronoun Reference Resolution Tests
"""
import pytest
from models.query import ResponseType, QueryPlan, SubjectScope, QueryIntent
from models.user import CurrentUser, UserRole
from auth.authorization import AuthorizationError


def test_it_pronoun_reference_chain(chat_svc, employee_user):
    chat_id = "it_chain_1"
    
    # 1. Ask for latest requisition
    resp1 = chat_svc.handle_message("show my latest requisition", employee_user, chat_id)
    assert resp1.success is True
    assert resp1.response_type == ResponseType.SINGLE_RECORD
    req_no = resp1.sources[0]["requisition_no"]
    
    # 2. Ask "who approved it?" -> should resolve "it" to the latest requisition
    resp2 = chat_svc.handle_message("who approved it?", employee_user, chat_id)
    assert resp2.success is True
    assert resp2.response_type == ResponseType.SINGLE_RECORD
    assert req_no in resp2.message
    assert resp2.sources[0]["requisition_no"] == req_no
    
    # 3. Ask "what was it for?" -> should resolve "it" to same requisition
    resp3 = chat_svc.handle_message("what was it for?", employee_user, chat_id)
    assert resp3.success is True
    assert resp3.response_type == ResponseType.SINGLE_RECORD
    assert resp3.sources[0]["requisition_no"] == req_no


def test_previous_one_reference(chat_svc, employee_user):
    chat_id = "prev_chain_1"
    
    # 1. Fetch requisitions list to populate context list
    resp1 = chat_svc.handle_message("show my approved claims", employee_user, chat_id)
    assert len(resp1.sources) > 1
    first_req = resp1.sources[0]["requisition_no"]
    second_req = resp1.sources[1]["requisition_no"]

    # Select the first one
    chat_svc.handle_message(f"show details for {first_req}", employee_user, chat_id)
    
    # 2. Ask "what about the previous one?" -> should resolve to second_req
    resp2 = chat_svc.handle_message("what about the previous one?", employee_user, chat_id)
    assert resp2.success is True
    assert resp2.response_type == ResponseType.SINGLE_RECORD
    assert resp2.sources[0]["requisition_no"] == second_req


def test_pagination_followup(chat_svc, employee_user):
    chat_id = "paging_chain_1"
    
    # 1. Fetch list of requisitions
    resp1 = chat_svc.handle_message("show my claims", employee_user, chat_id, page=1, page_size=2)
    assert resp1.response_type == ResponseType.RECORD_LIST
    assert resp1.page == 1
    assert resp1.page_size == 2
    rec1 = resp1.sources[0]["requisition_no"]

    # 2. Ask "next page" -> should advance to page 2 using same filters
    resp2 = chat_svc.handle_message("next page", employee_user, chat_id)
    assert resp2.response_type == ResponseType.RECORD_LIST
    assert resp2.page == 2
    assert resp2.page_size == 2
    rec2 = resp2.sources[0]["requisition_no"]
    assert rec1 != rec2


# ── V3 QA REGRESSION TESTS ────────────────────────────────────────────────────

def test_regression_finance_april_approved_followup(chat_svc, finance_user):
    chat_id = "reg_fin_april_1"
    
    # 1. Show all approved requisitions from April
    resp1 = chat_svc.handle_message("Show all approved requisitions from April.", finance_user, chat_id)
    assert resp1.success is True
    assert resp1.total == 66
    
    # 2. How many are there?
    resp2 = chat_svc.handle_message("How many are there?", finance_user, chat_id)
    assert resp2.success is True
    assert resp2.analytics["count"] == 66
    
    # 3. What is the total approved value?
    resp3 = chat_svc.handle_message("What is the total approved value?", finance_user, chat_id)
    assert resp3.success is True
    assert abs(resp3.analytics["value"] - 319872.63) < 0.01


def test_regression_driver_salary_followup(chat_svc, finance_user):
    chat_id = "reg_driver_1"
    
    # 1. Show driver salary requisitions
    resp1 = chat_svc.handle_message("Show driver salary requisitions.", finance_user, chat_id)
    assert resp1.success is True
    assert resp1.total == 14
    
    # 2. How many are there?
    resp2 = chat_svc.handle_message("How many are there?", finance_user, chat_id)
    assert resp2.success is True
    assert resp2.analytics["count"] == 14


def test_regression_ajay_tomar_ranking_followup(chat_svc, finance_user):
    chat_id = "reg_ajay_1"
    
    # 1. Show Ajay Tomar's requisitions
    resp1 = chat_svc.handle_message("Show Ajay Tomar's requisitions.", finance_user, chat_id)
    assert resp1.success is True
    assert resp1.total >= 18
    
    # 2. Which one has the highest approved value?
    resp2 = chat_svc.handle_message("Which one has the highest approved value?", finance_user, chat_id)
    assert resp2.success is True
    assert resp2.analytics["value"] > 0.0


def test_regression_employee_pending_followup(chat_svc):
    chat_id = "reg_emp_pending_1"
    
    # Amit Patel (MI0076) has exactly 1 pending requisition
    user = CurrentUser(
        employee_id="MI0076",
        employee_name="Amit Patel",
        email="amit.patel@motherson.com",
        role=UserRole.EMPLOYEE,
        department="SW",
    )
    
    # 1. Show my pending requisitions
    resp1 = chat_svc.handle_message("Show my pending requisitions.", user, chat_id)
    assert resp1.success is True
    assert resp1.total == 1
    
    # 2. How many are there?
    resp2 = chat_svc.handle_message("How many are there?", user, chat_id)
    assert resp2.success is True
    assert resp2.analytics["count"] == 1


def test_regression_override_filter_instead(chat_svc, finance_user):
    chat_id = "reg_override_1"
    
    # 1. Show all approved requisitions from April
    resp1 = chat_svc.handle_message("Show all approved requisitions from April.", finance_user, chat_id)
    assert resp1.total == 66
    
    # 2. Show May instead
    resp2 = chat_svc.handle_message("Show May instead.", finance_user, chat_id)
    assert resp2.success is True
    assert resp2.total == 65


def test_regression_employee_tampering_denial(auth_gate, employee_user):
    # employee_user is Ajay Singh Tomar (MI0095) - should be blocked from searching Rahul Karn's name
    plan = QueryPlan(
        intent=QueryIntent.LIST_REQUISITIONS,
        subject_scope=SubjectScope.SPECIFIC_EMPLOYEE,
        target_employee_id="MI0168"  # Rahul Karn
    )
    with pytest.raises(AuthorizationError):
        auth_gate.validate(employee_user, plan)


def test_regression_finance_query_permitted(chat_svc, finance_user):
    chat_id = "reg_fin_query_1"
    
    resp = chat_svc.handle_message("Show Ajay Tomar's requisitions.", finance_user, chat_id)
    assert resp.success is True
    assert resp.response_type == ResponseType.RECORD_LIST


def test_regression_new_chat_context_reset(chat_svc, finance_user):
    chat_id_1 = "reg_reset_chat_1"
    chat_id_2 = "reg_reset_chat_2"
    
    # 1. Ask in Chat 1
    chat_svc.handle_message("Show all approved requisitions from April.", finance_user, chat_id_1)
    
    # 2. Ask in Chat 2 (without context)
    resp2 = chat_svc.handle_message("What is the total?", finance_user, chat_id_2)
    assert abs(resp2.analytics["value"] - 1025847.46) < 0.01


def test_regression_finance_all_approved_followup(chat_svc, finance_user):
    chat_id = "reg_fin_all_approved_1"
    
    # 1. Show all approved requisitions
    resp1 = chat_svc.handle_message("Show all approved requisitions.", finance_user, chat_id)
    assert resp1.total == 213
    
    # 2. How many are there?
    resp2 = chat_svc.handle_message("How many are there?", finance_user, chat_id)
    assert resp2.analytics["count"] == 213


def test_regression_employee_approved_followup(chat_svc, employee_user):
    chat_id = "reg_emp_approved_1"
    
    # employee_user is Ajay Singh Tomar (MI0095) who has 18 approved requisitions
    # 1. Show my approved requisitions
    resp1 = chat_svc.handle_message("Show my approved requisitions.", employee_user, chat_id)
    assert resp1.total == 18
    
    # 2. How many are there?
    resp2 = chat_svc.handle_message("How many are there?", employee_user, chat_id)
    assert resp2.analytics["count"] == 18

