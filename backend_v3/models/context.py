"""
Backend V3 — Conversation Context Model
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from models.query import QueryPlan, VerifiedResult


@dataclass
class ConversationContext:
    """
    State representing conversation context, scoped per user session.
    Used to resolve relative pronouns/references.
    """
    chat_id: str
    user_id: str
    user_role: str
    last_question: str = ""
    last_plan: Optional[QueryPlan] = None
    last_verified_result: Optional[VerifiedResult] = None
    last_subject_scope: Optional[Any] = None
    last_target_employee_id: Optional[str] = None
    last_entity: Optional[Any] = None
    last_filters: Dict[str, Any] = field(default_factory=dict)
    
    # Track lists of requisition numbers returned on last turn
    full_requisition_ids: List[str] = field(default_factory=list)
    latest_requisition_ids: List[str] = field(default_factory=list)
    latest_selection_single: Optional[str] = None # holds active requisition_no if resolved to one
    active_employee_id: Optional[str] = None

    last_page: int = 1
    last_page_size: int = 20

    def reset(self) -> None:
        self.last_question = ""
        self.last_plan = None
        self.last_verified_result = None
        self.last_subject_scope = None
        self.last_target_employee_id = None
        self.last_entity = None
        self.last_filters.clear()
        self.full_requisition_ids.clear()
        self.latest_requisition_ids.clear()
        self.latest_selection_single = None
        self.active_employee_id = None
        self.last_page = 1
        self.last_page_size = 20
