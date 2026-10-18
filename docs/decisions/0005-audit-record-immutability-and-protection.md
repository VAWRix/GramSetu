# ADR 0005: Audit Record Immutability, Multi-Layer Threat Model, and Tamper-Resistance Boundaries

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18 (Updated: 2026-10-18)
- **Domain:** `apps.audit`, `apps.identity`, `apps.governance`

---

## 1. Context and Problem Statement

As a statutory local governance platform, GramSetu must provide an unassailable record of all privileged administrative operations. In administrative inquiries, Right to Information (RTI) investigations, or election integrity audits, officials may be called upon to prove:
- Who approved a specific village tender or welfare scheme allocation?
- Who triggered an urgent notice publication without prior approval?
- When was an administrative account created or a role changed?
- What IP address and credentials initiated a controversial rollback or document withdrawal?

If audit logs are stored as ordinary Django models with default permissions, an authorized user (or an attacker who compromises an application account) could execute `AuditEvent.objects.filter(...).delete()` or `UPDATE audit_events SET actor_id = ...` directly or through the Django admin interface.

Key requirements:
1. Audit records must be **strictly append-only**.
2. **Neither Operators nor Super Administrators** must have the capability to edit or delete audit logs through the CMS or Django administrative interfaces.
3. Immutability must be defended at **both the application layer and the PostgreSQL database engine layer**, with clear recognition of the limits of local database protection.
4. Privileged actions across all domain apps must emit standardized, structured audit events capturing actor, action, timestamp, target entity, client metadata (IP, user agent), and structured contextual payloads.

---

## 2. Comprehensive 5-Layer Threat Model & Protection Boundaries

To ensure security guarantees are neither overstated nor misunderstood, the audit subsystem explicitly evaluates protection against five distinct threat layers:

| Threat Layer | Threat Actor / Scenario | Protection Mechanism | Security Boundary & Inherent Limits |
| :--- | :--- | :--- | :--- |
| **Layer 1: Normal Application Users & Operators** | CMS Operator attempting to alter, backdate, or erase an audit entry through normal CMS interfaces or APIs. | **Application UI & Route Exclusion:** Zero views, endpoints, forms, or serializers exist for updating or deleting audit events. `apps.audit` exposes read-only query views restricted to Super Administrators. | **Fully Protected:** Operators have no application path to modify audit records. |
| **Layer 2: Administrative Users (Super Administrators)** | Super Administrator attempting to erase an embarrassing or incriminating audit log via the CMS UI or Django Admin. | **Django Model-Level Enforcement:** `AuditEvent.save()` rejects updates when `not self._state.adding`. `AuditEvent.delete()` unconditionally raises `PermissionDenied`. In Django Admin, `has_add_permission`, `has_change_permission`, and `has_delete_permission` all return `False`. | **Fully Protected via UI:** Super Administrators cannot modify or delete audit logs through the Django web interface. |
| **Layer 3: Runtime Application Database Role (`gramsetu_app`)** | Compromise of the Django web process (e.g. Remote Code Execution or SQL Injection) attempting to run raw SQL `UPDATE` or `DELETE` statements. | **PostgreSQL Privilege Hardening & Triggers:**<br>1. `GRANT INSERT, SELECT ON TABLE audit_audit_event TO gramsetu_app;`<br>2. `REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_audit_event FROM gramsetu_app;`<br>3. `BEFORE UPDATE OR DELETE` database trigger raising an unignorable SQL exception. | **Fully Protected at DB Engine:** Even an attacker with arbitrary SQL injection running under `gramsetu_app` is blocked by PostgreSQL's permission matrix (`42501 permission denied`). |
| **Layer 4: Privileged Database Roles (`gramsetu_migrator`, `postgres`)** | A rogue database administrator, compromised migration credentials (`gramsetu_migrator`), or PostgreSQL superuser (`postgres`). | **Separation of Operational Roles:** The web runtime (`gramsetu_app`) has no DDL rights and cannot alter permissions. Migration credentials are only used during scheduled maintenance (`DB_ROLE=migrator`). | **LIMITATION OF LOCAL DB:** Database permissions and triggers **cannot prevent** a superuser or the table owner (`gramsetu_migrator`) from dropping triggers (`DROP TRIGGER`) or issuing direct `DELETE` queries via a database console. Absolute immutability against a database superuser is impossible within the same database engine. |
| **Layer 5: Host-Level & Storage Volume Compromise** | An attacker obtaining root OS access on the hosting server or direct write access to the Docker named volume (`gramsetu_pgdata`). | **Host OS Security & Volume Isolation:** Restricted file permissions, Docker container isolation, and loopback-only port binding (`127.0.0.1:5433`). | **LIMITATION OF LOCAL STORAGE:** Local database tables cannot survive an attacker with root OS access who can overwrite the raw PostgreSQL heap files on disk. Protection against this threat requires out-of-band external audit retention. |

---

## 3. Considered Options

1. **Option A: Standard Django Model with Admin Deletion Disabled.**
   - *Description:* Implement `AuditEvent` with `has_delete_permission() = False` in Django admin.
   - *Evaluation:* **Insufficient.** Only protects against accidental UI clicks. Any CMS view, custom script, or SQL injection executed by `gramsetu_app` can alter or truncate history.

