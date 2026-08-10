"""
Backend V3 — Excel Data Provider
"""
import os
import re
import logging
import dataclasses
from typing import List, Dict, Optional, Tuple
import pandas as pd

from models.requisition import RequisitionRecord
from models.user import CurrentUser, UserRole

logger = logging.getLogger(__name__)


class ExcelDataProvider:

    _REQ_COL_ALIASES: Dict[str, str] = {
        "Value In INR":              "Value in INR",
        "Approved Value In INR":     "Approved Value in INR",
        "HOD Approved value":        "HOD Approved Value",
        "Document title":            "Document Title",
        "STARS Requisition No.":     "STARS Req. No.",
        "S No.":                     "S.No.",
        "Requested By Employee Id":  "Requested By Employee ID",
    }

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

    def get_requisitions_df(self) -> pd.DataFrame:
        if self._req_df is None:
            self._load_all()
        return self._req_df

    def get_all_requisitions(self) -> List[RequisitionRecord]:
        if self._req_records is None:
            self._load_all()
        return self._req_records

    def get_all_employees(self) -> Dict[str, CurrentUser]:
        return self._employees

    def get_finance_roles(self) -> Dict[str, UserRole]:
        return self._finance_roles

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
        else:
            user = dataclasses.replace(self._email_to_user[email_clean])

        # Enforce overlay of the finance role dynamically
        role = self._finance_roles.get(user.email.strip().lower(),
               self._finance_roles.get(user.employee_id.strip().upper(), UserRole.EMPLOYEE))
        user.role = role
        return user

    def get_user_by_employee_id(self, employee_id: str) -> Optional[CurrentUser]:
        emp_id_clean = employee_id.strip().upper()
        if emp_id_clean in self._employees:
            user = dataclasses.replace(self._employees[emp_id_clean])
            role = self._finance_roles.get(user.email.strip().lower(),
                   self._finance_roles.get(emp_id_clean, UserRole.EMPLOYEE))
            user.role = role
            return user
        return None

    def refresh(self, requisition_path: str, employee_path: str, finance_path: str) -> int:
        """
        Transactional update: only updates active state if all reloaded sheets parse successfully.
        """
        logger.info(f"V3 refresh: req='{requisition_path}', emp='{employee_path}', fin='{finance_path}'")

        cand_req_path = requisition_path if os.path.exists(requisition_path) else self._req_path
        cand_emp_path = employee_path if os.path.exists(employee_path) else self._emp_path
        cand_fin_path = finance_path if os.path.exists(finance_path) else self._fin_path

        cand_employees, cand_email_to_user = self._parse_employees_file(cand_emp_path)
        cand_finance_roles = self._parse_finance_roles(cand_fin_path, cand_employees, cand_email_to_user)
        cand_df, cand_records = self._parse_requisitions_file(cand_req_path, cand_employees)

        if len(cand_records) == 0:
            raise ValueError("Requisition data contains 0 valid records.")

        # Swap active structures atomically
        self._req_path = cand_req_path
        self._emp_path = cand_emp_path
        self._fin_path = cand_fin_path

        self._employees = cand_employees
        self._email_to_user = cand_email_to_user
        self._finance_roles = cand_finance_roles

        self._req_df = cand_df
        self._req_records = cand_records

        logger.info(f"V3 refresh successful: {len(self._req_records)} records loaded.")
        return len(self._req_records)

    # ── Private Parsers ───────────────────────────────────────────────────────

    def _load_all(self):
        self._employees, self._email_to_user = self._parse_employees_file(self._emp_path)
        self._finance_roles = self._parse_finance_roles(self._fin_path, self._employees, self._email_to_user)
        self._req_df, self._req_records = self._parse_requisitions_file(self._req_path, self._employees)

    def _parse_employees_file(self, path: str) -> Tuple[Dict[str, CurrentUser], Dict[str, CurrentUser]]:
        employees = {}
        email_to_user = {}
        if not os.path.exists(path):
            logger.warning(f"Employee Excel not found: {path}")
            return employees, email_to_user

        try:
            df = pd.read_excel(path)
            df.columns = [str(c).strip() for c in df.columns]
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
            df.columns = [str(c).strip() for c in df.columns]
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

        return target_map

    @staticmethod
    def _extract_employee_id_from_field(value: str) -> str:
        m = re.search(r'\(\s*([A-Z][A-Z0-9]*\d[A-Z0-9]*)\s*\)', str(value), re.IGNORECASE)
        return m.group(1).upper() if m else ""

    def _parse_requisitions_file(
        self, path: str, employees_dict: Dict[str, CurrentUser]
    ) -> Tuple[pd.DataFrame, List[RequisitionRecord]]:
        records = []
        if not os.path.exists(path):
            logger.warning(f"Requisition Excel not found: {path}")
            return pd.DataFrame(), records

        try:
            df = pd.read_excel(path)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.rename(columns=self._REQ_COL_ALIASES)

            # Extract employee_id
            if "employee_id" not in df.columns:
                if "Requested By Employee ID" in df.columns:
                    df["employee_id"] = df["Requested By Employee ID"].astype(str).str.strip().str.upper()
                elif "Requested By" in df.columns:
                    df["employee_id"] = df["Requested By"].apply(self._extract_employee_id_from_field)
                else:
                    df["employee_id"] = ""

            # Extract employee_name
            if "employee_name" not in df.columns:
                if "Requested By Employee Name" in df.columns:
                    df["employee_name"] = df["Requested By Employee Name"].astype(str).str.strip()
                elif "Requested By" in df.columns:
                    df["employee_name"] = df["Requested By"].str.replace(
                        r'\s*\([^)]*\)\s*$', '', regex=True
                    ).str.strip()
                else:
                    df["employee_name"] = ""

            # Resolve Department
            if "Department" not in df.columns:
                emp_dept = {emp_id: u.department for emp_id, u in employees_dict.items() if u.department}
                df["Department"] = df["employee_id"].map(emp_dept).fillna("")
            else:
                if employees_dict:
                    emp_dept = {emp_id: u.department for emp_id, u in employees_dict.items() if u.department}
                    df["Department"] = df.apply(
                        lambda row: emp_dept.get(str(row["employee_id"]).upper(), row["Department"])
                        if not row["Department"] else row["Department"],
                        axis=1
                    )

            # Ensure numbers are floats
            for col in ["Value in INR", "Approved Value in INR", "Value", "Approved Value"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            # Ensure dates are parsed
            for col in ["Created On", "Finally Approved On"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

            # Build RequisitionRecord objects
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

            return df, records
        except Exception as e:
            logger.error(f"Failed to parse Requisition Excel '{path}': {e}", exc_info=True)
            return pd.DataFrame(), []
