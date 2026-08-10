"""
Backend V3 — Query Plan, Intent, Scope, and Result Models
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class QueryIntent(str, Enum):
    PROFILE                 = "PROFILE"
    LIST_REQUISITIONS       = "LIST_REQUISITIONS"
    GET_REQUISITION         = "GET_REQUISITION"
    GET_LATEST_REQUISITION  = "GET_LATEST_REQUISITION"
    GET_PREVIOUS_REQUISITION = "GET_PREVIOUS_REQUISITION"
    ANALYTICS               = "ANALYTICS"
    CLARIFICATION           = "CLARIFICATION"
    OUT_OF_SCOPE            = "OUT_OF_SCOPE"
    NO_DATA                 = "NO_DATA"
    ERROR                   = "ERROR"


class SubjectScope(str, Enum):
    CURRENT_USER       = "CURRENT_USER"        # "my" or default Employee scope
    SPECIFIC_EMPLOYEE  = "SPECIFIC_EMPLOYEE"   # Named employee (Finance/Admin only)
    ALL_EMPLOYEES      = "ALL_EMPLOYEES"       # Organization-wide (Finance/Admin only)


class QueryEntity(str, Enum):
    REQUISITION       = "Requisition"
    EMPLOYEE          = "Employee"
    DEPARTMENT        = "Department"
    COST_CENTRE       = "CostCentre"
    OPERATIONAL_UNIT  = "OperationalUnit"
    MONTH             = "Month"
    QUARTER           = "Quarter"
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
    NATURAL_TEXT    = "NaturalText"
    SINGLE_METRIC   = "SingleMetric"
    SHORT_SUMMARY   = "ShortSummary"
    TABLE           = "Table"


class ResponseType(str, Enum):
    RECORD_LIST     = "RECORD_LIST"
    SINGLE_RECORD   = "SINGLE_RECORD"
    SUMMARY         = "SUMMARY"
    ANALYTICS       = "ANALYTICS"
    CLARIFICATION   = "CLARIFICATION"
    ERROR           = "ERROR"
    OUT_OF_SCOPE    = "OUT_OF_SCOPE"
    NO_DATA         = "NO_DATA"


@dataclass
class DateRange:
    label: str = ""                    # e.g. "last month", "April 2026"
    start: Optional[Any] = None        # datetime
    end: Optional[Any] = None          # datetime


@dataclass
class QueryPlan:
    """
    Structured query plan produced by QueryPlanner and validated before execution.
    """
    intent: QueryIntent = QueryIntent.OUT_OF_SCOPE
    entity: QueryEntity = QueryEntity.REQUISITION
    metric: Optional[str] = None                # column to aggregate/sort on
    aggregation: Optional[str] = None           # SUM, COUNT, AVG, MAX, MIN
    group_by: Optional[str] = None              # column name to group by
    filters: Dict[str, Any] = field(default_factory=dict)
    date_range: DateRange = field(default_factory=DateRange)
    subject_scope: SubjectScope = SubjectScope.ALL_EMPLOYEES
    target_employee_id: Optional[str] = None    # employee ID referenced in query
    target_employee_name: Optional[str] = None  # name hint parsed from query
    sort_field: str = "Created On"
    sort_direction: str = "desc"                # asc, desc
    limit: Optional[int] = None
    page: int = 1
    page_size: int = 20
    output_type: OutputType = OutputType.NATURAL_TEXT
    exact_req_no: Optional[str] = None
    profile_metric: Optional[str] = None        # e.g. Name, EmployeeID
    is_follow_up: bool = False
    original_question: str = ""


@dataclass
class VerifiedResult:
    """
    The output produced by the data query & analytics engines.
    Passes verified ground truth to the response generator.
    """
    success: bool
    response_type: ResponseType
    message: str
    data: Optional[Dict[str, Any]] = None       # {"records": [...]} or similar
    analytics: Optional[Dict[str, Any]] = None  # {"count": 75, "approved_value_inr": 307872.63}
    sources: List[Dict[str, Any]] = field(default_factory=list)
    applied_filters: List[str] = field(default_factory=list)
    # Pagination
    page: Optional[int] = None
    page_size: Optional[int] = None
    total: Optional[int] = None
    total_pages: Optional[int] = None
    has_next: bool = False
    has_previous: bool = False

    def to_dict(self) -> dict:
        d = {
            "success": self.success,
            "response_type": self.response_type.value,
            "message": self.message,
            "data": self.data,
            "analytics": self.analytics,
            "sources": self.sources,
            "applied_filters": self.applied_filters,
        }
        if self.page is not None:
            d["pagination"] = {
                "page": self.page,
                "page_size": self.page_size,
                "total": self.total,
                "total_pages": self.total_pages,
                "has_next": self.has_next,
                "has_previous": self.has_previous,
            }
        else:
            d["pagination"] = None
        return d
