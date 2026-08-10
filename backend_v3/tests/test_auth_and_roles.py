"""
Backend V3 — Authentication and Role Overlay Tests
"""
import os
import pytest
from models.user import UserRole
from data.excel_provider import ExcelDataProvider


def test_login_success(auth_service):
    success, user, token = auth_service.authenticate_email("rahul.karn@motherson.com")
    assert success is True
    assert user.employee_id == "MI0168"
    assert user.role == UserRole.EMPLOYEE
    assert token.startswith("session_")


def test_login_unauthorized_domain(auth_service):
    success, user, msg = auth_service.authenticate_email("hacker@gmail.com")
    assert success is False
    assert user is None
    assert "corporate accounts" in msg


def test_finance_role_overlay(auth_service):
    # Intern3 / TEMP99 is in Employee list, but has Finance role in Sample/Finance.xlsx
    success, user, token = auth_service.authenticate_email("software.intern3@motherson.com")
    assert success is True
    assert user.employee_id == "TEMP99"
    assert user.role == UserRole.FINANCE


def test_admin_role_overlay(auth_service):
    success, user, token = auth_service.authenticate_email("admin@motherson.com")
    assert success is True
    assert user.role == UserRole.ADMIN


def test_role_overlay_survives_refresh(data_provider, auth_service, req_excel, emp_excel, fin_excel):
    # Initial state
    user = data_provider.get_user_by_employee_id("TEMP99")
    assert user.role == UserRole.FINANCE

    # Run dataset refresh (simulated reload)
    data_provider.refresh(req_excel, emp_excel, fin_excel)

    # Check data provider directly
    refreshed_user = data_provider.get_user_by_employee_id("TEMP99")
    assert refreshed_user.role == UserRole.FINANCE

    # Check active session lookup reload
    session_user = auth_service.get_user_from_session(f"session_TEMP99_software.intern3@motherson.com")
    # Store user in session
    auth_service.session_store.store("test_token", refreshed_user)
    session_user = auth_service.get_user_from_session("test_token")
    assert session_user.role == UserRole.FINANCE
