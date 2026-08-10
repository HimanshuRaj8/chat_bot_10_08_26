"""
Backend V2 — Excel Data Provider

Loads Requisitions, Employees, and Finance roles directly from Excel files using pandas.
Fast, deterministic, 100% vector-free data provider with atomic reload capabilities.
"""
import os
import re
import logging
from typing import List, Dict, Optional, Any, Tuple
import pandas as pd

from models.requisition import RequisitionRecord
from models.query import SubjectScope
from models.user import CurrentUser, UserRole
from .base_provider import DataProvider

logger = logging.getLogger(__name__)


class ExcelDataProvider(DataProvider):

    def __init__(
        self,
        requisition_path: str,
        employee_path: str,
        finance_path: str,
    ):
        self._req_path = requisition_path
        self._emp_path = employee_path
        self._fin_path = finance_path

        self._employees: Dict[str, CurrentUser] = {}
        self._email_to_user: Dict[str, CurrentUser] = {}
        self._finance_roles: Dict[str, UserRole] = {}

        self._req_df: Optional[pd.DataFrame] = None
        self._req_records: Optional[List[RequisitionRecord]] = None

        self._load_all()

    # ── DataProvider Contract Implementation ─────────────────────────────────

    def get_requisitions_df(self) -> pd.DataFrame:
        return self._build_requisitions_df()

    def get_all_requisitions(self) -> List[RequisitionRecord]:
        if self._req_records is None:
            self._req_records = self._build_requisition_records()
        return self._req_records

    def get_user_by_email(self, email: str) -> CurrentUser:
        email_clean = email.strip().lower()
        if email_clean not in self._email_to_user:
            name = email_clean.split("@")[0].replace(".", " ").title()
            emp_id = email_clean.split("@")[0].upper()
            user = CurrentUser(
                employee_id=emp_id,
                employee_name=name,
                email=email_clean,
                role=UserRole.EMPLOYEE,
            )
            user.role = self._finance_roles.get(email_clean,
                         self._finance_roles.get(emp_id, UserRole.EMPLOYEE))
            return user

        user = self._email_to_user[email_clean]
        return user

    def get_user_by_employee_id(self, employee_id: str) -> Optional[CurrentUser]:
        return self._employees.get(employee_id.strip().upper())

    def refresh(self, requisition_path: str, employee_path: str, finance_path: str) -> int:
        """
        Atomic reload: parses and validates candidate structures from the new Excel files.
        Only replaces active memory state if all files parse successfully.
        """
        logger.info(f"Initiating atomic refresh with files: req='{requisition_path}', emp='{employee_path}', fin='{finance_path}'")

        # 1. Parse candidates
        cand_emp_path = employee_path if os.path.exists(employee_path) else self._emp_path
        cand_fin_path = finance_path if os.path.exists(finance_path) else self._fin_path
        cand_req_path = requisition_path if os.path.exists(requisition_path) else self._req_path

        cand_employees, cand_email_to_user = self._parse_employees_file(cand_emp_path)
        cand_finance_roles = self._parse_finance_roles(cand_fin_path, cand_employees, cand_email_to_user)
        cand_df, cand_records = self._parse_requisitions_file(cand_req_path)

        if len(cand_records) == 0:
            raise ValueError(f"Uploaded requisition Excel '{cand_req_path}' contains zero valid requisition records.")

        # 2. Atomic swap of active state
        self._req_path = cand_req_path
        self._emp_path = cand_emp_path
        self._fin_path = cand_fin_path

        self._employees = cand_employees if cand_employees else self._employees
        self._email_to_user = cand_email_to_user if cand_email_to_user else self._email_to_user
        self._finance_roles = cand_finance_roles if cand_finance_roles else self._finance_roles

        self._req_df = cand_df
        self._req_records = cand_records

        logger.info(f"Atomic refresh successful: {len(self._req_records)} requisition records loaded into active state.")
        return len(self._req_records)

    # ── Private Parsers ───────────────────────────────────────────────────────

    def _load_all(self):
        self._employees, self._email_to_user = self._parse_employees_file(self._emp_path)
        self._finance_roles = self._parse_finance_roles(self._fin_path, self._employees, self._email_to_user)
        self._req_df, self._req_records = self._parse_requisitions_file(self._req_path)

    def _parse_employees_file(self, path: str) -> Tuple[Dict[str, CurrentUser], Dict[str, CurrentUser]]:
        employees = {}
        email_to_user = {}
        if not os.path.exists(path):
            logger.warning(f"Employee Excel not found: {path}")
            return employees, email_to_user

        try:
            df = pd.read_excel(path)
            df = self._normalize_columns(df)
            for _, row in df.iterrows():
                emp_id = str(row.get("Employee ID", "")).strip()
                if not emp_id or emp_id == "nan":
                    continue
                email = str(row.get("Official Email ID", "")).strip().lower()
                name = str(row.get("Employee Name", "")).strip()
                user = CurrentUser(
                    employee_id=emp_id,
                    employee_name=name,
                    email=email,
                    role=UserRole.EMPLOYEE,
                    department=str(row.get("Department", "")).strip() or None,
                    location=str(row.get("Location", "")).strip() or None,
                    teams_name=str(row.get("Outlook / Teams Name", "")).strip() or None,
                )
                employees[emp_id] = user
                if email and email != "nan":
                    email_to_user[email] = user
            logger.info(f"Parsed {len(employees)} employees from '{path}'.")
        except Exception as e:
            logger.error(f"Failed to parse Employee Excel '{path}': {e}")
        return employees, email_to_user

    def _parse_finance_file_into(
        self,
        path: str,
        target_map: Dict[str, UserRole],
        target_employees: Dict[str, CurrentUser],
        target_email_to_user: Dict[str, CurrentUser],
    ):
        if not os.path.exists(path):
            return
        try:
            df = pd.read_excel(path)
            df = self._normalize_columns(df)
            for _, row in df.iterrows():
                emp_id = str(row.get("Employee ID", "")).strip()
                email = (str(row.get("Email", "")).strip() or str(row.get("Official Email ID", "")).strip()).lower()
                role_str = str(row.get("Role", "")).strip().lower()

                if "admin" in role_str:
                    role = UserRole.ADMIN
                elif "finance" in role_str:
                    role = UserRole.FINANCE
                else:
                    role = UserRole.EMPLOYEE

                if emp_id and emp_id != "nan":
                    target_map[emp_id] = role
                    if emp_id in target_employees:
                        target_employees[emp_id].role = role
                if email and email != "nan":
                    target_map[email] = role
                    if email in target_email_to_user:
                        target_email_to_user[email].role = role
        except Exception as e:
            logger.error(f"Failed to parse Finance Excel '{path}': {e}")

    def _parse_finance_roles(
        self,
        path: str,
        target_employees: Dict[str, CurrentUser],
        target_email_to_user: Dict[str, CurrentUser],
    ) -> Dict[str, UserRole]:
        target_map = {}
        # 1. Base sample finance/admin roles
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sample_fin = os.path.join(os.path.dirname(base_dir), "Sample", "Finance.xlsx")
        if os.path.exists(sample_fin):
            self._parse_finance_file_into(sample_fin, target_map, target_employees, target_email_to_user)

        # 2. Overlay configured/uploaded finance file
        if os.path.exists(path) and os.path.abspath(path) != os.path.abspath(sample_fin):
            self._parse_finance_file_into(path, target_map, target_employees, target_email_to_user)

        logger.info(f"Parsed {len(target_map)} finance/admin roles.")
        return target_map

    # ── Requisition column-name alias map ────────────────────────────────────
    # Maps variants found in real Excels to the canonical names expected by
    # QueryExecutor, ResponseGenerator and all downstream callers.
    _REQ_COL_ALIASES: Dict[str, str] = {
        # Monetary – uppercase-I variant (the real Excel uses "In" not "in")
        "Value In INR":              "Value in INR",
        "Approved Value In INR":     "Approved Value in INR",
        "HOD Approved value":        "HOD Approved Value",
        # Alternate column header spellings
        "Requisition Description":   "Requisition Description",   # identity – kept for clarity
        "Document title":            "Document Title",
        "STARS Requisition No.":     "STARS Req. No.",
        "S No.":                     "S.No.",
        "Requested By Employee Id":  "Requested By Employee ID",
    }

    def _canonicalize_req_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Renames known variant column names to canonical names used by the executor."""
        return df.rename(columns=self._REQ_COL_ALIASES)

    @staticmethod
    def _extract_employee_id_from_field(value: str) -> str:
        """Extracts employee ID from 'Name (MIXXXX)' format. Returns '' if not found."""
        m = re.search(r'\(\s*([A-Z]{2}\d+)\s*\)', str(value), re.IGNORECASE)
        return m.group(1).upper() if m else ""

    def _parse_requisitions_file(self, path: str) -> Tuple[pd.DataFrame, List[RequisitionRecord]]:
        records = []
        if not os.path.exists(path):
            logger.warning(f"Requisition Excel not found: {path}")
            return pd.DataFrame(), records

        try:
            df = pd.read_excel(path)
            df = self._normalize_columns(df)          # strips whitespace from all column names
            df = self._canonicalize_req_columns(df)   # normalizes known variant names

            # ── Derive employee_id from 'Requested By' field if not already present ──
            if "employee_id" not in df.columns:
                if "Requested By Employee ID" in df.columns:
                    df["employee_id"] = df["Requested By Employee ID"].astype(str).str.strip().str.upper()
                elif "Requested By" in df.columns:
                    df["employee_id"] = df["Requested By"].apply(self._extract_employee_id_from_field)
                else:
                    df["employee_id"] = ""

            # ── Derive employee_name and Department by joining with employee directory ──
            if "employee_name" not in df.columns:
                if "Requested By Employee Name" in df.columns:
                    df["employee_name"] = df["Requested By Employee Name"].astype(str).str.strip()
                elif "Requested By" in df.columns:
                    # Extract the name part before the parenthesis
                    df["employee_name"] = df["Requested By"].str.replace(
                        r'\s*\([^)]*\)\s*$', '', regex=True
                    ).str.strip()
                else:
                    df["employee_name"] = ""

            if "Department" not in df.columns:
                # Build a lookup from employee directory
                emp_dept = {emp_id: u.department for emp_id, u in self._employees.items() if u.department}
                df["Department"] = df["employee_id"].map(emp_dept).fillna("")
            else:
                # Ensure empty-string Department cells get filled from employee directory
                if self._employees:
                    emp_dept = {emp_id: u.department for emp_id, u in self._employees.items() if u.department}
                    df["Department"] = df.apply(
                        lambda row: emp_dept.get(str(row["employee_id"]).upper(), row["Department"])
                        if not row["Department"] else row["Department"],
                        axis=1
                    )

            # ── Ensure numeric columns are floats ────────────────────────────
            for col in ["Value in INR", "Approved Value in INR", "Value", "Approved Value"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            # ── Ensure dates are parsed ──────────────────────────────────────
            for col in ["Created On", "Finally Approved On"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

            # ── Build RequisitionRecord list ─────────────────────────────────
            for idx, row in df.iterrows():
                created_val = row.get("Created On", "")
                created_str = str(created_val).split("T")[0] if pd.notna(created_val) else ""

                fin_val = row.get("Finally Approved On", "")
                fin_str = str(fin_val).split("T")[0] if pd.notna(fin_val) else ""

                val_inr = float(row.get("Value in INR", row.get("Value", 0.0)) or 0.0)
                app_val_inr = float(row.get("Approved Value in INR", row.get("Approved Value", 0.0)) or 0.0)

                rec = RequisitionRecord(
                    s_no=int(row.get("S.No.", idx + 1)) if pd.notna(row.get("S.No.")) else (idx + 1),
                    requisition_no=str(row.get("Requisition No", "")).strip(),
                    description=str(row.get("Requisition Description", "")).strip(),
                    document_title=str(row.get("Document Title", "")).strip(),
                    stars_req_no=str(row.get("STARS Req. No.", "")).strip(),
                    requested_by_raw=str(row.get("Requested By", "")).strip(),
                    employee_name=str(row.get("employee_name", "")).strip(),
                    employee_id=str(row.get("employee_id", "")).strip(),
                    operational_unit=str(row.get("Operational Unit Name", "")).strip(),
                    cost_centre=str(row.get("Cost Centre", "")).strip(),
                    department=str(row.get("Department", "")).strip(),
                    created_on=created_str,
                    finally_approved_on=fin_str,
                    currency=str(row.get("Currency", "INR")).strip(),
                    value=float(row.get("Value", val_inr) or 0.0),
                    value_in_inr=val_inr,
                    approved_value=float(row.get("Approved Value", app_val_inr) or 0.0),
                    approved_value_in_inr=app_val_inr,
                    hod_approved_value=pd.to_numeric(row.get("HOD Approved Value", 0.0), errors="coerce") or 0.0,
                    status=str(row.get("Status", "")).strip(),
                    approved_by=str(row.get("Approved By", "")).strip(),
                )
                records.append(rec)

            logger.info(f"Parsed {len(records)} requisition records from '{path}'.")
            return df, records
        except Exception as e:
            logger.error(f"Failed to parse Requisition Excel '{path}': {e}", exc_info=True)
            return pd.DataFrame(), []

    def _build_requisition_records(self) -> List[RequisitionRecord]:
        if self._req_records is not None:
            return self._req_records
        _, records = self._parse_requisitions_file(self._req_path)
        return records

    def _build_requisitions_df(self) -> pd.DataFrame:
        if self._req_df is not None:
            return self._req_df
        df, _ = self._parse_requisitions_file(self._req_path)
        self._req_df = df
        return self._req_df

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Strip whitespace from column names."""
        df.columns = [str(c).strip() for c in df.columns]
        return df
