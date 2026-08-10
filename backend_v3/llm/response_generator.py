"""
Backend V3 — Response Generator
"""
import logging
from typing import Dict, Any, List, Optional

from models.query import QueryPlan, VerifiedResult, ResponseType, QueryIntent, SubjectScope
from llm.client import LLMClient

logger = logging.getLogger(__name__)


class ResponseGenerator:

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def generate_response(self, plan: QueryPlan, result: VerifiedResult) -> str:
        """
        Generates the final conversational response message based on the VerifiedResult.
        Prefers deterministic templates for accuracy, falling back to LLM narration if needed.
        """
        if not result.success:
            return result.message

        t = result.response_type

        # ── 1. Error / Clarification / Out of Scope ──────────────────────────
        if t == ResponseType.ERROR:
            return result.message
        elif t == ResponseType.CLARIFICATION:
            return result.message
        elif t == ResponseType.OUT_OF_SCOPE:
            return "I can help with requisitions, approvals, reimbursements, approval status, and authorized approval-system analytics."
        elif t == ResponseType.NO_DATA:
            return result.message or "I couldn't find any matching requisitions in the available approval-system data."

        # ── 2. Profile Metrics ────────────────────────────────────────────────
        if plan.intent == QueryIntent.PROFILE:
            return self._narrate_profile_result(plan, result)

        # ── 3. Single Record details ──────────────────────────────────────────
        if t == ResponseType.SINGLE_RECORD:
            return self._narrate_single_record(plan, result)

        # ── 4. Summary result (single aggregations) ───────────────────────────
        if t == ResponseType.SUMMARY:
            return self._narrate_summary(plan, result)

        # ── 5. Analytics (grouped / trends tables) ────────────────────────────
        if t == ResponseType.ANALYTICS:
            return self._narrate_analytics(plan, result)

        # ── 6. Record Lists ───────────────────────────────────────────────────
        if t == ResponseType.RECORD_LIST:
            records = result.data.get("records", []) if result.data else []
            count = result.total or len(records)
            if not records:
                return f"I found {count} requisitions matching your request."

            # Build a Markdown table for the first page of results
            rows_md = []
            for r in records:
                s = r.get("status", "")
                s_lower = s.lower()
                is_app = "approved" in s_lower
                is_pend = any(w in s_lower for w in ("pending", "open", "waiting"))
                emoji = "✅" if is_app else "⏳" if is_pend else "❌"
                req_no = r.get("requisition_no", "")
                desc = r.get("description", "")[:45] + ("..." if len(r.get("description", "")) > 45 else "")
                app_val = r.get("approved_value_inr", 0.0)
                app_by = r.get("approved_by", "") or ""
                # Try to extract approver from status if blank
                if not app_by and is_app:
                    import re
                    m2 = re.search(r'(?:approved by)[:\s]+([^(\n]+)', s, re.IGNORECASE)
                    if m2:
                        app_by = m2.group(1).strip().rstrip("- ")
                rows_md.append(f"| {req_no} | {desc} | {emoji} | ₹{app_val:,.2f} | {app_by} |")

            table = (
                "| Requisition No | Description | Status | Approved Value | Approved By |\n"
                "| --- | --- | --- | --- | --- |\n"
            ) + "\n".join(rows_md)

            return f"I found **{count}** requisitions matching your request. Below are the details:\n\n{table}"

        # Fallback to LLM if available
        if self.llm and self.llm.is_available():
            try:
                prompt = f"Narrate these query results naturally to the user:\nQuery: {plan.original_question}\nData: {result.to_dict()}"
                return self.llm.generate(prompt)
            except Exception as e:
                logger.warning(f"Response LLM failed: {e}")

        return result.message

    # ── Private Narrators ─────────────────────────────────────────────────────

    def _narrate_profile_result(self, plan: QueryPlan, result: VerifiedResult) -> str:
        rec = result.data.get("record") if result.data else None
        if not rec:
            return "I was unable to retrieve your profile information."
        
        m = plan.profile_metric
        if m == "EmployeeID":
            return f"Your Employee ID is **{rec['employee_id']}**."
        elif m == "Name":
            return f"Your name is **{rec['name']}**."
        elif m == "Department":
            return f"You are in the **{rec['department']}** department."
        elif m == "Location":
            return f"Your location is **{rec.get('location', 'N/A')}**."
        elif m == "Role":
            return f"Your role is **{rec['role']}**."
        elif m == "Email":
            return f"Your email address is **{rec['email']}**."
        else:
            # Full Profile
            return (
                f"### 👤 Your Profile Details\n"
                f"- **Name**: {rec['name']}\n"
                f"- **Employee ID**: {rec['employee_id']}\n"
                f"- **Role**: {rec['role']}\n"
                f"- **Department**: {rec['department']}"
            )

    def _narrate_single_record(self, plan: QueryPlan, result: VerifiedResult) -> str:
        rec = result.data.get("record") if result.data else None
        if not rec:
            return "No requisition record found."

        req_no = rec.get("requisition_no", "")
        desc = rec.get("description", "No description provided")
        status = rec.get("status", "Pending")
        app_val = rec.get("approved_value_inr", 0.0)
        app_by = rec.get("approved_by", "N/A")
        val = rec.get("value_inr", 0.0)

        detail = result.data.get("requested_detail")
        if detail == "approver":
            if status.lower() == "approved":
                return f"Requisition **{req_no}** was approved by **{app_by}**."
            else:
                return f"Requisition **{req_no}** is currently **{status}** and has not been approved."
        elif detail == "description":
            return f"Requisition **{req_no}** is for: *\"{desc}\"*."
        elif detail == "approved_value":
            return f"The approved value for requisition **{req_no}** is **₹{app_val:,.2f}**."
        elif detail == "requested_value":
            return f"The requested value for requisition **{req_no}** was **₹{val:,.2f}**."
        elif detail == "created_on":
            return f"Requisition **{req_no}** was created on **{rec.get('created_on', 'N/A')}**."

        # Default summary card narration
        # Status can be "Finally Approved By...", "Approved", "Pending", etc.
        status_lower = status.lower()
        is_approved = "approved" in status_lower
        is_pending = any(w in status_lower for w in ("pending", "open", "waiting", "awaiting"))
        status_emoji = "✅" if is_approved else "⏳" if is_pending else "❌"
        status_display = status.title() if status else "Unknown"

        # If approved_by is blank, try to extract from status text
        # e.g. "Finally Approved By Ajay Singh Tomar-(Mi0095)"
        if not app_by or app_by == "N/A":
            import re
            m = re.search(r'(?:approved by|approved (?:by)?)[:\s]+([^(\n]+)', status, re.IGNORECASE)
            if m:
                app_by = m.group(1).strip().rstrip("- ")

        return (
            f"Here are the details for requisition **{req_no}**:\n\n"
            f"- **Description**: {desc}\n"
            f"- **Status**: {status_emoji} {status_display}\n"
            f"- **Value**: ₹{val:,.2f}\n"
            f"- **Approved Value**: ₹{app_val:,.2f}\n"
            f"- **Approved By**: {app_by}\n"
            f"- **Created On**: {rec.get('created_on', 'N/A')}"
        )

    def _narrate_summary(self, plan: QueryPlan, result: VerifiedResult) -> str:
        metrics = result.analytics
        if not metrics:
            return result.message

        val = metrics.get("value", 0.0)
        count = metrics.get("count", 0)
        agg = metrics.get("aggregation", "SUM")

        # Format rupees
        val_str = f"₹{val:,.2f}"

        # Clean dates label
        date_lbl = plan.date_range.label or "the available period"

        # Check filter options
        status_lbl = plan.filters.get("status", "")
        kw_lbl = plan.filters.get("description_keyword", "")

        scope_lbl = "my" if plan.subject_scope == SubjectScope.CURRENT_USER else "all"
        if plan.subject_scope == SubjectScope.SPECIFIC_EMPLOYEE:
            scope_lbl = f"{plan.target_employee_name}'s"

        if agg == "SUM":
            desc_phrase = f"total value of {status_lbl} requisitions" if status_lbl else "total value of requisitions"
            if kw_lbl:
                desc_phrase += f" for '{kw_lbl}'"
            return f"The {scope_lbl} {desc_phrase} for {date_lbl} is **{val_str}** (across {count} claims)."
        elif agg == "COUNT" or plan.metric == "count":
            desc_phrase = f"{status_lbl} requisitions" if status_lbl else "requisitions"
            if kw_lbl:
                desc_phrase += f" for '{kw_lbl}'"
            return f"I found **{count}** {scope_lbl} {desc_phrase} for {date_lbl}."
        elif agg == "AVG":
            return f"The average approved reimbursement value for {date_lbl} is **{val_str}**."
        elif agg == "MAX":
            return f"The maximum approved value for {date_lbl} is **{val_str}**."
        elif agg == "MIN":
            return f"The minimum approved value for {date_lbl} is **{val_str}**."

        return f"Summary calculation completed: {agg} = {val_str}"

    def _narrate_analytics(self, plan: QueryPlan, result: VerifiedResult) -> str:
        data = result.data.get("analytics_data", []) if result.data else []
        if not data:
            return "No data found to build analytics summary."

        # Case 1: April month requisition summary
        if plan.group_by == "month_period" and len(data) == 1:
            row = data[0]
            val = row.get("value", 0.0)
            count = row.get("count", 0)
            month_label = row.get("group", "")
            
            # Format month name (e.g. 2026-04 -> April 2026)
            parts = month_label.split("-")
            month_fmt = month_label
            if len(parts) == 2:
                import calendar
                try:
                    m_idx = int(parts[1])
                    month_name = calendar.month_name[m_idx]
                    month_fmt = f"{month_name} {parts[0]}"
                except Exception:
                    pass

            val_str = f"₹{val:,.2f}"
            
            # Match prompt requirement exactly: "I found 75 requisitions from April 2026 with a total approved value of ₹307,872.63."
            return (
                f"I found **{count}** requisitions from **{month_fmt}** with a total approved value of **{val_str}**.\n\n"
                f"| Month | Approved Value (INR) | Count |\n"
                f"| --- | --- | --- |\n"
                f"| {month_label} | {val_str} | {count} |"
            )

        # Standard grouped lists
        group_type = "Department" if plan.group_by == "Department" else "Employee" if plan.group_by == "employee_name" else "Group"
        desc = "approved reimbursement totals"
        if plan.filters.get("status"):
            desc = f"{plan.filters['status']} totals"

        rows = []
        total_value = 0.0
        total_count = 0
        for row in data:
            group = str(row.get("group") or "N/A").strip() or "N/A"
            value = float(row.get("value") or 0.0)
            count = int(row.get("count") or 0)
            total_value += value
            total_count += count
            if plan.group_by == "employee_name":
                employee_id = str(row.get("employee_id") or "N/A").strip() or "N/A"
                rows.append(f"| {group} | {employee_id} | \u20b9{value:,.2f} | {count} |")
            else:
                rows.append(f"| {group} | \u20b9{value:,.2f} | {count} |")

        if plan.group_by == "employee_name":
            table = (
                "| Employee | Employee ID | Approved Value (INR) | Count |\n"
                "| --- | --- | ---: | ---: |\n"
                + "\n".join(rows)
            )
        else:
            table = (
                f"| {group_type} | Approved Value (INR) | Count |\n"
                "| --- | ---: | ---: |\n"
                + "\n".join(rows)
            )

        is_top_one = plan.limit == 1 and len(data) == 1
        if is_top_one:
            top = data[0]
            group = str(top.get("group") or "N/A").strip() or "N/A"
            value = float(top.get("value") or 0.0)
            count = int(top.get("count") or 0)
            employee_id = str(top.get("employee_id") or "N/A").strip() or "N/A"
            if plan.group_by == "employee_name":
                return (
                    f"**{group}** ({employee_id}) has the highest approved value: "
                    f"**\u20b9{value:,.2f}** across **{count}** claims.\n\n{table}"
                )
            return (
                f"**{group}** has the highest approved value: "
                f"**\u20b9{value:,.2f}** across **{count}** claims.\n\n{table}"
            )

        total_line = ""
        if len(data) > 1:
            total_line = f"\n\n**Total**: \u20b9{total_value:,.2f} across {total_count} claims."

        return f"Here is the breakdown of {desc} grouped by {group_type.lower()}:\n\n{table}{total_line}"
