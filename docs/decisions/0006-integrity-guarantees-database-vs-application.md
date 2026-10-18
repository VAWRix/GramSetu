# ADR 0006: Division of Data Integrity Guarantees — PostgreSQL Engine vs. Application Logic

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18
- **Domain:** Cross-Cutting / All Domain Applications

---

## 1. Context and Problem Statement

A recurring failure mode in web development is relying solely on application-level or frontend validation (e.g. Django forms, model `clean()` methods, or browser JavaScript) to enforce critical business and data integrity invariants. When concurrent requests occur, background workers run, or administrative scripts are executed, application-only checks are susceptible to race conditions, partial updates, and data corruption.

Conversely, attempting to push all business logic into PostgreSQL (via complex stored procedures and triggers) can make the codebase difficult to test, opaque to Django developers, and challenging to version-control and maintain.

We must define a clear, rigorous architectural boundary:
1. **Which invariants MUST be enforced by PostgreSQL database constraints?**
2. **Which invariants MUST be enforced by Django application logic and transaction boundaries?**
3. **How do concurrency controls (`SELECT FOR UPDATE`, atomic transactions) bridge the gap?**

---

## 2. Decision Drivers

- **Zero Tolerance for Corrupted Public States:** Citizens must never see two different published revisions of the same notice in the same language simultaneously, or an announcement whose expiry precedes its publication.
- **Race Condition Prevention:** Multiple operators submitting drafts or multiple administrators reviewing at the same time must not cause phantom approvals or duplicate records.
- **Maintainability & Testability:** Core business rules should remain readable in Python/Django test suites while resting on unshakeable database bedrock.
- **Fail-Safe Defaults:** If Django code has a bug, the database engine must reject invalid data states rather than silently corrupting records.

---

## 3. Considered Options

1. **Option A: Pure Application-Level Enforcement (Django "Skinny DB").**
   - *Description:* Use only standard Django model fields, relying on `clean()`, forms, and serializers to validate status transitions, dates, and uniqueness.
   - *Evaluation:* **High risk.** Vulnerable to race conditions (Time-of-Check to Time-of-Use / TOCTOU). Under concurrent requests (e.g., rapid double-clicks on "Publish"), two distinct revisions could simultaneously pass application checks and be marked as active, corrupting public views.

2. **Option B: Stored-Procedure-Heavy Architecture (Database "Fat DB").**
   - *Description:* Write all workflow logic in PL/pgSQL stored procedures; Django merely executes stored procedure calls.
   - *Evaluation:* Difficult to debug, fragments business logic between Python and SQL, impairs Django ORM integration, and complicates local automated testing.

3. **Option C: Layered Defense with Relational Invariants in PostgreSQL and Workflow Orchestration in Django.**
   - *Description:* 
     - **PostgreSQL Engine:** Enforces relational integrity, hard domain constraints, date-order sanity, enum validity, partial uniqueness, and structural immutability.
     - **Django Application Logic:** Enforces multi-step state transitions, user authorization, audit logging, contextual justification rules, and notification dispatch.
     - **Concurrency Controls:** Uses explicit database transactions (`transaction.atomic()`) and pessimistic row locking (`select_for_update()`) to eliminate TOCTOU race conditions.
   - *Evaluation:* Best-of-both-worlds industry standard. The database makes invalid states physically impossible, while Django retains clean, testable workflow orchestration.

---

## 4. Decision Outcome

**Chosen Option: Option C (Layered Defense with Relational Invariants in PostgreSQL and Workflow Orchestration in Django).**

### 4.1 Invariants Enforced Exclusively by PostgreSQL

The PostgreSQL schema will enforce the following invariants using native constraints and indexes:

| Invariant Category | PostgreSQL Mechanism | Specific Rule / Syntax |
| :--- | :--- | :--- |
| **Language Code Validation** | `CHECK` Constraint | `CONSTRAINT valid_lang CHECK (language_code IN ('mr', 'hi', 'en'))` |
| **Chronological Date Sanity** | `CHECK` Constraint | `CONSTRAINT check_dates CHECK (effective_from <= effective_until)` |
| **Notice Expiry Sanity** | `CHECK` Constraint | `CONSTRAINT check_expiry CHECK (expires_at IS NULL OR expires_at > published_at)` |
| **Single Active Publication** | **Partial Unique Index** | `CREATE UNIQUE INDEX uq_active_published_per_lang ON notices_noticetranslation (notice_id, language_code) WHERE (status = 'published');` |
| **Revision Number Sequence** | `UNIQUE` Constraint | `UNIQUE (translation_id, revision_number)` |
| **Cascade & Protection Rules** | Foreign Key Actions | `ON DELETE CASCADE` for parent-child translations/revisions;<br>`ON DELETE PROTECT` for documents attached to official notices;<br>`ON DELETE PROTECT` for users referenced in approvals. |
| **Audit Immutability (App-level)** | SQL Permissions & Triggers | `REVOKE UPDATE, DELETE ON audit_audit_event FROM gramsetu_app;`<br>`BEFORE UPDATE OR DELETE` trigger raising exception.<br>*(Note: Defends strictly against runtime role `gramsetu_app`; does not protect against superuser or table owner `gramsetu_migrator`)* |
| **Temporal Exclusion (If used)** | `EXCLUDE USING gist` | Prevents overlapping date ranges for single active states.<br>*(Prerequisite: requires trusted extension `btree_gist`, which must be enabled via migration)* |

