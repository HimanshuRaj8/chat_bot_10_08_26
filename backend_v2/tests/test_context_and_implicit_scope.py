"""
Backend V2 — Comprehensive Context & Analytical Follow-Up Tests

Verifies:
  1. Implicit CURRENT_USER scope for Employee role without needing explicit 'my'
  2. Security boundaries for explicit organization-wide queries by Employee
  3. Conversational follow-up context preservation and scope inheritance
  4. Analytical follow-up operation resolution (Approver, Date, SUM, COUNT, AVG, MAX, MIN, Comparison)
  5. Multi-turn A -> B -> C -> D context chaining with single ('it') vs plural ('these') reference resolution
  6. Strict distinction between FILTER and RANKING intent classification (e.g. 'show me all requisition of mine')
  7. Turn 1 -> Turn 2 'what were these claims made for?' description/purpose projection follow-up
  8. Recency queries ('my last requisition status', 'latest requisition', 'not all only recent one show me') returning exactly 1 record
"""
import pytest
from models.query import SubjectScope, QueryIntent
from models.user import CurrentUser, UserRole


class TestRecencyAndLatestQueries:

    def test_my_last_requisition_status(self, chat_svc):
        rajesh = CurrentUser(
            employee_name="Rajesh Upadhyay",
            email="rajesh.upadhyay@motherson.com",
            employee_id="MI0161",
            role=UserRole.EMPLOYEE,
            department="SW",
        )
        resp = chat_svc.handle_message("my last requisition status", rajesh, "chat_last_status")
        assert not resp.unauthorized
        assert "most recent requisition" in resp.answer.lower() or "status is" in resp.answer.lower()
        # Should return exactly 1 source pill/record
        assert len(resp.sources) == 1

    def test_my_latest_requisition(self, chat_svc, employee_user):
        resp = chat_svc.handle_message("show my latest requisition", employee_user, "chat_latest")
        assert not resp.unauthorized
        assert len(resp.sources) == 1

    def test_my_most_recent_requisition(self, chat_svc, employee_user):
        resp = chat_svc.handle_message("my most recent requisition", employee_user, "chat_recent")
        assert not resp.unauthorized
        assert len(resp.sources) == 1

    def test_not_all_only_recent_one_show_me(self, chat_svc, employee_user):
        resp = chat_svc.handle_message("not all only recent one show me", employee_user, "chat_only_recent")
        assert not resp.unauthorized
        assert len(resp.sources) == 1

    def test_turn1_filter_turn2_show_only_the_recent_one(self, chat_svc, employee_user):
        chat_id = "chat_followup_recent"
        # Turn 1: returns all requisitions
        resp1 = chat_svc.handle_message("show my requisitions", employee_user, chat_id)
        assert len(resp1.sources) > 1

        # Turn 2: returns only 1 record
        resp2 = chat_svc.handle_message("show only the recent one", employee_user, chat_id)
        assert not resp2.unauthorized
        assert len(resp2.sources) == 1

    def test_which_one_is_latest(self, chat_svc, employee_user):
        chat_id = "chat_which_latest"
        chat_svc.handle_message("show my requisitions", employee_user, chat_id)
        resp2 = chat_svc.handle_message("which one is the latest?", employee_user, chat_id)
        assert not resp2.unauthorized
        assert len(resp2.sources) == 1

    def test_latest_requisition_followed_by_what_was_it_for(self, chat_svc, employee_user):
        chat_id = "chat_latest_chain"
        chat_svc.handle_message("show my latest requisition", employee_user, chat_id)
        resp2 = chat_svc.handle_message("what was it for?", employee_user, chat_id)
        assert not resp2.unauthorized
        assert "purposes" in resp2.answer.lower() or "—" in resp2.answer or "description" in resp2.answer.lower()

    def test_latest_requisition_followed_by_who_approved_it(self, chat_svc, employee_user):
        chat_id = "chat_latest_appr"
        chat_svc.handle_message("show my latest requisition", employee_user, chat_id)
        resp2 = chat_svc.handle_message("who approved it?", employee_user, chat_id)
        assert not resp2.unauthorized

    def test_latest_requisition_followed_by_how_much_was_it(self, chat_svc, employee_user):
        chat_id = "chat_latest_val"
        chat_svc.handle_message("show my latest requisition", employee_user, chat_id)
        resp2 = chat_svc.handle_message("how much was it?", employee_user, chat_id)
        assert not resp2.unauthorized


