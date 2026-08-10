# Employee User Guide — Enterprise Approval System AI

---

## 👤 Overview

As an **Employee** (`UserRole.EMPLOYEE`), you have secure, self-service access to your personal approval requisitions, reimbursement history, and account profile details.

---

## 🔒 Data Privacy & Boundary

The system automatically enforces **Server-Side Authorization (`CURRENT_USER` scope)**:
- You will only see requisitions matching your authenticated Employee ID.
- You cannot view or search requisitions belonging to other employees.

---

## 💬 Sample Prompts

### Profile Queries
- `"What is my employee ID?"`
- `"What department am I in?"`
- `"What is my email address?"`

### Requisition Queries
- `"Show my requisitions."`
- `"Show my pending requisitions."`
- `"Show my approved requisitions."`
- `"Show my phone bill requisitions."`
- `"What is my total approved reimbursement value?"`

### Pagination & Navigation
- If you have more than 20 requisitions, the table will display Page 1 (records 1–20) with `[Next →]` navigation controls.
- You can type `"Next page"` or `"Page 2"` to view remaining records.
