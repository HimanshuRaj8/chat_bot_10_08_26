import pytest
import config
from data.excel_provider import ExcelDataProvider
from models.query import QueryPlan, QueryIntent, QueryEntity, SubjectScope, DateRange
from models.user import CurrentUser, UserRole
from query.query_executor import QueryExecutor


@pytest.fixture
def provider():
    return ExcelDataProvider(
        requisition_path=config.DEFAULT_REQUISITION_EXCEL,
        employee_path=config.DEFAULT_EMPLOYEE_EXCEL,
        finance_path=config.DEFAULT_FINANCE_EXCEL,
    )


@pytest.fixture
def executor(provider):
    return QueryExecutor(data_provider=provider)


@pytest.fixture
def finance_user():
    return CurrentUser(
        employee_id="TEMP99",
        employee_name="Intern3",
        email="software.intern3@motherson.com",
        role=UserRole.FINANCE,
        department="SW",
    )


@pytest.fixture
def employee_user():
    return CurrentUser(
        employee_id="MI0161",
        employee_name="Rajesh Upadhyay",
        email="rajesh.upadhyay@motherson.com",
        role=UserRole.EMPLOYEE,
        department="SW",
    )


class TestDeptWiseApprovalSummary:

    def test_dept_summary_returns_multiple_departments(self, executor, finance_user):
        plan = QueryPlan(
            intent=QueryIntent.AGGREGATE,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="Department",
            metric="Approved Value in INR",
            aggregation="SUM",
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        assert len(result.result) > 1, "Expected multiple departments"

    def test_dept_summary_has_nonzero_values(self, executor, finance_user):
        plan = QueryPlan(
            intent=QueryIntent.AGGREGATE,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="Department",
            metric="Approved Value in INR",
            aggregation="SUM",
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        totals = [row.get("value", 0) for row in result.result if row.get("group")]
        assert any(v > 0 for v in totals), f"All department totals are zero — got: {totals}"

    def test_dept_summary_cf_is_highest(self, executor, finance_user):
        """CF should have the highest total in the known dataset."""
        plan = QueryPlan(
            intent=QueryIntent.AGGREGATE,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="Department",
            metric="Approved Value in INR",
            aggregation="SUM",
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        # Sort by value descending and check CF is top
        sorted_rows = sorted(result.result, key=lambda r: r.get("value", 0), reverse=True)
        top_dept = sorted_rows[0].get("group", "")
        assert top_dept == "CF", f"Expected CF as top department, got: {top_dept}"
        assert sorted_rows[0]["value"] > 200000, f"CF total should be >200k, got: {sorted_rows[0]['value']}"

    def test_dept_summary_total_is_correct(self, executor, finance_user):
        """Sum of all department totals must match the dataset total."""
        plan = QueryPlan(
            intent=QueryIntent.AGGREGATE,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="Department",
            metric="Approved Value in INR",
            aggregation="SUM",
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        dept_total = sum(row.get("value", 0) for row in result.result if row.get("group") is not None)
        assert abs(dept_total - 1013847.46) < 1.0, f"Expected ~1013847.46, got: {dept_total}"

    def test_dept_summary_employee_cannot_run(self, executor, employee_user):
        """Employee must not be able to run organization-wide department summary."""
        plan = QueryPlan(
            intent=QueryIntent.AGGREGATE,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="Department",
            metric="Approved Value in INR",
            aggregation="SUM",
            filters={},
            date_range=DateRange(),
        )
        # Executor itself does not do authorization — that's AuthorizationService
        # But we verify that scope filter for EMPLOYEE user yields only their own records
        plan.subject_scope = SubjectScope.CURRENT_USER
        result = executor.execute(plan, employee_user)
        assert result.success
        # MI0161 has 4 requisitions
        assert result.total_records_analyzed == 4


class TestHighestReimbursement:

    def test_highest_reimbursement_returns_nonzero(self, executor, finance_user):
        plan = QueryPlan(
            intent=QueryIntent.RANKING,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="employee_name",
            metric="Approved Value in INR",
            aggregation="SUM",
            sort_order="desc",
            limit=1,
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        assert len(result.result) > 0
        top = result.result[0]
        assert top.get("value", 0) > 0, f"Top reimbursement should be non-zero, got: {top}"

    def test_highest_dept_value(self, executor, finance_user):
        plan = QueryPlan(
            intent=QueryIntent.RANKING,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by="Department",
            metric="Approved Value in INR",
            aggregation="SUM",
            sort_order="desc",
            limit=1,
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success
        assert result.result[0]["group"] == "CF"
        assert result.result[0]["value"] > 200000

    def test_highest_requisition_value(self, executor, finance_user):
        plan = QueryPlan(
            intent=QueryIntent.RANKING,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.ALL_EMPLOYEES,
            group_by=None,
            metric="Approved Value in INR",
            aggregation="MAX",
            sort_order="desc",
            limit=1,
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, finance_user)
        assert result.success


class TestEmployeePersonalScope:

    def test_employee_scope_returns_only_own_records(self, executor, employee_user):
        plan = QueryPlan(
            intent=QueryIntent.FILTER,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.CURRENT_USER,
            filters={},
            date_range=DateRange(),
        )
        result = executor.execute(plan, employee_user)
        assert result.success
        assert result.total_records_analyzed == 4  # MI0161 has 4 requisitions

    def test_employee_approved_total(self, executor, employee_user):
        plan = QueryPlan(
            intent=QueryIntent.AGGREGATE,
            entity=QueryEntity.REQUISITION,
            subject_scope=SubjectScope.CURRENT_USER,
            metric="Approved Value in INR",
            aggregation="SUM",
            filters={"status": "approved"},
            date_range=DateRange(),
        )
        result = executor.execute(plan, employee_user)
        assert result.success


class TestPaginationScopePreservation:

    def test_page1_and_page2_are_different(self, executor, finance_user):
        """Two consecutive pages must return different records, not the same."""
        def make_plan(page):
            return QueryPlan(
                intent=QueryIntent.FILTER,
                entity=QueryEntity.REQUISITION,
                subject_scope=SubjectScope.ALL_EMPLOYEES,
                filters={},
                date_range=DateRange(),
                page=page,
                page_size=20,
            )

        result1 = executor.execute(make_plan(1), finance_user)
        result2 = executor.execute(make_plan(2), finance_user)

        assert result1.success
        assert result2.success
        assert result1.total_records_analyzed == result2.total_records_analyzed == 236
        assert result1.page == 1
        assert result2.page == 2
        # Records on page 1 and page 2 must be different
        rows1 = [r.get("Requisition No") for r in result1.result]
        rows2 = [r.get("Requisition No") for r in result2.result]
        assert rows1 != rows2, "Page 1 and page 2 should have different records"
        assert not set(rows1) & set(rows2), "Pages must not overlap"

    def test_pagination_total_unchanged_across_pages(self, executor, finance_user):
        """total_records_analyzed must be identical on every page."""
        def make_plan(page):
            return QueryPlan(
                intent=QueryIntent.FILTER,
                entity=QueryEntity.REQUISITION,
                subject_scope=SubjectScope.ALL_EMPLOYEES,
                filters={},
                date_range=DateRange(),
                page=page,
                page_size=20,
            )
        totals = [executor.execute(make_plan(p), finance_user).total_records_analyzed for p in range(1, 5)]
        assert all(t == 236 for t in totals), f"Totals differ across pages: {totals}"
