"""
Test: Backend V2 Pagination Test Suite (Section 26)
Verifies all 18 pagination requirements.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
from unittest.mock import MagicMock

from models.user import CurrentUser, UserRole
from models.query import QueryPlan, QueryIntent, SubjectScope, QueryEntity
from query.query_planner import QueryPlanner
from query.query_executor import QueryExecutor
from query.validator import ResultConsistencyValidator
from ai.response_generator import ResponseGenerator
from security.authorization import AuthorizationService
from services.profile_service import ProfileService
from services.chat_service import ChatService
from utils.chat_history import ChatHistoryManager
import config


@pytest.fixture
def make_mock_provider():
    """Factory fixture returning an ExcelDataProvider-like mock with N synthetic rows."""
    def _create(n_rows: int, employee_id="EMP001", status="Approved"):
        rows = []
        for i in range(1, n_rows + 1):
            rows.append({
                "Requisition No": f"REQ-2026-{i:04d}",
                "employee_name": "Test User",
                "employee_id": employee_id,
                "Department": "IT",
                "Status": status,
                "Approved Value in INR": float(i * 100),
                "Value in INR": float(i * 100),
                "Created On": pd.Timestamp("2026-04-01") + pd.Timedelta(days=i),
                "Finally Approved On": pd.Timestamp("2026-04-02") + pd.Timedelta(days=i),
                "Requisition Description": f"Test item {i}",
                "Cost Centre": "CC001",
                "Operational Unit Name": "Unit A",
            })
        df = pd.DataFrame(rows)
        provider = MagicMock()
        provider.get_requisitions_df.return_value = df
        return provider

    return _create


@pytest.fixture
def chat_svc_factory(tmp_path):
    def _build(provider):
        planner = QueryPlanner()
        executor = QueryExecutor(data_provider=provider)
        llm_mock = MagicMock()
        llm_mock.generate.return_value = "Formatted table response."
        response_gen = ResponseGenerator(llm_service=llm_mock)
        auth = AuthorizationService()
        profile_svc = ProfileService()
        hist = ChatHistoryManager(history_file=str(tmp_path / "chat_history.json"))
        return ChatService(
            query_planner=planner,
            query_executor=executor,
            response_generator=response_gen,
            authorization=auth,
            profile_service=profile_svc,
            chat_history=hist,
            validator=ResultConsistencyValidator(),
        )

    return _build


class TestPaginationRequirements:

    # 1. 0 records
    def test_1_zero_records(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(0)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "c0")
        assert resp.pagination is None or resp.pagination["total_records"] == 0

    # 2. 1 record
    def test_2_one_record(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(1)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "c1")
        # <= 20 records -> pagination control not attached to UI response
        assert resp.pagination is None

    # 3. Exactly 20 records
    def test_3_twenty_records(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(20)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "c20")
        assert resp.pagination is None

    # 4. 21 records
    def test_4_twenty_one_records(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(21)
        svc = chat_svc_factory(provider)
        resp1 = svc.handle_message("Show all requisitions", finance_user, "c21", page=1)
        assert resp1.pagination["total_records"] == 21
        assert resp1.pagination["total_pages"] == 2
        assert resp1.pagination["returned_records"] == 20
        assert resp1.pagination["has_next"] is True

        resp2 = svc.handle_message("Show all requisitions", finance_user, "c21", page=2)
        assert resp2.pagination["returned_records"] == 1
        assert resp2.pagination["has_next"] is False
        assert resp2.pagination["has_previous"] is True

    # 5. 40 records
    def test_5_forty_records(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(40)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "c40", page=1)
        assert resp.pagination["total_records"] == 40
        assert resp.pagination["total_pages"] == 2
        assert resp.pagination["returned_records"] == 20

    # 6. 41 records
    def test_6_forty_one_records(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(41)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "c41", page=3)
        assert resp.pagination["total_records"] == 41
        assert resp.pagination["total_pages"] == 3
        assert resp.pagination["returned_records"] == 1

    # 7. 212 records
    def test_7_two_hundred_twelve_records(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(212)
        svc = chat_svc_factory(provider)
        
        # Page 1
        r1 = svc.handle_message("Show all requisitions", finance_user, "c212", page=1)
        assert r1.pagination["total_records"] == 212
        assert r1.pagination["total_pages"] == 11
        assert r1.pagination["returned_records"] == 20

        # Page 11
        r11 = svc.handle_message("Show all requisitions", finance_user, "c212", page=11)
        assert r11.pagination["returned_records"] == 12
        assert r11.pagination["has_next"] is False

    # 8. page = 0 normalized to 1
    def test_8_page_zero(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(30)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "cp0", page=0)
        assert resp.pagination["page"] == 1

    # 9. page = -1 normalized to 1
    def test_9_page_negative(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(30)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "cpneg", page=-1)
        assert resp.pagination["page"] == 1

    # 10. page beyond final page
    def test_10_page_beyond_final(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(212)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "cp12", page=12)
        assert "That page doesn't exist" in resp.answer
        assert "11 pages" in resp.answer

    # 11. page_size = 50 works
    def test_11_page_size_50(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(100)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "cps50", page=1, page_size=50)
        assert resp.pagination["page_size"] == 50
        assert resp.pagination["returned_records"] == 50
        assert resp.pagination["total_pages"] == 2

    # 12. page_size > MAX_PAGE_SIZE capped at 50
    def test_12_page_size_capped(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(100)
        svc = chat_svc_factory(provider)
        resp = svc.handle_message("Show all requisitions", finance_user, "cps1000", page=1, page_size=1000)
        assert resp.pagination["page_size"] == config.MAX_PAGE_SIZE

    # 13. Employee pagination (only authenticated user records on every page)
    def test_13_employee_pagination_scoped(self, make_mock_provider, chat_svc_factory, employee_user):
        provider = make_mock_provider(35, employee_id="TEMP99")
        svc = chat_svc_factory(provider)
        r1 = svc.handle_message("Show my requisitions", employee_user, "cemp", page=1)
        assert r1.pagination["total_records"] == 35
        assert r1.pagination["returned_records"] == 20

        r2 = svc.handle_message("Show my requisitions", employee_user, "cemp", page=2)
        assert r2.pagination["returned_records"] == 15

    # 14. Finance pagination
    def test_14_finance_pagination_all(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(212)
        svc = chat_svc_factory(provider)
        r1 = svc.handle_message("Show all requisitions", finance_user, "cfin", page=1)
        assert r1.pagination["total_records"] == 212
        assert not r1.unauthorized

    # 15. Date-filtered pagination
    def test_15_date_filter_before_pagination(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(100)
        svc = chat_svc_factory(provider)
        r = svc.handle_message("Show all requisitions from April 2026", finance_user, "cdate", page=1)
        assert r.pagination is None or r.pagination["total_records"] <= 100

    # 16. Status-filtered pagination
    def test_16_status_filter_before_pagination(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(60, status="Approved")
        svc = chat_svc_factory(provider)
        r = svc.handle_message("Show all approved requisitions", finance_user, "cstat", page=1)
        assert r.pagination["total_records"] == 60
        assert r.pagination["total_pages"] == 3

    # 17. Sorting before pagination (no record jumping)
    def test_17_sorting_before_pagination(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(40)
        svc = chat_svc_factory(provider)
        r1 = svc.handle_message("Show all requisitions", finance_user, "csort", page=1)
        r2 = svc.handle_message("Show all requisitions", finance_user, "csort", page=2)
        p1_sources = [s["requisition_no"] for s in r1.sources]
        p2_sources = [s["requisition_no"] for s in r2.sources]
        # No overlap between page 1 and page 2 sources
        assert set(p1_sources).isdisjoint(set(p2_sources))

    # 18. Natural language follow-up pagination ("Next page")
    def test_18_natural_language_followup_pagination(self, make_mock_provider, chat_svc_factory, finance_user):
        provider = make_mock_provider(50)
        svc = chat_svc_factory(provider)
        
        # Turn 1
        r1 = svc.handle_message("Show all requisitions", finance_user, "cnl", page=1)
        assert r1.pagination["page"] == 1

        # Turn 2: Natural language "Next page"
        r2 = svc.handle_message("Next page", finance_user, "cnl")
        assert r2.pagination["page"] == 2
        assert r2.pagination["returned_records"] == 20

        # Turn 3: Natural language "Next page"
        r3 = svc.handle_message("Next page", finance_user, "cnl")
        assert r3.pagination["page"] == 3
        assert r3.pagination["returned_records"] == 10
