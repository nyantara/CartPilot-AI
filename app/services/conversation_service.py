import time
from typing import Dict, List, Optional, Any
from threading import Lock

class SessionData:
    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.history: List[Dict[str, str]] = []
        self.last_discussed_product_id: Optional[str] = None
        self.last_discussed_variant: Dict[str, str] = {}
        self.last_intent: Optional[str] = None
        self.last_clarification_question: Optional[str] = None
        self.current_budget: Optional[float] = None

class ConversationService:
    """
    In-memory session storage for multi-turn conversations.
    Thread-safe and context-isolated across different session IDs.
    """
    _sessions: Dict[str, SessionData] = {}
    _lock: Lock = Lock()
    MAX_HISTORY_TURNS: int = 12

    @classmethod
    def get_or_create_session(cls, session_id: str) -> SessionData:
        with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = SessionData(session_id=session_id)
            session = cls._sessions[session_id]
            session.updated_at = time.time()
            return session

    @classmethod
    def add_message(cls, session_id: str, role: str, content: str) -> None:
        """Add a user or assistant message to bounded session history."""
        session = cls.get_or_create_session(session_id)
        with cls._lock:
            session.history.append({"role": role, "content": content})
            session.updated_at = time.time()
            # Keep history bounded to avoid unbounded token accumulation
            if len(session.history) > cls.MAX_HISTORY_TURNS:
                session.history = session.history[-cls.MAX_HISTORY_TURNS:]

    @classmethod
    def get_history(cls, session_id: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Retrieve conversation history for a session."""
        session = cls.get_or_create_session(session_id)
        with cls._lock:
            turns = session.history
            if limit and limit < len(turns):
                return turns[-limit:]
            return list(turns)

    @classmethod
    def update_context(
        cls,
        session_id: str,
        product_id: Optional[str] = None,
        variant: Optional[Dict[str, str]] = None,
        budget: Optional[float] = None,
        intent: Optional[str] = None,
        clarification: Optional[str] = None
    ) -> None:
        """Update recent shopping context to assist follow-up turns."""
        session = cls.get_or_create_session(session_id)
        with cls._lock:
            if product_id:
                session.last_discussed_product_id = product_id
            if variant:
                session.last_discussed_variant.update(variant)
            if budget is not None:
                session.current_budget = budget
            if intent:
                session.last_intent = intent
            session.last_clarification_question = clarification
            session.updated_at = time.time()

    @classmethod
    def get_context(cls, session_id: str) -> Dict[str, Any]:
        """Get contextual memory for a session."""
        session = cls.get_or_create_session(session_id)
        with cls._lock:
            return {
                "session_id": session.session_id,
                "last_discussed_product_id": session.last_discussed_product_id,
                "last_discussed_variant": dict(session.last_discussed_variant),
                "last_intent": session.last_intent,
                "last_clarification_question": session.last_clarification_question,
                "current_budget": session.current_budget,
                "history_length": len(session.history)
            }

    @classmethod
    def clear_session(cls, session_id: str) -> None:
        """Clear memory for a given session."""
        with cls._lock:
            if session_id in cls._sessions:
                del cls._sessions[session_id]

    @classmethod
    def clear_all(cls) -> None:
        """Clear all active sessions (useful for tests)."""
        with cls._lock:
            cls._sessions.clear()

