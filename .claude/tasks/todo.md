# Plan — Module 2: Product Lifecycle Management (PLM)

> Status: **COMPLETE — all 5 sub-modules implemented, migrated, seeded, and smoke-tested**
> Created: 2026-04-25
> Completed: 2026-04-25
> Owner: Navaid

## Review (post-implementation)

- 13 list/form pages render 200, 5 detail pages render 200, cross-tenant
  isolation verified (globex returns 404 on acme's product).
- `python manage.py makemigrations plm` → `0001_initial.py` clean.
- `python manage.py migrate plm` → applied successfully.
- `python manage.py seed_plm` → idempotent (second run skips per tenant).
- `python manage.py seed_data` orchestrator now chains
  `seed_plans → seed_tenants → seed_plm`.
- Per tenant: 8 categories, 20 products (with revisions A & B), 5 ECOs in
  mixed statuses, 8 CAD docs, 16 compliance records, 3 NPI projects each
  with 7 stages and 1–3 deliverables per stage.
- Global catalog: 8 ComplianceStandards (ISO 9001, ISO 14001, RoHS, REACH,
  CE, UL, FCC, IPC).
- Pagination warning on category list resolved with explicit
  `.order_by('name')`.
- ECO file allowlist enforced in form clean: `.pdf .dwg .dxf .step .stp
  .iges .igs .png .jpg .jpeg .svg .zip .docx .xlsx .txt .csv`, max 25 MB.
- CAD file allowlist: same minus office/text formats.
- Compliance certificate allowlist: `.pdf .png .jpg .jpeg .zip`.
- Audit-log signals wired: ECO status changes write `TenantAuditLog`
  entries (`eco.status.<new>`); ProductCompliance status changes write
  to both `TenantAuditLog` and a per-record `ComplianceAuditLog` trail.

## Out of scope (deferred)

- BOM linkage (Module 3), inventory (8), procurement (9), workflow engine
  for ECO routing rules — all stubbed via `Product` FKs ready for use.
- Real CAD viewer; CAD seed creates docs without binary files (real files
  must be uploaded via the UI).


This module follows the `apps/tenants/` blueprint exactly (TenantAwareModel,
TenantRequiredMixin / TenantAdminRequiredMixin, full CRUD per CLAUDE.md,
idempotent seeders, multi-tenant filtering on every queryset).

---

## 1. App scaffolding

- [ ] Create `apps/plm/` Django app with: `__init__.py`, `apps.py`, `models.py`,
      `forms.py`, `views.py`, `urls.py`, `admin.py`, `signals.py`,
      `migrations/__init__.py`, `management/__init__.py`,
      `management/commands/__init__.py`, `management/commands/seed_plm.py`
- [ ] Register `apps.plm` in `config/settings.py` `INSTALLED_APPS`
- [ ] Mount `path('plm/', include('apps.plm.urls'))` in `config/urls.py`
- [ ] Add a "Product Lifecycle (PLM)" collapsible group to
      `templates/partials/sidebar.html` with sub-links for the 5 sub-modules
- [ ] Create `templates/plm/` with sub-folders per sub-module

---

## 2. Sub-module 2.1 — Product Master Data

**Models** (all `TenantAwareModel + TimeStampedModel` unless noted):

- [ ] `ProductCategory` — `name`, `code`, `parent` (self-FK, nullable),
      `description`, `is_active`. Unique `(tenant, code)`.
- [ ] `Product` — `sku` (unique per tenant), `name`, `category` FK,
      `product_type` choices (`raw_material`, `component`, `sub_assembly`,
      `finished_good`, `service`), `unit_of_measure`, `description`,
      `status` choices (`draft`, `active`, `obsolete`, `phased_out`),
      `current_revision` FK to `ProductRevision` (nullable, related_name='+').
- [ ] `ProductRevision` — `product` FK, `revision_code` (e.g. "A", "B"),
      `effective_date`, `status` (`draft`, `active`, `superseded`),
      `change_notes`. Unique `(product, revision_code)`.
- [ ] `ProductSpecification` — `product` FK, `revision` FK (nullable),
      `key`, `value`, `unit` (blank), `spec_type` (`physical`, `electrical`,
      `mechanical`, `chemical`, `other`).
- [ ] `ProductVariant` — `product` FK, `variant_sku` (unique per tenant),
      `name`, `attributes` JSONField, `status` (`active`/`inactive`).

**Views (CRUD for each main model — Category, Product, Revision, Variant):**

- [ ] `category_list_view` (search + active filter) / `_create_view` /
      `_detail_view` / `_edit_view` / `_delete_view`
- [ ] `product_list_view` (search by sku/name; filter by category, type, status)
      + create/detail/edit/delete; on detail show specs + revisions + variants tabs
- [ ] `revision_create_view` / `_edit_view` / `_delete_view` (nested under product)
- [ ] `specification_create_view` / `_delete_view` (inline on product detail)
- [ ] `variant_create_view` / `_edit_view` / `_delete_view`

---

## 3. Sub-module 2.2 — Engineering Change Orders (ECO)

**Models:**

- [ ] `EngineeringChangeOrder` — `number` auto `ECO-00001` per tenant,
      `title`, `description`, `change_type` (`design`, `specification`,
      `material`, `process`, `documentation`),
      `priority` (`low`, `medium`, `high`, `critical`),
      `reason`, `requested_by` FK accounts.User,
      `status` (`draft`, `submitted`, `under_review`, `approved`, `rejected`,
      `implemented`, `cancelled`),
      `target_implementation_date`, `approved_at`, `implemented_at`.
- [ ] `ECOImpactedItem` — `eco` FK, `product` FK, `change_summary` (text),
      `before_revision` FK ProductRevision (nullable), `after_revision` FK (nullable).
- [ ] `ECOApproval` — `eco` FK, `approver` FK accounts.User,
      `decision` (`pending`, `approved`, `rejected`), `comment`, `decided_at`.
- [ ] `ECOAttachment` — `eco` FK, `title`, `file` (FileField, `upload_to='plm/eco/'`),
      `uploaded_by` FK, `uploaded_at`.

**Views (full CRUD on ECO; nested for impacted items / approvals / attachments):**

- [ ] `eco_list_view` (search by number/title; filter by status, priority, change_type)
- [ ] `eco_create_view` / `_detail_view` (with impacted-items, approvals, attachments tabs)
      / `_edit_view` (only if status=draft) / `_delete_view` (only if status=draft)
- [ ] `eco_submit_view` (POST — draft → submitted)
- [ ] `eco_approve_view` / `eco_reject_view` (POST — sets ECOApproval + flips status)
- [ ] `eco_implement_view` (POST — approved → implemented; stamps `implemented_at`)
- [ ] Impacted-item / approval / attachment add+delete views

**Signals:**

- [ ] `post_save` on `EngineeringChangeOrder` → write `TenantAuditLog` entry on
      status changes (mirrors the tenants/signals.py pattern)

---

## 4. Sub-module 2.3 — CAD / Drawing Repository

**Models:**

- [ ] `CADDocument` — `product` FK (nullable; some drawings are tooling/general),
      `drawing_number` (unique per tenant), `title`,
      `doc_type` (`2d_drawing`, `3d_model`, `schematic`, `pcb`, `assembly`, `other`),
      `description`, `current_version` FK CADDocumentVersion (nullable, related_name='+'),
      `is_active`.
- [ ] `CADDocumentVersion` — `document` FK, `version` (e.g. "1.0", "1.1"),
      `file` FileField (`upload_to='plm/cad/'`),
      `change_notes`, `uploaded_by` FK accounts.User,
      `status` (`draft`, `under_review`, `released`, `obsolete`),
      `released_at`. Unique `(document, version)`.

**Views:**

- [ ] `cad_list_view` (search by drawing_number/title; filter by type, product, active)
- [ ] `cad_create_view` / `_detail_view` (lists all versions, mark current,
      download links) / `_edit_view` / `_delete_view`
- [ ] `cad_version_upload_view` (POST upload new version; auto-bumps current)
- [ ] `cad_version_release_view` (POST — flips draft → released, stamps `released_at`)
- [ ] `cad_version_delete_view`

**Security note:** validate uploaded file extensions against an allowlist
(`.pdf`, `.dwg`, `.dxf`, `.step`, `.stp`, `.iges`, `.igs`, `.png`, `.jpg`, `.jpeg`,
`.svg`, `.zip`); reject everything else to avoid arbitrary file storage.

---

## 5. Sub-module 2.4 — Product Compliance Tracking

**Models:**

- [ ] `ComplianceStandard` — NOT tenant-scoped (shared catalog like `Plan`):
      `code` (unique, e.g. `ISO_9001`, `RoHS`, `REACH`, `CE`, `UL`, `FCC`, `IPC`),
      `name`, `description`, `region` (`global`, `us`, `eu`, `apac`, …),
      `is_active`. Pre-seeded with the standard set.
- [ ] `ProductCompliance` — `product` FK, `standard` FK,
      `status` (`pending`, `in_progress`, `compliant`, `non_compliant`, `expired`),
      `certification_number` (blank), `issued_date`, `expiry_date`,
      `certificate_file` FileField (blank), `issuing_body` (blank), `notes`.
      Unique `(tenant, product, standard)`.
- [ ] `ComplianceAuditLog` (immutable, no edit/delete UI) — `compliance` FK,
      `event` (`created`, `status_changed`, `renewed`, `expired`, `note_added`),
      `performed_by` FK accounts.User, `performed_at`, `meta` JSONField.

**Views:**

- [ ] `compliance_list_view` (search by product/cert#; filter by standard + status;
      shows expiring-within-30-days flag in the row)
- [ ] `compliance_create_view` / `_detail_view` (with audit-trail tab)
      / `_edit_view` / `_delete_view`
- [ ] `standard_list_view` (read-only catalog page, admins only via Django admin)

**Signals:**

- [ ] `post_save` on `ProductCompliance` → write `ComplianceAuditLog` entry
      whenever `status` changes

---

## 6. Sub-module 2.5 — NPI / Stage-Gate Management

**Models:**

- [ ] `NPIProject` — `code` auto `NPI-00001` per tenant, `name`, `description`,
      `product` FK (nullable — project may precede the product record),
      `project_manager` FK accounts.User,
      `status` (`planning`, `in_progress`, `on_hold`, `completed`, `cancelled`),
      `current_stage` choice field (mirrors `NPIStage.STAGE_CHOICES`),
      `target_launch_date`, `actual_launch_date`.
- [ ] `NPIStage` — `project` FK,
      `stage` (`concept`, `feasibility`, `design`, `development`,
      `validation`, `pilot_production`, `launch`),
      `sequence` PositiveInt,
      `planned_start`, `planned_end`, `actual_start`, `actual_end`,
      `status` (`pending`, `in_progress`, `passed`, `failed`, `skipped`),
      `gate_decision` (`pending`, `go`, `no_go`, `recycle`),
      `gate_notes`, `gate_decided_by` FK (nullable), `gate_decided_at`.
      Unique `(project, stage)`.
- [ ] `NPIDeliverable` — `stage` FK, `name`, `description`,
      `owner` FK accounts.User, `due_date`, `completed_at`,
      `status` (`pending`, `in_progress`, `done`, `blocked`).

**Views:**

- [ ] `npi_list_view` (search by code/name; filter by status, current_stage)
- [ ] `npi_create_view` / `_detail_view` (Gantt-ish stage timeline + deliverables list)
      / `_edit_view` / `_delete_view`
- [ ] `npi_stage_advance_view` (POST — closes current stage with gate_decision,
      auto-creates next stage if not present, updates project.current_stage)
- [ ] `deliverable_create_view` / `_edit_view` / `_delete_view` /
      `_complete_view` (POST flag done)

---

## 7. Templates (under `templates/plm/`)

Each sub-module gets its own folder. List + form + detail templates
mirror `templates/tenants/invoices.html` / `branding.html` patterns.

- [ ] `plm/products/` — list, form, detail (tabs: Overview / Specs / Revisions / Variants), category_list, category_form
- [ ] `plm/eco/` — list, form, detail (tabs: Items / Approvals / Attachments)
- [ ] `plm/cad/` — list, form, detail (with version history + upload form)
- [ ] `plm/compliance/` — list, form, detail (with audit trail)
- [ ] `plm/npi/` — list, form, detail (with stages + deliverables)

All list templates MUST include the standard search input + status filter +
View / Edit / Delete actions column per CLAUDE.md "CRUD Completeness Rules".

---

## 8. Admin

- [ ] Register every model in `apps/plm/admin.py` with `list_display`,
      `list_filter`, `search_fields`, and inlines for child models
      (e.g. `ProductSpecificationInline` on `ProductAdmin`).

---

## 9. Forms

- [ ] One ModelForm per CRUD-able model (mirrors `apps/tenants/forms.py`).
- [ ] File-upload forms validate extensions for CAD + ECO attachments +
      compliance certificates.

---

## 10. Migrations

- [ ] `python manage.py makemigrations plm`
- [ ] `python manage.py migrate plm`

---

## 11. Seed command — `seed_plm`

Idempotent per CLAUDE.md "Seed Command Rules":

- [ ] For each existing tenant, skip if `Product.objects.filter(tenant=t).exists()`
- [ ] Create:
  - 8 categories (3 root + 5 children)
  - 20 products spanning all product_types, with revisions A & B
  - 5 ECOs in mixed statuses (draft / submitted / approved / implemented)
  - 8 CAD documents with 1–3 versions each
  - 12 compliance records across standards (RoHS, REACH, ISO_9001, CE, UL)
  - 3 NPI projects in different stages with deliverables
- [ ] Pre-seed `ComplianceStandard` global catalog (idempotent get_or_create)
- [ ] Hook into `apps/core/management/commands/seed_data.py` to call
      `seed_plm` after `seed_tenants` (only if `--with-plm` flag passed,
      or default-on — TBD with user)

---

## 12. Verification (per CLAUDE.md "Verification Before Done")

- [ ] `python manage.py makemigrations --check --dry-run` — no missing migrations
- [ ] `python manage.py migrate` — applies cleanly on a fresh DB
- [ ] `python manage.py seed_plm` — runs idempotently (twice in a row, no errors)
- [ ] `python manage.py runserver` — manually visit each list / detail / form
      page as `admin_acme` and confirm CRUD works for at least one model in
      each sub-module
- [ ] Every list page filter actually filters (per CLAUDE.md "Filter
      Implementation Rules")
- [ ] Cross-tenant isolation: log in as `admin_globex` and confirm Acme's
      products don't appear

---

## 13. Out of scope (deferred to later modules)

- BOM linkage (Module 3) — `Product.boms` reverse relation will wire up later
- Inventory linkage (Module 8) — stock balances per product
- Procurement linkage (Module 9) — supplier bindings on products
- Real-time collaboration / live preview on CAD viewer
- Workflow engine for ECO routing rules (a hard-coded linear approval is fine for now)

---

## 14. Per-file git commits (per CLAUDE.md GIT Commit Rule)

After each file is added/changed, the assistant will hand the user a
single-line `git add 'path'; git commit -m '...'` snippet (PowerShell-safe,
NEVER `&&`). Final delivery includes a "single copy" block aggregating all
commits for one paste.
