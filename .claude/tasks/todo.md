# Module 9 — Procurement & Supplier Portal — Implementation Plan

> **Status:** DRAFT — awaiting user approval before any code is written.
>
> **Source spec:** `MSM.md` Module 9 + user message 2026-05-03.

---

## Sub-module breakdown (per user spec)

| # | Sub-module | Description |
|---|-----------|-------------|
| 9.1 | Purchase Order Management | PO creation, approval workflows, revision tracking, acknowledgment |
| 9.2 | Supplier Quotation & RFQ | Multi-round bidding, quote comparison, award management |
| 9.3 | Supplier Performance Scorecard | OTD, quality rating, price variance, vendor ranking dashboards |
| 9.4 | Supplier Self-Service Portal | External vendor access for invoice submission, ASN, order visibility |
| 9.5 | Blanket Orders & Scheduling Agreements | Long-term contracts with periodic release management |

---

## Decisions to confirm with user BEFORE building

| # | Question | Default proposal |
|---|----------|-----------------|
| Q1 | Build all 5 sub-modules in one pass, or stage them? | **All 5 in one pass** (matches Module 8 style); user can ship in slices if preferred. |
| Q2 | Auto-number prefix for procurement PO — `PO-00001` collides with `pps.ProductionOrder`. | Use **`PUR-00001`** to avoid prefix collision in operator conversation. |
| Q3 | Supplier-portal authentication model | **Reuse `accounts.User`** with new role `supplier` + new FK `User.supplier_company → procurement.Supplier`. Avoids parallel auth stack; supplier users still respect `request.tenant`. |
| Q4 | Cross-module FKs (replace free-text `supplier_name` / `po_reference` in `inventory.GoodsReceiptNote` and `qms.IncomingInspection`) | **Add nullable FKs** (`supplier`, `purchase_order`) alongside the existing free-text columns — forward-compatible, no data loss for existing seeded data. |
| Q5 | MRP → Procurement bridge | Add `MRPPurchaseRequisition.converted_po → procurement.PurchaseOrder` (nullable FK) AND keep the existing `converted_reference` text column. `RFQConvertView` / `PRConvertView` flips MRP PR `status='converted'`. |
| Q6 | Include full pytest test suite (~80–120 tests, RBAC + IDOR + workflow + services + signals)? | **Yes** — matches Modules 5/6/7/8. |
| Q7 | Seed command per tenant: ~8 suppliers, 4 RFQs, 6 POs (some converted from MRP PRs), 2 ASNs, 2 supplier invoices, 1 blanket order + 2 releases, 1 scorecard per supplier? | **Yes**, idempotent. |
| Q8 | External-supplier portal surfaces (invoice upload, ASN submission, order visibility) — render inside the same `base.html` or a stripped-down `portal_base.html`? | **Stripped-down `portal_base.html`** — supplier sees only "My POs / My ASNs / My Invoices / My Profile"; sidebar hidden, no links to internal modules. |

---

## App layout (`apps/procurement/`)

```
apps/procurement/
├── __init__.py
├── apps.py                       # ready() loads signals
├── models.py
├── admin.py
├── forms.py
├── views.py
├── urls.py
├── signals.py
├── services/
│   ├── __init__.py
│   ├── po_revision.py            # snapshot_po(po) — JSON capture + diff
│   ├── scorecard.py              # compute_scorecard(supplier, events, period) — pure
│   ├── conversion.py             # convert_pr_to_po(pr) — MRP → procurement bridge
│   └── blanket.py                # consume_release(release) — atomic blanket consumption
├── migrations/__init__.py
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       └── seed_procurement.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_forms.py
    ├── test_services.py
    ├── test_signals.py
    ├── test_views.py
    └── test_security.py          # RBAC matrix + IDOR + supplier portal scope
```

---

## Models (all `TenantAwareModel` unless noted)

