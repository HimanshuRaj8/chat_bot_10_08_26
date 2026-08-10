"""
Backend V2 — Profile Service

Answers ALL identity and profile questions directly from the authenticated session.
NEVER touches the database, DataFrame, or ChromaDB.
This is the first handler invoked when QueryPlanner detects PROFILE intent.
"""
from models.user import CurrentUser
from models.query import QueryPlan


class ProfileService:

    PROFILE_METRIC_RESPONSES = {
        "EmployeeID": lambda u: (
            f"Your Employee ID is **{u.employee_id}**."
        ),
        "Name": lambda u: (
            f"Your name is **{u.employee_name}**."
        ),
        "Role": lambda u: (
            f"Your role is **{u.role.value}**."
        ),
        "Department": lambda u: (
            f"You are in the **{u.department or 'N/A'}** department."
        ),
        "Email": lambda u: (
            f"Your corporate email is **{u.email}**."
        ),
        "Location": lambda u: (
            f"Your location is **{u.location or 'N/A'}**."
        ),
        "FullProfile": lambda u: (
            f"**Your Profile**\n\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| Name | {u.employee_name} |\n"
            f"| Employee ID | {u.employee_id} |\n"
            f"| Email | {u.email} |\n"
            f"| Department | {u.department or 'N/A'} |\n"
            f"| Role | {u.role.value} |\n"
            f"| Location | {u.location or 'N/A'} |"
        ),
    }

    def answer(self, plan: QueryPlan, user: CurrentUser) -> str:
        """
        Returns a deterministic profile answer from session data.
        No database access. No LLM call.
        """
        metric = plan.profile_metric or "FullProfile"
        handler = self.PROFILE_METRIC_RESPONSES.get(metric)
        if handler:
            return handler(user)
        # Fallback to full profile
        return self.PROFILE_METRIC_RESPONSES["FullProfile"](user)
