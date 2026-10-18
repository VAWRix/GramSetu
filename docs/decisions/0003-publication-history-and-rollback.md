# ADR 0003: Append-Only Publication History, Lifecycle Transitions, and Non-Destructive Rollback

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18
- **Domain:** `apps.governance`, `apps.content`, `apps.notices`, `apps.documents`

---

## 1. Context and Problem Statement

When government notices, resolutions, or informational pages are published or changed, questions often arise regarding:
- *When exactly was an announcement visible to the public?*
- *Who authorized the publication or withdrawal?*
- *If an error was discovered and the content rolled back to an earlier version, what was the timeline of that rollback?*

In naive publishing systems, publishing content simply updates a boolean flag (`is_published = True`) and a timestamp (`published_at = NOW()`). A "rollback" in such systems either overwrites the row or changes a foreign key back to the older revision, erasing the fact that the flawed revision was ever live.

Key requirements:
1. Every publication, scheduled activation, early withdrawal, urgent release, and rollback must be recorded as an **immutable, append-only historical event**.
2. A rollback must **never delete or overwrite past publication events**; it must create a **new publication event** referencing the reinstated approved revision, documenting who authorized the rollback and why.
3. Separation must exist between:
   - **Editorial Revision Status:** `draft` → `submitted` → `approved` / `rejected`.
   - **Public Publication Lifecycle:** `unpublished` → `scheduled` → `published` → `withdrawn` / `archived`.
4. The system must prevent invalid lifecycle transitions (e.g., publishing a rejected or unapproved revision, or withdrawing content that was never published).

---

## 2. Decision Drivers

- **Legal Auditability:** Legal proceedings (such as RTI queries or tender disputes) require verifiable proof of publication windows.
- **Append-Only History:** Historical operational logs must never be rewritten or deleted during normal application workflows.
- **Transaction Safety:** Pointing the public-facing entity to a new (or rolled-back) revision must happen atomically alongside the creation of the publication event.
- **Fail-Safe Offline Behavior:** Public availability checks must be evaluated safely even if scheduled background workers (celery/cron) fail or experience delays.

---

## 3. Considered Options

1. **Option A: In-Place State Mutation on Translation Records.**
   - *Description:* Maintain `status`, `published_at`, and `withdrawn_at` directly on the translation row. Rollback mutates these columns to previous values.
   - *Evaluation:* Completely loses publication history. If Revision 1 was published, then Revision 2 was published for 2 hours and rolled back to Revision 1, there is no historical record in the table showing Revision 2 was ever published or why it was rolled back.

2. **Option B: Temporal Database Tables (`PERIOD FOR ...` or `django-simple-history`).**
   - *Description:* Maintain system-versioned shadow tables tracking all row modifications.
   - *Evaluation:* Tracks database-level field diffs but fails to capture explicit business intent (e.g., *was this a rollback? was it an urgent safety override? what was the justification?*). Querying business events across shadow tables is cumbersome and error-prone.

3. **Option C: Explicit PublicationEvent Entity & Atomic Pointer Updates.**
   - *Description:* Maintain an append-only `PublicationEvent` ledger in `apps.governance`. The translation entity maintains a denormalized pointer `current_publication_event_id` and `current_approved_revision_id` updated within an atomic transaction.
   - *Evaluation:* Provides complete, first-class domain modeling of publication history. Rollback is modeled explicitly as a new event of type `rollback`. Full business context (reason, user, timestamps, previous event pointer) is preserved.

---

## 4. Decision Outcome

**Chosen Option: Option C (Explicit PublicationEvent Entity & Atomic Pointer Updates).**

