# ADR 0002: Immutable Content Revisions and Explicit Approval Binding

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18
- **Domain:** `apps.governance`, `apps.content`, `apps.notices`

---

## 1. Context and Problem Statement

GramSetu serves as an official public record for an Indian local self-government body. Published village announcements, statutory meeting notices, and citizen information carry administrative and legal consequences under the Maharashtra Village Panchayats Act.

Traditional CMS systems often overwrite content in-place (`UPDATE pages SET body = ... WHERE id = ...`), which destroys the historical provenance of published material. Other systems keep revision histories, but allow revisions to be silently edited after submission or allow an approval record to point vaguely to an entity rather than an exact, tamper-evident content snapshot.

Key requirements:
1. When an author submits content for review, the submitted revision must become **strictly immutable**. Any subsequent editorial change must produce a new revision.
2. An official approval by a Super Administrator must bind to the **exact revision** that was inspected. An approver must never approve a moving target.
3. If an approved revision is edited, the existing approved revision remains unchanged and active; the new edit starts a new draft revision cycle.
4. The currently published content displayed to citizens must remain stable and unchanged while newer revisions are drafted, rejected, or awaiting review.

---

## 2. Decision Drivers

- **Accountability & Audit Provenance:** Administrative reviewers must be held accountable for the exact words, figures, and dates they signed off on.
- **Editorial Safety:** Live published information must not be taken offline or replaced with work-in-progress drafts.
- **Tamper Evidence:** Modifying a revision after approval or submission must be strictly prohibited at the database and application levels.
- **Clear State Demarcation:** Differentiate between an *editorial revision state* (e.g. `draft`, `submitted`, `approved`, `rejected`) and an entity's *public lifecycle state* (e.g. `published`, `scheduled`, `withdrawn`, `archived`).

---

## 3. Considered Options

1. **Option A: In-Place Editing with Timestamp Logging.**
   - *Description:* Overwrite the main entity table; record `updated_at` and `updated_by`.
   - *Evaluation:* Completely unacceptable for an official government portal. Historical integrity is lost, rollbacks are impossible, and approval validity cannot be proven.

2. **Option B: Event Sourcing for All Entities.**
   - *Description:* Store every keystroke or delta as an event stream; reconstruct current state on read.
   - *Evaluation:* Overly complex for a Django monolith targeting a Gram Panchayat. Introduces event schema migration pain, difficult relational queries, and unnecessary performance overhead for a low-churn administrative site.

3. **Option C: Explicit Immutable Revision Rows with Parent Foreign Keys.**
   - *Description:* Every content entity has a translation record (e.g., `PageTranslation`), which contains a collection of immutable child `PageRevision` records. The translation record maintains a pointer `current_approved_revision_id` to the currently active approved revision.
   - *Evaluation:* Combines relational simplicity with tamper-proof versioning. Submissions freeze the revision row. Approvals bind specifically to `PageRevision.id`. Edits insert a new row with incremented `revision_number`. The live site continues reading `current_approved_revision_id` until an explicit publication event switches the pointer.

---

## 4. Decision Outcome

**Chosen Option: Option C (Explicit Immutable Revision Rows with Parent Foreign Keys).**

### Architectural Rules:
1. **Revision Structure:**
   - Entities requiring versioning (Pages, Notices) implement dedicated revision models (`PageRevision`, `NoticeRevision`).
   - Fields on revision: `id` (UUIDv7), `translation_id` (FK), `revision_number` (Integer, auto-incrementing per translation), `title`, `summary`, `content_body`, `content_hash` (SHA-256 digest of normalized payload), `created_by` (FK to User), `created_at` (Timestamp), `editorial_status` (`draft`, `submitted`, `approved`, `rejected`).
2. **Immutability Enforcement:**
   - While `editorial_status == 'draft'`, the author may update the draft row.
   - When the author clicks "Submit for Review", `editorial_status` transitions to `submitted`, `submitted_at` is stamped, and `content_hash` is computed.
   - Once `editorial_status != 'draft'`, application logic and PostgreSQL trigger/constraint rules **reject all `UPDATE` operations** on content fields (`title`, `content_body`, `summary`, `content_hash`).
   - If an author wishes to make corrections to a submitted or approved revision, the system creates a **new revision row** (`revision_number = max + 1`) initialized in `draft` status, copying content from the previous revision.
3. **Approval Binding:**
   - An `ApprovalRecord` (`apps.governance`) does not point to the generic `Notice` or `Page`; it holds a foreign key to the specific `NoticeRevision` or `PageRevision`.
   - The approval record stores `approved_by` (Super Administrator), `approved_at`, `revision_hash` (verifying matches `content_hash` at review time), and mandatory administrative notes.
   - Self-approval by a Super Administrator is permitted (as a Panchayat may have a single executive officer), but is flagged with `is_self_approval = True` and emits a high-priority audit log.
4. **Live Content Decoupling:**
   - The parent `PageTranslation` / `NoticeTranslation` table maintains `current_approved_revision_id` (nullable FK to Revision).
   - Public views query `WHERE current_approved_revision_id = revision.id AND status = 'published'`.
   - While authors draft revisions 2, 3, and 4, the public views continue serving revision 1 seamlessly.

---

## 5. Consequences

### Positive
- **Guaranteed Provenance:** Every published character is permanently linked to the specific revision approved by an official.
- **Zero Public Downtime:** Drafting and reviewing replacements never impacts citizen access to current notices or pages.
- **Rejection Accountability:** Rejections set `editorial_status = 'rejected'` on the revision, requiring a mandatory `rejection_reason` in `RejectionRecord`. The author can inspect the feedback and generate a corrected new revision without losing the rejected record.

### Negative / Trade-offs
- **Storage Growth:** Content strings are duplicated across revisions. Given the low-to-moderate volume of a Gram Panchayat (hundreds to thousands of notices/pages over years), PostgreSQL storage impact is negligible (a few tens of megabytes per year).
- **Orphan Drafts:** Abandoned drafts may accumulate. Handled via periodic soft-archival or administrative cleanup views without deleting submitted/approved revisions.

---

## 6. Implementation Notes for Future Milestones
- In Django, the `save()` method on revision models must assert `if self.editorial_status != 'draft' and self.tracker.has_changed('content_body'): raise ValidationError(...)`.
- In PostgreSQL, a `BEFORE UPDATE` trigger can enforce that rows with `editorial_status IN ('submitted', 'approved', 'rejected')` reject mutations on content columns unless invoked by a migration.
