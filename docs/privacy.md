# Privacy & Data Handling (Story 5.4)

Process Intelligence is designed **privacy-by-default**: it stores only what is strictly needed for mining, and provides full erasure controls so organisations can meet GDPR / revDSG requirements out of the box.

---

## Data categories stored

| Category | Examples | Stored where | Retention |
|---|---|---|---|
| **User accounts** | Email (hashed password), workspace ID | `users` / `workspaces` tables | Until account deletion |
| **Event-log metadata** | Log name, import date, source, row/case counts | `event_logs` table | Until log deletion |
| **Events** | Activity name, timestamp, lifecycle, optional cost | `events` table | Until log deletion |
| **Cases** | External case key (e.g. order number) | `cases` table | Until log deletion |
| **Activities** | Activity label | `activities` table | Until log deletion |
| **Resources** | Operator / agent name (optional, only if mapped at import) | `resources` table | Until log deletion |
| **Key-value attributes** | Extensible per-event metadata (reserved for future use) | `attributes` table | Until log deletion |
| **Uploaded files** | Temporary CSV / XES file on disk | `uploads/` directory | Deleted immediately after import |

No data is shared with third parties. When an LLM provider is configured (OpenAI / Anthropic) for AI features, column headers and a small sample of rows may be sent for schema suggestions. The actual event data is never sent to external APIs unless the user explicitly calls the AI conformance explanation endpoint.

---

## Privacy-by-default settings

| Setting | Default | Notes |
|---|---|---|
| Task-mining input capture | **Off** | Story 4.1 records clicks/URL changes only; keystroke/input content recording is disabled by default and requires explicit opt-in. |
| Resource column mapping | **Optional** | If the import mapping omits the resource column, no personal identifiers are stored. |
| LLM / AI provider | **Disabled** | No external API calls unless `AI_PROVIDER` and the corresponding key are explicitly configured. |
| Uploaded file retention | **0** | Raw upload files are deleted from disk immediately after successful import. |

---

## Right to erasure (log deletion)

Deleting an event log via `DELETE /api/logs/{id}` (or the UI trash button) removes **all** derived data in a single CASCADE operation:

* The `event_logs` row itself
* All linked `cases`, `events`, `activities`, `resources` and `attributes`
* The temporary upload file (already removed at import time)

This is enforced by `ON DELETE CASCADE` foreign keys in PostgreSQL and by explicit `PRAGMA foreign_keys=ON` enforcement for SQLite, verified by an automated test (`test_delete_log_removes_all_derived_data`).

Computed analytics (variants, performance KPIs, bottlenecks, conformance reports) are derived on the fly and never persisted, so they disappear automatically when the underlying events are gone.

---

## Recommendations for deployers

1. **TLS in production** — deploy behind a reverse proxy with HTTPS; the app itself listens on plain HTTP.
2. **Database encryption** — enable PostgreSQL TDE or disk-level encryption if the hosting environment requires data-at-rest protection.
3. **Minimal resource mapping** — advise analysts to omit the resource column during import if personal-name-level data is not needed for the analysis.
4. **Audit logging** — consider enabling PostgreSQL's `pgaudit` extension for tamper-evident access logs when processing sensitive process data.