### 9.1 — Purchase Order Management
- **`Supplier`** — vendor master. Fields: `code` (unique per tenant), `name`, `legal_name`, `email`, `phone`, `website`, `tax_id`, `address`, `country`, `currency` (default `USD`), `payment_terms` (e.g. NET30), `delivery_terms` (e.g. FOB), `is_active`, `is_approved`, `risk_rating` (`low / medium / high`), `notes`. Unique `(tenant, code)`.
- **`SupplierContact`** — per-supplier contacts. Fields: `supplier` FK, `name`, `role`, `email`, `phone`, `is_primary`, `is_active`.
- **`PurchaseOrder`** — auto-numbered **`PUR-00001`**. Fields: `po_number`, `supplier` FK, `order_date`, `required_date`, `currency`, `payment_terms`, `delivery_terms`, `status` (`draft → submitted → approved → acknowledged → in_progress → received → closed`, plus `rejected` + `cancelled` terminals), `priority` (`low / normal / high / rush`), `notes`, `created_by`, `approved_by` / `approved_at`, `acknowledged_by` (optional supplier user) / `acknowledged_at`, `subtotal`, `tax_total`, `discount_total`, `grand_total` (denorms recomputed on line save), optional FK `source_requisition → mrp.MRPPurchaseRequisition`, optional FK `source_quotation → SupplierQuotation`, optional FK `blanket_order → BlanketOrder`. Unique `(tenant, po_number)`.
- **`PurchaseOrderLine`** — Fields: `po` FK, `line_number` (auto), `product` FK to `plm.Product`, `description` (free-text fallback), `quantity` (validators: ≥0.0001), `unit_of_measure`, `unit_price` (≥0), `tax_pct` (0–100), `discount_pct` (0–100), `required_date`, `notes`. Computed `line_subtotal` / `line_tax` / `line_total` (saved denorms). Unique `(po, line_number)`.
- **`PurchaseOrderRevision`** — immutable JSON snapshot of the entire PO + lines on every "Revise" action. Fields: `po` FK (PROTECT — Lesson L-17), `revision_number` (auto), `change_summary`, `changed_by`, `created_at`, `snapshot_json`. Unique `(po, revision_number)`.
- **`PurchaseOrderApproval`** — append-only approval log. Fields: `po` FK, `approver` FK to `accounts.User`, `decision` (`approved / rejected`), `comments`, `decided_at`.

### 9.2 — Supplier Quotation & RFQ
- **`RequestForQuotation`** — auto-numbered **`RFQ-00001`**. Fields: `rfq_number`, `title`, `description`, `currency`, `issued_date`, `response_due_date`, `round_number` (default 1; multi-round = create a new RFQ that links to prior `parent_rfq`), `parent_rfq` (self-FK nullable for multi-round), `status` (`draft → issued → closed → awarded`, plus `cancelled`), `created_by`. Unique `(tenant, rfq_number)`.
- **`RFQLine`** — Fields: `rfq` FK, `line_number` (auto), `product` FK, `description`, `quantity`, `unit_of_measure`, `target_price` (optional, hidden from suppliers), `required_date`. Unique `(rfq, line_number)`.
- **`RFQSupplier`** — through table for suppliers invited to bid. Fields: `rfq` FK, `supplier` FK, `invited_at`, `responded_at`, `participation_status` (`invited / quoted / declined / no_response`). Unique `(rfq, supplier)`.
- **`SupplierQuotation`** — auto-numbered **`QUO-00001`**; supplier's response to the RFQ. Fields: `quote_number`, `rfq` FK (PROTECT), `supplier` FK, `quote_date`, `valid_until`, `currency`, `payment_terms`, `delivery_terms`, `status` (`submitted → under_review → accepted → rejected`), `notes`, `subtotal`, `tax_total`, `grand_total`. Unique `(tenant, quote_number)` + `(rfq, supplier)` (one quote per supplier per RFQ; multi-round handled via separate RFQ).
- **`QuotationLine`** — Fields: `quotation` FK, `rfq_line` FK, `unit_price`, `lead_time_days`, `min_order_qty`, `comments`. Unique `(quotation, rfq_line)`.
- **`QuotationAward`** — one-to-one with `RequestForQuotation`. Fields: `rfq` OneToOneField, `quotation` FK (winner; PROTECT), `awarded_by`, `awarded_at`, `award_notes`, `auto_create_po` (bool — if true the award action also drafts a `PurchaseOrder`).

