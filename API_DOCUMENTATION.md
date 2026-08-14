# API Specification — Enterprise Approval System AI (Version 3.0)

---

## Base URLs
- **Backend V3 (Production Engine)**: `http://localhost:8002`

---

## 🔑 Authentication & Health Endpoints

### 1. System Health Check
- **HTTP Method**: `GET`
- **Endpoint**: `/health`
- **Response `200 OK`**:
  ```json
  {
    "status": "healthy",
    "version": "3.0.0",
    "ollama_connected": true,
    "active_sessions": 1
  }
  ```

### 2. User Login
Authenticates an employee, finance, or admin user by email address (`@motherson.com`).

- **HTTP Method**: `POST`
- **Endpoint**: `/login`
- **Request Body**:
  ```json
  {
    "email": "rahul.karn@motherson.com"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "success": true,
    "session_token": "session_MI0168_rahul.karn@motherson.com",
    "user": {
      "employee_id": "MI0168",
      "name": "Rahul Karn",
      "email": "rahul.karn@motherson.com",
      "department": "SW",
      "role": "Employee"
    }
  }
  ```

---

## 💬 Chat & Query Endpoints

### 3. Natural Language Query Execution
Executes a natural language query with automatic role authorization, entity resolution, context resolution, and deterministic execution.

- **HTTP Method**: `POST`
- **Endpoint**: `/chat`
- **Request Body**:
  ```json
  {
    "message": "What is the status of my latest requisition?",
    "chat_id": "chat_session_001",
    "session_token": "session_MI0168_rahul.karn@motherson.com",
    "page": 1,
    "page_size": 20
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "success": true,
    "response_type": "SINGLE_RECORD",
    "answer": "Here are the details for requisition **G_212_4992274/2026**:\n\n- **Description**: Phone Bills\n- **Status**: ✅ Finally Approved By Ajay Singh Tomar-( Mi0095 )\n- **Value**: ₹11,000.00\n- **Approved Value**: ₹11,000.00\n- **Approved By**: Ajay Singh Tomar\n- **Created On**: 2026-04-06 00:00:00",
    "sources": [
      {
        "source": "G_212_4992274/2026",
        "requisition_no": "G_212_4992274/2026",
        "employee_id": "MI0168",
        "employee_name": "Rahul Karn",
        "department": "SW",
        "status": "Finally Approved By Ajay Singh Tomar-( Mi0095 )",
        "approved_value_inr": 11000.0,
        "value_inr": 11000.0,
        "description": "Phone Bills",
        "created_on": "2026-04-06 00:00:00",
        "approved_by": ""
      }
    ],
    "unauthorized": false,
    "user_context": {
      "name": "Rahul Karn",
      "email": "rahul.karn@motherson.com",
      "employee_id": "MI0168",
      "role": "Employee",
      "department": "SW"
    },
    "pagination": null
  }
  ```

---

## 📂 Chat Session Management Endpoints

### 4. Create New Chat Session
- **HTTP Method**: `POST`
- **Endpoint**: `/new_chat`
- **Request Headers**: `Authorization: Bearer <session_token>`
- **Response `200 OK`**:
  ```json
  {
    "chat_id": "chat_1786310000000"
  }
  ```

### 5. Fetch User Chat History
- **HTTP Method**: `POST`
- **Endpoint**: `/get_history`
- **Request Headers**: `Authorization: Bearer <session_token>`
- **Response `200 OK`**: Returns user chat sessions dictionary.

### 6. Delete Chat Session
- **HTTP Method**: `POST`
- **Endpoint**: `/delete_chat`
- **Request Body**:
  ```json
  {
    "chat_id": "chat_1786310000000"
  }
  ```

---

## 🛡️ Admin Portal Endpoints

### 7. Admin Login
- **HTTP Method**: `POST`
- **Endpoint**: `/admin_login`
- **Request Body**:
  ```json
  {
    "username": "admin@motherson.com"
  }
  ```

### 8. Fetch Admin System Status
- **HTTP Method**: `GET`
- **Endpoint**: `/admin/status`
- **Response `200 OK`**:
  ```json
  {
    "status": "Online",
    "indexed_records": 236,
    "ollama_url": "http://localhost:11434/api/generate",
    "ollama_model": "qwen2.5:3b",
    "data_provider_type": "excel"
  }
  ```

### 9. Upload Enterprise Excel Datasets
- **HTTP Method**: `POST`
- **Endpoint**: `/admin/upload_excels`
- **Form Data**:
  - `email`: `admin@motherson.com`
  - `requisition_file`: File upload (`.xlsx`)
  - `employee_file`: File upload (`.xlsx`)
  - `finance_file`: File upload (`.xlsx`)
- **Response `200 OK`**:
  ```json
  {
    "success": true,
    "message": "Successfully reloaded dataset. 236 active records loaded."
  }
  ```

---

## 🧠 Claim Period Intelligence Features

Requisition records automatically undergo deterministic claim period extraction on load/refresh. Free-text description fields are parsed to derive structured period metadata.

### 1. Enriched Fields in Source Records
Every requisition record in chat sources contains these derived fields:
- `claim_period_start` (string, `YYYY-MM-DD` or `null`): Start date of the claim period.
- `claim_period_end` (string, `YYYY-MM-DD` or `null`): End date of the claim period.
- `claim_period_text` (string, e.g. `"Mar-2026"`, `"18-Feb-2026 to 03-Apr-2026"`, or `"Not determined"`): Structured display string.
- `claim_months` (array of strings, e.g. `["2026-03"]`): List of all months covered by the claim.
- `period_confidence` (string, `HIGH` | `MEDIUM` | `LOW`): Confidence rating of the extraction.

### 2. Supported Natural Language Analytics
Users can execute the following analytical operations:
- **Timeline Lookup:** `Show my internet reimbursement timeline.` -> Displays chronological list of claims.
- **Period Checks:** `Have I already claimed March internet reimbursement?` -> Checks overlaps in that period.
- **Missing Periods Analysis:** `Am I missing any months for internet?` -> Scans monthly claim continuity.
- **Duplicate Detection (Finance):** `Show duplicate parking claims.` -> Finds identical category claims within the same month.
- **Overlap Checks (Finance):** `Which claims have overlapping periods?` -> Finds date-range overlaps for the same employee and category.

