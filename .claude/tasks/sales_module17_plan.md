# Module 17 — Sales & Customer Order Management — Implementation Plan

**Status:** approved · **Drafted:** 2026-05-14 · **Approved:** 2026-05-14
**Module spec:** [MSM.md](../../MSM.md) section "17. Sales & Customer Order Management"
**App label:** `sales`  ·  **URL prefix:** `/sales/`  ·  **Auto-number prefixes:** see "Auto-number prefixes" below.

> Note on ordering: Module 16 (Business Intelligence) plan exists at [bi_module16_plan.md](bi_module16_plan.md) but is not yet implemented. Module 17 can ship before Module 16 — they are independent. The README "Roadmap" section will be updated accordingly.

## Approved scope decisions (2026-05-14)

| Decision | Chosen | Notes |
|----------|--------|-------|
| SalesQuotation | **Defer** | Direct Sales Order entry; quote can be added as a 17.6 follow-up. Removes ~8 files. |
| Make-to-order auto-PO | **Enabled with per-line `is_make_to_order` flag** | `SalesOrder.status=confirmed` post_save signal drafts one `pps.ProductionOrder` per MTO line. Idempotent on `source_sales_line` FK. |
| Customer Portal URL | **`/sales/portal/...`** | Mirrors existing supplier-portal layout under `/procurement/portal/...`. |
| Delivery cadence | **One sub-module at a time** | Hand off commit snippets after each sub-module; wait for user OK before starting the next. |

---

## 1. Sub-modules (from MSM.md §17)

| # | Sub-module | Description |
|---|------------|-------------|
| 17.1 | Customer Master & CRM Lite | Customer profiles, contact management, and communication history |
| 17.2 | Sales Order Processing | Order entry, availability check, credit hold, and order confirmation |
| 17.3 | Order Promising & ATP/CTP | Available-to-promise and capable-to-promise calculation with real-time inventory |
| 17.4 | Delivery Scheduling & Dispatch | Shipment planning, logistics integration, and proof of delivery |
| 17.5 | Customer Portal | Self-service order tracking, invoice access, and document download |

---

## 2. Auto-number prefixes (all tenant-scoped, atomic via `select_for_update` like existing modules)

| Prefix | Model | Where used |
|--------|-------|-----------|
| `CUST-00001` | `Customer` | 17.1 |
| `PL-00001` | `PriceList` | 17.1 (pricing reference) |
| `SO-00001` | `SalesOrder` | 17.2 |
| `ATP-00001` | `ATPCalculation` | 17.3 |
| `CTP-00001` | `CTPCalculation` | 17.3 |
| `SHP-00001` | `Shipment` | 17.4 |
| `ROUTE-00001` | `DeliveryRoute` | 17.4 |
| `POD-00001` | `ProofOfDelivery` | 17.4 |
| `SINV-00001` | `SalesInvoice` | 17.4 / 17.5 |
| `COMM-00001` | `CommunicationLog` | 17.1 |
| `QUOTE-00001` | `SalesQuotation` (optional — see §10) | 17.2 |

---

## 3. Models (`apps/sales/models.py`, ~20 models)

All inherit from `core.TenantAwareModel` (provides `tenant`, `created_at`, `updated_at`, `created_by`).

### 17.1 — Customer Master & CRM Lite (7 models)

1. **`CustomerCategory`** — name, code, parent (self-FK), `is_active`. Examples: Industry, Region, Segment.
2. **`PriceList`** — code (`PL-00001`), name, currency, effective_from, effective_to, `is_default`, `is_active`.
3. **`PriceListItem`** — price_list FK, product FK (`plm.Product`), unit_price, min_qty, discount %, valid_from, valid_to. unique_together (price_list, product, min_qty).
4. **`Customer`** — code (`CUST-00001`), name, legal_name, customer_class (`key / standard / distributor / one_time`), category FK, tax_id, currency, payment_terms (Net 0/15/30/45/60/90), credit_limit (Decimal), credit_used (denorm), default_price_list FK, default_warehouse FK (`inventory.Warehouse`), status (`active / inactive / on_hold / blacklisted`), risk_flag, billing/shipping address fields (city, state, postal, country), notes.
5. **`CustomerContact`** — customer FK, full_name, designation, email, phone_primary, phone_alt, is_primary, role (`buyer / accounts / shipping / technical / executive`), notes.
6. **`CommunicationLog`** — code (`COMM-00001`), customer FK, contact FK (nullable), type (`call / email / meeting / note / sms`), direction (`inbound / outbound / internal`), subject, body (text), related_order FK (nullable, `SalesOrder`), follow_up_date, status (`open / done / cancelled`). Append-only via L-03 service layer (no Edit / Delete on rows older than 24h — match `procurement.SupplierMetricEvent` pattern).
7. **`CustomerDocument`** — customer FK, doc_type (`nda / msa / contract / certificate / other`), title, file (FileField, 25 MB cap, allowlist `.pdf .png .jpg .jpeg .docx`), uploaded_by FK, expires_at.

