# Security & Compliance Model — Enterprise Approval System AI

---

## 🛡️ Security Overview

The Enterprise Approval System AI Assistant enforces enterprise-grade security invariants across authentication, authorization, session management, data privacy, and secret isolation.

---

## 🔐 Key Security Invariants

### 1. Server-Side Authorization Gateway
- Authorization checks are performed **server-side** by `AuthorizationService` inside the Flask core pipeline.
- The client frontend is never trusted for identity or permission scope decisions.
- Attempts by an `Employee` user to query `ALL_EMPLOYEES` or another employee's records are rejected immediately with:
  `🔒 Access denied. You are not authorized to query another employee's requisitions.`

### 2. Session Token Architecture
- Authenticated sessions generate secure tokens in format: `session_<employee_id>_<email>`.
- The token is mapped in-memory to an immutable `CurrentUser` object inside `SessionStore`.
- Requests without a valid token or session map to unauthorized responses (`401 Unauthorized`).
- Supports JWT Bearer token validation for Microsoft Entra ID (Azure AD) Single Sign-On (SSO).

### 3. LLM Authorization Isolation
- **The LLM does NOT determine authorization.**
- Query intent, entity detection, subject scope, and authorization validation are executed **before** the LLM is invoked.
- The LLM only receives pre-filtered, verified result DataFrames (`VerifiedResult`). Prompt injection cannot leak unauthorized records.

### 4. Ground-Truth Invariant Validation
- `QueryPlanValidator` & `AuthorizationService` validate every query plan before database execution:
  - Validates that every record query for an `Employee` user is strictly restricted to `user.employee_id`.
  - Rejects target employee ID mismatches.

### 5. Data Privacy & Git Secret Isolation
- Real enterprise Excel spreadsheets (`.xlsx`, `.csv`), credentials, local logs, vector databases (`chromadb_store/`), uploaded datasets (`uploads/`), and chat histories (`chat_history.json`) are strictly excluded via `.gitignore`.
- No API keys, passwords, or production secrets are hardcoded in source code. Configuration templates are provided via `.env.example`.

---

## 🔍 Security Audit Verification

The codebase has undergone automated secret scans and security invariant test suite verification for Backend V3:

```bash
# Backend V3 Authorization & Role Suite
.venv/bin/python -m pytest backend_v3/tests/test_authorization.py backend_v3/tests/test_auth_and_roles.py -v
```

**Verified Authorization Invariants**: `ALL PASSED`
- `test_employee_scope_is_forced` PASSED
- `test_employee_cannot_query_another_employee_by_id` PASSED
- `test_employee_cannot_query_another_employee_by_name` PASSED
- `test_finance_can_query_specific_employee` PASSED
- `test_finance_can_query_all_employees` PASSED
