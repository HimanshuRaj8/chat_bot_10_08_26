"""
Backend V2 — Test Fixtures (conftest.py)

Shared fixtures:
  - employee_user: normal Employee
  - finance_user: Finance role
  - admin_user: Admin role
  - test_df: minimal DataFrame with 10 synthetic rows
  - mock_data_provider: returns test_df
  - query_planner: QueryPlanner instance
  - chat_svc: fully wired ChatService with mock provider
"""
import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock

# Add backend_v2 to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import CurrentUser, UserRole
from query.query_planner import QueryPlanner
from query.query_executor import QueryExecutor
from security.authorization import AuthorizationService
from services.profile_service import ProfileService
from services.chat_service import ChatService
from ai.response_generator import ResponseGenerator
from utils.chat_history import ChatHistoryManager


@pytest.fixture
def employee_user():
    return CurrentUser(
        employee_id="TEMP99",
        employee_name="Intern3",
        email="intern3@motherson.com",
        role=UserRole.EMPLOYEE,
        department="SW",
        location="Pune",
    )


@pytest.fixture
def finance_user():
    return CurrentUser(
        employee_id="FIN001",
        employee_name="Finance Manager",
        email="finance.manager@motherson.com",
        role=UserRole.FINANCE,
        department="Finance",
        location="Delhi",
    )


@pytest.fixture
def admin_user():
    return CurrentUser(
        employee_id="ADMIN01",
        employee_name="Admin User",
        email="admin@motherson.com",
        role=UserRole.ADMIN,
        department="IT",
        location="Mumbai",
    )


@pytest.fixture
def test_df():
    """Minimal synthetic DataFrame with 10 rows for testing."""
    return pd.DataFrame({
        "Requisition No": [f"REQ-2024-{i:03d}" for i in range(1, 11)],
        "Requisition Description": [
            "Travel to Pune", "Software License", "Laptop Purchase",
            "Hotel Stay", "Training Course", "Office Supplies",
            "Vehicle Fuel", "Repair Service", "Flight Ticket", "Equipment"
        ],
        "Document Title": [f"Doc-{i}" for i in range(1, 11)],
        "employee_name": [
            "Intern3", "Rahul Karn", "Prashant Saxena",
            "Intern3", "Rahul Karn", "Prashant Saxena",
            "Intern3", "Rahul Karn", "Prashant Saxena", "Intern3"
        ],
        "employee_id": [
            "TEMP99", "MI0168", "MI0161",
            "TEMP99", "MI0168", "MI0161",
            "TEMP99", "MI0168", "MI0161", "TEMP99"
        ],
        "Department": [
            "SW", "Engineering", "Finance",
            "SW", "Engineering", "Finance",
            "SW", "Engineering", "Finance", "SW"
        ],
        "Status": [
            "Approved", "Pending", "Approved",
            "Rejected", "Approved", "Pending",
            "Approved", "Pending", "Approved", "Pending"
        ],
        "Approved Value in INR": [
            50000.0, 0.0, 75000.0,
            0.0, 120000.0, 0.0,
            30000.0, 0.0, 85000.0, 0.0
        ],
        "Value in INR": [
            55000.0, 20000.0, 80000.0,
            15000.0, 125000.0, 10000.0,
            32000.0, 8000.0, 90000.0, 12000.0
        ],
        "Created On": pd.to_datetime([
            "2024-01-15", "2024-02-10", "2024-01-20",
            "2024-03-05", "2024-02-28", "2024-03-10",
            "2024-04-01", "2024-04-15", "2024-05-01", "2024-05-20"
        ]),
        "Finally Approved On": pd.to_datetime([
            "2024-01-20", None, "2024-01-25",
            None, "2024-03-05", None,
            "2024-04-10", None, "2024-05-10", None
        ]),
        "Cost Centre": ["CC001", "CC002", "CC003"] * 3 + ["CC001"],
        "Operational Unit Name": ["OU-SW", "OU-ENG", "OU-FIN"] * 3 + ["OU-SW"],
        "Currency": ["INR"] * 10,
        "Requested By": [
            "Intern3 (TEMP99)", "Rahul Karn (MI0168)", "Prashant Saxena (MI0161)",
        ] * 3 + ["Intern3 (TEMP99)"],
        "STARS Requisition No": [f"STARS-{i}" for i in range(1, 11)],
    })


@pytest.fixture
def mock_data_provider(test_df):
    """Mock DataProvider that returns the test DataFrame."""
    provider = MagicMock()
    provider.get_requisitions_df.return_value = test_df.copy()
    provider.get_all_requisitions.return_value = []
    return provider


@pytest.fixture
def query_planner():
    return QueryPlanner()


@pytest.fixture
def chat_svc(mock_data_provider, tmp_path):
    planner = QueryPlanner()
    executor = QueryExecutor(data_provider=mock_data_provider)
    llm_mock = MagicMock()
    llm_mock.generate.return_value = "Formatted LLM Response."
    response_gen = ResponseGenerator(llm_service=llm_mock)
    auth = AuthorizationService()
    profile_svc = ProfileService()
    history_file = str(tmp_path / "chat_history.json")
    chat_hist = ChatHistoryManager(history_file=history_file)

    return ChatService(
        query_planner=planner,
        query_executor=executor,
        response_generator=response_gen,
        authorization=auth,
        profile_service=profile_svc,
        chat_history=chat_hist,
    )