class TestFilterVsRankingClassification:

    def test_exact_user_bug_query(self, query_planner, chat_svc):
        rajesh = CurrentUser(
            employee_name="Rajesh Upadhyay",
            email="rajesh.upadhyay@motherson.com",
            employee_id="MI0161",
            role=UserRole.EMPLOYEE,
            department="SW",
        )
        plan = query_planner.plan("show me all requisition of mine", rajesh)

        assert plan.intent == QueryIntent.FILTER
        assert plan.intent != QueryIntent.RANKING
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == "MI0161"
        assert plan.aggregation == "NONE"

        resp = chat_svc.handle_message("show me all requisition of mine", rajesh, "chat_rajesh_bug")
        assert not resp.unauthorized
        assert "highest approved reimbursement" not in resp.answer.lower()
        assert len(resp.sources) > 0 or len(resp.user_context) > 0

    def test_turn2_what_were_these_claims_made_for(self, chat_svc):
        rajesh = CurrentUser(
            employee_name="Rajesh Upadhyay",
            email="rajesh.upadhyay@motherson.com",
            employee_id="MI0161",
            role=UserRole.EMPLOYEE,
            department="SW",
        )
        chat_id = "rajesh_turn2_chat"

        # Turn 1
        resp1 = chat_svc.handle_message("show me all requisition of mine", rajesh, chat_id)
        assert not resp1.unauthorized

        # Turn 2: Follow-up purpose query
        resp2 = chat_svc.handle_message("what were these claims made for?", rajesh, chat_id)
        assert not resp2.unauthorized
        assert "purposes" in resp2.answer.lower() or "—" in resp2.answer or "description" in resp2.answer.lower()

    def test_show_my_requisitions_is_filter(self, query_planner, employee_user):
        plan = query_planner.plan("show my requisitions", employee_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.subject_scope == SubjectScope.CURRENT_USER

    def test_show_all_my_requisitions_is_filter(self, query_planner, employee_user):
        plan = query_planner.plan("show all my requisitions", employee_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.subject_scope == SubjectScope.CURRENT_USER

    def test_give_me_all_my_requisitions_is_filter(self, query_planner, employee_user):
        plan = query_planner.plan("give me all my requisitions", employee_user)
        assert plan.intent == QueryIntent.FILTER

    def test_list_my_approved_requisitions_is_filter(self, query_planner, employee_user):
        plan = query_planner.plan("list my approved requisitions", employee_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.filters.get("status") == "approved"

    def test_show_my_pending_requisitions_is_filter(self, query_planner, employee_user):
        plan = query_planner.plan("show my pending requisitions", employee_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.filters.get("status") == "pending"

    def test_explicit_highest_triggers_ranking(self, query_planner, employee_user):
        plan = query_planner.plan("what is my highest approved reimbursement?", employee_user)
        assert plan.intent == QueryIntent.RANKING

    def test_which_has_highest_amount_triggers_ranking(self, query_planner, employee_user):
        plan = query_planner.plan("which of my requisitions has the highest amount?", employee_user)
        assert plan.intent == QueryIntent.RANKING

    def test_what_is_total_approved_amount_triggers_aggregate(self, query_planner, employee_user):
        plan = query_planner.plan("what is my total approved amount?", employee_user)
        assert plan.intent == QueryIntent.AGGREGATE
        assert plan.aggregation == "SUM"

    def test_how_many_requisitions_triggers_count(self, query_planner, employee_user):
        plan = query_planner.plan("how many requisitions do I have?", employee_user)
        assert plan.intent == QueryIntent.COUNT

    def test_show_descriptions_is_filter(self, query_planner, employee_user):
        plan = query_planner.plan("show my requisitions with their descriptions", employee_user)
        assert plan.intent == QueryIntent.FILTER
        assert plan.intent != QueryIntent.RANKING


class TestImplicitEmployeeScope:

    def test_1_employee_show_requisitions_defaults_to_current_user(self, query_planner, employee_user):
        plan = query_planner.plan("show requisitions", employee_user)
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == employee_user.employee_id

    def test_2_employee_show_all_requisitions_defaults_to_current_user(self, query_planner, employee_user):
        plan = query_planner.plan("show all requisitions", employee_user)
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == employee_user.employee_id

    def test_3_employee_summary_of_requisitions_defaults_to_current_user(self, query_planner, employee_user):
        plan = query_planner.plan("give me summary of requisitions", employee_user)
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == employee_user.employee_id

    def test_4_employee_explicit_which_employee_denied(self, chat_svc, employee_user):
        resp = chat_svc.handle_message(
            question="which employee has highest approved value?",
            user=employee_user,
            chat_id="test_chat_1",
        )
        assert resp.unauthorized
        assert "Access denied" in resp.answer

    def test_5_employee_explicit_department_wise_summary_denied(self, chat_svc, employee_user):
        resp = chat_svc.handle_message(
            question="department-wise approval summary",
            user=employee_user,
            chat_id="test_chat_2",
        )
        assert resp.unauthorized
        assert "Access denied" in resp.answer

    def test_6_employee_show_my_approved_requisitions(self, query_planner, employee_user):
        plan = query_planner.plan("show my approved requisitions", employee_user)
        assert plan.subject_scope == SubjectScope.CURRENT_USER
        assert plan.target_employee_id == employee_user.employee_id
        assert plan.filters.get("status") == "approved"


class TestAnalyticalFollowUpEngine:

    def test_1_approver_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_appr")
        resp = chat_svc.handle_message("who approved these?", employee_user, "chat_appr")
        assert not resp.unauthorized
        assert ("approved by" in resp.answer.lower() or "passed official" in resp.answer.lower())

    def test_2_sum_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_sum")
        resp = chat_svc.handle_message("what is the total approved amount?", employee_user, "chat_sum")
        assert not resp.unauthorized
        assert "total" in resp.answer.lower() and "₹" in resp.answer

    def test_3_count_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_cnt")
        resp = chat_svc.handle_message("how many are there?", employee_user, "chat_cnt")
        assert not resp.unauthorized
        assert "requisitions" in resp.answer.lower()

    def test_4_avg_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_avg")
        resp = chat_svc.handle_message("what is the average approved amount?", employee_user, "chat_avg")
        assert not resp.unauthorized
        assert "average" in resp.answer.lower()

    def test_5_max_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_max")
        resp = chat_svc.handle_message("which one is the highest?", employee_user, "chat_max")
        assert not resp.unauthorized
        assert "highest" in resp.answer.lower()

    def test_6_min_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_min")
        resp = chat_svc.handle_message("which one is lowest?", employee_user, "chat_min")
        assert not resp.unauthorized

    def test_7_status_analysis_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_stat")
        resp = chat_svc.handle_message("how many of these are approved?", employee_user, "chat_stat")
        assert not resp.unauthorized
        assert "approved" in resp.answer.lower()

    def test_8_comparison_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_comp")
        resp = chat_svc.handle_message("how much requested vs approved?", employee_user, "chat_comp")
        assert not resp.unauthorized
        assert "requested value" in resp.answer.lower()

    def test_9_description_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_desc")
        resp = chat_svc.handle_message("show their descriptions", employee_user, "chat_desc")
        assert not resp.unauthorized
        assert "purposes" in resp.answer.lower() or "•" in resp.answer

    def test_10_date_followup(self, chat_svc, employee_user):
        chat_svc.handle_message("show requisitions", employee_user, "chat_date")
        resp = chat_svc.handle_message("when were these approved?", employee_user, "chat_date")
        assert not resp.unauthorized
        assert "approved" in resp.answer.lower()

    def test_11_single_item_it_resolution(self, chat_svc, employee_user):
        chat_id = "chat_single_item"
        # Turn 1: List
        chat_svc.handle_message("show requisitions", employee_user, chat_id)
        # Turn 2: MAX (single selection)
        resp2 = chat_svc.handle_message("which one is highest?", employee_user, chat_id)
        assert not resp2.unauthorized

        # Turn 3: Single item reference "it"
        resp3 = chat_svc.handle_message("when was it approved?", employee_user, chat_id)
        assert not resp3.unauthorized

    def test_12_multi_turn_chaining(self, chat_svc, employee_user):
        chat_id = "chat_chain"
        # Turn 1: Filter
        chat_svc.handle_message("show requisitions", employee_user, chat_id)
        # Turn 2: Approver
        chat_svc.handle_message("who approved these?", employee_user, chat_id)
        # Turn 3: Total
        chat_svc.handle_message("what was the total approved amount?", employee_user, chat_id)
        # Turn 4: Requested vs approved
        resp4 = chat_svc.handle_message("how much requested vs approved?", employee_user, chat_id)
        assert not resp4.unauthorized

    def test_13_session_user_isolation(self, chat_svc):
        emp1 = CurrentUser(employee_name="Emp1", email="e1@motherson.com", employee_id="EMP01", role=UserRole.EMPLOYEE, department="SW")
        emp2 = CurrentUser(employee_name="Emp2", email="e2@motherson.com", employee_id="EMP02", role=UserRole.EMPLOYEE, department="SW")

        chat_svc.handle_message("show requisitions", emp1, "shared_chat_id")
        resp2 = chat_svc.handle_message("show requisitions", emp2, "shared_chat_id")
        assert resp2.user_context["employee_id"] == "EMP02"

    def test_14_impersonation_blocked(self, chat_svc, employee_user):
        resp = chat_svc.handle_message("show Rajesh's requisitions", employee_user, "imp_chat")
        if not resp.unauthorized:
            assert resp.user_context["employee_id"] == employee_user.employee_id

    def test_15_finance_followup_inherits_authorized_context(self, chat_svc, finance_user):
        chat_svc.handle_message("show all approved requisitions", finance_user, "fin_chat")
        resp2 = chat_svc.handle_message("who approved these?", finance_user, "fin_chat")
        assert not resp2.unauthorized
