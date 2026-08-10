# Admin Portal Guide — Enterprise Approval System AI Assistant

---

## 🛠️ Overview

As an **Administrator** (`UserRole.ADMIN`), you oversee system health, inspect active record telemetry, and refresh enterprise Excel datasets (`Requisitions.xlsx`, `Employees.xlsx`, `Finance.xlsx`).

---

## ⚙️ Key Capabilities

1. **Admin Portal Login**: Navigate to `http://localhost:8002/admin.html` and sign in using your corporate admin email (`admin@motherson.com`).
2. **System Telemetry Dashboard**: Inspect total indexed requisition records, active data provider mode (`Excel`), local LLM model (`qwen2.5:3b`), and real-time backend health.
3. **Enterprise Excel Dataset Upload**:
   - Upload new `Requisition Excel (.xlsx)`, `Employee Directory Excel (.xlsx)`, or `Finance Team Excel (.xlsx)`.
   - Click **⚡ Upload Excels & Reload Dataset** to reload memory DataFrames atomically without restarting the backend server.