### 17.2 — Sales Order Processing (4 models)

8. **`SalesOrder`** — code (`SO-00001`), customer FK, customer_po_number (free text), order_date, requested_delivery_date, promised_delivery_date, status (`draft → submitted → credit_check → confirmed → in_production → fulfilled → invoiced → closed`, plus `cancelled / on_hold`), credit_hold (bool, set by service), payment_terms, currency, source_warehouse FK, sales_rep FK (`accounts.User`), billing/shipping address snapshot, denorm totals (subtotal, discount_total, tax_total, shipping_total, grand_total), notes.
9. **`SalesOrderLine`** — sales_order FK, line_no, product FK, description (free text override), qty_ordered (Decimal), qty_promised, qty_shipped, qty_invoiced (all denorms), unit_price, line_discount_pct, line_tax_pct, line_total, requested_date, promised_date, source_production_order FK (`pps.ProductionOrder`, nullable), is_make_to_order (bool).
10. **`SalesOrderRevision`** — immutable snapshot per Revise action: sales_order FK, version_no, snapshot_json (header + all lines as JSON), revised_by FK, revised_at, reason. Pattern matches `procurement.PurchaseOrderRevision`.
11. **`SalesOrderApprovalLog`** — sales_order FK, action (`submit / credit_release / credit_hold / approve / cancel / hold / resume / revise`), from_status, to_status, performed_by FK, performed_at, notes. Append-only.

### 17.3 — Order Promising & ATP/CTP (3 models)

12. **`ATPCalculation`** — code (`ATP-00001`), order_line FK (nullable — can also be ad-hoc), product FK, requested_qty, requested_date, available_qty (denorm), available_date (denorm), method (`stock_only / stock_plus_open_po / stock_plus_pps`), result_status (`fully_promised / partially_promised / no_stock`), computed_at, snapshot_json (full breakdown of stock + open PO arrivals + planned receipts). Pure read — never mutates stock.
13. **`CTPCalculation`** — code (`CTP-00001`), order_line FK, product FK, shortfall_qty, target_date, capable_qty (denorm), earliest_completion_date (denorm), bottleneck_work_center FK (`pps.WorkCenter`, nullable), simulation_json (full BOM explosion + capacity trace), computed_at. Pure read — never mutates schedule.
14. **`OrderPromise`** — denormalized result: order_line FK (1-to-1), promise_type (`stock / production / mixed / unfulfillable`), promised_qty, promised_date, atp_ref FK (nullable), ctp_ref FK (nullable), confirmed_at, confirmed_by FK.

### 17.4 — Delivery Scheduling & Dispatch (4 models)

15. **`DeliveryRoute`** — code (`ROUTE-00001`), name, route_date, driver_name, vehicle_no, status (`planned / dispatched / completed / cancelled`), total_stops (denorm), notes.
16. **`Shipment`** — code (`SHP-00001`), sales_order FK, route FK (nullable), status (`planned → picked → packed → in_transit → delivered`, plus `returned / cancelled`), source_warehouse FK, carrier_name, tracking_number, weight_kg, volume_m3, planned_ship_date, actual_ship_date, expected_delivery_date, actual_delivery_date, freight_cost, insurance_cost, notes. **Cross-module hook:** `post_save(status='delivered')` emits one `inventory.StockMovement(type='shipment_out')` per ShipmentLine (idempotent on `source_shipment`).
17. **`ShipmentLine`** — shipment FK, order_line FK, qty_to_ship, qty_shipped, lot_no, serial_no, source_bin FK (`inventory.Bin`, nullable), pick_status (`pending / picked / packed`).
18. **`ProofOfDelivery`** — code (`POD-00001`), shipment FK (1-to-1), delivered_at, received_by_name, received_by_signature_image (FileField, 5 MB cap, allowlist `.png .jpg .jpeg`), photo_attachment (FileField, 25 MB cap), notes, recorded_by FK.

