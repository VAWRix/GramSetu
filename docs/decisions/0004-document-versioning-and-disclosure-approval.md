# ADR 0004: Document Versioning, Disclosure Approval, and Protected Storage Architecture

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18
- **Domain:** `apps.documents`, `apps.governance`, `apps.audit`

---

## 1. Context and Problem Statement

Gram Panchayats process sensitive statutory files, tender documentation, financial audit statements, Gram Sabha resolutions, and citizen application forms.

Common vulnerabilities in government document portals include:
1. **Direct Public Uploads:** Files uploaded directly to public static directories (`/media/uploads/tender.pdf`), allowing unapproved drafts or restricted documents to be accessed by anyone who guesses the URL (Insecure Direct Object Reference / Information Leakage).
2. **In-Place File Overwrite:** Replacing a file overwrites the previous binary, destroying historical audit trails and evidentiary integrity.
3. **Premature Disclosure:** Documents made available before formal administrative review and signature.
4. **Broken Access on Withdrawal:** Withdrawing a document simply deletes the database record while leaving the physical file on disk, accessible to search engine crawlers and direct links.

Key requirements:
- All uploads must be **private by default**.
- Public disclosure requires an **explicit approval action** by a Super Administrator.
- Updating a document introduces a new version; the **existing approved file remains accessible** to citizens while the replacement version is drafted and reviewed.
- Previous versions must be privately retained for administrative and RTI audit records.
- Restricted or unapproved files must **never be guessable** or accessible via direct web server static paths.
- Withdrawal must **immediately sever public access** while securely retaining private records on disk.
- Permanent deletion must be restricted to Super Administrators, subject to retention policies, legal holds, and dependency checks.
- Initial release search must index **metadata only** (titles, reference numbers, subjects, departments), deferring full-text document content parsing.

---

## 2. Decision Drivers

- **Information Security & Leakage Prevention:** Zero exposure of draft, rejected, or withdrawn documents through URL enumeration or predictability.
- **Statutory Evidentiary Chain:** Meeting minutes, budget allocations, and tenders require immutable historical preservation.
- **High-Availability Citizen Access:** Citizen downloads of approved documents must be fast and reliable, without risking unauthorized disclosure.
- **Clear Decoupling:** Complete separation of:
  - Physical file storage (paths, size, MIME type, cryptographic checksums).
  - Document metadata (title, category, reference number, issuing authority).
  - Disclosure approval state (`pending_review`, `approved_for_disclosure`, `rejected`, `withdrawn`).
  - Public availability status (`restricted`, `published`, `withdrawn`, `archived`).

---

## 3. Considered Options

1. **Option A: Public Media Directory Storage (`MEDIA_ROOT`) with Predictable Paths.**
   - *Description:* Standard Django `FileField` uploading to `media/documents/<filename>.pdf` served directly by Nginx.
   - *Evaluation:* **Unacceptable risk.** Anyone knowing or guessing the filename bypasses Django entirely. Draft tenders, sensitive audit queries, or unapproved records become publicly downloadable.

2. **Option B: Database BLOB Storage.**
   - *Description:* Store document byte streams in PostgreSQL `bytea` columns.
   - *Evaluation:* Severely degrades database performance, bloats backups (`pg_dump`), consumes database memory buffers, and complicates caching.

3. **Option C: Decoupled Private Storage with Controlled Streaming & Cryptographic Identifiers.**
   - *Description:* Physical files reside in a private directory inaccessible to public web servers. File paths on disk use random UUIDv7 identifiers with no extension or unguessable hashes. Metadata and versions are tracked in PostgreSQL (`Document`, `DocumentTranslation`, `DocumentVersion`). Downloads are routed through a Django view that enforces authentication and disclosure approval before authorizing download via reverse-proxy streaming headers (`X-Accel-Redirect` / `X-Sendfile`).
   - *Evaluation:* Provides industry-standard security. Direct guessing is mathematically impossible. Django maintains full authorization control over every download attempt while offloading high-bandwidth streaming to the web server.

---

## 4. Decision Outcome

**Chosen Option: Option C (Decoupled Private Storage with Controlled Streaming & Cryptographic Identifiers).**