2. **Option B: Database-Enforced Append-Only Audit Table + Django Model Protections (Current Selected Design).**
   - *Description:* Model `AuditEvent` in `apps.audit`. In PostgreSQL, revoke `UPDATE`, `DELETE`, and `TRUNCATE` privileges from `gramsetu_app`. Add a PostgreSQL `BEFORE UPDATE OR DELETE` trigger as secondary defense-in-depth. In Django, enforce read-only model permissions.
   - *Evaluation:* Provides robust defense against application-level threats (Layers 1, 2, and 3) with zero external service dependencies. Readily compatible with the project's least-privilege role architecture.

3. **Option C: External Write-Once-Read-Many (WORM) Remote Audit Appliance (Deferred Enterprise Control).**
   - *Description:* Synchronously or asynchronously ship structured audit logs to an external, write-only syslog server, cloud object store with Object Lock (WORM), or tamper-evident ledger with cryptographic timestamping.
   - *Evaluation:* Provides complete defense against Layers 4 and 5 (compromised DBA or compromised host). However, it introduces external cloud dependencies, network latency, and recurring hosting costs that are out of scope for the current local development foundation. This is retained as an **explicitly deferred control** for production readiness.

---

## 4. Decision Outcome

**Chosen Option: Option B (Database-Enforced Append-Only Audit Table + Django Model Protections), with Option C explicitly documented as a deferred future control.**

### Architectural Rules:
1. **Schema Definition (`apps.audit.AuditEvent`):**
   - `id`: `BigAutoField(primary_key=True)` (High-performance 64-bit integer sequential key).
   - `timestamp`: `DateTimeField(auto_now_add=True, db_index=True)` (Server timestamp in `Asia/Kolkata`).
   - `actor`: `ForeignKey(User, null=True, on_delete=SET_NULL, related_name='audit_events')`.
   - `actor_email_snapshot`: `EmailField(blank=True)` (Permanently preserves actor email even if `User` row is subsequently deleted).
   - `actor_role`: `CharField(max_length=20)` (`super_admin`, `operator`, `system`, `anonymous`).
   - `event_category`: `CharField(max_length=30, choices=[('auth', 'Authentication & MFA'), ('identity', 'User & Role Management'), ('governance', 'Approval & Rejection'), ('content', 'Page Lifecycle'), ('notices', 'Notice Lifecycle'), ('documents', 'Document Disclosure'), ('config', 'System Configuration'), ('security', 'Security Alert')])`.
   - `action`: `CharField(max_length=100)` (e.g., `user.login`, `revision.submitted`, `revision.approved`, `notice.urgent_published`, `content.rolled_back`, `document.withdrawn`).
   - `target_content_type`: `CharField(max_length=100, blank=True)`.
   - `target_id`: `CharField(max_length=100, blank=True)`.
   - `client_ip`: `GenericIPAddressField(null=True, blank=True)`.
   - `user_agent`: `TextField(blank=True)` (Truncated to 500 characters).
   - `context_payload`: `JSONBField(default=dict)` (Non-sensitive contextual parameters, hashes, diffs).
2. **PostgreSQL Privilege Grants & Invariance:**
   - In database provisioning migrations (executed by `gramsetu_migrator`):
     ```sql
     -- Runtime application user can ONLY insert and read audit records:
     GRANT INSERT, SELECT ON TABLE audit_audit_event TO gramsetu_app;
     REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_audit_event FROM gramsetu_app;

     -- Defense-in-depth trigger preventing row mutations:
     CREATE OR REPLACE FUNCTION protect_audit_immutability()
     RETURNS TRIGGER AS $$
     BEGIN
         RAISE EXCEPTION 'Audit records are strictly immutable. UPDATE and DELETE operations are prohibited.';
     END;
     $$ LANGUAGE plpgsql;

     CREATE TRIGGER trg_audit_event_immutability
     BEFORE UPDATE OR DELETE ON audit_audit_event
     FOR EACH ROW EXECUTE FUNCTION protect_audit_immutability();
     ```
3. **Explicit Documentation of Protection Limits:**
   - The trigger and table privileges defend **strictly against `gramsetu_app`**.
   - They **do not protect** against actions taken by `gramsetu_migrator` (table owner) or `postgres` (superuser).
   - To mitigate risk from privileged roles, `gramsetu_migrator` credentials are never loaded into the web runtime environment (`DB_ROLE=app`), and `postgres` credentials are restricted to container initialization.

---

## 5. Consequences

### Positive
- **Guaranteed Protection Against Web Exploits:** Any SQL injection or application compromise operating as `gramsetu_app` physically cannot modify or purge audit history.
- **Tamper Evidence within Application Scope:** Super Administrators and Operators cannot alter records through any web interface.
- **Zero External Overhead:** Requires no additional cloud services, network hops, or recurring costs.

### Negative / Explicit Architectural Limitations
- **Local Database Scope:** Does not protect against a root compromise of the database server or a malicious DBA connecting as superuser.
- **Independent Copy Requirement (Deferred):** If statutory regulations mandate protection against rogue database administrators, an out-of-band streaming pipeline (Option C) must be provisioned during production deployment.

---

## 6. Implementation Notes for Future Milestones
- Audit logging must occur synchronously inside the same database transaction as critical business mutations.
- Secrets, passwords, OTPs, session cookies, and private document binaries must **never** appear in `context_payload`.