### 9.3 — Supplier Performance Scorecard
- **`SupplierMetricEvent`** — append-only event log written by signals. Fields: `supplier` FK, `event_type` (`po_received_on_time / po_received_late / quality_pass / quality_fail / price_variance / response_received / response_missed`), `value` (decimal — e.g. days late, defect %, price delta %), `posted_at`, `reference_type` (e.g. `inventory.GRN` / `qms.IQC` / `procurement.PO`), `reference_id` (no FK — refs span apps).
- **`SupplierScorecard`** — periodic snapshot. Fields: `supplier` FK, `period_start`, `period_end`, `otd_pct` (0–100), `quality_rating` (0–100), `price_variance_pct`, `responsiveness_rating` (0–100), `defect_rate_pct`, `total_pos`, `total_value`, `overall_score` (0–100, weighted), `rank` (within tenant for the period), `computed_at`, `computed_by`. Unique `(tenant, supplier, period_start, period_end)`.

### 9.4 — Supplier Self-Service Portal
- **No new auth model** — extend `accounts.User`:
  - Add new role choice: `supplier`.
  - Add new FK `accounts.User.supplier_company → procurement.Supplier` (nullable; only set for `role='supplier'` users).
  - These two changes ship as a separate migration in the **`accounts`** app.
- **Routing guard** — new mixin `SupplierPortalRequiredMixin` enforces `request.user.role == 'supplier'` AND `request.user.supplier_company_id` is set. Internal-staff views additionally exclude `role='supplier'` from results so a misconfigured staff click doesn't leak data.
- **`SupplierASN`** — Advance Shipping Notice. Auto-numbered **`ASN-00001`**. Fields: `asn_number`, `purchase_order` FK (PROTECT), `ship_date`, `expected_arrival_date`, `carrier`, `tracking_number`, `total_packages`, `status` (`draft → submitted → in_transit → received / cancelled`), `submitted_by` (FK `accounts.User`, restricted to `role='supplier'`), `submitted_at`, `received_by` (internal user) / `received_at`, `notes`. Unique `(tenant, asn_number)`.
- **`SupplierASNLine`** — Fields: `asn` FK, `po_line` FK, `quantity_shipped` (≥0), `lot_number`, `serial_numbers` (comma-separated free text), `notes`. Unique `(asn, po_line)`.
- **`SupplierInvoice`** — auto-numbered **`SUPINV-00001`** (internal); also captures `vendor_invoice_number` (the supplier's own number). Fields: `invoice_number`, `vendor_invoice_number`, `supplier` FK, `purchase_order` FK (optional — general invoices allowed), `invoice_date`, `due_date`, `currency`, `subtotal`, `tax_total`, `grand_total`, `status` (`submitted → under_review → approved → paid / rejected / disputed`), `payment_reference`, `paid_at`, `notes`, `submitted_by` FK, `attachment` FileField (allowlist `.pdf .png .jpg .jpeg`, 25 MB cap). Unique `(tenant, invoice_number)` + `(supplier, vendor_invoice_number)`.
- **`SupplierInvoiceLine`** — Fields: `invoice` FK, `po_line` FK (optional), `description`, `quantity`, `unit_price`, `line_total`. Unique `(invoice, line_number)`.

### 9.5 — Blanket Orders & Scheduling Agreements
- **`BlanketOrder`** — auto-numbered **`BPO-00001`**. Fields: `bpo_number`, `supplier` FK, `start_date`, `end_date`, `currency`, `total_committed_value`, `consumed_value` (denorm), `status` (`draft → active → closed → expired / cancelled`), `notes`, `created_by`, `signed_at`, `signed_by`. Unique `(tenant, bpo_number)`.
- **`BlanketOrderLine`** — Fields: `blanket_order` FK, `line_number`, `product` FK, `description`, `total_quantity` (committed), `consumed_quantity` (denorm; updated by `consume_release`), `unit_of_measure`, `unit_price`, `notes`. Computed `remaining_quantity`. Unique `(blanket_order, line_number)`.
- **`ScheduleRelease`** — auto-numbered **`REL-00001`**; periodic call-off against a blanket. Fields: `release_number`, `blanket_order` FK (PROTECT), `release_date`, `required_date`, `status` (`draft → released → received / cancelled`), `purchase_order` FK (nullable — set when the release is materialised into a real PO via `convert_release_to_po`), `total_amount` (computed), `notes`. Unique `(tenant, release_number)`.
- **`ScheduleReleaseLine`** — Fields: `release` FK, `blanket_order_line` FK, `quantity` (validated: cumulative consumption ≤ committed `total_quantity` per line), `required_date`. Unique `(release, blanket_order_line)`.

---

## Cross-module integration (additive migrations)

| Touched module | Change | Migration files |
|---|---|---|
| `apps/inventory/models.py` | Add nullable FKs `GoodsReceiptNote.supplier → procurement.Supplier` and `GoodsReceiptNote.purchase_order → procurement.PurchaseOrder` (keep existing free-text `supplier_name` / `po_reference`). | `apps/inventory/migrations/0003_grn_procurement_fks.py` |
| `apps/qms/models.py` | Add nullable FKs `IncomingInspection.supplier → procurement.Supplier` and `IncomingInspection.purchase_order → procurement.PurchaseOrder`. | `apps/qms/migrations/0003_iqc_procurement_fks.py` |
| `apps/mrp/models.py` | Add nullable FK `MRPPurchaseRequisition.converted_po → procurement.PurchaseOrder` (keep existing `converted_reference` text). | `apps/mrp/migrations/0002_mrp_pr_converted_po.py` |
| `apps/accounts/models.py` | Add `User.role` choice `supplier` + add nullable FK `User.supplier_company → procurement.Supplier`. | `apps/accounts/migrations/0003_supplier_role.py` |
| `apps/inventory/signals.py` | When a `GoodsReceiptNote` flips to `completed`, post one `procurement.SupplierMetricEvent(po_received_on_time/late)` keyed off `expected_arrival_date` (from linked PO) vs. `now()`. Silently skip if no PO link. | inline edit |
| `apps/qms/signals.py` | When `IncomingInspection.status` flips to `accepted` / `rejected`, post one `procurement.SupplierMetricEvent(quality_pass/fail)`. Skip if no supplier link. | inline edit |

---

## Workflow (per resource)

| Resource | From → To | Required role |
|---|---|---|
| **PurchaseOrder** | `draft → submitted` (Submit) | tenant user |
| | `submitted → approved` (Approve) | tenant **admin** |
| | `submitted → rejected` (Reject) | tenant admin |
| | `approved → acknowledged` (Acknowledge — by supplier user OR internal admin) | supplier user OR tenant admin |
| | `acknowledged → in_progress` (auto on first ASN submitted) | system |
| | `in_progress → received` (auto when GRN completed for full qty) | system |
| | `received → closed` (Close) | tenant admin |
| | `draft / submitted / approved → revised` (creates `PurchaseOrderRevision` snapshot, status reverts to `draft`) | tenant admin |
| | any non-terminal → `cancelled` | tenant admin |
| **RequestForQuotation** | `draft → issued` (Issue — emails RFQSuppliers via `EmailTemplate`) | tenant admin |
| | `issued → closed` (Close — when `response_due_date` passes or admin clicks) | tenant admin |
| | `closed → awarded` (Award — creates `QuotationAward` + optional auto-PO) | tenant admin |
| | any non-terminal → `cancelled` | tenant admin |
| **SupplierQuotation** | `submitted → under_review → accepted / rejected` | tenant admin |
| **SupplierASN** | `draft → submitted` (supplier portal) | supplier user |
| | `submitted → in_transit` (auto on submit) / `in_transit → received` (Receive — internal) | tenant user |
| | any non-terminal → `cancelled` | supplier user (own draft) OR tenant admin |
| **SupplierInvoice** | `submitted → under_review → approved → paid` | tenant admin (after `approved`, payment ref required) |
| | `submitted → rejected` / `under_review → disputed` | tenant admin |
| **BlanketOrder** | `draft → active` (Activate — sets `signed_at` + `signed_by`) | tenant admin |
| | `active → closed` (Close — when fully consumed) / `expired` (auto when `end_date` passes) | tenant admin / system |
| | any non-terminal → `cancelled` | tenant admin |
| **ScheduleRelease** | `draft → released` (Release — also drafts the underlying `PurchaseOrder` if `auto_convert=True`) | tenant admin |
| | `released → received` (auto when linked PO is `received`) / `cancelled` | system / tenant admin |

Every transition uses **conditional `UPDATE … WHERE status IN (…)`** for race-safety (matches Module 4/5/8 pattern) — Lessons L-03, L-10, L-12.

---

## Operator vs Admin matrix (Lesson L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, scorecards | Authenticated tenant user | `TenantRequiredMixin` |
| File RFQ-supplier response (when supplier user), submit ASN, submit supplier invoice | Supplier user (`role='supplier'`) | `SupplierPortalRequiredMixin` |
| Supplier CRUD, PO CRUD + workflow, RFQ CRUD + workflow, Award, Quotation accept/reject, ASN receive, supplier invoice approve/pay/reject, blanket order CRUD + workflow, scorecard recompute | Tenant admin | `TenantAdminRequiredMixin` |
| View own POs / ASNs / Invoices (supplier portal) | Supplier user | `SupplierPortalRequiredMixin` filtered to `supplier_company_id` |

---

## Validation guards (apply Lessons L-01, L-02, L-14)

- Every form whose `Meta.fields` excludes `tenant` gets explicit `clean()` enforcing `(tenant, ...)` `unique_together` (Lesson L-01).
- Every Decimal field carries explicit `MinValueValidator` and (where natural) `MaxValueValidator` — quantities `≥0.0001`, percentages `0–100`, money `≥0`, lead-time `0–365`.
- Per-workflow forms (`POApproveForm`, `POAcknowledgeForm`, `InvoiceApproveForm`, `RFQAwardForm`, `BlanketCloseForm`) override `clean_<field>()` to enforce per-transition required fields (Lesson L-14) — e.g. `payment_reference` required when invoice → `paid`; `award_notes` required on `awarded`.
- `SupplierQuotationForm` enforces `quote_date <= valid_until`.
- `BlanketOrderForm` enforces `start_date <= end_date`.
- `ScheduleReleaseLineForm.clean()` enforces `cumulative_consumption + new_qty <= blanket_line.total_quantity`.

---

## Audit signals (`apps/procurement/signals.py`)

- `pre_save` + `post_save` on `PurchaseOrder` → `apps.tenants.TenantAuditLog` on creation and every status transition (`procurement.po.created`, `procurement.po.<status>`).
- `post_save` on `RequestForQuotation`, `SupplierQuotation`, `QuotationAward`, `SupplierASN`, `SupplierInvoice`, `BlanketOrder`, `ScheduleRelease` → audit on creation and status changes.
- `post_save` on `Supplier` → audit on creation + `is_approved` flip.
- `post_save` on `mes.GoodsReceiptNote` (cross-module) → emit `SupplierMetricEvent` if PO link exists.
- `post_save` on `qms.IncomingInspection` (cross-module) → emit `SupplierMetricEvent` if supplier link exists.

---

## Templates (sub-trees under `templates/procurement/`)

```
templates/procurement/
├── index.html                                   # dashboard with KPI cards
├── suppliers/{list,form,detail}.html
├── supplier_contacts/{form}.html                # inline on supplier detail
├── po/{list,form,detail,revisions}.html
├── po_lines/{form}.html                         # inline on PO detail
├── po_approvals/{form}.html
├── rfq/{list,form,detail}.html
├── rfq_lines/{form}.html                        # inline
├── rfq_suppliers/{form}.html                    # invite suppliers inline
├── quotations/{list,form,detail,compare}.html   # compare = side-by-side matrix
├── quotation_lines/{form}.html                  # inline
├── awards/{form}.html
├── scorecards/{list,detail}.html
├── metric_events/{list}.html
├── asn/{list,form,detail}.html
├── asn_lines/{form}.html                        # inline
├── supplier_invoices/{list,form,detail}.html
├── supplier_invoice_lines/{form}.html           # inline
├── blanket/{list,form,detail}.html
├── blanket_lines/{form}.html                    # inline
├── releases/{list,form,detail}.html
├── release_lines/{form}.html                    # inline
└── portal/                                      # supplier-facing
    ├── portal_base.html                         # stripped sidebar
    ├── dashboard.html
    ├── my_pos.html
    ├── my_asns.html
    ├── my_invoices.html
    └── profile.html
```

Roughly **~40 templates** total. All follow the existing `templates/inventory/...` pattern (status badges, Actions column with View / Edit / Delete, filter forms above table, `request.GET.<field> == 'value'` selected blocks per CLAUDE.md filter rules).

---

## Sidebar (`templates/partials/sidebar.html`) — new "Procurement" group

Added after the "Inventory" group, before "User Management":

```html
<li class="nav-item">
    <a class="nav-link menu-link" href="#sidebarProcurement" data-bs-toggle="collapse" role="button" aria-expanded="false">
        <i class="ri-shopping-cart-2-line"></i> <span>Procurement</span>
    </a>
    <div class="collapse menu-dropdown" id="sidebarProcurement" data-bs-parent="#navbar-nav">
        <ul class="nav nav-sm flex-column">
            <li><a href="{% url 'procurement:index' %}" class="nav-link">Procurement Dashboard</a></li>
            <li><a href="{% url 'procurement:supplier_list' %}" class="nav-link">Suppliers</a></li>
            <li><a href="{% url 'procurement:po_list' %}" class="nav-link">Purchase Orders</a></li>
            <li><a href="{% url 'procurement:rfq_list' %}" class="nav-link">RFQs</a></li>
            <li><a href="{% url 'procurement:quotation_list' %}" class="nav-link">Quotations</a></li>
            <li><a href="{% url 'procurement:scorecard_list' %}" class="nav-link">Scorecards</a></li>
            <li><a href="{% url 'procurement:asn_list' %}" class="nav-link">ASNs</a></li>
            <li><a href="{% url 'procurement:invoice_list' %}" class="nav-link">Supplier Invoices</a></li>
            <li><a href="{% url 'procurement:blanket_list' %}" class="nav-link">Blanket Orders</a></li>
            <li><a href="{% url 'procurement:release_list' %}" class="nav-link">Schedule Releases</a></li>
        </ul>
    </div>
</li>
```

A separate **"Supplier Portal"** sidebar entry is rendered ONLY for `request.user.role == 'supplier'` (a `{% if user.role == 'supplier' %}` guard) and points at `portal/dashboard.html`.

---

## Seed command (`apps/procurement/management/commands/seed_procurement.py`)

Idempotent. Per tenant:

- 8 `Supplier` rows (mix of approved/pending), 1–2 contacts each.
- 4 `RequestForQuotation` (statuses: 1 draft / 1 issued / 1 closed / 1 awarded), each with 2–4 lines and 3 invited suppliers; the awarded RFQ has 3 quotations and an `auto_create_po=True` award that drafts a PO.
- 6 `PurchaseOrder` (statuses: draft / submitted / approved / acknowledged / in_progress / received), 2 of which carry `source_requisition` linking to an MRP PR (Lesson L-08: align with seeded MRP horizon), 1 with two `PurchaseOrderRevision` snapshots demonstrating revision workflow.
- 1 supplier user per tenant (e.g. `supplier_acme_demo` / `Welcome@123`) attached to one of the suppliers — for portal demo.
- 2 `SupplierASN` (1 submitted, 1 received) on POs in `acknowledged`/`in_progress`.
- 2 `SupplierInvoice` (1 under_review, 1 approved with payment ref).
- 1 `BlanketOrder` (active, 3 lines), 2 `ScheduleRelease` (1 released, 1 received) consuming portions of the blanket.
- 1 `SupplierScorecard` per active supplier for the previous month, computed from `SupplierMetricEvent`s back-filled from the seeded POs/GRNs.
- ASCII-only stdout (Lesson L-09); summary line prints non-zero counts for visibility.

---

## Updates to `seed_data` orchestrator
- Append `seed_procurement` after `seed_inventory` in `apps/core/management/commands/seed_data.py`.

---

## Tests (`apps/procurement/tests/`)

- `test_models.py` — model invariants + decimal validators (L-02), unique_together via DB.
- `test_forms.py` — L-01 unique_together via form, L-02 decimal bounds, L-14 per-workflow required fields, blanket cumulative-consumption guard.
- `test_services.py` — `snapshot_po` round-trip, `compute_scorecard` math (events → score), `convert_pr_to_po` idempotence, `consume_release` atomicity.
- `test_signals.py` — audit emission for every workflow transition, GRN→`SupplierMetricEvent`, IQC→`SupplierMetricEvent` round-trips.
- `test_views.py` — full CRUD smoke + workflow happy paths.
- `test_security.py` — RBAC matrix (operator vs admin vs supplier user), multi-tenant IDOR, supplier portal scope (supplier user can only see own supplier's POs / ASNs / invoices), CSRF.

Estimated **~100–120 tests, ~25 s runtime** (matches Module 8).

---

## README updates (mandatory — same session)

| Section | Change |
|---|---|
| Highlights | Add bullet for Module 9. |
| Project Structure | Add `apps/procurement/` sub-tree + add `templates/procurement/` line. |
| Screenshots / UI Tour | Append all `/procurement/...` routes (~30 entries). |
| New section: "Module 9 — Procurement & Supplier Portal" | Full module narrative (5 sub-sections, audit signals, validation guards, workflow tables, RBAC matrix, file-upload security, test suite, out-of-scope) — match the Module 7/8 shape. |
| Management Commands | Add `seed_procurement [--flush]` row. |
| Seeded Demo Data | Add per-tenant Module 9 fixture line. Add demo supplier-portal login. |
| Roadmap | Strike-through "9. Procurement & Supplier Portal". |
| Table of Contents | Insert "Module 9" entry. |

---

## Out of scope (deferred)

- Real EDI / X.12 850 (PO) / 856 (ASN) / 810 (Invoice) — UI-driven workflow only in v1.
- Real e-signature on blanket contracts (today: typed signature + timestamp).
- Multi-currency FX rate engine — POs in non-tenant currency stored at face value, no auto-conversion.
- ML-based supplier risk scoring — `risk_rating` is a manual choice in v1.
- Sourcing event auctions / reverse-bidding — only static-price quotes in v1.
- Dispute / escrow workflows on supplier invoices beyond `disputed` status.
- ~~Supplier portal SSO (SAML / OAuth)~~ — defer to Module 22 (System Admin & Security).

---

## Per-file commit plan

When implementation finishes, snippet block hands the user **one `git add` + `git commit` per file**, in PowerShell-safe form (`;` not `&&`) — Lessons L-06 + Shell Compatibility rules. Estimated ~80–100 commits across:
- 11 new app skeleton files (`apps.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, `signals.py`, `admin.py`, 4× services, all `__init__.py` files)
- 6 new tests files
- 1 new seed command
- ~40 new templates
- 4 cross-module migrations (inventory, qms, mrp, accounts)
- 2 cross-module signal edits (inventory/signals.py, qms/signals.py)
- 1 sidebar.html edit
- 1 settings.py edit (INSTALLED_APPS)
- 1 urls.py edit (config)
- 1 seed_data orchestrator edit
- 1 README.md edit

---

## Implementation order (when approved)

1. **Confirm Q1–Q8 with the user.**
2. App skeleton + register in `INSTALLED_APPS` + mount URL prefix `/procurement/`.
3. Models (single migration `0001_initial.py`) → migrate.
4. Cross-module migrations (additive nullable FKs) → migrate.
5. Forms + admin.
6. Services (pure functions first; they have no Django dependencies in their bodies).
7. Views + URLs.
8. Signals (in-app + cross-module hooks).
9. Templates (dashboard → list/form/detail per resource → portal).
10. Sidebar update.
11. Seed command (and `seed_data` orchestrator update).
12. Tests (TDD-style for services first; then form/view/security smoke).
13. **Run `pytest apps/procurement/tests/`** — must be green before declaring done.
14. **Manual smoke** — login as `admin_acme`, walk all 5 sub-modules; login as supplier user, confirm portal scope.
15. **README update** — full Module 9 section, all the table inserts.
16. Hand the user the per-file commit snippet block.

---

## Open questions awaiting answers — please respond

> **Q1**: Build all 5 sub-modules in one pass, or stage them?
>
> **Q2**: Use prefix `PUR-00001` for procurement Purchase Orders to avoid collision with `pps.ProductionOrder`'s `PO-00001`?
>
> **Q3**: Reuse `accounts.User` (with new `role='supplier'` + FK `supplier_company`) for the portal, or build a parallel `SupplierUser` model?
>
> **Q4**: Add nullable FKs on `inventory.GoodsReceiptNote` + `qms.IncomingInspection` keeping the free-text columns (forward-compatible, no data loss) — OK?
>
> **Q5**: MRP → Procurement bridge as `MRPPurchaseRequisition.converted_po` FK (additive, not replacing) — OK?
>
> **Q6**: Full pytest suite (~100 tests) — OK?
>
> **Q7**: Seed-data fixture as described (8 suppliers, 4 RFQs, 6 POs, etc.) — OK?
>
> **Q8**: Stripped-down `portal_base.html` for supplier-facing pages — OK?

Reply with answers (or "all defaults OK") and I'll start with the app skeleton.
