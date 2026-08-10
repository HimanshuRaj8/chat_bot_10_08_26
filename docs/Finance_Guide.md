# Finance Team Guide — Enterprise Approval System AI

---

## 📊 Overview

As a **Finance Team Member** (`UserRole.FINANCE`), you possess organization-wide authorized access (`ALL_EMPLOYEES` & `SPECIFIC_EMPLOYEE` scopes) to analyze requisitions, track departmental spending, and conduct audit queries across the organization.

---

## 💬 Sample Prompts

### Organization-Wide List & Filtering
- `"Show all approved requisitions."`
- `"Show all pending requisitions."`
- `"Show all approved requisitions from last month."`
- `"Show all requisitions for SW department."`

### Department & Employee Rankings
- `"Which department has the highest approved value?"`
- `"Which employee has the highest total approved value?"`
- `"Top 10 employees by approved reimbursement value."`
- `"Which requisition has the highest approved value?"`

### Department & Time Summaries
- `"Give me department-wise approval summary."`
- `"Give me monthly breakdown of approved requisitions."`

### Interactive Pagination Controls
- Large datasets (e.g. 212 approved requisitions) display 20 records per page.
- Click `[Next →]` / `[← Previous]` or type `"Next page"` / `"Page 3"` to navigate.
