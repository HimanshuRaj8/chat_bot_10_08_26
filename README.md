# Enterprise Approval System AI Assistant (Version 3.0)

[![Backend V3 Test Suite](https://img.shields.io/badge/V3%20Tests-29%2F29%20Passing-brightgreen)](backend_v3/tests/)
[![Backend V2 Baseline](https://img.shields.io/badge/V2%20Tests-151%2F151%20Passing-blue)](backend_v2/tests/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-black)](https://flask.palletsprojects.com/)
[![Cross-Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-orange)](https://github.com/HimanshuRaj8/enterprise-approval-ai-assistant)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

An enterprise-grade, role-aware AI Assistant for natural language querying of approval requisitions, employee directory data, and financial analytics. Built with a clean, modular **Deterministic Analytical Pipeline (Version 3)** and powered by local **Qwen2.5 LLM integration via Ollama**.

---

## 🌟 What's New in Version 3.0

- 🚀 **Modular Core Architecture**: Clean separation of Authentication, Security Boundaries, Query Parsing, Context Resolution, Repositories, Analytics, and Presentation.
- 💬 **Relative Pronoun & Multi-Turn Context**: Resolves follow-up queries naturally (e.g. `"Who approved it?"`, `"What is its requested value?"`, `"Previous one"`).
- 📊 **Markdown Table Rendering**: Automatic tabular response generation for multi-record lists and monthly/quarterly aggregations.
- 🛡️ **Strict Deterministic Security**: Zero LLM authorization leaks — security scopes are enforced by a dedicated gateway before repository execution.
- 🌐 **Dynamic Frontend Origin Binding**: Automatically binds UI requests to whichever port served the application (`http://localhost:8002` for V3, `http://localhost:8001` for V2).
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
git clone https://github.com/HimanshuRaj8/enterprise-approval-ai-assistant.git
cd enterprise-approval-ai-assistant

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
git clone https://github.com/HimanshuRaj8/enterprise-approval-ai-assistant.git
cd enterprise-approval-ai-assistant

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

#### Option A: Run Version 3 (Recommended — Port 8002)
```bash
# Windows:
python backend_v3/app.py

# macOS / Linux:
.venv/bin/python backend_v3/app.py
```
Open **`http://localhost:8002`** in your browser to access the V3 web assistant interface.

#### Option B: Run Version 2 (Legacy Baseline — Port 8001)
```bash
# Windows:
python app.py

# macOS / Linux:
.venv/bin/python app.py
```
Open **`http://localhost:8001`** in your browser.

---

## 🧪 Running Automated Test Suites

Both Version 3 and Version 2 include comprehensive automated unit and integration tests.

### Windows (PowerShell / CMD)
```cmd
# Run Backend V3 Test Suite (29 Tests)
python -m pytest backend_v3/tests/ -v --tb=short

# Run Backend V2 Test Suite (151 Tests)
python -m pytest backend_v2/tests/ -v --tb=short
```

### macOS / Linux (Terminal)
```bash
# Run Backend V3 Test Suite (29 Tests)
.venv/bin/python -m pytest backend_v3/tests/ -v --tb=short

# Run Backend V2 Test Suite (151 Tests)
.venv/bin/python -m pytest backend_v2/tests/ -v --tb=short
```

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
│   ├── app.py                  # V3 Flask server & API routes
│   ├── config.py               # Central settings & defaults
│   ├── auth/                   # Authentication & Session Store
│   ├── context/                # Multi-turn Context & Relative Pronoun Resolver
│   ├── data/                   # Excel Data Provider & Repositories
│   ├── llm/                    # Ollama LLM Client & Response Generator
│   ├── models/                 # Dataclasses (CurrentUser, QueryPlan, VerifiedResult)
│   ├── query/                  # Query Parser, Validator, Entity Resolver, Executor
│   ├── services/               # ChatService Pipeline Orchestrator
│   ├── utils/                  # Chat History JSON Persistence
│   └── tests/                  # V3 Automated Test Suite (29 Tests)
│
├── backend_v2/                 # Version 2 Legacy Baseline Engine (Port 8001)
│   ├── app.py                  # V2 Flask application entrypoint
│   └── tests/                  # V2 Regression Suite (151 Tests)
│
├── frontend/                   # Shared Modern Web Client
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
- **Cross-Platform Path Safety**: All file paths use `os.path.join` and standard relative path handling to ensure 100% smooth operation across Windows, macOS, and Linux.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
