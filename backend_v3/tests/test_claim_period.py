"""
Backend V3 — Claim Period Intelligence Tests
"""
import pytest
from datetime import datetime
from models.query import QueryPlan, QueryIntent, SubjectScope, ResponseType
from models.user import CurrentUser, UserRole
from utils.claim_period_extractor import ClaimPeriodExtractor
from services.claim_period_analytics import ClaimPeriodAnalytics
from data.requisition_repository import RequisitionRepository
from models.requisition import RequisitionRecord

# ── Extractor Tests ─────────────────────────────────────────────────────────

def test_extractor_single_month_with_year():
    extractor = ClaimPeriodExtractor()
    res = extractor.extract_period("Parking Charges March 2026", created_on="2026-05-10")
    assert res["claim_period_start"] == "2026-03-01"
    assert res["claim_period_end"] == "2026-03-31"
    assert res["claim_period_text"] == "Mar-2026"
    assert res["claim_months"] == ["2026-03"]
    assert res["period_confidence"] == "HIGH"

def test_extractor_single_month_without_year():
    extractor = ClaimPeriodExtractor()
    res = extractor.extract_period("Driver Salary - June", created_on="2026-07-15")
    assert res["claim_period_start"] == "2026-06-01"
    assert res["claim_period_end"] == "2026-06-30"
    assert res["claim_period_text"] == "Jun-2026"
    assert res["claim_months"] == ["2026-06"]
    assert res["period_confidence"] == "HIGH"

def test_extractor_explicit_date_range():
    extractor = ClaimPeriodExtractor()
    res = extractor.extract_period("18th Feb 26 to 3rd Apr 26 Parking Bill", created_on="2026-05-10")
    assert res["claim_period_start"] == "2026-02-18"
    assert res["claim_period_end"] == "2026-04-03"
    assert res["claim_months"] == ["2026-02", "2026-03", "2026-04"]
    assert res["period_confidence"] == "HIGH"

def test_extractor_multi_month_range():
    extractor = ClaimPeriodExtractor()
    res = extractor.extract_period("Internet re-imbursement from Jul25 till Feb 26", created_on="2026-05-10")
    assert res["claim_period_start"] == "2025-07-01"
    assert res["claim_period_end"] == "2026-02-28"
    assert "2025-07" in res["claim_months"]
    assert "2026-02" in res["claim_months"]
    assert len(res["claim_months"]) == 8  # Jul 25 to Feb 26 (8 months)
    assert res["period_confidence"] == "HIGH"

def test_extractor_plus_separated_months():
    extractor = ClaimPeriodExtractor()
    res = extractor.extract_period("Parking Bills Apr+May2026", created_on="2026-06-10")
    assert res["claim_period_start"] == "2026-04-01"
    assert res["claim_period_end"] == "2026-05-31"
    assert res["claim_months"] == ["2026-04", "2026-05"]
    assert res["period_confidence"] == "HIGH"

def test_extractor_cross_year_range():
    extractor = ClaimPeriodExtractor()
    res = extractor.extract_period("Newspaper Dec 25 till Jan 26", created_on="2026-02-10")
    assert res["claim_period_start"] == "2025-12-01"
    assert res["claim_period_end"] == "2026-01-31"
    assert res["claim_months"] == ["2025-12", "2026-01"]
    assert res["period_confidence"] == "HIGH"

def test_extractor_unknown_period():
    extractor = ClaimPeriodExtractor()
    # Non-recurring category gets null start/end
    res = extractor.extract_period("Need to download MATLAB software", created_on="2026-05-10")
    assert res["claim_period_start"] is None
    assert res["claim_period_end"] is None
    assert res["period_confidence"] == "LOW"

def test_extractor_created_on_fallback():
    extractor = ClaimPeriodExtractor()
    # Recurring category gets Created On month
    res = extractor.extract_period("Car Parking Bill", created_on="2026-05-10")
    assert res["claim_period_start"] == "2026-05-01"
    assert res["claim_period_end"] == "2026-05-31"
    assert "Inferred from Created On" in res["claim_period_text"]
    assert res["period_confidence"] == "LOW"

# ── Analytics Service Tests ──────────────────────────────────────────────────

