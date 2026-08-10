# Frequently Asked Questions (FAQ) — Enterprise Approval System AI

---

### Q1: Why does the AI Assistant not use Vector RAG for requisition analytics?
**Answer**: Tabular numerical data requires 100% exact math, grouping, and filtering. Vector search (embedding distance) is probabilistic and prone to hallucination. Backend V2 uses a deterministic pandas engine for tabular data, guaranteeing exact mathematical accuracy.

---

### Q2: Can an Employee user see requisitions of other employees by changing the question phrasing?
**Answer**: No. Authorization is enforced server-side before execution. An `Employee` user's queries are strictly restricted to `CURRENT_USER` scope (`employee_id == authenticated_user_id`). Phrasing tricks or prompt injection cannot bypass this security layer.

---

### Q3: How does pagination work?
**Answer**: Results with more than 20 rows display 20 records per page by default. The response includes `total_records`, `total_pages`, `has_next`, and `has_previous` metadata. Users can navigate via UI Previous/Next buttons or typing `"Next page"` / `"Page 3"`.

---

### Q4: How do I connect the AI Assistant to live EASY REST APIs?
**Answer**: Switch `DATA_PROVIDER_TYPE=easy_api` in `.env` or set it via the Admin portal (`/admin/config`). Implement the API endpoint URL in `backend_v2/data/easy_api_provider.py`. The rest of the AI chatbot pipeline remains unchanged.
