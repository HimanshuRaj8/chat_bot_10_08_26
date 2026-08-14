"""
Backend V3 — Requisition Record Model
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RequisitionRecord:
    """Canonical representation of a single requisition row loaded from Excel."""
    s_no: Optional[int] = None
    requisition_no: str = ""
    description: str = ""
    document_title: str = ""
    stars_req_no: str = ""
    requested_by_raw: str = ""
    employee_name: str = ""
    employee_id: str = ""
    operational_unit: str = ""
    cost_centre: str = ""
    department: str = ""
    created_on: str = ""
    finally_approved_on: str = ""
    currency: str = "INR"
    value: float = 0.0
    value_in_inr: float = 0.0
    approved_value: float = 0.0
    approved_value_in_inr: float = 0.0
    hod_approved_value: float = 0.0
    status: str = ""
    approved_by: str = ""

    # Claim Period Intelligence fields
    claim_period_start: Optional[str] = None
    claim_period_end: Optional[str] = None
    claim_period_text: Optional[str] = None
    claim_months: Optional[list] = None
    period_confidence: Optional[str] = None

    def to_source_dict(self) -> dict:
        """Compact representation for API source records."""
        return {
            "source": self.requisition_no,
            "requisition_no": self.requisition_no,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "department": self.department,
            "status": self.status,
            "approved_value_inr": self.approved_value_in_inr,
            "value_inr": self.value_in_inr,
            "description": self.description[:80] + "..." if len(self.description) > 80 else self.description,
            "created_on": self.created_on,
            "approved_by": self.approved_by,
            "claim_period_start": self.claim_period_start,
            "claim_period_end": self.claim_period_end,
            "claim_period_text": self.claim_period_text,
            "claim_months": self.claim_months,
            "period_confidence": self.period_confidence,
        }
