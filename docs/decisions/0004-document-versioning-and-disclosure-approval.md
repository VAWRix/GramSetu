# ADR 0004: Document Versioning, Disclosure Approval, and Deployment-Agnostic Protected Storage

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18 (Updated: 2026-10-18)
- **Domain:** `apps.documents`, `apps.governance`, `apps.audit`

---

## 1. Context and Problem Statement

Gram Panchayats process sensitive statutory documents, tender notices, village development resolutions, annual audit reports, and citizen application forms.

Common failure modes in government document portals include:
1. **Public Static Ingestion:** Files uploaded directly to public static directories (`/media/uploads/tender.pdf`), enabling unapproved drafts or restricted documents to be accessed by anyone who guesses the URL (IDOR / Information Leakage).
2. **In-Place File Overwrite:** Replacing a file overwrites the existing disk binary, destroying historical audit trails and evidentiary integrity.
3. **Premature Disclosure:** Documents made available before formal administrative review and signature.
4. **Leaked Access upon Withdrawal:** Withdrawing a document merely hides database references while leaving the physical file on disk, accessible via cached URLs or search engines.
5. **Coupling to Specific Web Servers:** Architecture hardcoded to specific reverse-proxy features (like Nginx `X-Accel-Redirect`) that break if deployed on alternative government hosting platforms (e.g. NIC/S3WaaS, Apache, Caddy, or cloud object storage).

Key requirements:
- All uploads must be **private by default**.
- Public disclosure requires an **explicit approval action** by a Super Administrator.
- Updating a document introduces a new version; the **existing approved file remains accessible** to citizens while the replacement version is drafted and reviewed.
- Previous versions must be privately retained for statutory audit.
- Restricted or unapproved files must **never be guessable** or accessible via direct web server static paths.
- Withdrawal must **immediately sever public access** while securely retaining private records on disk.
- Storage delivery must satisfy a **rigorous abstract security contract** independent of deployment hosting.

---

## 2. Decision Drivers

- **Zero Information Leakage:** Unapproved drafts, internal memos, and withdrawn resolutions must never be accessible via URL guessing or direct file paths.
- **Hosting Portability:** Because GramSetu's production hosting environment (e.g., state data center, NIC cloud, commercial VPS, or container platform) is not yet finalized, the delivery architecture must remain deployment-agnostic.
- **Statutory Evidentiary Chain:** Previous versions of documents must be immutably preserved with cryptographic checksums.
- **Fail-Safe Integrity:** The system must gracefully handle missing files, unauthorized access, and database/storage mismatches.

---

## 3. The Abstract Document Delivery Security Contract

To decouple application security from reverse-proxy technology, any future document delivery implementation **must satisfy this 5-point security contract**:

1. **Mandatory Application Mediation:**  
   Every download request must be intercepted, authenticated, and authorized by Django application logic before any byte of file content is transmitted. Direct filesystem or static web server access to the storage directory is strictly prohibited.
2. **Unguessable Storage Identifiers (No Identifier-as-Authorization):**  
   Files on disk are named using non-sequential, cryptographically random identifiers (e.g. UUIDv7 with no user-supplied filenames or predictable extensions). Knowledge of a storage path or UUID **never grants access**; authorization must be verified on every request.
3. **Strict Disclosure Gate:**  
   Anonymous citizens can download a document **only if**:
   - `DocumentTranslation.status == 'disclosed'`
   - `DocumentVersion.disclosure_status == 'approved_for_disclosure'`
   - `Document.retention_hold` is respected.
4. **Isolated Storage Location:**  
   The physical storage directory must reside completely outside the public web root (`STATIC_ROOT` and `MEDIA_ROOT`).
5. **Pluggable Delivery Backends:**  
   The application service layer authorizes the request and delegates the actual byte transfer to a pluggable delivery mechanism suitable for the deployed environment:
   - *Local Development / Portable Fallback:* Django streaming response (`FileResponse`).
   - *Nginx Reverse Proxy:* `X-Accel-Redirect` response header referencing an internal-only location block.
   - *Apache / Caddy:* `X-Sendfile` response header.
   - *Cloud Object Storage (S3 / GCS / Azure Blob):* Short-lived, time-limited pre-signed URL (e.g. 5-minute validity) generated after authorization.
   - *Government Cloud (NIC / SDC):* Application-mediated chunked streaming or internal gateway redirect depending on hosting constraints.

