# Module 18 — Returns & RMA Management — Implementation Plan

**App:** `apps/rma/` · **URL prefix:** `/rma/` · **Reference module:** `apps/sales/` (Module 17, most recent)
**Scope confirmed:** Full cross-module hooks + full pytest test suite.

---

## 0. Sub-module → model map

| # | Sub-module | Models |
|---|---|---|
| 18.1 | RMA Request & Authorization | `RMAReason`, `RMARequest` (auto `RMA-00001`), `RMALine`, `RMAApproval` |
| 18.2 | Returns Receiving & Inspection | `ReturnReceipt` (auto `RR-00001`), `ReturnReceiptLine` |
| 18.3 | Repair & Refurbishment Tracking | `RepairOrder` (auto `REP-00001`), `RepairPartUsage`, `RepairLaborLog` |
| 18.4 | Warranty Management | `WarrantyPolicy` (auto `WP-00001`), `WarrantyRegistration` (auto `WR-00001`), `WarrantyClaim` (auto `WC-00001`) |
| 18.5 | Returns Analytics | `FailureMode`, `RootCauseCategory`, `ReturnAnalysis` (auto `RA-00001`), `SupplierChargeback` (auto `SCB-00001`) |

All models inherit `TenantAwareModel, TimeStampedModel`. Auto-numbering via `services/numbering.next_code()` assigned in `save()` before `super().save()`. Decimal fields get `MinValueValidator`/`MaxValueValidator` (L-02). Audit/log child FKs use `on_delete=PROTECT` (L-17); structural children use `CASCADE`.

### Key model fields (condensed)

- **RMAReason** — `name`, `description`, `category` (quality_defect/shipping_damage/wrong_item/customer_change/warranty/other), `is_active`; `unique_together(tenant,name)`.
- **RMARequest** — `code`, `customer` FK→`sales.Customer` PROTECT, `sales_order` FK→`sales.SalesOrder` SET_NULL null, `sales_invoice` FK→`sales.SalesInvoice` SET_NULL null, `request_date`, `requested_action` (refund/replace/repair/credit_note), `status` (draft→submitted→approved/rejected→cancelled), `customer_reference`, `reason_summary`, `customer_notes`, `internal_notes`, `submitted_at`, `decided_at`, `decided_by` FK→User SET_NULL, `decision_notes`.
- **RMALine** — `rma` FK CASCADE, `product` FK→`plm.Product` PROTECT, `quantity`, `unit_price`, `reason` FK→RMAReason PROTECT, `lot_number`, `serial_number`, `condition_reported`, `line_notes`.
- **RMAApproval** — append-only log: `rma` FK PROTECT, `decision` (approved/rejected), `decided_by` FK→User SET_NULL, `notes`.
- **ReturnReceipt** — `code`, `rma` FK PROTECT, `warehouse` FK→`inventory.Warehouse` SET_NULL null, `received_date`, `received_by` FK→User SET_NULL, `status` (draft→inspecting→completed→cancelled), `notes`.
- **ReturnReceiptLine** — `receipt` FK CASCADE, `rma_line` FK PROTECT, `quantity_received`, `condition_assessed` (new/like_new/used/damaged/defective/scrap), `disposition` (restock/repair/refurbish/scrap/return_to_supplier/quarantine), `inspection_notes`, `inspected_by` FK→User SET_NULL, `disposition_done` bool (signal idempotency flag), `stock_movement` FK→`inventory.StockMovement` SET_NULL null.
- **RepairOrder** — `code`, `receipt_line` FK→ReturnReceiptLine PROTECT null/blank, `product` FK→`plm.Product` PROTECT, `order_type` (repair/refurbishment), `status` (draft→in_progress→on_hold→completed→cancelled), `problem_description`, `repair_instructions`, `resolution_notes`, `assigned_to` FK→User SET_NULL null, `started_at`, `completed_at`, `estimated_cost`, `actual_cost` (denorm), `labor_minutes` (denorm).
- **RepairPartUsage** — `repair_order` FK CASCADE, `part` FK→`plm.Product` PROTECT, `quantity`, `unit_cost`, `stock_movement` FK→`inventory.StockMovement` SET_NULL null, `notes`.
- **RepairLaborLog** — `repair_order` FK CASCADE, `employee` FK→`labor.Employee` SET_NULL null, `work_date`, `minutes`, `hourly_rate`, `labor_cost` (computed in save), `labor_booking` FK→`labor.LaborBooking` SET_NULL null, `notes`.
- **WarrantyPolicy** — `code`, `name`, `coverage_type` (parts/labor/parts_and_labor/full), `duration_months`, `terms`, `product` FK→`plm.Product` SET_NULL null/blank, `product_category` FK→`plm.ProductCategory` SET_NULL null/blank, `is_active`.
- **WarrantyRegistration** — `code`, `product` FK→`plm.Product` PROTECT, `customer` FK→`sales.Customer` PROTECT, `policy` FK→WarrantyPolicy PROTECT, `serial_number`, `purchase_date`, `start_date`, `end_date` (computed in save = start_date + duration_months), `status` (active/expired/void/claimed), `sales_order` FK→`sales.SalesOrder` SET_NULL null, `notes`.
- **WarrantyClaim** — `code`, `registration` FK→WarrantyRegistration PROTECT, `rma` FK→RMARequest SET_NULL null/blank, `claim_date`, `status` (submitted→validated→approved/rejected→fulfilled), `defect_description`, `resolution` (repair/replace/refund/credit), `validation_notes`, `decided_by` FK→User SET_NULL, `decided_at`, `replacement_order` FK→`sales.SalesOrder` SET_NULL null.
- **FailureMode** — `name`, `description`, `category` (electrical/mechanical/software/cosmetic/material/process/other), `is_active`; `unique_together(tenant,name)`.
- **RootCauseCategory** — `name`, `description`, `responsible_area` (design/manufacturing/supplier/logistics/installation/user_error/unknown), `is_active`; `unique_together(tenant,name)`.
- **ReturnAnalysis** — `code`, `rma_line` FK→RMALine PROTECT, `failure_mode` FK→FailureMode SET_NULL null, `root_cause_category` FK→RootCauseCategory SET_NULL null, `supplier` FK→`procurement.Supplier` SET_NULL null/blank, `analysis_notes`, `corrective_action`, `analyzed_by` FK→User SET_NULL, `analyzed_at`.
- **SupplierChargeback** — `code`, `analysis` FK→ReturnAnalysis PROTECT, `supplier` FK→`procurement.Supplier` PROTECT, `amount`, `currency`, `status` (draft→pending→issued→disputed→recovered/written_off), `issued_date`, `recovered_date`, `reference`, `notes`.