### 4.2 Invariants Enforced by Django Application Logic

The application layer handles dynamic, context-dependent rules that cannot be cleanly expressed in static SQL:

| Invariant Category | Django Application Mechanism | Enforcement Description |
| :--- | :--- | :--- |
| **State Machine Transitions** | Service Layer / Model Methods | Verifies legal state transitions (e.g. `draft` can transition to `submitted`, but `draft` cannot transition directly to `published`). |
| **Role-Based Authorization** | View / Permission Classes | Verifies actor has `Super Administrator` role for approvals, rollbacks, and withdrawals; verifies `Operator` has urgent publishing grant. |
| **Rejection / Rollback Justification** | Form / Model Validation | Enforces minimum character length and non-empty rationale when rejecting or rolling back content. |
| **Self-Approval Audit Flagging** | Service Layer | Detects when `revision.created_by == approver` and flags `is_self_approval = True`, logging a high-priority audit event. |
| **MFA Challenge Verification** | Authentication Backend | Validates time-based OTP codes and token expiration windows. |
| **File Integrity & Antivirus** | Upload Form Cleaners | Validates MIME types, magic numbers, maximum byte limits, and rejects executable extensions. |

### 4.3 Concurrency & Transaction Safeguards (Bridging the Gap)

To prevent race conditions during critical workflow transitions:

1. **Pessimistic Row Locking on Approval and Publication:**
   When an administrator approves, publishes, or rolls back content, the workflow executes within an atomic transaction with a row lock:
   ```python
   with transaction.atomic():
       # Pessimistically lock the translation row to prevent concurrent publications
       translation = (
           NoticeTranslation.objects
           .select_for_update()
           .get(id=translation_id)
       )
       # Verify revision is still in 'submitted' state
       revision = (
           NoticeRevision.objects
           .select_for_update()
           .get(id=revision_id, translation=translation)
       )
       if revision.editorial_status != 'submitted':
           raise WorkflowConflictError("Revision state has changed concurrently.")

       # Execute transition, create ApprovalRecord, emit AuditEvent
   ```

2. **Idempotent Background Jobs:**
   - Background tasks (e.g. scheduled notice activation or expiry toggles) must be idempotent.
   - If a cron job or Celery worker triggers twice, it performs `UPDATE ... WHERE status = 'scheduled' AND effective_from <= NOW()`, which is a safe no-op on subsequent invocations.
   - Queries to the public site evaluate `effective_from <= NOW() AND (expires_at IS NULL OR expires_at > NOW())` dynamically, ensuring public consistency even if background workers are delayed.

---

## 5. Consequences

### Positive
- **Guaranteed Consistency:** Even if concurrent users hit the publication button simultaneously, PostgreSQL partial unique indexes and row-level locks prevent conflicting states.
- **Fail-Fast Error Handling:** Any bug violating fundamental domain constraints is caught immediately at the database layer with a descriptive error.
- **Clear Engineering Guidance:** Developers know exactly where to implement new rules: hard relational boundaries go in PostgreSQL, workflow routing goes in Django services.

### Negative / Trade-offs
- **Custom Migrations for Advanced Constraints:** Partial unique indexes and database triggers require `RunSQL` or custom migration operations in Django migrations rather than pure ORM declarations.
- **Database Portability:** Relies on PostgreSQL-specific features (partial indexes, ICU collation, `REVOKE` permissions). This is fully acceptable since PostgreSQL 16 is the locked, permanent database engine for GramSetu.

---

## 6. Implementation Notes for Future Milestones
- All database constraints must be explicitly declared in Django model `Meta.constraints` (using `CheckConstraint` and `UniqueConstraint(condition=...)`) so Django generates them automatically in migrations.
- Database triggers for audit protection and immutability must be packaged in dedicated migration files using `migrations.RunSQL`.