---

## 4. Handling Edge Cases and Error States

| Scenario / Edge Case | System Behavior & Technical Specification | HTTP Response |
| :--- | :--- | :--- |
| **Unauthorized Anonymous Request** | Anonymous user attempts to download an unapproved draft or restricted document. | **`404 Not Found`** *(Never return `403 Forbidden` to anonymous users, as returning 403 confirms the existence of a sensitive file).* |
| **Unauthorized Authenticated Request** | Logged-in Operator attempts to download an unapproved draft belonging to another user. | **`403 Forbidden`** with standardized generic error JSON/page. |
| **Withdrawn Document** | Citizen requests a document that was previously public but has been withdrawn by Super Admin. | **`404 Not Found`** (or `410 Gone`). Public download is immediately severed; the binary remains in private storage for statutory audit. |
| **Missing Physical File (Storage Drift)** | Database metadata points to a `storage_path`, but the physical file is missing from disk/storage. | Log critical operational error (`logger.critical`) with full context; return **`404 Not Found`** to the user with no path leakage. |
| **Integrity Mismatch (Tampering)** | The SHA-256 checksum of the file on disk does not match `DocumentVersion.checksum_sha256`. | **Halt download immediately.** Emit a high-severity `security.integrity_failure` audit event. Return **`500 Internal Server Error`** with generic message. |
| **Version Transition** | While Version 1 is disclosed, an Operator uploads Version 2 (which is `pending_approval`). | Citizens downloading `/documents/<id>/download/` receive **Version 1**. Only when Version 2 is approved does public delivery switch to Version 2. |
| **Historical Version Access** | Citizen requests a previous version of a document. | By default, citizens can access only the `current_version`. Access to historical approved versions is restricted to Super Administrators via explicit audit routes. |

---

## 5. Architectural Data Model for Documents

```
[ Document (Logical Container) ]
  ├── category, reference_number, issuing_department
  ├── is_confidential (boolean)
  └── retention_hold (boolean, prevents deletion during legal/RTI inquiries)
        │
        └──► [ DocumentTranslation (mr, hi, en) ]
               ├── title, description
               ├── current_version_id ──► Points to active approved DocumentVersion
               └── status (draft, pending_approval, disclosed, withdrawn, archived)
                     │
                     └──► [ DocumentVersion (Physical Files) ]
                            ├── version_number (1, 2, 3...)
                            ├── storage_path (e.g., private_docs/0192a83f-...dat)
                            ├── original_filename (e.g., Gram_Sabha_Minutes_Oct2026.pdf)
                            ├── file_size_bytes, mime_type, checksum_sha256
                            ├── uploaded_by, uploaded_at
                            ├── disclosure_status (draft, pending_approval, approved_for_disclosure, rejected, withdrawn)
                            └── approval_record_id (FK to ApprovalRecord)
```

---

## 6. Backup & Recovery Risk Tracking

> [!WARNING]
> **Document-Storage Backup Decoupling Risk:**  
> A standard PostgreSQL logical backup (`pg_dump`) backs up only the database metadata (`documents_document`, `documents_document_version`), **not the physical files on disk**.  
> If database backups and file storage backups are executed independently at different times, restoring from backup creates severe consistency anomalies:
> 1. *Orphaned Files:* Binary files exist on disk with no database metadata.
> 2. *Missing Files / Broken Links:* Database records point to storage paths that do not exist in the restored storage volume.  
> **Recovery Invariant:** Database metadata and private file storage must be recoverable to a **mutually consistent point-in-time**. Full restore testing across both database and file storage is an **unresolved operational risk** that must be validated prior to production launch.

---

## 7. Consequences

### Positive
- **Guaranteed Disclosure Control:** Impossible for draft or unapproved documents to leak via URL guessing or web crawlers.
- **Portability Across Hosting Providers:** The application logic is clean and decoupled from whether the final host uses Nginx, Apache, or cloud object storage.
- **Statutory Audit Integrity:** Historical versions and checksums are retained indefinitely.

### Negative / Trade-offs
- **Application Overhead:** Every download request executes authentication and disclosure checks in Django, introducing ~5–10ms latency compared to raw static file serving. This is fully acceptable for governance documents.
- **Storage Management:** Versioning increases disk usage. Mitigated by strict file size limits (50 MB cap per file) and restricting uploads to verified formats (PDF, JPEG, PNG).
