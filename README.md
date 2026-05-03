# NavMSM — Manufacturing / Production Management System

A multi-tenant, modular Django + Bootstrap 5 platform for managing the full manufacturing lifecycle — from tenant onboarding, billing and branding, through production planning, shop-floor execution, quality, inventory, procurement, and beyond.

This repository contains **Phase 1** of the platform: the core foundation plus **Module 1 — Tenant & Subscription Management**, **Module 2 — Product Lifecycle Management (PLM)**, **Module 3 — Bill of Materials (BOM) Management**, **Module 4 — Production Planning & Scheduling**, **Module 5 — Material Requirements Planning (MRP)**, **Module 6 — Shop Floor Control (MES)**, **Module 7 — Quality Management (QMS)**, **Module 8 — Inventory & Warehouse Management**, and **Module 9 — Procurement & Supplier Portal**. The remaining 13 functional modules listed in [`MSM.md`](./MSM.md) are planned as follow-up phases.

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
15. [Module 4 — Production Planning & Scheduling](#module-4--production-planning--scheduling)
16. [Module 5 — Material Requirements Planning (MRP)](#module-5--material-requirements-planning-mrp)
17. [Module 6 — Shop Floor Control (MES)](#module-6--shop-floor-control-mes)
18. [Module 7 — Quality Management (QMS)](#module-7--quality-management-qms)
19. [Module 8 — Inventory & Warehouse Management](#module-8--inventory--warehouse-management)
20. [Module 9 — Procurement & Supplier Portal](#module-9--procurement--supplier-portal)
21. [UI / Theme Customization](#ui--theme-customization)
18. [Management Commands](#management-commands)
19. [Payment Gateway Integration](#payment-gateway-integration)
20. [Security Notes](#security-notes)
21. [Roadmap](#roadmap)
22. [Troubleshooting](#troubleshooting)
23. [License](#license)

---

## Highlights

- **Multi-tenant by design** — every domain model inherits from a `TenantAwareModel` abstract base; a `TenantMiddleware` binds the current tenant to the request and thread-local storage, and a custom manager auto-scopes every query.
- **Full authentication suite** — login (username *or* email), registration (provisions tenant + admin user + trial subscription atomically), forgot / reset password with token links, and token-based invite acceptance.
- **Complete user management** — list with search/filter, create, edit, detail, delete, toggle-active; per-user profile with UI theme preferences.
- **Module 1 in full** — tenant onboarding wizard, plans & subscriptions, invoices & payments (mock gateway), custom branding, email templates, tenant audit log, and health monitoring with charts.
- **Module 2 — Product Lifecycle Management (PLM)** — product master data with revisions, specs and variants; engineering change orders with submit/approve/reject/implement workflow; CAD/drawing repository with version control; product compliance tracking against global regulatory standards (ISO, RoHS, REACH, CE, UL, FCC, IPC); NPI/Stage-Gate project management with 7-stage gate reviews and deliverables.
- **Module 3 — Bill of Materials (BOM) Management** — multi-level BOMs with self-referencing tree and phantom assemblies; transparent recursive explosion; immutable revision snapshots with one-click rollback; alternate / substitute material catalog with approval workflow; per-component cost elements (material / labor / overhead / tooling) with cascading roll-up through default released sub-assembly BOMs; EBOM / MBOM / SBOM discriminator with sync mappings and automated drift detection.
- **Module 4 — Production Planning & Scheduling** — Master Production Schedule with horizon + time-bucket planning and draft → released workflow; demand forecasts (manual / sales-order / historical); work centers, working calendars, and recomputable capacity load with bottleneck flagging; routings with sequenced operations; production orders with forward / backward / infinite scheduling laid down on the calendar by a pure-function scheduler service; ApexCharts Gantt of scheduled operations; what-if scenario simulator that never mutates the base MPS; deterministic greedy optimizer with weighted objectives (changeovers / idle / lateness / priority) and before/after KPI deltas.
- **Module 6 — Shop Floor Control (MES)** — one-click dispatch from a released `pps.ProductionOrder` into a `MESWorkOrder` (auto-numbered `WO-00001`) with per-routing-op fan-out; touchscreen operator terminal at `/mes/terminal/` with Start / Pause / Resume / Stop buttons backed by an append-only `OperatorTimeLog`; production reports (good / scrap / rework) that bump per-op denorms and roll up to the parent work order; andon alerts (quality / material / equipment / safety / other) with severity + acknowledge / resolve / cancel workflow; paperless work instructions with versioned content + 25 MB attachment + video URL, auth-gated downloads, automatic version supersession on release, and per-operator typed-signature acknowledgements.
- **Module 7 — Quality Management (QMS)** — Incoming Quality Control with ANSI/ASQ Z1.4 single-sampling AQL plans, per-product characteristics, and accept / reject / accept-with-deviation workflow; In-Process Quality Control with checkpoint plans pinned to PPS routing operations, X-bar/R SPC chart math (A2/D3/D4 constants) + Western Electric runs rules 1–4, ApexCharts SPC visualisation; Final Quality Control with finished-good test protocols and HTML Certificate-of-Analysis generation (browser print-to-PDF); Non-Conformance Reports (auto-numbered `NCR-00001`) sourced from IQC / IPQC / FQC / customer with full root-cause analysis (5-Why, fishbone, FMEA), corrective &amp; preventive action tracking, attachment uploads, and `open → investigating → awaiting_capa → resolved → closed` workflow; Calibration Management with measurement-equipment registry, due-tracker (rows go red ≤7 days), append-only calibration records (pass / pass-with-adjustment / fail), tolerance verification, NIST-traceable reference standards, and signal-driven `next_due_at` propagation back onto the parent equipment.
- **Module 8 — Inventory & Warehouse Management** — multi-warehouse tree (Warehouse → Zone → Bin) with `is_default` flag for auto-emit routing, ABC velocity classes on bins; goods receipt notes (auto-numbered `GRN-00001`) with line-level lot/serial capture, optional `qms.IncomingInspection` link, and four putaway strategies (`fixed_bin / nearest_empty / abc_zone / directed`); append-only `StockMovement` ledger covering eight movement types written exclusively through `services/movements.post_movement()` so `StockItem` denorms stay consistent; inter-warehouse transfers (auto `TRF-00001`) with `draft → in_transit → received` workflow that posts an issue + receipt pair, plus stock adjustments (auto `ADJ-00001`, admin-only) that emit one variance movement per line; cycle-count plans + sheets (auto `CC-00001`) with FIFO/FEFO allocation services and ABC Pareto classification, variance recount-trigger on >5%; lot/serial traceability with `Product.tracking_mode` enum (`none / lot / serial / lot_and_serial`), expiry tracking with red/yellow row tinting at 30 / 0 days, and per-lot stock + movement history; **automatic `production_in` movement emission** when `mes.ProductionReport` is filed (signal-based, idempotent, silently skipped when no default warehouse is configured) plus `pre_delete` reversal so the ledger never drifts.
- **Module 9 — Procurement & Supplier Portal** — supplier master with code/risk/approval flags (8 seeded per tenant); purchase orders (auto `PUR-00001`) with full `draft → submitted → approved → acknowledged → in_progress → received → closed` workflow, line-level tax/discount/total denorms, race-safe conditional UPDATE on every transition, immutable `PurchaseOrderRevision` snapshots on every Revise action, and append-only approval log; multi-round RFQs (auto `RFQ-00001`) with invited-supplier matrix, side-by-side quote comparison view, and one-click Award action that optionally drafts a real PO from the winning quotation; supplier scorecards with weighted overall score (40% OTD + 40% Quality + 10% Responsiveness + 10% Price) computed by a pure-function service from append-only `SupplierMetricEvent` rows; **cross-module event hooks** that auto-emit OTD events when `inventory.GoodsReceiptNote` flips to completed and quality pass/fail events when `qms.IncomingInspection` is accepted/rejected; supplier self-service portal (role=`supplier` user with `supplier_company` FK) for ASN submission (auto `ASN-00001`), invoice upload (auto `SUPINV-00001`, 25 MB attachment cap), and own-PO visibility — every portal queryset is scoped to `request.user.supplier_company`; long-term blanket orders (auto `BPO-00001`) with periodic schedule releases (auto `REL-00001`) that consume the parent commitment via a race-safe conditional UPDATE so concurrent releases can never overdraw.
- **Module 5 — Material Requirements Planning (MRP)** — statistical forecast models (moving avg / weighted MA / exp smoothing / naive seasonal) with seasonality profiles and run history; per-product inventory snapshot with safety stock, reorder point, lead time, and lot-sizing rule (L4L / FOQ / POQ / Min-Max); scheduled receipts (open POs, planned production, transfers); regenerative / net-change / simulation MRP runs that explode multi-level BOMs via `bom.BillOfMaterials.explode()` to compute gross-to-net requirements; auto-generation of MRP-suggested purchase requisitions for purchased items; exception engine producing late-order / expedite / defer / no-bom action messages with severity and recommended action; one-click commit / discard.
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
| `/pps/` | PPS dashboard — open MPS, planned/released/in-progress orders, bottleneck count, last optimization gain, recent orders + recent MPS |
| `/pps/forecasts/` | Demand forecast list with source / product filters; create, edit, delete |
| `/pps/forecasts/<pk>/` | Forecast detail |
| `/pps/mps/` | Master Production Schedule list with status / time-bucket filters |
| `/pps/mps/<pk>/` | MPS detail with line CRUD inline + Submit / Approve / Release / Obsolete workflow buttons |
| `/pps/mps/<pk>/submit/` · `/approve/` · `/release/` · `/obsolete/` | POST — MPS workflow transitions |
| `/pps/mps/<id>/lines/new/` | POST — add an MPS line |
| `/pps/mps/lines/<pk>/edit/` · `/delete/` | MPS line CRUD |
| `/pps/work-centers/` | Work center list with type / active filters |
| `/pps/work-centers/<pk>/` | Work center detail with working calendar + recent capacity load |
| `/pps/calendars/` | Capacity calendar entries (per shift per weekday per work center) |
| `/pps/capacity/` | Capacity load dashboard — ApexCharts column chart of utilization with 95% bottleneck threshold annotation |
| `/pps/capacity/recompute/` | POST — recompute capacity load for the next 14 days |
| `/pps/routings/` | Routing list with status / product filters |
| `/pps/routings/<pk>/` | Routing detail with sequenced operation CRUD inline |
| `/pps/routings/<id>/operations/new/` · `/operations/<pk>/edit/` · `/delete/` | Routing operation CRUD |
| `/pps/orders/` | Production order list with status / priority / method / product filters |
| `/pps/orders/<pk>/` | Order detail with scheduled operations table + Release / Start / Complete / Cancel + Schedule (forward/backward/infinite) actions |
| `/pps/orders/<pk>/release/` · `/start/` · `/complete/` · `/cancel/` | POST — production order workflow |
| `/pps/orders/<pk>/schedule/` | POST — replace `ScheduledOperation` rows by laying routing operations onto work-center calendars |
| `/pps/orders/gantt/` | ApexCharts `rangeBar` Gantt of scheduled operations grouped by work center |
| `/pps/scenarios/` | What-if scenario list with status filter |
| `/pps/scenarios/<pk>/` | Scenario detail with change CRUD + Run / Apply / Discard actions and KPI result panel |
| `/pps/scenarios/<pk>/run/` · `/apply/` · `/discard/` | POST — scenario workflow (simulator never mutates the base MPS) |
| `/pps/optimizer/objectives/` | Weighted optimization objective catalog |
| `/pps/optimizer/runs/` | Optimization run list |
| `/pps/optimizer/runs/<pk>/` | Run detail with before/after changeovers / lateness / minutes and improvement % |
| `/pps/optimizer/runs/<pk>/start/` · `/apply/` | POST — start the greedy heuristic / mark result as applied |
| `/mrp/` | MRP dashboard — KPI cards (open runs, exceptions, late orders, PR suggestions, last coverage), recent runs + open exceptions |
| `/mrp/forecast-models/` | Forecast model list with method / period / active filters; create, edit, delete, and **Run** action |
| `/mrp/forecast-models/<pk>/` | Forecast model detail with config + recent runs + run-now button |
| `/mrp/forecast-models/<pk>/run/` | POST — execute the forecast and create a `ForecastRun` + `ForecastResult` rows |
| `/mrp/seasonality/` | Seasonality profile list (per-product per-period multipliers used by naive_seasonal) |
| `/mrp/forecast-runs/` | Forecast run list filterable by status / forecast model |
| `/mrp/forecast-runs/<pk>/` | Forecast run detail with all generated `ForecastResult` rows |
| `/mrp/inventory/` | Inventory snapshot list with lot-sizing-method filter; create, edit, delete |
| `/mrp/inventory/<pk>/` | Inventory snapshot detail with upcoming receipts panel |
| `/mrp/receipts/` | Scheduled receipt list filterable by type / product |
| `/mrp/calculations/` | MRP calculation list filterable by status |
| `/mrp/calculations/<pk>/` | MRP calculation detail with tabs for **Net Requirements**, **PR Suggestions**, **Exceptions** |
| `/mrp/runs/` | MRP run list filterable by run type / status |
| `/mrp/runs/new/` | Two-pane form — create the run + its calculation in one step |
| `/mrp/runs/<pk>/` | MRP run detail with KPI sidebar (coverage, planned orders, PR count, exceptions, late count) |
| `/mrp/runs/<pk>/start/` | POST — execute the regenerative / net-change / simulation engine and record `MRPRunResult` |
| `/mrp/runs/<pk>/apply/` | POST — commit the calculation (regenerative or net-change only — simulations are read-only) |
| `/mrp/runs/<pk>/discard/` | POST — discard the run; calculation marked `discarded` |
| `/mrp/requisitions/` | MRP-suggested PR list with status / priority / product filters |
| `/mrp/requisitions/<pk>/` | PR detail with Approve / Cancel / Delete actions |
| `/mrp/exceptions/` | MRP exception list with type / severity / status filters |
| `/mrp/exceptions/<pk>/` | Exception detail with Acknowledge / Resolve / Ignore actions |
| `/mes/` | MES dashboard — KPI cards (open WOs, in-progress ops, open andon, today's good qty, completed today), recent work orders + open andon alerts |
| `/mes/terminal/` | Touchscreen operator terminal — clock in/out + open jobs grouped with Start / Pause / Resume / Stop / Report buttons |
| `/mes/work-orders/` | MES work order list with status / priority filters; dispatched from PPS production orders |
| `/mes/work-orders/<pk>/` | Work order detail with rollup (good/scrap/rework, hours actual/planned), operations table, recent reports, and Start / Hold / Complete / Cancel actions |
| `/mes/operations/<pk>/` | Operation detail with time-log table + production-report table |
| `/mes/operations/<pk>/start/` · `/pause/` · `/resume/` · `/stop/` | POST — operation lifecycle (records `OperatorTimeLog`, recomputes `actual_minutes`) |
| `/mes/dispatch/<production_order_pk>/` | POST — dispatch a released PPS production order to the shop floor as a MES work order |
| `/mes/operators/` | Operator profile list with active-status filter; create, edit, delete |
| `/mes/operators/<pk>/clock-in/` · `/clock-out/` | POST — clock in/out (also reachable from the terminal) |
| `/mes/time-logs/` | Append-only time-log list filterable by operator + action |
| `/mes/reports/` | Production-report list filterable by scrap reason; create, view, delete |
| `/mes/reports/new/` | File a production report against any open MES operation — bumps op denorms + work-order rollup transactionally |
| `/mes/andon/` | Andon alert list filterable by type / severity / status |
| `/mes/andon/<pk>/` | Andon detail with Acknowledge / Resolve / Cancel actions |
| `/mes/instructions/` | Work-instruction list filterable by doc type / status / product |
| `/mes/instructions/<pk>/` | Instruction detail with all versions, Acknowledge form, current-version content + downloads |
| `/mes/instructions/<pk>/versions/new/` | Add a new draft version (content + 25 MB attachment + video URL) |
| `/mes/instructions/versions/<pk>/release/` | POST — release a version (auto-obsoletes prior released version, updates `current_version`, invalidates prior acks) |
| `/mes/instructions/versions/<pk>/download/` | Auth-gated download for a version's attachment |
| `/mes/instructions/<pk>/ack/` | POST — operator typed-signature acknowledgement of the current released version |
| `/qms/` | QMS dashboard — KPI cards (open NCRs, IQC pending, FQC pending, equipment due ≤7d, open CAPAs), recent NCRs + open corrective actions + equipment due |
| `/qms/iqc/plans/` and CRUD | IQC plan CRUD with characteristic CRUD inline on detail |
| `/qms/iqc/inspections/` and CRUD | IQC inspection list + detail with measurement entry inline + Start / Accept / Reject / Accept-with-deviation actions |
| `/qms/ipqc/plans/` and CRUD | Process inspection plan + checkpoint CRUD (auto-creates an SPC chart shell when chart_type ≠ none) |
| `/qms/ipqc/inspections/` and CRUD | Process inspection list + detail; auto-pushes a `ControlChartPoint` when a chart exists |
| `/qms/ipqc/charts/` and `<pk>/` | SPC chart list + ApexCharts line chart with UCL/LCL annotations (uses `json_script` per Lesson L-07) |
| `/qms/ipqc/charts/<pk>/recompute/` | POST — recompute UCL / LCL / CL from latest 25 subgroups |
| `/qms/fqc/plans/` and CRUD | Final inspection plan + test spec CRUD |
| `/qms/fqc/inspections/` and CRUD | Final inspection list + detail with test-result entry + Start / Pass / Fail / Release-with-deviation actions |
| `/qms/fqc/inspections/<pk>/coa/` | View / generate CoA (HTML view; Save as PDF via browser print) |
| `/qms/fqc/inspections/<pk>/coa/release/` | POST — mark CoA released to customer |
| `/qms/ncr/` and CRUD | NCR list filterable by source / severity / status; full lifecycle (Investigate / Awaiting CAPA / Resolve / Close / Cancel) |
| `/qms/ncr/<pk>/` | NCR detail with tabs for Root Cause, Corrective Actions, Preventive Actions, Attachments + workflow buttons |
| `/qms/ncr/<pk>/rca/edit/` | RCA edit (one-to-one) |
| `/qms/ncr/<pk>/ca/new/` · `<pk>/edit/` · `<pk>/delete/` · `<pk>/complete/` | Corrective action CRUD + complete |
| `/qms/ncr/<pk>/pa/new/` · `<pk>/edit/` · `<pk>/delete/` · `<pk>/complete/` | Preventive action CRUD + complete |
| `/qms/ncr/attachments/<pk>/download/` | Auth-gated NCR attachment download |
| `/qms/equipment/` and CRUD | Measurement equipment registry with `Due ≤7d` filter and red highlight |
| `/qms/equipment/<pk>/` | Equipment detail with calibration history table |
| `/qms/equipment/<pk>/retire/` | POST — retire equipment (terminal status) |
| `/qms/calibrations/` and CRUD | Calibration record list filterable by equipment / result |
| `/qms/calibrations/<pk>/certificate/` | Auth-gated certificate download |
| `/qms/calibration-standards/` and CRUD | Reference-standard catalog (NIST-traceable gauges, etc.) |
| `/inventory/` | Inventory dashboard — KPI cards (warehouses, bins, distinct SKUs, open GRNs, open transfers, open cycle counts, lots expiring ≤30d / expired), recent movements, expiring-lot list |
| `/inventory/stock/` | Read-only `StockItem` list — filter by SKU / warehouse / in-stock-only |
| `/inventory/warehouses/` and CRUD | Warehouse master (code unique per tenant, default flag drives MES auto-emit) |
| `/inventory/zones/` and CRUD | Zone master (receiving / storage / picking / shipping / quarantine) |
| `/inventory/bins/` and CRUD | Storage bin master with ABC class + blocked flag + capacity |
| `/inventory/grn/` and CRUD | Goods Receipt Notes with line-level lot/serial; receive action generates `PutawayTask` rows from the chosen strategy |
| `/inventory/grn/<pk>/receive/` | POST — `draft → putaway_pending`; runs `services/grn.generate_putaway_tasks` |
| `/inventory/grn/<pk>/cancel/` | POST — admin-only cancellation of a non-completed GRN |
| `/inventory/grn/putaway/<pk>/complete/` | POST — picks the actual bin and posts the `receipt` movement |
| `/inventory/movements/` and CRUD | Append-only `StockMovement` ledger with type filter; create posts via `services/movements.post_movement()` |
| `/inventory/transfers/` and CRUD | Inter-warehouse transfer headers with line CRUD inline + Ship / Receive / Cancel |
| `/inventory/transfers/<pk>/ship/` · `/receive/` · `/cancel/` | POST — transfer workflow (atomic per-line movement posting) |
| `/inventory/adjustments/` and CRUD | Admin-only stock adjustments with reason-codes and per-line system-vs-actual comparison |
| `/inventory/adjustments/<pk>/post/` | POST — emits one `adjustment` `StockMovement` per non-zero variance line |
| `/inventory/cycle-count/plans/` and CRUD | Recurring count plan catalog (frequency + ABC filter) |
| `/inventory/cycle-count/sheets/` and CRUD | Cycle count sheets with line CRUD inline + Start / Reconcile workflow |
| `/inventory/cycle-count/sheets/<pk>/start/` · `/reconcile/` | POST — `draft → counting → reconciled`; reconciliation emits `cycle_count` variance movements |
| `/inventory/lots/` and CRUD | Lot/batch traceability with manufactured + expiry dates and stock-item / movement history per lot |
| `/inventory/serials/` and CRUD | Per-unit serial number registry (admin-only CRUD) |
| `/procurement/` | Procurement dashboard — KPI cards (suppliers, open POs, open RFQs, pending invoices, in-transit ASNs, active blankets), recent POs + invoices, top-ranked supplier scorecards |
| `/procurement/suppliers/` and CRUD | Supplier master with risk-rating + approval filters; per-supplier contacts inline on detail |
| `/procurement/po/` and CRUD | Purchase order list with status / priority / supplier filters; full workflow + revision snapshots |
| `/procurement/po/<pk>/submit/` · `/approve/` · `/reject/` · `/acknowledge/` · `/close/` · `/cancel/` · `/revise/` | POST — PO lifecycle (each transition uses race-safe conditional UPDATE) |
| `/procurement/po/<pk>/lines/new/` · `/lines/<pk>/delete/` | PO line CRUD inline on PO detail |
| `/procurement/rfq/` and CRUD | RFQ list with status filter + multi-round support |
| `/procurement/rfq/<pk>/issue/` · `/close/` · `/award/` · `/cancel/` | POST — RFQ lifecycle; Award optionally auto-creates a draft PO |
| `/procurement/rfq/<pk>/invite/` · `/invited/<pk>/remove/` | Manage invited suppliers per RFQ |
| `/procurement/rfq/<rfq_pk>/compare/` | Side-by-side quotation matrix (per-line unit price across all submitted quotes) |
| `/procurement/quotations/` and CRUD | Supplier quotation list filterable by status |
| `/procurement/scorecards/` and `<pk>/` | Supplier scorecard list (ranked) + per-supplier detail with KPI cards + source events |
| `/procurement/scorecards/recompute/` | POST — recompute every active supplier's scorecard for the previous calendar month |
| `/procurement/asn/` and CRUD | Advance Shipping Notice list filterable by status; submit / receive / cancel actions |
| `/procurement/invoices/` and CRUD | Supplier invoice list filterable by status; review / approve / pay (requires payment ref) / reject / dispute |
| `/procurement/blanket/` and CRUD | Blanket order list with consumption denorms; activate / close / cancel actions |
| `/procurement/releases/` and CRUD | Schedule release list; release action consumes blanket commitment, cancel reverses |
| `/procurement/portal/` | Supplier-portal dashboard (role=`supplier` user only) — KPIs scoped to `request.user.supplier_company` |
| `/procurement/portal/pos/` · `/asns/` · `/invoices/` | Supplier-facing read views — only show records belonging to the user's supplier company |

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
│   ├── bom/                      # MODULE 3 — Bill of Materials Management
│   │   ├── models.py             # BillOfMaterials, BOMLine (self-FK tree, phantom flag),
│   │   │                         # BOMRevision (JSON snapshot), AlternateMaterial,
│   │   │                         # SubstitutionRule, CostElement, BOMCostRollup,
│   │   │                         # BOMSyncMap, BOMSyncLog
│   │   ├── signals.py            # Audit-log receivers on BOM status + alternate approval;
│   │   │                         # BOMLine save/delete invalidates the parent BOM rollup
│   │   ├── forms.py              # ModelForms with cross-component validation
│   │   ├── views.py              # Full CRUD + workflow (submit/approve/release/obsolete),
│   │   │                         # BOMExplodeView, BOMRecomputeRollupView, BOMRollbackView,
│   │   │                         # AlternateApproveView/RejectView, BOMSyncRunView
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_bom.py       # Idempotent demo data per tenant (BOMs + costs + alternates + sync)
│   │
│   ├── pps/                      # MODULE 4 — Production Planning & Scheduling
│   │   ├── models.py             # DemandForecast, MasterProductionSchedule, MPSLine,
│   │   │                         # WorkCenter, CapacityCalendar, CapacityLoad,
│   │   │                         # Routing, RoutingOperation, ProductionOrder,
│   │   │                         # ScheduledOperation, Scenario, ScenarioChange,
│   │   │                         # ScenarioResult, OptimizationObjective,
│   │   │                         # OptimizationRun, OptimizationResult
│   │   ├── services/
│   │   │   ├── scheduler.py      # Pure-function forward/backward/infinite scheduler
│   │   │   │                     # + per-day load summary; no ORM imports at module level
│   │   │   ├── simulator.py      # apply_scenario(scenario) — never mutates real data
│   │   │   └── optimizer.py      # Greedy priority-then-product-grouping heuristic (v1)
│   │   ├── signals.py            # Audit-log receivers on MPS / ProductionOrder /
│   │   │                         # Scenario / OptimizationRun status; ScheduledOperation
│   │   │                         # save/delete invalidates the relevant CapacityLoad
│   │   ├── forms.py              # ModelForms with cross-field validation
│   │   ├── views.py              # Full CRUD + workflow + Gantt + capacity dashboard
│   │   │                         # + ScenarioRunView, OptimizationStartView
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_pps.py       # Idempotent demo data per tenant (work centers,
│   │                             # MPS, routings, orders, scenario, optimizer run)
│   │
│   ├── mrp/                      # MODULE 5 — Material Requirements Planning
│       ├── models.py             # ForecastModel, SeasonalityProfile, ForecastRun,
│       │                         # ForecastResult, InventorySnapshot, ScheduledReceipt,
│       │                         # MRPCalculation, NetRequirement,
│       │                         # MRPPurchaseRequisition, MRPException,
│       │                         # MRPRun, MRPRunResult
│       ├── services/
│       │   ├── forecasting.py    # moving_avg / weighted_ma / exp_smoothing /
│       │   │                     # naive_seasonal — pure functions, no ORM imports
│       │   ├── lot_sizing.py     # L4L / FOQ / POQ / Min-Max — pure functions
│       │   ├── mrp_engine.py     # Gross-to-net + multi-level BOM explosion via
│       │   │                     # bom.BillOfMaterials.explode()
│       │   └── exceptions.py     # late_order / expedite / defer / no_bom rules
│       ├── signals.py            # Audit-log receivers on MRPRun, MRPCalculation,
│       │                         # MRPPurchaseRequisition, MRPException save() paths
│       ├── forms.py              # ModelForms with manual unique_together checks
│       ├── views.py              # Full CRUD + run lifecycle + workflow actions
│       ├── urls.py
│       ├── admin.py
│   │   └── management/commands/
│   │       └── seed_mrp.py       # Idempotent demo data per tenant (forecasts,
│   │                             # inventory, receipts, completed MRP run)
│   │
│   ├── mes/                      # MODULE 6 — Shop Floor Control (MES)
│       ├── models.py             # MESWorkOrder, MESWorkOrderOperation,
│       │                         # ShopFloorOperator, OperatorTimeLog,
│       │                         # ProductionReport, AndonAlert,
│       │                         # WorkInstruction, WorkInstructionVersion,
│       │                         # WorkInstructionAcknowledgement
│       ├── services/
│       │   ├── dispatcher.py     # dispatch_production_order() — fans routing ops
│       │   │                     # into MESWorkOrderOperation rows; idempotent
│       │   ├── time_logging.py   # record_event() + pure compute_actual_minutes()
│       │   └── reporting.py      # record_production() + rollup_work_order()
│       ├── signals.py            # Audit-log receivers on MESWorkOrder /
│       │                         # MESWorkOrderOperation / AndonAlert /
│       │                         # WorkInstruction / WorkInstructionVersion;
│       │                         # ack-version snapshot on save
│       ├── forms.py              # ModelForms with file-extension allowlists +
│       │                         # 25 MB cap; manual (tenant, …) uniqueness
│       ├── views.py              # Full CRUD + workflow + Terminal kiosk + dispatch
│       ├── urls.py
│       ├── admin.py
│   │   └── management/commands/
│   │       └── seed_mes.py       # Idempotent demo data (operators, work orders,
│   │                             # time logs, reports, andon, instructions, acks)
│   │
│   ├── inventory/                # MODULE 8 — Inventory & Warehouse Management
│   │   ├── models.py             # Warehouse, WarehouseZone, StorageBin, StockItem,
│   │   │                         # GoodsReceiptNote, GRNLine, PutawayTask,
│   │   │                         # StockMovement, StockTransfer, StockTransferLine,
│   │   │                         # StockAdjustment, StockAdjustmentLine,
│   │   │                         # CycleCountPlan, CycleCountSheet, CycleCountLine,
│   │   │                         # Lot, SerialNumber
│   │   ├── services/
│   │   │   ├── movements.py      # post_movement() — atomic ledger + StockItem updater
│   │   │   ├── allocation.py     # FIFO / FEFO lot picking — pure functions
│   │   │   ├── grn.py            # putaway-strategy bin suggestions + task generator
│   │   │   └── cycle_count.py    # ABC Pareto classification + variance math (pure)
│   │   ├── signals.py            # Audit-log receivers (Warehouse / GRN / Transfer /
│   │   │                         # Adjustment / CycleCountSheet);
│   │   │                         # mes.ProductionReport.post_save -> auto
│   │   │                         # production_in StockMovement;
│   │   │                         # mes.ProductionReport.pre_delete -> reverse
│   │   ├── forms.py              # ModelForms with manual (tenant, …) uniqueness
│   │   │                         # checks and movement-type cross-field validation
│   │   ├── views.py              # Full CRUD + workflow + dashboard
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_inventory.py # Idempotent demo data per tenant
│   │                             # (warehouses, zones, bins, lots, serials,
│   │                             # initial movements, GRN, cycle-count sheet)
│   │
│   ├── procurement/              # MODULE 9 — Procurement & Supplier Portal
│   │   ├── models.py             # Supplier, SupplierContact, PurchaseOrder,
│   │   │                         # PurchaseOrderLine, PurchaseOrderRevision,
│   │   │                         # PurchaseOrderApproval, RequestForQuotation,
│   │   │                         # RFQLine, RFQSupplier, SupplierQuotation,
│   │   │                         # QuotationLine, QuotationAward,
│   │   │                         # SupplierMetricEvent, SupplierScorecard,
│   │   │                         # SupplierASN, SupplierASNLine,
│   │   │                         # SupplierInvoice, SupplierInvoiceLine,
│   │   │                         # BlanketOrder, BlanketOrderLine,
│   │   │                         # ScheduleRelease, ScheduleReleaseLine
│   │   ├── services/
│   │   │   ├── po_revision.py    # snapshot_po(po) + next_revision_number(po)
│   │   │   ├── scorecard.py      # compute_scorecard(events) — pure, weighted
│   │   │   ├── conversion.py     # convert_pr_to_po + convert_quotation_to_po
│   │   │   └── blanket.py        # consume_release / reverse_release atomic UPDATE
│   │   ├── signals.py            # Audit-log on PO/RFQ/Quotation/ASN/Invoice/
│   │   │                         # Blanket/Release status; cross-module hooks
│   │   │                         # on inventory.GRN completion -> SupplierMetricEvent
│   │   │                         # and qms.IQC accept/reject -> SupplierMetricEvent
│   │   ├── forms.py              # ModelForms with L-01 unique_together,
│   │   │                         # L-02 decimal validators, L-14 per-workflow
│   │   │                         # required (PO reject reason, invoice payment ref);
│   │   │                         # blanket cumulative-consumption guard
│   │   ├── views.py              # Full CRUD + workflow + supplier portal mixin
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_procurement.py # Idempotent demo (suppliers, RFQs, POs,
│   │                                # ASNs, invoices, blanket + releases,
│   │                                # scorecards) + 1 supplier-portal demo user
│   │
│   └── qms/                      # MODULE 7 — Quality Management (QMS)
│       ├── models.py             # IncomingInspectionPlan, InspectionCharacteristic,
│       │                         # IncomingInspection, InspectionMeasurement,
│       │                         # ProcessInspectionPlan, ProcessInspection,
│       │                         # SPCChart, ControlChartPoint,
│       │                         # FinalInspectionPlan, FinalTestSpec,
│       │                         # FinalInspection, FinalTestResult,
│       │                         # CertificateOfAnalysis,
│       │                         # NonConformanceReport, RootCauseAnalysis,
│       │                         # CorrectiveAction, PreventiveAction,
│       │                         # NCRAttachment,
│       │                         # MeasurementEquipment, CalibrationStandard,
│       │                         # CalibrationRecord, ToleranceVerification
│       ├── services/
│       │   ├── aql.py            # ANSI/ASQ Z1.4 single-sampling table (pure)
│       │   ├── spc.py            # X-bar/R limits + Western Electric rules (pure)
│       │   └── coa.py            # CoA payload builder (pure dict)
│       ├── signals.py            # Audit-log receivers on IQC / IPQC / FQC /
│       │                         # NCR / CoA / CA / PA status transitions;
│       │                         # CalibrationRecord post_save propagates
│       │                         # last_calibrated_at + next_due_at to the
│       │                         # parent MeasurementEquipment (Lesson L-15)
│       ├── forms.py              # ModelForms with manual (tenant, …) uniqueness
│       │                         # checks, file-extension allowlists +
│       │                         # 25 MB cap, per-workflow clean_<field>
│       ├── views.py              # Full CRUD + workflow + SPC chart + CoA
│       │                         # generation + auth-gated downloads
│       ├── urls.py
│       ├── admin.py
│       └── management/commands/
│           └── seed_qms.py       # Idempotent demo data (IQC plans + inspections,
│                                 # IPQC plans + SPC chart with 25 points,
│                                 # FQC plans + inspections + CoAs,
│                                 # NCRs with RCA + CA + PA, equipment +
│                                 # calibration standards + records)
│
├── templates/
│   ├── base.html                 # master layout with data-* attrs
│   ├── partials/                 # topbar, sidebar, theme_settings, preloader, footer
│   ├── auth/                     # login, register, forgot_password, reset_password, accept_invite
│   ├── dashboard/index.html
│   ├── accounts/                 # user list/form/detail, profile, invite list/form
│   ├── tenants/                  # onboarding_wizard, plans, subscription, invoices, branding, health, audit, email_templates
│   ├── plm/                      # index, categories/, products/, eco/, cad/, compliance/, npi/
│   ├── bom/                      # index, boms/, lines/, revisions/, alternates/, substitution_rules/, cost_elements/, sync_maps/
│   ├── pps/                      # index, forecasts/, mps/, mps_lines/, work_centers/, calendars/, capacity/, routings/, routing_operations/, orders/, scenarios/, scenario_changes/, optimizer/
│   ├── mrp/                      # index, forecast_models/, seasonality/, forecast_runs/, inventory/, receipts/, calculations/, runs/, requisitions/, exceptions/
│   ├── mes/                      # index, terminal/, work_orders/, operators/, time_logs/, reports/, andon/, instructions/
│   ├── qms/                      # index, iqc/{plans,inspections}, ipqc/{plans,inspections,charts}, fqc/{plans,inspections,coa}, ncr/, equipment/, calibrations/
│   ├── inventory/                # index, warehouses/, zones/, bins/, stock_items/, grn/, movements/, transfers/, adjustments/, cycle_count_plans/, cycle_count_sheets/, lots/, serials/
│   └── procurement/              # index, suppliers/, po/, rfq/, quotations/, scorecards/, asn/, supplier_invoices/, blanket/, releases/, portal/
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
- **Per tenant (Module 4 — PPS)** — 4 work centers (machine / labor / cell / assembly_line) each with Mon–Fri 08:00–17:00 calendars, 5 routings (one per seeded finished-good) with 2–4 sequenced operations, 8 demand forecasts spanning 2 weeks across 4 products, 1 released `MasterProductionSchedule` covering 4 weeks with 8 lines, 6 production orders in mixed statuses (planned / released / in_progress / completed) — released and in-progress orders carry full `ScheduledOperation` chains laid down by the forward scheduler — 56 daily `CapacityLoad` snapshots, 1 completed What-If scenario with 2 changes + KPI result, 1 default `OptimizationObjective`, and 1 completed `OptimizationRun` with before/after result.
- **Per tenant (Module 6 — MES)** — 5 `ShopFloorOperator` profiles (badges `B0001`–`B0005`) linked to seeded staff users, up to 6 `MESWorkOrder`s dispatched from released / in-progress production orders (with the parent's status preserved) — each with its own `MESWorkOrderOperation` chain — ~12 `OperatorTimeLog` rows across the in-progress and completed work orders, ~8 `ProductionReport` rows with mixed scrap reasons, 4 `AndonAlert`s spanning open / acknowledged / resolved / cancelled states, 3 `WorkInstruction`s with 1–2 `WorkInstructionVersion`s each (one released, one draft) attached to seeded routing operations (one carries a `video_url`), and 4 `WorkInstructionAcknowledgement` rows on the released versions.
- **Per tenant (Module 5 — MRP)** — 2 `ForecastModel`s (moving_avg + naive_seasonal), 24 monthly `SeasonalityProfile` rows across 2 finished-goods, 1 completed `ForecastRun` with 16 `ForecastResult` rows, 8 `InventorySnapshot` rows covering finished-goods + components with mixed lot-sizing rules (L4L / FOQ / POQ / Min-Max), 5 `ScheduledReceipt`s (open POs / planned production / transfers), 1 completed `MRPCalculation` (linked to the seeded MPS) with **19 planned orders**, **10 PR suggestions**, and **35 exceptions**, plus 1 completed `MRPRun` + `MRPRunResult` capturing coverage / planned-orders / late-orders KPIs.
- **Per tenant (Module 8 — Inventory)** — 2 `Warehouse` rows (`MAIN` flagged default + `SEC`) × 3 zones × 4 bins = 24 bins, 4 `Lot` rows (one expiring in 15 days, one already expired), 6 `SerialNumber` rows on the first finished good, 9 initial `StockMovement` rows that seed `StockItem` denorms across 4 bins (6 receipts + 1 issue + 1 transfer + 1 positive adjustment), 1 completed `GoodsReceiptNote` with 3 lines and matching completed `PutawayTask` rows, and 1 draft `CycleCountSheet` with 4 lines (one carrying a 2-unit variance and `recount_required=True`).
- **Per tenant (Module 9 — Procurement)** — 8 `Supplier` rows (mix of approved/unapproved, mix of low/medium/high risk) each with 1 contact; 1 supplier-portal user (`supplier_<slug>_demo` / `Welcome@123`) attached to the first supplier; 4 `RequestForQuotation` rows (statuses: draft / issued / closed / awarded), the awarded one carries 3 `SupplierQuotation` rows + a `QuotationAward` pointing at the lowest bidder; 6 `PurchaseOrder` rows spanning every workflow status (draft / submitted / approved / acknowledged / in_progress / received), one of them carries 2 immutable `PurchaseOrderRevision` snapshots; 2 `SupplierASN` rows (1 in_transit, 1 received); 2 `SupplierInvoice` rows (1 under_review, 1 approved with payment ref); 1 `BlanketOrder` (active, 3 lines, 12-month horizon) with 2 `ScheduleRelease` rows (1 received with the per-line consumption denorm bumped, 1 currently released); ~80 `SupplierMetricEvent` rows back-filled across the previous calendar month (mix of OTD pass/fail + quality pass/fail); 1 `SupplierScorecard` per active supplier for the previous month with computed weighted overall score and rank.
- **Per tenant (Module 7 — QMS)** — 3 `IncomingInspectionPlan`s (each with 3 characteristics) + 6 `IncomingInspection`s (mix accepted / rejected / accepted-with-deviation / pending / in-inspection) + 8 `InspectionMeasurement` rows; 3 `ProcessInspectionPlan`s pinned to seeded routing operations + 8 `ProcessInspection`s + 1 `SPCChart` with 25 `ControlChartPoint`s (one outlier OOC); 2 `FinalInspectionPlan`s on finished goods with 3 specs each + 5 `FinalInspection`s (mix passed / failed / released-with-deviation / pending) + 3 `CertificateOfAnalysis` records (one released to customer); 4 `NonConformanceReport`s (one per source: iqc / ipqc / fqc / customer) with `RootCauseAnalysis`, 1–2 `CorrectiveAction`s, 1–2 `PreventiveAction`s in mixed statuses; 6 `MeasurementEquipment` items (one due in 5 days, one overdue, four healthy) + 3 `CalibrationStandard`s + 8 `CalibrationRecord`s (mix pass / pass-with-adjustment / 1 fail) with 16 `ToleranceVerification` rows.
- **Global (shared) catalog** — 8 `ComplianceStandard` records (ISO 9001, ISO 14001, RoHS, REACH, CE, UL, FCC, IPC).

### Demo logins (all share password `Welcome@123`)

| Username | Role | Tenant |
|----------|------|--------|
| `admin_acme` | Tenant Admin | Acme Manufacturing |
| `admin_globex` | Tenant Admin | Globex Industries |
| `admin_stark` | Tenant Admin | Stark Production Co. |
| `supplier_acme_demo` | Supplier Portal | Acme Manufacturing (vendor SUP001) |
| `supplier_globex_demo` | Supplier Portal | Globex Industries (vendor SUP001) |
| `supplier_stark_demo` | Supplier Portal | Stark Production Co. (vendor SUP001) |

Staff accounts follow the pattern `<slug>_<role>_<n>`, e.g. `acme_production_manager_1`, `globex_supervisor_2`, etc. Supplier-portal users see only the stripped-down `/procurement/portal/` surface — they cannot access internal Procurement screens or other modules.

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
- `post_save` on `BillOfMaterials` → enforces a single `is_default=True` per `(tenant, product, bom_type)` so the cost-rollup cascade picks deterministically.
- `post_save` on `AlternateMaterial` → writes audit entries when approval status changes.
- `post_save` / `post_delete` on `BOMLine` → invalidates the parent BOM's `BOMCostRollup.computed_at` so the UI shows the rollup as stale until recomputed.

### Validation guards

- `BillOfMaterialsForm.clean()` enforces the `(tenant, product, bom_type, version, revision)` `unique_together` (which Django's default `validate_unique` cannot do because `tenant` is not a form field) and rejects `effective_to < effective_from`.
- `BOMLine.quantity` is bounded `>= 0.0001` (no zero or negative); `BOMLine.scrap_percent` is bounded `0..100`.
- `BOMDeleteView` only permits deletion while the BOM is `draft` or `under_review`. Approved and Released BOMs must be marked Obsolete first, matching the buttons rendered by the list and detail templates.
- `BOMRollbackView` reports the count and SKUs of any snapshot lines whose components are missing from the catalog (so a partial rollback no longer looks like a full success).

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

## Module 4 — Production Planning & Scheduling

Module 4 is implemented in [`apps/pps/`](apps/pps/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (scheduling, simulation, optimization) lives behind small pure-function services in [`apps/pps/services/`](apps/pps/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 4.1 — Master Production Schedule (MPS)

- **`DemandForecast`** — per-product per-period forecast quantity with `source` (`manual` / `sales_order` / `historical`), confidence percentage, and free-text notes.
- **`MasterProductionSchedule`** — auto-numbered `MPS-00001` per tenant; `horizon_start` / `horizon_end` plus `time_bucket` (`day` / `week` / `month`); workflow `draft → under_review → approved → released → obsolete`. Released MPS records auto-stamp `approved_by` / `approved_at` / `released_at`.
- **`MPSLine`** — one product/period row per MPS with `forecast_qty`, `firm_planned_qty`, `scheduled_qty`, and `available_to_promise`. Unique per `(mps, product, period_start)`.

Workflow buttons on the MPS detail page: **Submit for review**, **Approve**, **Release**, **Obsolete** — gated by current status, all using a conditional `UPDATE` for race safety.

### Sub-module 4.2 — Capacity Planning

- **`WorkCenter`** — `code` unique per tenant, `work_center_type` (`machine` / `labor` / `cell` / `assembly_line`), `capacity_per_hour`, `efficiency_pct`, `cost_per_hour`, `is_active`.
- **`CapacityCalendar`** — one row per shift per weekday per work center (`shift_start`, `shift_end`, `is_working`). Drives available-minutes computation.
- **`CapacityLoad`** — recomputable per-day snapshot of `planned_minutes` / `available_minutes` / `utilization_pct` / `is_bottleneck`. Bottleneck threshold is **95%** (rendered as a dashed `dc3545` annotation on the dashboard's ApexCharts column chart).
- **Recompute view** at `/pps/capacity/recompute/` walks the next 14 days, sums `ScheduledOperation` minutes per work center per date, and updates / creates `CapacityLoad` rows. A `post_save` / `post_delete` signal on `ScheduledOperation` clears the affected `CapacityLoad.computed_at` so the UI shows the row as **stale** until recomputed.

### Sub-module 4.3 — Finite & Infinite Scheduling

- **`Routing`** — auto-numbered `ROUT-00001` per tenant; FK to a `plm.Product`; `is_default` flag and `status` (`draft` / `active` / `obsolete`). Unique per `(tenant, product, version)`.
- **`RoutingOperation`** — sequenced operations with `setup_minutes`, `run_minutes_per_unit`, `queue_minutes`, `move_minutes`, and an FK to a `WorkCenter`.
- **`ProductionOrder`** — auto-numbered `PO-00001`; FK to product, optional FK to a routing and a `bom.BillOfMaterials`; optional FK to an `MPSLine` so completion data feeds back to the MPS bucket; status workflow `planned → released → in_progress → completed` (plus `cancelled`); `priority` (`low` / `normal` / `high` / `rush`); `scheduling_method` (`forward` / `backward` / `infinite`).
- **`ScheduledOperation`** — one row per laid-down routing operation with `planned_start` / `planned_end` / `planned_minutes` / `status`. Created and replaced atomically by the schedule action.
- **Scheduler service** — [`apps/pps/services/scheduler.py`](apps/pps/services/scheduler.py) exposes `schedule_forward(start)`, `schedule_backward(end)`, `schedule_infinite(start)`, and `compute_load(scheduled, available)`. The functions are pure — they consume `OperationRequest` dataclasses and return `ScheduledSlot` lists, leaving persistence to the caller. Forward scheduling walks each work center's calendar shift-by-shift, respecting both the flow-cursor (previous op finished) and the per-work-center cursor (free-time). Backward scheduling reuses forward scheduling from a generous probe-start, then slides the entire block so the last operation ends at the target. Naive vs aware datetimes are normalized at function entry / exit.
- **Gantt view** at `/pps/orders/gantt/` renders an ApexCharts `rangeBar` of all `ScheduledOperation` rows in the selected window (default 14 days), grouped by work center, filterable by work center.

### Sub-module 4.4 — What-If Simulation

- **`Scenario`** — clones from a `base_mps`; status workflow `draft → running → completed → applied / discarded`. The Apply action records intent only — it never mutates the base MPS, so simulations stay completely safe.
- **`ScenarioChange`** — one entry per modeled change: `add_order` / `remove_order` / `change_qty` / `change_date` / `change_priority` / `shift_resource`. Carries a `target_ref` (e.g. `mps_line:42`) and a free-form JSON `payload`.
- **`ScenarioResult`** — KPI snapshot (`on_time_pct`, `total_load_minutes`, `total_idle_minutes`, `bottleneck_count`) plus a `summary_json` with line counts and rush count. Computed by [`services/simulator.py`](apps/pps/services/simulator.py)'s `apply_scenario(scenario)` — projects MPSLines into mutable dicts, walks the changes in sequence, never touches the database.

### Sub-module 4.5 — Advanced Planning & Optimization (APO)

- **`OptimizationObjective`** — weighted goal definition with `weight_changeovers`, `weight_idle`, `weight_lateness`, `weight_priority` plus an `is_default` flag. Form-level validation enforces at least one weight > 0.
- **`OptimizationRun`** — a single execution against an MPS; status `queued → running → completed / failed`; captures `started_at`, `finished_at`, `started_by`, `error_message`.
- **`OptimizationResult`** — before / after `total_minutes`, `changeovers`, `lateness` plus `improvement_pct` and a `suggestion_json` with the proposed order sequence.
- **Optimizer** — [`apps/pps/services/optimizer.py`](apps/pps/services/optimizer.py) runs a deterministic greedy heuristic for v1 (priority-bucket sort, then group-by-product within bucket to minimize changeovers, secondary key by `requested_end` for lateness). Real ML/AI optimization is intentionally deferred to a follow-up phase — same way the payment gateway is mock-only today; the data model and UI are forward-compatible, so a different ranker can drop in.

### Audit signals

[`apps/pps/signals.py`](apps/pps/signals.py) wires:

- `pre_save` + `post_save` on `MasterProductionSchedule` → `apps.tenants.TenantAuditLog` entries on every status transition (`mps.created`, `mps.status.<new>` with `meta={'from': old, 'to': new}`).
- `pre_save` + `post_save` on `ProductionOrder` → audit entries on creation and on every status transition.
- `post_save` on `Scenario` → audit entries when the scenario is `applied` / `discarded` / `completed`.
- `post_save` on `OptimizationRun` → audit entries on every status change (queued / running / completed / failed).
- `post_save` / `post_delete` on `ScheduledOperation` → invalidates the matching `CapacityLoad.computed_at` so the dashboard surfaces the row as stale until recomputed.

### Workflow buttons (production order detail page)

| From | Action button | To |
|---|---|---|
| `planned` | Edit / Delete | (mutating) |
| `planned` | Release | `released` |
| `planned` | Schedule (forward / backward / infinite) | (replaces `ScheduledOperation` rows) |
| `released` | Start | `in_progress` (stamps `actual_start`) |
| `in_progress` | Complete | `completed` (stamps `actual_end`) |
| any non-terminal | Cancel | `cancelled` |

All workflow transitions use the same conditional `UPDATE … WHERE status IN (…)` pattern as Module 3 so two operators racing on the floor cannot double-action.

### Operator vs Admin matrix (post-SQA fix)

The post-Module-4 SQA review flagged that every PPS view used `TenantRequiredMixin` only — any authenticated tenant user could approve, release, or obsolete records. The remediated module separates the two roles:

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, Gantt, capacity dashboard (read-only) | Authenticated tenant user (operator) | `TenantRequiredMixin` |
| Create / edit / delete forms; MPS workflow (Submit / Approve / Release / Obsolete); production order workflow (Release / Start / Complete / Cancel / Schedule); scenario Run / Apply / Discard; optimizer Start / Apply / Discard; capacity recompute | Tenant admin (`is_tenant_admin=True`) or Django superuser | `TenantAdminRequiredMixin` |

A regular tenant user attempting any admin-gated POST is redirected to the dashboard with a flash error; the underlying record is not modified. The 58-test pytest suite at [`apps/pps/tests/`](apps/pps/tests/) covers this end-to-end.

### Test suite

Run the PPS test suite with `pytest apps/pps/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory, MD5 hasher, in-memory file storage). The suite covers model invariants, form validation (including the post-review L-01/L-02 regression guards), workflow + tenant isolation + RBAC integration, OWASP A01/A03/A04 + CSRF security tests, pure-function scheduler/optimizer correctness (including the L-05 naive/aware-datetime regression), audit-log emission for configuration mutations, and list-page query budgets. **58 tests, ~6 s runtime.**

---

## Module 5 — Material Requirements Planning (MRP)

Module 5 is implemented in [`apps/mrp/`](apps/mrp/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (forecasting, lot sizing, gross-to-net + BOM explosion, exception generation) lives behind small pure-function services in [`apps/mrp/services/`](apps/mrp/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 5.1 — Demand Forecasting

- **`ForecastModel`** — reusable forecast configuration: `name`, `method` (`moving_avg` / `weighted_ma` / `simple_exp_smoothing` / `naive_seasonal`), `params` JSON (window / weights / alpha / season length), `period_type` (`day` / `week` / `month`), `horizon_periods` (1–104), `is_active`. Unique per `(tenant, name)`.
- **`SeasonalityProfile`** — per-product per-period multiplier (1.0 = neutral, 1.2 = 20% above baseline, 0.8 = 20% below). Unique per `(tenant, product, period_type, period_index)`. Drives `naive_seasonal` forecasts.
- **`ForecastRun`** — auto-numbered `FRUN-00001` execution log with `status` (`queued` / `running` / `completed` / `failed`), `started_by`, `started_at`, `finished_at`, `error_message`. Created by the **Run Forecast** action on a `ForecastModel`.
- **`ForecastResult`** — one row per `(run, product, period_start)` with `forecasted_qty`, `lower_bound`, `upper_bound`, `confidence_pct`. Unique per `(run, product, period_start)`.

The forecasting algorithms in [`services/forecasting.py`](apps/mrp/services/forecasting.py) are deterministic, side-effect-free, and ORM-independent — they accept `list[Decimal]` history and return `list[Decimal]` forecast values. Real ML (Prophet / scikit-learn / ARIMA) is intentionally deferred to a follow-up phase, the same way Module 4's optimizer is a greedy stub today.

### Sub-module 5.2 — Net Requirements Calculation

- **`InventorySnapshot`** — per-product input to the MRP engine: `on_hand_qty`, `safety_stock`, `reorder_point`, `lead_time_days` (0–365), `lot_size_method` (`l4l` / `foq` / `poq` / `min_max`), `lot_size_value`, `lot_size_max`, `as_of_date`. **One row per `(tenant, product)`** — when Module 8 (Inventory & Warehouse) ships, that module is expected to populate these rows by aggregating bin-level data; the MRP engine itself is unaffected.
- **`ScheduledReceipt`** — incoming supply pegged to a date: `receipt_type` (`open_po` / `planned_production` / `transfer`), `quantity`, `expected_date`, `reference` text. Subtracted from gross requirements during the engine pass.
- **`MRPCalculation`** — auto-numbered `MRP-00001` calculation header with `horizon_start` / `horizon_end`, `time_bucket` (`day` / `week`), `status` (`draft` → `running` → `completed` / `failed` → `committed` / `discarded`), optional FK to `pps.MasterProductionSchedule` for end-item demand. Deletion is blocked once `committed`.
- **`NetRequirement`** — gross-to-net result row produced by the engine. Unique per `(mrp_calculation, product, period_start)`. Carries `gross_requirement`, `scheduled_receipts_qty`, `projected_on_hand`, `net_requirement`, `planned_order_qty`, `planned_release_date`, `lot_size_method`, `bom_level` (0 = end item, 1+ = component depth), and `parent_product` for traceability.

The engine in [`services/mrp_engine.py`](apps/mrp/services/mrp_engine.py) walks every end-item demand period, explodes each item's released MBOM (or default released BOM as fallback) via `bom.BillOfMaterials.explode()`, accumulates dependent demand at every level, layers in scheduled receipts, computes `projected_on_hand → net_requirement` honoring `safety_stock`, and finally applies the per-product lot-sizing rule from [`services/lot_sizing.py`](apps/mrp/services/lot_sizing.py). Lot-size methods ship: **L4L** (each period exact), **FOQ** (multiples of fixed qty), **POQ** (group N periods into one order), **Min-Max** (clamp between min and max).

### Sub-module 5.3 — Purchase Requisition Auto-Generation

- **`MRPPurchaseRequisition`** — auto-numbered `MPR-00001` per tenant. Fields: `mrp_calculation` FK, `product` FK, `quantity`, `required_by_date`, `suggested_release_date`, `status` (`draft` → `approved` → `converted` / `cancelled`), `priority` (`low` / `normal` / `high` / `rush`), `approved_by`, `approved_at`, `converted_at`, `converted_reference` (free-text — Module 9 / Procurement will fill this when a PR is promoted to a real PO).

The engine generates draft PRs only for products with `product_type` in (`raw_material`, `component`) — i.e. purchased items. End-items and sub-assemblies still get planned-order entries on `NetRequirement` rows but no PR. Approval and cancel actions are `_atomic_status_transition` UPDATEs for race-safety.

### Sub-module 5.4 — MRP Exception Management

- **`MRPException`** — engine-generated action message. Fields: `exception_type` (`late_order` / `expedite` / `defer` / `cancel` / `release_early` / `below_min` / `above_max` / `no_routing` / `no_bom`), `severity` (`low` / `medium` / `high` / `critical`), `message`, `recommended_action` (`expedite` / `defer` / `cancel` / `release_early` / `manual_review` / `no_action`), `target_type` + nullable `target_id` (no FK — targets live in different apps and may move under refactors), `current_date`, `recommended_date`, `status` (`open` → `acknowledged` → `resolved` / `ignored`).

[`services/exceptions.py`](apps/mrp/services/exceptions.py) generates the rows in bulk after the engine completes. Triggers wired today: planned release in the past (`late_order`), required date earlier than `period_start - lead_time` (`expedite`), Min-Max planned qty below the minimum (`below_min`), end items with no released BOM (`no_bom`), purchased items with no `InventorySnapshot` (`no_routing`).

### Sub-module 5.5 — MRP Run & Simulation

- **`MRPRun`** — auto-numbered `MRPRUN-00001` wrapper. Fields: `name`, `run_type` (`regenerative` / `net_change` / `simulation`), `status` (`queued` → `running` → `completed` / `failed` → `applied` / `discarded`), FK to the `MRPCalculation` it produced, optional FK to `pps.MasterProductionSchedule`, `started_by`, `started_at`, `finished_at`, `error_message`, `applied_at`, `applied_by`, `commit_notes`.
- **`MRPRunResult`** — KPI summary: `total_planned_orders`, `total_pr_suggestions`, `total_exceptions`, `late_orders_count`, `coverage_pct` (0–100), `summary_json` (notes + skipped end-items), `computed_at`.

Run modes:
- **Regenerative** — the engine wipes prior `NetRequirement` rows in the calculation's horizon and recomputes everything. Default for end-of-day / weekly MRP runs.
- **Net Change** — for v1, falls through to regenerative semantics; the data model and UI are forward-compatible with a true delta-aware path in a follow-up phase.
- **Simulation** — the engine produces the same artifacts but the **Apply** button is disabled, so the run can be discarded without ever committing the calculation. Equivalent to PPS's "what-if scenario" pattern.

Workflow buttons (run detail page):

| From | Action | To |
|---|---|---|
| `queued` | Start | `running` → `completed` / `failed` |
| `completed` | Apply (regenerative or net-change only) | `applied`; calculation flips to `committed` |
| `completed` / `failed` | Discard | `discarded`; calculation flips to `discarded` |

### Audit signals

[`apps/mrp/signals.py`](apps/mrp/signals.py) wires:

- `pre_save` + `post_save` on `MRPRun` → `apps.tenants.TenantAuditLog` entries on creation and every status change (`mrp_run.created`, `mrp_run.<status>` with `meta={'from': old, 'to': new}`).
- `pre_save` + `post_save` on `MRPCalculation` → audit on creation and every status transition.
- `post_save` on `MRPPurchaseRequisition` → audit when status flips to `approved` / `cancelled` / `converted` (only via `instance.save()` paths; `_atomic_status_transition` UPDATEs deliberately bypass signals for race-safety, mirroring the PPS pattern).
- `post_save` on `MRPException` → audit on `acknowledged` / `resolved` / `ignored` transitions.

### Validation guards

- `ForecastModelForm.clean()`, `SeasonalityProfileForm.clean()`, and `InventorySnapshotForm.clean()` perform manual `(tenant, …)` uniqueness checks because Django's default `validate_unique()` cannot enforce a `unique_together` set that touches `tenant` (Lesson L-01).
- `Decimal` quantity / percentage fields use explicit `MinValueValidator` and `MaxValueValidator` per Lesson L-02 — `confidence_pct` 0–100, `seasonal_index >= 0`, `safety_stock`, `on_hand_qty`, `lead_time_days <= 365`, etc.
- `MRPRun.can_apply()` rejects simulations: only `regenerative` and `net_change` runs can be committed. The view re-checks before the atomic `UPDATE`, matching the visible button state (Lesson L-03).
- `RunStartView` surfaces skipped end-items (no released BOM) via `messages.warning(...)` listing the SKUs (Lesson L-04). The same list is persisted to `MRPRunResult.summary_json.skipped_no_bom`.

### Out of scope (deferred)

- Real ML forecasting (Prophet / scikit-learn / ARIMA)
- True delta-aware Net Change MRP (today: regenerative semantics)
- CSV bulk import for inventory snapshots
- Linear-program / MILP optimization (today: greedy + lot sizing only)
- Procurement integration — Module 9 will consume `MRPPurchaseRequisition` later
- Inventory integration — Module 8 will populate `InventorySnapshot` later

---

## Module 6 — Shop Floor Control (MES)

Module 6 is implemented in [`apps/mes/`](apps/mes/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (dispatch fan-out, time-log accounting, production rollup) lives behind small pure-function services in [`apps/mes/services/`](apps/mes/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 6.1 — Work Order Execution

- **`MESWorkOrder`** — auto-numbered `WO-00001` per tenant; FK to `pps.ProductionOrder` (the source of truth for "what to build"); `status` workflow (`dispatched → in_progress → on_hold → completed`, plus `cancelled`); `quantity_to_build` / `quantity_completed` / `quantity_scrapped` denorms (rolled up from operations); `priority` (inherited from the production order at dispatch time, mutable for floor reprioritisation); audit stamps for `dispatched_by` / `completed_by`. Unique per `(tenant, wo_number)`.
- **`MESWorkOrderOperation`** — one row per source `pps.RoutingOperation`, fanned out at dispatch time. Carries `sequence`, `operation_name`, `work_center`, `setup_minutes`, `run_minutes_per_unit`, `planned_minutes`, `actual_minutes` (recomputed from time logs), denormalised `total_good_qty / total_scrap_qty / total_rework_qty`, `status` (`pending` / `setup` / `running` / `paused` / `completed` / `skipped`), and `current_operator`.
- **Dispatcher** — [`services/dispatcher.py`](apps/mes/services/dispatcher.py) creates the work order + per-routing-op operation rows in one `transaction.atomic` block. Idempotent: a re-dispatch of the same production order returns the existing non-cancelled work order rather than producing duplicates. The PPS production order is never mutated — its release / start / complete state remains the system-of-record for planning. A "Dispatch to Shop Floor" button on the released production-order detail page gives a one-click handoff.

### Sub-module 6.2 — Operator Terminal Interface

- **`ShopFloorOperator`** — thin one-to-one profile over `accounts.User` carrying `badge_number` (unique per tenant), `default_work_center`, `is_active`. Exists so a future kiosk-mode badge-scan login can key off `badge_number` without touching the auth user.
- **`OperatorTimeLog`** — append-only event log: `(operator, work_order_operation, action, recorded_at, notes)` where action is `clock_in / clock_out / start_job / pause_job / resume_job / stop_job`. Admin UI marks the row read-only for non-superusers.
- **Terminal page** at `/mes/terminal/` — touchscreen kiosk landing for the current operator: clock-in / clock-out toggle, list of all open operations grouped by priority, with big Start / Pause / Resume / Stop buttons and a deep link to the production-report form.
- **Time-logging service** — [`services/time_logging.py`](apps/mes/services/time_logging.py) exposes `record_event(operator, action, work_order_operation=None)` which appends one log row, recomputes the parent operation's `actual_minutes` from accumulated start/pause/resume/stop pairs (a trailing un-stopped run is clamped to `now()`), flips the op's status, auto-promotes the parent work order from `dispatched → in_progress` on the first start, and auto-completes it once every op reaches a terminal state. The pure helper `compute_actual_minutes(time_logs)` is unit-testable without a database fixture.

### Sub-module 6.3 — Production Reporting

- **`ProductionReport`** — operator-filed quantities against an op: `good_qty / scrap_qty / rework_qty` (each `>= 0`), `scrap_reason` (`material_defect / setup_error / tooling / process / operator_error / other`), optional `cycle_time_minutes`, `reported_by`, `reported_at`. A single op can carry multiple reports (multi-shift, partial completions). Form-level `clean()` rejects all-zero submissions and requires a scrap reason once `scrap_qty > 0`.
- **Reporting service** — [`services/reporting.py`](apps/mes/services/reporting.py) bumps the parent op's denorms (`total_good_qty / total_scrap_qty / total_rework_qty`) and rolls up to the parent work order (`quantity_completed / quantity_scrapped`) inside one `transaction.atomic`. The pure helper `rollup_work_order(work_order)` returns a `{good, scrap, rework, completed_pct, hours_actual, hours_planned}` dict for the detail page.
- Deleting a production report rebuilds the op denorms by subtracting the deleted quantities and re-aggregates the parent work order — no orphan rollup state.

### Sub-module 6.4 — Andon & Alert Management

- **`AndonAlert`** — auto-numbered `AND-00001` per tenant; `alert_type` (`quality / material / equipment / safety / other`), `severity` (`low / medium / high / critical`), `title`, `message`, `work_center` FK, optional `work_order` and `work_order_operation` FKs (for tracing alerts to the exact job that triggered them). Workflow `open → acknowledged → resolved` (or `cancelled`) with separate timestamps + actors per transition. Each transition uses the conditional `UPDATE … WHERE status IN (…)` race-safe pattern.
- The dashboard surfaces `open` and `acknowledged` alerts sorted by severity. The work-order detail page lists alerts that referenced its work order so the floor sees its own quality/material issues first.

### Sub-module 6.5 — Paperless Work Instructions

- **`WorkInstruction`** — auto-numbered `SOP-00001` per tenant; `doc_type` (`sop / setup_sheet / quality_check / safety / other`); links to a `pps.RoutingOperation`, a `plm.Product`, or both (validated by `Form.clean()` and the model's `clean()`); `status` (`draft / released / obsolete`); FK `current_version` always points at the latest released version.
- **`WorkInstructionVersion`** — immutable revision per instruction with `version` string (`1.0`, `1.1`, `2.0`), `content` text, `attachment` `FileField` (allowlist `.pdf .png .jpg .jpeg .mp4 .docx .xlsx .txt`, 25 MB cap), `video_url`, `change_notes`, `status`, `uploaded_by`. Releasing a version atomically obsoletes any prior released version for the same instruction and updates `current_version` — there is always exactly one current version per instruction.
- **`WorkInstructionAcknowledgement`** — typed-signature evidence per `(instruction, user, instruction_version)` (unique). The version is stored as a *snapshot string* so a deleted version row does not orphan the ack — the audit trail survives. A `pre_save` signal auto-fills the snapshot from `instruction.current_version.version` when the form omits it.
- Auth-gated download view at `/mes/instructions/versions/<pk>/download/` mirrors the PLM CAD pattern: `get_object_or_404(..., tenant=request.tenant)` then `FileResponse` — a guessed `/media/mes/...` path would still hit the static mount in DEBUG but is never produced by the application.

### Audit signals

[`apps/mes/signals.py`](apps/mes/signals.py) wires:

- `pre_save` + `post_save` on `MESWorkOrder` → `apps.tenants.TenantAuditLog` entries on creation and every status change (`mes_work_order.created`, `mes_work_order.<status>` with `meta={'from': old, 'to': new}`).
- `post_save` on `MESWorkOrderOperation` → audit entries only on transitions to `running / paused / completed / skipped` (high-frequency model — no per-create entry).
- `pre_save` + `post_save` on `AndonAlert` → audit on creation and every status change.
- `post_save` on `WorkInstruction` and `WorkInstructionVersion` → audit on every status transition.
- `pre_save` on `WorkInstructionAcknowledgement` → snapshot the `instruction_version` string before save so a future version deletion does not orphan the ack.

### Operator vs Admin matrix

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, terminal kiosk | Authenticated tenant user | `TenantRequiredMixin` |
| Operator clock-in / clock-out, job start / pause / resume / stop, file production reports, raise andon alerts, acknowledge alerts, resolve alerts, acknowledge work instructions | Authenticated tenant user (operator) | `TenantRequiredMixin` |
| Edit / delete work orders, dispatch from PPS, create / edit / delete operator profiles, edit / cancel andon alerts, create / edit / delete work instructions, add new versions, release / obsolete versions, delete production reports | Tenant admin | `TenantAdminRequiredMixin` |

### Out of scope (deferred)

- Badge-scan kiosk authentication (today: standard `LoginRequiredMixin` + `request.user.shop_floor_operator` lookup)
- Per-station physical signage integration (Andon → physical light tower)
- ~~Statistical Process Control (SPC) charts on production reports~~ ✅ shipped in Module 7
- Sub-batch / lot serialisation on output quantities — Module 8 (Inventory) territory
- ~~Integration with the Quality module for in-line inspections~~ ✅ Module 7 (QMS) consumes `MESWorkOrderOperation` directly via `ProcessInspection.work_order_operation`

---

## Module 7 — Quality Management (QMS)

Module 7 is implemented in [`apps/qms/`](apps/qms/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (AQL sample-size lookup, X-bar/R control-limit math, Western Electric runs rules, CoA payload assembly) lives behind small pure-function services in [`apps/qms/services/`](apps/qms/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 7.1 — Incoming Quality Control (IQC)

- **`IncomingInspectionPlan`** — per-product plan with `aql_level` (I / II / III general), `aql_value` (0.10 – 10.0), `sample_method` (single / double / reduced), `version`, `is_active`. Unique per `(tenant, product, version)`.
- **`InspectionCharacteristic`** — one row per measurable characteristic on a plan, with `nominal`, `usl`, `lsl`, `unit_of_measure`, `is_critical`. Unique per `(plan, sequence)`.
- **`IncomingInspection`** — auto-numbered `IQC-00001` per tenant; FK `plm.Product` + free-text `supplier_name` / `po_reference` / `lot_number` (procurement Module 9 will replace these with FKs); `received_qty`, computed `sample_size` / `accept_number` / `reject_number` from the AQL service; status workflow `pending → in_inspection → accepted / rejected / accepted_with_deviation`.
- **`InspectionMeasurement`** — one measurement per characteristic per inspection. Unique per `(inspection, characteristic)`.

**AQL lookup** — [`services/aql.py`](apps/qms/services/aql.py) ships a complete ANSI/ASQ Z1.4 single-sampling table for general inspection levels I/II/III with the standard lot-size brackets (2 → 500 000+) and AQL values 0.10 – 10.0. `lookup_plan(lot_size, aql, level)` returns `(code_letter, sample_size, accept_number, reject_number)` and resolves down-arrow indirection automatically. Pure function, fully unit-testable.

### Sub-module 7.2 — In-Process Quality Control (IPQC)

- **`ProcessInspectionPlan`** — pins an inspection plan to a `pps.RoutingOperation`; carries `frequency` (every part / every N parts / every N minutes / shift start / lot change), `chart_type` (`x_bar_r` / `p` / `np` / `c` / `u` / `none`), `subgroup_size` (2 – 25), `nominal` / `usl` / `lsl`. Unique per `(tenant, product, routing_operation)`.
- **`ProcessInspection`** — auto-numbered `IPQC-00001`; links to a `mes.MESWorkOrderOperation`; carries `subgroup_index`, `measured_value`, `result` (`pass` / `fail` / `borderline`), optional 25 MB `attachment` (allowlist `.pdf .png .jpg .jpeg`).
- **`SPCChart`** — one-to-one with the plan; recomputed on demand from the latest 25 subgroups; carries `ucl` / `cl` / `lcl` for X-bar and `ucl_r` / `cl_r` / `lcl_r` for R, plus `sample_size_used` and `recomputed_at`.
- **`ControlChartPoint`** — append-only point; `is_out_of_control` and `rule_violations` JSON populated at insert time by `services/spc.py`.

**SPC math** — [`services/spc.py`](apps/qms/services/spc.py) ships pure functions: `compute_xbar_r(subgroups) → XBarRLimits` using A2/D3/D4 constants for subgroup sizes 2–10; `check_western_electric(points, cl, ucl, lcl) → list[ViolationCode]` covering rules R1 (3-sigma), R2 (2 of 3 in zone A), R3 (4 of 5 in zone B+), R4 (8 consecutive on same side). The SPC chart detail page renders an ApexCharts line+annotation chart fed via Django's `{% json_script %}` (Lesson L-07 — never raw `json.dumps`).

### Sub-module 7.3 — Final Quality Control (FQC)

- **`FinalInspectionPlan`** — finished-good test protocol; unique per `(tenant, product, version)`.
- **`FinalTestSpec`** — typed test rows (mechanical / electrical / dimensional / visual / chemical / performance / other) with `nominal`, `usl`, `lsl`, `is_critical`. Unique per `(plan, sequence)`.
- **`FinalInspection`** — auto-numbered `FQC-00001`; FK `mes.MESWorkOrder`; status workflow `pending → in_inspection → passed / failed / released_with_deviation`.
- **`FinalTestResult`** — pass/fail per test per inspection. Unique per `(inspection, spec)`.
- **`CertificateOfAnalysis`** — auto-numbered `COA-00001`, one-to-one with a passed (or released-with-deviation) FQC inspection; carries `customer_name`, `customer_reference`, `released_to_customer` flag with timestamp + actor; only generated by an explicit click and only for `passed` / `released_with_deviation` statuses.

**CoA generation** — v1 renders an HTML certificate at `/qms/fqc/inspections/<pk>/coa/`; users click "Print / Save as PDF" to produce a PDF via the browser. The page hides chrome via `@media print`. Server-side PDF generation (`xhtml2pdf` / WeasyPrint) is intentionally deferred to a follow-up phase to keep the dependency surface small — same pattern as the mock payment gateway.

### Sub-module 7.4 — Non-Conformance & CAPA

- **`NonConformanceReport`** — auto-numbered `NCR-00001`; `source` (iqc / ipqc / fqc / customer / internal_audit / supplier_audit / other), `severity` (minor / major / critical), `status` workflow `open → investigating → awaiting_capa → resolved → closed` (`cancelled` from any non-terminal). Optional FKs to `IncomingInspection` / `ProcessInspection` / `FinalInspection` (one populated, others null) trace the NCR back to the source inspection.
- **`RootCauseAnalysis`** — one-to-one with the NCR; `method` (5-Why / fishbone / Pareto / FMEA / other), `analysis_text`, `root_cause_summary`. The empty RCA shell is auto-created when the NCR is raised so the detail page always shows the form.
- **`CorrectiveAction`** + **`PreventiveAction`** — sequenced action items with `owner`, `due_date`, `effectiveness_verified` flag, `verification_notes`, status `open → in_progress → completed` (`cancelled`).
- **`NCRAttachment`** — file upload (allowlist `.pdf .png .jpg .jpeg .docx .xlsx .txt .zip`, 25 MB cap); auth-gated download.

**Workflow buttons** (NCR detail page): Investigate (open → investigating), Awaiting CAPA (investigating → awaiting_capa), Resolve (investigating / awaiting_capa → resolved), Close (resolved → closed; requires `resolution_summary`), Cancel (any non-terminal → cancelled). Every transition uses the conditional `UPDATE … WHERE status IN (…)` race-safe pattern.

### Sub-module 7.5 — Calibration Management

- **`MeasurementEquipment`** — auto-numbered `EQP-00001`; `equipment_type` (caliper / micrometer / gauge / thermometer / scale / multimeter / pressure / torque / other); `serial_number` unique per tenant; optional FK to `pps.WorkCenter` (assigned location); `range_min` / `range_max` / `tolerance` / `unit_of_measure`; `calibration_interval_days` (1 – 3650); `last_calibrated_at` / `next_due_at` (auto-updated by signal); status `active ↔ out_of_service`, `retired` is terminal.
- **`CalibrationStandard`** — per-tenant catalog of reference standards (e.g. NIST-traceable gauge blocks).
- **`CalibrationRecord`** — auto-numbered `CAL-00001`, append-only event log; `result` (pass / pass_with_adjustment / fail); optional `certificate_file` (allowlist `.pdf .png .jpg .jpeg`, 25 MB) with auth-gated download. `notes` are required when `result='fail'` (Lesson L-14).
- **`ToleranceVerification`** — per-record point check (nominal, as_found, as_left, tolerance, is_within_tolerance).

**Equipment due tracker** — the equipment list view tints rows red when `next_due_at < now` and yellow when within 7 days. The dashboard surfaces both counts as KPI cards. Filing a `CalibrationRecord` triggers a `post_save` signal that updates the parent equipment's `last_calibrated_at` and recomputes `next_due_at` from `calibrated_at + interval_days` (Lesson L-15: the new value is captured into a local before the `update()` call so the in-memory equipment instance never goes stale).

### Audit signals

[`apps/qms/signals.py`](apps/qms/signals.py) wires:

- `pre_save` + `post_save` on `IncomingInspection`, `FinalInspection`, `NonConformanceReport` → `apps.tenants.TenantAuditLog` on creation and every status transition.
- `pre_save` + `post_save` on `ProcessInspection` → audit on creation and on every `result` change (`pass` ↔ `fail` ↔ `borderline`).
- `post_save` on `CertificateOfAnalysis` → audit on `released_to_customer` flip from False to True.
- `post_save` on `CorrectiveAction` and `PreventiveAction` → audit on transitions to `completed` / `cancelled`.
- `post_save` on `CalibrationRecord` → audit + propagates `last_calibrated_at` and `next_due_at` to the parent `MeasurementEquipment`.

### Operator vs Admin matrix

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, SPC chart view | Authenticated tenant user | `TenantRequiredMixin` |
| File an inspection (IQC / IPQC / FQC), file a measurement, raise an NCR, record a calibration, complete CA / PA, generate a CoA, IQC accept / reject | Authenticated tenant user | `TenantRequiredMixin` |
| Create / edit / delete inspection plans, edit / delete inspections, NCR workflow transitions (Investigate / Resolve / Close / Cancel), CoA release-to-customer, equipment retire / delete, calibration-standard CRUD, IQC release-with-deviation, FQC release-with-deviation | Tenant admin | `TenantAdminRequiredMixin` |

A regression test file ([`apps/qms/tests/test_security.py`](apps/qms/tests/test_security.py) — `TestRBACMatrix`) asserts redirect + state-not-changed for every admin-gated POST.

### File-upload security

Auth-gated download views ([`apps/qms/views.py`](apps/qms/views.py) — `NCRAttachmentDownloadView`, `CalibrationCertificateDownloadView`) verify tenant ownership via `get_object_or_404(..., tenant=request.tenant)` then stream via `FileResponse`. Templates link to these via `{% url %}` rather than `.file.url`. File-extension allowlists (defined in [`apps/qms/forms.py`](apps/qms/forms.py)):

| Surface | Allowed extensions | Notes |
|---|---|---|
| NCR attachments | `.pdf .png .jpg .jpeg .docx .xlsx .txt .zip` | |
| Calibration certificates | `.pdf .png .jpg .jpeg` | |
| IPQC inspection attachments | `.pdf .png .jpg .jpeg` | |

All uploads are capped at **25 MB**.

### Test suite

Run the QMS test suite with `pytest apps/qms/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory). The suite covers model invariants + validator bounds, form validation (L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required fields, file-extension allowlist), pure-function AQL table lookups across all 3 levels, X-bar/R limit math + Western Electric rules R1 / R4 + helpers, IQC / FQC / NCR / Calibration end-to-end workflow paths, RBAC matrix + multi-tenant IDOR + anonymous-redirect, and audit-log emission including the L-15 calibration → equipment propagation. **85 tests, ~19 s runtime.**

### Out of scope (deferred)

- **Procurement integration** — IQC's `supplier_name` / `po_reference` are free-text strings until Module 9 (Procurement) ships and provides the FK.
- **Real PDF CoA generation** — v1 is HTML + browser print-to-PDF; `xhtml2pdf` / WeasyPrint server-side rendering is a follow-up.
- **MES Andon auto-raise on critical NCR** — placeholder hook only; the actual `mes.AndonAlert` auto-creation is deferred (don't want to entangle the MES tests).
- **Customer portal CoA self-serve** — `released_to_customer` flag is set, but the customer-facing surface is Module 17 (Sales) territory.
- **Statistical capability indices (Cp / Cpk / Pp / Ppk)** — only UCL / LCL / CL + Western Electric rules 1 – 4 ship in v1.
- **p / np / c / u attribute-chart limit math** — model fields exist; the formula coverage will land in a follow-up alongside Cp/Cpk.
- **Gage R&R studies** — calibration covers single-instrument tolerance; multi-operator/multi-trial reproducibility study is deferred.
- **8D problem-solving template** for NCRs — v1 is RCA + CA + PA only; the formal 8D format is a follow-up template choice.
- **CSV bulk import** for inspection plans / equipment.

---

## Module 8 — Inventory & Warehouse Management

Module 8 is implemented in [`apps/inventory/`](apps/inventory/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (ledger writes, FIFO/FEFO allocation, ABC classification) lives behind small pure-function services in [`apps/inventory/services/`](apps/inventory/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 8.1 — Multi-Warehouse Inventory

- **`Warehouse`** — `code` unique per tenant, optional `manager` FK, `is_default` flag (drives the MES auto-emit signal — exactly one default per tenant), `is_active` toggle.
- **`WarehouseZone`** — FK to warehouse, `zone_type` (`receiving / storage / picking / shipping / quarantine`); unique per `(warehouse, code)`.
- **`StorageBin`** — FK to zone; `bin_type` (`shelf / pallet / rack / floor / bulk`), `capacity` (0 = unlimited), `abc_class` (set by cycle-count service), `is_blocked` flag. Unique per `(zone, code)`. The `warehouse` property hops through `zone`.
- **`StockItem`** — denorm row keyed by `(tenant, product, bin, lot, serial)`; auto-maintained by `services/movements.post_movement()`. Computed `qty_available` = `qty_on_hand - qty_reserved`. **Direct mutation is forbidden** — every write goes through `post_movement()`.

### Sub-module 8.2 — Goods Receipt & Putaway

- **`GoodsReceiptNote`** — auto-numbered `GRN-00001` per tenant; free-text `supplier_name` / `po_reference` (Module 9 will replace with FKs); optional FK to `qms.IncomingInspection` for "accept → receive" flow; status workflow `draft → received → putaway_pending → completed / cancelled`.
- **`GRNLine`** — FK to GRN + product; carries `expected_qty` / `received_qty`, `lot_number`, comma-separated `serial_numbers`, FK to receiving zone.
- **`PutawayTask`** — generated automatically by the **Receive** action (one per GRN line); `strategy` (`fixed_bin / nearest_empty / abc_zone / directed`), `suggested_bin` (computed by `services/grn.suggest_bin`), `actual_bin` (filled when the operator confirms). Completing a task posts a `receipt` `StockMovement` and, if every task on the GRN is done, flips the GRN to `completed`.

### Sub-module 8.3 — Inventory Movements & Transfers

- **`StockMovement`** — append-only ledger; eight `movement_type`s (`receipt / issue / transfer / adjustment / production_in / production_out / scrap / cycle_count`); optional FKs to `mes.ProductionReport`, `qms.IncomingInspection`, and `GRNLine` for full upstream traceability. Indexed on `(tenant, product, -posted_at)` and `(tenant, movement_type, -posted_at)`.
- **`StockTransfer`** — inter-warehouse header (auto `TRF-00001`); status `draft → in_transit → received / cancelled`; rejects same-warehouse source/dest in form clean.
- **`StockTransferLine`** — per-product line with `source_bin` / `destination_bin` / `lot` / `serial`. **Ship** posts an `issue` movement per line; **Receive** posts a matching `receipt` at the destination.
- **`StockAdjustment`** — header (auto `ADJ-00001`, admin-only), `reason` choice (`damage / loss / found / count_correction / expiry / quality_hold / other`), free-text `reason_notes` (required). Per-line system_qty vs actual_qty drives one `adjustment` movement per non-zero variance.
- **`StockAdjustmentLine`** — `system_qty`, `actual_qty`, computed `variance` property.

### Sub-module 8.4 — Cycle Counting & Physical Audit

- **`CycleCountPlan`** — recurring count schedule (`daily / weekly / monthly / quarterly`) with optional ABC-class filter.
- **`CycleCountSheet`** — auto `CC-00001`; status `draft → counting → reconciled / cancelled`; reconciliation posts one `cycle_count` `StockMovement` per non-zero variance line.
- **`CycleCountLine`** — `system_qty`, `counted_qty` (nullable while drafting), computed `variance`, `recount_required` flag set automatically when variance exceeds 5% (configurable in [`services/cycle_count.compute_variance`](apps/inventory/services/cycle_count.py)).
- **ABC classification** — pure function `classify_abc(consumption_by_product)` returns `{product_id: 'A' | 'B' | 'C'}` using a Pareto split (top 20% → A, next 30% → B, rest → C, deterministic on ties).

### Sub-module 8.5 — Lot / Serial / Batch Tracking

- **`Lot`** — `(tenant, product, lot_number)` unique; `manufactured_date`, `expiry_date`, `supplier_name`, `coa_reference`, status (`active / quarantine / expired / consumed`); `is_expiring_soon` property flips True at ≤30 days.
- **`SerialNumber`** — `(tenant, product, serial_number)` unique; status (`available / reserved / shipped / scrapped`); FK to its parent `Lot` (nullable).
- **FIFO / FEFO allocation** — pure functions in [`services/allocation.py`](apps/inventory/services/allocation.py). `allocate_fifo(rows, qty)` consumes oldest-first; `allocate_fefo(rows, qty)` consumes earliest-expiry-first (callers pre-sort the queryset). Raises `InsufficientStockError` with `requested` / `available` decimals attached when the pool can't cover.

### Cross-module integration

- **PLM** — added `Product.tracking_mode` enum (`none / lot / serial / lot_and_serial`) so other modules can enforce traceability rules; default `none`.
- **MES** — `apps/inventory/signals.py` listens on `mes.ProductionReport`. On `post_save` (created only) it auto-emits `StockMovement(production_in)` to the tenant's default warehouse for `good_qty > 0`. On `pre_delete` it issues a compensating reversal so the ledger never drifts. Both side-effects are silently skipped when no default warehouse / suitable storage bin is configured — the floor never gets blocked by inventory state.
- **QMS** — `GoodsReceiptNote.incoming_inspection` is an optional FK; the receipt flow can branch from a passing IQC inspection without touching QMS code.
- **MRP** — Module 5's `InventorySnapshot` is preserved as-is. Future tickets can add a sync that aggregates `StockItem.qty_on_hand` per product into the MRP snapshot — the data model is forward-compatible.

### Audit signals

[`apps/inventory/signals.py`](apps/inventory/signals.py) wires:
- `pre_save` + `post_save` on `Warehouse` → audit on creation and every `is_active` toggle.
- `pre_save` + `post_save` on `GoodsReceiptNote`, `StockTransfer`, `CycleCountSheet` → audit on creation and every status change (`inventory.<resource>.<status>` with `meta={'from': old, 'to': new}`).
- `post_save` on `StockAdjustment` → audit on creation only (status transitions go through admin-only views and are logged via the conditional UPDATE).
- `post_save` on `mes.ProductionReport` → auto `StockMovement(production_in)`.
- `pre_delete` on `mes.ProductionReport` → reverse the auto-emitted movement.

### Validation guards

- `WarehouseForm.clean()`, `WarehouseZoneForm.clean()`, `StorageBinForm.clean()`, `LotForm.clean()`, `SerialNumberForm.clean()`, `CycleCountPlanForm.clean()` enforce `(tenant, …)` `unique_together` (Lesson L-01) and reject duplicates with friendly field errors.
- `LotForm.clean()` rejects `expiry_date < manufactured_date`.
- `StockMovementForm.clean()` enforces movement-type semantics (which of `from_bin` / `to_bin` are required) so the form fails closed before reaching the service.
- `StockTransferForm.clean()` rejects same-warehouse source/dest.
- `StockAdjustmentForm.clean_reason_notes()` requires non-empty text.
- `services/movements.post_movement()` does the same checks at the service layer as a defence-in-depth guard, plus rejects negative qty and refuses to drive a bin balance below zero for operational types (`adjustment` / `cycle_count` are exempt — they exist to correct).

### Operator vs Admin matrix

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages | Authenticated tenant user | `TenantRequiredMixin` |
| File a GRN, complete a putaway task, post a movement, count a cycle-count line, ship/receive a transfer | Authenticated tenant user (operator) | `TenantRequiredMixin` |
| Warehouse / zone / bin CRUD, stock adjustment posting, cycle-count plan CRUD, manual lot creation, transfer cancel, GRN cancel, sheet reconcile, sheet delete | Tenant admin | `TenantAdminRequiredMixin` |

### Workflow buttons

| Resource | From | Action | To |
|---|---|---|---|
| GRN | `draft` | Receive (with strategy) | `putaway_pending` (PutawayTasks generated) |
| GRN | `draft` / `received` / `putaway_pending` | Cancel (admin) | `cancelled` |
| Putaway task | `pending` | Complete (with `actual_bin`) | `completed` (posts `receipt` movement; flips GRN → `completed` when last task done) |
| Transfer | `draft` | Ship | `in_transit` (one `issue` movement per line) |
| Transfer | `in_transit` | Receive | `received` (one `receipt` movement per line) |
| Transfer | `draft` | Cancel (admin) | `cancelled` |
| Adjustment | `draft` | Post (admin) | `posted` (one `adjustment` movement per non-zero variance line) |
| Cycle count sheet | `draft` | Start | `counting` |
| Cycle count sheet | `counting` | Reconcile (admin) | `reconciled` (variance movements posted) |

Every transition uses the conditional `UPDATE … WHERE status IN (…)` race-safe pattern so two operators racing on the floor cannot double-action.

### Test suite

Run the inventory test suite with `pytest apps/inventory/tests/` — uses [`config/settings_test.py`](config/settings_test.py). The suite covers model invariants + validators, pure-function services (`post_movement` atomicity, FIFO/FEFO allocation, ABC Pareto, variance math, putaway strategy), audit-log emission for every workflow, MES `ProductionReport` → auto `StockMovement` round-trip including `pre_delete` reversal, full CRUD smoke + workflow transitions across all sub-modules, RBAC matrix (operator vs admin), and multi-tenant IDOR guards. **101 tests, ~23 s runtime.**

### Out of scope (deferred)

- **Procurement integration** — `GRN.supplier_name` / `po_reference` are free-text strings until Module 9 ships and provides the FK.
- **Real-time barcode / RFID** — UI-driven workflow only in v1; REST endpoints for hardware are a follow-up.
- **WMS slot optimization** — directed putaway is rule-based (no genetic / ILP solver).
- **Wave / batch picking** — release picking is single-line v1; multi-order wave is a Module 17 (Sales) concern.
- **Negative stock** — operational moves (`receipt` / `issue` / `transfer`) reject. Adjustments + cycle counts can drive a bin to zero but never below; full back-orders / consigned stock is a follow-up.

---

## Module 9 — Procurement & Supplier Portal

Module 9 is implemented in [`apps/procurement/`](apps/procurement/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (PO snapshots, scorecard math, blanket consumption, conversion bridges) lives behind small pure-function services in [`apps/procurement/services/`](apps/procurement/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 9.1 — Purchase Order Management

- **`Supplier`** — vendor master. Fields: `code` (unique per tenant), `name`, `legal_name`, contact info, `tax_id`, `currency`, `payment_terms`, `delivery_terms`, `is_active`, `is_approved`, `risk_rating` (low / medium / high). Referenced by every other resource in the module.
- **`SupplierContact`** — per-supplier contact people; `is_primary` flag for the default reply-to.
- **`PurchaseOrder`** — auto-numbered **`PUR-00001`** per tenant. Workflow `draft → submitted → approved → acknowledged → in_progress → received → closed`, plus `rejected` and `cancelled` terminals. Carries denorm `subtotal` / `tax_total` / `discount_total` / `grand_total` (recomputed on every line save). Optional FKs: `source_quotation` (auto-created via RFQ Award), `blanket_order` (when issued under a long-term agreement).
- **`PurchaseOrderLine`** — `quantity ≥ 0.0001`, `tax_pct` / `discount_pct` 0–100, computed `line_subtotal / line_tax / line_discount / line_total` denorms.
- **`PurchaseOrderRevision`** — immutable JSON snapshot captured on every Revise action via [`services/po_revision.snapshot_po()`](apps/procurement/services/po_revision.py). PROTECT FK per Lesson L-17 — audit-trail child must outlive its parent.
- **`PurchaseOrderApproval`** — append-only log of every approve / reject decision with comments and timestamp.

Workflow buttons on the PO detail page: **Submit for Approval** (draft → submitted), **Approve** / **Reject** (submitted → approved / rejected; rejection requires comments per Lesson L-14), **Acknowledge** (approved → acknowledged; supplier user OR tenant admin), **Close** (received → closed), **Cancel** (any non-terminal → cancelled), **Revise** (snapshots the current PO + lines into `PurchaseOrderRevision` and reverts status to draft for further edits). Every transition uses the conditional `UPDATE … WHERE status IN (…)` race-safe pattern.

### Sub-module 9.2 — Supplier Quotation & RFQ

- **`RequestForQuotation`** — auto-numbered **`RFQ-00001`**. Workflow `draft → issued → closed → awarded`, plus `cancelled`. Multi-round bidding via the self-FK `parent_rfq` field; create a new RFQ that points back to the prior round.
- **`RFQLine`** — per-product line with `quantity`, `target_price` (internal-only, hidden from suppliers), `required_date`.
- **`RFQSupplier`** — invited-supplier matrix; `participation_status` tracks `invited / quoted / declined / no_response`.
- **`SupplierQuotation`** — auto-numbered **`QUO-00001`**; one per `(rfq, supplier)`. Carries `quote_date`, `valid_until`, `status` (`submitted → under_review → accepted / rejected`), and computed `subtotal / tax_total / grand_total` from its lines.
- **`QuotationLine`** — supplier's bid against a specific RFQ line: `unit_price`, `lead_time_days` (0–365), `min_order_qty`, `comments`. Computed `quoted_subtotal = unit_price × rfq_line.quantity`.
- **`QuotationAward`** — one-to-one with the RFQ. Records winning quotation + actor + timestamp + free-text rationale + `auto_create_po` flag.

The RFQ detail page exposes Issue → Close → Award workflow buttons. Award optionally invokes [`services/conversion.convert_quotation_to_po()`](apps/procurement/services/conversion.py) which materialises the winning quote into a draft `PurchaseOrder` with one PO line per quoted line. A side-by-side comparison matrix at `/procurement/rfq/<pk>/compare/` shows every line × every quotation in a single table for evaluation.

### Sub-module 9.3 — Supplier Performance Scorecard

- **`SupplierMetricEvent`** — append-only event log feeding scorecard math. Event types: `po_received_on_time / po_received_late / quality_pass / quality_fail / price_variance / response_received / response_missed`. Indexed on `(tenant, supplier, -posted_at)`.
- **`SupplierScorecard`** — periodic snapshot, unique per `(tenant, supplier, period_start, period_end)`. Stores `otd_pct`, `quality_rating`, `defect_rate_pct`, `price_variance_pct`, `responsiveness_rating`, `overall_score`, and `rank`.

**Weighted overall-score formula** (in [`services/scorecard.py`](apps/procurement/services/scorecard.py)):

```
overall = 0.40 × OTD_pct
        + 0.40 × quality_rating
        + 0.10 × responsiveness_rating
        + 0.10 × price_score   (price_score = 100 - |price_variance_pct|, only when there's data)
```

The pure-function `compute_scorecard(events)` is fully ORM-independent and accepts any iterable of objects exposing `event_type` and `value` — making it trivial to unit-test with stub events.

The Recompute action at `/procurement/scorecards/recompute/` walks every active supplier, sums the previous calendar month's events, computes scores, and updates / creates a `SupplierScorecard` row. Suppliers are then re-ranked by `overall_score` (descending) so the dashboard's "Top Suppliers" panel always reflects the current period.

### Sub-module 9.4 — Supplier Self-Service Portal

- **No parallel auth model** — Module 9 extends `accounts.User` with a new role `supplier` and a nullable FK `User.supplier_company → procurement.Supplier`. Internal staff are still scoped by `request.tenant`; supplier-portal users are *additionally* scoped by `request.user.supplier_company` so a supplier sees only its own POs / ASNs / invoices.
- **`SupplierPortalRequiredMixin`** — class-based view guard that enforces `role='supplier'` AND `supplier_company_id IS NOT NULL`. Internal admins hitting `/procurement/portal/` are redirected to the dashboard with a friendly toast.
- **`SupplierASN`** — auto-numbered **`ASN-00001`**. Workflow `draft → submitted → in_transit → received`, plus `cancelled`. Carries carrier, tracking number, total package count, expected arrival date.
- **`SupplierASNLine`** — per-PO-line shipped quantity with optional `lot_number` and free-text `serial_numbers`.
- **`SupplierInvoice`** — auto-numbered **`SUPINV-00001`** internally, plus `vendor_invoice_number` for the supplier's own number (unique per supplier). Workflow `submitted → under_review → approved → paid`, plus `rejected` and `disputed`. Optional `attachment` FileField (allowlist `.pdf .png .jpg .jpeg`, 25 MB cap). Marking an invoice paid requires a non-empty `payment_reference` per Lesson L-14.
- **`SupplierInvoiceLine`** — line-by-line breakdown with optional `po_line` cross-reference.

The portal layout uses a dedicated stripped-down [`templates/procurement/portal/portal_base.html`](templates/procurement/portal/portal_base.html) which hides the internal sidebar and shows only Dashboard / My POs / My ASNs / My Invoices / Profile. The internal Procurement sidebar group is conditionally hidden for `role='supplier'` users via `{% if request.user.role != 'supplier' %}`.

### Sub-module 9.5 — Blanket Orders & Scheduling Agreements

- **`BlanketOrder`** — auto-numbered **`BPO-00001`** long-term contract per supplier. Workflow `draft → active → closed → expired`, plus `cancelled`. Carries `total_committed_value` and `consumed_value` (denorm bumped by released schedule releases) so `remaining_value` is always one query away.
- **`BlanketOrderLine`** — per-product commitment with `total_quantity`, `consumed_quantity` (denorm), `unit_price`. Computed `remaining_quantity` property.
- **`ScheduleRelease`** — auto-numbered **`REL-00001`** call-off against a blanket. Workflow `draft → released → received`, plus `cancelled`. Computed `total_amount` from lines.
- **`ScheduleReleaseLine`** — per-blanket-line quantity with explicit form-level guard: `cumulative_consumption + new_qty ≤ blanket_line.total_quantity`. The service-layer [`consume_release()`](apps/procurement/services/blanket.py) uses a conditional `UPDATE … WHERE consumed_quantity ≤ total_quantity - new_qty` so two concurrent releases can never overdraw the commitment — the second one fails closed with a `ValueError`.

### Cross-module integration

| Touched | Bridge | Migration |
|---|---|---|
| `apps.accounts.User` | Added role `supplier` + nullable FK `supplier_company → procurement.Supplier`. Internal-staff queries can additionally exclude `role='supplier'` to keep portal users out of staff lists. | [`apps/accounts/migrations/0002_user_supplier_company_alter_user_role_and_more.py`](apps/accounts/migrations/) |
| `apps.inventory.GoodsReceiptNote` | Added nullable FKs `supplier → procurement.Supplier` and `purchase_order → procurement.PurchaseOrder` (legacy free-text columns kept for back-compat). | [`apps/inventory/migrations/0002_goodsreceiptnote_purchase_order_and_more.py`](apps/inventory/migrations/) |
| `apps.qms.IncomingInspection` | Added nullable FKs `supplier` and `purchase_order` (legacy free-text columns kept). | [`apps/qms/migrations/0003_incominginspection_purchase_order_and_more.py`](apps/qms/migrations/) |
| `apps.mrp.MRPPurchaseRequisition` | Added nullable FK `converted_po → procurement.PurchaseOrder` so MRP can navigate directly to its converted PO; the existing `converted_reference` text column stays as a back-compat fallback. The conversion service [`services/conversion.convert_pr_to_po()`](apps/procurement/services/conversion.py) is idempotent (returns the existing PO if `converted_po` is already set). | [`apps/mrp/migrations/0003_mrppurchaserequisition_converted_po_and_more.py`](apps/mrp/migrations/) |
| Cross-module signal: `inventory.GoodsReceiptNote.post_save` | When status flips to `completed` AND a `purchase_order` link exists, [`apps/procurement/signals.py`](apps/procurement/signals.py) emits a `SupplierMetricEvent(po_received_on_time)` or `(po_received_late)` keyed off `purchase_order.required_date` vs `received_date`. Skipped silently for legacy free-text GRNs. | (signal only) |
| Cross-module signal: `qms.IncomingInspection.post_save` | When status transitions to `accepted` / `accepted_with_deviation` / `rejected` AND a `supplier` link exists, emit `SupplierMetricEvent(quality_pass)` or `(quality_fail)`. Silently skipped for legacy free-text IQCs. | (signal only) |

Both cross-module hooks live inside `apps/procurement/signals.py` (not in inventory/qms) so removing the procurement app cleanly disables the events without leaving orphan code in other modules. Each hook stashes the previous status in its own `_proc_x_prev_status` attribute via a dedicated `pre_save` handler — that way the procurement code does not depend on the inventory/QMS modules' own naming conventions for stashed prev-status flags.

### Audit signals

[`apps/procurement/signals.py`](apps/procurement/signals.py) wires the standard `pre_save` + `post_save` audit pattern for every status-tracked model: `PurchaseOrder`, `RequestForQuotation`, `SupplierQuotation`, `SupplierASN`, `SupplierInvoice`, `BlanketOrder`, `ScheduleRelease`. Audit actions follow the convention `procurement.<resource>.<status>` (e.g. `procurement.po.approved`, `procurement.invoice.paid`) with `meta={'from': old, 'to': new}`. The factory `_mk_status_signals()` is invoked once per model and connects with `weak=False` (the inner closure handlers would otherwise be garbage-collected and the signals would silently never fire).

### Validation guards (apply Lessons L-01, L-02, L-14)

- Every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check (Lesson L-01).
- Every Decimal field carries explicit `MinValueValidator` + (where natural) `MaxValueValidator`: quantities ≥ 0.0001, percentages 0–100, money ≥ 0, lead-time 0–365 (Lesson L-02).
- Per-workflow forms enforce per-transition required fields (Lesson L-14): `PurchaseOrderApprovalForm.clean()` requires comments when decision is `rejected`; `QuotationAwardForm.clean_award_notes()` requires non-empty notes; `SupplierInvoiceWorkflowForm` requires `payment_reference` when `action='paid'`. `ScheduleReleaseLineForm.clean()` enforces blanket cumulative-consumption cap so the form fails closed before reaching the service layer.

### Operator vs Admin matrix

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, scorecards | Authenticated tenant user | `TenantRequiredMixin` |
| File a new ASN, complete a putaway task (post-receipt), submit a supplier invoice (any tenant user) | Authenticated tenant user | `TenantRequiredMixin` |
| Acknowledge a PO (supplier user OR tenant admin) | Either | `TenantRequiredMixin` + manual `is_tenant_admin` / `role==supplier` check |
| View own POs / ASNs / Invoices via `/procurement/portal/...` | Supplier user (`role='supplier'`) | `SupplierPortalRequiredMixin` (additionally scoped to `request.user.supplier_company_id`) |
| Supplier CRUD; PO create / edit / delete / approve / reject / close / cancel / revise; RFQ CRUD + workflow + Award; Quotation CRUD + accept/reject; ASN cancel + receive (internal); Invoice review / approve / pay / reject / dispute / delete; Blanket CRUD + activate / close / cancel; Release create / release / receive / cancel; scorecard recompute | Tenant admin | `TenantAdminRequiredMixin` |

A regression test file ([`apps/procurement/tests/test_security.py`](apps/procurement/tests/test_security.py) — `TestRBACMatrix`) asserts redirect + state-not-changed for every admin-gated POST, plus `TestMultiTenantIDOR` confirms cross-tenant reads/writes 404, plus `TestSupplierPortalIDOR` confirms a supplier-portal user only sees their own supplier's data.

### Test suite

Run the procurement test suite with `pytest apps/procurement/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory). The suite covers model invariants + decimal validators, form validation (L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required fields, blanket cumulative-consumption cap, file-extension allowlist, `subtotal+tax==grand_total` soft-check), pure-function services (`snapshot_po` round-trip, weighted `compute_scorecard` math across multiple event mixes, `consume_release` denorm updates with overdraw protection, `reverse_release` symmetry), audit signal emission across creation + transitions, **cross-module hooks** (GRN→`SupplierMetricEvent`, IQC→`SupplierMetricEvent`, plus the no-supplier-link skip path), full CRUD smoke + workflow happy paths, RBAC matrix (operator vs admin), multi-tenant IDOR (Globex blocked from Acme records), supplier-portal IDOR (portal user blocked from other suppliers' POs and from internal admin pages), and anonymous-redirect on every URL. **70 tests, ~27 s runtime.**

### Out of scope (deferred)

- **Real EDI / X.12 850 / 856 / 810** — UI-driven workflow only in v1.
- **Real e-signature on blanket contracts** — typed signature + timestamp only.
- **Multi-currency FX rate engine** — POs in non-tenant currency stored at face value; no auto-conversion.
- **ML-based supplier risk scoring** — `risk_rating` is a manual choice in v1.
- **Sourcing event auctions / reverse-bidding** — only static-price quotes in v1.
- **Supplier portal SSO (SAML / OAuth)** — deferred to Module 22 (System Admin & Security).
- **Email notification on RFQ Issue / PO Approve** — placeholder hook only; the actual `send_mail` call lives behind a TODO until the SMTP backend is wired in production.

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
| `python manage.py seed_pps [--flush]` | Seed PPS demo data (work centers, calendars, routings, MPS, production orders + scheduled operations, capacity load, scenario, optimizer run) per tenant |
| `python manage.py seed_mrp [--flush]` | Seed MRP demo data (forecast models + seasonality + completed forecast run, inventory snapshots, scheduled receipts, completed MRP run with planned orders / PRs / exceptions) per tenant |
| `python manage.py seed_mes [--flush]` | Seed MES demo data (operators, MES work orders fanned out from PPS production orders, time logs, production reports, andon alerts, work instructions with versions + acks) per tenant |
| `python manage.py seed_qms [--flush]` | Seed QMS demo data (IQC plans + inspections, IPQC plans + SPC chart with 25 points, FQC plans + inspections + CoAs, NCRs with RCA + CA + PA, equipment + calibration standards + records) per tenant |
| `python manage.py seed_inventory [--flush]` | Seed Inventory demo data (warehouses + zones + bins, lots + serials, initial stock via real movements, completed GRN with putaway, draft cycle-count sheet) per tenant |
| `python manage.py seed_procurement [--flush]` | Seed Procurement demo data (8 suppliers + 1 supplier-portal user, 4 RFQs incl. 1 awarded with 3 quotations, 6 POs across all statuses + 2 revisions, 2 ASNs, 2 invoices, 1 active blanket + 2 releases, ~80 metric events, 1 scorecard per supplier) per tenant |
| `python manage.py seed_data [--flush]` | Orchestrator that runs `seed_plans` + `seed_tenants` + `seed_plm` + `seed_bom` + `seed_pps` + `seed_mrp` + `seed_mes` + `seed_qms` + `seed_inventory` + `seed_procurement` |
| `python manage.py capture_health` | Capture a fresh health snapshot for every active tenant (schedule via cron) |
| `python manage.py runserver` | Dev server on port 8000 |
| `pytest apps/plm/tests/` | Run the PLM test suite (51 tests, ~3 s; uses [`config/settings_test.py`](config/settings_test.py)) |
| `pytest apps/pps/tests/` | Run the PPS test suite (58 tests, ~6 s; covers model bounds, form validation, RBAC, workflow, scheduler/optimizer, audit-log emission, query budgets) |
| `pytest apps/mes/tests/` | Run the MES test suite (142 tests, ~9 s; covers model invariants, dispatcher / time-logging / reporting services, forms, workflow, audit-log emission, multi-tenant IDOR, CSRF, plus 8 seeder-regression tests for the 6 BUGs found during the manual-test walkthrough) |
| `pytest --cov=apps/plm` | Run with coverage report |
| `pytest --cov=apps/pps` | Run PPS coverage report (services + signals + forms + models ≥ 84% each) |
| `pytest apps/qms/tests/` | Run the QMS test suite (85 tests, ~19 s; covers AQL table, SPC math + Western Electric rules, model invariants, form validation, IQC/FQC/NCR/Calibration workflow, RBAC matrix, multi-tenant IDOR, audit-log emission) |
| `pytest apps/inventory/tests/` | Run the Inventory test suite (101 tests, ~23 s; covers model invariants, services (post_movement, allocation, cycle_count math, putaway), audit + MES auto-emit signals, form validation, full CRUD + workflow smoke, RBAC matrix, multi-tenant IDOR) |
| `pytest apps/procurement/tests/` | Run the Procurement test suite (70 tests, ~27 s; covers model invariants + decimal validators, form validation (L-01 unique_together, L-02 bounds, L-14 per-workflow required, blanket cumulative-consumption cap), pure-function services (snapshot_po, weighted compute_scorecard, consume_release with overdraw protection), audit + cross-module signals (GRN→SupplierMetricEvent, IQC→SupplierMetricEvent), CRUD smoke + workflow happy paths, RBAC matrix, multi-tenant IDOR, supplier-portal IDOR, anonymous-redirect) |

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

Phase 1 (this release) covers the platform + **Module 1** (Tenant & Subscription), **Module 2** (Product Lifecycle Management), **Module 3** (Bill of Materials), **Module 4** (Production Planning & Scheduling), **Module 5** (Material Requirements Planning), **Module 6** (Shop Floor Control / MES), **Module 7** (Quality Management / QMS), **Module 8** (Inventory & Warehouse Management), and **Module 9** (Procurement & Supplier Portal). The 13 upcoming modules are fully specified in [`MSM.md`](./MSM.md):

2. ~~Product Lifecycle Management (PLM)~~ ✅ shipped
3. ~~Bill of Materials (BOM)~~ ✅ shipped
4. ~~Production Planning & Scheduling~~ ✅ shipped
5. ~~Material Requirements Planning (MRP)~~ ✅ shipped
6. ~~Shop Floor Control (MES)~~ ✅ shipped
7. ~~Quality Management (QMS)~~ ✅ shipped
8. ~~Inventory & Warehouse~~ ✅ shipped
9. ~~Procurement & Supplier Portal~~ ✅ shipped
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