**Preflight (L-25):** before writing FKs/signals, run the `_meta.fields` one-liner against `sales.Customer`, `sales.SalesOrder`, `sales.SalesInvoice`, `plm.Product`, `plm.ProductCategory`, `inventory.Warehouse`, `inventory.StockMovement` (+ the `post_movement()` service signature & movement-type choices), `labor.Employee`, `labor.LaborBooking`, `procurement.Supplier` — write code against the printed field lists, not guesses.

---

## Phase A — Scaffold, models, migration

- [ ] `apps/rma/__init__.py`, `apps.py` (`RmaConfig`, `verbose_name='Returns & RMA Management'`, `ready()` imports signals), `migrations/__init__.py`
- [ ] `apps/rma/services/__init__.py`, `numbering.py` (copy `next_code`), `disposition.py`, `warranty.py`, `repair.py`, `chargeback.py`
- [ ] `apps/rma/models.py` — all 16 models above
- [ ] `apps/rma/admin.py` — `@admin.register` per model, `tenant` in `list_display`+`list_filter`, `autocomplete_fields` for FKs
- [ ] Register `'apps.rma'` in `config/settings.py` INSTALLED_APPS (end of Local block)
- [ ] Mount `path('rma/', include('apps.rma.urls'))` in `config/urls.py`
- [ ] `python manage.py makemigrations rma` → `0001_initial.py`; `python manage.py migrate`

## Phase B — Forms, views, URLs

- [ ] `apps/rma/forms.py` — ModelForm per CRUD model; `tenant=` kwarg in `__init__`; per-tenant FK querysets; explicit `clean()` for `unique_together` (L-01); per-workflow forms where a field is required only at a transition (L-14)
- [ ] `apps/rma/views.py` — `PAGE_SIZE=25`; `@login_required` everywhere; `request.tenant` filter first; list (search+filters+pagination, passes `*_choices`/FK querysets per Filter Rules), create, detail, edit, delete (POST-only, status-gated to match templates — L-03), workflow POST views; dashboard `index` view
- [ ] `apps/rma/urls.py` — `app_name='rma'`; standard `*_list/_create/_detail/_edit/_delete` + workflow action names
- [ ] State-mutating views (approve/reject/receive/complete/validate/issue-chargeback/etc.) guarded by tenant-admin check (L-10)

## Phase C — Templates

- [ ] `templates/rma/index.html` — dashboard: KPI cards (open RMAs, pending approvals, receipts in inspection, open repair orders, active warranties, open chargebacks), recent RMAs, open repair orders
- [ ] `templates/rma/_pagination.html`
- [ ] Per sub-module folders: `requests/`, `reasons/`, `receipts/`, `repairs/`, `warranty/` (policies+registrations+claims), `analytics/` (failure_modes, root_causes, analysis, chargebacks) — `list.html` / `form.html` / `detail.html` each; inline line CRUD on RMA/Receipt/Repair detail pages
- [ ] Actions column (view/edit/delete, status-gated) + detail Actions sidebar per CRUD Completeness Rules
- [ ] Denorm fields rendered with row-level visual cues (L-26): warranty expiry red/yellow tint, chargeback status badges, repair cost rollups
- [ ] `templates/partials/sidebar.html` — add "Returns & RMA" collapse group (`#sidebarRma`, `ri-arrow-go-back-line` icon) inside the `role != 'supplier'/'customer'` block

