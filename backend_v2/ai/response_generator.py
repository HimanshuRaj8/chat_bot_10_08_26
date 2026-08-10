"""
Backend V2 — ResponseGenerator

Converts a VerifiedResult + original question into a natural language response.

CRITICAL CONTRACT:
  - ResponseGenerator NEVER queries data.
  - ResponseGenerator NEVER re-interprets the question.
  - ResponseGenerator ONLY explains the pre-computed VerifiedResult.
  - The LLM receives the verified data embedded in the prompt as ground truth.
  - The LLM is explicitly instructed NOT to calculate, guess, or add facts.

Formatting Rules:
  - Single metric → conversational sentence
  - Multi-row result → markdown table
  - Profile query → handled by ProfileService (not here)
  - Empty result → polite "no records found" with filters listed
"""
import json
import logging
from typing import Optional

from models.query import QueryPlan, QueryIntent, OutputType, VerifiedResult, SubjectScope, QueryEntity
from models.user import CurrentUser
from .llm_service import LLMService

logger = logging.getLogger(__name__)

INR_FORMAT = "₹{:,.2f}"


class ResponseGenerator:

    SYSTEM_INSTRUCTION = """You are an Enterprise Approval AI Assistant for Motherson Group.
Your task is ONLY to present pre-calculated data to the user in clear, professional language.

STRICT RULES:
- DO NOT calculate, compute, or derive any numbers yourself.
- DO NOT add information not present in the Verified Data below.
- DO NOT guess employee names, IDs, or amounts.
- DO NOT reference ChromaDB, vectors, or documents.
- Use ₹ for INR amounts and format numbers with commas.
- For tables, use proper Markdown table format.
- Keep responses concise and professional.
- Always address the user by first name if known.
"""

    def __init__(self, llm_service: LLMService, max_table_rows: int = 20):
        self.llm = llm_service
        self.max_table_rows = max_table_rows

    def generate(
        self,
        result: VerifiedResult,
        plan: QueryPlan,
        user: CurrentUser,
    ) -> str:
        """
        Main entry point. Returns a formatted natural language response.
        For simple single-metric or single-record results, returns without LLM call.
        For complex multi-row results, builds a structured prompt for Mistral.
        """
        # Handle empty / no-data results without LLM
        if not result.success or (result.total_records_analyzed == 0 and not result.result):
            return self._format_empty(result, plan, user)

        if result.error_message and not result.result:
            return f"ℹ️ {result.error_message}"

        # Dispatch specific analytical follow-up intents
        if plan.intent == QueryIntent.APPROVER_ANALYSIS:
            return self._format_approver_analysis(result, plan, user)

        if plan.intent == QueryIntent.DATE_ANALYSIS:
            return self._format_date_analysis(result, plan, user)

        if plan.intent == QueryIntent.COMPARISON:
            return self._format_comparison_analysis(result, plan, user)

        # Special formatting for single month/quarter summary queries
        if plan.intent == QueryIntent.TREND and len(result.result) == 1:
            if plan.group_by == "month_period":
                return self._format_month_summary(result, plan)
            if plan.group_by == "quarter_period":
                return self._format_quarter_summary(result, plan)

        if plan.is_follow_up and (
            plan.filters.get("projection") == "description" or
            any(w in (plan.original_question or "").lower() for w in ["made for", "purpose", "for what", "why were", "descriptions", "description"])
        ):
            return self._format_description_projection(result, plan, user)

        # Format based on output type
        if plan.intent == QueryIntent.RANKING and (plan.aggregation == "LATEST" or plan.metric == "Created On"):
            return self._format_latest_requisition(result, plan, user)

        if plan.output_type == OutputType.NATURAL_TEXT and plan.intent == QueryIntent.RANKING:
            return self._format_single_ranking(result, plan, user)

        if plan.output_type == OutputType.SINGLE_METRIC:
            return self._format_single_metric(result, plan, user)

        if plan.output_type == OutputType.TABLE:
            return self._format_table_with_llm(result, plan, user)

        if plan.output_type == OutputType.SHORT_SUMMARY:
            return self._format_lookup_summary(result, plan, user)

        # Default: use LLM to narrate
        return self._format_table_with_llm(result, plan, user)

    # ── Formatters ────────────────────────────────────────────────────────────

    def _format_single_ranking(
        self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser
    ) -> str:
        """Formats a single top-1 ranking result as natural language text."""
        if not result.result:
            return self._format_empty(result, plan, user)

        row = result.result[0]
        scope = plan.subject_scope

        # Case 1: CURRENT_USER scope ("What is my highest approved reimbursement?")
        if scope == SubjectScope.CURRENT_USER:
            req_no = row.get("Requisition No", "N/A")
            desc = row.get("Requisition Description", row.get("Document Title", ""))
            val = row.get("Approved Value in INR", row.get("Value in INR", row.get("value", 0)))
            formatted_val = self._format_inr(val)
            desc_part = f" for **{desc}**" if desc else ""
            req_part = f" (Requisition No: **{req_no}**)" if req_no != "N/A" else ""
            return f"Your highest approved reimbursement is **{formatted_val}**{desc_part}{req_part}."

        # Case 2: ALL_EMPLOYEES scope
        if plan.entity == QueryEntity.EMPLOYEE:
            emp_name = row.get("group", row.get("employee_name", "Unknown"))
            emp_id = row.get("employee_id", "")
            id_part = f" ({emp_id})" if emp_id else ""
            val = row.get("value", row.get("Approved Value in INR", 0))
            formatted_val = self._format_inr(val)
            return f"**{emp_name}**{id_part} has the highest total approved reimbursement at **{formatted_val}**."

        if plan.entity == QueryEntity.DEPARTMENT:
            dept = row.get("group", row.get("Department", "Unknown"))
            val = row.get("value", row.get("Approved Value in INR", 0))
            formatted_val = self._format_inr(val)
            return f"The department with the highest approved value is **{dept}** with **{formatted_val}**."

        if plan.entity == QueryEntity.REQUISITION:
            req_no = row.get("Requisition No", row.get("group", "N/A"))
            emp = row.get("employee_name", "")
            emp_part = f" requested by **{emp}**" if emp else ""
            desc = row.get("Requisition Description", "")
            desc_part = f" for **{desc}**" if desc else ""
            val = row.get("Approved Value in INR", row.get("Value in INR", row.get("value", 0)))
            formatted_val = self._format_inr(val)
            return f"The requisition with the highest approved value is **{req_no}**{emp_part}{desc_part} at **{formatted_val}**."

        return self._format_single_metric(result, plan, user)

    def _format_single_metric(
        self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser
    ) -> str:
        """Formats a single aggregated value. No LLM needed."""
        if not result.result:
            return self._format_empty(result, plan, user)

        row = result.result[0]
        value = row.get("value", 0)
        count = row.get("count", result.total_records_analyzed)

        metric_label = self._metric_label(plan.metric)
        agg_label = self._aggregation_label(plan.aggregation)
        scope_label = self._scope_label(result, plan, user)
        date_label = f" in **{plan.date_range.label}**" if plan.date_range.label else ""
        filter_label = self._filter_label(plan)

        if plan.is_follow_up:
            total_reqs = result.total_records_analyzed
            if plan.intent == QueryIntent.COUNT:
                status_part = f" matching status '{plan.filters.get('status')}'" if plan.filters.get("status") else ""
                return f"There are **{value}** requisitions{status_part} in this active set of **{total_reqs}**."
            if plan.aggregation == "SUM":
                metric_name = "requested amount" if "value_inr" in str(plan.metric).lower() else "approved amount"
                return f"The total {metric_name} across these **{total_reqs}** requisitions is **{self._format_inr(value)}**."
            if plan.aggregation == "AVG":
                return f"The average approved amount across these **{total_reqs}** requisitions is **{self._format_inr(value)}**."

        if plan.intent == QueryIntent.COUNT:
            return (
                f"There {'is' if count == 1 else 'are'} **{count:,}** "
                f"requisition{'s' if count != 1 else ''} {scope_label}{date_label}{filter_label}."
            )

        formatted_value = self._format_inr(value) if "inr" in (plan.metric or "").lower() else f"{value:,.2f}"
        return (
            f"The **{agg_label} {metric_label}** {scope_label}{date_label}{filter_label} "
            f"is **{formatted_value}** across **{count:,}** requisition{'s' if count != 1 else ''}."
        )

    def _format_approver_analysis(self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser) -> str:
        if not result.result:
            return "No approval records found for these requisitions."
        row = result.result[0]
        total = row.get("total_requisitions", len(result.result))
        breakdown = row.get("breakdown", [])
        if breakdown:
            if len(breakdown) == 1:
                app_name = breakdown[0]["approver"]
                return f"The {total} requisition(s) were finally approved by **{app_name}**."
            else:
                lines = [f"These {total} requisitions were approved by:"]
                for item in breakdown:
                    lines.append(f"- **{item['approver']}**: {item['count']} requisition(s)")
                return "\n".join(lines)
        summary = row.get("approver_summary", f"All {total} requisitions passed official department approval workflow.")
        return summary

    def _format_date_analysis(self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser) -> str:
        if not result.result:
            return "No date records found for these requisitions."
        row = result.result[0]
        total = row.get("total_requisitions", 1)
        min_d = row.get("min_date")
        max_d = row.get("max_date")
        if min_d and max_d:
            if min_d == max_d:
                return f"These {total} requisition(s) were approved on **{min_d}**."
            return f"These {total} requisitions were approved between **{min_d}** and **{max_d}**."
        return f"Found approval dates for {total} requisitions."

    def _format_comparison_analysis(self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser) -> str:
        if not result.result:
            return "No comparison data available."
        row = result.result[0]
        total = row.get("total_requisitions", 0)
        req_v = self._format_inr(row.get("requested_value_inr", 0.0))
        app_v = self._format_inr(row.get("approved_value_inr", 0.0))
        diff = self._format_inr(row.get("difference_inr", 0.0))
        return f"For these **{total}** requisitions, the Total Requested Value is **{req_v}** and the Total Approved Value is **{app_v}** (a difference of **{diff}**)."

    def _format_table_with_llm(
        self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser
    ) -> str:
        """Builds a prompt with the verified data and asks LLM to present it or returns clean table."""
        table_md = self._build_markdown_table(result, plan)

        # For list/filter results, return clean deterministic header + table_md
        if plan.intent == QueryIntent.FILTER:
            if result.total_records_analyzed == 0 or not result.result:
                return self._format_empty(result, plan, user)
            start_idx = (result.page - 1) * result.page_size + 1
            end_idx = start_idx + len(result.result) - 1
            filter_str = f" ({', '.join(result.applied_filters)})" if result.applied_filters else ""
            header = f"Showing records **{start_idx}–{end_idx}** of **{result.total_records_analyzed:,}** matching requisitions{filter_str}."
            return f"{header}\n\n{table_md}"

        # Build minimal context for the LLM for complex summary/trend tables
        scope_label = self._scope_label(result, plan, user)
        date_label = f" in {plan.date_range.label}" if plan.date_range.label else ""
        filter_label = self._filter_label(plan)
        entity = result.entity
        metric_label = self._metric_label(plan.metric)
        agg_label = self._aggregation_label(plan.aggregation)
        total = result.total_records_analyzed

        data_summary = json.dumps(result.result[:self.max_table_rows], indent=2, default=str)

        prompt = f"""{self.SYSTEM_INSTRUCTION}

USER: {user.employee_name} ({user.employee_id}) | Role: {user.role.value}
ORIGINAL QUESTION: {plan.original_question}

VERIFIED DATA (pre-calculated, ground truth — do NOT recalculate):
- Query Type: {result.query_type}
- Entity: {entity}
- Metric: {metric_label}
- Aggregation: {agg_label}
- Scope: {scope_label}{date_label}{filter_label}
- Total Records Analyzed: {total}
- Applied Filters: {', '.join(result.applied_filters) if result.applied_filters else 'none'}

RESULT DATA:
{data_summary}

FORMATTED TABLE (use this exactly):
{table_md}

Write a professional 1-2 sentence introduction, then present the table above.
Do not add any numbers or facts not shown in the data.
"""
        return self.llm.generate(prompt)

    def _format_lookup_summary(
        self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser
    ) -> str:
        """Formats a single requisition lookup result."""
        if not result.result:
            return f"No requisition found with number **{plan.exact_req_no}**."

        row = result.result[0]
        req_no = row.get("Requisition No", plan.exact_req_no or "N/A")
        emp = row.get("employee_name", "N/A")
        status = row.get("Status", "N/A")
        approved = self._format_inr(row.get("Approved Value in INR", 0))
        requested = self._format_inr(row.get("Value in INR", 0))
        created = row.get("Created On", "N/A")
        dept = row.get("Department", "N/A")
        desc = row.get("Requisition Description", "")

        return (
            f"**Requisition {req_no}**\n\n"
            f"| Field | Details |\n"
            f"|---|---|\n"
            f"| Employee | {emp} |\n"
            f"| Department | {dept} |\n"
            f"| Status | {status} |\n"
            f"| Requested Value | {requested} |\n"
            f"| Approved Value | {approved} |\n"
            f"| Created On | {created} |\n"
            + (f"| Description | {desc[:100]}... |" if desc else "")
        )

    def _format_empty(
        self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser
    ) -> str:
        """Returns a friendly no-results message."""
        scope_label = self._scope_label(result, plan, user)
        date_label = f" in **{plan.date_range.label}**" if plan.date_range.label else ""
        filter_label = self._filter_label(plan)
        filters_applied = ", ".join(result.applied_filters) if result.applied_filters else "none"
        return (
            f"No requisitions found {scope_label}{date_label}{filter_label}.\n\n"
            f"*Filters applied: {filters_applied}*\n\n"
            f"Please check the filters or try a different query."
        )

    # ── Table Builder ─────────────────────────────────────────────────────────

    def _build_markdown_table(self, result: VerifiedResult, plan: QueryPlan) -> str:
        """Builds a proper Markdown table from VerifiedResult.result."""
        rows = result.result[:self.max_table_rows]
        if not rows:
            return "_No data to display._"

        # Determine columns from the data
        sample = rows[0]
        cols = list(sample.keys())

        # Friendly headers
        header_map = {
            "group": self._entity_column_label(plan),
            "value": self._metric_label(plan.metric),
            "count": "Count",
            "Requisition No": "Requisition No.",
            "employee_name": "Employee",
            "employee_id": "Employee ID",
            "Department": "Department",
            "Status": "Status",
            "Approved Value in INR": "Approved Value (INR)",
            "Value in INR": "Requested Value (INR)",
            "Created On": "Created On",
            "Finally Approved On": "Approved On",
            "Requisition Description": "Description",
            "Cost Centre": "Cost Centre",
        }

        headers = [header_map.get(c, c) for c in cols]
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]

        for row in rows:
            cells = []
            for col in cols:
                val = row.get(col, "")
                if isinstance(val, float) and col in ("value", "Approved Value in INR", "Value in INR"):
                    cells.append(self._format_inr(val))
                elif isinstance(val, (int, float)):
                    cells.append(f"{val:,}")
                else:
                    cells.append(str(val)[:60] if len(str(val)) > 60 else str(val))
            lines.append("| " + " | ".join(cells) + " |")

        if len(result.result) > self.max_table_rows:
            lines.append(f"\n*Showing top {self.max_table_rows} of {len(result.result)} results.*")

        return "\n".join(lines)

    # ── Label Helpers ─────────────────────────────────────────────────────────

    def _metric_label(self, metric: Optional[str]) -> str:
        labels = {
            "Approved Value in INR": "Approved Value (INR)",
            "Value in INR": "Requested Value (INR)",
            "count": "Count",
            "approved_value_inr": "Approved Value (INR)",
        }
        return labels.get(metric or "", metric or "Value")

    def _aggregation_label(self, agg: str) -> str:
        return {
            "SUM": "Total", "COUNT": "Count", "AVG": "Average",
            "MAX": "Maximum", "MIN": "Minimum", "NONE": "",
        }.get(agg.upper(), agg)

    def _scope_label(self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser) -> str:
        from models.query import SubjectScope
        if plan.subject_scope == SubjectScope.CURRENT_USER:
            return f"for **{user.employee_name}** ({user.employee_id})"
        elif plan.subject_scope == SubjectScope.SPECIFIC_EMPLOYEE and plan.target_employee_id:
            return f"for employee **{plan.target_employee_id}**"
        return "organization-wide"

    def _filter_label(self, plan: QueryPlan) -> str:
        parts = []
        if plan.filters.get("status"):
            parts.append(f"with status **{plan.filters['status']}**")
        if plan.filters.get("description_keyword"):
            parts.append(f"matching **{plan.filters['description_keyword']}**")
        return " " + ", ".join(parts) if parts else ""

    def _entity_column_label(self, plan: QueryPlan) -> str:
        labels = {
            "Department": "Department",
            "employee_name": "Employee",
            "Cost Centre": "Cost Centre",
            "Operational Unit Name": "Operational Unit",
            "month_period": "Month",
            "quarter_period": "Quarter",
        }
        return labels.get(plan.group_by or "", "Group")

    @staticmethod
    def _format_inr(value) -> str:
        try:
            return f"₹{float(value):,.2f}"
        except (TypeError, ValueError):
            return "₹0.00"

    def _format_description_projection(self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser) -> str:
        if not result.result:
            return "No description records found for these requisitions."

        total = result.total_records_analyzed or len(result.result)
        lines = [f"The **{total}** requisition{'s' if total != 1 else ''} were requested for the following purposes:\n"]

        for item in result.result[:20]:
            req_no = item.get("Requisition No", "N/A")
            desc = str(item.get("Requisition Description", "")).strip() or "No description specified"
            val = item.get("Approved Value in INR", item.get("Value in INR"))
            val_str = f" ({self._format_inr(val)})" if val and isinstance(val, (int, float)) and val > 0 else ""
            lines.append(f"• **{req_no}** — {desc}{val_str}")

        return "\n".join(lines)

    def _format_latest_requisition(self, result: VerifiedResult, plan: QueryPlan, user: CurrentUser) -> str:
        if not result.result:
            return self._format_empty(result, plan, user)

        row = result.result[0]
        req_no = row.get("Requisition No", "N/A")
        status = row.get("Status", "N/A")
        created = row.get("Created On", "")
        desc = row.get("Requisition Description", "")
        val = row.get("Approved Value in INR", row.get("Value in INR", 0.0))

        created_part = f" created on **{created}**" if created else ""
        desc_part = f" ({desc})" if desc else ""

        if plan.filters.get("requested_field") == "status" or "status" in (plan.original_question or "").lower():
            return (
                f"Your most recent requisition is **{req_no}**{desc_part}{created_part}, "
                f"and its current status is **{status}**."
            )

        val_str = self._format_inr(val) if isinstance(val, (int, float)) and val > 0 else ""
        val_part = f" for **{val_str}**" if val_str else ""

        return (
            f"Your most recent requisition is **{req_no}**{desc_part}{val_part}{created_part}. "
            f"Status: **{status}**."
        )

    def _format_month_summary(self, result: VerifiedResult, plan: QueryPlan) -> str:
        row = result.result[0]
        group_val = row.get("group", "")
        month_label = group_val
        try:
            import datetime
            parts = group_val.split("-")
            if len(parts) == 2:
                y = int(parts[0])
                m = int(parts[1])
                dt = datetime.date(y, m, 1)
                month_label = dt.strftime("%B %Y")
        except Exception:
            pass

        count = row.get("count", 0)
        total_val = row.get("value", 0.0)
        formatted_val = self._format_inr(total_val)

        intro = f"I found **{count}** requisition{'s' if count != 1 else ''} from **{month_label}** with a total approved value of **{formatted_val}**."
        table_md = self._build_markdown_table(result, plan)
        return f"{intro}\n\n{table_md}"

    def _format_quarter_summary(self, result: VerifiedResult, plan: QueryPlan) -> str:
        row = result.result[0]
        group_val = row.get("group", "")
        quarter_label = group_val
        try:
            parts = group_val.split("-")
            if len(parts) == 2:
                quarter_label = f"{parts[1]} {parts[0]}"
        except Exception:
            pass

        count = row.get("count", 0)
        total_val = row.get("value", 0.0)
        formatted_val = self._format_inr(total_val)

        intro = f"I found **{count}** requisition{'s' if count != 1 else ''} from **{quarter_label}** with a total approved value of **{formatted_val}**."
        table_md = self._build_markdown_table(result, plan)
        return f"{intro}\n\n{table_md}"