### 17.4 / 17.5 — Sales Invoicing (2 models)

19. **`SalesInvoice`** — code (`SINV-00001`), sales_order FK, shipment FK (nullable — supports partial / consolidated invoicing), invoice_date, due_date, payment_terms, status (`draft → issued → paid → overdue → cancelled`), denorm totals (same shape as SalesOrder), amount_paid (denorm), tenants_invoice FK (optional — bridge to `tenants.Invoice` if/when consolidated billing is wired).
20. **`SalesInvoiceLine`** — invoice FK, shipment_line FK (nullable for service lines), description, qty, unit_price, line_discount_pct, line_tax_pct, line_total.

### Customer-portal user binding

Reuse the existing `accounts.User` model. **No new model** — add one optional FK `customer_company` (FK to `sales.Customer`, null=True, related_name='portal_users') via a separate migration in `apps/accounts/migrations/00XX_user_customer_company.py`. This mirrors the existing `supplier_company` FK pattern (`apps/accounts/models.py`).

Add role choice `'customer'` (already present? — verify in `apps/accounts/models.py`).

---

## 4. Services (`apps/sales/services/`, pure functions, no ORM side-effects at import)

1. **`atp.py`** — `compute_atp(product, qty, requested_date, *, warehouse=None, method='stock_plus_open_po') -> ATPResult` dataclass. Sources: `inventory.StockItem`, open `procurement.PurchaseOrder` arrivals, `mrp` planned receipts. **Never writes.**
2. **`ctp.py`** — `compute_ctp(product, shortfall_qty, target_date) -> CTPResult` dataclass. Walks `plm.Product` → released `bom.BillOfMaterials` → `pps.Routing.RoutingOperation` against `pps.CapacityLoad`. Bottleneck-flagging via existing PPS capacity service. **Never writes.**
3. **`pricing.py`** — `resolve_price(customer, product, qty, on_date=None) -> Decimal` walks PriceListItem with fallbacks (customer default → tenant default → product.list_price). Pure function.
4. **`credit.py`** — `check_credit(customer, additional_amount) -> CreditCheckResult` (ok/hold/limit_exceeded/over_due_invoices). Sums denorm `credit_used` + open SO totals + unpaid SalesInvoice. Returns dataclass — view layer sets `SalesOrder.credit_hold` based on result.
5. **`numbering.py`** — shared `next_code(tenant, prefix, model)` helper with `select_for_update`, matching `procurement.services.numbering.next_code` (or its in-line equivalent). Reuse existing helper if extracted; otherwise add a sales-local copy.
6. **`workflow.py`** — `submit_sales_order`, `confirm_sales_order`, `cancel_sales_order`, `revise_sales_order(reason, new_lines)` — race-safe conditional UPDATE (matches `procurement` PO workflow pattern), writes `SalesOrderApprovalLog`.
7. **`shipping.py`** — `pick_shipment_lines(shipment)`, `confirm_delivery(shipment, pod_data)`. Confirm-delivery emits one `inventory.StockMovement` per line via existing `inventory.services.movements.post_movement(type='shipment_out')`, idempotent on `source_shipment`.
8. **`invoicing.py`** — `generate_invoice_from_shipment(shipment)` builds a draft `SalesInvoice` + lines (idempotent on `source_shipment`).

---

## 5. Signals (`apps/sales/signals.py`)

| Signal | Source | Target | Idempotency key |
|--------|--------|--------|------------------|
| `SalesOrder.post_save(status='submitted')` | sales | run `credit.check_credit` → set `credit_hold` flag | per-save (not stored — flag is current state) |
| `SalesOrder.post_save(status='confirmed', is_make_to_order=True)` | sales | optionally draft `pps.ProductionOrder` (one per make-to-order line) | `source_sales_line` FK on `pps.ProductionOrder` |
| `Shipment.post_save(status='delivered')` | sales | emit `inventory.StockMovement(type='shipment_out')` per ShipmentLine | `source_shipment` FK on movement |
| `Shipment.pre_delete` | sales | reverse the shipment_out movements (mirror MES report pattern) | same key |
| `SalesInvoice.post_save(status='paid')` | sales | bump `Customer.credit_used` denorm down (atomic conditional UPDATE) | per-payment record |
| `mes.ProductionReport.post_save` (existing signal) | mes → sales | update `SalesOrderLine.qty_shipped`-ready flag (advisory only; actual qty_shipped still tracked via ShipmentLine) | n/a |