@pytest.fixture
def mock_requisition_repo(monkeypatch):
    """Fixture returning a RequisitionRepository pre-populated with deterministic mock data."""
    class MockProvider:
        def get_requisitions_df(self):
            import pandas as pd
            return pd.DataFrame()
            
    repo = RequisitionRepository(MockProvider())
    
    mock_records = [
        RequisitionRecord(
            requisition_no="REQ-001",
            employee_id="MI0095",
            employee_name="Ajay Singh Tomar",
            document_title="Internet Charges",
            description="Internet bill reimbursement for April 2026",
            created_on="2026-05-10",
            status="Finally Approved",
            value_in_inr=1500.0,
            approved_value_in_inr=1500.0,
            claim_period_start="2026-04-01",
            claim_period_end="2026-04-30",
            claim_period_text="Apr-2026",
            claim_months=["2026-04"],
            period_confidence="HIGH",
        ),
        RequisitionRecord(
            requisition_no="REQ-002",
            employee_id="MI0095",
            employee_name="Ajay Singh Tomar",
            document_title="Internet Charges",
            description="Internet bill reimbursement for May 2026",
            created_on="2026-06-10",
            status="Finally Approved",
            value_in_inr=1500.0,
            approved_value_in_inr=1500.0,
            claim_period_start="2026-05-01",
            claim_period_end="2026-05-31",
            claim_period_text="May-2026",
            claim_months=["2026-05"],
            period_confidence="HIGH",
        ),
        RequisitionRecord(
            requisition_no="REQ-003",
            employee_id="MI0095",
            employee_name="Ajay Singh Tomar",
            document_title="Internet Charges",
            description="Internet bill reimbursement for July 2026",
            created_on="2026-08-10",
            status="Finally Approved",
            value_in_inr=1500.0,
            approved_value_in_inr=1500.0,
            claim_period_start="2026-07-01",
            claim_period_end="2026-07-31",
            claim_period_text="Jul-2026",
            claim_months=["2026-07"],
            period_confidence="HIGH",
        ),
        RequisitionRecord(
            requisition_no="REQ-004",
            employee_id="MI0095",
            employee_name="Ajay Singh Tomar",
            document_title="Parking Charges",
            description="Parking April 2026",
            created_on="2026-05-12",
            status="Finally Approved",
            value_in_inr=500.0,
            approved_value_in_inr=500.0,
            claim_period_start="2026-04-01",
            claim_period_end="2026-04-30",
            claim_period_text="Apr-2026",
            claim_months=["2026-04"],
            period_confidence="HIGH",
        ),
        # Overlapping parking claim
        RequisitionRecord(
            requisition_no="REQ-005",
            employee_id="MI0095",
            employee_name="Ajay Singh Tomar",
            document_title="Parking Charges",
            description="Parking 15 Apr to 15 May",
            created_on="2026-05-20",
            status="Pending",
            value_in_inr=600.0,
            approved_value_in_inr=0.0,
            claim_period_start="2026-04-15",
            claim_period_end="2026-05-15",
            claim_period_text="15-Apr-2026 to 15-May-2026",
            claim_months=["2026-04", "2026-05"],
            period_confidence="HIGH",
        ),
        # Another employee's record
        RequisitionRecord(
            requisition_no="REQ-006",
            employee_id="MI0168",
            employee_name="Rahul Karn",
            document_title="Internet Charges",
            description="Internet April",
            created_on="2026-05-10",
            status="Finally Approved",
            value_in_inr=1200.0,
            approved_value_in_inr=1200.0,
            claim_period_start="2026-04-01",
            claim_period_end="2026-04-30",
            claim_period_text="Apr-2026",
            claim_months=["2026-04"],
            period_confidence="HIGH",
        ),
    ]
    
    def mock_get_requisitions(
        scope, employee_id=None, status=None, keyword=None, date_range=None, requisition_id_list=None, **kwargs
    ):
        filtered = list(mock_records)
        # Apply scope
        if scope == SubjectScope.CURRENT_USER and employee_id:
            filtered = [r for r in filtered if r.employee_id == employee_id]
        elif scope == SubjectScope.SPECIFIC_EMPLOYEE and employee_id:
            filtered = [r for r in filtered if r.employee_id == employee_id]
            
        # Apply keyword (case-insensitive description matching)
        if keyword:
            filtered = [r for r in filtered if keyword.lower() in r.description.lower() or keyword.lower() in r.document_title.lower()]
            
        # Apply sorting
        sort_field = kwargs.get("sort_field", "Created On")
        sort_direction = kwargs.get("sort_direction", "desc")
        rev = (sort_direction.lower() == "desc")
        if sort_field == "Created On":
            filtered.sort(key=lambda x: x.created_on, reverse=rev)
        elif sort_field == "claim_period_start":
            filtered.sort(key=lambda x: x.claim_period_start or "", reverse=rev)

        return filtered, len(filtered)
        
    monkeypatch.setattr(repo, "get_requisitions", mock_get_requisitions)
    return repo

