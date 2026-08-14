# Enterprise Approval System AI Assistant (Version 3.1)

[![Backend V3 Test Suite](https://img.shields.io/badge/V3%20Tests-57%2F57%20Passing-brightgreen)](backend_v3/tests/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-black)](https://flask.palletsprojects.com/)
[![Cross-Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-orange)](https://github.com/HimanshuRaj8/chat_bot_10_08_26)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

An enterprise-grade, role-aware AI Assistant for natural language querying of approval requisitions, employee directory data, and financial analytics. Built with a clean, modular **Deterministic Analytical Pipeline (Version 3)** and powered by local **Qwen2.5 LLM integration via Ollama**.

---

## 🌟 What's New in Version 3.1

- 🧠 **Claim Period Intelligence**: Automatic extraction of reimbursement claim periods from unstructured texts. Features duration suffix protection (e.g. `30 Days`) and context ref-year validation window bounds.
- 🚀 **Modular Core Architecture**: Clean separation of Authentication, Security Boundaries, Query Parsing, Context Resolution, Repositories, Analytics, and Presentation.
- 💬 **Relative Pronoun & Multi-Turn Context**: Resolves follow-up queries naturally (e.g. `"Who approved it?"`, `"What is its requested value?"`, `"Previous one"`).
- 📊 **Markdown Table Rendering**: Automatic tabular response generation for multi-record lists, duplicate warnings, and timeline views.
- 🛡️ **Strict Deterministic Security**: Zero LLM authorization leaks — security scopes are enforced by a dedicated gateway before repository execution.
- 🌐 **Dynamic Frontend Origin Binding**: Automatically binds UI requests to the port serving the application (`http://localhost:8002`).
- 🖥️ **Full Cross-Platform Compatibility**: Native support for **Windows**, **macOS**, and **Linux** runtimes.

---

## 🏗️ System Architecture

```
User Natural Language Question
              │
              ▼
┌───────────────────────────┐
│ Authentication & Session  │  (Session Token / Corporate Email)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Query Plan Parser     │  (LLM JSON Parser + Regex Fallback)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│  Conversation Context     │  (Resolves Pronouns & History References)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│   Query Plan Validator    │  (Enforces Plan Syntax & Invariants)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│   Authorization Gateway   │  (Forces CURRENT_USER for Employees)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│      Entity Resolver      │  (Matches Employee Names & Req IDs)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Deterministic Repositories│  (Pandas Aggregations & Pagination)
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│    Response Generator     │  (Markdown Tables & Qwen2.5 Narration)
└───────────────────────────┘
```

---

## 👥 Role & Permission Matrix

| User Role | Default Scope | Authorized Capabilities | Data Visibility |
|---|---|---|---|
| 👤 **Employee** | `CURRENT_USER` | Personal claims, status lookup, profile details, total reimbursements | Strictly own requisitions (`employee_id` match) |
| 📊 **Finance** | `ALL_EMPLOYEES` / `SPECIFIC_EMPLOYEE` | Org-wide analytics, department rankings, employee breakdowns, status filters | Entire organization dataset |
| 🛡️ **Admin** | System Management | Excel dataset upload & reload, active record telemetry | Full administrative access |

---

## 💻 Installation & Quick Start

### 1. Prerequisites
- **Python 3.11 or higher**
- **Ollama** running locally with `qwen2.5:3b` model:
  ```bash
  ollama pull qwen2.5:3b
  ```

---

### 2. Environment Setup

#### 🪟 On Windows (Command Prompt / PowerShell)
```cmd
# Clone repository
git clone https://github.com/HimanshuRaj8/chat_bot_10_08_26.git
cd chat_bot_10_08_26

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# In Command Prompt:
.venv\Scripts\activate.bat
# OR in PowerShell:
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create environment configuration file
copy .env.example .env
```

#### 🍎 / 🐧 On macOS & Linux (Terminal)
```bash
# Clone repository
git clone https://github.com/HimanshuRaj8/chat_bot_10_08_26.git
cd chat_bot_10_08_26

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration file
cp .env.example .env
```

---

### 3. Running the Server

```bash
# Windows:
python backend_v3/app.py

# macOS / Linux:
.venv/bin/python backend_v3/app.py
```
Open **`http://localhost:8002`** in your browser to access the web assistant interface.

---

## 🧪 Running Automated Tests

### Windows (PowerShell / CMD)
```cmd
python -m pytest backend_v3/tests/ -v --tb=short
```

### macOS / Linux (Terminal)
```bash
.venv/bin/python -m pytest backend_v3/tests/ -v --tb=short
```

Expected: **39 tests passing.**

---

## 📖 Sample Test Scenarios

### Employee User Login (`rahul.karn@motherson.com`)
- `"What is my employee ID?"`
- `"What is the status of my latest requisition?"`
- `"Who approved it?"` *(Pronoun follow-up)*
- `"Show my pending requisitions"`
- `"What is my total approved amount?"`

### Finance User Login (`TEMP99@motherson.com`)
- `"Show all approved requisitions"`
- `"April month requisition"` *(Aggregates monthly count & value into Markdown table)*
- `"Which department has the highest total approved value?"`
- `"Show pending requisitions"`

---

## 📂 Repository Structure

```
.
├── backend_v3/                 # Version 3 Production Engine (Port 8002)
│   ├── app.py                  # Flask server & API routes
│   ├── config.py               # Central settings & defaults
│   ├── auth/                   # Authentication & Session Store
│   ├── context/                # Multi-turn Context & Relative Pronoun Resolver
│   ├── data/                   # Excel Data Provider & Repositories
│   ├── llm/                    # Ollama LLM Client & Response Generator
│   ├── models/                 # Dataclasses (CurrentUser, QueryPlan, VerifiedResult)
│   ├── query/                  # Query Parser, Validator, Entity Resolver, Executor
│   ├── services/               # ChatService Pipeline Orchestrator
│   ├── utils/                  # Chat History JSON Persistence
│   └── tests/                  # Automated Test Suite (39 Tests)
│
├── frontend/                   # Modern Web Client
│   ├── index.html              # Main Chat Assistant interface
│   ├── app.js                  # Frontend dynamic origin logic & table renderer
│   ├── style.css               # Styling system & dark theme tokens
│   ├── admin.html              # Admin Portal interface
│   ├── admin.js                # Admin Portal Excel upload handler
│   └── admin.css               # Admin Portal stylesheet
│
├── Sample/                     # Default Enterprise Excel Datasets
│   ├── Requisitions.xlsx       # Sample requisition records dataset
│   ├── Employees.xlsx          # Sample employee directory dataset
│   └── Finance.xlsx            # Sample finance role overlay dataset
│
├── docs/                       # Guides & Documentation
├── scripts/                    # Utility scripts (health check)
├── requirements.txt            # Python dependencies manifest
├── pyrightconfig.json          # IDE type checker configuration
├── README.md                   # Primary project documentation
├── PROJECT_ARCHITECTURE.md     # Architectural blueprint specification
├── API_DOCUMENTATION.md        # REST API endpoint reference
├── PROJECT_OVERVIEW.md         # Executive project summary
└── LICENSE                     # MIT License
```

---

## 🛡️ Security & Privacy

- **Deterministic Execution**: Financial calculations and data slicing are computed exclusively via pandas data engines — LLMs are restricted to text narration and natural language parsing.
- **Pre-Retrieval Authorization**: Authorization boundaries are enforced on every request before repository access occurs.
- **Cross-Platform Path Safety**: All file paths use `os.path.join` and standard relative path handling to ensure smooth operation across Windows, macOS, and Linux.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
