# ADR 0001: Multilingual Content Representation via Explicit Translation Entities

- **Status:** Accepted
- **Deciders:** Senior Django Architect, PostgreSQL Database Designer, Application Security Engineer
- **Date:** 2026-10-18
- **Domain:** All content-producing applications (`apps.content`, `apps.notices`, `apps.documents`, `apps.events`, `apps.schemes`, `apps.gallery`, `apps.site_config`)

---

## 1. Context and Problem Statement

GramSetu is the official information portal for a Gram Panchayat in Maharashtra, India. In accordance with state statutory norms and administrative standards:
- **Marathi (`mr`)** is the primary, statutory language of official communication and default locale.
- **Hindi (`hi`)** and **English (`en`)** are supported secondary languages for broader accessibility.

Content published on government portals cannot assume symmetric, simultaneous translation:
1. An official village notice or resolution may be drafted and approved in Marathi immediately, while Hindi and English translations are produced days later or not at all.
2. A translation must never be automatically inferred, machine-translated without human review, or displayed to the public prior to formal administrative approval.
3. Edits, revisions, approval cycles, and emergency withdrawals must function **independently per language**.
4. Modifying an English translation must never mutate, invalidate, or revert an approved Marathi record.
5. Incomplete translations must not leave the site broken or leak unapproved draft fragments; instead, the public user experience must indicate language availability and provide clear fallback navigation.

We must decide on the architectural pattern for representing multilingual content within Django and PostgreSQL.

---

## 2. Decision Drivers

- **Independent Governance Lifecycle:** Translations must undergo independent drafting, review, approval, and publication cycles.
- **Editorial Revision Immutability:** Revisions in one language must not trigger revision bumps or status changes in other languages.
- **Referential Integrity & Relational Queries:** Queries filtering by active language, category, or date must be fast, indexable via standard B-tree indexes, and verifiable via PostgreSQL foreign keys.
- **Devanagari Unicode Fidelity:** Collation and sorting must support Marathi script order (`mr-IN-x-icu` or standard UTF-8) without character corruption.
- **Search Isolation:** Text search indexes (TSVector) must be generated per language using language-specific stemming and dictionaries.

---

## 3. Considered Options

1. **Option A: Field-Level Translation (Columns per Language, e.g. `title_mr`, `title_hi`, `title_en`).**
   - *Description:* Add suffixed columns on the base model (e.g. `django-modeltranslation`).
   - *Evaluation:* Severely flawed for governance. It couples all languages into a single database row. Approving or publishing an update to one column forces a modification of the entire row, making independent revision history, individual approval timestamps, and separate publication states nearly impossible to audit cleanly. Adding new languages requires DDL schema migrations.

2. **Option B: JSONB Field per Translated Attribute (`{"mr": "...", "hi": "...", "en": "..."}`).**
   - *Description:* Store translated strings inside PostgreSQL JSONB fields.
   - *Evaluation:* Lacks relational foreign key constraints, makes indexation complex, prevents row-level locking per translation, and obscures approval metadata. Review status, approver identity, and revision identifiers would need to be embedded within JSON documents or managed externally, violating 3NF and weakening database-enforced integrity.

3. **Option C: Explicit Translation Entity / Translation by Row (Logical Container + Translation Row).**
   - *Description:* A language-agnostic logical entity (e.g. `Notice`, `Page`, `Document`) acts as the anchor, linked via a 1:N foreign key to a dedicated translation model (e.g. `NoticeTranslation`, `PageTranslation`, `DocumentTranslation`).
   - *Evaluation:* Completely decouples each language into its own relational record with its own status, revision pointer, approval history, and publication timestamps. Perfectly mirrors the real-world administrative reality where translations are distinct artifacts produced at different times by different translators.

---

## 4. Decision Outcome

**Chosen Option: Option C (Explicit Translation Entity / Translation by Row).**

### Architectural Rules:
1. **Logical Anchor:** Every multilingual domain entity consists of a root logical record (e.g., `Notice`) containing language-agnostic metadata:
   - Primary key (`UUIDv7` or `BigAutoField`).
   - Domain category, dates (e.g., event date, meeting date, tender opening date).
   - Creation and system timestamps.
2. **Translation Child Entity:** All translatable attributes (title, summary, rich-text body, slug, SEO description) reside on a child entity (e.g., `NoticeTranslation`):
   - Foreign key to the logical anchor (`ON DELETE CASCADE`).
   - `language_code`: `CharField(max_length=5, choices=[('mr', 'Marathi'), ('hi', 'Hindi'), ('en', 'English')])`.
   - PostgreSQL `CHECK` constraint: `CONSTRAINT valid_language_code CHECK (language_code IN ('mr', 'hi', 'en'))`.
   - PostgreSQL unique constraint: `UNIQUE (notice_id, language_code)`.
   - Independent publication status (`status`: `draft`, `submitted`, `approved`, `published`, `withdrawn`, `archived`).
   - Active revision pointer (`current_approved_revision_id`).
3. **Graceful Fallback & Availability Signaling:**
   - When a citizen accesses a page in English (`/en/pages/about-panchayat/`) and no approved English translation exists, the application does **not** leak draft content or return a generic 500 error.
   - The view renders the statutory default (Marathi) with an explicit banner: *"This page is not yet available in English. Displaying official Marathi version."*
   - Language switchers dynamically indicate whether a target translation is published (`🟢 Available`, `⚪ Not available in this language`).

---

## 5. Consequences

### Positive
- **Strict Separation of Concerns:** Reviewing, approving, or withdrawing an English translation has zero side effects on the Marathi or Hindi records.
- **Relational Integrity:** Foreign keys, check constraints, and partial unique indexes natively prevent invalid language states in PostgreSQL.
- **Optimized Indexing:** Language-specific text search vectors (PostgreSQL `tsvector`) can be maintained directly on the translation table without JSON parsing overhead.
- **Extensibility:** Adding another statutory language in the future requires adding a choice to the `CHECK` constraint without altering table schemas.

### Negative / Trade-offs
- **Query Complexity:** Retrieving an entity requires a `JOIN` between the logical entity and the requested translation entity (or an explicit `prefetch_related`).
- **Slug Uniqueness:** Slugs must be scoped per language (`UNIQUE (language_code, slug)`) rather than globally unique.

---

## 6. Implementation Notes for Future Milestones
- In Django, translation models must use `select_related('parent')` for view lookups.
- Slugs in Devanagari (Marathi and Hindi) must support full UTF-8 Unicode characters via `allow_unicode=True` on `SlugField`.
- The default ordering for Marathi content should leverage PostgreSQL ICU collation (`COLLATE "mr-IN-x-icu"` or standard C.UTF-8) where alphabetical listing of Marathi titles is required.