**No signal mutates user data without a deterministic dedup key.** All idempotent on FK or natural-key per existing project pattern (L-03 service-layer write rule).

---

## 6. Forms (`apps/sales/forms.py`) — L-01/L-02/L-14/L-17/L-22 compliance

- `CustomerForm`, `CustomerContactForm`, `CommunicationLogForm`, `CustomerDocumentForm` (FileField validation per L-22).
- `PriceListForm`, `PriceListItemForm`.
- `SalesOrderForm`, `SalesOrderLineForm` (inline formset), `SalesOrderReviseForm`.
- `ATPRequestForm`, `CTPRequestForm` (ad-hoc check forms).
- `ShipmentForm`, `ShipmentLineForm` (inline formset), `ProofOfDeliveryForm` (image upload validation), `DeliveryRouteForm`.
- `SalesInvoiceForm`, `SalesInvoiceLineForm`.
- `CustomerPortalOrderFilterForm`.

All forms use `crispy-forms` Bootstrap-5 pack — match `apps/procurement/forms.py` style.

---

## 7. Views (`apps/sales/views.py`) — ~55 view functions

All views: `@login_required`, filter `tenant=request.tenant`, CRUD-complete per CLAUDE.md "CRUD Completeness Rules".

### Dashboard (1)
- `index_view` — KPI cards (open orders, on-hold orders, today's shipments, today's invoice value, top 5 customers by revenue), recent SOs, recent shipments.

### 17.1 Customer & CRM Lite (~15)
- Customer: `list / create / detail / edit / delete / toggle_active`
- CustomerContact: `add / edit / delete`
- CommunicationLog: `list / add / detail` (no edit/delete on >24h-old)
- CustomerDocument: `upload / download / delete`
- CustomerCategory: `list / create / edit / delete`
- PriceList: `list / create / detail / edit / delete`
- PriceListItem: inline CRUD on PriceList detail

### 17.2 Sales Order Processing (~12)
- SalesOrder: `list / create / detail / edit / delete (draft only)`
- SalesOrderLine: inline `add / edit / delete` on detail
- Workflow: `submit / approve / cancel / hold / resume / revise`
- Revision: `list / detail`
- Approval log: read-only on detail tab

### 17.3 Order Promising (~6)
- ATP: `request_form / compute / detail / list`
- CTP: `request_form / compute / detail / list`
- OrderPromise: read-only on SO detail; `confirm_promise` POST action

### 17.4 Delivery (~12)
- Shipment: `list / create / detail / edit / delete`
- ShipmentLine: inline CRUD
- Workflow: `pick / pack / dispatch / mark_delivered / cancel`
- ProofOfDelivery: `record / detail`
- DeliveryRoute: `list / create / detail / edit / delete`
- SalesInvoice: `list / create / detail / edit / delete / mark_paid`

### 17.5 Customer Portal (~6)
- `/sales/portal/` — landing
- `/sales/portal/orders/` — list (scoped to `request.user.customer_company`)
- `/sales/portal/orders/<pk>/` — detail
- `/sales/portal/shipments/<pk>/tracking/` — tracking page
- `/sales/portal/invoices/` — list + detail
- `/sales/portal/documents/<pk>/download/` — auth-gated

All portal querysets scoped via `request.user.customer_company` — never `request.tenant` alone (matches existing `supplier_company` portal pattern).

---

## 8. URLs (`apps/sales/urls.py`)

- App namespace: `sales`
- Mount in [`config/urls.py`](../../config/urls.py): `path('sales/', include('apps.sales.urls')),` — placed after `path('iot/', ...)` line 25.
- URL pattern matches existing modules (e.g. `customers/`, `customers/<int:pk>/`, `orders/<int:pk>/submit/`).

---

## 9. Templates (`templates/sales/`, ~50 files)