## Phase D — Signals & cross-module hooks (`apps/rma/signals.py`)

All `@receiver` at module scope, `dispatch_uid='rma.<action>'`, idempotent, `transaction.atomic()` for writes:

1. `RMARequest.post_save(status='approved')` → auto-create draft `ReturnReceipt` (idempotent: skip if receipt exists for rma)
2. `ReturnReceiptLine.post_save(disposition='restock', not disposition_done)` → emit `inventory.StockMovement` via `inventory.services.movements.post_movement()`, link `stock_movement`, set `disposition_done=True`
3. `ReturnReceiptLine.post_save(disposition in {repair,refurbish}, not disposition_done)` → auto-create draft `RepairOrder` (idempotent on `receipt_line` FK), set `disposition_done=True`
4. `RepairLaborLog.post_save` → emit `labor.LaborBooking` (idempotent on `labor_booking` FK) + recompute `RepairOrder` `labor_minutes`/`actual_cost` denorms
5. `RepairPartUsage.post_save`/`pre_delete` → recompute `RepairOrder.actual_cost` denorm
6. `WarrantyClaim.post_save(status='approved', resolution='replace')` → auto-draft `sales.SalesOrder` replacement (idempotent on `replacement_order` FK)
7. Audit-log receivers on status changes of RMARequest / ReturnReceipt / RepairOrder / WarrantyClaim / SupplierChargeback → tenant audit log (`_audit` helper logs failures at WARNING, L-23)
- [ ] `apps/rma/management/commands/expire_warranties.py` — daily job flips `WarrantyRegistration active→expired` past `end_date` via conditional `update()`, `--dry-run`, `--tenant` (L-21)

## Phase E — Seeder

- [ ] `apps/rma/management/__init__.py`, `management/commands/__init__.py`, `seed_rma.py`
- [ ] Idempotent (skip-if-exists + `--flush` + `--tenant`), iterates active tenants, `get_or_create` for catalogs, existence-check for auto-numbered rows
- [ ] Seeds: reasons, failure modes, root-cause categories, warranty policies, ~6 RMA requests across statuses (with lines), ~3 return receipts (with dispositions), ~2 repair orders (with parts+labor), warranty registrations + claims, return analyses + chargebacks
- [ ] ASCII-only stdout (L-09); print non-zero counts (L-08); print tenant-admin login hint

## Phase F — Tests (`apps/rma/tests/`)

- [ ] `__init__.py`, `conftest.py` (fixtures: `tenant_a`, `tenant_b`, `tenant_admin`, `staff_user`, `customer`, `product`, base RMA objects — mirror `apps/sales/tests/conftest.py`)
- [ ] `test_models.py` — auto-numbering, computed fields (warranty `end_date`, labor `labor_cost`, repair cost rollup), `__str__`, validators
- [ ] `test_forms.py` — `unique_together` `clean()` (L-01), workflow-form required-field (L-14), FK querysets tenant-scoped
- [ ] `test_views.py` — HTTP CRUD smoke (list 200, create/edit/delete), filters apply, pagination
- [ ] `test_services.py` — `next_code`, disposition routing, warranty period math, repair cost recompute, chargeback helpers
- [ ] `test_signals.py` — each cross-module hook fires + is idempotent (second save = no dup)
- [ ] `test_security.py` — multi-tenant IDOR (cross-tenant 404 on every detail URL), RBAC matrix (staff blocked from workflow mutations — L-10), anonymous redirect on every list URL
- [ ] `test_seeder.py` — seeder idempotency (run twice, counts stable)
- [ ] Run `pytest apps/rma/tests/` green before done

## Phase G — README & docs

- [ ] `README.md` — Highlights bullet; Project Structure tree entry for `apps/rma/`; new "Module 18 — Returns & RMA Management" section (sub-modules table, models, services, cross-module hooks table, routes/UI-tour table, test suite, out-of-scope); Table of Contents entry; Roadmap line `18. ~~Returns & RMA~~ ✅ shipped`; Management Commands table rows for `seed_rma` + `expire_warranties`; Screenshots/UI Tour `/rma/...` routes
- [ ] Update intro paragraph "Phase 1 ... Module 17" → include Module 18
- [ ] Add Review section to this plan file when done

## Phase H — Verification & handoff

