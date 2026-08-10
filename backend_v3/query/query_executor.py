"""
Backend V3 — Query Executor
"""
import logging
import math
from typing import List, Dict, Optional, Any, Tuple

from models.query import QueryPlan, QueryIntent, VerifiedResult, ResponseType, SubjectScope
from models.user import CurrentUser
from data.requisition_repository import RequisitionRepository
from data.employee_repository import EmployeeRepository

logger = logging.getLogger(__name__)


class QueryExecutor:

    def __init__(self, requisition_repo: RequisitionRepository, employee_repo: EmployeeRepository):
        self.requisition_repo = requisition_repo
        self.employee_repo = employee_repo

    def execute(self, plan: QueryPlan, user: CurrentUser) -> VerifiedResult:
        """
        Executes a validated and authorized QueryPlan against repositories.
        Produces a VerifiedResult containing ground truth computed data.
        """
        try:
            # ── 1. GET_REQUISITION (exact lookup) ─────────────────────────────
            if plan.intent == QueryIntent.GET_REQUISITION:
                req = self.requisition_repo.get_requisition_by_id(plan.exact_req_no)
                if not req:
                    return self._no_data_result(plan, f"No requisition found with number '{plan.exact_req_no}'.")
                
                # Check target detail projection if requested
                detail = plan.filters.get("requested_detail")
                val_dict = req.to_source_dict()
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.SINGLE_RECORD,
                    message=f"Found requisition details for {plan.exact_req_no}.",
                    data={"record": val_dict, "requested_detail": detail},
                    sources=[val_dict],
                )

            # ── 2. GET_LATEST_REQUISITION ─────────────────────────────────────
            elif plan.intent == QueryIntent.GET_LATEST_REQUISITION:
                req = self.requisition_repo.get_latest_requisition(
                    scope=plan.subject_scope,
                    employee_id=plan.target_employee_id,
                    status=plan.filters.get("status"),
                    keyword=plan.filters.get("description_keyword"),
                    date_range=plan.date_range,
                    requisition_id_list=plan.filters.get("requisition_id_list"),
                    offset=0,
                )
                if not req:
                    return self._no_data_result(plan, "No latest requisition found.")
                
                val_dict = req.to_source_dict()
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.SINGLE_RECORD,
                    message="Found your latest requisition.",
                    data={"record": val_dict, "requested_field": plan.filters.get("requested_field")},
                    sources=[val_dict],
                )

            # ── 3. GET_PREVIOUS_REQUISITION ───────────────────────────────────
            elif plan.intent == QueryIntent.GET_PREVIOUS_REQUISITION:
                req = self.requisition_repo.get_latest_requisition(
                    scope=plan.subject_scope,
                    employee_id=plan.target_employee_id,
                    status=plan.filters.get("status"),
                    keyword=plan.filters.get("description_keyword"),
                    date_range=plan.date_range,
                    requisition_id_list=plan.filters.get("requisition_id_list"),
                    offset=1,  # previous = offset 1
                )
                if not req:
                    return self._no_data_result(plan, "No previous requisition found.")
                
                val_dict = req.to_source_dict()
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.SINGLE_RECORD,
                    message="Found your previous requisition.",
                    data={"record": val_dict},
                    sources=[val_dict],
                )

            # ── 4. LIST_REQUISITIONS (with pagination) ────────────────────────
            elif plan.intent == QueryIntent.LIST_REQUISITIONS:
                records, total_count = self.requisition_repo.get_requisitions(
                    scope=plan.subject_scope,
                    employee_id=plan.target_employee_id,
                    status=plan.filters.get("status"),
                    keyword=plan.filters.get("description_keyword"),
                    date_range=plan.date_range,
                    requisition_id_list=plan.filters.get("requisition_id_list"),
                    sort_field=plan.sort_field,
                    sort_direction=plan.sort_direction,
                    page=plan.page,
                    page_size=plan.page_size,
                )
                if total_count == 0:
                    return self._no_data_result(plan, "No matching requisitions found.")

                total_pages = math.ceil(total_count / plan.page_size)
                records_list = [r.to_source_dict() for r in records]

                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.RECORD_LIST,
                    message=f"I found {total_count} matching requisitions.",
                    data={"records": records_list},
                    sources=records_list,
                    applied_filters=self._build_applied_filters(plan),
                    page=plan.page,
                    page_size=plan.page_size,
                    total=total_count,
                    total_pages=total_pages,
                    has_next=(plan.page < total_pages),
                    has_previous=(plan.page > 1),
                )

            # ── 5. ANALYTICS (trend, grouped summary, single aggregate) ───────
            elif plan.intent == QueryIntent.ANALYTICS:
                # A. Trend queries (e.g., month-wise summary)
                if plan.group_by in ("month_period", "quarter_period"):
                    results = self.requisition_repo.get_trend(
                        scope=plan.subject_scope,
                        metric=plan.metric or "Approved Value in INR",
                        group_by=plan.group_by,
                        employee_id=plan.target_employee_id,
                        status=plan.filters.get("status"),
                        keyword=plan.filters.get("description_keyword"),
                        date_range=plan.date_range,
                        requisition_id_list=plan.filters.get("requisition_id_list"),
                    )
                    if not results:
                        return self._no_data_result(plan, "No trend data found.")
                    
                    return VerifiedResult(
                        success=True,
                        response_type=ResponseType.ANALYTICS,
                        message="Generated monthly/quarterly trend analysis.",
                        data={"analytics_data": results},
                        applied_filters=self._build_applied_filters(plan),
                    )

                # B. Grouped rankings/summaries
                elif plan.group_by:
                    results = self.requisition_repo.aggregate_requisitions(
                        scope=plan.subject_scope,
                        metric=plan.metric or "Approved Value in INR",
                        aggregation=plan.aggregation or "SUM",
                        employee_id=plan.target_employee_id,
                        status=plan.filters.get("status"),
                        keyword=plan.filters.get("description_keyword"),
                        date_range=plan.date_range,
                        requisition_id_list=plan.filters.get("requisition_id_list"),
                        group_by=plan.group_by,
                    )
                    if not results:
                        return self._no_data_result(plan, "No analytics data found.")

                    # Sort & Limit in Python safely
                    sort_asc = (plan.sort_direction.lower() == "asc")
                    sorted_results = sorted(
                        results,
                        key=lambda x: x.get("value", 0.0) if x.get("value") is not None else 0.0,
                        reverse=not sort_asc
                    )
                    if plan.limit:
                        sorted_results = sorted_results[:plan.limit]

                    return VerifiedResult(
                        success=True,
                        response_type=ResponseType.ANALYTICS,
                        message="Generated grouped summary analytics.",
                        data={"analytics_data": sorted_results},
                        applied_filters=self._build_applied_filters(plan),
                    )

                # C. Single aggregate value (e.g. sum, avg, count with no grouping)
                else:
                    results = self.requisition_repo.aggregate_requisitions(
                        scope=plan.subject_scope,
                        metric=plan.metric or "Approved Value in INR",
                        aggregation=plan.aggregation or "SUM",
                        employee_id=plan.target_employee_id,
                        status=plan.filters.get("status"),
                        keyword=plan.filters.get("description_keyword"),
                        date_range=plan.date_range,
                        requisition_id_list=plan.filters.get("requisition_id_list"),
                        group_by=None,
                    )
                    if not results:
                        return self._no_data_result(plan, "No summary values found.")

                    val = results[0]["value"]
                    count = results[0]["count"]
                    
                    return VerifiedResult(
                        success=True,
                        response_type=ResponseType.SUMMARY,
                        message="Calculated summary metrics.",
                        analytics={
                            "value": val,
                            "count": count,
                            "aggregation": plan.aggregation,
                            "metric": plan.metric,
                        },
                        applied_filters=self._build_applied_filters(plan),
                    )

            if plan.intent == QueryIntent.OUT_OF_SCOPE:
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.OUT_OF_SCOPE,
                    message="I can help with requisitions, approvals, reimbursements, approval status, and authorized approval-system analytics.",
                )

            # ── 6. PROFILE (user identity questions) ──────────────────────────
            if plan.intent == QueryIntent.PROFILE:
                profile_data = {
                    "name": user.employee_name,
                    "employee_id": user.employee_id,
                    "email": user.email,
                    "role": user.role.value,
                    "department": user.department or "N/A",
                    "location": user.location or "N/A",
                }
                return VerifiedResult(
                    success=True,
                    response_type=ResponseType.SINGLE_RECORD,
                    message="Here is your profile information.",
                    data={"record": profile_data},
                    sources=[profile_data],
                )

            # ── 7. LLM misclassified as ANALYTICS but without aggregation — treat as LIST ──
            # Default fallback
            return self._no_data_result(plan, "I'm not sure how to answer that. Could you rephrase your question?")

        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            return VerifiedResult(
                success=False,
                response_type=ResponseType.ERROR,
                message=f"I couldn't process that request because an internal error occurred: {e}",
            )

    def _no_data_result(self, plan: QueryPlan, msg: str) -> VerifiedResult:
        return VerifiedResult(
            success=True,
            response_type=ResponseType.NO_DATA,
            message=msg,
            applied_filters=self._build_applied_filters(plan),
        )

    def _build_applied_filters(self, plan: QueryPlan) -> List[str]:
        filters = []
        if plan.subject_scope == SubjectScope.CURRENT_USER:
            filters.append("employee = self")
        elif plan.subject_scope == SubjectScope.SPECIFIC_EMPLOYEE and plan.target_employee_id:
            filters.append(f"employee_id = {plan.target_employee_id}")
        if plan.date_range.label:
            filters.append(f"date = {plan.date_range.label}")
        if plan.filters.get("status"):
            filters.append(f"status = {plan.filters['status']}")
        if plan.filters.get("description_keyword"):
            filters.append(f"keyword = {plan.filters['description_keyword']}")
        return filters
