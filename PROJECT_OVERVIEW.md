# Project Overview — Enterprise Approval System AI Assistant (Version 3.0)

---

## 📌 Executive Summary

The **Enterprise Approval System AI Assistant** is a role-aware, production-grade AI assistant designed to streamline approval workflows, financial analytics, and requisition tracking across enterprise organizations. 

**Version 3.0** introduces a modular, decoupled architecture where data security, entity resolution, aggregations, context memory, and page slicing are executed deterministically by dedicated Python services, while Ollama (`qwen2.5:3b`) powers natural language query parsing and conversational presentation.

---

## 🔑 Key Objectives

1. **Zero Hallucination Financial Accuracy**: All sums, counts, averages, and rankings are calculated deterministically via Python repositories — LLMs never perform financial math or direct raw data retrieval.
2. **Server-Side Role-Based Authorization (RBAC)**: Enforces strict data isolation. Employee roles are constrained to `CURRENT_USER` data, whereas Finance administrators have organization-wide analytical scope.
3. **Conversational Multi-Turn Context**: Supports natural relative pronoun resolution (`"who approved it?"`, `"its requested value"`, `"previous one"`).
4. **Cross-Platform Compatibility**: Fully tested and optimized to run out-of-the-box on **Windows**, **macOS**, and **Linux**.
5. **Pluggable Data Engine**: `ExcelDataProvider` (default) with seamless extension points for enterprise REST API integration.

---

## 🎯 User Roles & Experience

### 👤 Employee Role (`rahul.karn@motherson.com`)
- **Focus**: Personal claims, status tracking, reimbursements, profile info.
- **Sample Queries**:
  - *"What is my employee ID?"*
  - *"What is the status of my latest requisition?"*
  - *"Who approved it?"*
  - *"Show my pending requisitions."*

### 📊 Finance Role (`TEMP99@motherson.com`)
- **Focus**: Organization-wide financial analytics, department rankings, trend analysis, audit lists.
- **Sample Queries**:
  - *"Which department has the highest approved value?"*
  - *"April month requisition"*
  - *"Show all approved requisitions"*

### 🛡️ Admin Role (`admin@motherson.com`)
- **Focus**: System health monitoring, active telemetry, uploading updated 3-Excel enterprise datasets (`Requisitions.xlsx`, `Employees.xlsx`, `Finance.xlsx`).

---

## 📊 Core Technical Capabilities

| Feature | Description |
|---|---|
| **Deterministic Parsing** | Dual query planner using LLM structured JSON output with fallback to regex parsing. |
| **Context Memory** | Resolves pronouns (`it`, `its`) and follow-up pagination (`next page`, `previous one`). |
| **Markdown Tables** | Renders formatted HTML/Markdown tables for multi-record lists and monthly aggregations. |
| **Dynamic Port Binding** | Web client binds automatically via `window.location.origin` (Port 8002 for V3). |
| **Automated Testing** | 39 passing unit & integration tests for Version 3. |

---

## 🚀 Release Information

- **Production Engine**: Backend V3 (`backend_v3/app.py` on Port 8002)
- **License**: MIT License
