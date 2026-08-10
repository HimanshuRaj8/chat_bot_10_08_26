"""
Backend V3 — Entity Resolver
"""
import logging
from typing import Optional

from models.query import QueryPlan, QueryIntent, VerifiedResult, ResponseType
from data.employee_repository import EmployeeRepository
from data.requisition_repository import RequisitionRepository

logger = logging.getLogger(__name__)


class EntityResolver:

    def __init__(self, employee_repo: EmployeeRepository, requisition_repo: RequisitionRepository):
        self.employee_repo = employee_repo
        self.requisition_repo = requisition_repo

    def resolve_entities(self, plan: QueryPlan) -> Optional[VerifiedResult]:
        """
        Resolves named employees and exact requisition numbers against raw enterprise data.
        Returns a VerifiedResult (e.g., CLARIFICATION, NO_DATA) to short-circuit the execution
        if resolution fails or is ambiguous. Otherwise returns None.
        """
        # 1. Resolve Target Employee Name
        if plan.target_employee_name and not plan.target_employee_id:
            matches = self.employee_repo.resolve_by_name(plan.target_employee_name)
            
            if len(matches) == 0:
                req_match = self._resolve_employee_from_requisitions(plan.target_employee_name)
                if req_match:
                    plan.target_employee_id = req_match["employee_id"]
                    plan.target_employee_name = req_match["employee_name"]
                    logger.info(
                        "Resolved employee from requisitions: %s (%s)",
                        plan.target_employee_name,
                        plan.target_employee_id,
                    )
                else:
                    logger.warning(f"Employee entity not resolved for search hint '{plan.target_employee_name}'")
                    return VerifiedResult(
                        success=True,
                        response_type=ResponseType.NO_DATA,
                        message=f"I couldn't find any employee matching '{plan.target_employee_name}' in the employee directory or requisition records.",
                    )
            
            if len(matches) > 1:
                logger.info(f"Ambiguous matches found ({len(matches)}) for employee hint '{plan.target_employee_name}'")
                # Format options for clarification
                options = [f"{m.employee_name} ({m.employee_id}) - {m.department or 'N/A'}" for m in matches]
                choices_str = ", ".join(options)
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.CLARIFICATION,
                    message=f"I found multiple employees matching '{plan.target_employee_name}': {choices_str}. Which employee do you mean?",
                    data={"matches": [m.to_api_dict() for m in matches]},
                )
            
            # Exactly one match
            matched_user = matches[0]
            plan.target_employee_id = matched_user.employee_id
            plan.target_employee_name = matched_user.employee_name
            logger.info(f"Resolved employee entity: {plan.target_employee_name} ({plan.target_employee_id})")

        # 2. Verify Directly Specified Employee ID
        if plan.target_employee_id:
            user_check = self.employee_repo.get_by_id(plan.target_employee_id)
            if not user_check:
                req_match = self._resolve_employee_from_requisitions(plan.target_employee_id)
                if req_match:
                    plan.target_employee_id = req_match["employee_id"]
                    plan.target_employee_name = req_match["employee_name"]
                    logger.info(
                        "Resolved employee ID from requisitions: %s (%s)",
                        plan.target_employee_name,
                        plan.target_employee_id,
                    )
                else:
                    logger.warning(f"Target employee ID '{plan.target_employee_id}' not found in directory or requisitions.")
                    return VerifiedResult(
                        success=True,
                        response_type=ResponseType.NO_DATA,
                        message=f"I couldn't find an employee with ID '{plan.target_employee_id}' in the directory or requisition records.",
                    )
            else:
                plan.target_employee_name = user_check.employee_name

        # 3. Resolve Requisition Number existence
        if plan.intent == QueryIntent.GET_REQUISITION and plan.exact_req_no:
            req_check = self.requisition_repo.get_requisition_by_id(plan.exact_req_no)
            if not req_check:
                logger.warning(f"Requisition lookup for '{plan.exact_req_no}' failed: record not found.")
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.NO_DATA,
                    message=f"No requisition found with number '{plan.exact_req_no}'.",
                )

        return None

    def _resolve_employee_from_requisitions(self, hint: str) -> Optional[dict]:
        df = self.requisition_repo.data_provider.get_requisitions_df()
        if df.empty or "employee_id" not in df.columns:
            return None

        hint_clean = hint.strip().lower()
        id_mask = df["employee_id"].astype(str).str.strip().str.lower() == hint_clean

        name_mask = False
        if "employee_name" in df.columns:
            words = [w for w in hint_clean.split() if w]
            name_series = df["employee_name"].astype(str).str.strip().str.lower()
            if words:
                name_mask = name_series.apply(lambda value: all(word in value for word in words))

        matched = df[id_mask | name_mask].copy()
        if matched.empty:
            return None

        unique = matched[["employee_id", "employee_name"]].dropna().drop_duplicates()
        unique = unique[unique["employee_id"].astype(str).str.strip() != ""]
        if unique.empty:
            return None

        row = unique.iloc[0]
        return {
            "employee_id": str(row["employee_id"]).strip().upper(),
            "employee_name": str(row["employee_name"]).strip(),
        }
