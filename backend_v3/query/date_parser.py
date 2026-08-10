"""
Backend V3 — Date Parser Utility
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

DateRangeTuple = Tuple[Optional[datetime], Optional[datetime], str]


def parse_date_phrase(text: str) -> DateRangeTuple:
    """
    Converts natural language date phrases to (start, end, label) tuple.
    Deterministic, offline.
    """
    text_lower = text.lower()
    now = datetime.now()

    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    month_abbrs = ["jan", "feb", "mar", "apr", "may", "jun",
                   "jul", "aug", "sep", "oct", "nov", "dec"]

    for i, (full, abbr) in enumerate(zip(month_names, month_abbrs), start=1):
        for pattern in [rf"\b{full}\s+(\d{{4}})\b", rf"\b{abbr}\s+(\d{{4}})\b"]:
            m = re.search(pattern, text_lower)
            if m:
                year = int(m.group(1))
                start = datetime(year, i, 1)
                end = (start + relativedelta(months=1)) - timedelta(days=1)
                label = f"{full.title()} {year}"
                return start, end, label

        for pattern in [rf"\b{full}\b", rf"\b{abbr}\b"]:
            if re.search(pattern, text_lower):
                start = datetime(now.year, i, 1)
                end = (start + relativedelta(months=1)) - timedelta(days=1)
                label = f"{full.title()} {now.year}"
                return start, end, label

    if "last month" in text_lower or "previous month" in text_lower:
        first_of_this = datetime(now.year, now.month, 1)
        start = first_of_this - relativedelta(months=1)
        end = first_of_this - timedelta(days=1)
        return start, end, "Last Month"

    if "this month" in text_lower or "current month" in text_lower:
        start = datetime(now.year, now.month, 1)
        end = now
        return start, end, "This Month"

    if "last quarter" in text_lower or "previous quarter" in text_lower:
        current_q = (now.month - 1) // 3
        if current_q == 0:
            start = datetime(now.year - 1, 10, 1)
            end = datetime(now.year, 1, 1) - timedelta(days=1)
        else:
            start_month = (current_q - 1) * 3 + 1
            start = datetime(now.year, start_month, 1)
            end = datetime(now.year, start_month + 3, 1) - timedelta(days=1)
        return start, end, "Last Quarter"

    if "this quarter" in text_lower or "current quarter" in text_lower:
        current_q = (now.month - 1) // 3 + 1
        start_month = (current_q - 1) * 3 + 1
        start = datetime(now.year, start_month, 1)
        return start, now, f"Q{current_q} {now.year}"

    if "this year" in text_lower or "current year" in text_lower:
        start = datetime(now.year, 1, 1)
        return start, now, f"Year {now.year}"

    if "last year" in text_lower or "previous year" in text_lower:
        start = datetime(now.year - 1, 1, 1)
        end = datetime(now.year, 1, 1) - timedelta(days=1)
        return start, end, f"Year {now.year - 1}"

    if "last week" in text_lower:
        end = now - timedelta(days=now.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end, "Last Week"

    if "this week" in text_lower:
        start = now - timedelta(days=now.weekday())
        return start, now, "This Week"

    m = re.search(r"last\s+(\d+)\s+months?", text_lower)
    if m:
        n = int(m.group(1))
        start = now - relativedelta(months=n)
        return start, now, f"Last {n} Months"

    m = re.search(r"\b(20\d{2})\b", text_lower)
    if m:
        year = int(m.group(1))
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
        return start, end, f"Year {year}"

    m = re.search(r"\bq([1-4])\s*(?:fy)?(\d{2,4})?\b", text_lower)
    if m:
        q = int(m.group(1))
        year = int(m.group(2)) if m.group(2) else now.year
        if year < 100:
            year += 2000
        start_month = (q - 1) * 3 + 1
        start = datetime(year, start_month, 1)
        end = (start + relativedelta(months=3)) - timedelta(days=1)
        return start, end, f"Q{q} {year}"

    return None, None, ""
