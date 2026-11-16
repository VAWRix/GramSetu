# GramSetu — Frontend Architecture & UI Foundation

This directory houses the unified **Next.js (React 19, TypeScript, Tailwind CSS)** frontend for **GramSetu**, the official Gram Panchayat information portal in Maharashtra, India.

---

## 1. Architectural Overview & Boundaries

The frontend provides two strictly separated route and layout boundaries within a single codebase:

```
frontend/src/app/
├── (public)/               # Citizen-facing public portal
│   ├── layout.tsx          # Public shell: Accessibility bar, Government header, Nav, Footer
│   ├── page.tsx            # Portal homepage with statutory identity & domain sections
│   ├── about/              # Village profile & Panchayat history
│   ├── notices/            # Public announcements & circulars
│   ├── documents/          # Public resolutions & downloads
│   ├── events/             # Gram Sabha meetings & public calendar
│   ├── schemes/            # Welfare schemes & official links
│   ├── gallery/            # Approved photo albums
│   └── search/             # Unified search across all public content
└── (cms)/                  # Administrative Content Management System
    └── cms/                # Root path: /cms
        ├── layout.tsx      # CMS shell: Security banner, role indicators, sidebar nav
        ├── page.tsx        # CMS administrative dashboard & governance overview
        ├── content/        # Page revision management
        ├── notices/        # Notice authoring & urgent protocol
        ├── documents/      # Document disclosure approval & retention hold
        ├── events/         # Gram Sabha scheduling
        ├── schemes/        # Welfare schemes catalog
        ├── gallery/        # Media uploads
        ├── governance/     # Dual-approval state machine visualizer
        └── audit/          # Immutable audit trail overview
```

---

## 2. Accessibility & Standards Compliance

The frontend is built to satisfy **GIGW (Guidelines for Indian Government Websites)** and **WCAG 2.2 Level AA**:
1. **Marathi-First Locale:** Default language is Marathi (`mr`), with explicit selectors for Hindi (`hi`) and English (`en`). Zero silent language fallback.
2. **Skip to Main Content:** Accessible landmark bypass link as the first focusable element on every page.
3. **Text Size Scaling:** Accessibility toolbar with `A-`, `A`, and `A+` controls dynamically scaling root font size (14px, 16px, 18px, 20px).
4. **Official-Light Default Theme:** Clean government aesthetic with Ashoka Navy (`#1e3a8a`), Saffron gold (`#d97706`), and flag green accents.
5. **High-Contrast Mode:** GIGW-compliant black background with bright yellow text and high-contrast borders (contrast ratio > 7:1).
6. **Focus Visibility:** Unbroken 2px focus indicators on all interactive elements.
7. **Semantic HTML & ARIA:** Proper landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`, `<aside>`, `<article>`) and screen reader labels.

---

## 3. Data Integrity & Anti-Fabrication Principles

- **No Fabricated Information:** Village names, census codes, LGD codes, official phone numbers, and representative names are marked with explicit `[Pending Official Configuration]` tags.
- **Truthful Placeholders:** Sections awaiting official Panchayat content or backend feeds display `PlaceholderNotice` components stating that authentic records are pending administrative verification.
- **Governance Logic Preservation:** The frontend does **not** duplicate or replace backend governance rules, database constraints, anti-self-approval checks, or publication state machines.

---

## 4. Backend Integration & API Status

### 4.1 Currently Available Django Endpoints
| Endpoint | Method | Format | Description |
|---|---|---|---|
| `/health/` | GET | JSON | Liveness probe (HTTP 200) |
| `/ready/` | GET | JSON | Database readiness probe (HTTP 200 / 503) |
| `/events/` | GET | JSON | Public events list (`?lang=mr\|hi\|en&filter=upcoming\|past\|all`) |
| `/events/<uuid>/` | GET | JSON | Public event detail view |
| `/schemes/` | GET | JSON | Public schemes list (`?lang=mr\|hi\|en&level=...`) |
| `/schemes/<id_or_slug>/` | GET | JSON | Public scheme detail view |
| `/gallery/` | GET | JSON | Public gallery albums list (`?lang=mr\|hi\|en&category=...`) |
| `/gallery/<id_or_slug>/` | GET | JSON | Public album detail view |
| `/gallery/image/<uuid>/` | GET | Binary | Authenticated stream of approved photograph with SHA-256 check |
| `/documents/<uuid>/download/` | GET | Binary | Stream of approved document translation with SHA-256 check |
| `/documents/version/<uuid>/download/` | GET | Binary | Administrative version download |
| `/search/` | GET | JSON | Unified search across approved public content (`?q=...&lang=...&page=...`) |
| `/admin/` | GET/POST | HTML | Django Admin administrative portal |

### 4.2 Missing Backend Endpoints for Dedicated Frontend CMS
The following JSON API endpoints are identified as required in upcoming milestones for full headless integration:
1. `GET /api/site-config/`: Profile details (Panchayat name, LGD code, Census code, official contacts, active EmergencyBanner, SiteNavigation items).
2. `GET /api/content/pages/` and `GET /api/content/pages/<slug>/`: Public informational pages (About Village, Administration, History).
3. `GET /api/notices/` and `GET /api/notices/<id>/`: Public notices listing and detail JSON view.
4. `GET /api/documents/`: Public documents listing with category filtering and download links.
5. `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET /api/auth/me/`: Dedicated session-based authentication and role reflection endpoints for the Next.js CMS interface.

---

## 5. Security & Session Handling

- **Cookie Transport:** Session authentication relies exclusively on `HttpOnly`, `SameSite='Lax'`, `Secure` cookies managed by Django.
- **No LocalStorage Tokens:** Administrator credentials, session IDs, or secret keys are **never** stored in browser `localStorage` or `sessionStorage`.
- **MFA Status:** Multi-Factor Authentication (MFA) is an outstanding production launch blocker. Until implemented, administrative access (`/admin/` and `/cms`) must be restricted to internal networks or VPNs.
- **Zero Exposed Secrets:** No environment secrets or private API keys are embedded in client bundles.

---

## 6. Development & Verification Commands

```powershell
# Navigate to frontend directory
cd frontend

# Development server (http://localhost:3000)
npm run dev

# Run ESLint checks
npm run lint

# TypeScript verification
npx tsc --noEmit

# Production build
npm run build
```
