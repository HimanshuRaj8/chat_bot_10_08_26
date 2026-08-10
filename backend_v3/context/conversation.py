"""
Backend V3 — Conversation Context Manager and Resolver
"""
import re
import logging
from typing import Dict, Optional, List

from models.query import QueryPlan, QueryIntent, SubjectScope, QueryEntity
from models.context import ConversationContext
from models.user import CurrentUser

logger = logging.getLogger(__name__)


class ConversationManager:

    def __init__(self):
        self._contexts: Dict[str, ConversationContext] = {}

    def get_context(self, chat_id: str, user: CurrentUser) -> ConversationContext:
        """Retrieves or creates a ConversationContext for a user session."""
        context_key = f"{user.employee_id}_{chat_id}"
        if context_key not in self._contexts:
            self._contexts[context_key] = ConversationContext(
                chat_id=chat_id,
                user_id=user.employee_id,
                user_role=user.role.value,
            )
        return self._contexts[context_key]

    def remove_context(self, chat_id: str, user: CurrentUser) -> None:
        context_key = f"{user.employee_id}_{chat_id}"
        self._contexts.pop(context_key, None)


class ContextResolver:

    def resolve_context(self, question: str, plan: QueryPlan, context: ConversationContext, user: CurrentUser) -> None:
        """
        Resolves relative pronouns like "it", "that", "previous one" and
        paginations by modifying the QueryPlan in place based on context memory.
        Enforces that context safety checks happen in authorization layer subsequently.
        """
        q_lower = question.strip().lower()

        # ── 1. Pagination Follow-Up Resolution ───────────────────────────────
        target_page = self._detect_pagination_phrase(q_lower, context.last_page)
        if target_page is not None and context.last_plan:
            prev = context.last_plan
            plan.intent = prev.intent
            plan.entity = prev.entity
            plan.metric = prev.metric
            plan.aggregation = prev.aggregation
            plan.group_by = prev.group_by
            plan.filters = dict(prev.filters)
            plan.date_range = prev.date_range
            plan.subject_scope = prev.subject_scope
            plan.target_employee_id = prev.target_employee_id
            plan.target_employee_name = prev.target_employee_name
            plan.sort_field = prev.sort_field
            plan.sort_direction = prev.sort_direction
            plan.limit = prev.limit
            plan.page = target_page
            plan.page_size = prev.page_size
            plan.is_follow_up = True
            logger.info(f"ContextResolver: Resolved pagination turn to Page {plan.page}")
            return

        # ── 2. Reference / Pronoun Resolution ("it", "that", "previous one") ──
        has_it = bool(re.search(r"\b(it|this|that|its|approved amount|requested amount|who approved|what for|whom|who created|who submitted|who made|by whom)\b", q_lower))
        wants_details = bool(re.search(r"\b(details?|show|list)\b", q_lower))
        has_previous_one = "previous" in q_lower or "last one" in q_lower or "before" in q_lower
        
        is_follow_up = (
            has_it or has_previous_one or wants_details or
            any(w in q_lower for w in [
                "there", "total", "sum", "average", "avg", "mean", 
                "max", "min", "highest", "lowest", "count", "how many", 
                "who", "when", "what", "where", "compare", "which", "instead", 
                "details", "more", "approved", "pending", "rejected", "reimbursement"
            ])
            or (
                plan.intent in (QueryIntent.ANALYTICS, QueryIntent.LIST_REQUISITIONS, QueryIntent.GET_LATEST_REQUISITION)
                and not plan.filters.get("status")
                and not plan.filters.get("description_keyword")
                and (not plan.date_range or (not plan.date_range.start and not plan.date_range.end))
                and not plan.target_employee_id
                and not plan.target_employee_name
            )
        )
        
        # Check if the query is a follow-up reference
        if is_follow_up and context.last_plan:
            # Check if there is a target employee mismatch/change
            prev_emp = context.last_plan.target_employee_id or context.last_plan.target_employee_name
            new_emp = plan.target_employee_id or plan.target_employee_name
            
            # If the new query contains "all" keyword, we treat it as broadening scope
            contains_all = "all" in q_lower
            
            # If the new query explicitly introduces a new/different employee target,
            # or broadens scope, and contains no relative pronouns referencing the previous turn,
            # then it is a new unrelated query and should NOT inherit.
            has_pronouns = has_it or has_previous_one or bool(re.search(r"\b(his|her|their|him|them)\b", q_lower))
            if (new_emp and (new_emp != prev_emp) and not has_pronouns) or (contains_all and not has_pronouns):
                logger.info("ContextResolver: New target employee or broadened scope query detected. Starting a new fresh context.")
            else:
                plan.is_follow_up = True
                
                # Inherit scope & target employee if not explicitly overridden in the new plan
                if not plan.target_employee_id and not plan.target_employee_name:
                    plan.subject_scope = context.last_plan.subject_scope
                    plan.target_employee_id = context.last_plan.target_employee_id
                    plan.target_employee_name = context.last_plan.target_employee_name

                # Inherit filters (status, description_keyword, etc.)
                for key, val in context.last_plan.filters.items():
                    if key != "requested_detail" and val is not None and key not in plan.filters:
                        plan.filters[key] = val

                # Inherit date range if not explicitly overridden in the new plan
                has_new_date = plan.date_range and (plan.date_range.start or plan.date_range.end)
                if not has_new_date and context.last_plan.date_range and (context.last_plan.date_range.start or context.last_plan.date_range.end):
                    plan.date_range = context.last_plan.date_range

            # A. Resolve "previous one" to the previous requisition in the last result set
            if has_previous_one and context.latest_selection_single and context.full_requisition_ids:
                try:
                    ids_normalized = [i.strip().upper() for i in context.full_requisition_ids]
                    target_normalized = context.latest_selection_single.strip().upper()
                    
                    curr_idx = ids_normalized.index(target_normalized)
                    # Next oldest is index + 1 in a desc sorted list
                    if curr_idx + 1 < len(context.full_requisition_ids):
                        prev_req_no = context.full_requisition_ids[curr_idx + 1]
                        plan.intent = QueryIntent.GET_REQUISITION
                        plan.exact_req_no = prev_req_no
                        context.latest_selection_single = prev_req_no
                        logger.info(f"ContextResolver: Resolved 'previous one' to requisition {prev_req_no}")
                        return
                except ValueError as e:
                    logger.warning(f"ContextResolver index lookup failed: {e}")

            # B. Resolve "it" to the active requisition
            if (has_it or has_previous_one) and context.latest_selection_single:
                plan.exact_req_no = context.latest_selection_single
                plan.intent = QueryIntent.GET_REQUISITION
                logger.info(f"ContextResolver: Resolved pronoun 'it' to requisition {context.latest_selection_single}")

                # Detect specific details requested about the active requisition
                if any(w in q_lower for w in ["who approved", "approver", "approved by", "by whom"]):
                    plan.filters["requested_detail"] = "approver"
                elif any(w in q_lower for w in ["who created", "who submitted", "who made", "created by", "submitted by", "creator"]):
                    plan.filters["requested_detail"] = "creator"
                elif any(w in q_lower for w in ["what was it for", "purpose", "description"]):
                    plan.filters["requested_detail"] = "description"
                elif any(w in q_lower for w in ["approved value", "approved amount", "how much was approved"]):
                    plan.filters["requested_detail"] = "approved_value"
                elif any(w in q_lower for w in ["requested value", "requested amount", "how much was requested", "value"]):
                    plan.filters["requested_detail"] = "requested_value"
                elif any(w in q_lower for w in ["created", "submission date", "submitted on"]):
                    plan.filters["requested_detail"] = "created_on"
                return

            if wants_details and (has_it or has_previous_one):
                plan.intent = QueryIntent.LIST_REQUISITIONS
                plan.entity = QueryEntity.REQUISITION
                plan.exact_req_no = None
                logger.info("ContextResolver: Resolved detail follow-up to previous filtered requisition list")
                return

    def _detect_pagination_phrase(self, q_lower: str, current_page: int) -> Optional[int]:
        if re.search(r"\b(prev(ious)?\s+(one|claim|requisition|item|record))\b", q_lower):
            return None
        if re.search(r"\b(next\s+page|show\s+next|next)\b", q_lower):
            return current_page + 1
        if re.search(r"\b(previous\s+page|prev\s+page|show\s+previous|previous|prev)\b", q_lower):
            return max(1, current_page - 1)
        m = re.search(r"\b(?:go\s+to\s+)?page\s+(\d+)\b", q_lower)
        if m:
            return int(m.group(1))
        return None