def test_analytics_last_claimed_period(mock_requisition_repo):
    analytics = ClaimPeriodAnalytics(mock_requisition_repo)
    res = analytics.get_last_claimed_period(SubjectScope.CURRENT_USER, employee_id="MI0095", keyword="internet")
    assert res is not None
    # REQ-003 is the latest created on (August 10, 2026)
    assert res["requisition_no"] == "REQ-003"
    assert res["claim_period_text"] == "Jul-2026"

def test_analytics_claim_timeline(mock_requisition_repo):
    analytics = ClaimPeriodAnalytics(mock_requisition_repo)
    timeline = analytics.get_claim_timeline(SubjectScope.CURRENT_USER, employee_id="MI0095", keyword="internet")
    assert len(timeline) == 3
    # Verify chronological sorting
    assert timeline[0]["requisition_no"] == "REQ-001" # April
    assert timeline[1]["requisition_no"] == "REQ-002" # May
    assert timeline[2]["requisition_no"] == "REQ-003" # July

def test_analytics_missing_months(mock_requisition_repo):
    analytics = ClaimPeriodAnalytics(mock_requisition_repo)
    missing = analytics.find_missing_periods(SubjectScope.CURRENT_USER, employee_id="MI0095", keyword="internet")
    assert len(missing) == 1
    # Between April (2026-04) and July (2026-07), June (2026-06) is missing! (REQ-002 is May, REQ-003 is July)
    assert "Jun-2026" in missing[0]["missing_months"]

def test_analytics_duplicates(mock_requisition_repo):
    analytics = ClaimPeriodAnalytics(mock_requisition_repo)
    duplicates = analytics.find_duplicate_periods(SubjectScope.ALL_EMPLOYEES, employee_id=None, keyword="parking")
    assert len(duplicates) == 1
    d = duplicates[0]
    assert d["employee_id"] == "MI0095"
    assert d["category"] == "Parking/Conveyance"
    # REQ-004 (April) and REQ-005 (April to May) share month "2026-04"
    assert "2026-04" in d["overlapping_months"]

def test_analytics_overlaps(mock_requisition_repo):
    analytics = ClaimPeriodAnalytics(mock_requisition_repo)
    overlaps = analytics.find_overlapping_periods(SubjectScope.ALL_EMPLOYEES, employee_id=None, keyword="parking")
    assert len(overlaps) == 1
    o = overlaps[0]
    # REQ-004 (April 1 to April 30) overlaps with REQ-005 (April 15 to May 15)
    assert o["overlap_start"] == "2026-04-15"
    assert o["overlap_end"] == "2026-04-30"

# ── Authorization / Security Turn Tests ─────────────────────────────────────

def test_authorization_enforced_for_employee(chat_svc, employee_user):
    # Employee Ajay Tomar (MI0095) queries duplicates
    resp = chat_svc.handle_message("Show duplicate parking claims", employee_user, "test_chat")
    # Authorization service must restrict Ajay Tomar's query to CURRENT_USER.
    # Therefore, he only sees duplicate parking claims for himself (not other employees organization-wide).
    assert resp.success is True
    # Verify duplicates returned only for Ajay
    if resp.data and "duplicates" in resp.data:
        for d in resp.data["duplicates"]:
            assert d["employee_id"] == employee_user.employee_id