Mirror IoT / Procurement layout:

```
templates/sales/
  _pagination.html
  index.html
  customers/
    list.html, form.html, detail.html, contact_form.html, communication_form.html, document_upload.html
  pricelists/
    list.html, form.html, detail.html, item_form.html
  orders/
    list.html, form.html, detail.html, revision_detail.html, revise_form.html
  promising/
    atp_request.html, atp_detail.html, atp_list.html, ctp_request.html, ctp_detail.html, ctp_list.html
  shipments/
    list.html, form.html, detail.html, line_form.html, pod_form.html
  routes/
    list.html, form.html, detail.html
  invoices/
    list.html, form.html, detail.html
  portal/
    base_portal.html, dashboard.html, order_list.html, order_detail.html, invoice_list.html, invoice_detail.html, tracking.html
```

All templates extend `base.html`; portal templates extend `portal/base_portal.html` (minimal chrome — no internal sidebar). Filter dropdowns + Actions columns per CLAUDE.md Filter & CRUD rules.

---

## 10. Optional scope items (DEFER unless user asks)

- **`SalesQuotation`** (auto `QUOTE-00001`) — explicit quote → order conversion. MSM.md §17 doesn't require it; modern systems often go straight to SO. Recommend deferring to a Module 17.6 follow-up.
- **EDI / external carrier integration** (FedEx / UPS / DHL APIs) — out of scope; carrier_name + tracking_number stay free-text.
- **Tax engine integration** — keep tax as a flat line % per the existing pattern (procurement does the same).
- **Multi-currency revaluation** — store `currency` field on Customer/SO but no FX conversion engine in this phase.

---

## 11. Sidebar (`templates/partials/sidebar.html`)

Add new group **"Sales & Customer Orders"** with icon `ri-shopping-cart-2-line` after IoT (line ~363 / before any BI placeholder), with children:
- Sales Dashboard
- Customers
- Price Lists
- Sales Orders
- ATP / CTP Calculations
- Shipments
- Delivery Routes
- Sales Invoices
- **Customer Portal** (only shown when `user.customer_company` is set — match supplier-portal pattern)

---

## 12. Cross-module integration checkpoints (read carefully — these are L-03 critical paths)

| Direction | Where | Pattern |
|-----------|-------|---------|
| sales → inventory | `Shipment.status=delivered` → `StockMovement(type='shipment_out')` | post_save signal, idempotent on `source_shipment` FK on movement; `pre_delete` reverses |
| sales → pps | `SalesOrder.status=confirmed` (make-to-order) → draft `ProductionOrder` | post_save signal, idempotent on `source_sales_line` FK |
| sales → mrp | `SalesOrderLine.qty_ordered` exposed as demand source | read-only — `mrp.services.demand.collect_sales_demand(tenant, horizon)` (extend existing demand interface) |
| sales ← qms | `SalesOrder` displays linked open NCRs on detail (read-only) | reverse FK lookup, no signal |
| sales ← cost | `SalesInvoice.status=paid` recognized as revenue for `cost.GrossMarginReport` | extend `cost.services.margin` to consume `SalesInvoice` (1 line change) |

The sales module must NOT touch existing `tenants.Invoice` (subscription billing) — that's a separate concern.

---

## 13. Management commands (`apps/sales/management/commands/`)

1. `seed_sales.py` — idempotent demo seeder: 12 customers, 4 price lists, 30 communication logs, 20 SOs (mixed statuses), 12 shipments, 8 invoices per tenant. Register in [`apps/core/management/commands/seed_data.py`](../../apps/core/management/commands/seed_data.py) orchestrator.
2. `recompute_credit_used.py` — idempotent batch recomputer for `Customer.credit_used` denorm (matches `recompute_capacity_load` style).

---

## 14. Tests (`apps/sales/tests/`, target ≥ 85% coverage on services / forms / signals)

