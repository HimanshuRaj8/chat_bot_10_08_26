"""
Backend V3 — Claim Period Extractor
"""
import re
import calendar
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}

MONTH_PATTERN = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

# Recurring monthly categories
RECURRING_KEYWORDS = [
    "internet", "wifi", "driver", "salary", "wages", "newspaper", 
    "periodical", "parking", "conveyance", "fuel", "petrol", 
    "telephone", "phone", "broadband", "mobile"
]

class ClaimPeriodExtractor:

    def __init__(self, default_ref_year: int = 2026):
        self.default_ref_year = default_ref_year

    def _get_ref_year(self, created_on: Any) -> int:
        if pd.isna(created_on) or not created_on:
            return self.default_ref_year
        try:
            if isinstance(created_on, str):
                # Try common formats
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        return datetime.strptime(created_on.split()[0], fmt).year
                    except ValueError:
                        continue
                dt = pd.to_datetime(created_on)
                return dt.year if pd.notna(dt) else self.default_ref_year
            if hasattr(created_on, "year"):
                return created_on.year
            dt = pd.to_datetime(created_on)
            return dt.year if pd.notna(dt) else self.default_ref_year
        except Exception:
            return self.default_ref_year

    def _is_duration(self, yr_str: Optional[str], text: str, end_idx: int) -> bool:
        if not yr_str:
            return False
        following = text[end_idx:].strip().lower()
        if following.startswith(("day", "month", "week")):
            return True
        return False

    def resolve_year(self, yr_str: Optional[str], ref_year: int) -> int:
        if not yr_str:
            return ref_year
        yr_clean = re.sub(r"\D", "", yr_str)
        if not yr_clean:
            return ref_year
        yr = int(yr_clean)
        if yr < 100:
            yr = 2000 + yr
            
        context_ref = getattr(self, "current_ref_year", ref_year)
        if yr < context_ref - 5 or yr > context_ref + 1:
            return ref_year
        return yr

    def get_months_in_date_range(self, start_date: datetime, end_date: datetime) -> List[str]:
        months = []
        cy, cm = start_date.year, start_date.month
        ey, em = end_date.year, end_date.month
        while (cy < ey) or (cy == ey and cm <= em):
            months.append(f"{cy:04d}-{cm:02d}")
            cm += 1
            if cm > 12:
                cm = 1
                cy += 1
        return months

    def get_months_in_month_range(self, start_m: int, start_y: int, end_m: int, end_y: int) -> List[str]:
        months = []
        cy, cm = start_y, start_m
        while (cy < end_y) or (cy == end_y and cm <= end_m):
            months.append(f"{cy:04d}-{cm:02d}")
            cm += 1
            if cm > 12:
                cm = 1
                cy += 1
        return months

    def extract_date_range(self, text: str, ref_year: int) -> Optional[Tuple[str, str, List[str], str]]:
        # 1. Pattern: 18th Feb 26 to 3rd Apr 26 / 1 Apr to 5 Jun 48 days / 26 April 2026 to 2 May 2026
        # Matches day, month, optional year to day, month, optional year
        pat_dates = rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_PATTERN}\s*(\d{{2,4}})?\s*(?:to|till|-|and)\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_PATTERN}\s*(\d{{2,4}})?\b"
        match = re.search(pat_dates, text, re.IGNORECASE)
        if match:
            d1_str, m1_str, y1_str, d2_str, m2_str, y2_str = match.groups()
            m1 = MONTH_MAP[m1_str.lower()]
            m2 = MONTH_MAP[m2_str.lower()]
            
            if y2_str and self._is_duration(y2_str, text, match.end(6)):
                y2_str = None
            if y1_str and self._is_duration(y1_str, text, match.end(3)):
                y1_str = None
            
            y2 = self.resolve_year(y2_str, ref_year)
            y1 = self.resolve_year(y1_str, y2) # Use end year if start year is missing
            
            try:
                dt1 = datetime(y1, m1, int(d1_str))
                dt2 = datetime(y2, m2, int(d2_str))
                if dt1 > dt2:
                    dt1, dt2 = dt2, dt1
                months = self.get_months_in_date_range(dt1, dt2)
                return (
                    dt1.strftime("%Y-%m-%d"),
                    dt2.strftime("%Y-%m-%d"),
                    months,
                    f"{dt1.strftime('%d-%b-%Y')} to {dt2.strftime('%d-%b-%Y')}"
                )
            except ValueError:
                pass

        # 2. Pattern: 18/02/2026 to 03/04/2026 or 18-02-26 to 03-04-26
        pat_numeric = r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\s*(?:to|till|-)\s*(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b"
        match = re.search(pat_numeric, text)
        if match:
            d1, m1, y1_str, d2, m2, y2_str = match.groups()
            if y2_str and self._is_duration(y2_str, text, match.end(6)):
                y2_str = None
            if y1_str and self._is_duration(y1_str, text, match.end(3)):
                y1_str = None
                
            y1 = self.resolve_year(y1_str, ref_year)
            y2 = self.resolve_year(y2_str, ref_year)
            try:
                dt1 = datetime(y1, int(m1), int(d1))
                dt2 = datetime(y2, int(m2), int(d2))
                if dt1 > dt2:
                    dt1, dt2 = dt2, dt1
                months = self.get_months_in_date_range(dt1, dt2)
                return (
                    dt1.strftime("%Y-%m-%d"),
                    dt2.strftime("%Y-%m-%d"),
                    months,
                    f"{dt1.strftime('%d-%b-%Y')} to {dt2.strftime('%d-%b-%Y')}"
                )
            except ValueError:
                pass

        # 3. Pattern: 24 - 25 June 2026 (same month, different days)
        pat_same_month = rf"\b(\d{{1,2}})\s*(?:to|till|-)\s*(\d{{1,2}})\s+{MONTH_PATTERN}\s*(\d{{2,4}})?\b"
        match = re.search(pat_same_month, text, re.IGNORECASE)
        if match:
            d1, d2, m_str, y_str = match.groups()
            m = MONTH_MAP[m_str.lower()]
            if y_str and self._is_duration(y_str, text, match.end(4)):
                y_str = None
            y = self.resolve_year(y_str, ref_year)
            try:
                dt1 = datetime(y, m, int(d1))
                dt2 = datetime(y, m, int(d2))
                if dt1 > dt2:
                    dt1, dt2 = dt2, dt1
                months = self.get_months_in_date_range(dt1, dt2)
                return (
                    dt1.strftime("%Y-%m-%d"),
                    dt2.strftime("%Y-%m-%d"),
                    months,
                    f"{dt1.strftime('%d-%b-%Y')} to {dt2.strftime('%d-%b-%Y')}"
                )
            except ValueError:
                pass

        return None

    def extract_multi_month(self, text: str, ref_year: int) -> Optional[Tuple[str, str, List[str], str]]:
        # 1. Pattern: Jul25 till Feb 26 / Apr - Jun / Newspaper and Periodicals Apr - Jun
        pat_range = rf"\b{MONTH_PATTERN}\s*(\d{{2,4}})?\s*(?:to|till|-|and|&)\s*{MONTH_PATTERN}\s*(\d{{2,4}})?\b"
        match = re.search(pat_range, text, re.IGNORECASE)
        if match:
            m1_str, y1_str, m2_str, y2_str = match.groups()
            m1 = MONTH_MAP[m1_str.lower()]
            m2 = MONTH_MAP[m2_str.lower()]
            
            if y2_str and self._is_duration(y2_str, text, match.end(4)):
                y2_str = None
            if y1_str and self._is_duration(y1_str, text, match.end(2)):
                y1_str = None
                
            y2 = self.resolve_year(y2_str, ref_year)
            y1 = self.resolve_year(y1_str, y2)
            
            # Start of month 1 to end of month 2
            start_date = datetime(y1, m1, 1)
            last_day = calendar.monthrange(y2, m2)[1]
            end_date = datetime(y2, m2, last_day)
            
            if start_date > end_date:
                start_date, end_date = end_date, start_date
                m1, m2 = m2, m1
                y1, y2 = y2, y1
                
            months = self.get_months_in_month_range(m1, y1, m2, y2)
            
            return (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                months,
                f"{start_date.strftime('%b-%Y')} to {end_date.strftime('%b-%Y')}"
            )

        # 2. Pattern: Apr+May2026 / Apr26, May26 / May June (space or comma separated list of months)
        pat_list = rf"\b{MONTH_PATTERN}\s*(\d{{2,4}})?\s*[+,\s/]+\s*{MONTH_PATTERN}\s*(\d{{2,4}})?\b"
        match = re.search(pat_list, text, re.IGNORECASE)
        if match:
            m1_str, y1_str, m2_str, y2_str = match.groups()
            m1 = MONTH_MAP[m1_str.lower()]
            m2 = MONTH_MAP[m2_str.lower()]
            
            if y2_str and self._is_duration(y2_str, text, match.end(4)):
                y2_str = None
            if y1_str and self._is_duration(y1_str, text, match.end(2)):
                y1_str = None
                
            y2 = self.resolve_year(y2_str, ref_year)
            y1 = self.resolve_year(y1_str, y2)
            
            # Start of month 1 to end of month 2
            start_date = datetime(y1, m1, 1)
            last_day = calendar.monthrange(y2, m2)[1]
            end_date = datetime(y2, m2, last_day)
            
            if start_date > end_date:
                start_date, end_date = end_date, start_date
                m1, m2 = m2, m1
                y1, y2 = y2, y1
                
            months = self.get_months_in_month_range(m1, y1, m2, y2)
            
            return (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                months,
                f"{start_date.strftime('%b-%Y')} to {end_date.strftime('%b-%Y')}"
            )

        return None

    def extract_single_month(self, text: str, ref_year: int) -> Optional[Tuple[str, str, List[str], str]]:
        # Matches e.g. "April 2026", "June", "May Month", "salary - May", "June2026"
        pat_month_yr = rf"\b{MONTH_PATTERN}\s*['-]?\s*(\d{{2,4}})\b"
        match = re.search(pat_month_yr, text, re.IGNORECASE)
        if match:
            m_str, y_str = match.groups()
            m = MONTH_MAP[m_str.lower()]
            if y_str and self._is_duration(y_str, text, match.end(2)):
                y_str = None
            y = self.resolve_year(y_str, ref_year)
            start_date = datetime(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            end_date = datetime(y, m, last_day)
            month_key = f"{y:04d}-{m:02d}"
            return (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                [month_key],
                start_date.strftime("%b-%Y")
            )
            
        # Match month name without year (e.g., Driver Salary - June, May Month)
        pat_month_only = rf"\b{MONTH_PATTERN}\b"
        match = re.search(pat_month_only, text, re.IGNORECASE)
        if match:
            m_str = match.group(1)
            m = MONTH_MAP[m_str.lower()]
            y = ref_year
            start_date = datetime(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            end_date = datetime(y, m, last_day)
            month_key = f"{y:04d}-{m:02d}"
            return (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                [month_key],
                start_date.strftime("%b-%Y")
            )

        return None

    def extract_partial_date(self, text: str, ref_year: int) -> Optional[Tuple[str, str, List[str], str]]:
        # Matches e.g. "till 8-May" or "till 18-May-26" or "till 20 may"
        pat_till = rf"\btill\s+(\d{{1,2}})\s*[-/]?\s*{MONTH_PATTERN}(?:\s*[-/]?\s*(\d{{2,4}}))?\b"
        match = re.search(pat_till, text, re.IGNORECASE)
        if match:
            d_str, m_str, y_str = match.groups()
            m = MONTH_MAP[m_str.lower()]
            if y_str and self._is_duration(y_str, text, match.end(3)):
                y_str = None
            y = self.resolve_year(y_str, ref_year)
            try:
                dt_end = datetime(y, m, int(d_str))
                dt_start = datetime(y, m, 1) # Default to start of that same month
                months = self.get_months_in_date_range(dt_start, dt_end)
                return (
                    dt_start.strftime("%Y-%m-%d"),
                    dt_end.strftime("%Y-%m-%d"),
                    months,
                    f"Up to {dt_end.strftime('%d-%b-%Y')}"
                )
            except ValueError:
                pass
        return None

    def extract_period(self, description: str, title: str = "", created_on: Any = None) -> Dict[str, Any]:
        ref_year = self._get_ref_year(created_on)
        self.current_ref_year = ref_year
        text_to_search = f"{title} | {description}" if title else description

        # 1. Try explicit date range
        res = self.extract_date_range(text_to_search, ref_year)
        if res:
            start, end, months, text = res
            return {
                "claim_period_start": start,
                "claim_period_end": end,
                "claim_period_text": text,
                "claim_months": months,
                "period_confidence": "HIGH"
            }

        # 2. Try multi-month range
        res = self.extract_multi_month(text_to_search, ref_year)
        if res:
            start, end, months, text = res
            return {
                "claim_period_start": start,
                "claim_period_end": end,
                "claim_period_text": text,
                "claim_months": months,
                "period_confidence": "HIGH"
            }

        # 3. Try single month
        res = self.extract_single_month(text_to_search, ref_year)
        if res:
            start, end, months, text = res
            return {
                "claim_period_start": start,
                "claim_period_end": end,
                "claim_period_text": text,
                "claim_months": months,
                "period_confidence": "HIGH"
            }

        # 4. Try partial date (e.g. till 8-May)
        res = self.extract_partial_date(text_to_search, ref_year)
        if res:
            start, end, months, text = res
            return {
                "claim_period_start": start,
                "claim_period_end": end,
                "claim_period_text": text,
                "claim_months": months,
                "period_confidence": "MEDIUM"
            }

        # 5. Try recurring category fallback to Created On month
        search_lower = text_to_search.lower()
        is_recurring = any(kw in search_lower for kw in RECURRING_KEYWORDS)
        
        if is_recurring and created_on and not pd.isna(created_on):
            try:
                created_dt = pd.to_datetime(created_on)
                if pd.notna(created_dt):
                    y = created_dt.year
                    m = created_dt.month
                    start_date = datetime(y, m, 1)
                    last_day = calendar.monthrange(y, m)[1]
                    end_date = datetime(y, m, last_day)
                    month_key = f"{y:04d}-{m:02d}"
                    return {
                        "claim_period_start": start_date.strftime("%Y-%m-%d"),
                        "claim_period_end": end_date.strftime("%Y-%m-%d"),
                        "claim_period_text": f"{start_date.strftime('%b-%Y')} (Inferred from Created On)",
                        "claim_months": [month_key],
                        "period_confidence": "LOW"
                    }
            except Exception:
                pass

        # 6. Fallback: Unknown
        return {
            "claim_period_start": None,
            "claim_period_end": None,
            "claim_period_text": "Not determined",
            "claim_months": [],
            "period_confidence": "LOW"
        }

    def normalize_period(self, text: str) -> str:
        res = self.extract_period(text)
        return res["claim_period_text"]
