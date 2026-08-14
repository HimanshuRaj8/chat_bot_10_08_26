"""
Backend V3 — Claim Period Analytics Service
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from models.query import SubjectScope
from data.requisition_repository import RequisitionRepository

logger = logging.getLogger(__name__)

class ClaimPeriodAnalytics:

    def __init__(self, requisition_repo: RequisitionRepository):
        self.requisition_repo = requisition_repo

    def _normalize_category(self, title: str, desc: str) -> str:
        t = (title or "").lower()
        d = (desc or "").lower()
        if "internet" in t or "wifi" in t or "internet" in d or "wifi" in d:
            return "Internet"
        if "parking" in t or "parking" in d or "conveyance" in t or "conveyance" in d:
            return "Parking/Conveyance"
        if "driver" in t or "driver" in d:
            return "Driver Salary"
        if "newspaper" in t or "periodical" in t or "newspaper" in d or "periodical" in d:
            return "Newspaper & Periodicals"
        if "welfare" in t or "welfare" in d:
            return "Staff Welfare"
        if "travel" in t or "travel" in d:
            return "Travel"
        return title or "Other"

    def get_last_claimed_period(
        self,
        scope: SubjectScope,
        employee_id: Optional[str],
        keyword: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Finds the most recent requisition with a valid claim period."""
        records, _ = self.requisition_repo.get_requisitions(
            scope=scope,
            employee_id=employee_id,
            keyword=keyword,
            sort_field="Created On",
            sort_direction="desc",
            page=1,
            page_size=1000,
        )
        for r in records:
            if r.claim_period_start and r.claim_period_end:
                return {
                    "requisition_no": r.requisition_no,
                    "description": r.description,
                    "claim_period_start": r.claim_period_start,
                    "claim_period_end": r.claim_period_end,
                    "claim_period_text": r.claim_period_text,
                    "period_confidence": r.period_confidence,
                    "created_on": r.created_on,
                    "status": r.status,
                    "value_inr": r.value_in_inr,
                    "approved_value_inr": r.approved_value_in_inr,
                    "finally_approved_on": r.finally_approved_on,
                }
        return None

    def get_claim_timeline(
        self,
        scope: SubjectScope,
        employee_id: Optional[str],
        keyword: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Returns sorted timeline of claim periods."""
        records, _ = self.requisition_repo.get_requisitions(
            scope=scope,
            employee_id=employee_id,
            keyword=keyword,
            page=1,
            page_size=1000,
        )
        # Filter records with claim periods and sort them by start date
        timeline_records = [r for r in records if r.claim_period_start]
        # Sort chronologically by start date
        timeline_records.sort(key=lambda x: x.claim_period_start)
        
        timeline = []
        for r in timeline_records:
            timeline.append({
                "requisition_no": r.requisition_no,
                "employee_id": r.employee_id,
                "employee_name": r.employee_name,
                "claim_period_text": r.claim_period_text,
                "claim_period_start": r.claim_period_start,
                "claim_period_end": r.claim_period_end,
                "status": r.status,
                "approved_value_inr": r.approved_value_in_inr,
                "description": r.description,
            })
        return timeline

    def find_missing_periods(
        self,
        scope: SubjectScope,
        employee_id: Optional[str],
        keyword: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Identifies gaps in monthly claims within an employee's window."""
        records, _ = self.requisition_repo.get_requisitions(
            scope=scope,
            employee_id=employee_id,
            keyword=keyword,
            page=1,
            page_size=10000,
        )
        
        # Group by employee
        emp_records = {}
        for r in records:
            if r.claim_period_start and r.claim_months:
                emp_records.setdefault(r.employee_id, []).extend(r.claim_months)
                
        missing_by_employee = []
        for emp_id, months in emp_records.items():
            unique_months = sorted(list(set(months)))
            if len(unique_months) < 2:
                continue # No gaps possible with < 2 claims
                
            # Parse start and end month
            sy, sm = map(int, unique_months[0].split("-"))
            ey, em = map(int, unique_months[-1].split("-"))
            
            # Generate all months in between
            all_expected = []
            cy, cm = sy, sm
            while (cy < ey) or (cy == ey and cm <= em):
                all_expected.append(f"{cy:04d}-{cm:02d}")
                cm += 1
                if cm > 12:
                    cm = 1
                    cy += 1
                    
            missing = [m for m in all_expected if m not in unique_months]
            if missing:
                # Find employee name
                emp_name = next(r.employee_name for r in records if r.employee_id == emp_id)
                # Form list of missing months formatted nicely (e.g. May-2026)
                months_formatted = []
                for m in missing:
                    y_part, m_part = map(int, m.split("-"))
                    import calendar
                    m_abbr = calendar.month_abbr[m_part]
                    months_formatted.append(f"{m_abbr}-{y_part}")
                    
                missing_by_employee.append({
                    "employee_id": emp_id,
                    "employee_name": emp_name,
                    "missing_months": months_formatted,
                    "period_range": f"{unique_months[0]} to {unique_months[-1]}"
                })
                
        return missing_by_employee

    def find_duplicate_periods(
        self,
        scope: SubjectScope,
        employee_id: Optional[str],
        keyword: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Detects duplicate claims (same employee + same normalized category + overlapping month)."""
        records, _ = self.requisition_repo.get_requisitions(
            scope=scope,
            employee_id=employee_id,
            keyword=keyword,
            page=1,
            page_size=10000,
        )
        
        groups = {}
        for r in records:
            if not r.claim_period_start or not r.claim_months:
                continue
            cat = self._normalize_category(r.document_title, r.description)
            key = (r.employee_id, cat)
            groups.setdefault(key, []).append(r)
            
        duplicates = []
        for (emp_id, cat), rec_list in groups.items():
            if len(rec_list) < 2:
                continue
            for i in range(len(rec_list)):
                for j in range(i + 1, len(rec_list)):
                    r1 = rec_list[i]
                    r2 = rec_list[j]
                    shared = set(r1.claim_months).intersection(set(r2.claim_months))
                    if shared:
                        duplicates.append({
                            "employee_id": emp_id,
                            "employee_name": r1.employee_name,
                            "department": r1.department,
                            "category": cat,
                            "requisition_1": r1.requisition_no,
                            "period_1": r1.claim_period_text,
                            "value_1": r1.approved_value_in_inr or r1.value_in_inr,
                            "status_1": r1.status,
                            "requisition_2": r2.requisition_no,
                            "period_2": r2.claim_period_text,
                            "value_2": r2.approved_value_in_inr or r2.value_in_inr,
                            "status_2": r2.status,
                            "overlapping_months": sorted(list(shared)),
                        })
        return duplicates

    def find_overlapping_periods(
        self,
        scope: SubjectScope,
        employee_id: Optional[str],
        keyword: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Detects date-range overlaps within claims."""
        records, _ = self.requisition_repo.get_requisitions(
            scope=scope,
            employee_id=employee_id,
            keyword=keyword,
            page=1,
            page_size=10000,
        )
        
        groups = {}
        for r in records:
            if not r.claim_period_start or not r.claim_period_end:
                continue
            cat = self._normalize_category(r.document_title, r.description)
            key = (r.employee_id, cat)
            groups.setdefault(key, []).append(r)
            
        overlaps = []
        for (emp_id, cat), rec_list in groups.items():
            if len(rec_list) < 2:
                continue
            for i in range(len(rec_list)):
                for j in range(i + 1, len(rec_list)):
                    r1 = rec_list[i]
                    r2 = rec_list[j]
                    s1, e1 = r1.claim_period_start, r1.claim_period_end
                    s2, e2 = r2.claim_period_start, r2.claim_period_end
                    
                    if s1 <= e2 and s2 <= e1:
                        overlap_start = max(s1, s2)
                        overlap_end = min(e1, e2)
                        overlaps.append({
                            "employee_id": emp_id,
                            "employee_name": r1.employee_name,
                            "department": r1.department,
                            "category": cat,
                            "requisition_1": r1.requisition_no,
                            "period_1": r1.claim_period_text,
                            "value_1": r1.approved_value_in_inr or r1.value_in_inr,
                            "status_1": r1.status,
                            "requisition_2": r2.requisition_no,
                            "period_2": r2.claim_period_text,
                            "value_2": r2.approved_value_in_inr or r2.value_in_inr,
                            "status_2": r2.status,
                            "overlap_start": overlap_start,
                            "overlap_end": overlap_end,
                        })
        return overlaps