```
apps/sales/tests/
  __init__.py
  conftest.py
  test_models.py             — model constraints, auto-numbering, denorm fields
  test_forms.py              — L-01/L-02/L-14/L-17/L-22 form validation
  test_views.py              — view smoke + filter / pagination
  test_views_crud.py         — full CRUD per model with tenant isolation
  test_views_workflow.py     — SO workflow transitions + race-safety
  test_services_atp.py       — ATP edge cases (zero stock, partial, with PO arrivals)
  test_services_ctp.py       — CTP capacity simulation
  test_services_pricing.py   — price list resolution + fallbacks
  test_services_credit.py    — credit check + hold thresholds
  test_services_shipping.py  — pick / pack / deliver + StockMovement emission
  test_services_invoicing.py — generate_invoice_from_shipment idempotency
  test_signals.py            — Shipment delivered → StockMovement; pre_delete reversal
  test_portal.py             — portal scoping (cross-customer 404)
  test_security.py           — file upload allowlist (L-22), XSS, CSRF, IDOR per tenant
  test_seeder.py             — idempotent seed_sales
```

Total ~15 test files, ~170+ test cases targeting parity with QMS / Procurement test depth.

---

## 15. README updates (per README Maintenance Rule)

- **Highlights** — add Module 17 bullet
- **Table of Contents** — add entry "Module 17 — Sales & Customer Order Management"
- **Project Structure** — add `apps/sales/` + `templates/sales/`
- **Screenshots / UI Tour** — add ~25 route rows (mirroring IoT count)
- **Module 17** — new dedicated section
- **Management Commands** — add `seed_sales`, `recompute_credit_used`
- **Roadmap** — mark Module 17 ✅ (and update the intro paragraph at line 5)

---

## 16. File-by-file checklist

### Skeleton + Settings (3)
- [ ] `apps/sales/__init__.py`
- [ ] `apps/sales/apps.py`
- [ ] Register `apps.sales` in [`config/settings.py`](../../config/settings.py) INSTALLED_APPS (after `apps.bi`)

### Models + Migration (3)
- [ ] `apps/sales/models.py` (~20 models)
- [ ] `apps/sales/migrations/__init__.py`
- [ ] `apps/sales/migrations/0001_initial.py`

### Customer-portal FK on User (1)
- [ ] `apps/accounts/migrations/00XX_user_customer_company.py` — add nullable FK `customer_company` (verify role choice `'customer'` exists; add if missing)
- [ ] (Possibly) `apps/accounts/models.py` — add field + choice

### Admin (1)
- [ ] `apps/sales/admin.py`

### Services (9)
- [ ] `apps/sales/services/__init__.py`
- [ ] `apps/sales/services/atp.py`
- [ ] `apps/sales/services/ctp.py`
- [ ] `apps/sales/services/pricing.py`
- [ ] `apps/sales/services/credit.py`
- [ ] `apps/sales/services/numbering.py`
- [ ] `apps/sales/services/workflow.py`
- [ ] `apps/sales/services/shipping.py`
- [ ] `apps/sales/services/invoicing.py`

### Signals (1)
- [ ] `apps/sales/signals.py`

### Forms (1)
- [ ] `apps/sales/forms.py`

### Views (1)
- [ ] `apps/sales/views.py`

### URLs (2)
- [ ] `apps/sales/urls.py`
- [ ] Mount in [`config/urls.py`](../../config/urls.py)

### Templates (~50)
- [ ] All under `templates/sales/…` per layout in §9

### Sidebar (1)
- [ ] Add "Sales & Customer Orders" group in [`templates/partials/sidebar.html`](../../templates/partials/sidebar.html)

### Management Commands (3)
- [ ] `apps/sales/management/__init__.py`
- [ ] `apps/sales/management/commands/__init__.py`
- [ ] `apps/sales/management/commands/seed_sales.py`
- [ ] `apps/sales/management/commands/recompute_credit_used.py`
- [ ] Register `seed_sales` in [`apps/core/management/commands/seed_data.py`](../../apps/core/management/commands/seed_data.py)

### Tests (~15)
- [ ] All under `apps/sales/tests/…` per §14

### README (1)
- [ ] Update [`README.md`](../../README.md) per §15

### Final
- [ ] Hand off as one-`git add` + one-`git commit` per file PowerShell snippets (per CLAUDE.md "ONE FILE PER COMMIT" rule)

**Estimated file count:** ~95 files (skeleton 3 + models/migrations 3 + accounts patch 1-2 + admin 1 + services 9 + signals 1 + forms 1 + views 1 + urls 2 + templates ~50 + sidebar 1 + commands 4 + tests ~15 + README 1)

---

## 17. Review

(To be added after implementation completes per CLAUDE.md Task Management §5.)
