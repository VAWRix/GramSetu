# ADR 0005: Audit Record Immutability and Multi-Layer Tamper Resistance

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18
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
3. Immutability must be defended at **both the application layer and the PostgreSQL database engine layer**.
4. Privileged actions across all domain apps must emit standardized, structured audit events capturing actor, action, timestamp, target entity, client metadata (IP, user agent), and structured contextual payloads.

---

## 2. Decision Drivers

- **Evidentiary Integrity:** Audit logs must withstand legal scrutiny; absence of tampering must be provable.
- **Defense in Depth:** Even if application logic contains an authorization bug or an administrative account is compromised, the database engine must physically reject `UPDATE` and `DELETE` queries on audit tables.
- **Operational Non-Repudiation:** Actors cannot deny having performed sensitive actions (e.g., self-approvals, urgent publications, rollbacks).
- **Separation of Concerns:** Application diagnostic logs (`LOGGING` in `settings.py`) must remain separate from regulatory audit events (`apps.audit`).

---

## 3. Considered Options

1. **Option A: Standard Django Model with Admin Deletion Disabled.**
   - *Description:* Implement `AuditEvent` with `has_delete_permission() = False` in Django admin.
   - *Evaluation:* **Insufficient.** Only protects against accidental UI clicks in Django admin. Any CMS view, custom script, or database query executed by the application user (`gramsetu_app`) can still issue raw SQL `UPDATE` or `DELETE` statements.

2. **Option B: External Write-Once-Read-Many (WORM) Remote Audit Service (e.g. AWS CloudWatch / Dedicated Syslog Server).**
   - *Description:* Stream audit events immediately to an external, write-only logging appliance.
   - *Evaluation:* Excellent security, but introduces heavy operational dependencies and recurring external hosting costs unsuitable for an initial self-hosted or state-hosted Gram Panchayat server. Can be layered on in future enterprise deployments.

3. **Option C: Database-Enforced Append-Only Audit Table + Django Model Protections.**
   - *Description:* Model `AuditEvent` in `apps.audit`. In PostgreSQL, revoke `UPDATE` and `DELETE` privileges on the `audit_events` table from the runtime application role (`gramsetu_app`). Add a PostgreSQL `BEFORE UPDATE OR DELETE` trigger that unconditionally raises an exception as a secondary safeguard. In Django, enforce read-only model permissions.
   - *Evaluation:* Maximum local security with zero external service dependencies. The runtime user has permission only to `INSERT` and `SELECT`. Any attempt by the application to alter an existing audit record results in a fatal PostgreSQL permission denial.

---

## 4. Decision Outcome

**Chosen Option: Option C (Database-Enforced Append-Only Audit Table + Django Model Protections).**

### Architectural Rules:
1. **Schema Definition (`apps.audit.AuditEvent`):**
   - `id`: BigAutoField or UUIDv7 PK.
   - `timestamp`: DateTime (`auto_now_add=True`, index: B-tree DESC).
   - `actor`: Nullable FK to `apps.identity.User` (`ON DELETE SET NULL`). If an administrator account is subsequently deleted or deactivated, historical audit records retain `actor_id` or copy actor details into `actor_email` and `actor_name` fields before dereferencing.
   - `actor_role`: CharField (`super_admin`, `operator`, `system`, `anonymous`).
   - `event_category`: Choice (`auth`, `identity`, `governance`, `content`, `notices`, `documents`, `configuration`, `security`).
   - `action`: CharField (e.g., `user.invited`, `user.login.failed`, `revision.submitted`, `revision.approved`, `revision.rejected`, `content.published`, `content.urgent_published`, `content.withdrawn`, `content.rolled_back`, `document.disclosed`, `banner.activated`).
   - `target_type`: CharField or ContentType identifier.
   - `target_id`: CharField (stores UUID or integer PK of the affected domain object).
   - `client_ip`: GenericIPAddressField (records client IPv4/IPv6, respecting trusted reverse proxy headers).
   - `user_agent`: TextField (truncated to 500 characters).
   - `context_payload`: JSONB (stores non-sensitive operational parameters: revision numbers, rejection reasons, urgent justifications, before/after config diffs).
2. **Database-Level Protection (PostgreSQL Permissions & Triggers):**
   - In database provisioning migrations (executed by `gramsetu_migrator`):
     ```sql
     -- Runtime application user can ONLY insert and read audit records
     GRANT INSERT, SELECT ON TABLE audit_audit_event TO gramsetu_app;
     REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_audit_event FROM gramsetu_app;

     -- Database trigger as defense-in-depth:
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
3. **Django Application-Level Enforcement:**
   - The `AuditEvent` model in Django overrides `save()` and `delete()`:
     ```python
     def save(self, *args, **kwargs):
         if not self._state.adding:
             raise PermissionDenied("Audit records cannot be updated once created.")
         super().save(*args, **kwargs)

     def delete(self, *args, **kwargs):
         raise PermissionDenied("Audit records cannot be deleted.")
     ```
   - In Django admin (if registered), `has_add_permission(request) = False`, `has_change_permission(request) = False`, `has_delete_permission(request) = False`.

4. **Audited Critical Events Inventory:**
   - **Identity:** `user.invited`, `user.registered`, `user.role_changed`, `user.deactivated`, `mfa.device_registered`, `mfa.challenge_failed`.
   - **Governance & Publishing:** `revision.submitted`, `revision.approved`, `revision.rejected`, `publication.scheduled`, `publication.published`, `publication.urgent_published`, `publication.rolled_back`, `publication.withdrawn`.
   - **Documents:** `document.uploaded`, `document.disclosure_approved`, `document.withdrawn`, `document.deleted_permanently`.
   - **Configuration:** `panchayat_profile.updated`, `emergency_banner.toggled`, `navigation.updated`.

---

## 5. Consequences

### Positive
- **Tamper Evidence & Non-Repudiation:** Even a malicious Super Administrator logged into the CMS cannot delete incriminating audit records.
- **Engine-Level Security:** Defends against SQL injection or application bugs attempting to truncate or alter history.
- **Streamlined Regulatory Compliance:** Satisfies Indian RTI and government audit standards for electronic governance systems.

### Negative / Trade-offs
- **Table Growth:** The table will grow continuously over years. However, for a Panchayat generating ~10,000–50,000 administrative actions annually, this represents only ~15–30 MB per year, easily handled by PostgreSQL.
- **Partitioning Strategy (Future):** After 5–10 years, range partitioning by year (`PARTITION BY RANGE (timestamp)`) can be introduced if table size exceeds millions of rows.

---

## 6. Implementation Notes for Future Milestones
- Audit logging must occur synchronously inside the same database transaction as the business operation where consistency is mandatory, or via a reliable signal/middleware handler.
- Secrets, passwords, OTPs, session tokens, and raw private document binaries must **never** appear in `context_payload`.
