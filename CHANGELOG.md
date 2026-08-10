# Changelog — Enterprise Approval System AI

All notable changes to this project are documented in this file.

---

## [3.0.0] — 2026-08-10

### Added
- **Backend V3 Production Architecture**: Modular core engine decoupled into distinct services (`auth`, `context`, `data`, `query`, `llm`, `services`). Runs on Port 8002.
- **Multi-Turn Context & Pronoun Resolution**: Natural resolution for relative pronoun questions (`"who approved it?"`, `"its requested value"`, `"previous one"`).
- **Markdown Table Generation**: Automatic tabular formatting for multi-record lists and monthly/quarterly aggregations.
- **Dynamic Frontend Origin Binding**: Updated `app.js` and `admin.js` to use `window.location.origin` for dynamic server port detection across V2 and V3 runtimes.
- **Cross-Platform Compatibility**: Full verification and platform-independent path handling (`os.path.join`) for Windows, macOS, and Linux.
- **V3 Automated Test Suite**: 29 automated test cases covering authorization invariants, context resolution, API endpoints, analytics, and query parsing.

### Fixed
- Status badge mapping for `"Finally Approved By..."` text patterns (renders ✅ instead of ❌).
- Approver name extraction fallback when `Approved By` Excel column is blank.
- Admin dashboard telemetry bug where active record count showed 0.
- Pyright IDE configuration (`pyrightconfig.json`) updated with `backend_v3` search path.

---

## [2.1.0] — 2026-08-09

### Added
- **Deterministic Pagination**: Real page navigation (`DEFAULT_PAGE_SIZE = 20`, `MAX_PAGE_SIZE = 50`) returning `total_records`, `total_pages`, `has_next`, `has_previous`, and `returned_records`.
- **UI Pagination Controls**: Frontend Previous/Next buttons rendered below list/filter chat bubbles.
- **Natural Language Pagination Follow-ups**: Support for commands like `"Next page"`, `"Previous page"`, `"Page 3"`.

---

## [2.0.0] — 2026-08-08

### Added
- **Backend V2 Core Architecture**: Introduced modular pipeline (`QueryPlanner`, `AuthorizationService`, `QueryExecutor`, `ResultConsistencyValidator`, `ResponseGenerator`, `ChatService`).
- **Profile Query Engine**: Direct handling of identity questions from session memory.
- **Role-Based Access Control**: Strict scope enforcement (`CURRENT_USER` for Employees vs `ALL_EMPLOYEES` for Finance).

---

## [1.0.0] — 2026-08-05

### Added
- Initial prototype approval system interface with basic Excel data loader.
