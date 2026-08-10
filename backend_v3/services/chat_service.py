"""
Backend V3 — Chat Service Orchestrator
"""
import logging
import time
from typing import Dict, Any

from models.user import CurrentUser
from models.query import QueryPlan, QueryIntent, VerifiedResult, ResponseType
from models.context import ConversationContext

from auth.authorization import AuthorizationService, AuthorizationError
from context.conversation import ConversationManager, ContextResolver
from query.parser import QueryParser
from query.validator import QueryPlanValidator, QueryPlanValidationError
from query.entity_resolver import EntityResolver
from query.query_executor import QueryExecutor
from llm.response_generator import ResponseGenerator

logger = logging.getLogger(__name__)


class ChatService:

    def __init__(
        self,
        query_parser: QueryParser,
        query_validator: QueryPlanValidator,
        authorization_service: AuthorizationService,
        entity_resolver: EntityResolver,
        query_executor: QueryExecutor,
        response_generator: ResponseGenerator,
        conversation_manager: ConversationManager,
    ):
        self.parser = query_parser
        self.validator = query_validator
        self.auth = authorization_service
        self.entity_resolver = entity_resolver
        self.executor = query_executor
        self.response_generator = response_generator
        self.conversation_manager = conversation_manager

    def handle_message(self, message: str, user: CurrentUser, chat_id: str, page: int = 1, page_size: int = 20) -> VerifiedResult:
        """
        Executes the entire orchestrator pipeline:
        1. Context Resolution & Reference resolution
        2. Natural Language Query Plan Parser
        3. Structure Query Validation
        4. Centralized Authorization Gateway
        5. Entity Resolution against Database
        6. Deterministic Repository Execution & Calculations
        7. State updates to session context
        8. Conversational Response Generation
        """
        start_time = time.time()
        logger.info(f"ChatService start [chat_id={chat_id}, user={user.employee_id}]")

        # ── Step 1. Fetch Session Context ─────────────────────────────────────
        context = self.conversation_manager.get_context(chat_id, user)

        try:
            # ── Step 2. Parse Question to QueryPlan ────────────────────────────
            plan = self.parser.parse_query(message, user, page, page_size)

            # ── Step 3. Context & Relative Pronoun Resolution ──────────────────
            context_resolver = ContextResolver()
            context_resolver.resolve_context(message, plan, context, user)

            # ── Step 4. Validate Query Plan Structure ─────────────────────────
            self.validator.validate(plan, user)

            # ── Step 5. Enforce Deterministic Authorization Boundaries ──────────
            self.auth.validate(user, plan)

            # ── Step 6. Resolve Entities (Names / IDs / Exact matches) ────────
            short_circuit = self.entity_resolver.resolve_entities(plan)
            if short_circuit:
                # E.g. Ambiguous name (CLARIFICATION) or missing employee (NO_DATA)
                logger.info(f"EntityResolver short-circuit: {short_circuit.response_type.value}")
                return short_circuit

            # ── Step 7. Execute Query and Analytics ───────────────────────────
            result = self.executor.execute(plan, user)

            # ── Step 8. Update Session Conversation Context ───────────────────
            self._update_context(context, plan, result)

            # ── Step 9. Generate Conversational Response Narration ─────────────
            narration = self.response_generator.generate_response(plan, result)
            result.message = narration

            latency = (time.time() - start_time) * 1000
            logger.info(
                f"ChatService success: intent={plan.intent.value}, response_type={result.response_type.value}, "
                f"latency={latency:.2f}ms, results={result.total or 1}"
            )
            return result

        except AuthorizationError as ae:
            logger.warning(f"Authorization denied for {user.employee_id}: {ae}")
            return VerifiedResult(
                success=True,
                response_type=ResponseType.ERROR,
                message=str(ae),
            )
        except QueryPlanValidationError as qve:
            logger.warning(f"Query plan validation rejected: {qve}")
            return VerifiedResult(
                success=False,
                response_type=ResponseType.ERROR,
                message=f"I couldn't process your query: {qve}",
            )
        except Exception as e:
            logger.error(f"Uncaught pipeline exception: {e}", exc_info=True)
            return VerifiedResult(
                success=False,
                response_type=ResponseType.ERROR,
                message="I encountered an internal error while processing your request.",
            )

    def _update_context(self, context: ConversationContext, plan: QueryPlan, result: VerifiedResult) -> None:
        """Saves turn state into context memory."""
        context.last_question = plan.original_question
        context.last_plan = plan
        context.last_verified_result = result
        context.last_subject_scope = plan.subject_scope
        context.last_target_employee_id = plan.target_employee_id
        context.last_entity = plan.entity
        context.last_filters = dict(plan.filters)

        # Track requisition IDs for follow-ups
        if result.response_type == ResponseType.RECORD_LIST:
            records = result.data.get("records", [])
            req_nos = [r.get("requisition_no") for r in records if r.get("requisition_no")]
            context.full_requisition_ids = req_nos
            context.latest_requisition_ids = req_nos
            # If multiple records, reset active single pointer unless it's only 1 item
            if len(req_nos) == 1:
                context.latest_selection_single = req_nos[0]
            else:
                context.latest_selection_single = None
        elif result.response_type == ResponseType.SINGLE_RECORD:
            rec = result.data.get("record", {})
            req_no = rec.get("requisition_no")
            if req_no:
                context.latest_selection_single = req_no
                if req_no not in context.full_requisition_ids:
                    context.full_requisition_ids.insert(0, req_no)

        context.last_page = plan.page
        context.last_page_size = plan.page_size