- [ ] `python manage.py makemigrations --check` clean; `python manage.py check`
- [ ] `python manage.py seed_rma` runs clean on seeded tenants; re-run is a no-op
- [ ] `pytest apps/rma/tests/` green
- [ ] Hand user **one `git add` + `git commit` per file** (PowerShell `;` syntax, no `&&`) — L-06

---

## Out of scope (v1)

- EDI / carrier-API return label generation — `carrier`/`tracking_number` stay free text
- Automated refund posting to `cost`/accounting — chargeback & refund amounts are tracked, not journaled
- Customer-facing RMA self-service portal — deferred (sales portal pattern exists; can follow later)

---

## Review (shipped 2026-05-15)

Module 18 was built end-to-end in one session. Final state:

**Code (35 files added under `apps/rma/`):**
- `apps.py`, `__init__.py`, `migrations/0001_initial.py` + `migrations/__init__.py`
- `models.py` (16 models, 632 lines), `admin.py`, `forms.py` (14 ModelForms), `views.py` (~60 views, ~900 lines), `urls.py` (55 patterns), `signals.py` (6 hooks)
- `services/{numbering,warranty,disposition,repair,chargeback}.py`
- `management/commands/{seed_rma,expire_warranties}.py` + `__init__.py` × 2
- `tests/` — `conftest.py` + 7 test files

**Templates (32 files added under `templates/rma/`):**
- `_pagination.html`, `index.html`
- 6 sub-folder groups: `reasons/`, `requests/`, `receipts/`, `repairs/`, `warranty/`, `analytics/`

**Modified (5 files):**
- `README.md` — Highlights bullet, TOC entry, Project Structure tree, full Module 18 section, Management Commands table (`seed_rma` + `expire_warranties` + updated `seed_data`), pytest entry, Roadmap (Module 18 marked shipped)
- `config/settings.py` — `apps.rma` added to INSTALLED_APPS
- `config/urls.py` — `/rma/` mount
- `templates/partials/sidebar.html` — new "Returns & RMA" collapse group with 12 child links
- `apps/core/management/commands/seed_data.py` — `seed_rma` added to orchestrator

**Verification:**
- `python manage.py makemigrations --check` — no changes detected ✓
- `python manage.py check` — `System check identified no issues (0 silenced)` ✓
- `python manage.py seed_rma --flush` — clean run, all 6 signals fired (verified via DB inspection: receipt drafted, repair order auto-spawned, inventory movement posted, labor booking mirrored, warranty replacement SO drafted, repair cost rolled up) ✓
- `python manage.py expire_warranties --dry-run` — clean ✓
- `pytest apps/rma/tests/` — **93 passed in 156s** ✓
- HTTP smoke (logged in as `admin_acme`) — 22 list / create / detail URLs return 200 ✓

**Lessons applied:**
- L-01 — every tenant-catalog form (`RMAReasonForm`, `FailureModeForm`, `RootCauseCategoryForm`) overrides `clean()` to enforce `unique_together(tenant, name)` since `tenant` is excluded from `Meta.fields`.
- L-02 — every Decimal field carries explicit `MinValueValidator`; `WarrantyPolicy.duration_months` carries `MaxValueValidator(600)`.
- L-03 — view status gates match the template buttons (e.g., RMA delete view rejects non-draft just like the template hides the button).
- L-09 — seeder stdout is ASCII-only (`->` not `→`).
- L-10 — `@tenant_admin_required` decorator gates every workflow + delete view; staff users get a redirect-with-error and the DB never mutates.
- L-14 — `RepairCompleteForm.resolution_notes` is required at the complete transition even though the model field is `blank=True` at other states.
- L-17 — every audit-trail / regulated child FK uses `on_delete=PROTECT` (RMARequest, RMALine, RMAReason, WarrantyPolicy, WarrantyRegistration, etc.).
- L-18 — every `@receiver` is module-level (strong reference); each carries a `dispatch_uid='rma.<action>'`.
- L-21 — `expire_warranties` management command keeps `WarrantyRegistration.status='expired'` honest via a race-safe conditional `update()`; idempotent + `--dry-run`.
- L-23 — every cross-module signal handler logs failures at WARNING via `logger.warning(..., exc_info=True)` instead of swallowing with bare `except: pass`.
- L-25 — preflighted `sales.Customer / SalesOrder / SalesInvoice`, `plm.Product / ProductCategory`, `inventory.Warehouse / StockMovement`, `labor.Employee / LaborBooking`, `procurement.Supplier`, and `inventory.services.movements.post_movement` signature via `_meta.fields` inspection BEFORE writing any FK or signal — no field-name retries this session.
- L-26 — denorm fields (`RepairOrder.actual_cost`, `WarrantyRegistration.is_expiring_soon`) are rendered in templates with visual cues (cost roll-up panel; yellow row tinting on registration list).
