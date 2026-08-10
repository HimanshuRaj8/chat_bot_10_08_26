"""
Backend V3 — Pytest conftest
"""
import os
import sys
import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import CurrentUser, UserRole
from data.excel_provider import ExcelDataProvider
from data.employee_repository import EmployeeRepository
from data.requisition_repository import RequisitionRepository
from auth.authentication import AuthService
from auth.session_store import SessionStore
from auth.authorization import AuthorizationService
from context.conversation import ConversationManager
from query.parser import QueryParser
from query.validator import QueryPlanValidator
from query.entity_resolver import EntityResolver
from query.query_executor import QueryExecutor
from llm.response_generator import ResponseGenerator
from services.chat_service import ChatService


@pytest.fixture
def base_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_folder(base_dir):
    return os.path.join(base_dir, "Sample")


def _pick_test_file(upload_name: str, sample_name: str, base_dir: str) -> str:
    upload_path = os.path.join(base_dir, "uploads", upload_name)
    sample_path = os.path.join(base_dir, "Sample", sample_name)
    return upload_path if os.path.exists(upload_path) else sample_path


@pytest.fixture
def req_excel(base_dir):
    return _pick_test_file("Requisitions_Latest.xlsx", "Requisitions.xlsx", base_dir)


@pytest.fixture
def emp_excel(base_dir):
    return _pick_test_file("Employees_Latest.xlsx", "Employees.xlsx", base_dir)


@pytest.fixture
def fin_excel(base_dir):
    return _pick_test_file("Finance_Latest.xlsx", "Finance.xlsx", base_dir)


@pytest.fixture
def data_provider(req_excel, emp_excel, fin_excel):
    return ExcelDataProvider(
        requisition_path=req_excel,
        employee_path=emp_excel,
        finance_path=fin_excel,
    )


@pytest.fixture
def employee_repo(data_provider):
    return EmployeeRepository(data_provider)


@pytest.fixture
def requisition_repo(data_provider):
    return RequisitionRepository(data_provider)


@pytest.fixture
def auth_service(data_provider):
    return AuthService(data_provider, SessionStore())


@pytest.fixture
def auth_gate():
    return AuthorizationService()


@pytest.fixture
def conv_manager():
    return ConversationManager()


@pytest.fixture
def query_parser():
    # Pass None for LLM Client during standard unit testing to enforce deterministic fallback parser
    return QueryParser(llm_client=None)


@pytest.fixture
def query_validator():
    return QueryPlanValidator()


@pytest.fixture
def entity_resolver(employee_repo, requisition_repo):
    return EntityResolver(employee_repo, requisition_repo)


@pytest.fixture
def query_executor(requisition_repo, employee_repo):
    return QueryExecutor(requisition_repo, employee_repo)


@pytest.fixture
def response_generator():
    return ResponseGenerator(llm_client=None)


@pytest.fixture
def chat_svc(
    query_parser,
    query_validator,
    auth_gate,
    entity_resolver,
    query_executor,
    response_generator,
    conv_manager,
):
    return ChatService(
        query_parser=query_parser,
        query_validator=query_validator,
        authorization_service=auth_gate,
        entity_resolver=entity_resolver,
        query_executor=query_executor,
        response_generator=response_generator,
        conversation_manager=conv_manager,
    )


@pytest.fixture
def employee_user():
    return CurrentUser(
        employee_id="MI0095",
        employee_name="Ajay Singh Tomar",
        email="ajay.tomar@motherson.com",
        role=UserRole.EMPLOYEE,
        department="SW",
    )


@pytest.fixture
def finance_user():
    return CurrentUser(
        employee_id="TEMP99",
        employee_name="Intern3",
        email="Software.Intern3@motherson.com",
        role=UserRole.FINANCE,
        department="SW",
    )


@pytest.fixture
def admin_user():
    return CurrentUser(
        employee_id="MI0001",
        employee_name="System Admin",
        email="admin@motherson.com",
        role=UserRole.ADMIN,
        department="IT",
    )
