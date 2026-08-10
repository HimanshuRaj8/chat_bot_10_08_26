"""
Backend V2 — QueryPlanner

The ONLY component that reads natural language.
Converts a user question into a precise, deterministic QueryPlan.
NEVER calls the LLM. NEVER accesses data.

Pipeline:
  1. Detect PROFILE intent → early return
  2. Detect subject scope ("my" / named employee / all)
  3. Detect exact requisition number lookup
  4. Detect date range
  5. Detect status filter (ONLY when explicitly requested)
  6. Detect category/description keyword
  7. Detect intent + entity + metric + aggregation + grouping
  8. Set output type from result shape
"""
import re
import logging
from typing import Any, List, Optional

from models.query import (
    QueryPlan, QueryIntent, SubjectScope, QueryEntity, QueryMetric,
    OutputType, DateRange,
)
from models.user import CurrentUser
from .date_parser import parse_date_phrase

logger = logging.getLogger(__name__)


class QueryPlanner:

    # ── Identity / Profile Patterns ───────────────────────────────────────────
    PROFILE_PATTERNS = [
        (r"\bwhat\s+is\s+my\s+(id|employee\s*id|emp\s*id)\b",                QueryMetric.EMPLOYEE_ID),
        (r"\bmy\s+(id|employee\s*id|emp\s*id)\b",                              QueryMetric.EMPLOYEE_ID),
        (r"\bwhat\s+is\s+my\s+name\b",                                         QueryMetric.NAME),
        (r"\bwho\s+am\s+i\b",                                                   QueryMetric.FULL_PROFILE),
        (r"\bmy\s+profile\b",                                                   QueryMetric.FULL_PROFILE),
        (r"\bmy\s+(role|position)\b",                                           QueryMetric.ROLE),
        (r"\bwhat\s+is\s+my\s+(role|position)\b",                              QueryMetric.ROLE),
        (r"\b(what|which)\s+department\s+(am\s+i|i\s+am)\s*(in|part\s+of)?\b", QueryMetric.DEPARTMENT),
        (r"\bwhat\s+is\s+my\s+department\b",                                    QueryMetric.DEPARTMENT),
        (r"\bmy\s+department\b",                                                 QueryMetric.DEPARTMENT),
        (r"\b(what|which)\s+location\s+(am\s+i|i\s+am)\s*(in|at|located)?\b",  QueryMetric.LOCATION),
        (r"\bwhat\s+is\s+my\s+location\b",                                      QueryMetric.LOCATION),
        (r"\bmy\s+location\b",                                                   QueryMetric.LOCATION),
        (r"\bwhat\s+is\s+my\s+(email|mail)\b",                                 QueryMetric.EMAIL),
        (r"\bmy\s+(email|mail)\b",                                              QueryMetric.EMAIL),
        (r"\bmy\s+account\s+info(rmation)?\b",                                  QueryMetric.FULL_PROFILE),
    ]

    # ── Status Normalizer ─────────────────────────────────────────────────────
    STATUS_MAP = {
        "approved":     ["approved", "approve", "accepted"],
        "pending":      ["pending", "open", "waiting", "awaiting", "not approved", "unapproved"],
        "rejected":     ["rejected", "declined", "denied"],
        "cancelled":    ["cancelled", "canceled", "withdrawn"],
    }

    # ── Entity + Aggregation Signal Keywords (Word-Boundary Enforced) ───────
    RANKING_SIGNALS    = [
        "highest", "largest", "top", "maximum", "max",
        "lowest", "smallest", "minimum", "min", "least",
        "most expensive", "least expensive", "best", "worst"
    ]
    AGGREGATE_SIGNALS  = ["total", "sum", "overall", "cumulative", "aggregate"]
    COUNT_SIGNALS      = ["how many", "count", "number of", "total number"]
    AVERAGE_SIGNALS    = ["average", "mean", "avg", "typical"]
    TREND_SIGNALS      = [
        "month-wise", "monthly", "month by month", "over time",
        "quarter-wise", "quarterly", "year-wise", "yearly", "trend"
    ]
    SUMMARY_SIGNALS    = ["summary", "overview", "breakdown", "department-wise", "employee-wise"]
    LIST_SIGNALS       = ["show", "list", "display", "give me", "fetch", "what are", "get", "see", "view"]

    def _has_word_signal(self, text: str, signals: List[str]) -> bool:
        """Helper to match signal keywords strictly against word boundaries."""
        for sig in signals:
            pattern = rf"\b{re.escape(sig)}\b"
            if re.search(pattern, text):
                return True
        return False

    def _is_recency_query(self, q_lower: str) -> bool:
        """Detects queries specifically asking for the last / latest / most recent requisition."""
        # Exclude date-range phrases like 'last month', 'last quarter', 'last year', 'last week'
        if re.search(r"\blast\s+(month|quarter|year|week|30\s+days|60\s+days|90\s+days)\b", q_lower):
            return False

        recency_patterns = [
            r"\b(my\s+)?last\s+(requisition|claim|pr|wo|request|submission)\b",
            r"\blatest\s+(requisition|claim|pr|wo|request|submission)\b",
            r"\bmost\s+recent\b",
            r"\brecent\s+(requisition|claim|pr|wo|request|submission|one)\b",
            r"\bnewest\s+(requisition|claim|pr|wo|request|submission|one)\b",
            r"\b(show\s+)?(only\s+)?the\s+(recent|latest|last)\s+one\b",
            r"\b(only|just)\s+(the\s+)?(recent|latest|last)\s+one\b",
            r"\bnot\s+all.*(recent|latest|last)\b",
            r"\bwhich\s+one\s+is\s+(the\s+)?(latest|most\s+recent|last)\b",
            r"\blast\s+requisition\s+status\b",
            r"\blatest\s+requisition\s+status\b",
            r"\bstatus\s+of\s+(my\s+)?(last|latest|most\s+recent)\b",
        ]
        for p in recency_patterns:
            if re.search(p, q_lower):
                return True
        return False

    def plan(
        self,
        question: str,
        user: CurrentUser,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        previous_plan: Optional[QueryPlan] = None,
        previous_context: Optional[Any] = None,
    ) -> QueryPlan:
        """
        Main entry point. Converts NL question into a QueryPlan.
        Supports explicit page/page_size parameters and natural language follow-ups.
        """
        import config
        q = question.strip()
        q_lower = q.lower()
        logger.info(f"Planning query: '{q}' [user={user.employee_id}, role={user.role.value}, page={page}, page_size={page_size}]")

        # ── Follow-Up Pagination Check ───────────────────────────────────────
        effective_prev_plan = previous_plan
        if previous_context and previous_context.last_plan:
            effective_prev_plan = previous_context.last_plan

        if effective_prev_plan and effective_prev_plan.intent != QueryIntent.PROFILE:
            target_page = self._detect_pagination_followup(q_lower, effective_prev_plan.page)
            if target_page is not None:
                req_page_size = page_size if page_size is not None else effective_prev_plan.page_size
                req_page_size = min(config.MAX_PAGE_SIZE, max(1, req_page_size))
                new_plan = QueryPlan(
                    intent=effective_prev_plan.intent,
                    entity=effective_prev_plan.entity,
                    metric=effective_prev_plan.metric,
                    aggregation=effective_prev_plan.aggregation,
                    group_by=effective_prev_plan.group_by,
                    filters=dict(effective_prev_plan.filters),
                    date_range=effective_prev_plan.date_range,
                    subject_scope=effective_prev_plan.subject_scope,
                    target_employee_id=effective_prev_plan.target_employee_id,
                    sort_order=effective_prev_plan.sort_order,
                    limit=effective_prev_plan.limit,
                    page=max(1, target_page),
                    page_size=req_page_size,
                    output_type=effective_prev_plan.output_type,
                    exact_req_no=effective_prev_plan.exact_req_no,
                    profile_metric=effective_prev_plan.profile_metric,
                    is_follow_up=True,
                    original_question=q,
                )
                logger.info(f"→ Pagination follow-up plan: page={new_plan.page}, page_size={new_plan.page_size}")
                return new_plan

        plan = QueryPlan(original_question=q)

        # Normalize page & page_size
        req_page = page if page is not None else 1
        req_page_size = page_size if page_size is not None else config.DEFAULT_PAGE_SIZE
        plan.page = max(1, req_page)
        plan.page_size = min(config.MAX_PAGE_SIZE, max(1, req_page_size))

        # ── Step 0: Conversational Follow-Up Resolution ──────────────────────
        if previous_context or effective_prev_plan:
            prev_scope = previous_context.last_subject_scope if previous_context else (effective_prev_plan.subject_scope if effective_prev_plan else None)
            prev_target_id = previous_context.last_target_employee_id if previous_context else (effective_prev_plan.target_employee_id if effective_prev_plan else None)
            prev_filters = dict(previous_context.last_filters if previous_context and previous_context.last_filters else (effective_prev_plan.filters if effective_prev_plan else {}))

            is_single_ref = bool(re.search(r"\b(it|this one|that one)\b", q_lower)) and not re.search(r"\b(these|those|them|their)\b", q_lower)

            if previous_context and is_single_ref and previous_context.latest_selection_single:
                target_ids = [previous_context.latest_selection_single]
            elif previous_context and previous_context.full_requisition_ids:
                target_ids = list(previous_context.full_requisition_ids)
            elif previous_context and previous_context.last_requisition_ids:
                target_ids = list(previous_context.last_requisition_ids)
            else:
                target_ids = []

            if self._detect_followup_reference(q_lower) and (prev_scope is not None or target_ids):
                plan.is_follow_up = True
                plan.subject_scope = prev_scope or SubjectScope.CURRENT_USER
                plan.target_employee_id = prev_target_id or (user.employee_id if plan.subject_scope == SubjectScope.CURRENT_USER else None)
                plan.filters = prev_filters

                if target_ids:
                    plan.filters["requisition_id_list"] = target_ids

                # ── NEW ANALYTICAL INTENT FOR FOLLOW-UP ──
                # 1. Recency / Latest follow-up
                if self._is_recency_query(q_lower) or any(w in q_lower for w in ["latest", "recent", "last one", "recent one"]):
                    plan.intent = QueryIntent.RANKING
                    plan.entity = QueryEntity.REQUISITION
                    plan.metric = "Created On"
                    plan.sort_order = "desc"
                    plan.aggregation = "LATEST"
                    plan.limit = 1
                    plan.output_type = OutputType.NATURAL_TEXT
                    if "status" in q_lower:
                        plan.filters["requested_field"] = "status"
                    logger.info(f"→ Follow-up LATEST/RECENCY resolved: target_reqs={len(target_ids)}")
                    return plan

                # 2. Approver Analysis
                if any(w in q_lower for w in ["who approved", "who gave", "approver", "final approval"]):
                    plan.intent = QueryIntent.APPROVER_ANALYSIS
                    plan.entity = QueryEntity.REQUISITION
                    plan.output_type = OutputType.NATURAL_TEXT
                    logger.info(f"→ Follow-up APPROVER_ANALYSIS resolved: target_reqs={len(target_ids)}")
                    return plan

                # 3. Date Analysis
                if any(w in q_lower for w in ["when were", "when was it", "approval date", "approved on", "created on"]):
                    plan.intent = QueryIntent.DATE_ANALYSIS
                    plan.entity = QueryEntity.REQUISITION
                    plan.output_type = OutputType.NATURAL_TEXT
                    logger.info(f"→ Follow-up DATE_ANALYSIS resolved: target_reqs={len(target_ids)}")
                    return plan

                # 4. Comparison (Requested vs Approved)
                if any(w in q_lower for w in ["requested vs approved", "requested versus approved", "compare requested", "difference"]):
                    plan.intent = QueryIntent.COMPARISON
                    plan.entity = QueryEntity.REQUISITION
                    plan.output_type = OutputType.NATURAL_TEXT
                    logger.info(f"→ Follow-up COMPARISON resolved: target_reqs={len(target_ids)}")
                    return plan

                # 5. SUM / Total
                if any(w in q_lower for w in ["total approved", "total requested", "what is the total", "how much was approved", "total amount"]):
                    plan.intent = QueryIntent.AGGREGATE
                    plan.aggregation = "SUM"
                    plan.entity = QueryEntity.REQUISITION
                    plan.metric = "Value in INR" if "requested" in q_lower else "Approved Value in INR"
                    plan.output_type = OutputType.SINGLE_METRIC
                    logger.info(f"→ Follow-up SUM AGGREGATE resolved: target_reqs={len(target_ids)}")
                    return plan

                # 6. AVG / Average
                if any(w in q_lower for w in ["average", "avg"]):
                    plan.intent = QueryIntent.AGGREGATE
                    plan.aggregation = "AVG"
                    plan.entity = QueryEntity.REQUISITION
                    plan.metric = "Approved Value in INR"
                    plan.output_type = OutputType.SINGLE_METRIC
                    logger.info(f"→ Follow-up AVG AGGREGATE resolved: target_reqs={len(target_ids)}")
                    return plan

                # 7. COUNT / Status Analysis
                if any(w in q_lower for w in ["how many", "count"]):
                    plan.intent = QueryIntent.COUNT
                    plan.aggregation = "COUNT"
                    plan.entity = QueryEntity.REQUISITION
                    plan.output_type = OutputType.SINGLE_METRIC
                    status = self._detect_status(q_lower)
                    if status:
                        plan.filters["status"] = status
                    logger.info(f"→ Follow-up COUNT resolved: target_reqs={len(target_ids)}, status={status}")
                    return plan

                # 8. MAX / Highest
                if any(w in q_lower for w in ["highest", "most expensive", "largest", "which one is highest", "which one has the highest"]):
                    plan.intent = QueryIntent.RANKING
                    plan.entity = QueryEntity.REQUISITION
                    plan.limit = 1
                    plan.sort_order = "desc"
                    plan.aggregation = "MAX"
                    plan.output_type = OutputType.NATURAL_TEXT
                    logger.info(f"→ Follow-up MAX RANKING resolved: target_reqs={len(target_ids)}")
                    return plan

                # 9. MIN / Lowest
                if any(w in q_lower for w in ["lowest", "smallest", "least expensive", "which one is lowest"]):
                    plan.intent = QueryIntent.RANKING
                    plan.entity = QueryEntity.REQUISITION
                    plan.limit = 1
                    plan.sort_order = "asc"
                    plan.aggregation = "MIN"
                    plan.output_type = OutputType.NATURAL_TEXT
                    logger.info(f"→ Follow-up MIN RANKING resolved: target_reqs={len(target_ids)}")
                    return plan

                # 10. Descriptions / Purpose / Detail Projection
                if any(w in q_lower for w in [
                    "description", "descriptions", "details", "detail",
                    "what were these for", "made for", "purpose", "for what",
                    "why were these", "what did i request", "how much were these"
                ]):
                    plan.intent = QueryIntent.FILTER
                    plan.entity = QueryEntity.REQUISITION
                    plan.output_type = OutputType.NATURAL_TEXT
                    plan.filters["projection"] = "description"
                    logger.info(f"→ Follow-up DETAIL/PURPOSE resolved: target_reqs={len(target_ids)}")
                    return plan

        # ── Step 1: PROFILE intent ────────────────────────────────────────────
        profile_metric = self._detect_profile_intent(q_lower)
        if profile_metric:
            plan.intent = QueryIntent.PROFILE
            plan.subject_scope = SubjectScope.CURRENT_USER
            plan.profile_metric = profile_metric
            plan.output_type = OutputType.NATURAL_TEXT
            logger.info(f"→ PROFILE intent detected: {profile_metric}")
            return plan

        # ── Step 2: Subject scope ─────────────────────────────────────────────
        scope, target_id, target_name = self._detect_scope(q_lower, user)
        plan.subject_scope = scope
        plan.target_employee_id = target_id

        # ── Step 3: Recency / Latest Query Check ──────────────────────────────
        if self._is_recency_query(q_lower):
            plan.intent = QueryIntent.RANKING
            plan.entity = QueryEntity.REQUISITION
            plan.metric = "Created On"
            plan.sort_order = "desc"
            plan.aggregation = "LATEST"
            plan.limit = 1
            plan.output_type = OutputType.NATURAL_TEXT
            if "status" in q_lower:
                plan.filters["requested_field"] = "status"
            logger.info(f"→ Direct RECENCY intent: scope={scope.value}, limit=1, sort=Created On DESC")
            return plan

        # ── Step 4: Exact requisition lookup ─────────────────────────────────
        req_no = self._detect_exact_req_no(q)
        if req_no:
            plan.intent = QueryIntent.LOOKUP
            plan.exact_req_no = req_no
            plan.output_type = OutputType.SHORT_SUMMARY
            logger.info(f"→ LOOKUP intent: req_no={req_no}")
            return plan

        # ── Step 5: Date range ────────────────────────────────────────────────
        start, end, date_label = parse_date_phrase(q)
        plan.date_range = DateRange(label=date_label, start=start, end=end)

        # ── Step 6: Status filter ─────────────────────────────────────────────
        status = self._detect_status(q_lower)
        if status:
            plan.filters["status"] = status

        # ── Step 7: Category/keyword filter ──────────────────────────────────
        keyword = self._detect_description_keyword(q_lower)
        if keyword:
            plan.filters["description_keyword"] = keyword

        # ── Step 8: Intent + Entity + Aggregation ────────────────────────────
        self._detect_intent_entity_aggregation(q_lower, plan, user)

        # ── Step 9: Output type ───────────────────────────────────────────────
        plan.output_type = self._determine_output_type(plan)

        logger.info(
            f"→ Plan: intent={plan.intent.value}, entity={plan.entity.value}, "
            f"metric={plan.metric}, agg={plan.aggregation}, scope={plan.subject_scope.value}, "
            f"group_by={plan.group_by}, page={plan.page}, page_size={plan.page_size}, filters={plan.filters}"
        )
        return plan

    def _detect_followup_reference(self, q_lower: str) -> bool:
        followup_keywords = [
            r"\bits\b", r"\btheir\b", r"\bthem\b", r"\bthose\b", r"\bthese\b",
            r"\bthese claims\b", r"\bthose claims\b",
            r"\bthese requisitions\b", r"\bthose requisitions\b",
            r"\bthese requests\b", r"\bthose requests\b",
            r"\bthe above\b", r"\bsame\b", r"\balso\b", r"\band also\b",
            r"\bwhat about\b", r"\bwhen was it\b", r"\bwhen were\b", r"\btell me more\b",
            r"\bshow details\b", r"\bdescriptions?\b", r"\bdetails?\b",
            r"\bwhich one\b", r"\bapproval date\b", r"\bstatus\b", r"\brequested value\b",
            r"\bwho approved\b", r"\bwho gave\b", r"\bapprover\b", r"\bhow many\b",
            r"\btotal\b", r"\baverage\b", r"\bavg\b", r"\bcompare\b", r"\bversus\b", r"\bvs\b",
            r"\bmade for\b", r"\bpurpose\b", r"\bfor what\b", r"\bwhy were\b",
            r"\bthey\b", r"\bthe listed ones\b", r"\bthese records\b", r"\bthe results\b",
            r"\bone\b", r"\bthe recent one\b", r"\bthe latest one\b", r"\bthe last one\b"
        ]
        for kw in followup_keywords:
            if re.search(kw, q_lower):
                return True
        return False

    def _detect_pagination_followup(self, q_lower: str, current_page: int) -> Optional[int]:
        """Detects pagination follow-up commands like 'next page', 'previous page', 'page 3'."""
        if re.search(r"\b(next\s+page|show\s+next|next)\b", q_lower):
            return current_page + 1
        if re.search(r"\b(previous\s+page|prev\s+page|show\s+previous|previous|prev)\b", q_lower):
            return max(1, current_page - 1)
        m = re.search(r"\b(go\s+to\s+)?page\s+(\d+)\b", q_lower)
        if m:
            return int(m.group(2))
        return None

    # ── Step 1: Profile Detection ─────────────────────────────────────────────

    def _detect_profile_intent(self, q_lower: str) -> Optional[str]:
        for pattern, metric in self.PROFILE_PATTERNS:
            if re.search(pattern, q_lower):
                return metric
        return None

    # ── Step 2: Scope Detection ───────────────────────────────────────────────

    def _detect_scope(self, q_lower: str, user: CurrentUser):
        """
        Returns (SubjectScope, target_employee_id, target_name_hint).

        Rules:
          - Any "my"/"mine"/"I"/"me"/"for me"/"of mine" → CURRENT_USER (employee_id = user.employee_id)
          - Specific name pattern (Finance only) → SPECIFIC_EMPLOYEE
          - Explicit multi-employee or multi-department requests → ALL_EMPLOYEES
          - Role-based default: For non-Finance (Employee), default scope for requisitions is CURRENT_USER.
        """
        # 1. "my" / self-reference semantics — check first, highest priority
        # NOTE: \bme\b is intentionally excluded: "show me X" uses "me" as an
        # indirect object (dative), NOT as a possessive. Finance/Admin users saying
        # "show me requisitions related to driver salary" must get org-wide scope.
        # Personal intent is captured by \bmy\b, \bmine\b, \bfor me\b, and \bi\b.
        my_patterns = [r"\bmy\b", r"\bmine\b", r"\bof mine\b", r"\bfor me\b", r"\bmy own\b", r"\bi\b"]
        for p in my_patterns:
            if re.search(p, q_lower):
                return SubjectScope.CURRENT_USER, user.employee_id, None

        # 2. Named employee (Finance/Admin only resolution)
        if user.is_finance:
            target_id, target_name = self._detect_named_employee(q_lower)
            if target_id or target_name:
                return SubjectScope.SPECIFIC_EMPLOYEE, target_id, target_name

        # 3. Explicit organization-wide / multi-employee / multi-department signals
        explicit_org_signals = [
            "which employee", "who has", "top employee", "top department",
            "which department", "all employees", "everyone", "all departments",
            "department-wise", "organization-wide", "across company", "company-wide",
            "all employees'", "across the company", "across department", "who is the"
        ]
        for signal in explicit_org_signals:
            if signal in q_lower:
                return SubjectScope.ALL_EMPLOYEES, None, None

        # 4. Role-based implicit scope resolution:
        # If user is Employee (not Finance/Admin), requisition queries default to CURRENT_USER.
        if not user.is_finance:
            return SubjectScope.CURRENT_USER, user.employee_id, None

        # Default for Finance/Admin is ALL_EMPLOYEES
        return SubjectScope.ALL_EMPLOYEES, None, None

    def _detect_named_employee(self, q_lower: str):
        """
        Detects references to specific employees by name pattern.
        Example: "Rahul's requisitions" → ("", "Rahul")
        """
        possessive = re.search(
            r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?)'s?\s+\w+", 
            q_lower.title()
        )
        if possessive:
            return None, possessive.group(1)

        m = re.search(r"\b(?:for|by)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", q_lower.title())
        if m:
            return None, m.group(1)

        return None, None

    # ── Step 3: Exact Req No ─────────────────────────────────────────────────

    def _detect_exact_req_no(self, q: str) -> Optional[str]:
        patterns = [
            r"\b([A-Z]{2,4}-\d{4}-\d{3,6})\b",
            r"\b([A-Z]{2,4}-\d{4,10})\b",
            r"\b(REQ\d{4,10})\b",
            r"\b(WO\d{4,10})\b",
        ]
        for p in patterns:
            m = re.search(p, q.upper())
            if m:
                return m.group(1)
        return None

    # ── Step 5: Status ────────────────────────────────────────────────────────

    def _detect_status(self, q_lower: str) -> Optional[str]:
        """
        Detects explicit status filters.
        DO NOT match 'approved' when it is part of metric phrases like
        'approved reimbursement' or 'approved value'.
        """
        # Explicit status context patterns
        explicit_approved_patterns = [
            r"\bapproved\s+(requisitions?|claims?|records?|submissions?|docs?|documents?|status)\b",
            r"\bstatus\s*(is|=|:)?\s*approved\b",
            r"\bshow\s+.*approved\b",
            r"\blist\s+.*approved\b",
            r"\bhow\s+many\s+.*approved\b",
            r"\bare\s+approved\b",
        ]

        for p in explicit_approved_patterns:
            if re.search(p, q_lower):
                return "approved"

        # Check other status keywords (pending, rejected, cancelled)
        for canonical, keywords in self.STATUS_MAP.items():
            if canonical == "approved":
                continue
            for kw in keywords:
                if re.search(rf"\b{kw}\b", q_lower):
                    return canonical

        return None

    # ── Step 6: Category Keyword ──────────────────────────────────────────────

    def _detect_description_keyword(self, q_lower: str) -> Optional[str]:
        categories = [
            "travel", "hotel", "flight", "accommodation", "transport",
            "software", "hardware", "laptop", "computer", "equipment",
            "training", "course", "certification",
            "office", "stationery", "supplies",
            "medical", "health",
            "fuel", "vehicle", "car",
            "repair", "maintenance", "service",
            "subscription", "license",
            "driver", "salary", "wages", "food", "catering", "uniform",
            "printing", "courier", "logistics", "electricity", "rent",
            "security", "cleaning", "insurance", "telephone", "internet",
        ]
        for cat in categories:
            if cat in q_lower:
                return cat

        # Free-form keyword extraction from relational phrases
        # Captures: "related to driver salary", "for driver salary", "about travel", "regarding rent"
        phrase_patterns = [
            r"\brelated\s+to\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
            r"\babout\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
            r"\bregarding\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
            r"\bfor\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
        ]
        # Noise words to strip from extracted keywords
        noise = {"the", "a", "an", "all", "any", "some", "my", "our", "their"}
        for p in phrase_patterns:
            m = re.search(p, q_lower)
            if m:
                raw = m.group(1).strip()
                # Remove noise words
                tokens = [t for t in raw.split() if t not in noise]
                if tokens:
                    return " ".join(tokens)

        return None

    # ── Step 7: Intent + Entity + Aggregation ────────────────────────────────

    def _detect_intent_entity_aggregation(
        self, q_lower: str, plan: QueryPlan, user: CurrentUser
    ) -> None:
        has_ranking  = self._has_word_signal(q_lower, self.RANKING_SIGNALS)
        has_total    = self._has_word_signal(q_lower, self.AGGREGATE_SIGNALS)
        has_count    = self._has_word_signal(q_lower, self.COUNT_SIGNALS)
        has_average  = self._has_word_signal(q_lower, self.AVERAGE_SIGNALS)
        has_trend    = self._has_word_signal(q_lower, self.TREND_SIGNALS)
        has_summary  = self._has_word_signal(q_lower, self.SUMMARY_SIGNALS)
        has_list     = self._has_word_signal(q_lower, self.LIST_SIGNALS)

        # Detect limit
        limit_match = re.search(r"\btop\s+(\d+)\b", q_lower)
        if limit_match:
            plan.limit = int(limit_match.group(1))
        elif has_ranking and not plan.limit:
            plan.limit = 1

        # Detect order
        ascending_signals  = ["lowest", "smallest", "minimum", "min", "least", "worst"]
        if self._has_word_signal(q_lower, ascending_signals):
            plan.sort_order = "asc"
        else:
            plan.sort_order = "desc"

        # Detect metric
        if any(kw in q_lower for kw in [
            "approved value", "approved amount", "approved reimbursement",
            "reimbursement", "disbursed", "paid"
        ]):
            plan.metric = "Approved Value in INR"
        elif any(kw in q_lower for kw in [
            "requested value", "requested amount", "requested"
        ]):
            plan.metric = "Value in INR"
        else:
            plan.metric = "Approved Value in INR"

        # Entity detection & grouping
        if any(kw in q_lower for kw in ["department", "dept"]):
            plan.entity = QueryEntity.DEPARTMENT
            plan.group_by = "Department"

        elif any(kw in q_lower for kw in [
            "employee", "person", "who", "staff", "member",
            "rahul", "prashant", "intern", "him", "her"
        ]):
            plan.entity = QueryEntity.EMPLOYEE
            plan.group_by = "employee_name"

        elif any(kw in q_lower for kw in ["cost centre", "cost center", "cc"]):
            plan.entity = QueryEntity.COST_CENTRE
            plan.group_by = "Cost Centre"

        elif any(kw in q_lower for kw in ["operational unit", "ou", "unit"]):
            plan.entity = QueryEntity.OPERATIONAL_UNIT
            plan.group_by = "Operational Unit Name"

        elif any(kw in q_lower for kw in ["month", "monthly", "month-wise"]):
            plan.entity = QueryEntity.MONTH
            plan.group_by = "month_period"

        elif any(kw in q_lower for kw in ["quarter", "quarterly", "quarter-wise"]):
            plan.entity = QueryEntity.QUARTER
            plan.group_by = "quarter_period"

        elif any(kw in q_lower for kw in ["requisition", "claim", "pr", "wo"]):
            plan.entity = QueryEntity.REQUISITION
            plan.group_by = None

        else:
            plan.entity = QueryEntity.REQUISITION
            plan.group_by = None

        # Intent assignment with strict operational precedence
        if has_trend or plan.group_by in ("month_period", "quarter_period"):
            plan.intent = QueryIntent.TREND
            plan.aggregation = "SUM"

        elif has_ranking:
            if plan.group_by:
                plan.intent = QueryIntent.RANKING
                plan.aggregation = "SUM"
            else:
                plan.intent = QueryIntent.RANKING
                plan.aggregation = "MAX" if plan.limit == 1 else "SUM"

        elif has_average:
            plan.intent = QueryIntent.AGGREGATE
            plan.aggregation = "AVG"

        elif has_total:
            plan.intent = QueryIntent.AGGREGATE
            plan.aggregation = "SUM"

        elif has_count:
            plan.intent = QueryIntent.COUNT
            plan.aggregation = "COUNT"
            plan.metric = "count"

        elif has_summary and plan.group_by:
            plan.intent = QueryIntent.SUMMARY
            plan.aggregation = "SUM"

        else:
            plan.intent = QueryIntent.FILTER
            plan.aggregation = "NONE"
            if not plan.limit:
                plan.limit = 20

    # ── Step 8: Output Type ───────────────────────────────────────────────────

    def _determine_output_type(self, plan: QueryPlan) -> OutputType:
        if plan.intent == QueryIntent.PROFILE:
            return OutputType.NATURAL_TEXT
        if plan.intent == QueryIntent.LOOKUP:
            return OutputType.SHORT_SUMMARY
        if plan.intent in (QueryIntent.AGGREGATE, QueryIntent.COUNT):
            if not plan.group_by:
                return OutputType.SINGLE_METRIC
            return OutputType.TABLE
        if plan.intent == QueryIntent.RANKING and plan.limit == 1:
            return OutputType.NATURAL_TEXT
        if plan.intent in (QueryIntent.RANKING, QueryIntent.TREND, QueryIntent.SUMMARY, QueryIntent.COMPARISON):
            return OutputType.TABLE
        if plan.intent == QueryIntent.FILTER:
            if plan.is_follow_up and plan.filters.get("projection") == "description":
                return OutputType.NATURAL_TEXT
            return OutputType.TABLE
        return OutputType.NATURAL_TEXT
