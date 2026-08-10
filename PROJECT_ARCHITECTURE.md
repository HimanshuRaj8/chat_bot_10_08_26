# Project Architecture Blueprint — Enterprise Approval System AI (Version 3.0)

---

## 1. Executive Architecture Summary

Version 3 of the Motherson Enterprise Approval System AI Assistant is built around a **Modular Deterministic Pipeline**. The LLM (Ollama `qwen2.5:3b`) is strictly constrained to natural language parsing and natural language narration. Data access, authorization checks, entity resolution, aggregations, sorting, and pagination are executed 100% deterministically by Python services and pandas data repositories.

$$\text{User Query} \xrightarrow{\text{Auth / Session}} \text{Query Parser} \xrightarrow{\text{Context Resolver}} \text{Validator} \xrightarrow{\text{Authorization}} \text{Entity Resolver} \xrightarrow{\text{Query Executor}} \text{Response Generator} \xrightarrow{\text{Client}}$$

### Core Architectural Principles
1. **Strict Separation of Intent & Execution**: Natural language intent parsing produces a typed `QueryPlan` contract. Execution occurs exclusively against ground-truth DataFrames — no raw database access or calculations are performed by LLMs.
2. **Pre-Retrieval Security Gateway**: Security scope validation (`CURRENT_USER` vs. `ALL_EMPLOYEES`) occurs **before** any repository query is executed.
3. **Multi-Turn Pronoun Context Resolution**: Maintains conversation context to resolve relative pronouns (`"it"`, `"its approved value"`, `"who approved it?"`, `"previous one"`) back to target requisitions.
4. **Dynamic Frontend Origin Binding**: The frontend uses `window.location.origin` to automatically communicate with the backend port serving the page (`port 8002` for V3).
5. **Cross-Platform Readiness**: All file paths use platform-independent `os.path.join` and standard relative imports to run smoothly across **Windows**, **macOS**, and **Linux**.

---

## 2. Component Blueprint

```
                               ┌────────────────────────┐
                               │    HTTP REST API       │  (backend_v3/app.py)
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │      ChatService       │  (Pipeline Orchestrator)
                               └───────────┬────────────┘
                                           │
                ┌──────────────────────────┼──────────────────────────┐
                ▼                          ▼                          ▼
     ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
     │     QueryParser     │    │   ContextResolver   │    │ QueryPlanValidator  │
     │(LLM + Regex Fallback)│    │(Pronouns & History) │    │(Invariants & Bounds)│
     └──────────┬──────────┘    └──────────┬──────────┘    └──────────┬──────────┘
                │                          │                          │
                └──────────────────────────┼──────────────────────────┘
                                           ▼
                               ┌────────────────────────┐
                               │  AuthorizationGateway  │  (Role Scope Enforcement)
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │     EntityResolver     │  (Employee & Req Matcher)
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │     QueryExecutor      │  (Pandas Aggregations)
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │   ResponseGenerator    │  (Markdown & LLM Narration)
                               └────────────────────────┘
```

---

## 3. Module Details

### 3.1 Authentication & Session Store (`backend_v3/auth/`)
- `AuthService`: Authenticates corporate email addresses (`@motherson.com`), resolves roles (`Employee`, `Finance`, `Admin`), and creates secure session tokens.
- `SessionStore`: Thread-safe, in-process session manager tracking active user sessions.

### 3.2 Authorization Gateway (`backend_v3/auth/authorization.py`)
- `AuthorizationService`: Enforces role-based security boundaries.
- **Rule**: `UserRole.EMPLOYEE` users are mandatorily constrained to `SubjectScope.CURRENT_USER` and `target_employee_id == user.employee_id`. Queries attempting to access other employees' data throw an `AuthorizationError`.
- **Rule**: `UserRole.FINANCE` / `ADMIN` users can query `SubjectScope.ALL_EMPLOYEES` or `SubjectScope.SPECIFIC_EMPLOYEE`.

### 3.3 Data Layer & Excel Provider (`backend_v3/data/`)
- `ExcelDataProvider`: Loads and caches DataFrames from `Requisitions.xlsx`, `Employees.xlsx`, and `Finance.xlsx`. Supports atomic `refresh()` when new Excels are uploaded.
- `EmployeeRepository`: Resolves employees by ID, email, or partial name matching.
- `RequisitionRepository`: Provides high-performance pandas data filtering, grouping, date range parsing, trend calculations, sorting, and page slicing.

### 3.4 Query Plan Parser (`backend_v3/query/parser.py`)
- `QueryParser`: Uses Ollama `qwen2.5:3b` with structured JSON output instructions to translate user queries into a `QueryPlan`. Falls back to a deterministic regex parser if offline or if JSON parsing fails.

### 3.5 Context & Reference Resolver (`backend_v3/context/conversation.py`)
- `ContextResolver`: Tracks multi-turn chat context per session.
- Resolves relative pronouns (`"who approved it?"`, `"its description"`, `"previous one"`) by injecting `exact_req_no` or status filters from context memory.

### 3.6 Query Executor (`backend_v3/query/query_executor.py`)
- `QueryExecutor`: Takes a validated and authorized `QueryPlan` and executes deterministic operations against repositories:
  - `GET_REQUISITION`: Single record lookup.
  - `LIST_REQUISITIONS`: Filtered, sorted, paginated record list.
  - `ANALYTICS`: Grouped sum, count, average, max, min metrics or trend analysis.
  - `PROFILE`: User identity queries.
  - `OUT_OF_SCOPE`: Friendly boundary message.

### 3.7 Response Generator (`backend_v3/llm/response_generator.py`)
- `ResponseGenerator`: Converts `VerifiedResult` objects into clean natural language narration and Markdown tables.
- Standard lists and monthly breakdowns automatically render formatted HTML/Markdown tables with status badges (✅ Approved, ⏳ Pending, ❌ Rejected).

---

## 4. Cross-Platform Compatibility Architecture

To guarantee seamless execution on **Windows**, **macOS**, and **Linux**:
1. **Path Normalization**: All file system operations use `os.path.join(BASE_DIR, ...)` rather than hardcoded path strings or forward/backslash concatenations.
2. **Environment Variables**: Port overrides, LLM timeouts, and page size settings use standard `os.environ.get()` defaults.
3. **Encoding Invariants**: Text file operations explicitly use `encoding="utf-8"`.
4. **Dynamic Origin Binding**: Frontend client assets use standard browser `window.location.origin` HTTP resolution, avoiding hardcoded OS localhost ports.

---

## 5. RAG Isolation Strategy

Tabular requisition data and financial aggregations bypass vector store search entirely to eliminate hallucination risk. Structured data is executed strictly via Python/Pandas logic.