def test_authorization_permitted_for_finance(chat_svc, finance_user):
    # Finance user queries organization-wide duplicates
    resp = chat_svc.handle_message("Show duplicate parking claims", finance_user, "test_chat")
    assert resp.success is True
    # Privileged query should run organization-wide

# ── Parser & Context Tests ──────────────────────────────────────────────────

def test_query_parsing_intents(query_parser, employee_user):
    plan = query_parser.parse_query("Show my internet reimbursement timeline.", employee_user)
    assert plan.intent == QueryIntent.CLAIM_TIMELINE
    
    plan2 = query_parser.parse_query("Am I missing any months for internet?", employee_user)
    assert plan2.intent == QueryIntent.CLAIM_MISSING_PERIOD
    assert plan2.filters.get("description_keyword") == "internet"

def test_conversation_context_follow_up(chat_svc, employee_user):
    chat_id = "context_test_chat"
    # First message sets category context
    resp1 = chat_svc.handle_message("Show my internet reimbursement timeline.", employee_user, chat_id)
    assert resp1.success is True
    
    # Follow-up inherits the category "internet"
    resp2 = chat_svc.handle_message("Which month is missing?", employee_user, chat_id)
    assert resp2.success is True
    # The output should talk about missing months for internet
    assert "internet" in resp2.message or "Internet" in resp2.message


# ── Year Inference & Duration Regression Tests ──────────────────────────────

def test_regression_duration_and_year_bounds():
    extractor = ClaimPeriodExtractor()
    
    # 1. "Parking 17 Feb to 31 Mar 30 Days -3000" -> 17-Feb-2026 to 31-Mar-2026
    r1 = extractor.extract_period("Parking 17 Feb to 31 Mar 30 Days -3000", created_on="2026-04-01")
    assert r1["claim_period_start"] == "2026-02-17"
    assert r1["claim_period_end"] == "2026-03-31"
    
    # 2. "Parking 1 Apr to 5 Jun 48 days" -> 1-Apr-2026 to 5-Jun-2026
    r2 = extractor.extract_period("Parking 1 Apr to 5 Jun 48 days", created_on="2026-06-01")
    assert r2["claim_period_start"] == "2026-04-01"
    assert r2["claim_period_end"] == "2026-06-05"
    
    # 3. "Internet re-imbursement from Jul25 till Feb 26" -> Jul-2025 to Feb-2026
    r3 = extractor.extract_period("Internet re-imbursement from Jul25 till Feb 26", created_on="2026-05-10")
    assert r3["claim_period_start"] == "2025-07-01"
    assert r3["claim_period_end"] == "2026-02-28"
    
    # 4. "26 April 2026 to 2 May 2026" -> 26-Apr-2026 to 2-May-2026
    r4 = extractor.extract_period("26 April 2026 to 2 May 2026", created_on="2026-05-10")
    assert r4["claim_period_start"] == "2026-04-26"
    assert r4["claim_period_end"] == "2026-05-02"
    
    # 5. "December 2025 to January 2026" -> Dec-2025 to Jan-2026
    r5 = extractor.extract_period("December 2025 to January 2026", created_on="2026-02-10")
    assert r5["claim_period_start"] == "2025-12-01"
    assert r5["claim_period_end"] == "2026-01-31"
    
    # 6. "Parking 17 Feb 2026 to 31 Mar 2026" -> 17-Feb-2026 to 31-Mar-2026
    r6 = extractor.extract_period("Parking 17 Feb 2026 to 31 Mar 2026", created_on="2026-04-10")
    assert r6["claim_period_start"] == "2026-02-17"
    assert r6["claim_period_end"] == "2026-03-31"
    
    # 7. Legitimate year must never be rejected because it is outside the current month (tested in 3, 4, 5, 6)
    # e.g., claiming July 2025 from a Created On in May 2026 (10 months ago) is valid (2025 is within 2026 - 5)
    r7 = extractor.extract_period("Internet re-imbursement for Jul25", created_on="2026-05-10")
    assert r7["claim_period_start"] == "2025-07-01"
    assert r7["claim_period_end"] == "2025-07-31"

