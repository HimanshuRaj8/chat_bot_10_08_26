"""
Backend V3 — Authorization Service
"""
import logging
from models.user import CurrentUser, UserRole
from models.query import QueryPlan, SubjectScope

logger = logging.getLogger(__name__)


class AuthorizationError(PermissionError):
    """Raised when authorization check fails."""
    pass


class AuthorizationService:

    def validate(self, user: CurrentUser, plan: QueryPlan) -> None:
        """
        Validates the QueryPlan against the authenticated CurrentUser's role.
        Enforces security scope dynamically and injects mandatory filters.
        """
        is_privileged = user.role in (UserRole.FINANCE, UserRole.ADMIN)

        # ── EMPLOYEE Role ─────────────────────────────────────────────────────
        if not is_privileged:
            # 1. Check if trying to access a specific other employee
            if plan.target_employee_id and plan.target_employee_id.strip().upper() != user.employee_id.upper():
                raise AuthorizationError(
                    "🔒 Access denied. You are not authorized to query another employee's requisitions."
                )
            if plan.target_employee_name and (not plan.target_employee_id or plan.target_employee_id.strip().upper() != user.employee_id.upper()):
                # If they specified a name, check if it's theirs
                name_clean = plan.target_employee_name.strip().lower()
                user_name_clean = user.employee_name.strip().lower()
                # Check for direct inclusion or match
                if name_clean not in user_name_clean and user_name_clean not in name_clean:
                    raise AuthorizationError(
                        "🔒 Access denied. You are not authorized to query another employee's requisitions."
                    )

            # 2. Inject current user scope (mandatorily restrict query)
            plan.subject_scope = SubjectScope.CURRENT_USER
            plan.target_employee_id = user.employee_id
            plan.target_employee_name = user.employee_name
            logger.info(f"Authorization: Enforced CURRENT_USER scope for Employee {user.employee_id}")
            return

        # ── FINANCE / ADMIN Role ──────────────────────────────────────────────
        else:
            # Privileged users can query CURRENT_USER, SPECIFIC_EMPLOYEE, or ALL_EMPLOYEES
            if plan.subject_scope == SubjectScope.CURRENT_USER:
                plan.target_employee_id = user.employee_id
                plan.target_employee_name = user.employee_name
            
            logger.info(
                f"Authorization: Permitted {plan.subject_scope.value} query for "
                f"{user.role.value} user {user.employee_id}"
            )
            return

    def require_admin(self, user: CurrentUser, action: str = "this action") -> None:
        """Raises AuthorizationError if user is not Admin."""
        if user.role != UserRole.ADMIN:
            raise AuthorizationError(
                f"🔒 Admin authorization required for {action}."
            )
