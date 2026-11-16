# GramSetu — REST API Documentation

**Project Title:** GramSetu – A Digital Gram Panchayat Information and Governance Portal  
**Base URL:** `http://127.0.0.1:8000/api/`  
**Communication Format:** JSON (`Content-Type: application/json; charset=utf-8`)  

---

## 1. Public Read-Only APIs (Citizen Portal)

These endpoints provide public information and require no authentication:

| API Endpoint | Method | Description | Query Parameters |
|:---|:---:|:---|:---|
| `/api/site-config/` | `GET` | Village profile, office-holders, and emergency banners | None |
| `/api/content/pages/` | `GET` | Lists all published content pages | None |
| `/api/content/pages/<slug>/` | `GET` | Full page content (e.g. `narayangaon-village` 14 sections JSON) | None |
| `/api/notices/` | `GET` | Active statutory notices | `language_code` (`mr`, `hi`, `en`), `category` |
| `/api/notices/<uuid:id>/` | `GET` | Detailed notice content and attachments | None |
| `/api/documents/` | `GET` | Disclosed public documents, budgets, and resolutions | `category` |
| `/api/documents/<uuid:id>/` | `GET` | Document metadata and available versions | None |
| `/api/documents/<uuid:id>/download/` | `GET` | Streams PDF binary with SHA-256 integrity verification | None |
| `/api/events/` | `GET` | Upcoming Gram Sabha meetings and events | `month`, `year` |
| `/api/events/<uuid:id>/` | `GET` | Meeting schedule, venue, and structured agenda | None |
| `/api/schemes/` | `GET` | Active welfare schemes | `level` (`state`, `central`), `beneficiary` |
| `/api/schemes/<slug>/` | `GET` | Full scheme details: eligibility, benefits, checklist, links | None |
| `/api/gallery/` | `GET` | Approved photo albums with cover photos | `category` |
| `/api/gallery/<slug>/` | `GET` | Album details and photo items | None |
| `/api/gallery/image/<uuid:id>/` | `GET` | Streams approved photo binary | None |
| `/api/search/` | `GET` | Unified full-text search across all approved records | `q` (query), `lang` (`mr`, `hi`, `en`) |

---

## 2. Authentication & Session APIs

| API Endpoint | Method | Auth Required | Description |
|:---|:---:|:---:|:---|
| `/api/auth/csrf/` | `GET` | None | Issues a `csrftoken` cookie to the client |
| `/api/auth/login/` | `POST` | None | Validates email & password; initiates MFA challenge |
| `/api/auth/mfa/verify/` | `POST` | Partial Session | Verifies 6-digit Email OTP; issues `sessionid` cookie |
| `/api/auth/mfa/resend/` | `POST` | Partial Session | Resends OTP (subject to 60s cooldown) |
| `/api/auth/me/` | `GET` | Authenticated | Returns current authenticated user profile and system role |
| `/api/auth/logout/` | `POST` | Authenticated | Terminates active session and invalidates cookie |

---

## 3. Administrative Staff CMS APIs (`/api/cms/*`)

All CMS endpoints require an active authenticated staff session (`@require_cms_auth`):

| API Endpoint | Method | Role Permission | Description |
|:---|:---:|:---:|:---|
| `/api/cms/dashboard/` | `GET` | Staff Session | Operational dashboard stats and pending review counts |
| `/api/cms/pending/` | `GET` | Staff Session | Maker-Checker queue listing all pending content revisions |
| `/api/cms/action/` | `POST` | **Super Admin Only** | Unified governance engine: `approve`, `reject`, or `publish` |
| `/api/cms/audit/` | `GET` | Staff Session | Immutable audit ledger of all approvals, rejections, and publications |
| `/api/cms/pages/` | `GET`, `POST` | Staff Session | Lists pages or creates new draft revisions |
| `/api/cms/pages/revisions/<id>/` | `PUT` | Staff Session | Updates drafted sections of the Village Knowledge Portal |
| `/api/cms/notices/` | `GET`, `POST` | Staff Session | Lists notices or drafts new notices |
| `/api/cms/notices/<id>/` | `GET`, `PUT` | Staff Session | Edits notice metadata and creates new draft revisions |
| `/api/cms/documents/` | `GET`, `POST` | Staff Session | Lists documents or registers new document entries |
| `/api/cms/documents/<id>/versions/` | `POST` | Staff Session | Uploads new document version binary with SHA-256 calculation |
| `/api/cms/events/` | `GET`, `POST` | Staff Session | Lists events or schedules new meetings |
| `/api/cms/events/<id>/` | `GET`, `PUT`, `DELETE` | Staff Session | Edits event or triggers mandatory 6-hour cancellation broadcast |
| `/api/cms/schemes/` | `GET`, `POST` | Staff Session | Lists schemes or creates new welfare scheme drafts |
| `/api/cms/schemes/<id>/` | `GET`, `PUT` | Staff Session | Edits scheme criteria, required documents, and benefits |
| `/api/cms/gallery/` | `GET`, `POST` | Staff Session | Lists photo albums or creates new album entries |
| `/api/cms/gallery/<id>/` | `GET`, `POST` | Staff Session | Edits album or uploads photos with SHA-256 calculation |
| `/api/cms/profile/` | `GET`, `PUT` | **Super Admin Only** | Updates official village contacts, LGD code, and Gramsevak name |

---

## 4. Key Request / Response Workflows

### 4.1 Login & MFA Flow
1. Client fetches CSRF token: `GET /api/auth/csrf/`
2. Client submits credentials: `POST /api/auth/login/`
   ```json
   {
     "email": "local.admin@gramsetu.gov.in",
     "password": "..."
   }
   ```
   *Response*: `HTTP 200 OK` with `{"mfa_required": true, "user_id": "<uuid>"}`.
3. Client submits OTP: `POST /api/auth/mfa/verify/`
   ```json
   {
     "code": "123456"
   }
   ```
   *Response*: `HTTP 200 OK` with `Set-Cookie: sessionid=...; HttpOnly; SameSite=Lax`.

### 4.2 Maker-Checker Approval Flow
Super Admin reviews pending revision and submits governance decision: `POST /api/cms/action/`
```json
{
  "action": "approve",
  "target_content_type": "notice",
  "target_id": "<uuid>",
  "revision_id": "<uuid>",
  "notes": "Verified against statutory block development order."
}
```
*Response*: `HTTP 200 OK` with updated status and audit record confirmation.