### Architectural Rules:
1. **Entity Separation:**
   - **`Document` (Logical Anchor):** Language-agnostic container.
     - `id`: UUIDv7 PK.
     - `category`: Choice (`resolution`, `tender`, `budget`, `audit_report`, `statutory_notice`, `citizen_form`).
     - `reference_number`: Optional official government dispatch/filing number (e.g., `GP/2026/RES-42`).
     - `issuing_department`: Text.
     - `is_confidential`: Boolean (defaults to `False`, restricts disclosure workflow).
     - `retention_hold`: Boolean (if `True`, prevents deletion even by Super Admin due to active audit/legal inquiry).
     - `created_at`: Timestamp.
   - **`DocumentTranslation` (Multilingual Metadata):**
     - `id`: UUIDv7 PK.
     - `document`: FK to `Document` (`ON DELETE CASCADE`).
     - `language_code`: `mr`, `hi`, `en`.
     - `title`: Translated title.
     - `description`: Translated subject summary.
     - `current_version_id`: FK to active `DocumentVersion` (nullable).
     - `status`: `draft`, `pending_approval`, `disclosed`, `withdrawn`, `archived`.
   - **`DocumentVersion` (Physical Binary & Disclosure State):**
     - `id`: UUIDv7 PK.
     - `document_translation`: FK to `DocumentTranslation` (`ON DELETE CASCADE`).
     - `version_number`: Auto-incrementing integer per translation (1, 2, 3...).
     - `storage_path`: Internal storage key on disk (e.g. `private_docs/2026/10/0192a83f-42e1-7d31-89e4-c78216314abc.dat`).
     - `original_filename`: Cleaned filename presented to user on download (e.g., `GramSabha_Minutes_Oct2026.pdf`).
     - `file_size_bytes`: BigInteger.
     - `file_format`: MIME type string (`application/pdf`, `application/vnd.openxmlformats...`).
     - `checksum_sha256`: Hexadecimal SHA-256 hash for integrity validation.
     - `uploaded_by`: FK to User.
     - `uploaded_at`: Timestamp.
     - `disclosure_status`: `draft`, `pending_approval`, `approved_for_disclosure`, `rejected`, `withdrawn`.
     - `approval_record_id`: Nullable FK to `apps.governance.ApprovalRecord`.
2. **Workflow and Invariance:**
   - **Private Upload:** When an Operator or Admin uploads a file, it is written to the private storage bucket. `disclosure_status` is `draft`.
   - **Review Request:** Operator transitions status to `pending_approval`.
   - **Disclosure Approval:** Super Administrator reviews document and approves disclosure. An `ApprovalRecord` is created. `disclosure_status` becomes `approved_for_disclosure`.
   - **Public Promotion:** In the same transaction, `DocumentTranslation.current_version_id` points to the new version, and `DocumentTranslation.status` becomes `disclosed`.
   - **Version Coexistence:** If Version 1 is `disclosed`, and Version 2 is uploaded and is `pending_approval`, citizens downloading the document receive Version 1. Only after Version 2 is approved does public delivery switch to Version 2. Version 1 is retained as `archived_version` in private storage.
3. **Direct URL Guessing Prevention & Download Routing:**
   - File downloads are requested via a logical endpoint: `/documents/<document_id>/download/?lang=mr`.
   - The view executes an authorization check:
     - If user is anonymous: requires `DocumentTranslation.status == 'disclosed'` AND `DocumentVersion.disclosure_status == 'approved_for_disclosure'`.
     - If user is authenticated Operator: can download drafts they authored or pending reviews.
     - If user is Super Administrator: can download all versions.
   - If authorized, Django issues an `X-Accel-Redirect` (Nginx) or `X-Sendfile` (Apache) header referencing the private storage path. In development (`DEBUG=True`), Django safely streams chunks via `FileResponse`.
   - The public web server is configured with `internal;` for the private documents directory, completely rejecting direct HTTP requests.
4. **Withdrawal and Deletion:**
   - **Withdrawal:** Super Admin sets `disclosure_status = 'withdrawn'` and `DocumentTranslation.status = 'withdrawn'`. The download view immediately returns `404 Not Found` (or `410 Gone`) to citizens. The binary file remains in private storage for administrative audit.
   - **Deletion:** Permitted only by Super Administrator. Deletion is blocked if `retention_hold == True` or if active references exist. Permanent physical file deletion is logged with high-severity audit entries.

---

## 5. Consequences

### Positive
- **Guaranteed Disclosure Control:** Impossible for unapproved or draft documents to leak through web crawlers or URL guessing.
- **Auditable Integrity:** Cryptographic SHA-256 hashes prevent silent file corruption or unauthorized disk replacements.
- **Smooth Replacement Cycle:** Live public documents remain downloadable while new versions undergo administrative scrutiny.

### Negative / Trade-offs
- **Streaming View Overhead:** Every download request touches Django for session and permission verification before delegating to the web server, slightly increasing request latency (~5-10ms) compared to raw static serving. This is completely acceptable for government portals where security and auditability outweigh microsecond static file performance.
- **Initial Search Limitation:** In Milestone 3 / MVP, search indexes metadata only. Full-text indexing (e.g. `pdftotext` extraction) is deferred to a future milestone.

---

## 6. Implementation Notes for Future Milestones
- In Django, file upload handlers must validate MIME types against an explicit whitelist (`application/pdf`, `image/jpeg`, `image/png`) and verify magic numbers, rejecting executable binaries or scripts.
- Storage directories must be configured outside the web root (e.g. `DATA_DIR/private_storage/`).
