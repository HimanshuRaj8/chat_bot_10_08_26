"""
Backend V3 — AuthService
"""
import logging
from typing import Optional, Tuple
from models.user import CurrentUser
from .session_store import SessionStore

logger = logging.getLogger(__name__)


class AuthService:
    ALLOWED_DOMAIN = "@motherson.com"

    def __init__(self, data_provider, session_store: SessionStore):
        self.data_provider = data_provider
        self.session_store = session_store

    def authenticate_email(self, email: str) -> Tuple[bool, Optional[CurrentUser], str]:
        """
        Authenticates a user by corporate email.
        Returns (success, CurrentUser, session_token).
        """
        email_clean = email.strip().lower()
        if not email_clean:
            return False, None, "Email address is required."

        if not email_clean.endswith(self.ALLOWED_DOMAIN):
            return False, None, f"Only {self.ALLOWED_DOMAIN} corporate accounts are authorized."

        try:
            user = self.data_provider.get_user_by_email(email_clean)
        except Exception as e:
            logger.error(f"User resolution failed for {email_clean}: {e}")
            return False, None, "Authentication failed: user not found."

        session_token = f"session_{user.employee_id}_{user.email}"
        self.session_store.store(session_token, user)
        logger.info(f"Authenticated: {user.employee_name} ({user.employee_id}) [{user.role.value}]")
        return True, user, session_token

    def verify_entra_token(self, token: str) -> Tuple[bool, Optional[CurrentUser], str]:
        """
        Verifies Microsoft Entra ID token by extracting the email claim.
        """
        try:
            import jwt as pyjwt
            claims = pyjwt.decode(token, options={"verify_signature": False})
            email = (claims.get("preferred_username")
                     or claims.get("upn")
                     or claims.get("email", ""))
            if not email:
                return False, None, "Invalid Entra ID token: no email claim."
            return self.authenticate_email(email)
        except ImportError:
            logger.warning("PyJWT not installed — Entra token verification fallback.")
            return False, None, "Entra ID token verification not configured."
        except Exception as e:
            logger.error(f"Entra token verification error: {e}")
            return False, None, f"Entra ID authentication failed: {e}"

    def get_user_from_session(self, session_token: str) -> Optional[CurrentUser]:
        """
        Returns CurrentUser for session token.
        Dynamically refreshes from data provider to ensure role stays correct after data refresh.
        """
        user = self.session_store.get(session_token)
        if user:
            # Re-fetch to survive dataset refresh role overlay updates
            updated_user = self.data_provider.get_user_by_employee_id(user.employee_id)
            if updated_user:
                self.session_store.store(session_token, updated_user)
                return updated_user
        return user
