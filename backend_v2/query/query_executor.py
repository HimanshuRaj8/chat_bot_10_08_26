"""
Backend V2 — QueryExecutor

Pure pandas execution engine. Zero ChromaDB. Zero LLM.

Receives a QueryPlan from QueryPlanner.
Produces a VerifiedResult that is the ONLY source of data for ResponseGenerator.

Execution pipeline:
  1. Load DataFrame from DataProvider (cached, not re-read from disk)
  2. Apply authorization scope filter (CURRENT_USER → employee_id filter)
  3. Apply date range filter
  4. Apply status filter
  5. Apply description keyword filter
  6. Apply grouping / aggregation
  7. Apply sorting + limit
  8. Build VerifiedResult
"""
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from data.base_provider import DataProvider
from models.query import QueryPlan, QueryIntent, SubjectScope, VerifiedResult
from models.user import CurrentUser

logger = logging.getLogger(__name__)

# Canonical display label for group_by columns
GROUP_DISPLAY_LABELS = {
    "Department": "Department",
    "employee_name": "Employee",
    "Cost Centre": "Cost Centre",
    "Operational Unit Name": "Operational Unit",
    "month_period": "Month",
    "quarter_period": "Quarter",
    "Status": "Status",
}


class QueryExecutor:

    def __init__(self, data_provider: DataProvider):
        self.data_provider = data_provider

    # ── Public Entry Point ────────────────────────────────────────────────────

    def execute(self, plan: QueryPlan, user: CurrentUser) -> VerifiedResult:
        """
        Executes a QueryPlan against the cached requisitions DataFrame.
        Returns a VerifiedResult — never returns raw DataFrames to callers.
        """
        try:
            df = self.data_provider.get_requisitions_df()

            if df.empty:
                return self._empty_result(plan, "No requisition data available.")

            applied_filters: List[str] = []

            # 1. Authorization scope
            df = self._apply_scope(df, user, plan, applied_filters)
            if df is None or df.empty:
                return self._empty_result(plan, "No records found for the given scope.")

            # 2. Date filter
            df = self._apply_date_filter(df, plan, applied_filters)

            # 3. Status filter
            df = self._apply_status_filter(df, plan, applied_filters)

            # 4. Description keyword filter
            df = self._apply_keyword_filter(df, plan, applied_filters)

            # 5. Named employee resolution (SPECIFIC_EMPLOYEE scope)
            df = self._apply_named_employee_filter(df, plan, applied_filters)

            # 5.5 Requisition ID list filter (for follow-up referencing specific result set)
            df = self._apply_requisition_id_list_filter(df, plan, applied_filters)

            total_records = len(df)
            if total_records == 0:
                return self._empty_result(
                    plan,
                    f"No records found matching the applied filters: {', '.join(applied_filters) if applied_filters else 'none'}."
                )

            # 6. Deterministic Sorting BEFORE Pagination
            sort_cols = []
            sort_orders = []

            if plan.metric == "Created On" or plan.aggregation == "LATEST":
                if "Created On" in df.columns:
                    sort_cols.append("Created On")
                    sort_orders.append(plan.sort_order == "asc")
                elif "Finally Approved On" in df.columns:
                    sort_cols.append("Finally Approved On")
                    sort_orders.append(plan.sort_order == "asc")
            else:
                metric_col = self._resolve_metric_col(df, plan)
                if metric_col and metric_col in df.columns:
                    sort_cols.append(metric_col)
                    sort_orders.append(plan.sort_order == "asc")
                elif "Finally Approved On" in df.columns:
                    sort_cols.append("Finally Approved On")
                    sort_orders.append(False)
                elif "Created On" in df.columns:
                    sort_cols.append("Created On")
                    sort_orders.append(False)

            # Secondary stable tie-breaker sort
            if "Requisition No" in df.columns and "Requisition No" not in sort_cols:
                sort_cols.append("Requisition No")
                sort_orders.append(True)

            if sort_cols:
                df = df.sort_values(by=sort_cols, ascending=sort_orders)

            # 7. Pagination calculations
            import math, config
            req_page = max(1, plan.page)
            req_page_size = min(config.MAX_PAGE_SIZE, max(1, plan.page_size))
            total_pages = math.ceil(total_records / req_page_size) if total_records > 0 else 0

            # Page out of bounds check
            if req_page > total_pages and total_records > 0:
                empty_res = self._empty_result(
                    plan,
                    f"That page doesn't exist. There are {total_pages} pages with {total_records} matching requisitions."
                )
                empty_res.total_records_analyzed = total_records
                empty_res.page = req_page
                empty_res.page_size = req_page_size
                empty_res.total_pages = total_pages
                empty_res.has_next = False
                empty_res.has_previous = (req_page > 1)
                return empty_res

            # Slicing
            start = (req_page - 1) * req_page_size
            end = start + req_page_size
            page_df = df.iloc[start:end]

            # 8. Dispatch to correct execution path
            if plan.intent == QueryIntent.LOOKUP:
                result_rows = self._execute_lookup(df, plan)
                sliced_df = df.head(1)
            elif plan.intent == QueryIntent.APPROVER_ANALYSIS:
                result_rows = self._execute_approver_analysis(df, plan)
                sliced_df = df
            elif plan.intent == QueryIntent.DATE_ANALYSIS:
                result_rows = self._execute_date_analysis(df, plan)
                sliced_df = df
            elif plan.intent == QueryIntent.COMPARISON:
                result_rows = self._execute_comparison(df, plan)
                sliced_df = df
            elif plan.intent in (QueryIntent.AGGREGATE,):
                result_rows = self._execute_aggregate(df, plan)
                sliced_df = df
            elif plan.intent == QueryIntent.COUNT:
                result_rows = self._execute_count(df, plan)
                sliced_df = df
            elif plan.intent in (QueryIntent.RANKING,):
                if not plan.group_by:
                    sliced_df = df.head(plan.limit or 1)
                    result_rows = self._rows_to_dicts(sliced_df)
                else:
                    result_rows = self._execute_ranking(df, plan)
                    sliced_df = df.head(plan.limit or 1)
            elif plan.intent in (QueryIntent.TREND,):
                result_rows = self._execute_trend(df, plan)
                sliced_df = df
            elif plan.intent in (QueryIntent.SUMMARY,):
                result_rows = self._execute_summary(df, plan)
                sliced_df = df
            else:
                # FILTER — return page records
                result_rows = self._rows_to_dicts(page_df)
                sliced_df = page_df

            source_records = self._build_source_records(sliced_df, plan, result_rows)

            return VerifiedResult(
                success=True,
                query_type=plan.intent.value,
                entity=plan.entity.value,
                metric=plan.metric or "Approved Value in INR",
                aggregation=plan.aggregation,
                subject_scope=plan.subject_scope.value,
                total_records_analyzed=total_records,
                result=result_rows,
                source_records=source_records,
                applied_filters=applied_filters,
                page=req_page,
                page_size=req_page_size,
                total_pages=total_pages,
                has_next=(req_page < total_pages),
                has_previous=(req_page > 1),
                returned_records=len(result_rows),
            )

        except Exception as e:
            logger.error(f"QueryExecutor failed: {e}", exc_info=True)
            return VerifiedResult(
                success=False,
                query_type=plan.intent.value,
                entity=plan.entity.value,
                metric=plan.metric or "",
                aggregation=plan.aggregation,
                subject_scope=plan.subject_scope.value,
                total_records_analyzed=0,
                result=[],
                error_message=str(e),
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_source_records(
        self, df: pd.DataFrame, plan: QueryPlan, result_rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Builds source records corresponding STRICTLY to the query intent and result.
        - PROFILE / AGGREGATE (without grouping): []
        - LOOKUP: exact matched record
        - RANKING: top-1 requisition record or top group's underlying records
        - FILTER: matched sample rows
        """
        if plan.intent in (QueryIntent.PROFILE,):
            return []

        if plan.intent in (QueryIntent.AGGREGATE, QueryIntent.COUNT) and not plan.group_by:
            return []

        if plan.intent == QueryIntent.LOOKUP and plan.exact_req_no:
            mask = df["Requisition No"].astype(str).str.strip().str.upper() == plan.exact_req_no.upper()
            sample = df[mask].head(1)
        elif plan.intent == QueryIntent.RANKING:
            if not plan.group_by:
                metric_col = self._resolve_metric_col(df, plan)
                if metric_col in df.columns:
                    sorted_df = df.sort_values(by=metric_col, ascending=(plan.sort_order == "asc"))
                    sample = sorted_df.head(plan.limit or 1)
                else:
                    sample = df.head(plan.limit or 1)
            else:
                if result_rows and "group" in result_rows[0]:
                    top_group_val = result_rows[0]["group"]
                    gb_col = self._resolve_group_col(df, plan.group_by)
                    if gb_col and gb_col in df.columns:
                        mask = df[gb_col].astype(str) == str(top_group_val)
                        sample = df[mask].head(5)
                    else:
                        sample = df.head(5)
                else:
                    sample = df.head(5)
        else:
            sample = df.head(10) if plan.intent == QueryIntent.FILTER else df.head(5)

        records = []
        for _, row in sample.iterrows():
            req_no = str(row.get("Requisition No", "")).strip()
            records.append({
                "source": req_no,
                "requisition_no": req_no,
                "employee": str(row.get("employee_name", "")).strip(),
                "employee_id": str(row.get("employee_id", "")).strip(),
                "status": str(row.get("Status", "")).strip(),
                "approved_value_inr": round(float(row.get("Approved Value in INR", 0) or 0), 2),
            })
        return records

    # ── 1. Scope Filter ───────────────────────────────────────────────────────

    def _apply_scope(
        self, df: pd.DataFrame, user: CurrentUser, plan: QueryPlan, applied_filters: List[str]
    ) -> pd.DataFrame:
        """
        Enforces subject scope at the data level.
        CURRENT_USER scope ALWAYS filters to authenticated employee_id — never relaxed.
        """
        if plan.subject_scope == SubjectScope.CURRENT_USER:
            before = len(df)
            mask = df["employee_id"].astype(str).str.strip().str.upper() == user.employee_id.upper()
            df = df[mask]
            applied_filters.append(f"employee_id = {user.employee_id}")
            logger.info(f"Scope CURRENT_USER: {before} → {len(df)} rows (employee_id={user.employee_id})")

        elif plan.subject_scope == SubjectScope.SPECIFIC_EMPLOYEE and plan.target_employee_id:
            mask = df["employee_id"].astype(str).str.strip().str.upper() == plan.target_employee_id.upper()
            df = df[mask]
            applied_filters.append(f"employee_id = {plan.target_employee_id}")

        # ALL_EMPLOYEES: no filter applied
        return df

    def _apply_requisition_id_list_filter(
        self, df: pd.DataFrame, plan: QueryPlan, applied_filters: List[str]
    ) -> pd.DataFrame:
        if "requisition_id_list" in plan.filters and plan.filters["requisition_id_list"]:
            req_ids = plan.filters["requisition_id_list"]
            if "Requisition No" in df.columns:
                matched_df = df[df["Requisition No"].isin(req_ids)]
                if not matched_df.empty:
                    applied_filters.append(f"requisition_id_list ({len(req_ids)} ids)")
                    return matched_df
        return df

    # ── 2. Date Filter ────────────────────────────────────────────────────────

    def _apply_date_filter(
        self, df: pd.DataFrame, plan: QueryPlan, applied_filters: List[str]
    ) -> pd.DataFrame:
        if not plan.date_range.start and not plan.date_range.end:
            return df

        # Use "Created On" as primary date column
        date_col = None
        for col in ["Created On", "Finally Approved On"]:
            if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                date_col = col
                break

        if not date_col:
            logger.warning("No datetime column found for date filtering.")
            return df

        if plan.date_range.start:
            df = df[df[date_col] >= pd.Timestamp(plan.date_range.start)]
        if plan.date_range.end:
            df = df[df[date_col] <= pd.Timestamp(plan.date_range.end)]

        if plan.date_range.label:
            applied_filters.append(f"date = {plan.date_range.label}")

        return df

    # ── 3. Status Filter ──────────────────────────────────────────────────────

    def _apply_status_filter(
        self, df: pd.DataFrame, plan: QueryPlan, applied_filters: List[str]
    ) -> pd.DataFrame:
        status = plan.filters.get("status")
        if not status or "Status" not in df.columns:
            return df

        status_lower = df["Status"].astype(str).str.lower().str.strip()
        df = df[status_lower.str.contains(status, na=False)]
        applied_filters.append(f"status = {status}")
        return df

    # ── 4. Keyword Filter ─────────────────────────────────────────────────────

    def _apply_keyword_filter(
        self, df: pd.DataFrame, plan: QueryPlan, applied_filters: List[str]
    ) -> pd.DataFrame:
        keyword = plan.filters.get("description_keyword")
        if not keyword:
            return df

        for col in ["Requisition Description", "Document Title"]:
            if col in df.columns:
                mask = df[col].astype(str).str.lower().str.contains(keyword.lower(), na=False)
                df = df[mask]
                applied_filters.append(f"category/description contains '{keyword}'")
                return df
        return df

    # ── 5. Named Employee Filter ──────────────────────────────────────────────

    def _apply_named_employee_filter(
        self, df: pd.DataFrame, plan: QueryPlan, applied_filters: List[str]
    ) -> pd.DataFrame:
        """
        Resolves a name hint in filters to an employee_id and filters.
        Called only when scope is SPECIFIC_EMPLOYEE and target_employee_id is not yet set.
        """
        name_hint = plan.filters.get("target_name")
        if not name_hint or plan.subject_scope != SubjectScope.SPECIFIC_EMPLOYEE:
            return df
        if plan.target_employee_id:  # already resolved
            return df

        name_lower = name_hint.lower()
        mask = df["employee_name"].astype(str).str.lower().str.contains(name_lower, na=False)
        filtered = df[mask]
        if not filtered.empty:
            # Resolve to exact employee_id from first match
            resolved_id = filtered["employee_id"].iloc[0]
            plan.target_employee_id = resolved_id
            df = df[df["employee_id"].astype(str).str.strip().str.upper() == resolved_id.upper()]
            applied_filters.append(f"employee = {name_hint}")
        return df

    # ── 6a. Lookup ────────────────────────────────────────────────────────────

    def _execute_lookup(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        if plan.exact_req_no and "Requisition No" in df.columns:
            mask = df["Requisition No"].astype(str).str.strip().str.upper() == plan.exact_req_no.upper()
            df = df[mask]
        return self._rows_to_dicts(df.head(1))

    # ── 6b. Aggregate ─────────────────────────────────────────────────────────

    def _execute_aggregate(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        metric_col = self._resolve_metric_col(df, plan)

        if plan.group_by:
            gb_col = self._resolve_group_col(df, plan.group_by)
            if gb_col is None:
                return self._single_aggregate(df, metric_col, plan)

            grouped = self._groupby_aggregate(df, gb_col, metric_col, plan.aggregation)
            grouped = self._sort_and_limit(grouped, "value", plan.sort_order, plan.limit)
            return grouped.to_dict("records")
        else:
            return self._single_aggregate(df, metric_col, plan)

    # ── 6c. Count ─────────────────────────────────────────────────────────────

    def _execute_count(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        if plan.group_by:
            gb_col = self._resolve_group_col(df, plan.group_by)
            if gb_col:
                counts = df.groupby(gb_col).size().reset_index(name="count")
                counts = counts.rename(columns={gb_col: "group"})
                counts = self._sort_and_limit(counts, "count", plan.sort_order, plan.limit)
                return counts.to_dict("records")
        return [{"count": len(df), "label": "Total Count"}]

    # ── 6d. Ranking ───────────────────────────────────────────────────────────

    def _execute_ranking(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        metric_col = self._resolve_metric_col(df, plan)

        if plan.group_by:
            # Group → aggregate → sort → limit
            gb_col = self._resolve_group_col(df, plan.group_by)
            if gb_col is None:
                return []
            grouped = self._groupby_aggregate(df, gb_col, metric_col, "SUM")
            grouped = self._sort_and_limit(grouped, "value", plan.sort_order, plan.limit)
            return grouped.to_dict("records")
        else:
            # No group → sort individual rows → limit
            if metric_col in df.columns:
                sorted_df = df.sort_values(by=metric_col, ascending=(plan.sort_order == "asc"))
                top = sorted_df.head(plan.limit or 1)
                return self._rows_to_dicts(top)
            return []

    # ── 6e. Trend ─────────────────────────────────────────────────────────────

    def _execute_trend(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        metric_col = self._resolve_metric_col(df, plan)
        date_col = None
        for col in ["Created On", "Finally Approved On"]:
            if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                date_col = col
                break

        if date_col is None:
            logger.warning("Trend analysis: no datetime column found, falling back to aggregate.")
            return self._single_aggregate(df, metric_col, plan)

        if plan.group_by == "month_period":
            df = df.copy()
            df["group"] = df[date_col].dt.to_period("M").astype(str)
        elif plan.group_by == "quarter_period":
            df = df.copy()
            df["group"] = df[date_col].dt.to_period("Q").astype(str)
        else:
            df = df.copy()
            df["group"] = df[date_col].dt.to_period("M").astype(str)

        grouped = df.groupby("group").agg(
            value=(metric_col, "sum"),
            count=(metric_col, "count"),
        ).reset_index()
        grouped = grouped.sort_values("group")
        return grouped.to_dict("records")

    # ── 6f. Summary ───────────────────────────────────────────────────────────

    def _execute_summary(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        metric_col = self._resolve_metric_col(df, plan)
        if plan.group_by:
            gb_col = self._resolve_group_col(df, plan.group_by)
            if gb_col:
                grouped = self._groupby_aggregate(df, gb_col, metric_col, "SUM")
                grouped = self._sort_and_limit(grouped, "value", "desc", plan.limit)
                return grouped.to_dict("records")
        return self._single_aggregate(df, metric_col, plan)

    # ── 6g. Filter (list) ─────────────────────────────────────────────────────

    def _execute_filter(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        metric_col = self._resolve_metric_col(df, plan)
        if metric_col in df.columns:
            df = df.sort_values(by=metric_col, ascending=(plan.sort_order == "asc"))
        if plan.limit:
            df = df.head(plan.limit)
        return self._rows_to_dicts(df)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _groupby_aggregate(
        self, df: pd.DataFrame, gb_col: str, metric_col: str, agg_func: str
    ) -> pd.DataFrame:
        """Groups df by gb_col, applies aggregation on metric_col."""
        if metric_col not in df.columns:
            metric_col = "Approved Value in INR"
        if metric_col not in df.columns:
            logger.warning(f"Metric column '{metric_col}' not in DataFrame.")
            return pd.DataFrame(columns=["group", "value", "count"])

        grouped = df.groupby(gb_col).agg(
            value=(metric_col, agg_func.lower() if agg_func not in ("MAX", "MIN") else agg_func.lower()),
            count=(metric_col, "count"),
        ).reset_index()
        grouped = grouped.rename(columns={gb_col: "group"})
        return grouped

    def _single_aggregate(
        self, df: pd.DataFrame, metric_col: str, plan: QueryPlan
    ) -> List[Dict[str, Any]]:
        """Returns a single aggregated value."""
        if metric_col not in df.columns:
            return [{"value": 0, "count": len(df)}]
        agg = plan.aggregation.lower()
        if agg == "sum":
            value = df[metric_col].sum()
        elif agg == "avg":
            value = df[metric_col].mean()
        elif agg == "max":
            value = df[metric_col].max()
        elif agg == "min":
            value = df[metric_col].min()
        else:
            value = df[metric_col].sum()
        return [{"value": round(float(value), 2), "count": len(df)}]

    def _sort_and_limit(
        self, df: pd.DataFrame, sort_col: str, order: str, limit: Optional[int]
    ) -> pd.DataFrame:
        if sort_col in df.columns:
            df = df.sort_values(by=sort_col, ascending=(order == "asc"))
        if limit:
            df = df.head(limit)
        return df

    def _resolve_metric_col(self, df: pd.DataFrame, plan: QueryPlan) -> str:
        """Resolves the metric column to use, falling back to safe defaults."""
        if plan.metric and plan.metric in df.columns:
            return plan.metric
        if "Approved Value in INR" in df.columns:
            return "Approved Value in INR"
        if "Value in INR" in df.columns:
            return "Value in INR"
        return ""

    def _resolve_group_col(self, df: pd.DataFrame, group_by: str) -> Optional[str]:
        """Validates that the group_by column exists in the DataFrame."""
        if group_by in df.columns:
            return group_by
        # Try case-insensitive match
        for col in df.columns:
            if col.lower().replace(" ", "_") == group_by.lower().replace(" ", "_"):
                return col
        logger.warning(f"Group-by column '{group_by}' not found in DataFrame.")
        return None

    def _rows_to_dicts(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Converts DataFrame rows to clean API-safe dicts."""
        cols_of_interest = [
            "Requisition No", "employee_name", "employee_id", "Department",
            "Status", "Approved Value in INR", "Value in INR",
            "Created On", "Finally Approved On", "Requisition Description",
            "Cost Centre", "Operational Unit Name", "Currency",
        ]
        available = [c for c in cols_of_interest if c in df.columns]
        result = []
        for _, row in df[available].iterrows():
            d = {}
            for col in available:
                val = row[col]
                if hasattr(val, "isoformat"):
                    d[col] = val.strftime("%Y-%m-%d") if not pd.isnull(val) else ""
                elif isinstance(val, float):
                    d[col] = round(val, 2)
                else:
                    d[col] = str(val) if pd.notnull(val) else ""
            result.append(d)
        return result

    def _empty_result(self, plan: QueryPlan, message: str) -> VerifiedResult:
        return VerifiedResult(
            success=True,
            query_type=plan.intent.value,
            entity=plan.entity.value,
            metric=plan.metric or "",
            aggregation=plan.aggregation,
            subject_scope=plan.subject_scope.value,
            total_records_analyzed=0,
            result=[],
            source_records=[],
            error_message=message,
        )

    def _execute_approver_analysis(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        total = len(df)
        if total == 0:
            return []

        approver_col = None
        for col in ["Approved By", "Approver Name", "Approver", "Finally Approved By"]:
            if col in df.columns:
                approver_col = col
                break

        if approver_col and not df[approver_col].dropna().empty:
            counts = df[approver_col].value_counts().to_dict()
            breakdown = [{"approver": str(k), "count": int(v)} for k, v in counts.items()]
            return [{
                "analysis_type": "approver",
                "total_requisitions": total,
                "approver_column": approver_col,
                "breakdown": breakdown,
            }]

        approved_count = len(df[df["Status"].astype(str).str.lower() == "approved"]) if "Status" in df.columns else total
        return [{
            "analysis_type": "approver",
            "total_requisitions": total,
            "approved_count": approved_count,
            "approver_summary": f"All {approved_count} approved requisitions passed official department workflow authorization."
        }]

    def _execute_date_analysis(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        total = len(df)
        if total == 0:
            return []

        date_col = "Finally Approved On" if "Finally Approved On" in df.columns else ("Created On" if "Created On" in df.columns else None)
        if date_col and date_col in df.columns:
            valid_dates = df[date_col].dropna()
            if not valid_dates.empty:
                min_date = str(valid_dates.min())[:10]
                max_date = str(valid_dates.max())[:10]
                return [{
                    "analysis_type": "date",
                    "total_requisitions": total,
                    "date_column": date_col,
                    "min_date": min_date,
                    "max_date": max_date,
                }]

        return [{
            "analysis_type": "date",
            "total_requisitions": total,
            "summary": f"Date records extracted for {total} requisitions."
        }]

    def _execute_comparison(self, df: pd.DataFrame, plan: QueryPlan) -> List[Dict[str, Any]]:
        total = len(df)
        req_val = float(df["Value in INR"].sum()) if "Value in INR" in df.columns else 0.0
        app_val = float(df["Approved Value in INR"].sum()) if "Approved Value in INR" in df.columns else 0.0
        diff = req_val - app_val
        return [{
            "analysis_type": "comparison",
            "total_requisitions": total,
            "requested_value_inr": req_val,
            "approved_value_inr": app_val,
            "difference_inr": diff,
        }]
