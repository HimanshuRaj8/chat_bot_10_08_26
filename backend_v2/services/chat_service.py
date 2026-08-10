"""
Backend V2 — ChatService (Main Orchestrator)

This is the single entry point for every chat message.
It coordinates all V2 components in strict 14-step pipeline order.

Execution Order per message:
  1. Load dataset (cached in DataProvider)
  2. Determine authenticated user (CurrentUser)
  3. Determine subject_scope & context resolution (QueryPlanner)
  4. Apply authorization (AuthorizationService)
  5. Apply scope filter (QueryExecutor)
  6. Apply status filter
  7. Apply category filter
  8. Apply date filter
  9. Calculate total_records_analyzed & deterministic sorting
  10. Slice page (start:end)
  11. Select page result records
  12. Generate source records from SAME page result
  13. Validate result consistency (ResultConsistencyValidator)
  14. Pass VERIFIED_RESULT to ResponseGenerator

PRINCIPLES:
  - ChatService never reads raw data.
  - ChatService never calls LLM directly.
  - ChatService never bypasses authorization or validation.
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from models.query import QueryIntent, QueryPlan
from models.user import CurrentUser
from models.context import ConversationContext
from query.query_planner import QueryPlanner
from query.query_executor import QueryExecutor
from query.validator import ResultConsistencyValidator, ResultValidationError
from ai.response_generator import ResponseGenerator
from security.authorization import AuthorizationService, AuthorizationError
from services.profile_service import ProfileService
from utils.chat_history import ChatHistoryManager

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    answer: str
    sources: List[Dict[str, Any]]
    unauthorized: bool = False
    user_context: Optional[Dict[str, Any]] = None
    pagination: Optional[Dict[str, Any]] = None
    response_type: str = "SUMMARY"


class ChatService:

    def __init__(
        self,
        query_planner: QueryPlanner,
        query_executor: QueryExecutor,
        response_generator: ResponseGenerator,
        authorization: AuthorizationService,
        profile_service: ProfileService,
        chat_history: ChatHistoryManager,
        validator: Optional[ResultConsistencyValidator] = None,
    ):
        self.planner = query_planner
        self.executor = query_executor
        self.response_gen = response_generator
        self.authorization = authorization
        self.profile_svc = profile_service
        self.chat_history = chat_history
        self.validator = validator or ResultConsistencyValidator()
        self.active_plans: Dict[str, QueryPlan] = {}
        self.conversation_contexts: Dict[str, ConversationContext] = {}

    def handle_message(
        self,
        question: str,
        user: CurrentUser,
        chat_id: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> ChatResponse:
        """
        Main entry point. Processes a user message and returns a ChatResponse.
        """
        user_key = f"{user.employee_id}_{user.email}"
        context_key = f"{user.employee_id}_{chat_id}"
        prev_context = self.conversation_contexts.get(context_key)

        # Security check: ignore stale context if user ID mismatch
        if prev_context and prev_context.user_id != user.employee_id:
            prev_context = None

        # ── Step 1 & 2: Authenticated User & Plan ──────────────────────────────
        plan = self.planner.plan(
            question,
            user,
            page=page,
            page_size=page_size,
            previous_plan=self.active_plans.get(context_key),
            previous_context=prev_context,
        )

        # ── Step 2 Fast-Path: PROFILE Intent ──────────────────────────────────
        if plan.intent == QueryIntent.PROFILE:
            answer = self.profile_svc.answer(plan, user)
            self._log_pipeline_debug(question, user, plan, "AUTHORIZED (PROFILE)", 0, [], [], answer)
            self._persist(user_key, chat_id, question, answer)
            return ChatResponse(
                answer=answer,
                sources=[],
                user_context=user.to_api_dict(),
                pagination=None,
                response_type="SUMMARY",
            )

        # Update active plan
        self.active_plans[context_key] = plan

        # ── Step 3 & 4: Authorization Check ───────────────────────────────────
        try:
            self.authorization.validate(user, plan)
            auth_status = f"AUTHORIZED ({plan.subject_scope.value})"
        except AuthorizationError as e:
            answer = str(e)
            self._log_pipeline_debug(question, user, plan, f"DENIED: {e}", 0, [], [], answer)
            self._persist(user_key, chat_id, question, answer)
            return ChatResponse(
                answer=answer,
                sources=[],
                unauthorized=True,
                user_context=user.to_api_dict(),
                pagination=None,
                response_type="ERROR",
            )

        # ── Step 5 to 12: Query Execution & Pagination ────────────────────────
        verified_result = self.executor.execute(plan, user)

        # ── Step 13: Result Consistency Validation ─────────────────────────────
        try:
            self.validator.validate(verified_result, user, plan)
        except ResultValidationError as e:
            error_msg = f"⚠️ Internal Data Consistency Error: {e}"
            self._log_pipeline_debug(
                question, user, plan, auth_status,
                verified_result.total_records_analyzed,
                verified_result.result, verified_result.source_records,
                error_msg
            )
            return ChatResponse(
                answer=error_msg,
                sources=[],
                unauthorized=False,
                user_context=user.to_api_dict(),
                pagination=None,
                response_type="ERROR",
            )

        # Update ConversationContext with structured execution output
        req_ids = []
        if verified_result.result:
            for r in verified_result.result:
                if isinstance(r, dict) and "Requisition No" in r:
                    req_ids.append(r["Requisition No"])
        if not req_ids and verified_result.source_records:
            for s in verified_result.source_records:
                if isinstance(s, dict) and "source" in s:
                    req_ids.append(s["source"])

        # Determine full_req_ids vs latest_req_ids & single selection
        if prev_context and prev_context.full_requisition_ids and plan.is_follow_up:
            full_ids = prev_context.full_requisition_ids
        elif req_ids:
            full_ids = list(req_ids)
        else:
            full_ids = prev_context.full_requisition_ids if prev_context else []

        latest_ids = list(req_ids) if req_ids else (prev_context.latest_requisition_ids if prev_context else [])
        single_selection = latest_ids[0] if (latest_ids and len(latest_ids) == 1) else (prev_context.latest_selection_single if prev_context else None)

        new_ctx = ConversationContext(
            chat_id=chat_id,
            user_id=user.employee_id,
            user_role=user.role.value,
            last_plan=plan,
            last_verified_result=verified_result,
            last_subject_scope=plan.subject_scope,
            last_target_employee_id=plan.target_employee_id,
            last_entity=plan.entity,
            last_filters=dict(plan.filters),
            full_requisition_ids=full_ids,
            latest_requisition_ids=latest_ids,
            latest_selection_single=single_selection,
            last_result_records=verified_result.result if verified_result.result else [],
            last_page=verified_result.page,
            last_page_size=verified_result.page_size,
        )
        self.conversation_contexts[context_key] = new_ctx

        # ── Step 14: Pass VERIFIED_RESULT to Response Layer ───────────────────
        answer = self.response_gen.generate(verified_result, plan, user)

        # Determine response_type internally
        if plan.intent == QueryIntent.LOOKUP:
            response_type = "SINGLE_RECORD"
        elif plan.intent == QueryIntent.FILTER:
            response_type = "RECORD_LIST"
        else:
            response_type = "SUMMARY"

        # Build pagination metadata dict if total_records > page_size
        pagination_meta = None
        if (
            response_type == "RECORD_LIST"
            and verified_result.total_records_analyzed > verified_result.page_size
        ):
            pagination_meta = {
                "total_records": verified_result.total_records_analyzed,
                "page": verified_result.page,
                "page_size": verified_result.page_size,
                "total_pages": verified_result.total_pages,
                "has_next": verified_result.has_next,
                "has_previous": verified_result.has_previous,
                "returned_records": verified_result.returned_records,
            }

        # Log full pipeline debug context
        self._log_pipeline_debug(
            question, user, plan, auth_status,
            verified_result.total_records_analyzed,
            verified_result.result, verified_result.source_records,
            answer
        )

        # Persist to history and return response
        self._persist(user_key, chat_id, question, answer)
        return ChatResponse(
            answer=answer,
            sources=verified_result.source_records,
            unauthorized=False,
            user_context=user.to_api_dict(),
            pagination=pagination_meta,
            response_type=response_type,
        )

    def _log_pipeline_debug(
        self,
        question: str,
        user: CurrentUser,
        plan: Any,
        auth_status: str,
        filtered_count: int,
        result_data: Any,
        sources: Any,
        final_answer: str,
    ):
        """Debug logger outputting full pipeline state for development inspection."""
        logger.debug(
            f"\n--- [PIPELINE DEBUG TRACE] ---\n"
            f"REQUEST:\n  Question: {question}\n  User: {user.employee_name} ({user.employee_id}) [{user.role.value}]\n"
            f"QUERY PLAN:\n  Intent: {plan.intent.value} | Scope: {plan.subject_scope.value} | Page: {getattr(plan, 'page', 1)}/{getattr(plan, 'page_size', 20)}\n"
            f"AUTHORIZATION:\n  Status: {auth_status}\n"
            f"FILTERED COUNT:\n  {filtered_count}\n"
            f"EXECUTION RESULT:\n  {json.dumps(result_data, default=str)}\n"
            f"SOURCE RECORDS:\n  {json.dumps(sources, default=str)}\n"
            f"FINAL ANSWER:\n  {final_answer[:200]}...\n"
            f"-------------------------------\n"
        )

    def _persist(self, user_key: str, chat_id: str, question: str, answer: str):
        """Saves the Q&A pair to chat history."""
        if chat_id:
            try:
                self.chat_history.add_message(user_key, chat_id, "user", question)
                self.chat_history.add_message(user_key, chat_id, "assistant", answer)
            except Exception as e:
                logger.warning(f"Chat history save failed: {e}")
