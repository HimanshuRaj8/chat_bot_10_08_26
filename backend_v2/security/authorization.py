"""
Backend V2 — Authorization Service

Enforces role-based access control BEFORE any data is retrieved.
This is the security gateway — if it raises, the query dies here.

Rules:
  - CURRENT_USER scope: always allowed for any role
  - SPECIFIC_EMPLOYEE scope: Finance and Admin only
  - ALL_EMPLOYEES scope: Finance and Admin only
  - Admin-only actions: explicit flag check
"""
import logging
from models.user import CurrentUser, UserRole
from models.query import QueryPlan, SubjectScope

logger = logging.getLogger(__name__)


class AuthorizationError(PermissionError):
    """Raised when an authorization check fails."""
    pass


class AuthorizationService:

    def validate(self, user: CurrentUser, plan: QueryPlan) -> None:
        """
        Validates that the authenticated user is permitted to execute this plan.
        Raises AuthorizationError with a user-safe message if denied.
        """
        scope = plan.subject_scope
        is_privileged = user.role in (UserRole.FINANCE, UserRole.ADMIN)

        if scope == SubjectScope.CURRENT_USER:
            # Always permitted — and executor will enforce the employee_id filter
            return

        if scope == SubjectScope.SPECIFIC_EMPLOYEE:
            if not is_privileged:
                raise AuthorizationError(
                    "🔒 Access denied. You are not authorized to query another employee's "
                    "requisitions. Only Finance and Admin users can access employee-specific data."
                )
            logger.info(
                f"AUTHORIZED: {user.employee_name} ({user.role.value}) → "
                f"SPECIFIC_EMPLOYEE query for {plan.target_employee_id}"
            )
            return

        if scope == SubjectScope.ALL_EMPLOYEES:
            if not is_privileged:
                raise AuthorizationError(
                    "🔒 Access denied. Organization-wide analytics require Finance or Admin role. "
                    "Please query your personal requisitions using 'my' (e.g. 'my pending requisitions')."
                )
            logger.info(
                f"AUTHORIZED: {user.employee_name} ({user.role.value}) → ALL_EMPLOYEES scope"
            )
            return

    def require_admin(self, user: CurrentUser, action: str = "this action") -> None:
        """Raises AuthorizationError if user is not Admin."""
        if user.role != UserRole.ADMIN:
            raise AuthorizationError(
                f"🔒 Admin authorization required for {action}."
            )
