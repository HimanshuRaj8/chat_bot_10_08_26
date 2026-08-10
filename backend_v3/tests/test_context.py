"""
Backend V3 — Conversational Context and Pronoun Reference Resolution Tests
"""
import pytest
from models.query import ResponseType


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