### Architectural Rules:
1. **Publication Event Ledger (`apps.governance.PublicationEvent`):**
   - Fields:
     - `id`: UUIDv7 primary key.
     - `target_type`: Content type (`PageTranslation`, `NoticeTranslation`, `DocumentVersion`).
     - `target_id`: UUIDv7 foreign key to the translation/version entity.
     - `revision_id`: UUIDv7 foreign key to the specific approved `Revision` being made live.
     - `event_type`: Choice field: `initial_publish`, `update_publish`, `scheduled_publish`, `urgent_publish`, `rollback`, `withdrawal`, `archival`.
     - `scheduled_for`: Optional timestamp (null for immediate actions).
     - `effective_from`: Timestamp when content becomes visible to citizens.
     - `effective_until`: Optional timestamp when content automatically expires.
     - `actor_id`: Foreign key to `User` (must be Super Administrator, or authorized Operator for urgent notices).
     - `created_at`: Timestamp (`auto_now_add=True`).
     - `justification`: Mandatory text string for rollbacks, urgent publishes, and early withdrawals.
     - `superseded_event_id`: Nullable foreign key to the `PublicationEvent` this event replaces.
2. **State Machine Transitions:**
   ```
   [Draft Revision]
          │ (Submit for Review)
          ▼
   [Submitted Revision]
          │
     ┌────┴────────────────────────┐
     │ (Approve)                   │ (Reject with Reason)
     ▼                             ▼
   [Approved Revision]         [Rejected Revision]
     │                             │
     ├──────────────────────────┐  └─► [Author creates new Draft]
     │ (Publish Immediately)    │ (Schedule)
     ▼                          ▼
   [Published State]         [Scheduled State]
     │ (Effective From reached)    │
     ├─────────────────────────────┘
     │
     ├──► [Normal Update] ──► (Publish New Approved Revision)
     │
     ├──► [Rollback]       ──► (Publish Previous Approved Revision + Log Reason)
     │
     ├──► [Withdrawal]     ──► (Withdraw immediately + Sever public access + Log Reason)
     │
     └──► [Expiry/Archive] ──► (Automatic transition to Archived state)
   ```
3. **Rollback Workflow:**
   - A Super Administrator selects an earlier approved revision (e.g., Revision 1) from the audit history to replace the current live revision (e.g., Revision 2).
   - The user must provide a mandatory `rollback_reason` (e.g., *"Typographical error in tender closing date discovered; reverting to approved baseline pending correction"*).
   - Within an atomic database transaction (`transaction.atomic()`):
     1. Lock target translation row (`SELECT FOR UPDATE`).
     2. Create a new `PublicationEvent`:
        - `event_type = 'rollback'`
        - `revision_id = revision_1.id`
        - `superseded_event_id = current_event.id`
        - `justification = rollback_reason`
        - `actor = request.user`
     3. Update the translation row:
        - `current_approved_revision_id = revision_1.id`
        - `status = 'published'`
     4. Emit an immutable `AuditEvent` (`apps.audit`) documenting the rollback.
4. **Resilient Public Availability Resolution:**
   - To ensure site reliability if background workers fail, public view availability is determined declaratively at SQL query time:
     ```sql
     WHERE status = 'published'
       AND effective_from <= NOW()
       AND (effective_until IS NULL OR effective_until > NOW())
     ```
   - Celery or cron maintenance tasks simply toggle status flags for fast index lookups, but queries never serve expired or not-yet-effective content even if the cron job is delayed.

---

## 5. Consequences

### Positive
- **Historical Integrity:** A complete, tamper-evident timeline of who published what, when it went live, and when it was taken down is permanently preserved.
- **Clean Separation:** Revision drafting/editing status is completely decoupled from public site exposure.
- **Safe Rollback:** Rollback is treated as a forward-moving administrative action rather than destructive record editing.

### Negative / Trade-offs
- **Multiple Tables per Domain Object:** Involves logical entity, translation entity, revision entity, and publication event entity.
- **Constraint Coordination:** Requires careful foreign key configuration and database transactions to avoid race conditions.

---

## 6. Implementation Notes for Future Milestones
- Database `CHECK` constraint on `PublicationEvent`:
  `CONSTRAINT check_justification_required CHECK (event_type NOT IN ('rollback', 'urgent_publish', 'withdrawal') OR (justification IS NOT NULL AND LENGTH(TRIM(justification)) >= 10))`
- PostgreSQL partial index on `PublicationEvent (target_id, created_at DESC)` for high-speed publication history inspection.
