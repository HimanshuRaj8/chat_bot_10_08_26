"""
Backend V3 — Requisition Repository
"""
import logging
import math
import re
from typing import List, Dict, Optional, Any, Tuple
import pandas as pd

from models.requisition import RequisitionRecord
from models.query import QueryPlan, SubjectScope, DateRange
from models.user import CurrentUser
from .excel_provider import ExcelDataProvider

logger = logging.getLogger(__name__)


class RequisitionRepository:

    def __init__(self, data_provider: ExcelDataProvider):
        self.data_provider = data_provider

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Converts messy Excel values to floats without crashing record rendering."""
        if value is None or pd.isna(value):
            return default
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text:
            return default

        cleaned = text.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            matches = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
            if matches:
                return float(matches[-1])
            logger.warning("Could not parse numeric value from Excel cell: %r", value)
            return default

    # ── Clean Repository API ──────────────────────────────────────────────────

    def get_requisition_by_id(self, requisition_no: str) -> Optional[RequisitionRecord]:
        """Looks up a single requisition by its unique Requisition No."""
        if not requisition_no:
            return None
        df = self.data_provider.get_requisitions_df()
        if df.empty or "Requisition No" not in df.columns:
            return None
        mask = df["Requisition No"].astype(str).str.strip().str.upper() == requisition_no.strip().upper()
        matched = df[mask]
        if matched.empty:
            return None
        records = self._df_to_records(matched)
        return records[0] if records else None

    def get_requisitions(
        self,
        scope: SubjectScope,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        date_range: Optional[DateRange] = None,
        requisition_id_list: Optional[List[str]] = None,
        sort_field: str = "Created On",
        sort_direction: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[RequisitionRecord], int]:
        """
        Retrieves a paginated list of RequisitionRecords matching the filters,
        along with the total records count before pagination.
        """
        df = self.data_provider.get_requisitions_df()
        if df.empty:
            return [], 0

        # Apply filters
        df = self._apply_filters(df, scope, employee_id, status, keyword, date_range, requisition_id_list)
        total_count = len(df)
        if total_count == 0:
            return [], 0

        # Sort
        df = self._sort_df(df, sort_field, sort_direction)

        # Slice Page
        start = (page - 1) * page_size
        end = start + page_size
        page_df = df.iloc[start:end]

        return self._df_to_records(page_df), total_count

    def get_latest_requisition(
        self,
        scope: SubjectScope,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        date_range: Optional[DateRange] = None,
        requisition_id_list: Optional[List[str]] = None,
        offset: int = 0,
    ) -> Optional[RequisitionRecord]:
        """Gets the N-th latest requisition based on offset (0 = latest, 1 = previous, etc.)."""
        df = self.data_provider.get_requisitions_df()
        if df.empty:
            return None

        df = self._apply_filters(df, scope, employee_id, status, keyword, date_range, requisition_id_list)
        if df.empty:
            return None

        # Sort latest first
        df = self._sort_df(df, "Created On", "desc")
        if offset >= len(df):
            return None

        target_row = df.iloc[[offset]]
        records = self._df_to_records(target_row)
        return records[0] if records else None

    # ── Analytics Engine Capabilities ─────────────────────────────────────────

    def count_requisitions(
        self,
        scope: SubjectScope,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        date_range: Optional[DateRange] = None,
        requisition_id_list: Optional[List[str]] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Counts requisitions, optionally grouped."""
        df = self.data_provider.get_requisitions_df()
        if df.empty:
            return []

        df = self._apply_filters(df, scope, employee_id, status, keyword, date_range, requisition_id_list)
        if df.empty:
            return []

        if group_by:
            gb_col = self._resolve_column(df, group_by)
            if gb_col:
                grouped = df.groupby(gb_col).size().reset_index(name="count")
                grouped = grouped.rename(columns={gb_col: "group"})
                # Fill missing/NaN group labels
                grouped["group"] = grouped["group"].fillna("N/A").astype(str)
                return grouped.to_dict("records")

        return [{"count": len(df), "label": "Total Count"}]

    def sum_approved_value(
        self,
        scope: SubjectScope,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        date_range: Optional[DateRange] = None,
        requisition_id_list: Optional[List[str]] = None,
    ) -> float:
        """Returns the sum of Approved Value in INR for matched requisitions."""
        df = self.data_provider.get_requisitions_df()
        if df.empty:
            return 0.0

        df = self._apply_filters(df, scope, employee_id, status, keyword, date_range, requisition_id_list)
        if df.empty:
            return 0.0

        col = "Approved Value in INR" if "Approved Value in INR" in df.columns else "Approved Value"
        if col not in df.columns:
            return 0.0

        return float(df[col].sum())

    def aggregate_requisitions(
        self,
        scope: SubjectScope,
        metric: str,
        aggregation: str,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        date_range: Optional[DateRange] = None,
        requisition_id_list: Optional[List[str]] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Runs calculations: SUM, COUNT, AVG, MIN, MAX.
        Optionally groups results by group_by column.
        """
        df = self.data_provider.get_requisitions_df()
        if df.empty:
            return []

        df = self._apply_filters(df, scope, employee_id, status, keyword, date_range, requisition_id_list)
        if df.empty:
            return []

        metric_col = self._resolve_column(df, metric)
        if not metric_col or metric_col not in df.columns:
            metric_col = "Approved Value in INR" if "Approved Value in INR" in df.columns else "Value in INR"

        agg_func = aggregation.lower()
        if agg_func not in ("sum", "count", "avg", "mean", "min", "max"):
            agg_func = "sum"
        if agg_func == "avg":
            agg_func = "mean"

        if group_by:
            gb_col = self._resolve_column(df, group_by)
            if gb_col:
                agg_spec = {
                    "value": (metric_col, agg_func),
                    "count": (metric_col, "count"),
                }
                if gb_col == "employee_name" and "employee_id" in df.columns:
                    agg_spec["employee_id"] = ("employee_id", "first")
                grouped = df.groupby(gb_col).agg(**agg_spec).reset_index()
                grouped = grouped.rename(columns={gb_col: "group"})
                grouped["group"] = grouped["group"].fillna("N/A").astype(str)
                grouped["value"] = grouped["value"].round(2).fillna(0.0)
                return grouped.to_dict("records")
            return []

        # Single aggregate value
        if agg_func == "sum":
            val = df[metric_col].sum()
        elif agg_func == "mean":
            val = df[metric_col].mean()
        elif agg_func == "min":
            val = df[metric_col].min()
        elif agg_func == "max":
            val = df[metric_col].max()
        else:
            val = len(df)

        return [{"value": round(float(val), 2) if not pd.isna(val) else 0.0, "count": len(df)}]

    def get_trend(
        self,
        scope: SubjectScope,
        metric: str,
        group_by: str,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        date_range: Optional[DateRange] = None,
        requisition_id_list: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Returns monthly/quarterly aggregations for trend analysis."""
        df = self.data_provider.get_requisitions_df()
        if df.empty:
            return []

        df = self._apply_filters(df, scope, employee_id, status, keyword, date_range, requisition_id_list)
        if df.empty:
            return []

        metric_col = self._resolve_column(df, metric)
        if not metric_col:
            metric_col = "Approved Value in INR" if "Approved Value in INR" in df.columns else "Value in INR"

        date_col = None
        for col in ["Created On", "Finally Approved On"]:
            if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                date_col = col
                break

        if date_col is None:
            return []

        df_copy = df.copy()
        if group_by == "month_period":
            df_copy["group"] = df_copy[date_col].dt.to_period("M").astype(str)
        elif group_by == "quarter_period":
            df_copy["group"] = df_copy[date_col].dt.to_period("Q").astype(str)
        else:
            df_copy["group"] = df_copy[date_col].dt.to_period("M").astype(str)

        grouped = df_copy.groupby("group").agg(
            value=(metric_col, "sum"),
            count=(metric_col, "count"),
        ).reset_index()
        grouped = grouped.sort_values("group")
        return grouped.to_dict("records")

    # ── Filtering and Sorting Helpers ─────────────────────────────────────────

    def _apply_filters(
        self,
        df: pd.DataFrame,
        scope: SubjectScope,
        employee_id: Optional[str],
        status: Optional[str],
        keyword: Optional[str],
        date_range: Optional[DateRange],
        requisition_id_list: Optional[List[str]],
    ) -> pd.DataFrame:
        """Applies filters sequentially, safely returning a copy of the filtered dataframe."""
        df = df.copy()

        # 1. Scope filter
        if scope == SubjectScope.CURRENT_USER and employee_id:
            mask = df["employee_id"].astype(str).str.strip().str.upper() == employee_id.strip().upper()
            df = df[mask]
        elif scope == SubjectScope.SPECIFIC_EMPLOYEE and employee_id:
            mask = df["employee_id"].astype(str).str.strip().str.upper() == employee_id.strip().upper()
            df = df[mask]

        # 2. Date Range filter
        if date_range and (date_range.start or date_range.end):
            date_col = None
            for col in ["Created On", "Finally Approved On"]:
                if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                    date_col = col
                    break
            if date_col:
                if date_range.start:
                    df = df[df[date_col] >= pd.Timestamp(date_range.start)]
                if date_range.end:
                    df = df[df[date_col] <= pd.Timestamp(date_range.end)]

        # 3. Status filter
        if status:
            status_clean = status.strip().lower()
            if status_clean.startswith("approved_by:"):
                app_by_clean = status_clean.split("approved_by:", 1)[1].strip()
                mask = pd.Series(False, index=df.index)
                for col in ["Approved By", "Status"]:
                    if col in df.columns:
                        mask = mask | df[col].astype(str).str.lower().str.strip().str.contains(app_by_clean, na=False)
                df = df[mask]
            else:
                if "Status" in df.columns:
                    status_lower = df["Status"].astype(str).str.lower().str.strip()
                    df = df[status_lower.str.contains(status_clean, na=False)]

        # 4. Description keyword filter
        if keyword:
            keyword_clean = keyword.strip().lower()
            mask = pd.Series(False, index=df.index)
            for col in ["Requisition Description", "Document Title", "Requisition Description"]:
                if col in df.columns:
                    mask = mask | df[col].astype(str).str.lower().str.contains(keyword_clean, na=False)
            df = df[mask]

        # 5. Requisition ID list filter (for Turn follow-ups)
        if requisition_id_list:
            if "Requisition No" in df.columns:
                df = df[df["Requisition No"].isin(requisition_id_list)]

        return df

    def _sort_df(self, df: pd.DataFrame, sort_field: str, sort_direction: str) -> pd.DataFrame:
        """Sorts dataframe deterministically, using Requisition No as tie-breaker."""
        sort_cols = []
        sort_ascending = []

        col = self._resolve_column(df, sort_field)
        if col and col in df.columns:
            sort_cols.append(col)
            sort_ascending.append(sort_direction.lower() == "asc")

        # Stable tie-breaker
        if "Requisition No" in df.columns and "Requisition No" not in sort_cols:
            sort_cols.append("Requisition No")
            sort_ascending.append(True)

        if sort_cols:
            return df.sort_values(by=sort_cols, ascending=sort_ascending)
        return df

    def _resolve_column(self, df: pd.DataFrame, key: Optional[str]) -> Optional[str]:
        """Resolves raw key to actual DataFrame column name."""
        if not key:
            return None
        if key in df.columns:
            return key
        key_lower = key.strip().lower().replace(" ", "_")
        for col in df.columns:
            if col.lower().replace(" ", "_") == key_lower:
                return col
            # Common matches
            if key_lower in ("value", "requested_value", "value_inr") and col == "Value in INR":
                return col
            if key_lower in ("approved_value", "approved_value_inr") and col == "Approved Value in INR":
                return col
            if key_lower in ("created_on", "created_date") and col == "Created On":
                return col
            if key_lower in ("approved_on", "approved_date", "finally_approved_on") and col == "Finally Approved On":
                return col
        return None

    def _df_to_records(self, df: pd.DataFrame) -> List[RequisitionRecord]:
        """Translates slices of DataFrame into list of RequisitionRecords."""
        records = []
        cols = list(df.columns)
        for idx, row in df.iterrows():
            created_val = row.get("Created On")
            created_str = str(created_val).split("T")[0] if pd.notna(created_val) else ""

            fin_val = row.get("Finally Approved On")
            fin_str = str(fin_val).split("T")[0] if pd.notna(fin_val) else ""

            records.append(
                RequisitionRecord(
                    s_no=int(row.get("S.No.", idx + 1)) if pd.notna(row.get("S.No.")) else (idx + 1),
                    requisition_no=str(row.get("Requisition No", "")).strip(),
                    description=str(row.get("Requisition Description", "")).strip(),
                    document_title=str(row.get("Document Title", "")).strip(),
                    stars_req_no=str(row.get("STARS Req. No.", "")).strip(),
                    requested_by_raw=str(row.get("Requested By", "")).strip(),
                    employee_name=str(row.get("employee_name", "")).strip(),
                    employee_id=str(row.get("employee_id", "")).strip(),
                    operational_unit=str(row.get("Operational Unit Name", "")).strip(),
                    cost_centre=str(row.get("Cost Centre", "")).strip(),
                    department=str(row.get("Department", "")).strip(),
                    created_on=created_str,
                    finally_approved_on=fin_str,
                    currency=str(row.get("Currency", "INR")).strip(),
                    value=self._safe_float(row.get("Value", 0.0)),
                    value_in_inr=self._safe_float(row.get("Value in INR", 0.0)),
                    approved_value=self._safe_float(row.get("Approved Value", 0.0)),
                    approved_value_in_inr=self._safe_float(row.get("Approved Value in INR", 0.0)),
                    hod_approved_value=self._safe_float(row.get("HOD Approved Value", 0.0)),
                    status=str(row.get("Status", "")).strip(),
                    approved_by=str(row.get("Approved By", "")).strip(),
                )
            )
        return records
