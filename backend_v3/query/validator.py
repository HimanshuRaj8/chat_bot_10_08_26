"""
Backend V3 — Query Plan Validator
"""
import logging
from models.query import QueryPlan, QueryIntent, SubjectScope
from models.user import CurrentUser

logger = logging.getLogger(__name__)


class QueryPlanValidationError(ValueError):
    """Exception raised when a query plan fails validation check."""
    pass


class QueryPlanValidator:

    def validate(self, plan: QueryPlan, user: CurrentUser) -> None:
        """
        Validates structure and security invariants of the parsed QueryPlan
        before any database execution.
        """
        # 1. Check for valid intent
        if not plan.intent or not isinstance(plan.intent, QueryIntent):
            raise QueryPlanValidationError("Invalid QueryPlan intent.")

        # 2. Check Employee specific bounds
        if not user.is_finance and plan.intent not in (QueryIntent.OUT_OF_SCOPE, QueryIntent.PROFILE):
            # Employee role must be restricted to CURRENT_USER subject scope
            if plan.subject_scope != SubjectScope.CURRENT_USER:
                raise QueryPlanValidationError("🔒 Invalid plan scope for Employee role.")
            if plan.target_employee_id and plan.target_employee_id.strip().upper() != user.employee_id.upper():
                raise QueryPlanValidationError("🔒 Target employee ID mismatch for Employee role.")

        # 3. Check for valid Date Ranges
        if plan.date_range.start and plan.date_range.end:
            if plan.date_range.start > plan.date_range.end:
                raise QueryPlanValidationError("Start date cannot be after end date.")

        # 4. Check for aggregate metrics
        if plan.intent == QueryIntent.ANALYTICS:
            if not plan.aggregation:
                plan.aggregation = "SUM"

        logger.info("QueryPlan successfully validated.")
