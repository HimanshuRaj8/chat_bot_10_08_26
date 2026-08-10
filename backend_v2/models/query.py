"""
Backend V2 — Query Plan and Verified Result Models

These are the canonical contracts that flow through the entire pipeline.
The QueryPlan is produced by the QueryPlanner.
The VerifiedResult is produced by the QueryExecutor.
The ResponseGenerator only ever uses VerifiedResult — never raw data.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class QueryIntent(str, Enum):
    PROFILE      = "PROFILE"       # Identity questions — bypass data layer
    LOOKUP       = "LOOKUP"        # Exact requisition number lookup
    FILTER       = "FILTER"        # Show/list with filters applied
    AGGREGATE    = "AGGREGATE"     # Total / sum / average single value
    COUNT        = "COUNT"         # How many / number of
    RANKING      = "RANKING"       # Highest / lowest / top N with grouping
    TREND        = "TREND"         # Month-wise / quarter-wise / time analysis
    COMPARISON   = "COMPARISON"    # Compare departments / employees / periods
    SUMMARY      = "SUMMARY"       # Department/employee-wise overview table
    APPROVER_ANALYSIS = "APPROVER_ANALYSIS" # Extract/group approver information
    DATE_ANALYSIS = "DATE_ANALYSIS"   # Extract date / approval timing information
    FOLLOW_UP    = "FOLLOW_UP"     # Refers to previous query context
    AMBIGUOUS    = "AMBIGUOUS"     # Cannot safely determine intent


class SubjectScope(str, Enum):
    CURRENT_USER       = "CURRENT_USER"        # "my" — authenticated user only
    SPECIFIC_EMPLOYEE  = "SPECIFIC_EMPLOYEE"   # Named employee (Finance only)
    ALL_EMPLOYEES      = "ALL_EMPLOYEES"        # Organization-wide


class QueryEntity(str, Enum):
    REQUISITION       = "Requisition"
    EMPLOYEE          = "Employee"
    DEPARTMENT        = "Department"
    COST_CENTRE       = "CostCentre"
    OPERATIONAL_UNIT  = "OperationalUnit"
    CATEGORY          = "Category"
    MONTH             = "Month"
    QUARTER           = "Quarter"
    YEAR              = "Year"
    STATUS            = "Status"


class QueryMetric(str, Enum):
    APPROVED_VALUE_INR  = "approved_value_inr"
    REQUESTED_VALUE_INR = "value_inr"
    COUNT               = "count"
    AVERAGE_VALUE       = "average_approved_value_inr"
    # Profile metrics
    EMPLOYEE_ID         = "EmployeeID"
    NAME                = "Name"
    DEPARTMENT          = "Department"
    ROLE                = "Role"
    EMAIL               = "Email"
    LOCATION            = "Location"
    FULL_PROFILE        = "FullProfile"


class OutputType(str, Enum):
    NATURAL_TEXT    = "NaturalText"    # Single sentence conversational
    SINGLE_METRIC   = "SingleMetric"   # One number answer
    SHORT_SUMMARY   = "ShortSummary"   # 1-3 bullet points
    TABLE           = "Table"          # Markdown table for multi-row


@dataclass
class DateRange:
    label: str = ""                    # "last month", "this quarter", etc.
    start: Optional[Any] = None        # datetime
    end: Optional[Any] = None          # datetime


@dataclass
class QueryPlan:
    """
    The authoritative execution plan produced by QueryPlanner.
    QueryExecutor MUST follow this plan exactly — never re-interpret NL.
    """
    intent: QueryIntent = QueryIntent.AMBIGUOUS
    entity: QueryEntity = QueryEntity.REQUISITION
    metric: Optional[str] = None                # column name to aggregate
    aggregation: str = "SUM"                    # SUM, COUNT, AVG, MAX, MIN
    group_by: Optional[str] = None              # pandas groupby column name
    filters: Dict[str, Any] = field(default_factory=dict)
    date_range: DateRange = field(default_factory=DateRange)
    subject_scope: SubjectScope = SubjectScope.ALL_EMPLOYEES
    target_employee_id: Optional[str] = None    # for SPECIFIC_EMPLOYEE scope
    sort_order: str = "desc"
    limit: Optional[int] = None
    page: int = 1
    page_size: int = 20
    output_type: OutputType = OutputType.NATURAL_TEXT
    exact_req_no: Optional[str] = None
    profile_metric: Optional[str] = None        # for PROFILE intent
    is_follow_up: bool = False
    original_question: str = ""


@dataclass
class VerifiedResult:
    """
    The authoritative result produced by QueryExecutor.
    ResponseGenerator MUST only use this — never query data again.
    """
    success: bool
    query_type: str
    entity: str
    metric: str
    aggregation: str
    subject_scope: str
    total_records_analyzed: int
    result: List[Dict[str, Any]]       # [{group, value, count, ...}]
    source_records: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    applied_filters: List[str] = field(default_factory=list)
    # Pagination metadata
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    has_next: bool = False
    has_previous: bool = False
    returned_records: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "query_type": self.query_type,
            "entity": self.entity,
            "metric": self.metric,
            "aggregation": self.aggregation,
            "subject_scope": self.subject_scope,
            "total_records_analyzed": self.total_records_analyzed,
            "total_records": self.total_records_analyzed,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
            "returned_records": self.returned_records,
            "result": self.result,
            "source_records": self.source_records,
            "applied_filters": self.applied_filters,
        }
