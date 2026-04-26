# NavMSM — Manufacturing / Production Management System

A multi-tenant, modular Django + Bootstrap 5 platform for managing the full manufacturing lifecycle — from tenant onboarding, billing and branding, through production planning, shop-floor execution, quality, inventory, procurement, and beyond.

This repository contains **Phase 1** of the platform: the core foundation plus **Module 1 — Tenant & Subscription Management**, **Module 2 — Product Lifecycle Management (PLM)**, and **Module 3 — Bill of Materials (BOM) Management**. The remaining 19 functional modules listed in [`MSM.md`](./MSM.md) are planned as follow-up phases.

---

## Table of Contents

1. [Highlights](#highlights)
2. [Tech Stack](#tech-stack)
3. [Screenshots / UI Tour](#screenshotsui-tour)
4. [Project Structure](#project-structure)
5. [Requirements](#requirements)
6. [Setup & Installation](#setup--installation)
7. [Environment Variables](#environment-variables)
8. [Running the App](#running-the-app)
9. [Seeded Demo Data](#seeded-demo-data)
10. [Multi-Tenancy Model](#multi-tenancy-model)
11. [Authentication & User Management](#authentication--user-management)
12. [Module 1 — Tenant & Subscription Management](#module-1--tenant--subscription-management)
13. [Module 2 — Product Lifecycle Management (PLM)](#module-2--product-lifecycle-management-plm)
14. [Module 3 — Bill of Materials (BOM) Management](#module-3--bill-of-materials-bom-management)
15. [UI / Theme Customization](#ui--theme-customization)
14. [Management Commands](#management-commands)
15. [Payment Gateway Integration](#payment-gateway-integration)
16. [Security Notes](#security-notes)
17. [Roadmap](#roadmap)
18. [Troubleshooting](#troubleshooting)
19. [License](#license)

---

## Highlights

- **Multi-tenant by design** — every domain model inherits from a `TenantAwareModel` abstract base; a `TenantMiddleware` binds the current tenant to the request and thread-local storage, and a custom manager auto-scopes every query.
- **Full authentication suite** — login (username *or* email), registration (provisions tenant + admin user + trial subscription atomically), forgot / reset password with token links, and token-based invite acceptance.
- **Complete user management** — list with search/filter, create, edit, detail, delete, toggle-active; per-user profile with UI theme preferences.
- **Module 1 in full** — tenant onboarding wizard, plans & subscriptions, invoices & payments (mock gateway), custom branding, email templates, tenant audit log, and health monitoring with charts.
- **Module 2 — Product Lifecycle Management (PLM)** — product master data with revisions, specs and variants; engineering change orders with submit/approve/reject/implement workflow; CAD/drawing repository with version control; product compliance tracking against global regulatory standards (ISO, RoHS, REACH, CE, UL, FCC, IPC); NPI/Stage-Gate project management with 7-stage gate reviews and deliverables.
- **Module 3 — Bill of Materials (BOM) Management** — multi-level BOMs with self-referencing tree and phantom assemblies; transparent recursive explosion; immutable revision snapshots with one-click rollback; alternate / substitute material catalog with approval workflow; per-component cost elements (material / labor / overhead / tooling) with cascading roll-up through default released sub-assembly BOMs; EBOM / MBOM / SBOM discriminator with sync mappings and automated drift detection.
- **Highly customizable UI** — vertical / horizontal / detached layouts, light / dark themes, 4 sidebar sizes, 3 sidebar colors, fluid / boxed width, fixed / scrollable position, LTR / RTL — all persisted per-user and in `localStorage`.
- **Blue + white theme** — clean, professional, responsive — works from 360 px up to ultra-wide displays.
- **Idempotent seeders** — fake data for 3 tenants, their users, invites, plans, subscriptions, invoices, payments, 30 days of health snapshots, and audit entries.
- **MySQL via XAMPP** — out-of-the-box config using `python-decouple` and a `.env` file.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Django 4.2 (LTS) |
| Database | MySQL 8 (XAMPP) via `mysqlclient` |
| Frontend | Bootstrap 5.3, RemixIcon 4.1, ApexCharts 3.45 |
| Templating | Django Templates + `django-crispy-forms` (Bootstrap 5 pack) |
| Config | `python-decouple` (12-factor `.env`) |
| Seeding | `Faker` |
| Auth | Django sessions + custom `User(AbstractUser)` |
| Icons | RemixIcon (CDN) |

---

## Screenshots / UI Tour

> Routes available after setup. Log in as `admin_acme` / `Welcome@123` (seeded).

| Route | What you'll see |
|-------|-----------------|
| `/accounts/login/` | Split-card login page with blue gradient brand panel |
| `/accounts/register/` | Company + admin registration (creates tenant + trial subscription) |
| `/accounts/forgot-password/` | Request a reset email (console backend in dev) |
| `/` (dashboard) | KPI cards, health chart (ApexCharts), subscription panel, recent audit activity, quick actions |
| `/accounts/users/` | Paginated user list with role/status filters and Actions column |
| `/accounts/profile/` + `/accounts/profile/edit/` | Profile view + editor, including UI theme preferences |
| `/accounts/invites/` | Pending / accepted / expired invitations |
| `/tenants/onboarding/` | 4-step onboarding wizard (Organization → Plan → Admin → Review) |
| `/tenants/plans/` | Plan gallery with current-plan indicator |
| `/tenants/subscription/` | Subscription details, renewal, cancel-at-period-end / resume |
| `/tenants/invoices/` | Invoice list with status filter + "Pay" action |
| `/tenants/invoices/<pk>/` | Invoice detail with line items + payment history |
| `/tenants/branding/` | White-label form with live color preview (logos, colors, email, footer) |
| `/tenants/email-templates/` | Per-tenant transactional email templates (welcome, invite, reset, …) |
| `/tenants/health/` | Tenant health dashboard: score, users, storage, API calls + ApexCharts trends |
| `/tenants/audit/` | Immutable audit log of tenant-level actions |
| `/plm/` | PLM dashboard — KPI cards (products, open ECOs, CAD docs, compliant records), recent ECOs and active NPI projects |
| `/plm/products/` | Product master data list with category/type/status filters; create, edit, delete |
| `/plm/products/<pk>/` | Product detail with tabs for Specifications, Revisions, Variants, CAD, and Compliance |
| `/plm/categories/` | Hierarchical product category list with self-FK parent |
| `/plm/eco/` | Engineering Change Order list filterable by status, priority, change type |
| `/plm/eco/<pk>/` | ECO detail — tabs for Impacted Items, Approvals, Attachments, plus submit / approve / reject / implement actions |
| `/plm/cad/` | CAD / drawing repository list with type filter (2D, 3D, schematic, PCB, assembly) |
| `/plm/cad/<pk>/` | CAD detail with version history, upload form, and release action |
| `/plm/compliance/` | Product compliance tracker with expiry-soon flag and standard/status filters |
| `/plm/compliance/<pk>/` | Compliance record detail with immutable audit trail |
| `/plm/npi/` | NPI / Stage-Gate project list filterable by status and current stage |
| `/plm/npi/<pk>/` | NPI detail with 7-stage accordion (Concept → Launch), gate decisions, and per-stage deliverables |
| `/plm/cad/versions/<pk>/download/` | Auth-gated download for a CAD version file (404 cross-tenant; 302 → login if anonymous) |
| `/plm/eco/attachments/<pk>/download/` | Auth-gated download for an ECO attachment |
| `/plm/compliance/<pk>/certificate/` | Auth-gated download for a compliance certificate file |
| `/bom/` | BOM dashboard — total / draft / released BOMs, pending alternates, drift watch, recent BOMs |
| `/bom/boms/` | BOM list with status / type / product filters; create, edit, delete |
| `/bom/boms/<pk>/` | BOM detail with tabs for Lines, Revisions, Sync; Cost Roll-Up sidebar with Recompute action |
| `/bom/boms/<pk>/explode/` | Indented multi-level BOM explosion (phantom assemblies collapsed) |
| `/bom/boms/<pk>/submit/` | POST — Draft → Under Review |
| `/bom/boms/<pk>/approve/` | POST — Under Review → Approved |
| `/bom/boms/<pk>/release/` | POST — Approved → Released (supersedes prior released BOM, captures snapshot) |
| `/bom/boms/<pk>/recompute/` | POST — recompute the cost roll-up |
| `/bom/lines/<pk>/edit/` | Edit a BOM line (parent / phantom / scrap %) |
| `/bom/revisions/<pk>/` | Revision snapshot detail with rollback action |
| `/bom/revisions/<pk>/rollback/` | POST — rollback BOM to this snapshot (creates a new revision entry) |
| `/bom/lines/<line_id>/alternates/new/` | Add an alternate / substitute for a BOM line |
| `/bom/alternates/<pk>/approve/` | POST — approve an alternate |
| `/bom/rules/` | Substitution rule catalog (tenant-level reusable equivalences) |
| `/bom/costs/` | Per-component cost element list (material / labor / overhead / tooling) |
| `/bom/sync/` | EBOM / MBOM / SBOM sync map list filterable by sync status |
| `/bom/sync/<pk>/` | Sync map detail with append-only sync log |
| `/bom/sync/<pk>/run/` | POST — run drift detection between source and target BOM |

---

## Project Structure

```
NavMSM/
├── .env                          # local secrets (gitignored)
├── .env.example                  # template for .env
├── .gitignore
├── LICENSE
├── MSM.md                        # full 22-module specification
├── README.md                     # this file
├── manage.py
├── requirements.txt
│
├── config/                       # Django project
│   ├── settings.py               # MySQL, TenantMiddleware, crispy, auth URLs, etc.
│   ├── urls.py                   # root + include each app
│   ├── wsgi.py
│   └── asgi.py
│
├── apps/
│   ├── core/                     # Multi-tenancy foundation
│   │   ├── models.py             # Tenant, TenantAwareModel, TimeStampedModel, thread-local
│   │   ├── middleware.py         # TenantMiddleware → request.tenant
│   │   ├── context_processors.py # tenant + branding + UI preferences
│   │   ├── views.py              # DashboardView
│   │   ├── admin.py
│   │   └── management/commands/seed_data.py
│   │
│   ├── accounts/                 # Auth + users + invites + profile
│   │   ├── models.py             # User (AbstractUser + tenant + role), UserProfile, UserInvite
│   │   ├── forms.py
│   │   ├── views.py              # Login/Register/Forgot/Reset/UserCRUD/Profile/Invite
│   │   ├── urls.py
│   │   └── admin.py
│   │
│   ├── tenants/                  # MODULE 1 — Tenant & Subscription Management
│   │   ├── models.py             # Plan, Subscription, Invoice, InvoiceLineItem, Payment,
│   │   │                         # BillingAddress, UsageMeter, BrandingSettings,
│   │   │                         # EmailTemplate, TenantAuditLog, TenantHealthSnapshot,
│   │   │                         # HealthAlert
│   │   ├── services/
│   │   │   ├── gateway.py        # PaymentGateway Protocol + MockGateway
│   │   │   ├── billing.py        # start_trial, issue_invoice, mark_paid
│   │   │   └── health.py         # capture_snapshot
│   │   ├── signals.py            # Audit-log receivers on Subscription, Branding
│   │   ├── forms.py
│   │   ├── views.py              # Onboarding wizard, Plans, Subscription, Invoices, Branding, Health, Audit
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       ├── capture_health.py
│   │       ├── seed_plans.py
│   │       └── seed_tenants.py
│   │
│   ├── plm/                      # MODULE 2 — Product Lifecycle Management
│   │   ├── models.py             # ProductCategory, Product, ProductRevision, ProductSpecification,
│   │   │                         # ProductVariant, EngineeringChangeOrder, ECOImpactedItem,
│   │   │                         # ECOApproval, ECOAttachment, CADDocument, CADDocumentVersion,
│   │   │                         # ComplianceStandard (shared catalog), ProductCompliance,
│   │   │                         # ComplianceAuditLog, NPIProject, NPIStage, NPIDeliverable
│   │   ├── signals.py            # Audit-log receivers on ECO + ProductCompliance status changes
│   │   ├── forms.py              # ModelForms with file-extension allowlists + 25 MB cap
│   │   ├── views.py              # Full CRUD for all 5 sub-modules + workflow actions
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_plm.py       # Idempotent demo data per tenant
│   │
│   └── bom/                      # MODULE 3 — Bill of Materials Management
│       ├── models.py             # BillOfMaterials, BOMLine (self-FK tree, phantom flag),
│       │                         # BOMRevision (JSON snapshot), AlternateMaterial,
│       │                         # SubstitutionRule, CostElement, BOMCostRollup,
│       │                         # BOMSyncMap, BOMSyncLog
│       ├── signals.py            # Audit-log receivers on BOM status + alternate approval;
│       │                         # BOMLine save/delete invalidates the parent BOM rollup
│       ├── forms.py              # ModelForms with cross-component validation
│       ├── views.py              # Full CRUD + workflow (submit/approve/release/obsolete),
│       │                         # BOMExplodeView, BOMRecomputeRollupView, BOMRollbackView,
│       │                         # AlternateApproveView/RejectView, BOMSyncRunView
│       ├── urls.py
│       ├── admin.py
│       └── management/commands/
│           └── seed_bom.py       # Idempotent demo data per tenant (BOMs + costs + alternates + sync)
│
├── templates/
│   ├── base.html                 # master layout with data-* attrs
│   ├── partials/                 # topbar, sidebar, theme_settings, preloader, footer
│   ├── auth/                     # login, register, forgot_password, reset_password, accept_invite
│   ├── dashboard/index.html
│   ├── accounts/                 # user list/form/detail, profile, invite list/form
│   ├── tenants/                  # onboarding_wizard, plans, subscription, invoices, branding, health, audit, email_templates
│   ├── plm/                      # index, categories/, products/, eco/, cad/, compliance/, npi/
│   └── bom/                      # index, boms/, lines/, revisions/, alternates/, substitution_rules/, cost_elements/, sync_maps/
│
└── static/
    ├── css/style.css             # blue + white theme, all layout variants
    ├── js/app.js                 # theme switcher with localStorage
    └── images/                   # logo SVGs + favicon
```

---

## Requirements

- **Python 3.10+** (tested on 3.10.9)
- **MySQL 8.x** — via **XAMPP** on Windows, or any MySQL instance
- A C compiler toolchain for `mysqlclient`:
  - Windows: Microsoft C++ Build Tools, or install a pre-built wheel (see Troubleshooting)
  - macOS: `brew install mysql-client pkg-config`
  - Linux: `sudo apt-get install build-essential python3-dev default-libmysqlclient-dev pkg-config`

---

## Setup & Installation

All commands below assume **Windows PowerShell**. For bash/zsh substitute the activation step.

### 1. Clone & enter the project

```powershell
git clone https://github.com/mnavaid925/NavMSM.git
cd NavMSM
```

### 2. Create & activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If activation is blocked by execution policy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 3. Install Python dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create the MySQL database

Start **XAMPP → MySQL**, open phpMyAdmin ([http://localhost/phpmyadmin](http://localhost/phpmyadmin)), and run:

```sql
CREATE DATABASE navmsm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. Configure environment

Copy the example file and adjust as needed:

```powershell
Copy-Item .env.example .env
```

Then open `.env` and make sure `DB_USER` / `DB_PASSWORD` match your MySQL (default XAMPP root has no password).

### 6. Migrate the database

```powershell
python manage.py makemigrations core accounts tenants
python manage.py migrate
```

### 7. Create a Django superuser (for `/admin/`)

```powershell
python manage.py createsuperuser
```

> ⚠️ The superuser has `tenant=None` — tenant-scoped pages will appear empty when signed in as it. Use the seeded tenant-admin accounts instead.

### 8. Seed demo data

```powershell
python manage.py seed_data
```

---

## Environment Variables

All settings are read from `.env`. See [`.env.example`](./.env.example) for the full template.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | dev value | Django cryptographic key — **must be changed in production** |
| `DEBUG` | `True` | Toggle debug mode |
| `ALLOWED_HOSTS` | `*` | Comma-separated host list |
| `DB_ENGINE` | `django.db.backends.mysql` | |
| `DB_NAME` | `navmsm` | |
| `DB_USER` / `DB_PASSWORD` | `root` / *(empty)* | XAMPP defaults |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `3306` | |
| `APP_NAME` | `NavMSM` | Displayed in titles |
| `LOGIN_URL` | `/accounts/login/` | |
| `LOGIN_REDIRECT_URL` | `/` | |
| `LOGOUT_REDIRECT_URL` | `/accounts/login/` | |
| `EMAIL_BACKEND` | `console` | Switch to SMTP for production |
| `DEFAULT_FROM_EMAIL` | `no-reply@navmsm.local` | |
| `PAYMENT_GATEWAY` | `mock` | `mock` or a real gateway (Stripe/Razorpay — not wired yet) |

---

## Running the App

```powershell
python manage.py runserver
```

Then open:

- **App** — [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Login** — [http://127.0.0.1:8000/accounts/login/](http://127.0.0.1:8000/accounts/login/)
- **Django admin** — [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## Seeded Demo Data

Running `python manage.py seed_data` creates:

- **4 plans** — Starter ($29/mo), Growth ($99/mo, featured), Pro ($249/mo), Enterprise (custom)
- **3 demo tenants** — Acme Manufacturing, Globex Industries, Stark Production Co.
- **Per tenant (Module 1)** — 1 tenant admin + 4 staff users, 2 pending invites, 1 subscription, 3–6 invoices (mix of paid/open), 30 days of health snapshots, audit log entries, default branding, and 5 default email templates.
- **Per tenant (Module 2 — PLM)** — 8 categories (4 root + 4 child), 20 products spanning all product types with revisions A & B + specs + variants on finished goods, 5 ECOs in mixed statuses (draft / submitted / approved / implemented), 8 CAD documents, 16 compliance records linked to global standards, 3 NPI projects with all 7 stages and 1–3 deliverables per stage. CAD documents are seeded *without* binary files — upload real CAD files via the UI.
- **Per tenant (Module 3 — BOM)** — 5 BOMs (mix of EBOM / MBOM / SBOM) attached to seeded finished-good products with 1 phantom assembly across the set, 27 cost elements covering material / labor / overhead / tooling, 6 alternate materials (mix of approved / pending), 2 substitution rules, an initial release-time `BOMRevision` snapshot per released BOM, an initial cost roll-up per BOM, and 2 `BOMSyncMap` entries — one in sync, one with seeded drift between EBOM and MBOM.
- **Global (shared) catalog** — 8 `ComplianceStandard` records (ISO 9001, ISO 14001, RoHS, REACH, CE, UL, FCC, IPC).

### Demo logins (all share password `Welcome@123`)

| Username | Role | Tenant |
|----------|------|--------|
| `admin_acme` | Tenant Admin | Acme Manufacturing |
| `admin_globex` | Tenant Admin | Globex Industries |
| `admin_stark` | Tenant Admin | Stark Production Co. |

Staff accounts follow the pattern `<slug>_<role>_<n>`, e.g. `acme_production_manager_1`, `globex_supervisor_2`, etc.

The seeder is **idempotent** — running it again will skip existing tenants/plans. Use `--flush` to reset the 3 demo tenants:

```powershell
python manage.py seed_data --flush
```

---

## Multi-Tenancy Model

NavMSM uses the **tenant-FK-per-model** pattern (not DB-schema or subdomain isolation):

1. **`Tenant`** — top-level record ([`apps/core/models.py`](apps/core/models.py)).
2. **`TenantAwareModel`** — abstract base that adds `tenant = ForeignKey(Tenant)` and a custom `TenantManager` that auto-filters queries to the current tenant. Domain models inherit from it — e.g. `class Invoice(TenantAwareModel, TimeStampedModel)`.
3. **`TenantMiddleware`** — for each request, reads `request.user.tenant`, binds it to `request.tenant`, and to a thread-local so model managers can pick it up.
4. **Isolation guard** — `TenantAdminRequiredMixin` + `get_object_or_404(..., tenant=request.tenant)` patterns prevent cross-tenant data access.
5. **`all_objects`** — every `TenantAwareModel` exposes a second manager (`Model.all_objects`) for unscoped system queries in signals, seeders, and cross-tenant utilities.

> 💡 Never use `Model.objects.all()` in user-facing views — always filter by `tenant=request.tenant`.

---

## Authentication & User Management

### Authentication flows

- **Login** — username **or** email + password, "Remember me" toggles session expiry.
- **Register** — creates the `Tenant`, the first `User` (role = `tenant_admin`, `is_tenant_admin=True`), the `UserProfile`, the default `BrandingSettings`, a 14-day trial `Subscription`, and default `EmailTemplate`s — all inside one `transaction.atomic` block.
- **Forgot / Reset password** — standard Django `PasswordResetTokenGenerator`, email sent via the configured backend (console by default). Response never leaks whether the email exists.
- **Accept invite** — token-based URL (`/accounts/invites/accept/<uuid>/`) lets invitees set their own password and join the correct tenant.

### User management

Only **tenant admins** (or Django superusers) can access user CRUD. Features:

- Paginated list with search (name/email/username), role filter, active/inactive filter
- Create, edit, view, delete (with confirm), toggle-active
- Every list row has a View / Edit / Toggle-Active / Delete action column

### Profile

Any authenticated user can edit their own profile — account details, address, **and UI preferences** (theme, layout, sidebar size/color, topbar color, layout width/position, LTR/RTL). Preferences are persisted to `UserProfile` and injected into `<html data-*>` by the `ui_preferences` context processor on every request.

---

## Module 1 — Tenant & Subscription Management

### Sub-module 1.1 — Tenant Onboarding

A 4-step wizard at `/tenants/onboarding/`:

1. **Organization** — name, email, phone, website, industry, timezone, address, logo
2. **Plan** — pick from seeded plans (Starter / Growth / Pro / Enterprise)
3. **Admin** — current user already has `tenant_admin` role
4. **Review & finish** — provisions defaults and redirects to dashboard

### Sub-module 1.2 — Subscription & Billing

- **`Plan`** — price_monthly, price_yearly, trial_days, feature list (JSON), max users / production orders / storage, featured flag
- **`Subscription`** — one per tenant, status (`trial` / `active` / `past_due` / `cancelled` / `paused`), interval, current period, cancel-at-period-end flag, gateway subscription id
- **`Invoice`** + **`InvoiceLineItem`** + **`Payment`** — standard invoicing model with line items, tax, paid-at tracking, and payment refs
- **`BillingAddress`** — per-tenant billing details
- **`UsageMeter`** — tracks metrics (active users, production orders, storage, API calls) per billing period for usage-based billing
- **Mock gateway** — every "Pay Now" action routes through `MockGateway.charge()` which always succeeds, creating a `Payment` record and flipping the invoice to `paid`. See [Payment Gateway Integration](#payment-gateway-integration) for swapping in Stripe / Razorpay.

### Sub-module 1.3 — Tenant Isolation & Security

- **`TenantAwareModel`** abstract base + per-request thread-local tenant
- **`TenantAdminRequiredMixin`** — class-based view guard that only permits `is_tenant_admin=True` or superusers
- **`TenantAuditLog`** — immutable record with `action`, `target_type`, `target_id`, `user`, `ip_address`, `user_agent`, `meta` (JSON), and `timestamp`
- **Audit signals** — `post_save` / `post_delete` on `Subscription` and `BrandingSettings` auto-write audit entries
- **`encryption_key_ref`** — `BrandingSettings` stores a *pointer* to a tenant-specific encryption key; raw secrets are expected in a vault (Key Vault / AWS Secrets Manager / etc.). A `WARNING` comment in [`models.py`](apps/tenants/models.py) documents this.

### Sub-module 1.4 — Custom Branding

- **`BrandingSettings`** (OneToOne) — logo (light/dark), favicon, primary/secondary/sidebar/topbar colors, email-from name & address, footer text, support email & URL
- **`EmailTemplate`** — per-tenant overrides keyed by `code` (`welcome`, `invite`, `password_reset`, `invoice_issued`, `payment_received`, `subscription_cancelled`, `trial_ending`)
- **Runtime theming** — the `tenant_context` context processor injects `branding` into every template, and `base.html` emits `:root { --primary: {{ branding.primary_color }}; ... }` so each tenant's pages are painted with its own palette without a rebuild

### Sub-module 1.5 — Tenant Health Monitoring

- **`TenantHealthSnapshot`** — per-day capture of `active_users`, `storage_mb`, `api_calls_24h`, `error_rate`, `avg_response_ms`, `health_score`
- **`HealthAlert`** — configurable alerts by kind (`error_rate`, `response_time`, `storage`, `api_quota`), threshold, channel (email / webhook / in-app)
- **`capture_health`** command — run on a cron schedule to snapshot every active tenant
- **Dashboard** at `/tenants/health/` — KPI cards + ApexCharts area chart of the last 30 snapshots

---

## Module 2 — Product Lifecycle Management (PLM)

Module 2 is implemented in [`apps/plm/`](apps/plm/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel` and queries are scoped via `request.tenant`.

### Sub-module 2.1 — Product Master Data

- **`ProductCategory`** — hierarchical (self-FK `parent`), unique `(tenant, code)`, `is_active` toggle
- **`Product`** — `sku` unique per tenant, `product_type` (raw_material / component / sub_assembly / finished_good / service), `unit_of_measure`, `status` (draft / active / obsolete / phased_out), nullable FK to `current_revision`, optional product image
- **`ProductRevision`** — revision history (e.g. `A`, `B`) with `effective_date` and status (`draft` / `active` / `superseded`); promoting a revision to *active* auto-supersedes prior actives and updates `Product.current_revision`
- **`ProductSpecification`** — typed key/value pairs (physical / electrical / mechanical / chemical / performance / other), optionally pinned to a revision
- **`ProductVariant`** — variant SKU + free-form attributes JSON (rendered in form as `key=value` lines)

The product detail page exposes these as tabs alongside linked CAD docs and compliance records.

### Sub-module 2.2 — Engineering Change Orders (ECO)

- **`EngineeringChangeOrder`** — auto-numbered `ECO-00001` per tenant, `change_type` (design / specification / material / process / documentation), `priority` (low / medium / high / critical), `requested_by`, status workflow: `draft → submitted → under_review → approved → implemented`, with `rejected` and `cancelled` terminal states
- **`ECOImpactedItem`** — links ECO to one or more `Product`s with optional before/after revision FKs and a per-item change summary
- **`ECOApproval`** — written approval log (approver, decision, comment, decided_at)
- **`ECOAttachment`** — file upload per ECO; allowlist enforced in `forms.py` (`.pdf .dwg .dxf .step .stp .iges .igs .png .jpg .jpeg .svg .zip .docx .xlsx .txt .csv`), 25 MB cap

Workflow buttons on the detail page: **Submit for review** (draft → submitted), **Approve** / **Reject** (submitted/under_review → approved/rejected), **Mark Implemented** (approved → implemented). Edit and delete are gated to `draft` status only.

### Sub-module 2.3 — CAD / Drawing Repository

- **`CADDocument`** — `drawing_number` unique per tenant, `doc_type` (2d_drawing / 3d_model / schematic / pcb / assembly / other), optional FK to `Product`, nullable FK `current_version`
- **`CADDocumentVersion`** — version string + `FileField`, `change_notes`, `uploaded_by`, status (`draft` / `under_review` / `released` / `obsolete`); CAD file allowlist `.pdf .dwg .dxf .step .stp .iges .igs .png .jpg .jpeg .svg .zip` with 25 MB cap

Releasing a version automatically obsoletes any prior released version and promotes the new one to `current_version` — there is always exactly one current version per drawing.

### Sub-module 2.4 — Product Compliance Tracking

- **`ComplianceStandard`** — *shared* catalog (NOT tenant-scoped, like `Plan`) pre-seeded with 8 standards: ISO 9001, ISO 14001, RoHS, REACH, CE, UL, FCC, IPC
- **`ProductCompliance`** — links a `Product` to a `ComplianceStandard` with status (`pending` / `in_progress` / `compliant` / `non_compliant` / `expired`), `certification_number`, `issuing_body`, `issued_date`, `expiry_date`, optional `certificate_file`. Unique per `(tenant, product, standard)`.
- **`ComplianceAuditLog`** — immutable per-record trail; entries are written automatically by signals on create and on every status change

The list page surfaces an *Expiring within 30 days* counter and a per-row expiry warning icon. Certificate file allowlist: `.pdf .png .jpg .jpeg .zip`.

### Sub-module 2.5 — NPI / Stage-Gate Management

- **`NPIProject`** — auto-numbered `NPI-00001` per tenant, optional FK to `Product`, `project_manager`, `current_stage` (concept / feasibility / design / development / validation / pilot_production / launch), `status` (planning / in_progress / on_hold / completed / cancelled), target/actual launch dates
- **`NPIStage`** — pre-populated automatically when a project is created (one row per stage, sequenced 1-7), with `planned_start/end`, `actual_start/end`, `status` (pending / in_progress / passed / failed / skipped), `gate_decision` (pending / go / no_go / recycle), `gate_notes`, `gate_decided_by`
- **`NPIDeliverable`** — per-stage tasks with `owner`, `due_date`, `completed_at`, status (pending / in_progress / done / blocked)

The detail page renders the 7 stages as a Bootstrap accordion with inline deliverable add/edit/complete/delete forms. Editing a stage's `gate_decision` from `pending` automatically stamps `gate_decided_by` and `gate_decided_at`.

### Audit signals

`apps/plm/signals.py` wires:

- `pre_save` + `post_save` on `EngineeringChangeOrder` → writes `apps.tenants.TenantAuditLog` entries on every status transition (`eco.created`, `eco.status.<new>` with `meta={'from': old, 'to': new}`)
- `pre_save` + `post_save` on `ProductCompliance` → writes BOTH `TenantAuditLog` and a per-record `ComplianceAuditLog` entry on create and on status change

### File-upload security

Three auth-gated download views ([`apps/plm/views.py`](apps/plm/views.py) — `CADVersionDownloadView`, `ECOAttachmentDownloadView`, `ComplianceCertificateDownloadView`) protect PLM uploads. Each verifies tenant ownership via `get_object_or_404(..., tenant=request.tenant)` then streams via `FileResponse`. Templates link to these via `{% url %}` rather than `.file.url`, so a guessed `/media/plm/...` path would still hit the static mount in DEBUG but is never produced by the application.

> **Production hardening required:** remove the `static(MEDIA_URL, ...)` mount in [`config/urls.py`](config/urls.py) when `DEBUG=False` and configure the web server (Nginx `internal;` + `X-Accel-Redirect`, or Apache `mod_xsendfile`) to serve `MEDIA_ROOT/plm/*` ONLY via the auth-gated views. Documented in the views.py module docstring.

File-extension allowlists (defined in [`apps/plm/forms.py`](apps/plm/forms.py)):

| Surface | Allowed extensions | Notes |
|---|---|---|
| CAD version files | `.pdf .dwg .dxf .step .stp .iges .igs .png .jpg .jpeg .zip` | `.svg` deliberately excluded — XSS risk via embedded `<script>` |
| ECO attachments | CAD allowlist + `.docx .xlsx .txt .csv` | |
| Compliance certificates | `.pdf .png .jpg .jpeg .zip` | |

All uploads are capped at **25 MB**.

---

## Module 3 — Bill of Materials (BOM) Management

Module 3 is implemented in [`apps/bom/`](apps/bom/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel` and every query is scoped via `request.tenant`. BOMs link to existing PLM `Product` records — the BOM module deliberately *reuses* the part master from PLM rather than maintaining a parallel one.

### Sub-module 3.1 — Multi-Level BOM

- **`BillOfMaterials`** — auto-numbered `BOM-00001` per tenant, FK to `plm.Product` (the parent assembly), `bom_type` discriminator (`ebom` / `mbom` / `sbom`), `version` + `revision`, `status` workflow (`draft → under_review → approved → released → obsolete`), `is_default` flag, effective-date window, `created_by` / `approved_by` / `released_at` audit stamps. Unique per `(tenant, product, bom_type, version, revision)`.
- **`BOMLine`** — one row per component with self-FK `parent_line` (enables multi-level trees), `sequence`, FK to component `Product`, `quantity`, `unit_of_measure`, `scrap_percent`, `is_phantom` flag, `reference_designator`, `notes`.
- **Phantom assemblies** — when `is_phantom=True`, `BillOfMaterials.explode()` collapses the line transparently: the phantom itself is *not* yielded but its child components are emitted at the level the phantom would have occupied, with quantities multiplied through. This keeps phantoms out of MRP while preserving structural grouping in engineering data.
- **Recursive explosion** — `BillOfMaterials.explode()` is a generator yielding `(level, line, expanded_qty)` tuples; each line's effective quantity is `quantity × (1 + scrap%/100) × parent_qty`. Used by the `/bom/boms/<pk>/explode/` view.

### Sub-module 3.2 — BOM Versioning & Revision

- **`BOMRevision`** — immutable JSON snapshot of the full BOM tree taken at any point. Fields: `version`, `revision`, `revision_type` (`major` / `minor` / `engineering` / `rollback`), `change_summary`, `effective_from`, `snapshot_json`, `changed_by`. Every release auto-captures one of these.
- **Rollback** — `BOMRollbackView` reads `snapshot_json` and rebuilds the line tree (matching components by SKU); a new `revision_type='rollback'` entry is logged so the audit trail shows what happened. Only available while the BOM is `draft` or `under_review`.

### Sub-module 3.3 — Alternative & Substitute Materials

- **`AlternateMaterial`** — per-line alternates with `priority` (1 = preferred), `substitution_type` (`direct` / `approved` / `emergency` / `one_to_one` / `one_to_many`), `usage_rule` text, and an `approval_status` workflow (`pending` / `approved` / `rejected`) gated by `AlternateApproveView` / `AlternateRejectView`. Approval timestamps the actor.
- **`SubstitutionRule`** — tenant-level reusable equivalence catalog (e.g. "any 10kΩ 1% resistor in 0805 package"). Includes `condition_text`, `requires_approval`, `is_active`. Validates that original and substitute components differ.

### Sub-module 3.4 — BOM Cost Roll-Up

- **`CostElement`** — current cost per part per `cost_type` (`material` / `labor` / `overhead` / `tooling` / `other`) with `unit_cost`, `currency` (defaults `USD`), `effective_date`, `source` (`manual` / `vendor` / `computed`). Unique per `(tenant, product, cost_type)`.
- **`BOMCostRollup`** — computed snapshot per BOM with five cost buckets and a total. Recomputed on demand via `BOMRecomputeRollupView`. The detail page shows it as **stale** (`computed_at IS NULL`) when any line is added / edited / deleted — a `post_save` / `post_delete` signal on `BOMLine` invalidates the rollup so the user knows to recompute.
- **Sub-assembly cost cascade** — when a component has no direct `CostElement`, the rollup falls back to the unit total of the component's *default released* BOM (`is_default=True, status='released'`). This is the safe, predictable choice — explicit costs always win, and fallback only walks one level down per call (no runaway recursion).

### Sub-module 3.5 — EBOM / MBOM / SBOM Synchronization

- The `BillOfMaterials.bom_type` field discriminates the three views. A single Product can have one EBOM, one MBOM, and one SBOM (each with its own version line).
- **`BOMSyncMap`** — links a source BOM to a target BOM (typically EBOM → MBOM, or MBOM → SBOM). Validates that source and target have *different* `bom_type` values. Carries `sync_status` (`pending` / `in_sync` / `drift_detected` / `manual_override`), `last_synced_at`, `synced_by`, and a free-text `drift_summary`.
- **`BOMSyncLog`** — append-only event log, one row per sync run, with `before_json` / `after_json`, `actor`, and `notes`.
- **Drift detection** — `BOMSyncRunView` flattens both BOMs to `{component_sku → quantity}` dicts and reports: components only in source, only in target, and components present in both with different quantities. If the dicts match, the map flips to `in_sync`; otherwise to `drift_detected`. Either outcome is logged.

### Audit signals

[`apps/bom/signals.py`](apps/bom/signals.py) wires:

- `pre_save` + `post_save` on `BillOfMaterials` → writes `apps.tenants.TenantAuditLog` entries on every status transition (`bom.created`, `bom.status.<new>` with `meta={'from': old, 'to': new}`).
- `post_save` on `AlternateMaterial` → writes audit entries when approval status changes.
- `post_save` / `post_delete` on `BOMLine` → invalidates the parent BOM's `BOMCostRollup.computed_at` so the UI shows the rollup as stale until recomputed.

### Workflow buttons (BOM detail page)

| From | Action button | To |
|---|---|---|
| `draft` | Submit for review | `under_review` |
| `draft` | Edit / Delete | (mutating) |
| `under_review` | Approve | `approved` |
| `under_review` | Reject | `draft` |
| `under_review` | Edit | (mutating) |
| `approved` | Release | `released` (and a `BOMRevision` snapshot is captured; any prior released BOM with the same product+bom_type is auto-marked `obsolete`) |
| `approved` | Obsolete | `obsolete` |
| `released` | Obsolete | `obsolete` |

All workflow transitions use a conditional `UPDATE … WHERE status IN (…)` so two reviewers racing each other can't double-action — only one wins.

---

## UI / Theme Customization

The `<html>` element carries eight attributes that control every aspect of the layout; they're set from `UserProfile` on page load and can be changed live via the theme panel (`⚙️ icon in topbar`) — changes persist to both `localStorage` and the user profile.

| Attribute | Values | Effect |
|-----------|--------|--------|
| `data-layout` | `vertical` / `horizontal` / `detached` | Main layout mode |
| `data-theme` | `light` / `dark` | Overall color scheme |
| `data-topbar` | `light` / `dark` | Topbar background |
| `data-sidebar` | `light` / `dark` / `brand` | Sidebar background |
| `data-sidebar-size` | `default` / `compact` / `small` / `hover` | Sidebar width & label visibility |
| `data-layout-width` | `fluid` / `boxed` | Content container width |
| `data-layout-position` | `fixed` / `scrollable` | Whether the topbar stays pinned |
| `dir` | `ltr` / `rtl` | Text direction |

The switcher logic lives in [`static/js/app.js`](static/js/app.js) and reads/writes a single `navmsm.ui` key in `localStorage`. Tapping the **Reset to Default** button in the offcanvas wipes the override.

---

## Management Commands

| Command | Purpose |
|---------|---------|
| `python manage.py migrate` | Apply database migrations |
| `python manage.py createsuperuser` | Create a Django superuser for `/admin/` |
| `python manage.py seed_plans` | Seed/update the 4 default plans |
| `python manage.py seed_tenants [--flush]` | Seed 3 demo tenants with users, invoices, health snapshots |
| `python manage.py seed_plm [--flush]` | Seed PLM demo data (categories, products, ECOs, CAD, compliance, NPI) per tenant |
| `python manage.py seed_bom [--flush]` | Seed BOM demo data (BOMs, lines, alternates, substitution rules, cost elements, sync maps) per tenant |
| `python manage.py seed_data [--flush]` | Orchestrator that runs `seed_plans` + `seed_tenants` + `seed_plm` + `seed_bom` |
| `python manage.py capture_health` | Capture a fresh health snapshot for every active tenant (schedule via cron) |
| `python manage.py runserver` | Dev server on port 8000 |
| `pytest apps/plm/tests/` | Run the PLM test suite (51 tests, ~3 s; uses [`config/settings_test.py`](config/settings_test.py)) |
| `pytest --cov=apps/plm` | Run with coverage report |

---

## Payment Gateway Integration

The billing layer sits behind a **`PaymentGateway`** protocol in [`apps/tenants/services/gateway.py`](apps/tenants/services/gateway.py):

```python
class PaymentGateway(Protocol):
    name: str
    def charge(self, *, amount, currency, description, customer_ref='', metadata=None) -> ChargeResult: ...
    def refund(self, *, gateway_ref, amount) -> ChargeResult: ...
    def webhook_verify(self, payload: bytes, signature: str) -> bool: ...
```

Today `MockGateway` is the only implementation and always returns success. To wire in Stripe / Razorpay / others:

1. Add the SDK to `requirements.txt` (e.g. `stripe`)
2. Implement the protocol in `services/gateway.py` (e.g. `class StripeGateway`)
3. Extend `get_gateway()` to dispatch on `settings.PAYMENT_GATEWAY`
4. Add webhook URL(s) to `config/urls.py` and verify signatures via `webhook_verify()`

> ⚠️ **Security reminders** (documented in the source):
> - Never trust a client-submitted `amount` — derive it from the server-side `Invoice`.
> - Always verify webhook signatures with the gateway's shared secret.
> - Store only tokenized references — never raw PANs.
> - Run over HTTPS with `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True` in production.

---

## Security Notes

- **CSRF** — every POST form carries `{% csrf_token %}`; state-changing actions (delete, toggle-active, cancel subscription, pay invoice) are POST-only.
- **Authorization** — tenant-scoped views use `LoginRequiredMixin`; admin-only views use `TenantAdminRequiredMixin`; every detail/edit view loads the target with `get_object_or_404(Model, pk=..., tenant=request.tenant)`.
- **Password validation** — Django's full validator stack is enabled.
- **Email enumeration** — forgot-password responses never disclose whether an account exists.
- **Thread-local tenant** — cleared in `TenantMiddleware`'s `finally` clause so a stale tenant cannot leak into background threads that reuse the worker.
- **Secrets** — keep `SECRET_KEY`, DB creds, email SMTP creds, and payment gateway keys in `.env` (never committed). `.env` is in `.gitignore`.
- **Superuser caveat** — Django's default superuser has `tenant=None`; intended for system administration only.

---

## Roadmap

Phase 1 (this release) covers the platform + **Module 1** (Tenant & Subscription), **Module 2** (Product Lifecycle Management), and **Module 3** (Bill of Materials). The 19 upcoming modules are fully specified in [`MSM.md`](./MSM.md):

2. ~~Product Lifecycle Management (PLM)~~ ✅ shipped
3. ~~Bill of Materials (BOM)~~ ✅ shipped
4. Production Planning & Scheduling
5. Material Requirements Planning (MRP)
6. Shop Floor Control (MES)
7. Quality Management (QMS)
8. Inventory & Warehouse
9. Procurement & Supplier Portal
10. Equipment & Asset Management (EAM)
11. Labor & Workforce Management
12. Cost Management & Accounting
13. Compliance & Regulatory
14. Energy & Utility Management
15. IoT & SCADA Integration
16. Business Intelligence & Analytics
17. Sales & Customer Order Management
18. Returns & RMA
19. Document & Knowledge Management
20. Workflow & Business Process Automation
21. API & Integration Gateway
22. System Administration & Security

Additional technical to-dos outside the module list:

- Real payment gateway (Stripe / Razorpay) + webhook endpoints
- SMTP email backend + HTML template rendering of `EmailTemplate` records
- Unit + integration tests (pytest-django)
- CI pipeline (lint + tests + migration check)
- Docker Compose for MySQL + app
- i18n / translation files
- Accessibility audit (WCAG 2.1 AA)

---

## Troubleshooting

### `mysqlclient` fails to install on Windows

Install a pre-built wheel:

```powershell
pip install --only-binary :all: mysqlclient
```

If that fails, download the matching wheel from [PyPI](https://pypi.org/project/mysqlclient/#files) for your Python version and install it:

```powershell
pip install .\mysqlclient-2.2.8-cpXY-cpXY-win_amd64.whl
```

### `django.db.utils.OperationalError: (1049, "Unknown database 'navmsm'")`

Create the database in phpMyAdmin (see [Setup → step 4](#4-create-the-mysql-database)).

### `Access denied for user 'root'@'localhost'`

Edit `.env` — set `DB_PASSWORD` to your MySQL root password (XAMPP default is empty).

### Dashboard is empty even after seeding

You're likely signed in as the Django superuser, which has `tenant=None`. Sign out and log in as one of the seeded tenant admins (`admin_acme` / `Welcome@123`).

### PowerShell: `&&` causes a ParserError

Windows PowerShell doesn't support `&&` as a statement separator. Use `;` instead:

```powershell
python manage.py migrate; python manage.py seed_data
```

### `Set-ExecutionPolicy` error activating venv

Run PowerShell once with:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## License

See [`LICENSE`](./LICENSE).

---

**Built for manufacturing excellence** 🏭
