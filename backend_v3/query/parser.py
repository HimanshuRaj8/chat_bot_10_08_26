"""
Backend V3 — Query Parser (Hybrid LLM + Deterministic Fallback)
"""
import re
import json
import logging
from typing import Any, Dict, Optional, Tuple

from models.query import QueryPlan, QueryIntent, SubjectScope, QueryEntity, QueryMetric, OutputType, DateRange
from models.user import CurrentUser
from llm.client import LLMClient
from .date_parser import parse_date_phrase

logger = logging.getLogger(__name__)


class QueryParser:

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

    STATUS_MAP = {
        "approved":  ["approved", "approve", "accepted"],
        "pending":   ["pending", "open", "waiting", "awaiting", "not approved", "unapproved"],
        "rejected":  ["rejected", "declined", "denied"],
        "cancelled": ["cancelled", "canceled", "withdrawn"],
    }

    OUT_OF_SCOPE_WORDS = [
        "joke", "weather", "cook", "recipe", "pasta", "pizza", "funny", "story",
        "movie", "song", "play", "write code", "hello world", "temperature"
    ]

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def parse_query(self, question: str, user: CurrentUser, page: int = 1, page_size: int = 20) -> QueryPlan:
        """
        Main entry point. Translates natural language question into QueryPlan.
        Attempts LLM query plan generation first, falling back to deterministic regex parser if offline or fails.
        """
        q_clean = question.strip()
        q_lower = q_clean.lower()
        logger.info(f"V3 parsing query: '{q_clean}' [user={user.employee_id}, role={user.role.value}]")

        # Early out-of-scope check
        if any(w in q_lower for w in self.OUT_OF_SCOPE_WORDS) and not any(r in q_lower for r in ["requisition", "claim", "approve", "status"]):
            logger.info("Deterministic OUT_OF_SCOPE detected.")
            return QueryPlan(intent=QueryIntent.OUT_OF_SCOPE, original_question=q_clean)

        # Early PROFILE intent check
        profile_metric = self._detect_profile_intent(q_lower)
        if profile_metric:
            logger.info(f"Deterministic PROFILE detected: {profile_metric}")
            return QueryPlan(
                intent=QueryIntent.PROFILE,
                subject_scope=SubjectScope.CURRENT_USER,
                profile_metric=profile_metric,
                output_type=OutputType.NATURAL_TEXT,
                original_question=q_clean,
            )

        # Try LLM Parser
        if self.llm and self.llm.is_available():
            try:
                plan = self._parse_with_llm(q_clean, user, page, page_size)
                if plan:
                    # Sync page properties
                    plan.page = page
                    plan.page_size = page_size
                    plan.original_question = q_clean
                    self._normalize_employee_reference(plan, q_lower)
                    self._apply_scope_from_question(plan, q_lower, user)
                    self._normalize_detail_plan(plan, q_lower)
                    self._normalize_ranking_plan(plan, q_lower)
                    return plan
            except Exception as e:
                logger.warning(f"LLM query parser failed, falling back to deterministic: {e}")

        # Fallback to Deterministic Regex-based Parser
        plan = self._parse_deterministically(q_clean, user, page, page_size)
        self._normalize_employee_reference(plan, q_lower)
        self._apply_scope_from_question(plan, q_lower, user)
        self._normalize_detail_plan(plan, q_lower)
        self._normalize_ranking_plan(plan, q_lower)
        return plan

    # ── LLM Parser ────────────────────────────────────────────────────────────

    def _parse_with_llm(self, question: str, user: CurrentUser, page: int, page_size: int) -> Optional[QueryPlan]:
        system_instruction = """You are a precise Query Plan parser. Output a single JSON object (no backticks, no extra text) mapping the user's request to this schema:
{
  "intent": "PROFILE" | "LIST_REQUISITIONS" | "GET_REQUISITION" | "GET_LATEST_REQUISITION" | "GET_PREVIOUS_REQUISITION" | "ANALYTICS" | "OUT_OF_SCOPE",
  "entity": "Requisition" | "Employee" | "Department" | "CostCentre" | "OperationalUnit" | "Month" | "Quarter" | "Status",
  "metric": "approved_value_inr" | "value_inr" | "count" | "average_approved_value_inr" | null,
  "aggregation": "SUM" | "COUNT" | "AVG" | "MAX" | "MIN" | null,
  "group_by": "Department" | "employee_name" | "Cost Centre" | "Operational Unit Name" | "month_period" | "quarter_period" | null,
  "filters": {
     "status": "approved" | "pending" | "rejected" | "cancelled" | null,
     "description_keyword": string | null
  },
  "target_employee_name": string | null,
  "target_employee_id": string | null,
  "exact_req_no": string | null,
  "sort_field": string,
  "sort_direction": "desc" | "asc"
}

CRITICAL RULES — read carefully:
1. PROFILE intent is ONLY for user identity questions: "who am I", "what is my name", "my employee ID", "my department", "my email", "my role". NEVER use PROFILE for financial queries.
2. "total approved value", "sum of approved", "approved amount", "total reimbursement" -> intent="ANALYTICS", aggregation="SUM", metric="approved_value_inr".
3. "how many requisitions" -> intent="ANALYTICS", aggregation="COUNT".
4. "average approved value" -> intent="ANALYTICS", aggregation="AVG".
5. "April month requisition" -> intent="ANALYTICS", entity="Month", group_by="month_period".
6. "show me April requisitions" -> intent="LIST_REQUISITIONS", group_by=null.
7. Exact requisition lookup -> intent="GET_REQUISITION", exact_req_no="G_XXX...".
8. Never set "subject_scope" — authorization is handled separately.
"""
        try:
            resp_text = self.llm.generate(question, system=system_instruction, format_json=True)
            data = json.loads(resp_text)
            
            # Map strings to Enums
            intent_map = {
                "PROFILE": QueryIntent.PROFILE,
                "LIST_REQUISITIONS": QueryIntent.LIST_REQUISITIONS,
                "GET_REQUISITION": QueryIntent.GET_REQUISITION,
                "GET_LATEST_REQUISITION": QueryIntent.GET_LATEST_REQUISITION,
                "GET_PREVIOUS_REQUISITION": QueryIntent.GET_PREVIOUS_REQUISITION,
                "ANALYTICS": QueryIntent.ANALYTICS,
                "OUT_OF_SCOPE": QueryIntent.OUT_OF_SCOPE,
            }
            entity_map = {
                "Requisition": QueryEntity.REQUISITION,
                "Employee": QueryEntity.EMPLOYEE,
                "Department": QueryEntity.DEPARTMENT,
                "CostCentre": QueryEntity.COST_CENTRE,
                "OperationalUnit": QueryEntity.OPERATIONAL_UNIT,
                "Month": QueryEntity.MONTH,
                "Quarter": QueryEntity.QUARTER,
                "Status": QueryEntity.STATUS,
            }

            intent = intent_map.get(data.get("intent", ""), QueryIntent.LIST_REQUISITIONS)
            entity = entity_map.get(data.get("entity", ""), QueryEntity.REQUISITION)

            plan = QueryPlan(
                intent=intent,
                entity=entity,
                metric=data.get("metric"),
                aggregation=data.get("aggregation"),
                group_by=data.get("group_by"),
                target_employee_name=data.get("target_employee_name"),
                target_employee_id=data.get("target_employee_id"),
                exact_req_no=data.get("exact_req_no"),
                sort_field=data.get("sort_field", "Created On"),
                sort_direction=data.get("sort_direction", "desc"),
            )

            # Map filters
            raw_filters = data.get("filters", {})
            if isinstance(raw_filters, dict):
                for k, v in raw_filters.items():
                    if v:
                        plan.filters[k] = v

            # Parse date phrase
            start, end, date_label = parse_date_phrase(question)
            if start or end:
                plan.date_range = DateRange(label=date_label, start=start, end=end)

            self._apply_scope_from_question(plan, question.lower(), user)

            logger.info(f"LLM parsed query plan: {plan}")
            return plan
        except Exception as e:
            logger.error(f"Error parsing LLM response JSON: {e}")
            return None

    # ── Deterministic Parser ──────────────────────────────────────────────────

    def _parse_deterministically(self, question: str, user: CurrentUser, page: int, page_size: int) -> QueryPlan:
        q_lower = question.lower()
        plan = QueryPlan(original_question=question, page=page, page_size=page_size)

        # 1. Scope / Employee Identification
        if user.is_finance:
            plan.subject_scope = SubjectScope.ALL_EMPLOYEES
            target_id, target_name = self._detect_named_employee(q_lower)
            if target_id or target_name:
                plan.subject_scope = SubjectScope.SPECIFIC_EMPLOYEE
                plan.target_employee_id = target_id
                plan.target_employee_name = target_name
        else:
            plan.subject_scope = SubjectScope.CURRENT_USER
            plan.target_employee_id = user.employee_id
            plan.target_employee_name = user.employee_name

        # 2. Date parsing
        start, end, date_label = parse_date_phrase(question)
        plan.date_range = DateRange(label=date_label, start=start, end=end)

        # 3. Status parsing
        status = self._detect_status(q_lower)
        if status:
            plan.filters["status"] = status

        # 4. Keyword parsing
        keyword = self._detect_description_keyword(q_lower)
        if keyword:
            plan.filters["description_keyword"] = keyword

        # 5. Exact Requisition lookup
        req_no = self._detect_exact_req_no(question)
        if req_no:
            plan.intent = QueryIntent.GET_REQUISITION
            plan.exact_req_no = req_no
            plan.output_type = OutputType.TABLE
            return plan

        # 6. Recency / Latest intent checks
        if self._is_recency_query(q_lower):
            plan.intent = QueryIntent.GET_LATEST_REQUISITION
            plan.entity = QueryEntity.REQUISITION
            plan.sort_field = "Created On"
            plan.sort_direction = "desc"
            plan.limit = 1
            plan.output_type = OutputType.NATURAL_TEXT
            if "status" in q_lower:
                plan.filters["requested_field"] = "status"
            return plan

        # 7. Check trend, aggregates and ranking signals
        has_ranking = self._has_word_signal(q_lower, ["highest", "largest", "top", "max", "maximum", "lowest", "smallest", "min", "minimum", "least"])
        has_total = self._has_word_signal(q_lower, ["total", "sum", "overall", "cumulative", "aggregate"])
        has_count = self._has_word_signal(q_lower, ["how many", "count", "number of", "total number"])
        has_average = self._has_word_signal(q_lower, ["average", "mean", "avg"])
        has_trend = self._has_word_signal(q_lower, ["month-wise", "monthly", "month by month", "quarter-wise", "quarterly", "trend", "month"])
        has_summary = self._has_word_signal(q_lower, ["summary", "overview", "breakdown", "department-wise", "employee-wise"])

        # Determine metric
        if any(w in q_lower for w in ["approved value", "approved amount", "approved reimbursement", "reimbursement", "paid"]):
            plan.metric = "Approved Value in INR"
        elif any(w in q_lower for w in ["requested value", "requested amount", "value"]):
            plan.metric = "Value in INR"

        # Determine Entity & Grouping
        if any(w in q_lower for w in ["department", "dept"]):
            plan.entity = QueryEntity.DEPARTMENT
            plan.group_by = "Department"
        elif any(w in q_lower for w in ["employee", "person", "who", "staff", "member"]):
            plan.entity = QueryEntity.EMPLOYEE
            plan.group_by = "employee_name"
        elif any(w in q_lower for w in ["month", "monthly", "month-wise"]):
            plan.entity = QueryEntity.MONTH
            plan.group_by = "month_period"
        elif any(w in q_lower for w in ["quarter", "quarterly"]):
            plan.entity = QueryEntity.QUARTER
            plan.group_by = "quarter_period"
        else:
            plan.entity = QueryEntity.REQUISITION
            plan.group_by = None

        # Sort order
        if self._has_word_signal(q_lower, ["lowest", "smallest", "minimum", "min", "least"]):
            plan.sort_direction = "asc"
        else:
            plan.sort_direction = "desc"

        # Limit
        limit_match = re.search(r"\btop\s+(\d+)\b", q_lower)
        if limit_match:
            plan.limit = int(limit_match.group(1))
        elif has_ranking:
            plan.limit = 1

        # Map Intents
        if has_trend or plan.group_by in ("month_period", "quarter_period"):
            plan.intent = QueryIntent.ANALYTICS
            plan.aggregation = "SUM"
        elif has_ranking:
            plan.intent = QueryIntent.ANALYTICS
            plan.aggregation = "SUM" if plan.group_by else "MAX"
        elif has_average:
            plan.intent = QueryIntent.ANALYTICS
            plan.aggregation = "AVG"
            plan.output_type = OutputType.SINGLE_METRIC if not plan.group_by else OutputType.TABLE
        elif has_total:
            plan.intent = QueryIntent.ANALYTICS
            plan.aggregation = "SUM"
            plan.output_type = OutputType.SINGLE_METRIC if not plan.group_by else OutputType.TABLE
        elif has_count:
            plan.intent = QueryIntent.ANALYTICS
            plan.aggregation = "COUNT"
            plan.metric = "count"
            plan.output_type = OutputType.SINGLE_METRIC if not plan.group_by else OutputType.TABLE
        elif has_summary and plan.group_by:
            plan.intent = QueryIntent.ANALYTICS
            plan.aggregation = "SUM"
        else:
            plan.intent = QueryIntent.LIST_REQUISITIONS
            plan.output_type = OutputType.TABLE
            if not plan.limit:
                plan.limit = 20

        return plan

    # ── Utility Helpers ───────────────────────────────────────────────────────

    def _detect_profile_intent(self, q_lower: str) -> Optional[str]:
        for pattern, metric in self.PROFILE_PATTERNS:
            if re.search(pattern, q_lower):
                return metric
        return None

    def _detect_status(self, q_lower: str) -> Optional[str]:
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

        for canonical, keywords in self.STATUS_MAP.items():
            if canonical == "approved":
                continue
            for kw in keywords:
                if re.search(rf"\b{kw}\b", q_lower):
                    return canonical
        return None

    def _apply_scope_from_question(self, plan: QueryPlan, q_lower: str, user: CurrentUser) -> None:
        """Determines whether the user asked for personal, specific-person, or organization data."""
        personal_scope = bool(re.search(r"\b(my|mine|own|self)\b", q_lower))

        if not user.is_finance:
            plan.subject_scope = SubjectScope.CURRENT_USER
            plan.target_employee_id = user.employee_id
            plan.target_employee_name = user.employee_name
            return

        if personal_scope:
            plan.subject_scope = SubjectScope.CURRENT_USER
            plan.target_employee_id = user.employee_id
            plan.target_employee_name = user.employee_name
        elif plan.target_employee_name or plan.target_employee_id:
            plan.subject_scope = SubjectScope.SPECIFIC_EMPLOYEE
        else:
            plan.subject_scope = SubjectScope.ALL_EMPLOYEES

    def _normalize_employee_reference(self, plan: QueryPlan, q_lower: str) -> None:
        """Extracts employee references from phrases like 'claims made by MI0095'."""
        pattern = r"\b(?:made|created|raised|requested|submitted)\s+by\s+([a-z][a-z\s.]*\d*[a-z0-9]*|[a-z]{1,6}\d{2,})\b"
        match = re.search(pattern, q_lower, re.IGNORECASE)
        if not match:
            return

        raw = match.group(1).strip()
        raw = re.sub(r"\b(?:employee|emp|id|requisition|requisitions|claim|claims)\b.*$", "", raw).strip()
        if not raw:
            return

        plan.entity = QueryEntity.EMPLOYEE
        plan.subject_scope = SubjectScope.SPECIFIC_EMPLOYEE
        plan.group_by = None
        plan.filters.pop("description_keyword", None)

        if re.fullmatch(r"[a-z]{1,6}\d{2,}", raw, re.IGNORECASE):
            plan.target_employee_id = raw.upper()
            plan.target_employee_name = None
        else:
            plan.target_employee_name = raw.title()
            plan.target_employee_id = None

    def _normalize_ranking_plan(self, plan: QueryPlan, q_lower: str) -> None:
        """Preserves the requested dimension for highest/lowest ranking questions."""
        has_ranking = self._has_word_signal(
            q_lower,
            ["highest", "largest", "top", "max", "maximum", "lowest", "smallest", "min", "minimum", "least"],
        )
        if not has_ranking:
            return

        if any(w in q_lower for w in ["employee", "person", "who", "staff", "member"]):
            plan.intent = QueryIntent.ANALYTICS
            plan.entity = QueryEntity.EMPLOYEE
            plan.group_by = "employee_name"
            plan.aggregation = "SUM"
            plan.metric = plan.metric or "Approved Value in INR"
            plan.limit = plan.limit or 1
        elif any(w in q_lower for w in ["department", "dept"]):
            plan.intent = QueryIntent.ANALYTICS
            plan.entity = QueryEntity.DEPARTMENT
            plan.group_by = "Department"
            plan.aggregation = "SUM"
            plan.metric = plan.metric or "Approved Value in INR"
            plan.limit = plan.limit or 1

        if self._has_word_signal(q_lower, ["lowest", "smallest", "minimum", "min", "least"]):
            plan.sort_direction = "asc"
        else:
            plan.sort_direction = "desc"

    def _normalize_detail_plan(self, plan: QueryPlan, q_lower: str) -> None:
        """Avoids exact-record lookups unless the query contains a requisition number."""
        wants_requisition_details = (
            bool(re.search(r"\bdetails?\b", q_lower))
            and any(w in q_lower for w in ["requisition", "requisitions", "claim", "claims", "it", "its", "this", "that"])
        )
        if plan.intent == QueryIntent.GET_REQUISITION and not plan.exact_req_no and wants_requisition_details:
            plan.intent = QueryIntent.LIST_REQUISITIONS
            plan.entity = QueryEntity.REQUISITION
            plan.group_by = None
            plan.aggregation = None
            plan.metric = None
            plan.output_type = OutputType.TABLE

    def _detect_description_keyword(self, q_lower: str) -> Optional[str]:
        categories = [
            "travel", "hotel", "flight", "accommodation", "transport",
            "software", "hardware", "laptop", "computer", "equipment",
            "training", "course", "certification",
            "office", "stationery", "supplies", "medical", "health",
            "fuel", "vehicle", "car", "repair", "maintenance", "service",
            "subscription", "license", "driver", "salary", "wages", "food",
            "catering", "uniform", "printing", "courier", "logistics",
            "electricity", "rent", "security", "cleaning", "insurance",
            "telephone", "internet",
        ]
        for cat in categories:
            if cat in q_lower:
                return cat

        phrase_patterns = [
            r"\brelated\s+to\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
            r"\babout\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
            r"\bregarding\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
            r"\bfor\s+(.+?)(?:\s+requisition|\s+claim|\s+request|\s*$)",
        ]
        noise = {"the", "a", "an", "all", "any", "some", "my", "our", "their"}
        for p in phrase_patterns:
            m = re.search(p, q_lower)
            if m:
                raw = m.group(1).strip()
                tokens = [t for t in raw.split() if t not in noise]
                if tokens:
                    return " ".join(tokens)
        return None

    def _detect_exact_req_no(self, q: str) -> Optional[str]:
        patterns = [
            r"\b(REQ-\d{4}-\d+)\b",
            r"\b(REQ-\d+)\b",
            r"\b(G_\d+_\d+/\d{4})\b",
            r"\b(G-\d{4}-\d+)\b",
            r"\b([A-Z]{1,4}[_-]\d{2,4}[_-]\d+(?:/\d{4})?)\b",
            r"\b(REQ\d{4,10})\b",
            r"\b(WO\d{4,10})\b",
        ]
        for p in patterns:
            m = re.search(p, q.upper())
            if m:
                return m.group(1)
        return None

    def _is_recency_query(self, q_lower: str) -> bool:
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

    def _has_word_signal(self, text: str, signals: list) -> bool:
        for sig in signals:
            if rf"\b{re.escape(sig)}\b" in text or re.search(rf"\b{re.escape(sig)}\b", text):
                return True
        return False

    def _detect_named_employee(self, q_lower: str) -> Tuple[Optional[str], Optional[str]]:
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
