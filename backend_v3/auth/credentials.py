import os
import json
import logging
import random
import string
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

def generate_random_password(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

class CredentialsManager:
    def __init__(self, data_file: str, data_provider=None):
        self.data_file = data_file
        self.data_provider = data_provider
        self.credentials: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    self.credentials = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load credentials from {self.data_file}: {e}")
                self.credentials = {}
        else:
            self.credentials = {}
        self.sync_with_provider()

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, "w") as f:
                json.dump(self.credentials, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save credentials to {self.data_file}: {e}")

    def sync_with_provider(self) -> None:
        if not self.data_provider:
            return
        changed = False
        try:
            # Sync default employees
            employees = self.data_provider.get_all_employees()
            for emp in employees.values():
                if emp.email:
                    email_clean = emp.email.strip().lower()
                    if email_clean and email_clean not in self.credentials:
                        self.credentials[email_clean] = "123456"
                        changed = True
            
            # Sync finance table roles
            finance_roles = self.data_provider.get_finance_roles()
            for ident in finance_roles.keys():
                if "@" in ident:
                    email_clean = ident.strip().lower()
                    if email_clean not in self.credentials:
                        self.credentials[email_clean] = "123456"
                        changed = True
            # Force admin@motherson.com to have 123456
            if "admin@motherson.com" in self.credentials and self.credentials["admin@motherson.com"] != "123456":
                self.credentials["admin@motherson.com"] = "123456"
                changed = True
        except Exception as e:
            logger.error(f"Error syncing credentials with Excel provider: {e}")
        
        if changed:
            self.save()

    def verify_password(self, email: str, password: str) -> bool:
        self.sync_with_provider()
        email_clean = email.strip().lower()
        if email_clean not in self.credentials:
            return False
        return self.credentials[email_clean] == password

    def add_user(self, email: str, password: Optional[str] = None) -> str:
        email_clean = email.strip().lower()
        if not password:
            password = generate_random_password()
        self.credentials[email_clean] = password
        self.save()
        return password

    def change_password(self, email: str, password: Optional[str] = None) -> str:
        email_clean = email.strip().lower()
        if email_clean == "admin@motherson.com":
            return "123456"
        if not password:
            password = generate_random_password()
        self.credentials[email_clean] = password
        self.save()
        return password

    def delete_user(self, email: str) -> bool:
        email_clean = email.strip().lower()
        if email_clean in self.credentials:
            del self.credentials[email_clean]
            self.save()
            return True
        return False

    def list_users(self) -> List[Dict[str, str]]:
        self.sync_with_provider()
        return [
            {"email": email, "password": pwd}
            for email, pwd in self.credentials.items()
        ]
