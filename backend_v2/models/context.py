"""
Backend V2 — ConversationContext Model

Stores structured context for active chat sessions to enable natural
conversational follow-up queries without re-querying raw NL or bypassing authorization.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from models.query import QueryPlan, SubjectScope, QueryEntity


@dataclass
class ConversationContext:
    chat_id: str
    user_id: str                                  # Authenticated employee_id
    user_role: str                                # Role at context creation
    last_plan: Optional[QueryPlan] = None
    last_verified_result: Optional[Any] = None
    last_subject_scope: Optional[SubjectScope] = None
    last_target_employee_id: Optional[str] = None
    last_entity: Optional[QueryEntity] = None
    last_filters: Dict[str, Any] = field(default_factory=dict)
    
    # Context Stack: Full dataset vs latest selection (single/subset)
    full_requisition_ids: List[str] = field(default_factory=list)
    latest_requisition_ids: List[str] = field(default_factory=list)
    latest_selection_single: Optional[str] = None
    
    last_result_records: List[Dict[str, Any]] = field(default_factory=list)
    last_page: int = 1
    last_page_size: int = 20

    @property
    def last_requisition_ids(self) -> List[str]:
        """Backwards compatible property returning latest or full requisition IDs."""
        if self.latest_requisition_ids:
            return self.latest_requisition_ids
        return self.full_requisition_ids
