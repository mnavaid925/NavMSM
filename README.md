# NavMSM — Manufacturing / Production Management System

A multi-tenant, modular Django + Bootstrap 5 platform for managing the full manufacturing lifecycle — from tenant onboarding, billing and branding, through production planning, shop-floor execution, quality, inventory, procurement, and beyond.

This repository contains **Phase 1** of the platform: the core foundation plus **Module 1 — Tenant & Subscription Management**, **Module 2 — Product Lifecycle Management (PLM)**, **Module 3 — Bill of Materials (BOM) Management**, **Module 4 — Production Planning & Scheduling**, **Module 5 — Material Requirements Planning (MRP)**, **Module 6 — Shop Floor Control (MES)**, **Module 7 — Quality Management (QMS)**, **Module 8 — Inventory & Warehouse Management**, **Module 9 — Procurement & Supplier Portal**, **Module 10 — Equipment & Asset Management (EAM)**, **Module 11 — Labor & Workforce Management**, **Module 12 — Cost Management & Accounting**, **Module 13 — Compliance & Regulatory Management**, **Module 14 — Energy & Utility Management**, **Module 15 — IoT & SCADA Integration**, **Module 16 — Business Intelligence & Analytics**, **Module 17 — Sales & Customer Order Management**, **Module 18 — Returns & RMA Management**, **Module 19 — Document & Knowledge Management**, and **Module 20 — Workflow & Business Process Automation**. The remaining functional modules listed in [`MSM.md`](./MSM.md) are planned as follow-up phases.

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
21. [Module 10 — Equipment & Asset Management (EAM)](#module-10--equipment--asset-management-eam)
22. [Module 11 — Labor & Workforce Management](#module-11--labor--workforce-management)
23. [Module 12 — Cost Management & Accounting](#module-12--cost-management--accounting)
24. [Module 13 — Compliance & Regulatory Management](#module-13--compliance--regulatory-management)
25. [Module 14 — Energy & Utility Management](#module-14--energy--utility-management)
26. [Module 15 — IoT & SCADA Integration](#module-15--iot--scada-integration)
27. [Module 16 — Business Intelligence & Analytics](#module-16--business-intelligence--analytics)
28. [Module 17 — Sales & Customer Order Management](#module-17--sales--customer-order-management)
29. [Module 18 — Returns & RMA Management](#module-18--returns--rma-management)
30. [Module 19 — Document & Knowledge Management](#module-19--document--knowledge-management)
31. [Module 20 — Workflow & Business Process Automation](#module-20--workflow--business-process-automation)
32. [UI / Theme Customization](#ui--theme-customization)
33. [Management Commands](#management-commands)
34. [Payment Gateway Integration](#payment-gateway-integration)
35. [Manual-Test Walkthroughs](#manual-test-walkthroughs)
36. [Security Notes](#security-notes)
37. [Roadmap](#roadmap)
38. [Troubleshooting](#troubleshooting)
39. [License](#license)

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
- **Module 10 — Equipment & Asset Management (EAM)** — asset master (auto `ASSET-00001`) with parent-child hierarchy (`CNC-LATHE-01 → SPINDLE-01`), 6-level taxonomy of `AssetCategory` rows, optional `inventory.Warehouse` location FK, criticality / status enums, append-only `AssetMeterReading` ledger (hours / cycles / mileage / kWh) and per-asset `AssetSparePart` linkage to `plm.Product`; preventive maintenance plans with calendar / meter / both triggers, ordered checklist `MaintenanceTask` rows, idempotent `generate_pm_schedules` management command + on-demand `Generate Upcoming` button that materialises future `PMSchedule` rows (auto `PMS-00001`) via the pure `services/pm_scheduler.py`; predictive maintenance with sensor-style `ConditionMonitoringPoint` (vibration / temperature / pressure / current / oil-quality) and append-only `ConditionReading` rows auto-classified `normal / warning / critical` by the heuristic `services/prediction.py`, and a post-save signal that auto-spawns `FailurePrediction` rows on critical readings (with idempotency against existing open predictions); `MaintenanceWorkOrder` (auto `MWO-00001`) with `breakdown / preventive / corrective / predictive / inspection` types, `draft → scheduled → in_progress → on_hold → completed → cancelled` workflow guarded by L-03 view/template parity, race-safe conditional `UPDATE`, append-only `MWOLaborLog` (auto-computed minutes + total cost) + `MWOMaterialLog` (with optional `inventory.StockMovement` FK), and per-asset `DowntimeEvent` ledger that auto-refreshes the parent MWO's `downtime_minutes` denorm; tool & die management with `Tool` (auto `TOOL-00001`, types `mold / die / jig / fixture / cutting_tool / gauge`), append-only `ToolUsageLog` + atomic denorm bump via `services/tool_life.py`, `ToolMaintenanceRecord` for sharpening / cleaning / repair / calibration / inspection (with 25 MB attachment cap, allowlist `.pdf .png .jpg .jpeg`), and per-cavity `MoldCavityHistory` for mold-type tools; cross-module hooks: an `mes.AndonAlert(type='equipment', asset=<asset>)` post-save auto-creates a draft breakdown MWO (idempotent via `source_andon`), and a `mes.ProductionReport` post-save against an op whose work order has `tool=<tool>` set auto-emits a `ToolUsageLog` plus atomic `Tool.current_cycles` bump.
- **Module 9 — Procurement & Supplier Portal** — supplier master with code/risk/approval flags (8 seeded per tenant); purchase orders (auto `PUR-00001`) with full `draft → submitted → approved → acknowledged → in_progress → received → closed` workflow, line-level tax/discount/total denorms, race-safe conditional UPDATE on every transition, immutable `PurchaseOrderRevision` snapshots on every Revise action, and append-only approval log; multi-round RFQs (auto `RFQ-00001`) with invited-supplier matrix, side-by-side quote comparison view, and one-click Award action that optionally drafts a real PO from the winning quotation; supplier scorecards with weighted overall score (40% OTD + 40% Quality + 10% Responsiveness + 10% Price) computed by a pure-function service from append-only `SupplierMetricEvent` rows; **cross-module event hooks** that auto-emit OTD events when `inventory.GoodsReceiptNote` flips to completed and quality pass/fail events when `qms.IncomingInspection` is accepted/rejected; supplier self-service portal (role=`supplier` user with `supplier_company` FK) for ASN submission (auto `ASN-00001`), invoice upload (auto `SUPINV-00001`, 25 MB attachment cap), and own-PO visibility — every portal queryset is scoped to `request.user.supplier_company`; long-term blanket orders (auto `BPO-00001`) with periodic schedule releases (auto `REL-00001`) that consume the parent commitment via a race-safe conditional UPDATE so concurrent releases can never overdraw.
- **Module 12 — Cost Management & Accounting** — standard costing with effective-dated `StandardCostVersion` (auto `SCV-00001`) + per-product `StandardCost` rows recomputable from `bom.BOMCostRollup`; actual cost tracking via `ActualCost` rollups per production order + 6-axis `CostVariance` (auto `VAR-00001`: material price/usage, labor rate/efficiency, overhead spending/volume); WIP accounting with one `JobCost` (auto `JC-00001`) per `pps.ProductionOrder` and an append-only `WIPEntry` ledger (auto `WIP-00001`) covering material_issued / labor_applied / overhead_applied / completion / variance / adjustment with operation-wise rollup; ABC overhead allocation via `CostDriver` / `OverheadPool` / `OverheadRate` / `DriverActuals` / `OverheadAllocation` (auto `OHA-00001`) with idempotent `apply_overhead(period)` orchestrator and reverse path; manufacturing financial reports — `AccountingPeriod` (auto `ACP-00001`) with `open → locked → closed` workflow, `COGMReport` (auto `COGM-00001` = opening WIP + DM + DL + OH applied − closing WIP), per-product `GrossMarginReport` (revenue − cogs), and `PlantPnLReport` (revenue − COGM − SG&A − unallocated overhead); cross-module hooks: `labor.LaborBooking(kind=direct)` post_save → `WIPEntry(labor_applied)` (idempotent on `(source_labor_booking, entry_type)`); `labor.LaborBooking(kind=indirect)` → `OverheadActualPool` accumulation; `mes.ProductionReport(good_qty>0)` → `WIPEntry(completion)` at standard cost (with `pre_delete` reversal); ApexCharts dashboard with COGM stacked-bar trend + variance bar.
- **Module 14 — Energy & Utility Management** — utility meter integration with tenant-catalog `UtilityType` (electricity / water / natural_gas / steam / compressed_air / fuel_oil) optionally bridged to `cost.CostDriver`, auto-numbered `UtilityMeter` (`MTR-00001`) supporting parent-child sub-metering + optional `eam.Asset` link, append-only `UtilityConsumption` ledger (auto `UC-00001`) with `consumption = (end − start) × multiplier` + `total_cost = consumption × unit_cost` computed in `save()`; energy cost allocation with effective-dated `UtilityTariff` (auto `TRF-00001`) carrying flat-rate fall-back, period-scoped `UtilityAllocation` (auto `UAL-00001`) across cost-center / product / production-order targets via `meter_consumption / production_volume / floor_area / direct_assignment` methods and a [`services/allocation.post_allocation()`](apps/utility/services/allocation.py) writer that emits matching `cost.DriverActuals` so the existing `cost.services.overhead.apply_overhead(period)` sweeps utility cost into the Utilities pool automatically; peak-demand management with `TOURateBand` (peak / shoulder / off_peak across weekday / weekend / per-day windows), `DemandResponseEvent` (auto `DRE-00001`) workflow `scheduled → active → completed | cancelled`, and read-only `PeakShavingSuggestion` (auto `PSS-00001`) generated by [`services/peak.scan_for_peak_overlap`](apps/utility/services/peak.py) that flags `pps.ScheduledOperation` rows overlapping a peak window with `new → acknowledged → dismissed` workflow (never mutates the PPS schedule); carbon & sustainability reporting with effective-dated `EmissionFactor` per `(source_type, scope, region)` (Scope 1 / 2 / 3 with `PROTECT` audit trail), append-only `CarbonEmission` ledger (auto `CE-00001`) auto-emitted via signal from `UtilityConsumption.post_save` (idempotent on `source_consumption`) and per-period `SustainabilityKPI` headline ESG snapshot (totals across scopes + kWh/water/gas + units produced + intensity ratios); utility benchmarking with `BenchmarkSnapshot` per period × plant (per-unit kWh / water / CO2e / cost denorms computed in `save()`) plus tenant-`NULL` industry-average rows, and `BenchmarkComparison` reports (auto `BCR-00001`) for plant-to-plant / period-over-period / tenant-vs-industry comparisons; cross-module hooks: `eam.AssetMeterReading.post_save (meter_type='kwh')` → `UtilityConsumption` (idempotent on `source_meter_reading`); `UtilityConsumption.post_save` → `CarbonEmission` (resolves active factor + accounting period); `UtilityAllocation.post_allocation()` → `cost.DriverActuals`.
- **Module 11 — Labor & Workforce Management** — workforce master with auto-numbered `EMP-00001` employees, departments + positions + skills + certifications with expiry tracking; time & attendance with shifts, rosters, attendance records, leave types, leave requests (auto `LR-00001`) with `draft → submitted → approved / rejected → cancelled` workflow, and a tenant-level holiday calendar; labor cost allocation with cost centers, employee labor rates, and an append-only `LaborBooking` ledger (auto `LB-00001`) auto-emitted from `mes.OperatorTimeLog stop_job` (direct labor) and `eam.MWOLaborLog` (indirect labor) — both idempotent via natural-key dedup; training & competency management with programs, per-employee training plans, sessions (auto `TS-00001`) with attendance tracking, and competency assessments (auto `CA-00001`) with skill-gap analysis; incentive & piece-rate calculation with schemes, per-product / per-operation piece rates, monthly periods (`open → locked → paid`), and runs (auto `INC-00001`) that scan `mes.ProductionReport` rows and accumulate `IncentiveLine` totals with idempotent rerun; cross-module hooks: `mes.ShopFloorOperator.employee → labor.Employee` (soft link), `plm.Product.cost_center → labor.CostCenter`, `eam.Asset.cost_center → labor.CostCenter`. ApexCharts dashboard with attendance % trend (30d) + labor-cost-by-cost-center donut.
- **Module 5 — Material Requirements Planning (MRP)** — statistical forecast models (moving avg / weighted MA / exp smoothing / naive seasonal) with seasonality profiles and run history; per-product inventory snapshot with safety stock, reorder point, lead time, and lot-sizing rule (L4L / FOQ / POQ / Min-Max); scheduled receipts (open POs, planned production, transfers); regenerative / net-change / simulation MRP runs that explode multi-level BOMs via `bom.BillOfMaterials.explode()` to compute gross-to-net requirements; auto-generation of MRP-suggested purchase requisitions for purchased items; exception engine producing late-order / expedite / defer / no-bom action messages with severity and recommended action; one-click commit / discard.
- **Module 15 — IoT & SCADA Integration** — device connectivity hub with shared `DeviceProtocol` catalog (MQTT / OPC-UA / Modbus TCP+RTU / HTTP polling / CoAP), tenant-scoped `DeviceBroker` (auto `BRK-00001`) with TLS / username-password / cert / token auth, `Device` (auto `DEV-00001`) optionally linked to `eam.Asset`, and `DeviceTag` whose optional `eam.ConditionMonitoringPoint` FK drives the IoT→EAM cascade; real-time data acquisition with append-only `IoTReading` ledger (auto `IR-00001`), `IoTReadingBatch` envelope for JSON/CSV ingest via `services/ingestion.bulk_ingest`, pure-function `EdgeProcessor` transforms, and `StreamMetric` 1-to-1 denorm (latest value + 24h min/max/avg + count) refreshed by post-save signal; digital twin configuration with `DigitalTwin` (auto `DT-00001`), `TwinStateAttribute` (state / measurement / derived) using a security-critical whitelist-only formula evaluator (`services/twin._safe_eval` — never `eval()`/`exec()`), `TwinSimulationScenario` (auto `TSC-00001`) run by a pure-function simulator that never mutates persisted state, and `TwinStateSnapshot` for time-travel debugging; OEE monitoring with `MachineStateLog` (auto-idempotent on `eam.DowntimeEvent` cascades) feeding Availability, `mes.ProductionReport` feeding Performance + Quality, `pps.RoutingOperation.cycle_seconds` providing ideal cycle, all rolled up to `OEEPeriod` (auto `OEEP-00001`) with A × P × Q × OEE % computed in `save()`, and a `LossReason` Pareto driving the OEE dashboard; alert & anomaly detection with `AlertRule` (auto `AR-00001`) supporting threshold_high / threshold_low / range_outside / rate_of_change / missing_data / rolling z-score / IQR / Western-Electric runs rule (heuristic-only, no ML deps), XOR-validated scope (tag / device / asset), per-channel notification routing (`in_app / email / mes_andon`), and cooldown suppression; append-only `AnomalyDetection` (auto `AD-00001`) with `new → acknowledged → resolved | false_positive` workflow (resolution notes required at terminal transitions per L-14); cross-module hooks: `IoTReading.post_save → eam.ConditionReading` (when tag has `condition_point`), `AnomalyDetection.post_save → mes.AndonAlert` (severity ≥ high + `mes_andon` channel), `AnomalyDetection.post_save → eam.FailurePrediction` (severity = critical), `mes.ProductionReport.post_save → OEEPeriod` denorm refresh, `eam.DowntimeEvent.post_save → MachineStateLog` (idempotent on `source_downtime`). **Security flags:** `DeviceBroker.password_hash` is a stop-gap stable token (rotate to KMS / Vault for production); twin formulas evaluated by `_safe_eval` (whitelist of `+ - * / ()`, `min/max/abs`, variable refs, decimal numbers) — `eval()` / `exec()` are never called.
- **Module 16 — Business Intelligence & Analytics** — KPI definitions catalog (9 built-in: OEE / throughput / first-pass yield / scrap rate / on-time delivery / supplier OTD / gross margin / energy intensity / carbon intensity) with `higher_is_better` / `lower_is_better` direction + warning / critical thresholds, dispatched via a pluggable [`KPI_REGISTRY`](apps/bi/services/kpi.py) of pure-function calculators; named `KPIDashboard` surfaces grouping `KPIWidget` placements (chart_type ∈ kpi_card / line / bar / donut / gauge / sparkline) with `default_period` (last_7d / last_30d / mtd / qtd / ytd / custom) + `auto_refresh_minutes`; materialized `KPISnapshot` per (definition, period, scope) so widgets render in O(1); form-based ad-hoc report builder over a static whitelist of registered data sources (`production_orders` / `production_reports` / `non_conformance_reports` / `supplier_invoices` / `utility_consumption` / `failure_predictions` / `oee_periods` / `gross_margin_reports` / `cogm_reports` / `stock_movements` / `carbon_emissions` / `supplier_metric_events`), executor (`services/reports.execute_report`) builds Django ORM queries from `ReportField` + `ReportFilter` rows scoped to `tenant=request.tenant`, never raw SQL, never an un-whitelisted field; pure-Python heuristic predictors (no NumPy / scikit-learn): linear-regression demand forecast, rolling-failure-rate likelihood, SPC chart trend; `PredictionRun` + `PredictionResult` ledger plus `TrendAnalysis` slope/r-squared/direction summaries (auto `PR-` / `TA-`); tenant-isolated data marts with admin-defined `source_definition` JSON (model_label + group_by + measures + lookback_days), refresh service (`services/datamart.refresh_mart`) wipes prior snapshot rows inside an atomic block then materializes a fresh `DataMartSnapshot` + child `DataMartRow` rows; automated `ReportSchedule` (auto `SCH-`) with `daily / weekly / monthly / custom` frequencies, XOR-validated bind to a Report or Dashboard, fan-out `ReportRecipient` rows, `ReportDelivery` ledger with status, generated `ReportExport` artifacts (CSV / xlsx / pdf_html / inline_email with allowlist + 25 MB cap), sent via Django `send_mail`; cron-style `run_report_schedules` management command; cross-module hook on `cost.AccountingPeriod` going to `status='closed'` refreshes all active KPI snapshots for the period. **93 tests** in [`apps/bi/tests/`](apps/bi/tests/) covering models, forms (L-01 / L-14 / XOR), services (registry whitelist, KPI classification, linear regression, rolling avg, chart trend), signals (L-18 dispatch_uid), HTTP CRUD smoke, multi-tenant IDOR (cross-tenant 404 on every detail URL), RBAC matrix (staff blocked from create/delete), anonymous-redirect on every list URL, and seeder idempotency.
- **Module 19 — Document & Knowledge Management** — 17 models across 5 sub-modules covering the full controlled-document lifecycle. **19.1 Controlled Document Repository** — hierarchical `DocumentCategory` catalog, `Document` (auto `DOC-00001`) with 10-type taxonomy (sop / work_instruction / policy / form / manual / specification / report / drawing / training_material / other), `draft → in_review → approved → effective → superseded → archived` workflow, denorm `current_version` pointer, `DocumentVersion` with check-in/check-out optimistic lock ([`services/checkout.py`](apps/dms/services/checkout.py), conditional `UPDATE ... WHERE checked_out_by IS NULL`), 25 MB file cap + extension allowlist (L-22), `DocumentAccessRule` for per-document RBAC overrides via XOR (User / Department / Position). **19.2 SOP & Work Instruction Authoring** — `DocumentTemplate` (auto `TPL-00001`) with `{{placeholder}}` body + typed `TemplateField` rows; `MediaAttachment` per version (image / video / audio / pdf, http(s)-only embed URLs, 25 MB cap). **19.3 Document Approval Workflows** — reusable `ApprovalWorkflow` with ordered `ApprovalStage` rows (per-stage `approver_role` + `min_approvals` + `requires_signature`), `DocumentApprovalRequest` (auto `AR-00001`) with `pending → in_progress → approved | rejected | cancelled` workflow guarded by [`services/approval.py`](apps/dms/services/approval.py), append-only `ApprovalAction` log, **immutable `DocumentSignature` (FDA 21 CFR Part 11)** with `pre_save` guard rejecting any UPDATE + admin `readonly_fields = '__all__'`; final approval flips `Document` to `effective` and sets `effective_date`. **19.4 Training Document Assignment** — `DocumentAssignment` (auto `DA-00001`) with `active → completed | cancelled` workflow, `AssignmentTarget` XOR fan-out (role / department / position / employee / user), `ReadAcknowledgment` (auto `ACK-00001`) with typed-name e-sig pinned to the released `DocumentVersion` (unique on `(assignment, acknowledger, document_version)` so re-acks land per released revision); user-facing **My Acknowledgments** page collects every pending ack across the tenant. **19.5 Archive & Retention Policy** — `RetentionPolicy` (auto `RP-00001`, configurable years + archive / soft_delete / hard_delete action), `DocumentArchive` (auto `ARC-00001`) with `archived → restored → purged` workflow + L-14 restore notes required, `LegalHold` (auto `LH-00001`) M2M-pinning Documents; an active hold cascades `Document.is_locked=True` via `m2m_changed` signal + [`services/legal_hold.py`](apps/dms/services/legal_hold.py) that re-checks remaining holds on release, and a `pre_delete` guard refuses to delete a locked Document. **6 cross-module signal handlers** (all `dispatch_uid` / L-18-safe / L-23 best-effort): version-released supersedes prior + bumps `current_version`, approval-approved flips Document to effective, legal-hold M2M change cascades `is_locked`, retention denorm refresh on policy/doc save, signature immutability enforcement, locked-doc delete refusal. Time-driven cron — `archive_due_documents` race-safe-flips `effective → archived` past `retention_until` (skips active legal holds, L-21); `expire_assignments` reports overdue assignments. **116-test pytest suite** in [`apps/dms/tests/`](apps/dms/tests/) covering model auto-numbering + computed fields + L-22 validators ([`test_models.py`](apps/dms/tests/test_models.py)), L-01 unique_together + L-22 file caps + XOR validators + L-14 per-workflow required ([`test_forms.py`](apps/dms/tests/test_forms.py)), services (checkout optimistic-lock + holder/admin override, retention math with leap-day clamp, legal-hold cascade with multi-hold safety, approval stage advancement) ([`test_services.py`](apps/dms/tests/test_services.py)), all 6 cross-module signal cascades + idempotency ([`test_signals.py`](apps/dms/tests/test_signals.py)), full HTTP CRUD + approval workflow walk (multi-stage approve → effective) + assignment ack idempotency ([`test_views.py`](apps/dms/tests/test_views.py)), multi-tenant IDOR (cross-tenant 404) + RBAC matrix (staff blocked from delete / archive / legal-hold / approval-action — L-10) + anonymous-redirect ([`test_security.py`](apps/dms/tests/test_security.py)), and `seed_dms` idempotency + `--flush` consistency + cron dry-run safety ([`test_seeder.py`](apps/dms/tests/test_seeder.py)).
- **Module 20 — Workflow & Business Process Automation** — 22 models across 5 sub-modules covering the full BPM lifecycle. **20.1 Visual Workflow Designer** — hierarchical `ProcessCategory` catalog, `ProcessDefinition` (auto `BPM-00001`) versioned with `draft → active → archived` workflow + canonical `bpmn_model` JSON blob + indexed `ProcessNode` / `ProcessTransition` rows; `ProcessInstance` (auto `PI-00001`) runtime row bound to any tenant business object via `(business_object_type, business_object_id)`; `ProcessVariable` typed runtime store; append-only `ProcessActivity` log; transition `condition_expr` evaluated by a SECURITY-CRITICAL whitelist parser in [`services/bpmn_engine._safe_eval`](apps/wfa/services/bpmn_engine.py) that mirrors the `iot.twin` pattern and **rejects** `__import__`/`exec`/`lambda`/attribute access/`**` operator — never `eval()`/`exec()`; server-side SVG diagram (no JS canvas dependency). **20.2 Approval Engine** — `ApprovalPolicy` + ordered `ApprovalLevel` rows (per-level `approver_role` / `min_approvers` / `sla_hours`), `ApprovalRequest` (auto `APR-00001`) with `pending → in_progress → approved | rejected | cancelled | escalated` workflow guarded by race-safe conditional UPDATE in [`services/approval.py`](apps/wfa/services/approval.py); append-only `ApprovalActionLog` (immutable in admin); `ApprovalDelegation` for vacation/coverage routing with date-range guard; `EscalationRule` per-level SLA timer driving cron-based escalation. **20.3 Notification & Escalation Matrix** — `NotificationChannel` (email / sms / in_app / webhook), `NotificationTemplate` with Django-template subject/body + `channels` list, `NotificationRule` (auto `NR-00001`) fired from any event_type, `Notification` (auto `NTF-00001`) per-recipient with append-only `NotificationDelivery` log per channel via [`services/notification.dispatch`](apps/wfa/services/notification.py); SMS ships as a **logger stub** (`SMSDelivery` ledger so QA can verify wiring without a Twilio account — swap in a real provider in `dispatch_sms`). **20.4 Integration Orchestration** — `Connector` (auto `CON-00001`) with 11 connector_type values (rest_api / webhook / file_drop / db_pull / erp_sap / erp_oracle / erp_dynamics / erp_netsuite / crm_salesforce / crm_hubspot / other), `ConnectorEndpoint` per-route, `IntegrationFlow` with ordered `FlowStep` rows (http_call / transform / branch / log / sleep) executed by pure-function [`services/integration.execute_flow`](apps/wfa/services/integration.py); append-only `IntegrationRun` (auto `IR-00001`) ledger + `WebhookOutboxEntry` for outbound delivery retries. **Security flag:** `Connector.auth_secret_hash` is a stop-gap stable token (mirrors `iot.DeviceBroker.password_hash`); rotate to KMS/Vault for production. **20.5 Process Mining & Optimization** — `ProcessMetric` per-instance per-metric_type, `BottleneckAnalysis` (auto `BA-00001`) per-period with [`services/process_mining.detect_bottleneck`](apps/wfa/services/process_mining.py) heuristic, `ProcessOptimizationSuggestion` (auto `POS-00001`) with `new → acknowledged → dismissed | applied` workflow, `CycleTimeReport` (auto `CTR-00001`) with avg/p95/min/max statistics. **8 cross-module signal hooks** (all `dispatch_uid` / L-18 / L-23 best-effort): instance status change → activity log + audit, instance completed → cycle-time metric refresh, approval approved/rejected/escalated → notification fanout, pending notification auto-dispatch (zero delay), integration-failed → failure notification, `dms.DocumentApprovalRequest.approved` → close linked `wfa.ApprovalRequest`, `procurement.PurchaseOrder.submitted` → auto-create `wfa.ApprovalRequest` (gated on active policy — zero behavior change if no policy is configured). Time-driven cron — `escalate_approvals` race-safe-flips overdue `pending/in_progress → escalated` past `due_at` (L-21); `run_notifications` dispatches due pending rows; `mine_processes` regenerates bottleneck + cycle-time reports across the active definitions; all support `--dry-run` + `--tenant <slug>`. **98-test pytest suite** in [`apps/wfa/tests/`](apps/wfa/tests/) covering model auto-numbering + computed fields + L-02 validators ([`test_models.py`](apps/wfa/tests/test_models.py)), L-01 unique_together `clean()` + L-14 per-workflow required ([`test_forms.py`](apps/wfa/tests/test_forms.py)), pure-function services (BPMN whitelist parser rejecting `__import__`/`lambda`/`**`/attribute access, approval transition state machine, notification dispatch + delivery ledger, integration flow log step, mining severity classification + cycle stats) ([`test_services.py`](apps/wfa/tests/test_services.py)), cross-module signal cascades + L-18 dispatch_uid + audit-log emission ([`test_signals.py`](apps/wfa/tests/test_signals.py)), HTTP CRUD + multi-stage approval walk + flow run + instance advance ([`test_views.py`](apps/wfa/tests/test_views.py)), multi-tenant IDOR + RBAC matrix (staff blocked from policy/process/connector mutations — L-10) + anonymous-redirect ([`test_security.py`](apps/wfa/tests/test_security.py)), and `seed_wfa` idempotency + cron dry-run safety ([`test_seeder.py`](apps/wfa/tests/test_seeder.py)).
- **Module 18 — Returns & RMA Management** — 16 models across 5 sub-modules covering the full returns lifecycle. **18.1 RMA Request & Authorization** — tenant-scoped `RMAReason` catalog and `RMARequest` (auto `RMA-00001`) with `draft → submitted → approved | rejected → cancelled` workflow gated to tenant admins (L-10); RMA lines link to `plm.Product` + `sales.Customer` + optional `sales.SalesOrder` / `sales.SalesInvoice`, and an append-only `RMAApproval` log records every transition. **18.2 Returns Receiving & Inspection** — `ReturnReceipt` (auto `RR-00001`) auto-drafted by a `RMARequest.status='approved'` signal (idempotent on `rma` FK); per-line condition (`new / like_new / used / damaged / defective / scrap`) + disposition (`restock / repair / refurbish / scrap / return_to_supplier / quarantine`) drives the routing signal — `restock` posts an `inventory.StockMovement(type='receipt')` into the receipt's warehouse, `repair`/`refurbish` auto-drafts a `RepairOrder`, with a `disposition_done` idempotency latch so re-saves never double-emit. **18.3 Repair & Refurbishment Tracking** — `RepairOrder` (auto `REP-00001`) with `draft → in_progress → on_hold → completed → cancelled` workflow (resolution notes required at completion, L-14), append-only `RepairPartUsage` (computed `line_cost = qty × unit_cost` in `save()`) and `RepairLaborLog` (computed `labor_cost = minutes/60 × hourly_rate`) ledgers; both feed [`services/repair.recompute_repair_costs`](apps/rma/services/repair.py) so `RepairOrder.actual_cost` + `labor_minutes` denorms stay consistent (with `pre_delete` reversal via `on_commit` so the rollup excludes deleted parts); a `RepairLaborLog` post-save signal mirrors each entry into a `labor.LaborBooking(kind='indirect')` (idempotent on `labor_booking` FK). **18.4 Warranty Management** — reusable `WarrantyPolicy` (auto `WP-00001`, coverage `parts / labor / parts_and_labor / full`, configurable duration), `WarrantyRegistration` (auto `WR-00001`) with computed `end_date = start_date + policy.duration_months` (via [`services/warranty.compute_warranty_end`](apps/rma/services/warranty.py) — month-end-clamped, no `dateutil` dep), red/yellow expiry tinting at ≤30 days (`is_expiring_soon` property), and a daily `expire_warranties` management command that race-safe-flips `active → expired` past `end_date` (L-21); `WarrantyClaim` (auto `WC-00001`) with `submitted → validated → approved | rejected → fulfilled` workflow — an approved claim with `resolution='replace'` auto-drafts a `sales.SalesOrder` replacement (idempotent on `replacement_order` FK). **18.5 Returns Analytics** — tenant catalogs `FailureMode` (FMEA-style with `electrical / mechanical / software / cosmetic / material / process / other`) and `RootCauseCategory` (responsible area `design / manufacturing / supplier / logistics / installation / user_error / unknown`); `ReturnAnalysis` (auto `RA-00001`) per RMA line carrying optional `procurement.Supplier` FK for supplier-caused returns; `SupplierChargeback` (auto `SCB-00001`) with workflow `draft → pending → issued → disputed → recovered | written_off` guarded by [`services/chargeback.apply_transition`](apps/rma/services/chargeback.py) (illegal transitions raise `ValueError`). **93-test pytest suite** in [`apps/rma/tests/`](apps/rma/tests/) covering model auto-numbering + computed fields + validators ([`test_models.py`](apps/rma/tests/test_models.py)), tenant-scoped form `clean()` (L-01) + FK queryset isolation ([`test_forms.py`](apps/rma/tests/test_forms.py)), services (warranty math, disposition routing, repair rollup, chargeback transitions) ([`test_services.py`](apps/rma/tests/test_services.py)), all 6 cross-module signal hooks + idempotency on re-save ([`test_signals.py`](apps/rma/tests/test_signals.py)), CRUD smoke + workflow happy paths + filter regression ([`test_views.py`](apps/rma/tests/test_views.py)), multi-tenant IDOR (cross-tenant 404 on every detail URL) + RBAC matrix (staff blocked from submit / approve / complete / chargeback transition / delete — L-10) + anonymous-redirect ([`test_security.py`](apps/rma/tests/test_security.py)), and `seed_rma` idempotency + `expire_warranties` dry-run safety ([`test_seeder.py`](apps/rma/tests/test_seeder.py)).
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
| `/eam/` | EAM dashboard — KPI cards (active assets, critical assets, down assets, open MWOs, overdue PM, open predictions), recent MWOs, upcoming PM, open predictions |
| `/eam/assets/` | Asset list with status / criticality / category / active filters; create, edit, delete, retire, reactivate |
| `/eam/assets/<pk>/` | Asset detail with tabs for Spare Parts, Meter Readings, Documents, Open Work Orders, Sub-assets |
| `/eam/categories/` | Asset category list with self-FK parent; create, edit, delete |
| `/eam/meter-readings/` | Append-only meter reading ledger filterable by asset / meter type |
| `/eam/pm-plans/` and `<pk>/` | PM plan list + detail with tasks inline + Generate Upcoming button |
| `/eam/pm-schedules/` and `<pk>/` | PM schedule list + detail with task-completion checklist + Start / Complete / Skip workflow |
| `/eam/monitoring-points/` and `<pk>/` | Condition monitoring point list + detail with recent readings + record-reading form |
| `/eam/readings/` | Condition reading list filterable by point / status |
| `/eam/predictions/` and `<pk>/` | Failure prediction list + detail with Investigate / Resolve workflow (resolution notes required per L-14) |
| `/eam/mwo/` and `<pk>/` | Maintenance work order list + detail with Labor / Material / Downtime tabs and Schedule / Start / Hold / Resume / Complete / Cancel workflow |
| `/eam/downtime/` | Downtime event list filterable by asset / type |
| `/eam/tools/` and `<pk>/` | Tool list + detail with Usage Logs / Maintenance / Cavities tabs (cavities for mold-type tools only) |
| `/eam/tool-maintenance/` | Tool maintenance record list filterable by tool / record type |
| `/labor/` | Labor & Workforce dashboard — KPI cards (active employees, on-leave today, certs expiring/expired, pending leaves, open runs), ApexCharts attendance % trend (30d) + cost-center donut |
| `/labor/employees/` and `<pk>/` | Employee master list (auto `EMP-00001`) + detail with tabs for Skills / Certifications / Documents / Attendance / Leaves / Training / Bookings; terminate / reactivate workflow |
| `/labor/departments/`, `/labor/positions/` | Department + Position CRUD with self-FK parent (departments) and per-department levels (positions) |
| `/labor/skills/`, `/labor/skills-matrix/` | Skill catalog + employees × skills color-coded proficiency grid (L1 lightest → L5 darkest) |
| `/labor/certifications/` | Certification catalog with auto-computed `active / expiring_soon / expired` status from `expires_at` |
| `/labor/shifts/`, `/labor/shift-rosters/` | Shift templates + per-employee shift roster with date-range overlap protection |
| `/labor/attendance/` | Per-employee per-day attendance ledger; auto-upsert from `mes.OperatorTimeLog` clock-in/out events when employee soft-link is set |
| `/labor/leave-types/`, `/labor/leave-requests/` and `<pk>/` | Leave type catalog + leave request CRUD (auto `LR-00001`) with submit / approve / reject / cancel workflow (Lesson L-14: reject / cancel-of-approved require non-empty notes) |
| `/labor/holidays/` | Tenant calendar of paid holidays |
| `/labor/cost-centers/`, `/labor/labor-rates/` | Cost center master + per-employee hourly rates with effective-from/to ranges |
| `/labor/labor-bookings/` and `<pk>/`, `/summary/` | Append-only `LaborBooking` ledger (auto `LB-00001`) — auto-emitted from `mes.OperatorTimeLog stop_job` (direct) + `eam.MWOLaborLog` (indirect); summary view aggregates by cost-center within a date window |
| `/labor/training-programs/`, `/labor/training-plans/` | Program catalog + per-employee plan assignment with assigned / in_progress / completed / waived / overdue workflow; waive requires non-empty notes (L-14) |
| `/labor/training-sessions/` and `<pk>/` | Session list (auto `TS-00001`) + detail with inline attendee CRUD and per-attendee score |
| `/labor/competency-assessments/` and `<pk>/` | Per-employee competency assessment (auto `CA-00001`) with inline skill-result CRUD + Complete action (gap = expected − actual; overall_score = avg(min(actual, expected) / expected) × 100) |
| `/labor/incentive-schemes/` and `<pk>/` | Scheme catalog + detail with inline piece-rate CRUD; M2M to applicable employees / products / positions |
| `/labor/incentive-periods/` | Calculation-window catalog with `open → locked → paid` workflow |
| `/labor/incentive-runs/` and `<pk>/` | Per-period batch calculation (auto `INC-00001`) with Run / Discard workflow; Run scans `mes.ProductionReport` rows in the period, applies the matching `PieceRate`, and materializes idempotent `IncentiveLine` rows (M2M back to source reports for traceability) |
| `/cost/` | Cost & Accounting dashboard — KPI cards (active version, open jobs, closed jobs MTD, open periods, total WIP balance), ApexCharts COGM stacked trend + variance bar, recent allocations / variances / COGM tables |
| `/cost/standard-versions/` and `<pk>/` | Standard cost version list + detail with per-product `StandardCost` rows and Approve / Activate / Archive / Recompute / Add Cost buttons; auto-archives prior active on activation |
| `/cost/standard-versions/<pk>/approve/` · `/activate/` · `/archive/` · `/recompute/` | POST — version workflow + recompute_from_bom service action |
| `/cost/standard-versions/compare/` | Side-by-side diff of two versions (`?v1=&v2=`) sorted by absolute delta descending |
| `/cost/standard-costs/` | Flat StandardCost list with version + product filters |
| `/cost/standard-costs/<pk>/edit/` · `/delete/` | StandardCost row edit / delete (gated to draft version) |
| `/cost/actual-costs/` and `<pk>/` | ActualCost list + detail with live 6-axis variance vs. active standard |
| `/cost/actual-costs/<po_pk>/recompute/` | POST — re-aggregate actuals from `JobCost` denorms |
| `/cost/variances/` and `<pk>/` | CostVariance list + detail (auto `VAR-00001`) with Recompute action |
| `/cost/jobs/` and `<pk>/` | JobCost list + detail with WIP ledger tab + operation-wise rollup tab and Close action (refuses non-zero balance unless `force`) |
| `/cost/jobs/<pk>/close/` | POST — `wip_svc.close_job` invariant guard |
| `/cost/wip-entries/` and `<pk>/` | Append-only WIP ledger list + detail (filter by entry type / job) |
| `/cost/cost-drivers/` and CRUD | Activity driver catalog (machine_hours / direct_labor_hours / units / sq_ft / kwh) |
| `/cost/overhead-pools/` and CRUD | Indirect cost pools with allocation method (abc / volume / direct_labor_hours / direct_labor_cost / machine_hours) |
| `/cost/overhead-rates/` and CRUD | Period-scoped budgeted rate per pool (computed `rate_per_driver_unit = budget / qty`) |
| `/cost/driver-actuals/` and CRUD | Driver consumption per period (XOR cost-center / production-order target) |
| `/cost/overhead-allocations/` and `<pk>/` | Materialized allocations + Apply Overhead form |
| `/cost/overhead-allocations/apply/` | POST — `apply_overhead(period)` (idempotent: clears prior + emits matching WIP entries for PO targets) |
| `/cost/overhead-allocations/<pk>/reverse/` | POST — single-allocation reversal with required reason |
| `/cost/periods/` and `<pk>/` | AccountingPeriod list + detail showing COGM / margin / P&L tiles |
| `/cost/periods/<pk>/lock/` · `/close/` | POST — `open → locked → closed` workflow (close auto-generates COGM / margin / P&L reports) |
| `/cost/cogm/` and `<pk>/` | COGMReport list + detail with horizontal bar chart of buckets and Print / PDF action |
| `/cost/cogm/<period_pk>/generate/` | POST — `generate_cogm(period)` |
| `/cost/gross-margin/` and `<pk>/` | Per-product per-period gross-margin rows |
| `/cost/gross-margin/<period_pk>/generate/` | POST — `generate_gross_margin(period)` (scans `mes.ProductionReport.good_qty` × `ActualCost`) |
| `/cost/plant-pnl/` and `<pk>/` | PlantPnLReport list + detail with Income Statement table + waterfall-style chart |
| `/cost/plant-pnl/generate/` | POST — generate P&L with manual SG&A inputs |
| `/utility/` | Energy & Utility dashboard — KPI cards (active meters, current-period kWh / water / CO2e, open DR events, peak suggestions), recent consumption + allocations + emissions tables |
| `/utility/types/` and CRUD | UtilityType catalog (electricity / water / natural_gas / steam / compressed_air / fuel_oil) with optional `cost.CostDriver` bridge |
| `/utility/meters/` and `<pk>/` | UtilityMeter list + detail (auto `MTR-00001`) with parent / sub-meter tree, location FK, calibration date, multiplier, optional `eam.Asset` + `labor.CostCenter` links |
| `/utility/meters/new/` · `/<pk>/edit/` · `/<pk>/delete/` | UtilityMeter CRUD |
| `/utility/consumption/` and `<pk>/` | UtilityConsumption append-only ledger (auto `UC-00001`) with `consumption = (end − start) × multiplier` + total cost computed in `save()` |
| `/utility/consumption/new/` · `/<pk>/edit/` · `/<pk>/delete/` | Manual entry CRUD (auto-feed signal handles EAM-sourced rows) |
| `/utility/consumption/import/` | CSV bulk billing import view ([`services/meters.bulk_import_billing`](apps/utility/services/meters.py)) |
| `/utility/tariffs/` and `<pk>/` | UtilityTariff list + detail (auto `TRF-00001`) with effective-from/to + flat-rate fall-back + inline TOU bands |
| `/utility/tariffs/new/` · `/<pk>/edit/` · `/<pk>/delete/` | UtilityTariff CRUD |
| `/utility/tariffs/<tariff_pk>/bands/new/` · `/tariffs/bands/<pk>/delete/` | TOURateBand inline create / delete on a tariff (peak / shoulder / off_peak × weekday / weekend / per-day windows) |
| `/utility/allocations/` and `<pk>/` | UtilityAllocation list + detail (auto `UAL-00001`) showing share %, allocated consumption / cost, posted-to-cost flag |
| `/utility/allocations/post/` | POST — `services/allocation.post_allocation` (writes matching `cost.DriverActuals` for the Utilities pool) |
| `/utility/allocations/<pk>/reverse/` · `/<pk>/delete/` | POST — reversal with required reason / delete |
| `/utility/dr-events/` and `<pk>/` | DemandResponseEvent list + detail (auto `DRE-00001`) with target reduction %, incentive amount, source (utility_provider / manual) |
| `/utility/dr-events/new/` · `/<pk>/edit/` | Create / edit (gated to `scheduled`) |
| `/utility/dr-events/<pk>/activate/` · `/complete/` · `/cancel/` · `/delete/` | POST — `scheduled → active → completed | cancelled` workflow |
| `/utility/peak-suggestions/` and `<pk>/` | PeakShavingSuggestion list + detail (auto `PSS-00001`) showing original vs. suggested op slot + estimated savings |
| `/utility/peak-suggestions/scan/` | POST — [`services/peak.scan_for_peak_overlap(tenant)`](apps/utility/services/peak.py) sweeps `pps.ScheduledOperation` rows against active TOU peak bands + scheduled DR events |
| `/utility/peak-suggestions/<pk>/ack/` · `/<pk>/dismiss/` | POST — `new → acknowledged → dismissed` (never mutates PPS schedule) |
| `/utility/emission-factors/` and CRUD | EmissionFactor catalog (Scope 1 / 2 / 3 × electricity_grid / natural_gas / fuel_oil / water / refrigerant / commute / travel / waste / supply_chain) with effective-from + IPCC / GHG-Protocol / DEFRA / EPA citation |
| `/utility/emissions/` and `<pk>/` | CarbonEmission append-only ledger (auto `CE-00001`) — auto-emitted by `UtilityConsumption.post_save` signal |
| `/utility/emissions/period/<int:period_pk>/recompute/` | POST — [`services/carbon.recompute_emissions(period)`](apps/utility/services/carbon.py) refreshes the ledger for an open period |
| `/utility/sustainability/` and `<pk>/` | SustainabilityKPI per-period snapshot (Scope 1 / 2 / 3 totals, kWh, water m³, gas m³, units produced, kWh/unit, kgCO2e/unit) |
| `/utility/sustainability/period/<int:period_pk>/generate/` | POST — [`services/carbon.generate_sustainability_kpi(period)`](apps/utility/services/carbon.py) |
| `/utility/benchmarks/` and `<pk>/` | BenchmarkSnapshot list + detail (per-unit kWh / water / CO2e / cost) including tenant-`NULL` industry-average rows |
| `/utility/benchmarks/generate/` | POST — [`services/benchmark.generate_snapshot(period)`](apps/utility/services/benchmark.py) |
| `/utility/benchmark-reports/` and `<pk>/` | BenchmarkComparison list + detail (auto `BCR-00001`) with kWh / water / CO2e / cost delta % and winner label |
| `/utility/benchmark-reports/new/` · `/<pk>/delete/` | Plant-to-plant / period-over-period / tenant-vs-industry-average comparison creation + delete |
| `/compliance/` | Compliance & Regulatory dashboard — KPI cards (open incidents, open risks, effective documents, active recalls) + EHS Leading & Lagging panel (TRIR / LTIR / Near-Miss Ratio / Hours Worked, last 90 days) + recent incidents / recalls tables |
| `/compliance/incidents/` and CRUD + `/<pk>/investigate/` · `/action/` · `/close/` · `/cancel/` | IncidentReport (auto `INC-NNNNN`) with workflow `reported → investigating → corrective_action → closed | cancelled` |
| `/compliance/incident-types/` and CRUD | IncidentType catalog per tenant (admin-only management) |
| `/compliance/risks/` and CRUD + `/<pk>/submit/` · `/approve/` · `/archive/` | RiskAssessment (auto `RA-NNNNN`) with computed `risk_score` + `risk_band` (low / medium / high / critical) + residual scoring + workflow `draft → in_review → approved → archived` |
| `/compliance/checklists/` and CRUD | SafetyAuditChecklist with JSON `items` schema for ordered audit questions |
| `/compliance/audits/` and CRUD + `/<pk>/start/` · `/record/` · `/complete/` · `/cancel/` | SafetyAudit (one per checklist instance) with per-item `SafetyAuditItem` recording (pass / fail / na / observation) |
| `/compliance/documents/` and CRUD + `/<pk>/submit/` · `/approve/` · `/reject/` · `/publish/` · `/sign/` · `/supersede/` | ComplianceDocument (auto `DOC-NNNNN`, type = sop / wi / form / policy / iso_procedure / regulatory) with `draft → in_review → approved → effective → superseded` workflow + ElectronicSignature recording (FDA 21 CFR Part 11) |
| `/compliance/audit-trail/` | Aggregated cross-cutting view of `tenants.TenantAuditLog` + `plm.ComplianceAuditLog` with filter by target_type |
| `/compliance/audit-trail/archives/` and `<pk>/` + `/generate/` | AuditLogArchive (auto `ALA-NNNNN`) — periodic SHA-256 sealed snapshot of audit rows with `previous_archive` chain |
| `/compliance/waste-categories/` and CRUD | WasteCategory with `hazard_class` enum (general / hazardous_chemical / biohazard / e_waste / radioactive) |
| `/compliance/waste-manifests/` and CRUD + `/<pk>/dispatch/` · `/dispose/` · `/reconcile/` · `/cancel/` | WasteManifest (auto `WM-NNNNN`) with `draft → in_transit → disposed → reconciled` workflow + per-line `WasteDisposalRecord` (qty + facility) |
| `/compliance/recalls/` and CRUD + `/<pk>/progress/` · `/complete/` · `/close/` · `/cancel/` | ProductRecall (auto `REC-NNNNN`, severity = class_i / class_ii / class_iii) with `draft → in_progress → completed → closed | cancelled` workflow + computed `recovery_pct` + leak warnings (C.7 outbound `inventory.StockMovement` detection on recalled lots) |
| `/compliance/recalls/<pk>/lots/add/` · `/recalls/lots/<pk>/remove/` | RecallAffectedLot link CRUD with `recompute_affected_quantity` service |
| `/compliance/recalls/<pk>/notices/new/` · `/recalls/notices/<pk>/` · `/send/` · `/ack/` | RecallNotice (auto `RCN-NNNNN`) with channel = email / phone / letter / press_release / website / regulatory — channel=email actually delivers via Django `send_mail` (C.5) |
| `/iot/` | IoT & SCADA dashboard — KPI cards (active devices, brokers, 24h reading count, open anomalies, active twins, today's OEE), ApexCharts OEE trend (14d) + anomaly severity stack (30d), recent readings + open anomalies tables |
| `/iot/protocols/` and CRUD | Shared protocol catalog (MQTT / OPC-UA / Modbus TCP+RTU / HTTP / CoAP) |
| `/iot/brokers/` and CRUD + `/<pk>/heartbeat/` | DeviceBroker (auto `BRK-00001`) with TLS / auth-method config and ping-style heartbeat |
| `/iot/devices/` and CRUD + `/<pk>/retire/` + `/<pk>/reactivate/` | Device master (auto `DEV-00001`) with optional `eam.Asset` link |
| `/iot/devices/<pk>/` | Device detail with Tags, Recent Readings tabs |
| `/iot/tags/` and CRUD | DeviceTag — per-device data points (topic / NodeId / Modbus register), optional `eam.ConditionMonitoringPoint` link drives the IoT→EAM cascade |
| `/iot/readings/` and CRUD | Append-only `IoTReading` ledger (auto `IR-00001`) |
| `/iot/readings/ingest/` | POST — JSON/CSV bulk ingest endpoint via `services/ingestion.bulk_ingest` |
| `/iot/batches/` and detail | IoTReadingBatch list + detail with rows + error summary |
| `/iot/edge-processors/` and CRUD | Pure-function transforms (rolling_avg / sum / min / max / threshold_count / state_machine / derivative) |
| `/iot/stream-metrics/` | Read-only latest-value denorm + 24h aggregates per tag |
| `/iot/twins/` and CRUD + `/<pk>/activate/` + `/archive/` + `/snapshot/` + `/recompute/` | DigitalTwin (auto `DT-00001`) with state attributes inline + Activate / Archive / Snapshot / Recompute |
| `/iot/twins/<twin_pk>/attributes/new/` and edit/delete | TwinStateAttribute inline CRUD with safe-formula evaluator (no `eval()`) |
| `/iot/twins/<twin_pk>/scenarios/new/` and detail/run/delete | TwinSimulationScenario (auto `TSC-00001`) — pure-function simulator never mutates twin state |
| `/iot/oee/` | OEE dashboard with 14d period table + 30d loss-reason Pareto |
| `/iot/oee/periods/` and CRUD + `/<pk>/recompute/` | OEEPeriod (auto `OEEP-00001`) with A/P/Q/OEE % computed in `save()` from MachineStateLog + `mes.ProductionReport` + ideal cycle |
| `/iot/oee/state-logs/` and CRUD | Append-only MachineStateLog ledger (running / idle / down / starved / blocked / setup / changeover) |
| `/iot/oee/loss-reasons/` and CRUD | LossReason catalog (availability / performance / quality) |
| `/iot/alerts/rules/` and CRUD + `/<pk>/activate/` + `/deactivate/` | AlertRule (auto `AR-00001`) with XOR-validated scope (tag / device / asset) and condition_type ∈ threshold_high / threshold_low / range_outside / rate_of_change / missing_data / zscore / iqr / runs_rule |
| `/iot/alerts/detections/` and detail + `/<pk>/acknowledge/` + `/resolve/` + `/false-positive/` | Append-only AnomalyDetection ledger (auto `AD-00001`) with workflow new → acknowledged → resolved \| false_positive (resolution_notes required per L-14) |
| `/iot/alerts/notifications/` | Append-only fanout log of notifications per detection per channel (in_app / email / mes_andon) |
| `/bi/` | Business Intelligence dashboard — KPI cards (definitions, dashboards, reports, active schedules, recent runs, marts) + ApexCharts area chart of 30-day OEE trend, recent KPI snapshots, recent report runs, recent prediction runs |
| `/bi/kpi/definitions/` and CRUD | KPI definitions list with search / active filter + refresh-snapshot action |
| `/bi/kpi/definitions/<pk>/refresh/` | POST — recompute KPI snapshot for the last 30 days at tenant scope |
| `/bi/kpi/snapshots/` | Materialized snapshot ledger filterable by KPI code / scope / status (on_target / warning / critical) |
| `/bi/dashboards/` and CRUD | Dashboard list + detail with widget tiles (KPI value + prior-period delta + status badge), refresh-all action |
| `/bi/dashboards/<dashboard_pk>/widgets/new/` and edit/delete | Widget inline CRUD on a dashboard |
| `/bi/reports/data-sources/` and CRUD | Tenant catalog of registered report data sources (whitelisted in [`services/registry.py`](apps/bi/services/registry.py)) |
| `/bi/reports/` and CRUD | Ad-hoc report definitions list with data-source filter; create new report from any registered source |
| `/bi/reports/<pk>/` | Report detail with inline Fields + Filters CRUD, Run-now + Run+CSV download actions, recent runs table |
| `/bi/reports/<pk>/run/` | POST — execute the report (validates every field against the static whitelist), persists `ReportRun` + result preview |
| `/bi/reports/runs/` and `<pk>/` | Run list / detail with row count, duration, status, JSON preview of first 50 rows |
| `/bi/predictive/models/` and CRUD | Predictive-model catalog (demand_forecast / failure_likelihood / quality_trend / scrap_drift / cost_drift / energy_drift) with run-now action |
| `/bi/predictive/models/<pk>/run/` | POST — execute the heuristic predictor (pure-Python linear regression / rolling failure rate / SPC slope); writes `PredictionRun` + `PredictionResult` rows |
| `/bi/predictive/runs/` and `<pk>/` | Run list / detail with cancel action (L-14: reason required) |
| `/bi/predictive/trends/` | Trend analysis ledger filterable by source / direction |
| `/bi/marts/` and CRUD | Data mart list / detail with admin `source_definition` JSON, refresh-now action, snapshot history + latest-rows preview |
| `/bi/marts/<pk>/refresh/` | POST — refreshes the mart (atomic: deletes prior rows, creates new `DataMartSnapshot`, bulk-creates `DataMartRow` set) |
| `/bi/schedules/` and CRUD | Report schedule list filterable by status / frequency; XOR Report or Dashboard binding |
| `/bi/schedules/<pk>/run/` · `/pause/` · `/resume/` · `/disable/` | POST — schedule lifecycle (disable requires reason per L-14) |
| `/bi/schedules/<schedule_pk>/recipients/new/` and delete | Recipient inline CRUD on a schedule |
| `/bi/deliveries/` and `<pk>/` | Delivery ledger (one per recipient per execution) with status + error_message |
| `/bi/exports/` and `<pk>/download/` | Rendered export list + auth-gated CSV / xlsx / PDF download |

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
│   │   ├── models.py             # Tenant (incl. require_compliance_e_signature flag),
│   │   │                         # TenantAwareModel, TimeStampedModel, thread-local
│   │   ├── services/
│   │   │   └── audit_chain.py    # SHA-256 hash-chain helper used by tenants + plm audit logs
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
│   │   │                         # EmailTemplate, TenantAuditLog (SHA-256 chained),
│   │   │                         # TenantHealthSnapshot, HealthAlert
│   │   ├── services/
│   │   │   ├── gateway.py        # PaymentGateway Protocol + MockGateway
│   │   │   ├── billing.py        # start_trial, issue_invoice, mark_paid
│   │   │   ├── health.py         # capture_snapshot
│   │   │   └── audit_chain.py    # verify_tenant_audit_chain — FDA 21 CFR Part 11 verifier
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
│   │   │                         # ComplianceAuditLog (immutable + SHA-256 chained),
│   │   │                         # ProductComplianceSignature (FDA 21 CFR Part 11),
│   │   │                         # NPIProject, NPIStage, NPIDeliverable
│   │   ├── services/
│   │   │   └── audit_chain.py    # verify_compliance_audit_chain — chain integrity verifier
│   │   ├── signals.py            # Audit-log receivers on ECO + ProductCompliance status changes
│   │   ├── forms.py              # ModelForms with file-extension allowlists + 25 MB cap
│   │   ├── views.py              # Full CRUD for all 5 sub-modules + workflow actions
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       ├── seed_plm.py            # Idempotent demo data per tenant
│   │       └── expire_compliance.py   # Daily job: flips compliant→expired past expiry_date
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
│   ├── eam/                      # MODULE 10 — Equipment & Asset Management
│   │   ├── models.py             # AssetCategory, Asset, AssetSparePart,
│   │   │                         # AssetMeterReading, AssetDocument,
│   │   │                         # MaintenancePlan, MaintenanceTask, PMSchedule,
│   │   │                         # PMTaskCompletion, ConditionMonitoringPoint,
│   │   │                         # ConditionReading, FailurePrediction,
│   │   │                         # MaintenanceWorkOrder, MWOLaborLog,
│   │   │                         # MWOMaterialLog, DowntimeEvent, Tool,
│   │   │                         # ToolUsageLog, ToolMaintenanceRecord,
│   │   │                         # MoldCavityHistory
│   │   ├── services/
│   │   │   ├── pm_scheduler.py   # generate_upcoming_pm() — pure
│   │   │   ├── prediction.py     # classify_reading() — heuristic alarm-band
│   │   │   ├── downtime.py       # compute_downtime() + refresh_mwo_downtime()
│   │   │   └── tool_life.py      # bump_tool_life() + consume_usage_log()
│   │   ├── signals.py            # Audit pre/post_save factory (L-18 weak=False)
│   │   │                         # for Asset / PMSchedule / FailurePrediction /
│   │   │                         # MWO / Tool; ConditionReading post_save spawns
│   │   │                         # FailurePrediction on critical; DowntimeEvent
│   │   │                         # post_save refreshes MWO.downtime_minutes;
│   │   │                         # cross-module hook mes.AndonAlert post_save ->
│   │   │                         # auto-create breakdown MWO; cross-module hook
│   │   │                         # mes.ProductionReport post_save -> auto
│   │   │                         # ToolUsageLog + Tool denorm bump
│   │   ├── forms.py              # ModelForms with L-01 unique_together (asset
│   │   │                         # category, asset, plan name, monitoring
│   │   │                         # point, mold cavity), L-02 decimal validators,
│   │   │                         # L-14 per-workflow forms (PM completion needs
│   │   │                         # task results, prediction resolve needs
│   │   │                         # notes, MWO complete needs resolution notes)
│   │   ├── views.py              # Full CRUD + workflow + RBAC mixins
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       ├── seed_eam.py            # Idempotent demo data per tenant
│   │       └── generate_pm_schedules.py # Idempotent next-due PM generator
│   │
│   ├── labor/                    # MODULE 11 — Labor & Workforce Management
│   │   ├── models.py             # Department, Position, Employee, Skill,
│   │   │                         # EmployeeSkill, Certification,
│   │   │                         # EmployeeCertification, EmployeeDocument,
│   │   │                         # Shift, ShiftRoster, AttendanceRecord,
│   │   │                         # LeaveType, LeaveRequest, Holiday,
│   │   │                         # CostCenter, LaborRate, LaborBooking,
│   │   │                         # TrainingProgram, TrainingPlan,
│   │   │                         # TrainingSession, TrainingAttendance,
│   │   │                         # CompetencyAssessment, CompetencyResult,
│   │   │                         # IncentiveScheme, PieceRate,
│   │   │                         # IncentivePeriod, IncentiveRun,
│   │   │                         # IncentiveLine
│   │   ├── services/
│   │   │   ├── attendance.py     # compute_worked_minutes, derive_status
│   │   │   ├── scheduling.py     # date_range, split_overlapping (roster)
│   │   │   ├── cost_allocation.py # compute_total_cost, lookup_effective_rate,
│   │   │   │                       # summarize_by_cost_center
│   │   │   ├── competency.py     # compute_overall_score, gap_summary,
│   │   │   │                       # cert_status_for
│   │   │   └── piece_rate.py     # compute_amount, select_rate,
│   │   │                           # aggregate_employee_units
│   │   ├── signals.py            # Audit factory (L-18 weak=False) for
│   │   │                         # Employee / LeaveRequest / IncentiveRun /
│   │   │                         # IncentivePeriod / CompetencyAssessment /
│   │   │                         # TrainingPlan / EmployeeCertification;
│   │   │                         # cross-module hooks:
│   │   │                         #   mes.OperatorTimeLog clock_in/out ->
│   │   │                         #     AttendanceRecord upsert,
│   │   │                         #   mes.OperatorTimeLog stop_job ->
│   │   │                         #     direct LaborBooking,
│   │   │                         #   eam.MWOLaborLog ->
│   │   │                         #     indirect LaborBooking,
│   │   │                         #   mes.ProductionReport ->
│   │   │                         #     IncentiveLine accumulation
│   │   ├── forms.py              # ModelForms with L-01 unique_together,
│   │   │                         # L-02 decimal validators, L-14 per-workflow
│   │   │                         # required (LeaveDecisionForm reject/cancel,
│   │   │                         # TrainingPlanWaiveForm,
│   │   │                         # CompetencyAssessmentCompleteForm)
│   │   ├── views.py              # Full CRUD + workflow + RBAC mixins +
│   │   │                         # cost-center summary report + IncentiveRun
│   │   │                         # batch calculation engine
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_labor.py     # Idempotent demo data per tenant
│   │                             # (4 departments + Assembly sub-dept,
│   │                             # 8 positions, 12 skills, 5 certifications,
│   │                             # 20 employees with first 6 linked to
│   │                             # mes.ShopFloorOperator, 3 shifts, 14-day
│   │                             # roster + attendance, 5 leave types,
│   │                             # 6 leave requests across statuses,
│   │                             # 4 holidays, 5 cost centers, 20 labor rates,
│   │                             # 30 labor bookings, 4 training programs,
│   │                             # 8 training plans, 2 sessions, 1 assessment
│   │                             # with 5 results, 2 schemes, 1 open period,
│   │                             # 1 completed run with 6 incentive lines)
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
│   ├── cost/                     # MODULE 12 — Cost Management & Accounting
│   │   ├── models.py             # StandardCostVersion, StandardCost,
│   │   │                         # StandardCostHistory, CostDriver,
│   │   │                         # OverheadPool, AccountingPeriod,
│   │   │                         # OverheadRate, OverheadActualPool,
│   │   │                         # DriverActuals, OverheadAllocation,
│   │   │                         # JobCost, WIPEntry, ActualCost,
│   │   │                         # CostVariance, COGMReport,
│   │   │                         # GrossMarginReport, PlantPnLReport
│   │   ├── services/
│   │   │   ├── standard_costing.py # recompute_from_bom, compare_versions
│   │   │   ├── actual_costing.py   # compute_actual, compute_variances
│   │   │   ├── wip.py              # post_wip_entry, reverse_wip_entry,
│   │   │   │                       # close_job, compute_operation_rollup
│   │   │   ├── overhead.py         # apply_overhead, reverse_overhead,
│   │   │   │                       # accumulate_indirect_labor, compute_rate
│   │   │   └── reporting.py        # generate_cogm, generate_gross_margin,
│   │   │                           # generate_plant_pnl
│   │   ├── signals.py            # Audit factory (L-18 weak=False) for
│   │   │                         # StandardCostVersion / AccountingPeriod /
│   │   │                         # JobCost; cross-module hooks:
│   │   │                         #   labor.LaborBooking(direct).post_save ->
│   │   │                         #     WIPEntry(labor_applied),
│   │   │                         #   labor.LaborBooking(indirect).post_save ->
│   │   │                         #     OverheadActualPool accum,
│   │   │                         #   mes.ProductionReport(good_qty>0).post_save ->
│   │   │                         #     WIPEntry(completion) at standard cost
│   │   │                         #   plus pre_delete reversal counterparts;
│   │   │                         #   internal WIPEntry.pre_delete keeps
│   │   │                         #   JobCost denorms consistent
│   │   ├── forms.py              # ModelForms with L-01 unique_together,
│   │   │                         # L-02 decimal validators (-1e10 floor for
│   │   │                         # signed amounts, 0 for non-negative),
│   │   │                         # L-14 per-workflow forms (approve / lock /
│   │   │                         # reverse / close)
│   │   ├── views.py              # Full CRUD + workflow + RBAC mixins +
│   │   │                         # dashboard with ApexCharts
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_cost.py      # Idempotent demo data per tenant
│   │                             # (3 periods, 5 drivers, 5 pools, 5 rates,
│   │                             # 1 active std cost version with rows for
│   │                             # all finished/sub-assembly products,
│   │                             # JobCost per released/in-progress/completed
│   │                             # PO with seeded WIP entries, applied
│   │                             # overhead for the prior closed period,
│   │                             # 1 COGM + per-product margin rows + P&L)
│   │
│   ├── compliance/               # MODULE 13 — Compliance & Regulatory Management
│   │   ├── models.py             # IncidentType, IncidentReport (incl. source_ncr FK),
│   │   │                         # RiskAssessment, SafetyAuditChecklist, SafetyAudit,
│   │   │                         # SafetyAuditItem, ComplianceDocument, DocumentApproval,
│   │   │                         # ElectronicSignature (immutable, FDA 21 CFR Part 11),
│   │   │                         # AuditLogArchive (SHA-256 chained snapshots),
│   │   │                         # WasteCategory, WasteManifest, WasteDisposalRecord,
│   │   │                         # ProductRecall (incl. recovery_pct), RecallAffectedLot
│   │   │                         # (incl. post_recall_movement_count + last_leak_at),
│   │   │                         # RecallNotice (incl. recipient_email)
│   │   ├── services/
│   │   │   ├── audit.py          # generate_archive (SHA-256 sealed)
│   │   │   ├── document.py       # workflow + e-sig writer
│   │   │   ├── incident.py       # workflow transitions
│   │   │   ├── recall.py         # add/remove lots, lifecycle, send_notice (Django send_mail)
│   │   │   │                     # + sweep_lot_for_leaks (C.7 leak detection)
│   │   │   └── kpi.py            # compute_ehs_kpis — TRIR / LTIR / near-miss ratio (C.4)
│   │   ├── signals.py            # Status-audit factory + mes.AndonAlert(safety) hook
│   │   │                         # + qms.NCR(critical) hook (C.6)
│   │   │                         # + inventory.StockMovement(out) → recall leak hook (C.7)
│   │   ├── forms.py              # ModelForms with workflow-required reasons (L-14)
│   │   │                         # + RecallNoticeForm requires recipient_email when channel=email
│   │   ├── views.py              # 81 CBVs across all 5 sub-modules + dashboard with EHS KPIs
│   │   ├── urls.py               # 60+ patterns
│   │   ├── admin.py              # incl. ElectronicSignatureAdmin readonly (FDA 21 CFR Part 11)
│   │   └── management/commands/
│   │       └── seed_compliance.py
│   │
│   ├── utility/                  # MODULE 14 — Energy & Utility Management
│   │   ├── models.py             # UtilityType, UtilityMeter, UtilityConsumption,
│   │   │                         # UtilityTariff, UtilityAllocation, TOURateBand,
│   │   │                         # DemandResponseEvent, PeakShavingSuggestion,
│   │   │                         # EmissionFactor, CarbonEmission,
│   │   │                         # SustainabilityKPI, BenchmarkSnapshot,
│   │   │                         # BenchmarkComparison
│   │   ├── services/
│   │   │   ├── meters.py         # post_consumption, bulk_import_billing
│   │   │   ├── allocation.py     # compute_allocation, post_allocation
│   │   │   │                     # (writes cost.DriverActuals),
│   │   │   │                     # reverse_allocation
│   │   │   ├── peak.py           # scan_for_peak_overlap (sweeps
│   │   │   │                     # pps.ScheduledOperation × TOU bands + DR
│   │   │   │                     # events), compute_suggested_slot,
│   │   │   │                     # compute_estimated_savings,
│   │   │   │                     # acknowledge / dismiss
│   │   │   ├── carbon.py         # emit_for_consumption, recompute_emissions,
│   │   │   │                     # generate_sustainability_kpi
│   │   │   └── benchmark.py      # generate_snapshot, compare,
│   │   │                         # create_comparison
│   │   ├── signals.py            # Audit factory (L-18 weak=False) for
│   │   │                         # UtilityMeter / UtilityTariff /
│   │   │                         # UtilityAllocation / DemandResponseEvent /
│   │   │                         # PeakShavingSuggestion; cross-module hooks:
│   │   │                         #   eam.AssetMeterReading(meter_type='kwh')
│   │   │                         #     .post_save -> UtilityConsumption
│   │   │                         #     (idempotent on source_meter_reading);
│   │   │                         #   UtilityConsumption.post_save ->
│   │   │                         #     CarbonEmission (idempotent on
│   │   │                         #     source_consumption);
│   │   │                         #   pre_delete reversal counterparts
│   │   ├── forms.py              # ModelForms with L-01 unique_together,
│   │   │                         # L-02 decimal validators (NON_NEG / SIGNED /
│   │   │                         # PCT_MAX 0-100), L-14 per-workflow forms
│   │   │                         # (activate / cancel / reverse / dismiss /
│   │   │                         # post allocation), DriverActuals-style XOR
│   │   │                         # of cost_center / product / production_order
│   │   │                         # on UtilityAllocationForm
│   │   ├── views.py              # Full CRUD + workflow + RBAC mixins +
│   │   │                         # dashboard
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tests/                # conftest, test_models, test_forms
│   │   └── management/commands/
│   │       └── seed_utility.py   # Idempotent demo data per tenant
│   │                             # (6 utility types, 4 meters, 5 tariffs,
│   │                             # 4 TOU bands, 1 DRE, 5 emission factors,
│   │                             # ~120 consumption + auto-cascaded carbon
│   │                             # rows, 1 allocation per metered cost-center,
│   │                             # 2 sustainability KPIs, 2 benchmark
│   │                             # snapshots, 1 period-over-period comparison)
│   │
│   ├── iot/                      # MODULE 15 — IoT & SCADA Integration
│   │   ├── models.py             # DeviceProtocol [shared catalog],
│   │   │                         # DeviceBroker, Device, DeviceTag,
│   │   │                         # IoTReadingBatch, IoTReading,
│   │   │                         # EdgeProcessor, StreamMetric,
│   │   │                         # DigitalTwin, TwinStateAttribute,
│   │   │                         # TwinSimulationScenario,
│   │   │                         # TwinStateSnapshot, LossReason,
│   │   │                         # MachineStateLog, OEEPeriod,
│   │   │                         # AlertRule, AnomalyDetection,
│   │   │                         # AlertNotification (18 models)
│   │   ├── services/
│   │   │   ├── ingestion.py      # post_iot_reading, bulk_ingest
│   │   │   │                     # (atomic single + JSON/CSV batch)
│   │   │   ├── edge.py           # rolling_avg / sum / min / max /
│   │   │   │                     # threshold_count / derivative /
│   │   │   │                     # state_machine — pure functions
│   │   │   ├── twin.py           # compute_twin_state +
│   │   │   │                     # _safe_eval whitelist parser
│   │   │   │                     # (numbers, +-*/, parens, min/max/abs,
│   │   │   │                     # variable refs only - NEVER eval())
│   │   │   ├── twin_simulation.py # run_simulation — pure, never
│   │   │   │                      # mutates twin state
│   │   │   ├── oee.py            # compute_oee_period — pure
│   │   │   │                     # aggregation across MachineStateLog,
│   │   │   │                     # mes.ProductionReport,
│   │   │   │                     # pps.RoutingOperation cycle time
│   │   │   └── anomaly.py        # rolling_zscore / iqr_outlier /
│   │   │                         # runs_rule / threshold detectors
│   │   │                         # (pure, no ML deps)
│   │   ├── signals.py            # IoTReading.post_save -> StreamMetric
│   │   │                         # IoTReading.post_save -> AnomalyDetection
│   │   │                         # IoTReading.post_save -> eam.ConditionReading
│   │   │                         # AnomalyDetection.post_save ->
│   │   │                         #   AlertNotification fanout +
│   │   │                         #   mes.AndonAlert (severity>=high) +
│   │   │                         #   eam.FailurePrediction (severity=critical)
│   │   │                         # mes.ProductionReport.post_save ->
│   │   │                         #   OEEPeriod denorm refresh
│   │   │                         # eam.DowntimeEvent.post_save ->
│   │   │                         #   MachineStateLog (idempotent on
│   │   │                         #   source_downtime)
│   │   │                         # Audit factory (L-18 weak=False) for 8
│   │   │                         #   status-tracked models
│   │   ├── forms.py              # ModelForms with L-01 unique_together,
│   │   │                         # L-14 per-workflow forms (resolve /
│   │   │                         # false_positive require notes),
│   │   │                         # AlertRuleForm XOR scope validator
│   │   ├── views.py              # Full CRUD + workflow + RBAC mixins +
│   │   │                         # dashboard with ApexCharts
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_iot.py       # Idempotent demo data per tenant
│   │                             # (6 protocols + 2 brokers + 6 devices +
│   │                             # 24 tags + 5 loss reasons + 4 alert rules
│   │                             # + ~120 readings + 2 deliberate anomalies +
│   │                             # 3 twins with derived attrs + 1 scenario +
│   │                             # 7d × 3 assets of OEE periods + 5 edge
│   │                             # processors)
│   │
│   ├── sales/                    # MODULE 17 — Sales & Customer Order Management
│   │   ├── models.py             # CustomerCategory, PriceList, PriceListItem,
│   │   │                         # Customer, CustomerContact, CommunicationLog,
│   │   │                         # CustomerDocument, SalesOrder, SalesOrderLine,
│   │   │                         # SalesOrderRevision, SalesOrderApprovalLog,
│   │   │                         # ATPCalculation, CTPCalculation, OrderPromise,
│   │   │                         # DeliveryRoute, Shipment, ShipmentLine,
│   │   │                         # ProofOfDelivery, SalesInvoice, SalesInvoiceLine
│   │   ├── services/
│   │   │   ├── numbering.py      # next_code helper (atomic auto-numbering)
│   │   │   ├── pricing.py        # resolve_price walks customer PL -> tenant
│   │   │   │                     # default PL -> product list_price
│   │   │   ├── credit.py         # check_credit (blacklist, status, over-limit,
│   │   │   │                     # overdue invoices)
│   │   │   ├── workflow.py       # SalesOrder workflow: submit / confirm /
│   │   │   │                     # release_credit_hold / cancel / hold /
│   │   │   │                     # resume / revise (race-safe conditional UPDATE)
│   │   │   ├── atp.py            # Available-to-Promise (pure read; on-hand
│   │   │   │                     # + open PO arrivals - committed SO)
│   │   │   ├── ctp.py            # Capable-to-Promise walking released routing
│   │   │   │                     # + work-center capacity
│   │   │   ├── shipping.py       # pick / pack / dispatch / confirm_delivery /
│   │   │   │                     # cancel_shipment with conditional UPDATE
│   │   │   └── invoicing.py      # generate_invoice_from_shipment (idempotent
│   │   │                         # on shipment FK) + mark_invoice_paid
│   │   ├── signals.py            # MTO auto-PO on SO confirm (idempotent on
│   │   │                         # ProductionOrder.source_sales_line);
│   │   │                         # Shipment delivered -> StockMovement(shipment_out)
│   │   │                         # (idempotent on source_shipment_line);
│   │   │                         # Shipment pre_delete -> reverse movements;
│   │   │                         # SalesInvoice paid -> Customer.credit_used drop
│   │   ├── forms.py              # 14 ModelForms with tenant-scoped FK querysets
│   │   │                         # + L-22 file validators (25 MB cap / allowlist)
│   │   ├── views.py              # ~70 views across 5 sub-modules incl. portal
│   │   ├── urls.py               # ~55 URL patterns under sales namespace
│   │   ├── admin.py
│   │   ├── tests/                # conftest + test_models / test_forms /
│   │   │                         # test_views / test_security / test_seeder /
│   │   │                         # test_workflow_so / test_services_atp /
│   │   │                         # test_services_ctp / test_services_shipping /
│   │   │                         # test_services_invoicing / test_portal
│   │   └── management/commands/
│   │       ├── seed_sales.py             # Idempotent demo seeder per tenant
│   │       └── recompute_credit_used.py  # Repair credit_used denorm drift
│   │
│   ├── rma/                      # MODULE 18 — Returns & RMA Management
│   │   ├── models.py             # RMAReason, RMARequest (RMA-00001), RMALine,
│   │   │                         # RMAApproval, ReturnReceipt (RR-00001),
│   │   │                         # ReturnReceiptLine, RepairOrder (REP-00001),
│   │   │                         # RepairPartUsage, RepairLaborLog,
│   │   │                         # WarrantyPolicy (WP-00001),
│   │   │                         # WarrantyRegistration (WR-00001),
│   │   │                         # WarrantyClaim (WC-00001),
│   │   │                         # FailureMode, RootCauseCategory,
│   │   │                         # ReturnAnalysis (RA-00001),
│   │   │                         # SupplierChargeback (SCB-00001)
│   │   ├── services/
│   │   │   ├── numbering.py      # next_code atomic auto-numbering helper
│   │   │   ├── warranty.py       # add_months + compute_warranty_end +
│   │   │   │                     # is_under_warranty (no dateutil dep)
│   │   │   ├── disposition.py    # route_disposition classifier (restock /
│   │   │   │                     # repair_ticket / supplier_return / none)
│   │   │   ├── repair.py         # recompute_repair_costs aggregates parts +
│   │   │   │                     # labor onto RepairOrder.actual_cost
│   │   │   └── chargeback.py     # apply_transition with legal-path guards
│   │   ├── signals.py            # 6 cross-module hooks:
│   │   │                         #   RMA approved -> draft ReturnReceipt
│   │   │                         #   restock disposition -> inventory movement
│   │   │                         #   repair disposition -> draft RepairOrder
│   │   │                         #   RepairLaborLog -> labor.LaborBooking +
│   │   │                         #     cost rollup
│   │   │                         #   RepairPartUsage save/delete -> cost rollup
│   │   │                         #   WarrantyClaim approved+replace ->
│   │   │                         #     draft sales.SalesOrder
│   │   ├── forms.py              # 14 ModelForms with tenant-scoped FK querysets
│   │   │                         # + L-01 unique_together clean() on catalogs
│   │   ├── views.py              # ~60 views across 5 sub-modules with
│   │   │                         # @tenant_admin_required gating on workflow +
│   │   │                         # delete (L-10)
│   │   ├── urls.py               # ~55 URL patterns under rma namespace
│   │   ├── admin.py
│   │   ├── tests/                # conftest + test_models / test_forms /
│   │   │                         # test_services / test_signals /
│   │   │                         # test_views / test_security / test_seeder
│   │   └── management/commands/
│   │       ├── seed_rma.py               # Idempotent demo seeder per tenant
│   │       └── expire_warranties.py      # Daily job: active -> expired flip
│   │
│   ├── dms/                      # MODULE 19 — Document & Knowledge Management
│   │   ├── models.py             # DocumentCategory, Document (DOC-00001),
│   │   │                         # DocumentVersion (check-in/check-out),
│   │   │                         # DocumentAccessRule, DocumentTemplate
│   │   │                         # (TPL-00001), TemplateField,
│   │   │                         # MediaAttachment, ApprovalWorkflow,
│   │   │                         # ApprovalStage, DocumentApprovalRequest
│   │   │                         # (AR-00001), ApprovalAction,
│   │   │                         # DocumentSignature (immutable,
│   │   │                         # FDA 21 CFR Part 11),
│   │   │                         # DocumentAssignment (DA-00001),
│   │   │                         # AssignmentTarget (XOR fan-out),
│   │   │                         # ReadAcknowledgment (ACK-00001),
│   │   │                         # RetentionPolicy (RP-00001),
│   │   │                         # DocumentArchive (ARC-00001),
│   │   │                         # LegalHold (LH-00001) - 17 models
│   │   ├── services/
│   │   │   ├── numbering.py      # next_code atomic auto-numbering helper
│   │   │   ├── checkout.py       # check_in / check_out optimistic lock
│   │   │   │                     # (conditional UPDATE for race safety)
│   │   │   ├── approval.py       # current_stage / advance_stage helpers
│   │   │   ├── retention.py      # compute_retention_until +
│   │   │   │                     # is_due_for_archive (month-end clamped)
│   │   │   ├── legal_hold.py     # apply_hold / release_hold cascade
│   │   │   └── assignment.py     # expected/pending users for an assignment
│   │   ├── signals.py            # 6 hooks (L-18 weak=False):
│   │   │                         #   DocumentVersion released ->
│   │   │                         #     supersede prior + bump current_version
│   │   │                         #   DocumentApprovalRequest approved ->
│   │   │                         #     Document.status='effective'
│   │   │                         #   LegalHold.documents M2M change ->
│   │   │                         #     Document.is_locked cascade
│   │   │                         #   Document/RetentionPolicy save ->
│   │   │                         #     retention_until denorm refresh
│   │   │                         #   DocumentSignature pre_save ->
│   │   │                         #     reject any UPDATE (immutable)
│   │   │                         #   Document pre_delete ->
│   │   │                         #     refuse if is_locked
│   │   ├── forms.py              # 18 ModelForms / workflow forms with
│   │   │                         # tenant-scoped FK querysets + L-01
│   │   │                         # unique_together + XOR validators
│   │   │                         # (access rule / target) + L-22 file
│   │   │                         # cap + extension allowlist + L-14
│   │   │                         # per-workflow required (legal hold
│   │   │                         # release notes, archive restore notes,
│   │   │                         # approval reject/return notes)
│   │   ├── views.py              # ~55 views across all 5 sub-modules
│   │   ├── urls.py               # ~55 URL patterns under dms namespace
│   │   ├── admin.py              # DocumentSignatureAdmin readonly_fields
│   │   │                         # = '__all__' (FDA 21 CFR Part 11)
│   │   ├── tests/                # conftest + test_models /
│   │   │                         # test_forms / test_services /
│   │   │                         # test_signals / test_views /
│   │   │                         # test_security / test_seeder
│   │   │                         # (116 tests, ~2 min)
│   │   └── management/commands/
│   │       ├── seed_dms.py               # Idempotent demo seeder
│   │       ├── archive_due_documents.py  # Daily job: past-retention
│   │       │                             # effective -> archived
│   │       └── expire_assignments.py     # Daily job: overdue report
│   │
│   ├── wfa/                      # MODULE 20 — Workflow & Business Process Automation
│   │   ├── models.py             # ProcessCategory, ProcessDefinition (BPM-00001),
│   │   │                         # ProcessNode, ProcessTransition,
│   │   │                         # ProcessInstance (PI-00001),
│   │   │                         # ProcessVariable, ProcessActivity,
│   │   │                         # ApprovalPolicy, ApprovalLevel,
│   │   │                         # ApprovalRequest (APR-00001),
│   │   │                         # ApprovalDelegation, ApprovalActionLog,
│   │   │                         # EscalationRule,
│   │   │                         # NotificationChannel, NotificationTemplate,
│   │   │                         # NotificationRule (NR-00001),
│   │   │                         # Notification (NTF-00001),
│   │   │                         # NotificationDelivery, SMSDelivery,
│   │   │                         # Connector (CON-00001), ConnectorEndpoint,
│   │   │                         # IntegrationFlow, FlowStep,
│   │   │                         # IntegrationRun (IR-00001),
│   │   │                         # WebhookOutboxEntry,
│   │   │                         # ProcessMetric, BottleneckAnalysis (BA-00001),
│   │   │                         # ProcessOptimizationSuggestion (POS-00001),
│   │   │                         # CycleTimeReport (CTR-00001)  -- 22 models
│   │   ├── services/
│   │   │   ├── numbering.py      # next_code atomic auto-numbering helper
│   │   │   ├── bpmn_engine.py    # advance_instance + transition evaluator
│   │   │   │                     # with SECURITY-CRITICAL _safe_eval
│   │   │   │                     # whitelist parser (NEVER eval()/exec())
│   │   │   ├── approval.py       # submit / approve / reject / delegate /
│   │   │   │                     # escalate / recall with race-safe
│   │   │   │                     # conditional UPDATE + delegation lookup
│   │   │   ├── notification.py   # render + dispatch fanout (email /
│   │   │   │                     # SMS stub / in_app / webhook outbox)
│   │   │   ├── integration.py    # execute_flow + per-step executor
│   │   │   │                     # (requests library, never imports models
│   │   │   │                     # at module scope)
│   │   │   └── process_mining.py # detect_bottleneck / compute_cycle_seconds /
│   │   │                         # cycle_time_stats / classify_severity
│   │   ├── signals.py            # 8 hooks (all L-18 weak=False / dispatch_uid):
│   │   │                         #   instance status -> activity log
│   │   │                         #   instance completed -> cycle_time metric
│   │   │                         #   approval approved/rejected/escalated ->
│   │   │                         #     notification fanout
│   │   │                         #   pending notification auto-dispatch
│   │   │                         #   integration-failed -> failure notification
│   │   │                         #   dms.DocumentApprovalRequest approved ->
│   │   │                         #     close linked wfa.ApprovalRequest
│   │   │                         #   procurement.PurchaseOrder submitted ->
│   │   │                         #     auto-create wfa.ApprovalRequest
│   │   │                         #     (gated on active policy - no-op otherwise)
│   │   │                         #   audit factory for 8 status-tracked models
│   │   ├── forms.py              # 22 ModelForms with L-01 unique_together,
│   │   │                         # L-02 validators, L-14 per-workflow forms
│   │   │                         # (ApprovalRejectForm, ProcessInstanceCancelForm,
│   │   │                         # SuggestionStatusForm)
│   │   ├── views.py              # ~75 views across all 5 sub-modules with
│   │   │                         # @tenant_admin_required gating on policy /
│   │   │                         # process / connector mutations + delete (L-10)
│   │   ├── urls.py               # ~80 URL patterns under wfa namespace
│   │   ├── admin.py              # readonly_fields='__all__' on append-only
│   │   │                         # ledgers (ProcessActivity / ApprovalActionLog /
│   │   │                         # NotificationDelivery / SMSDelivery /
│   │   │                         # WebhookOutboxEntry)
│   │   ├── tests/                # conftest + test_models / test_forms /
│   │   │                         # test_services / test_signals / test_views /
│   │   │                         # test_security / test_seeder (98 tests)
│   │   └── management/commands/
│   │       ├── seed_wfa.py              # Idempotent demo seeder per tenant
│   │       ├── run_notifications.py     # Cron: dispatch due pending rows
│   │       ├── escalate_approvals.py    # Cron: SLA-breach escalation
│   │       └── mine_processes.py        # Refresh BottleneckAnalysis +
│   │                                    # CycleTimeReport for active processes
│   │
│   ├── bi/                       # MODULE 16 — Business Intelligence & Analytics
│   │   ├── models.py             # KPIDefinition, KPIDashboard, KPIWidget,
│   │   │                         # KPISnapshot, ReportDataSource,
│   │   │                         # ReportDefinition, ReportField, ReportFilter,
│   │   │                         # ReportRun, PredictiveModel, PredictionRun,
│   │   │                         # PredictionResult, TrendAnalysis,
│   │   │                         # DataMart, DataMartColumn, DataMartSnapshot,
│   │   │                         # DataMartRow, ReportSchedule, ReportRecipient,
│   │   │                         # ReportExport, ReportDelivery (21 models)
│   │   ├── services/
│   │   │   ├── registry.py       # REGISTERED_SOURCES whitelist (12 sources)
│   │   │   ├── kpi.py            # 9 KPI calculators + KPI_REGISTRY +
│   │   │   │                     # classify_value, refresh_snapshot
│   │   │   ├── reports.py        # execute_report, run_and_persist,
│   │   │   │                     # rows_to_csv (safe ORM builder)
│   │   │   ├── predictions.py    # linear_regression, linear_regression_forecast,
│   │   │   │                     # rolling_average, rolling_failure_rate,
│   │   │   │                     # naive_seasonal, chart_trend,
│   │   │   │                     # run_demand_forecast, run_failure_likelihood,
│   │   │   │                     # run_quality_trend + PREDICTION_REGISTRY
│   │   │   ├── datamart.py       # refresh_mart (atomic delete+insert)
│   │   │   └── scheduler.py      # due_schedules, run_schedule, sweep_due
│   │   ├── signals.py            # Audit factory (L-18 weak=False) for
│   │   │                         # 10 audited models;
│   │   │                         # cost.AccountingPeriod(status='closed')
│   │   │                         # post_save -> refresh all KPI snapshots
│   │   ├── forms.py              # 13 ModelForms + 2 workflow forms (L-01 /
│   │   │                         # L-14 / L-22 / XOR Report-or-Dashboard)
│   │   ├── views.py              # ~50 CBVs across all 5 sub-modules
│   │   ├── urls.py               # 50+ URL patterns
│   │   ├── admin.py
│   │   ├── tests/                # conftest + test_models / test_forms /
│   │   │                         # test_services / test_security /
│   │   │                         # test_views / test_signals / test_seeder
│   │   │                         # (93 tests, ~110s)
│   │   └── management/commands/
│   │       ├── seed_bi.py        # Idempotent demo seeder
│   │       └── run_report_schedules.py # Cron-style schedule sweeper
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
│   ├── procurement/              # index, suppliers/, po/, rfq/, quotations/, scorecards/, asn/, supplier_invoices/, blanket/, releases/, portal/
│   ├── eam/                      # index, categories/, assets/, meter_readings/, pm_plans/, pm_schedules/, condition_points/, condition_readings/, failure_predictions/, mwo/, downtime/, tools/, tool_maintenance/
│   ├── labor/                    # index, departments/, positions/, employees/, skills/, skills_matrix/, certifications/, employee_certifications/, employee_documents/, employee_skills/, shifts/, shift_rosters/, attendance/, leave_types/, leave_requests/, holidays/, cost_centers/, labor_rates/, labor_bookings/, training_programs/, training_plans/, training_sessions/, training_attendance/, competency_assessments/, incentive_schemes/, piece_rates/, incentive_periods/, incentive_runs/
│   ├── cost/                     # index, standard_versions/, standard_costs/, actual_costs/, variances/, jobs/, wip_entries/, cost_drivers/, overhead_pools/, overhead_rates/, driver_actuals/, overhead_allocations/, periods/, cogm/, gross_margin/, plant_pnl/
│   ├── utility/                  # index, types/, meters/, consumption/, tariffs/, allocations/, dr_events/, peak/, factors/, emissions/, sustainability/, benchmarks/, reports/
│   ├── iot/                      # index, protocols/, brokers/, devices/, tags/, readings/, batches/, edge_processors/, stream_metrics/, twins/, twin_attributes/, twin_scenarios/, oee/{dashboard,periods,state_logs,loss_reasons}, alerts/{rules,detections,notifications}
│   ├── bi/                       # index, _pagination, kpi/{definitions_list,definition_form,definition_detail,snapshots_list}, dashboards/{list,form,detail}, widgets/{form}, reports/{data_source_list,data_source_form,definitions_list,definition_form,definition_detail,run_list,run_detail}, predictive/{models_list,model_form,model_detail,run_list,run_detail,run_cancel,trend_list}, datamarts/{list,form,detail}, distribution/{schedule_list,schedule_form,schedule_detail,schedule_disable,delivery_list,delivery_detail,export_list}
│   ├── sales/                    # index, _pagination, customers/{list,form,detail,contact_form,communication_form,communication_list,document_upload}, categories/{list,form}, pricelists/{list,form,detail,item_form}, orders/{list,form,detail,line_form,revision_detail}, promising/{atp_list,atp_request,atp_detail,ctp_list,ctp_request,ctp_detail}, routes/{list,form,detail}, shipments/{list,form,detail,line_form,pod_form}, invoices/{list,form,detail,line_form}, portal/{dashboard,order_list,order_detail,tracking,invoice_list,invoice_detail}
│   └── wfa/                      # index, _pagination, processes/{list,form,detail,diagram,category_list,category_form,node_form,transition_form}, instances/{list,form,detail,cancel}, approvals/{policy_list,policy_form,policy_detail,level_form,escalation_form,request_list,request_form,request_detail,my_requests,delegation_list,delegation_form}, notifications/{channel_list,channel_form,template_list,template_form,rule_list,rule_form,list,detail,delivery_list,sms_list}, integrations/{connector_list,connector_form,connector_detail,endpoint_form,flow_list,flow_form,flow_detail,step_form,run_list,run_detail,outbox_list}, mining/{bottleneck_list,bottleneck_form,bottleneck_detail,suggestion_list,suggestion_form,suggestion_detail,cycle_time_list,cycle_time_detail}
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
- **Per tenant (Module 10 — EAM)** — 6 `AssetCategory` rows (Pumps, Motors, CNC Machines, Conveyor Systems, HVAC Equipment, Tooling); 10 `Asset` rows (auto `ASSET-00001`+) across 5 categories with mixed criticality (`PUMP-01`, `PUMP-02`, `MOTOR-01`, `MOTOR-02`, `CNC-LATHE-01` with `SPINDLE-01` as a sub-asset, `CNC-MILL-01`, `CONV-01`, `HVAC-01`, `COMP-01`); ~12 `AssetSparePart` rows linking critical/high assets to seeded `plm.Product` rows; 180 `AssetMeterReading` rows (30 days × 6 metered assets); 4 `MaintenancePlan`s (calendar / meter / both triggers) with 13 total `MaintenanceTask` rows + 3 future `PMSchedule` rows per plan via `generate_upcoming_pm`; 6 `ConditionMonitoringPoint`s on critical assets with 25 normal `ConditionReading` rows each, plus 1 deliberately critical reading on the first point so the post-save signal **auto-spawns a `FailurePrediction(status='open')`** (1 prediction per tenant); 3 `MaintenanceWorkOrder`s — 1 completed breakdown on a pump with full `MWOLaborLog` + `MWOMaterialLog` + `DowntimeEvent` (240 min unplanned downtime), 1 scheduled corrective on a motor, 1 in-progress preventive on a CNC; 2 `Tool` rows — 1 cutting tool (`TOOL-00001`) with 1 sharpening `ToolMaintenanceRecord` + 1 `ToolUsageLog`, plus 1 mold (`TOOL-00002`) with 4 `MoldCavityHistory` rows (one repaired, three active) + 1 cleaning `ToolMaintenanceRecord`.
- **Per tenant (Module 12 — Cost)** — 3 `AccountingPeriod` rows (prev month closed, current month open, next month open), 5 `CostDriver` rows (machine_hours / direct_labor_hours / units / sq_ft / kwh), 5 `OverheadPool` rows (Factory Rent / Utilities / Supervision / Indirect Materials / Plant Insurance), `OverheadRate` rows for both prior and current period (10 total), 1 active `StandardCostVersion` (`SCV-00001`) with one `StandardCost` row per finished_good / sub_assembly product (~13 per tenant — pulled from `bom.BOMCostRollup` where present, else fallback Decimals); `JobCost` rows for every released / in-progress / completed `pps.ProductionOrder` (~4 per tenant) with seeded `WIPEntry` chains (material_issued + labor_applied + overhead_applied + completion on closed jobs); `apply_overhead(prev_period)` invoked to materialize ~11 `OverheadAllocation` rows; 1 `CostVariance` (`VAR-00001`) per closed-period job; `ActualCost` rollups for every job; 1 `COGMReport` (`COGM-00001`) for the prior period; 1 `PlantPnLReport` with seeded SG&A inputs (selling=800, G&A=1200, unallocated=200).
- **Per tenant (Module 14 — Utility)** — 6 `UtilityType` rows (electricity / water / natural_gas / steam / compressed_air / fuel_oil; electricity bridged to `cost.CostDriver` `KWH` when present), 4 `UtilityMeter` rows (`MAIN-ELEC-01` linked to first seeded `eam.Asset`, `MAIN-WATER-01`, `MAIN-GAS-01`, plus a `LINE-2-ELEC-01` sub-meter under `MAIN-ELEC-01`), 5 `UtilityTariff` rows (one per type except fuel_oil) with flat-rate USD pricing anchored to the current accounting period, 4 `TOURateBand` rows on the electricity tariff (peak / shoulder / off_peak weekday + off_peak weekend), 1 `DemandResponseEvent` (`DRE-00001`, voluntary, scheduled tomorrow 14:00–17:00, 15 % target reduction, $500 incentive), 5 `EmissionFactor` rows (electricity_grid Scope 2, natural_gas Scope 1, water Scope 3, fuel_oil Scope 1, employee_commute Scope 3 — citing GHG Protocol / DEFRA), ~120 `UtilityConsumption` rows (~30 days × 4 meters spanning prior + current periods — electricity meters write `eam.AssetMeterReading` so the **EAM auto-feed signal** cascades a `UtilityConsumption` proving the cross-module hook; water / gas write directly via `services.meters.post_consumption`), each consumption auto-cascading a `CarbonEmission` row via `UtilityConsumption.post_save`, 1 `UtilityAllocation` (`UAL-00001`) per metered cost-center for the current period via `services/allocation.post_allocation` (which writes the matching `cost.DriverActuals` row), 2 `SustainabilityKPI` snapshots (one per period), 2 `BenchmarkSnapshot` rows (one per period), 1 `BenchmarkComparison` (`BCR-00001`, period-over-period: prior vs. current).
- **Per tenant (Module 16 — BI & Analytics)** — 9 `KPIDefinition` rows (OEE / throughput / yield / scrap_rate / on_time_delivery / supplier_otd / gross_margin / energy_intensity / carbon_intensity) with seeded `target_value` / `warning_threshold` / `critical_threshold`; 1 `KPIDashboard` ("Plant Operations") with 6 `KPIWidget` tiles (OEE / throughput / yield / scrap_rate as `kpi_card`, on_time_delivery as `gauge`, gross_margin as `kpi_card`); 9 tenant-scope `KPISnapshot` rows materialized via `services/kpi.refresh_snapshot()` for the last 30 days (each carries `value`, `status`, `sample_size`); 6 `ReportDataSource` catalog rows (production_orders / production_reports / non_conformance_reports / oee_periods / supplier_invoices / utility_consumption) bound to the static `REGISTERED_SOURCES` whitelist; 1 `ReportDefinition` ("Daily Production Summary") with 4 `ReportField` columns + 1 completed `ReportRun` (results coerced to JSON-safe shapes for inline preview); 2 `PredictiveModel` rows (demand_forecast + failure_likelihood) with 1 completed `PredictionRun`; 1 `DataMart` ("Production Daily") with 5 `DataMartColumn` rows + 1 `DataMartSnapshot` + materialized `DataMartRow` set scoped to the tenant; 1 active `ReportSchedule` (weekly, due tomorrow) with 1 `ReportRecipient`. Idempotent — re-running `seed_bi` skips a tenant if any KPI definition already exists; use `--flush` to wipe + re-seed.
- **Per tenant (Module 15 — IoT & SCADA)** — 6 shared `DeviceProtocol` rows (mqtt / opc_ua / modbus_tcp / modbus_rtu / http_polling / coap; created once and reused across tenants), 2 `DeviceBroker` rows (`MQTT-LOCAL` + `OPCUA-LOCAL`, both `active`), 6 `Device` rows linked to the first seeded `eam.Asset` rows (`SENSOR-PUMP-01`, `SENSOR-MOTOR-01`, `PLC-CNC-LATHE-01`, `PLC-CNC-MILL-01`, `SENSOR-CONV-01`, `GATEWAY-HVAC-01`), 30 `DeviceTag` rows (5 per device: temperature / vibration_x / pressure / electrical_load / machine_state), 5 `LossReason` rows (PLANNED_MAINT / BREAKDOWN / STARVED / MICRO_STOP / SETUP_CHANGEOVER), 4 `AlertRule` rows (High Temperature, High Vibration, Electrical Z-Score, Missing Data Watchdog), ~120 `IoTReading` rows (24h × 4 tags × 6 devices) seeded with normal-noise values, plus 2 deliberately anomalous rows (92.5°C temp, 15.2 mm/s vibration) that auto-cascade into `AnomalyDetection` + `AlertNotification` proving the post-save signal pipeline, 3 `DigitalTwin` rows on the first 3 metered devices with 4 attributes each (3 measurement + 1 derived `health_score = 100 - (temperature - 60) * 2`) plus 1 completed `TwinSimulationScenario` and 1 `TwinStateSnapshot` on the first twin, 7 days × 3 assets of `OEEPeriod` rows (~21 rows) with seeded run-minutes / total-count / good-count, ~21 corresponding `MachineStateLog` rows, and 2 `EdgeProcessor` rows (5-min rolling avg + threshold count). The `StreamMetric` denorm rows (latest value + 24h aggregates) materialize automatically via `IoTReading.post_save`.
- **Per tenant (Module 20 — Workflow & Automation)** — 3 `ProcessCategory` rows (Operations / Finance / Service), 2 `ProcessDefinition`s (`BPM-00001` Purchase Order Approval + `BPM-00002` RMA Request Triage) with full node/transition graphs (6 + 7 nodes), 1 active `ProcessInstance` per definition with sample `ProcessActivity` log entries, 2 `ApprovalPolicy`s (`POL-PO` 2-level for `procurement.PurchaseOrder` + `POL-RMA` 1-level for `rma.RMARequest`) with 1 `EscalationRule` on the PO policy, 3 sample `ApprovalRequest`s spanning `in_progress / approved / rejected`, 1 `ApprovalDelegation` between the first two seeded users, 4 `NotificationChannel` (email / sms / in_app / webhook), 5 `NotificationTemplate` covering `approval.requested / approved / rejected / escalated / integration.failed` + 5 matching `NotificationRule`s, 6 `Connector` catalog rows (SAP / Oracle / Dynamics / NetSuite / Salesforce / HubSpot — all `is_active=False` for safety so the seeder never fires a real request), 2 `IntegrationFlow`s (PO Sync to ERP + Customer Sync from CRM) each with 3 `FlowStep`s + 1 completed `IntegrationRun`, 4 `ProcessMetric` rows on the active PO instance, 1 `BottleneckAnalysis` (`BA-00001`) with 2 linked `ProcessOptimizationSuggestion`s (`POS-00001` new + `POS-00002` acknowledged), and 1 `CycleTimeReport` (`CTR-00001`) summarising the prior 30-day window.
- **Global (shared) catalog** — 8 `ComplianceStandard` records (ISO 9001, ISO 14001, RoHS, REACH, CE, UL, FCC, IPC) + 6 `DeviceProtocol` rows (MQTT, OPC-UA, Modbus TCP/RTU, HTTP, CoAP).

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
- **`TenantAuditLog`** — immutable record with `action`, `target_type`, `target_id`, `user`, `ip_address`, `user_agent`, `meta` (JSON), `timestamp`, plus tamper-evident **`prev_hash`** + **`this_hash`** SHA-256 chain (FDA 21 CFR Part 11 / ISO 9001). Every insert chains to the previous in-tenant row; the verifier service [`apps.tenants.services.audit_chain.verify_tenant_audit_chain(tenant)`](apps/tenants/services/audit_chain.py) recomputes the chain and reports any tampered or missing rows. Backfill data migration [`apps/tenants/migrations/0003_backfill_audit_chain.py`](apps/tenants/migrations/0003_backfill_audit_chain.py) chains pre-existing rows.
- **`Tenant.require_compliance_e_signature`** — opt-in BooleanField (default False). When True, every `plm.ProductCompliance` transition INTO `status='compliant'` requires a typed-name e-signature (writes a `plm.ProductComplianceSignature` row); see [Module 13 → Phase C additions](#module-13--compliance--regulatory-management).
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
- **`ProductCompliance`** — links a `Product` to a `ComplianceStandard` with status (`pending` / `in_progress` / `compliant` / `non_compliant` / `expired`), `certification_number`, `issuing_body`, `issued_date`, `expiry_date`, optional `certificate_file`. Unique per `(tenant, product, standard)` — duplicate POST is caught at the form layer (lessons L-01) so the user sees a clean error rather than a 500. `expiry_date < issued_date` is also rejected at the form layer.
- **`ComplianceAuditLog`** — **immutable** per-record trail (FDA 21 CFR Part 11 alignment): instance + queryset `save()` / `update()` / `delete()` raise `PermissionDenied`; admin registration disables add / change / delete buttons; only the post-save signal can write. Every row is **chained via SHA-256** (`prev_hash` + `this_hash` columns) — verify with [`apps.plm.services.audit_chain.verify_compliance_audit_chain(tenant)`](apps/plm/services/audit_chain.py). Backfill migration [`apps/plm/migrations/0006_backfill_compliance_audit_chain.py`](apps/plm/migrations/0006_backfill_compliance_audit_chain.py) chains pre-existing rows.
- **`ProductComplianceSignature`** *(opt-in)* — when `Tenant.require_compliance_e_signature=True`, every transition of a `ProductCompliance` record INTO `status='compliant'` requires the operator to type their name + role + reason; the view writes an immutable signature row anchored back into the `ComplianceAuditLog` chain. Form fields are hidden by default and only revealed on tenants that have opted in.
- **`expire_compliance` management command** — flips `status='compliant'` records past their `expiry_date` to `expired`; idempotent; emits one `ComplianceAuditLog(event='expired')` per flip + a cross-cutting `tenants.TenantAuditLog` row. Schedule daily via cron / Task Scheduler.

The list page surfaces an *Expiring within 30 days* counter (status-scoped to `compliant` only — non_compliant records are not "expiring", they're already broken). Certificate file allowlist: `.pdf .png .jpg .jpeg .zip`.

**Defects fixed against the SQA review (2026-05-09 / Phase A):** D-CR-01 (audit immutability), D-CR-02 (auto-expire), D-CR-04 (date inversion guard), D-CR-05 (unique-trap form guard), D-CR-07 (banner status filter), D-CR-08 (template doc string). All six are pinned by regression tests in [`apps/plm/tests/test_compliance_*.py`](apps/plm/tests/) (55 tests) plus 13 audit-chain + 10 e-signature regression tests added in Phase C (2026-05-10).

### Sub-module 2.5 — NPI / Stage-Gate Management

- **`NPIProject`** — auto-numbered `NPI-00001` per tenant, optional FK to `Product`, `project_manager`, `current_stage` (concept / feasibility / design / development / validation / pilot_production / launch), `status` (planning / in_progress / on_hold / completed / cancelled), target/actual launch dates
- **`NPIStage`** — pre-populated automatically when a project is created (one row per stage, sequenced 1-7), with `planned_start/end`, `actual_start/end`, `status` (pending / in_progress / passed / failed / skipped), `gate_decision` (pending / go / no_go / recycle), `gate_notes`, `gate_decided_by`
- **`NPIDeliverable`** — per-stage tasks with `owner`, `due_date`, `completed_at`, status (pending / in_progress / done / blocked)

The detail page renders the 7 stages as a Bootstrap accordion with inline deliverable add/edit/complete/delete forms. Editing a stage's `gate_decision` from `pending` automatically stamps `gate_decided_by` and `gate_decided_at`.

### Audit signals

`apps/plm/signals.py` wires:

- `pre_save` + `post_save` on `EngineeringChangeOrder` → writes `apps.tenants.TenantAuditLog` entries on every status transition (`eco.created`, `eco.status.<new>` with `meta={'from': old, 'to': new}`)
- `pre_save` + `post_save` on `ProductCompliance` → writes BOTH `TenantAuditLog` and a per-record `ComplianceAuditLog` entry on create and on status change. Both audit feeds are SHA-256 chained — `ComplianceAuditLog.prev_hash` / `this_hash` are computed at insert time via [`apps/core/services/audit_chain.py`](apps/core/services/audit_chain.py).

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
- **Customer portal CoA self-serve** — `released_to_customer` flag is set; surfacing the CoA on the [Module 17 customer portal](#module-17--sales--customer-order-management) is straightforward but not wired into the v1 portal templates yet.
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
- **Wave / batch picking** — release picking is single-line v1; multi-order wave is deferred. [Module 17](#module-17--sales--customer-order-management) ships single-shipment picking; multi-order wave grouping (route-based pick lists) is a v2 enhancement.
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

## Module 10 — Equipment & Asset Management (EAM)

Module 10 is implemented in [`apps/eam/`](apps/eam/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (PM scheduling, condition classification, downtime aggregation, atomic tool-life bumps) lives behind small pure-function services in [`apps/eam/services/`](apps/eam/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 10.1 — Asset Registry & Hierarchy

- **`AssetCategory`** — hierarchical taxonomy (e.g. `Pumps → Centrifugal → Process`). `unique_together=(tenant, name, parent)`. The form-level `clean()` covers the NULL-parent case the SQL constraint can't enforce.
- **`Asset`** — equipment master, auto-numbered **`ASSET-00001`**. `parent` self-FK enables hierarchies (e.g. `CNC-LATHE-01` carrying a `SPINDLE-01` sub-asset). Optional `inventory.Warehouse` FK for location, `criticality` (low / medium / high / critical), `status` (operational / down / maintenance / retired), `purchase_cost` / `current_value` / `warranty_expiry` for asset accounting. Per L-17, child audit-trail records (`AssetMeterReading`, `MaintenanceWorkOrder`) PROTECT this row from deletion if any audit data exists.
- **`AssetSparePart`** — through-table linking an asset to a `plm.Product` spare. `unique_together=(asset, product)` plus a form-level L-01 dedup check.
- **`AssetMeterReading`** — append-only ledger of meter readings across `hours / cycles / mileage / kwh / other`. PROTECT FK to `Asset` per L-17. Indexed on `(tenant, asset, meter_type, -recorded_at)` for the dashboard sparkline.
- **`AssetDocument`** — manuals / drawings / certificates / warranties / procedures with file uploads. Allowlist `.pdf .png .jpg .jpeg .dwg .dxf`, 25 MB cap.

### Sub-module 10.2 — Preventive Maintenance (PM)

- **`MaintenancePlan`** — recurring PM template. `trigger_type` ∈ `calendar / meter / both`. Calendar triggers use `frequency_days` (1–3650); meter triggers use `frequency_meter` + a free-text `meter_type` matching `AssetMeterReading.meter_type`. Form-level `clean()` enforces the right field-set per trigger.
- **`MaintenanceTask`** — ordered checklist row per plan with `expected_minutes` and `is_critical` flag. `unique_together=(plan, sequence)`.
- **`PMSchedule`** — auto-numbered **`PMS-00001`** specific upcoming PM event materialised from a plan. Status workflow `scheduled → in_progress → completed` (plus `skipped` and `overdue`). The `generate_pm_schedules` management command + the on-detail-page **Generate Upcoming** button both call the pure [`services/pm_scheduler.generate_upcoming_pm()`](apps/eam/services/pm_scheduler.py) which fans out future dates by `frequency_days` until either the horizon is exhausted or `max_count` is reached. The scheduler also pulls past anchor dates forward to today.
- **`PMTaskCompletion`** — operator-recorded result row, `pass / fail / na`, `unique_together=(pm_schedule, task)`. Per L-14, `PMScheduleCompleteForm` requires at least one task completion when the plan defines tasks.

### Sub-module 10.3 — Predictive Maintenance

- **`ConditionMonitoringPoint`** — per-asset measurement location for `vibration / temperature / pressure / current / oil_quality / noise / other`, with optional `low_alarm` and `high_alarm` thresholds. `unique_together=(tenant, asset, name)`.
- **`ConditionReading`** — append-only ledger. Auto-classified `normal / warning / critical` by [`services/prediction.classify_reading()`](apps/eam/services/prediction.py): inside the alarm band → `normal`; up to 20% beyond the band → `warning`; further → `critical`. Indexed on `(tenant, point, -recorded_at)` and `(tenant, status, -recorded_at)` for fast dashboard queries.
- **`FailurePrediction`** — heuristic prediction. `signals.condition_reading_post` auto-spawns a row (`status='open'`, default `confidence_pct=70`) when a reading lands as `critical` AND no open prediction already exists for the asset (idempotent). Workflow `open → investigating → resolved / false_positive`. Per L-14, `FailurePredictionResolveForm` requires non-empty `resolution_notes` to leave the open state.

### Sub-module 10.4 — Maintenance Work Orders

- **`MaintenanceWorkOrder`** — auto-numbered **`MWO-00001`**. Types: `breakdown / preventive / corrective / predictive / inspection`. Workflow `draft → scheduled → in_progress → on_hold → completed` (plus `cancelled`). Race-safe conditional `UPDATE … WHERE status IN (…)` on every transition (per L-03). Three optional source FKs: `source_pm_schedule`, `source_failure_prediction`, `source_andon` — enabling traceability from the originating event. Per L-14, `MWOCompleteForm` requires `resolution_notes` to complete.
- **`MWOLaborLog`** — append-only labor record with auto-computed `minutes` (from start/end timestamps) and `total_cost` (= `minutes × hourly_rate / 60`). PROTECT FK per L-17.
- **`MWOMaterialLog`** — append-only material consumption row with auto-computed `total_cost = quantity × unit_cost`. Optional `inventory.StockMovement` FK to cross-link the actual stock movement that backed the consumption.
- **`DowntimeEvent`** — append-only downtime ledger per asset, `planned / unplanned`, with auto-computed `minutes` from the start/end pair. The post-save signal calls [`services/downtime.refresh_mwo_downtime()`](apps/eam/services/downtime.py) to refresh the parent MWO's `downtime_minutes` denorm so the dashboard KPI stays in sync.

### Sub-module 10.5 — Tool & Die Management

- **`Tool`** — auto-numbered **`TOOL-00001`**. Types: `mold / die / jig / fixture / cutting_tool / gauge / other`. Tracks `expected_life_cycles` + `current_cycles` and `expected_life_hours` + `current_hours` denorms with helper methods `cycles_remaining()` / `hours_remaining()`. `cavity_count` is meaningful for mold-type tools only (form-level guard rejects the mismatch).
- **`ToolUsageLog`** — append-only usage record. The atomic [`services/tool_life.consume_usage_log()`](apps/eam/services/tool_life.py) writes the log and bumps the parent tool's denorms in a single transaction via a conditional `UPDATE` so two concurrent calls cannot stomp one another.
- **`ToolMaintenanceRecord`** — sharpening / cleaning / repair / calibration / inspection log with optional file attachment (allowlist `.pdf .png .jpg .jpeg`, 25 MB cap).
- **`MoldCavityHistory`** — per-cavity history for mold-type tools only (form-level guard). Tracks `cycles`, `defect_count`, and a `status` of `active / blocked / repaired`. `unique_together=(tool, cavity_number)`.

### Cross-module integration

| Touched | Bridge | Migration |
|---|---|---|
| `apps.mes.AndonAlert` | Added nullable FK `asset → eam.Asset`. Existing `equipment_id`-style free-text fields preserved (none today). | [`apps/mes/migrations/0002_andonalert_asset_mesworkorder_tool.py`](apps/mes/migrations/) |
| `apps.mes.MESWorkOrder` | Added nullable FK `tool → eam.Tool`. Enables tool-aware production reports. | (same migration) |
| `apps.qms.MeasurementEquipment` | Added nullable FK `asset → eam.Asset` so a calibrated instrument can be associated with the asset it lives on / serves. | [`apps/qms/migrations/0004_measurementequipment_asset.py`](apps/qms/migrations/) |
| Cross-module signal: `mes.AndonAlert.post_save` | When a new alert has `alert_type='equipment'` AND a non-NULL `asset` link AND no MWO already references it via `source_andon`, [`apps/eam/signals.py`](apps/eam/signals.py) auto-creates a draft `MaintenanceWorkOrder(wo_type='breakdown', source_andon=alert, priority=high/medium based on severity)`. Idempotent — re-firing on the same alert is a no-op. | (signal only) |
| Cross-module signal: `mes.ProductionReport.post_save` | When the parent `MESWorkOrder.tool` is set AND the report has positive `good_qty + scrap_qty`, the EAM signal emits a `ToolUsageLog(cycles_added=good+scrap)` and atomically bumps `Tool.current_cycles` via `services/tool_life.consume_usage_log()`. Idempotent via `(tool, mes_work_order, used_at)` natural key. | (signal only) |

Both EAM-side cross-module hooks live inside `apps/eam/signals.py` (not in mes/qms) so removing the EAM app cleanly disables the events without orphan code in other apps.

### Audit signals

[`apps/eam/signals.py`](apps/eam/signals.py) wires `pre_save` + `post_save` audit pattern for every status-tracked model (`Asset`, `PMSchedule`, `FailurePrediction`, `MaintenanceWorkOrder`, `Tool`) via the same `_mk_status_signals(model, action_prefix)` factory used by procurement. **All factory-registered handlers connect with `weak=False`** (Lesson L-18) so the inner closures are not garbage-collected after the factory returns; a regression-guard test in [`apps/eam/tests/test_signals.py — TestL18DispatchUIDPresence`](apps/eam/tests/test_signals.py) asserts every required `dispatch_uid` remains attached to `pre_save.receivers` / `post_save.receivers` after `apps.ready()`. Audit actions follow the convention `eam.<resource>.<status>` (e.g. `eam.mwo.in_progress`, `eam.tool.retired`, `eam.asset.down`).

`MaintenancePlan` carries its own dedicated handler that audits `eam.plan.activated` / `eam.plan.deactivated` on `is_active` flips (no factory needed — the trigger is binary, not a status enum).

### Validation guards (apply Lessons L-01, L-02, L-14)

- Every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check — `AssetCategoryForm` (parent + name), `AssetSparePartForm` (asset + product), `MaintenancePlanForm` (asset + name), `ConditionMonitoringPointForm` (asset + name), `MoldCavityHistoryForm` (tool + cavity number) (Lesson L-01).
- Every Decimal field carries explicit `MinValueValidator` + (where natural) `MaxValueValidator`: quantities ≥ 0.0001, percentages 0–100, money ≥ 0, `frequency_days` 1–3650, `confidence_pct` 0–100 (Lesson L-02).
- Per-workflow forms enforce per-transition required fields (Lesson L-14): `MWOCompleteForm.clean_resolution_notes()` requires non-empty notes; `FailurePredictionResolveForm.clean_resolution_notes()` requires non-empty notes; `PMScheduleCompleteForm.clean()` requires at least one `PMTaskCompletion` row when the plan defines tasks; `ToolMaintenanceRecordForm.clean_attachment()` enforces extension allowlist + 25 MB cap.

### Operator vs Admin matrix

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages | Authenticated tenant user | `TenantRequiredMixin` |
| Record a meter reading, record a condition reading, file labor / material logs against an MWO, create a downtime event, log tool usage, start / hold / resume / complete an MWO, start / complete a PM schedule, record a PM task completion | Authenticated tenant user | `TenantRequiredMixin` |
| Asset CRUD + retire / reactivate; PM plan + task CRUD + Generate Upcoming; PM schedule create + skip; Condition monitoring point CRUD + delete; Failure prediction Investigate / Resolve; MWO create / edit / delete / schedule / cancel; Tool CRUD + retire / reactivate; Tool maintenance record create; Mold cavity create; Downtime event delete | Tenant admin | `TenantAdminRequiredMixin` |

A regression test file ([`apps/eam/tests/test_security.py`](apps/eam/tests/test_security.py) — `TestRBACMatrix`) asserts redirect + state-not-changed for every admin-gated POST, plus `TestMultiTenantIDOR` confirms cross-tenant reads/writes 404, plus `TestAnonymousRedirect` confirms unauthenticated requests redirect to login.

### Test suite

Run the EAM test suite with `pytest apps/eam/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory). The suite covers model invariants + auto-numbering + decimal validators, form validation (L-01 + L-02 + L-14), pure-function services (`generate_upcoming_pm` calendar / meter / horizon caps; `classify_reading` across the alarm bands; `compute_downtime` planned/unplanned split; `bump_tool_life` atomic increment), audit + L-18 dispatch_uid presence guard, ConditionReading-spawns-FailurePrediction signal path with idempotency, DowntimeEvent-refreshes-MWO denorm, **cross-module hooks** (`mes.AndonAlert(equipment, asset)` → breakdown MWO with no-asset-link skip + non-equipment-type skip), full CRUD smoke + MWO/PM/prediction workflow, RBAC matrix (staff blocked from create/delete/retire/cancel/resolve while still allowed to record readings + start work), multi-tenant IDOR, and anonymous-redirect on every URL. **119 tests, ~58 s runtime.**

### Out of scope (deferred)

- **ML-driven failure prediction** — only heuristic alarm-band rules in v1; trend / anomaly / regression models deferred.
- **Real IoT / SCADA ingestion** — `ConditionReading` is created via UI form / management seed in v1; live MQTT / OPC-UA ingestion is **Module 15** scope.
- **Mobile-friendly technician app** — work order completion is desktop-only in v1; touch-optimized terminal akin to `mes/terminal/` deferred.
- **Spare-parts auto-reorder when asset triggers MWO** — the `MWOMaterialLog → inventory.StockMovement` link is manual in v1 (auto-create deferred).
- **Calibration consolidation** — `qms.MeasurementEquipment` and `eam.Asset` stay parallel concepts in v1 (linked by an optional FK, not unified).
- **Tool grinding / re-sharpening BOM cost roll-up** — tracked in `ToolMaintenanceRecord.cost` only; no rollup into `bom.CostElement`.
- **Warranty alerts** — `Asset.warranty_expiry` is stored but no proactive notification; deferred until Module 20 (Workflow & Process Automation).

---

## Module 11 — Labor & Workforce Management

Module 11 is implemented in [`apps/labor/`](apps/labor/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel`, every query is scoped by `request.tenant`, and the heavy work (cost lookups, attendance derivation, piece-rate aggregation, competency gap analysis) lives behind small pure-function services in [`apps/labor/services/`](apps/labor/services/) so the algorithms stay unit-testable and pluggable.

### Sub-module 11.1 — Employee Master & Skills Matrix

- **`Department`** — org-chart unit (Production / Quality / Maintenance / Admin) with self-FK `parent` and optional `manager` FK to `Employee`. `unique_together=(tenant, code)`.
- **`Position`** — job title within a department with `level` enum (`junior / mid / senior / lead / manager / director`).
- **`Employee`** — workforce master, auto-numbered **`EMP-00001`**. Optional `user` one-to-one to `accounts.User` (allows tracking contractors / non-system workers). `employment_type` (`permanent / contract / temporary / intern`), `status` (`active / on_leave / suspended / terminated`), `gender` choice with "prefer_not_to_say". Per L-17, child audit-trail rows protect this row from accidental deletion.
- **`Skill`** — tenant catalog (operations / quality / safety / leadership / technical / soft). `EmployeeSkill` maps employee → skill with 1–5 proficiency.
- **`Certification`** — tenant catalog with `valid_period_days`. `EmployeeCertification` records `issued_at` + `expires_at`, computes `status` (`active / expiring_soon / expired / revoked`) on `save()` (≤30 days → expiring_soon, past → expired). Dashboard surfaces expiring certs.

### Sub-module 11.2 — Time & Attendance Integration

- **`Shift`** — shift template (Morning / Evening / Night) with start/end times, `break_minutes`, `is_overnight` flag, and a `color` for the calendar UI.
- **`ShiftRoster`** — per-employee shift assignment over a date range with overlap protection.
- **`AttendanceRecord`** — one row per `(employee, work_date)` with `clock_in_at` / `clock_out_at`, computed `worked_minutes`, and a `status` (`present / absent / late / half_day / on_leave / holiday`). **Auto-emitted from `mes.OperatorTimeLog clock_in/out`** when the soft link `ShopFloorOperator.employee` is set.
- **`LeaveType`** — tenant catalog with `paid` flag, `default_annual_quota_days`, and `requires_attachment`.
- **`LeaveRequest`** — auto-numbered **`LR-00001`** with workflow `draft → submitted → approved / rejected → cancelled`. Per L-14, `LeaveDecisionForm` requires non-empty `decision_notes` for reject + cancel-of-already-approved.
- **`Holiday`** — tenant calendar of paid holidays (`unique_together=(tenant, holiday_date)`).

### Sub-module 11.3 — Labor Cost Allocation

- **`CostCenter`** — production / quality / maintenance / admin classifications with self-FK `parent`. Bound to `plm.Product` and `eam.Asset` via nullable FKs.
- **`LaborRate`** — per-employee hourly rate with `effective_from` / `effective_to` ranges and `overtime_multiplier` (1.0–3.0).
- **`LaborBooking`** — append-only labor cost ledger, auto-numbered **`LB-00001`**. PROTECT FK on `Employee` per L-17. Source types: `manual / mes_time_log / eam_mwo_labor`. Computed `total_cost = minutes × hourly_rate / 60` on `save()`. **Auto-emitted from**:
  - `mes.OperatorTimeLog stop_job` → **direct** booking against `production_order.product.cost_center`. Idempotent via `(source_time_log, kind='direct')` natural key.
  - `eam.MWOLaborLog` → **indirect** booking against `mwo.asset.cost_center`. Idempotent via `(source_mwo_labor, kind='indirect')`.
- The **`/labor/labor-bookings/summary/`** view aggregates by cost-center over a chosen date window with grand totals.

### Sub-module 11.4 — Training & Competency Management

- **`TrainingProgram`** — tenant catalog with `delivery_mode` (classroom / online / on_the_job / external), `duration_hours`, optional `competency_target` FK to `Skill`.
- **`TrainingPlan`** — per-employee assignment with workflow `assigned → in_progress → completed / waived / overdue`. Per L-14, `TrainingPlanWaiveForm` requires non-empty `notes`.
- **`TrainingSession`** — auto-numbered **`TS-00001`** with optional `instructor` FK to `Employee` and `capacity` (≥1).
- **`TrainingAttendance`** — per-attendee row with `attended` bool and 0–100 `score`. `unique_together=(session, employee)`.
- **`CompetencyAssessment`** — auto-numbered **`CA-00001`** with workflow `draft → completed`. Per L-14, complete requires ≥1 `CompetencyResult`. `overall_score` recomputed at completion via [`services/competency.compute_overall_score()`](apps/labor/services/competency.py) = `avg(min(actual, expected) / expected) × 100`.
- **`CompetencyResult`** — per-skill row with `expected_level` / `actual_level` (1–5) and computed `gap = expected − actual`. Skills-matrix view at `/labor/skills-matrix/` color-codes proficiency from L1 → L5.

### Sub-module 11.5 — Incentive & Piece-Rate Calculation

- **`IncentiveScheme`** — tenant catalog with `scheme_type` (`piece_rate / production_bonus / quality_bonus / attendance_bonus`). M2M to applicable employees / products / positions; empty M2M = applies to all.
- **`PieceRate`** — per-product **or** per-operation rate row inside a scheme, with optional min/max quantity bands. Form-level `clean()` requires either `product` or `operation` (not both NULL).
- **`IncentivePeriod`** — calculation window (typically monthly) with workflow `open → locked → paid`. `unique_together=(tenant, start_date, end_date)`.
- **`IncentiveRun`** — auto-numbered **`INC-00001`** per-period batch calculation with workflow `draft → running → completed / discarded`. The `Run` button executes inside an `transaction.atomic()`: clears prior `IncentiveLine` rows, scans `mes.ProductionReport` rows in the period (filtered by scheme.applicable_products M2M when set), groups by employee, applies the matching `PieceRate` via [`services/piece_rate.select_rate()`](apps/labor/services/piece_rate.py) (operation > product > catch-all preference), and materializes idempotent `IncentiveLine` rows.
- **`IncentiveLine`** — per-employee line within a run with `qualifying_units × rate_applied = amount` (computed on `save()`). M2M back to source `mes.ProductionReport` rows for traceability and idempotent re-firing of the cross-module signal.

### Cross-module integration

| Touched | Bridge | Migration |
|---|---|---|
| `apps.mes.ShopFloorOperator` | Added nullable one-to-one `employee → labor.Employee`. Existing seeded operators auto-link in the `seed_labor` first pass. | [`apps/mes/migrations/0003_shopflooroperator_employee.py`](apps/mes/migrations/) |
| `apps.eam.Asset` | Added nullable FK `cost_center → labor.CostCenter` so MWO indirect labor allocates to the right cost center. | [`apps/eam/migrations/0002_asset_cost_center.py`](apps/eam/migrations/) |
| `apps.plm.Product` | Added nullable FK `cost_center → labor.CostCenter` so MES direct labor allocates to the product's cost center. | [`apps/plm/migrations/0003_product_cost_center.py`](apps/plm/migrations/) |
| Cross-module signal: `mes.OperatorTimeLog.post_save (clock_in/out)` | Upserts today's `AttendanceRecord` for the linked Employee. Idempotent. Skips silently if `ShopFloorOperator.employee` is NULL. | (signal only) |
| Cross-module signal: `mes.OperatorTimeLog.post_save (stop_job)` | Looks up the previous `start_job/resume_job` for the same `(operator, work_order_operation)`, computes elapsed minutes, looks up the effective `LaborRate`, and writes a `LaborBooking(kind='direct')` against the product cost center. Idempotent. | (signal only) |
| Cross-module signal: `eam.MWOLaborLog.post_save` | Resolves `technician → User → Employee`, looks up the rate, writes `LaborBooking(kind='indirect')` against the asset cost center. Idempotent on the `MWOLaborLog` natural key. | (signal only) |
| Cross-module signal: `mes.ProductionReport.post_save` | When a draft `IncentiveRun` covers the report's period and a matching `PieceRate` exists, accumulates units into the per-employee `IncentiveLine` (M2M dedup). Silently skipped when no scheme matches. | (signal only) |

All cross-module hooks live inside [`apps/labor/signals.py`](apps/labor/signals.py) so removing the labor app cleanly disables the events without orphan code in other apps.

### Audit signals

[`apps/labor/signals.py`](apps/labor/signals.py) wires `pre_save` + `post_save` audit pattern via the same `_mk_status_signals(model, action_prefix)` factory used by procurement / EAM. **All factory-registered handlers connect with `weak=False`** (Lesson L-18). Audited models: `Employee`, `LeaveRequest`, `IncentiveRun`, `IncentivePeriod`, `CompetencyAssessment`, `TrainingPlan`, `EmployeeCertification`. A regression-guard test in [`apps/labor/tests/test_signals.py — TestL18DispatchUIDPresence`](apps/labor/tests/test_signals.py) asserts every required `dispatch_uid` remains attached after `apps.ready()`. Audit actions follow `labor.<resource>.<status>` (e.g. `labor.leave.approved`, `labor.incentive_run.completed`).

### Validation guards (apply Lessons L-01, L-02, L-14)

- Every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check — `DepartmentForm` / `PositionForm` / `SkillForm` / `CertificationForm` / `LeaveTypeForm` / `ShiftForm` / `CostCenterForm` / `IncentiveSchemeForm` / `TrainingProgramForm` (each on `code`); `HolidayForm` (on `holiday_date`); `IncentivePeriodForm` (on `start_date + end_date`); `EmployeeSkillForm` (employee + skill); `EmployeeCertificationForm` (employee + certification + certificate_number) (Lesson L-01).
- Every Decimal field carries explicit `MinValueValidator` (and `MaxValueValidator` where natural): `LaborRate.hourly_rate > 0` + `overtime_multiplier 1.0–3.0`; `LaborBooking.minutes > 0` + `total_cost ≥ 0`; `LeaveRequest.days_requested ≥ 0.5`; `TrainingProgram.duration_hours ≥ 0.5`; `TrainingAttendance.score 0–100`; `EmployeeSkill.proficiency 1–5`; `CompetencyResult.expected_level / actual_level 1–5`; `PieceRate.rate_per_unit > 0`; `IncentiveLine.amount ≥ 0` (Lesson L-02).
- Per-workflow forms enforce per-transition required fields (Lesson L-14): `LeaveDecisionForm.clean_decision_notes()` requires non-empty when `mode='reject'` or when cancelling an `approved` request; `TrainingPlanWaiveForm.clean_notes()` requires non-empty; `CompetencyAssessmentCompleteForm.clean()` requires `has_results=True`; `LeaveRequestForm.clean()` requires an attachment when `leave_type.requires_attachment` is set.

### RBAC (L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, leave-request submit / cancel-of-own | Authenticated tenant user | `TenantRequiredMixin` |
| Employee CRUD + terminate / reactivate; Department / Position / Skill / Certification / Shift / Roster / Attendance / LeaveType / Holiday / CostCenter / LaborRate CRUD; manual LaborBooking create / delete; LeaveRequest approve / reject; TrainingProgram / TrainingPlan / TrainingSession / Attendance / Competency CRUD + Complete / Waive; IncentiveScheme / PieceRate / IncentivePeriod / IncentiveRun CRUD + Run / Discard / Lock / Pay | Tenant admin | `TenantAdminRequiredMixin` |

A `TestRBACMatrix` regression test in [`apps/labor/tests/test_security.py`](apps/labor/tests/test_security.py) asserts redirect for every admin-gated GET when accessed by staff, plus `TestMultiTenantIDOR` (cross-tenant 404) and `TestAnonymousRedirect` (login-redirect on every URL).

### Test suite

Run the Labor test suite with `pytest apps/labor/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory). The suite covers model invariants + auto-numbering + decimal validators (L-02) + denorm computations (worked_minutes / total_cost / amount / gap / cert status), form validation (L-01 unique_together for every tenant-scoped form, L-02 bounds, L-14 per-workflow required), pure-function services (`compute_worked_minutes`, `derive_status`, `lookup_effective_rate`, `summarize_by_cost_center`, `compute_overall_score`, `gap_summary`, `cert_status_for`, `select_rate`, `aggregate_employee_units`, `date_range`, `split_overlapping`), audit + L-18 dispatch_uid presence guard, cross-module hooks (`eam.MWOLaborLog → indirect LaborBooking` with idempotency), full CRUD smoke + LeaveRequest workflow + Employee terminate/reactivate, RBAC matrix (staff blocked from 20 admin-only POST/GET endpoints), multi-tenant IDOR, and anonymous-redirect on every list URL. **145 tests, ~36 s runtime.**

### Out of scope (deferred)

- **Payroll computation** — labor bookings + incentive lines feed *into* payroll but actual payslip generation, tax math, and bank-disbursement integration are scoped to Module 12 (Cost Management & Accounting).
- **Biometric / RFID badge integration** — clock-in/out comes via the existing MES kiosk `OperatorTimeLog`; new biometric devices deferred to Module 15 (IoT & SCADA Integration).
- **Mobile self-service app** — desktop-only in v1; touch-optimized employee terminal deferred.
- **Multi-currency labor rates** — single tenant currency in v1.
- **Workflow approval chains** — flat 1-level approval (admin approves) in v1; multi-level (manager → HR → finance) deferred to Module 20 (Workflow & Process Automation).
- **Skill-gap-driven auto-training** — competency assessment surfaces gaps but does NOT auto-create training plans in v1; the admin reviews + creates manually.
- **Federated identity / SSO for employee login** — deferred to Module 22.

---

## Module 12 — Cost Management & Accounting

Module 12 is implemented in [`apps/cost/`](apps/cost/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel` and every query is scoped via `request.tenant`. Cross-module hooks read from `labor.LaborBooking` + `mes.ProductionReport` (additive — Module 12 owns no schema changes outside its own app, except for one nullable `standard_sale_price` field on `plm.Product` for the gross-margin revenue placeholder).

### Sub-module 12.1 — Standard Costing

- **`StandardCostVersion`** — auto-numbered **`SCV-00001`** per tenant, effective-dated container with workflow `draft → approved → active → archived`. Activating a version auto-archives any prior `active` version on the same tenant.
- **`StandardCost`** — per-product frozen cost row inside a version with `material_cost / labor_cost / overhead_cost / tooling_cost / subassembly_cost / total_cost` (denorm computed in `save()`). Source enum: `bom_rollup / manual / imported`. Unique per `(version, product)`.
- **`StandardCostHistory`** — immutable revision log of changes to active versions.
- [`services/standard_costing.recompute_from_bom(version)`](apps/cost/services/standard_costing.py) — pure-ish: reads `bom.BOMCostRollup` for each finished_good / sub_assembly product on the tenant and upserts `StandardCost` rows. Idempotent. Exposed as **Recompute from BOM** button on the version detail page.
- [`services/standard_costing.compare_versions(v1, v2)`](apps/cost/services/standard_costing.py) — pure dict diff sorted by absolute delta descending. Used by the `/cost/standard-versions/compare/` view.

### Sub-module 12.2 — Actual Cost Tracking & Variance

- **`ActualCost`** — computed actual-cost rollup snapshot per `(production_order, as_of_date)`. Aggregates from the parent `JobCost` denorms when present, falling back to direct labor-booking + overhead-allocation aggregation otherwise. `total_cost` denorm.
- **`CostVariance`** — auto-numbered **`VAR-00001`** with the canonical 6-axis breakdown: material price/usage, labor rate/efficiency, overhead spending/volume. `total_variance` denorm. Convention: positive = unfavorable (actual > standard); negative = favorable.
- [`services/actual_costing.compute_actual(po, as_of_date)`](apps/cost/services/actual_costing.py) — idempotent upsert.
- [`services/actual_costing.compute_variances(po, version)`](apps/cost/services/actual_costing.py) — uses a 60/40 split between price/usage and rate/efficiency in v1 (per-component qty + per-op minutes tracking deferred). Returns `None` when no `StandardCost` row exists for the version + product pair.

### Sub-module 12.3 — Work in Process (WIP) Accounting

- **`JobCost`** — auto-numbered **`JC-00001`**, one-to-one with `pps.ProductionOrder`. Status workflow: `open → closed`. Denorms `total_material / total_labor / total_overhead / total_completion_credit / wip_balance` are bumped atomically by `WIPEntry.save()` and rolled back by the internal `WIPEntry.pre_delete` signal.
- **`WIPEntry`** — auto-numbered **`WIP-00001`**, append-only ledger with entry types `material_issued / labor_applied / overhead_applied / completion / variance / adjustment`. Optional `cost_center` + `routing_operation` FKs enable operation-wise rollup. Optional source FKs (`source_movement`, `source_labor_booking`, `source_production_report`, `source_overhead_allocation`) enable idempotent cross-module emission, with **partial unique constraints** on `(source_*, entry_type)` (Postgres only — MariaDB silently drops these per its `W036` warning, but the application-level guard in each signal handler is already idempotent).
- [`services/wip.post_wip_entry(...)`](apps/cost/services/wip.py) — atomic ledger writer (mirrors `inventory.services.movements.post_movement`). Bumps the matching `JobCost` denorm under `select_for_update`.
- [`services/wip.close_job(job, force=False)`](apps/cost/services/wip.py) — refuses non-zero balance unless `force=True` (admin must post an explicit `adjustment` entry first to balance).
- [`services/wip.compute_operation_rollup(job)`](apps/cost/services/wip.py) — pure aggregation: `WIPEntry` rows grouped by `routing_operation` for the operation-wise cost report rendered on the job detail page.

### Sub-module 12.4 — Overhead Allocation

- **`CostDriver`** — tenant catalog of activity drivers (machine_hours, direct_labor_hours, units, sq_ft, kwh).
- **`OverheadPool`** — indirect cost pool (Factory Rent, Utilities, Supervision, Indirect Materials, Plant Insurance) with `pool_type` (`fixed / variable / semi_variable`) and `allocation_method` (`abc / volume / direct_labor_hours / direct_labor_cost / machine_hours`).
- **`OverheadRate`** — per-period budgeted rate per pool. Computed `rate_per_driver_unit = budgeted_amount / budgeted_driver_qty` on `save()`.
- **`OverheadActualPool`** — period rollup of actual indirect spend per pool. Fed by `labor.LaborBooking(kind='indirect')` accumulation via the `accumulate_indirect_labor` service.
- **`DriverActuals`** — recorded driver consumption per period (XOR `cost_center` / `production_order` target — form-level guard).
- **`OverheadAllocation`** — auto-numbered **`OHA-00001`** materialized allocation. Computed `applied_amount = driver_qty × rate_applied`.
- [`services/overhead.apply_overhead(period)`](apps/cost/services/overhead.py) — orchestrator: scans `DriverActuals` for the period, applies the matching `OverheadRate`, materializes `OverheadAllocation` rows, and auto-emits matching `WIPEntry(overhead_applied)` rows for production-order targets. **Idempotent** — re-running clears prior allocations + WIP entries for the period and re-emits. Refuses on `closed` periods.
- [`services/overhead.reverse_overhead(period, reason)`](apps/cost/services/overhead.py) — admin-only: marks all active allocations as reversed and emits offsetting WIP entries. Refused on closed periods.

### Sub-module 12.5 — Manufacturing Financial Reports

- **`AccountingPeriod`** — auto-numbered **`ACP-00001`** monthly (or quarterly) period with workflow `open → locked → closed`. Lock refuses new posts; close is irreversible and auto-generates the period's COGM / margin / P&L reports.
- **`COGMReport`** — auto-numbered **`COGM-00001`** with computed `cogm = opening_wip + direct_materials + direct_labor + overhead_applied − closing_wip`.
- **`GrossMarginReport`** — per-product per-period row with `revenue = units × sale_price`, `cogs = units × actual_cost_per_unit`, `gross_margin = revenue − cogs`, `margin_percent = gross_margin / revenue × 100`. Uses `plm.Product.standard_sale_price` as the v1 unit-price source; switching to `sales.SalesInvoiceLine` aggregates is a follow-up swap now that [Module 17 (Sales)](#module-17--sales--customer-order-management) has shipped.
- **`PlantPnLReport`** — period-level P&L with `gross_profit = revenue − cogm`, `operating_income = gross_profit − selling − general_admin − unallocated_overhead`. SG&A and unallocated-overhead inputs are manual (no SG&A schema in v1).
- All three reports render on the period detail page as compact tiles. The COGM detail page renders an ApexCharts horizontal bar of buckets; the P&L detail page renders a waterfall-style bar; both expose a **Print / PDF** action that uses the browser's print dialog (mirrors QMS CoA pattern).

### Cross-module integration

| Touched | Bridge | Migration |
|---|---|---|
| `apps.plm.Product` | Added nullable `standard_sale_price` (Decimal 14,4) for gross-margin revenue placeholder. | [`apps/plm/migrations/0004_product_standard_sale_price.py`](apps/plm/migrations/) |
| `apps.bom.BOMCostRollup` | **Read-only consumer** — `recompute_from_bom` reads it; no schema change. | — |
| `apps.pps.ProductionOrder` | **Read-only consumer** — `JobCost` references via one-to-one. | — |
| `apps.labor.LaborBooking` | **Read-only consumer** — `WIPEntry.source_labor_booking` lives in cost app. | — |
| `apps.mes.ProductionReport` | **Read-only consumer** — `WIPEntry.source_production_report` lives in cost app. | — |
| Cross-module signal: `labor.LaborBooking.post_save (kind='direct')` | Resolves `source_time_log → work_order_operation → work_order → production_order`, get-or-creates the `JobCost`, posts `WIPEntry(labor_applied)`. Idempotent via the `(source_labor_booking, entry_type)` constraint + application-level existence check. | (signal in `apps/cost/signals.py`) |
| Cross-module signal: `labor.LaborBooking.post_save (kind='indirect')` | Bumps `OverheadActualPool` for the matching open period + first active overhead pool. | (signal) |
| Cross-module signal: `labor.LaborBooking.pre_delete` | Reverses the matching `WIPEntry`. | (signal) |
| Cross-module signal: `mes.ProductionReport.post_save (good_qty > 0)` | Walks `work_order_operation → work_order → production_order`, looks up the active `StandardCost` for the product, posts `WIPEntry(completion)` at `good_qty × std_total`. Silently skipped when no active standard exists. | (signal) |
| Cross-module signal: `mes.ProductionReport.pre_delete` | Reverses the matching completion entry. | (signal) |
| Internal signal: `cost.WIPEntry.pre_delete` | Rolls back the parent `JobCost` denorm so manual deletes never drift. | (signal) |

All cross-module hooks live in [`apps/cost/signals.py`](apps/cost/signals.py) so removing the cost app cleanly disables the events without orphan code in other apps.

### Audit signals

[`apps/cost/signals.py`](apps/cost/signals.py) wires `pre_save` + `post_save` audit emissions via the same `_mk_status_signals(model, action_prefix)` factory used by procurement / EAM / labor. **All factory-registered handlers connect with `weak=False`** (Lesson L-18). Audited models: `StandardCostVersion`, `AccountingPeriod`, `JobCost`. Audit actions follow `cost.<resource>.<status>` (e.g. `cost.std_version.approved`, `cost.period.closed`, `cost.job.closed`).

### Validation guards (apply Lessons L-01, L-02, L-14)

- Every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check (Lesson L-01): `CostDriverForm`, `OverheadPoolForm`, `AccountingPeriodForm` (on `(start_date, end_date)`), `StandardCostVersionForm`, `StandardCostForm` (on `(version, product)`), `OverheadRateForm` (on `(pool, period)`), `CostVarianceForm` (on `(production_order, version)`).
- Every Decimal field carries explicit validators (Lesson L-02): `MinValueValidator(Decimal('0'))` on costs / amounts that cannot be negative; `MinValueValidator(Decimal('-99999999.9999'))` (effective `SIGNED` floor) on variance / signed-amount fields. `OverheadRate.budgeted_driver_qty` carries `MinValueValidator(Decimal('0.0001'))` so divide-by-zero is a form error rather than a runtime crash.
- Per-workflow forms enforce per-transition required fields (Lesson L-14): `StandardCostVersionApproveForm.clean_notes()` requires non-empty notes; `OverheadReverseForm.clean_reversal_reason()` requires non-empty reason; `AccountingPeriodLockForm` requires `confirm=True`; `DriverActualsForm.clean()` enforces XOR of `cost_center` / `production_order`.

### RBAC (L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, all list pages, detail pages, compare view, COGM / margin / P&L read | Authenticated tenant user | `TenantRequiredMixin` |
| StandardCostVersion CRUD + approve / activate / archive / recompute; StandardCost CRUD; CostVariance CRUD + recompute; ActualCost recompute; JobCost CRUD + close; WIPEntry CRUD; CostDriver / OverheadPool / OverheadRate / DriverActuals CRUD; apply / reverse overhead; AccountingPeriod CRUD + lock / close; COGM / margin / P&L generate | Tenant admin | `TenantAdminRequiredMixin` |

### Test suite

Run the Cost test suite with `pytest apps/cost/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory). The suite covers:

- **Model invariants + auto-numbering** (`SCV-`, `JC-`, `WIP-`, `OHA-`, `VAR-`, `ACP-`, `COGM-`) and denorm computations (`StandardCost.total_cost`, `OverheadRate.rate_per_driver_unit`, `OverheadAllocation.applied_amount`, `JobCost.wip_balance`, `COGMReport.cogm`, `GrossMarginReport.gross_margin / margin_percent`, `PlantPnLReport.gross_profit / operating_income`, `CostVariance.total_variance`).
- **Form validation** — L-01 unique_together for every tenant-scoped form, L-02 bounds (zero `budgeted_driver_qty` rejected), L-14 per-workflow required (approve / lock / reverse), `DriverActualsForm` XOR (cost-center XOR production-order), date range validation on `StandardCostVersionForm` and `AccountingPeriodForm`.
- **Pure-function services** — `recompute_from_bom`, `compare_versions`, `compute_actual`, `compute_variances`, `post_wip_entry` + denorm bump, `close_job` (zero / non-zero / force / already-closed paths), `reverse_wip_entry`, `compute_operation_rollup`, `compute_rate`, `apply_overhead` (idempotent rerun + closed-period refusal), `reverse_overhead`, `accumulate_indirect_labor`, `generate_cogm`, `generate_plant_pnl`.
- **Cross-module signals** — `labor.LaborBooking(direct).post_save → WIPEntry(labor_applied)`, idempotent on double-save, with full chain `OperatorTimeLog → WorkOrderOperation → ProductionOrder → JobCost`; `mes.ProductionReport(good_qty>0).post_save → WIPEntry(completion)` at standard cost; `WIPEntry.pre_delete` rolls back `JobCost` denorms.
- **Audit factory** — L-18 `dispatch_uid` presence guard; module-load smoke test.
- **Security** — `TestRBACMatrix` (~9 admin-only POST/GET endpoints redirect for staff), `TestMultiTenantIDOR` (cross-tenant 404 on every detail / edit / delete URL), `TestAnonymousRedirect` (login redirect on every list URL — 17 URLs), workflow gating on edit-after-approve and close-only-from-locked.
- **Views** — Full CRUD + workflow happy paths (create cost driver / period / version / pool + rate; version approve / activate auto-archives prior; period lock + close; create WIP entry via view; close job zero balance; recompute version; compare view; COGM / P&L generate views).

**129 tests, ~50 s runtime.**

### Out of scope (deferred)

- **Double-entry GL integration** — single-sided typed entries in v1; double-entry deferred to Module 21 (API & Integration Gateway).
- **Multi-currency** — single tenant currency in v1.
- **Real revenue feed** — `GrossMarginReport.unit_sale_price` reads `plm.Product.standard_sale_price` placeholder; the swap to `sales.SalesOrderLine` / `sales.SalesInvoiceLine` aggregates is a follow-up now that [Module 17 (Sales)](#module-17--sales--customer-order-management) has shipped.
- **FIFO / Average / LIFO costing methods** — standard costing only in v1.
- **Variance math precision** — v1 uses a 60/40 heuristic split between price/usage and rate/efficiency; full variance math requires per-component qty + per-op minutes tracking on `ActualCost`, deferred.
- **Capex / Opex budgeting** — out of scope; deferred to Module 16 (BI & Analytics).
- **Period-end audit roll-forward** — `WIPEntry` is append-only; once a period is closed, `WIPEntry` writes against that period's date range are still allowed on `JobCost` rows (no period-aware write guard yet). Tighten when audit-trail tampering becomes a risk.

---

## Module 13 — Compliance & Regulatory Management

Module 13 is implemented in [`apps/compliance/`](apps/compliance/) with full CRUD across all 5 sub-modules of [MSM.md §13](./MSM.md). Every model is `TenantAwareModel`, every query is scoped via `request.tenant`, and every workflow transition runs inside an atomic conditional `UPDATE` (lesson L-13). The complementary **PLM compliance subset** (`ComplianceStandard`, `ProductCompliance`, `ComplianceAuditLog` at [apps/plm/models.py:369](apps/plm/models.py#L369)) remains where it lives — Module 13 augments it with EHS, electronic document control, recall workflows, hazardous waste manifests, and an immutable cross-cutting audit trail.

| Sub-module | Models | URL prefix |
|---|---|---|
| **13.1 Environmental Health & Safety (EHS)** | `IncidentType`, `IncidentReport` (auto `INC-NNNNN`), `RiskAssessment` (auto `RA-NNNNN`, computed risk_score + risk_band), `SafetyAuditChecklist`, `SafetyAudit`, `SafetyAuditItem` | `/compliance/incidents/`, `/compliance/risks/`, `/compliance/checklists/`, `/compliance/audits/` |
| **13.2 Regulatory Document Control & e-Signatures** | `ComplianceDocument` (auto `DOC-NNNNN`, `draft → in_review → approved → effective → superseded` workflow, optional file attachment), `DocumentApproval`, `ElectronicSignature` (typed-name + reason + role; **immutable** — instance + queryset `save()`/`update()`/`delete()` raise `PermissionDenied`, FDA 21 CFR Part 11 alignment) | `/compliance/documents/` |
| **13.3 Audit Trail & Data Integrity** | `AuditLogArchive` (auto `ALA-NNNNN`, append-only snapshots of `tenants.TenantAuditLog` + `plm.ComplianceAuditLog` filtered by date range, sealed with SHA-256) — feeds the `Audit Trail` viewer that aggregates both audit feeds across the tenant | `/compliance/audit-trail/`, `/compliance/audit-trail/archives/` |
| **13.4 Waste & Emission Tracking** | `WasteCategory` (hazard_class enum), `WasteManifest` (auto `WM-NNNNN`, `draft → in_transit → disposed → reconciled` workflow with cancel guard), `WasteDisposalRecord` line items | `/compliance/waste-categories/`, `/compliance/waste-manifests/` |
| **13.5 Recall & Traceability Management** | `ProductRecall` (auto `RCL-NNNNN`, `initiated → in_progress → completed → closed` + cancel; severity = `class_i / class_ii / class_iii`; computed `recovery_pct` denorm), `RecallAffectedLot` (FK to `inventory.Lot`, recompute parent `affected_quantity / recovered_quantity`), `RecallNotice` (auto `RCN-NNNNN`, `draft → sent → acknowledged`) | `/compliance/recalls/` |

**Cross-module hooks** (signal-driven, all idempotent — three inbound + one outbound audit factory):
- **Hook 1 (C.1)** — `mes.AndonAlert(alert_type='safety').post_save` → auto-creates a draft `IncidentReport` linked back via `source_andon` (idempotent on the partial unique constraint `compliance_incident_unique_andon`).
- **Hook 2 (C.6)** — `qms.NonConformanceReport(severity='critical').post_save` → auto-creates an `IncidentReport` with `source_ncr` FK (idempotent on the partial unique constraint `compliance_incident_unique_ncr`). Mirrors hook 1; rationale is that a critical quality NCR often correlates with a safety event (recalled lot in production, contaminated material released).
- **Hook 3 (C.7)** — `inventory.StockMovement(outbound)` on a lot that's currently in an active `ProductRecall` → increments `RecallAffectedLot.post_recall_movement_count` and stamps `last_leak_at`. Outbound types covered: `issue / transfer / production_out / scrap`. Recall detail page renders affected-lot rows in yellow with a warning banner.
- **Status-change audit factory** in [`apps/compliance/signals.py`](apps/compliance/signals.py) emits `tenants.TenantAuditLog` rows for every `IncidentReport`, `RiskAssessment`, `SafetyAudit`, `ComplianceDocument`, `WasteManifest`, `ProductRecall`, and `RecallNotice` create / status-transition (lesson L-18 — closure receivers connected with `weak=False` + `dispatch_uid`; lesson L-23 — emit failures log `WARNING` instead of swallowing).
- `ElectronicSignature` rows are physically appended only — the model overrides `save()` to raise `ValidationError` after pk is set; admin registration sets all `has_*_permission` to `False`.

**Workflows** (all atomic + race-safe via conditional `QuerySet.update()` per lesson L-13):
- IncidentReport: `reported → investigating → corrective_action → closed | cancelled`.
- RiskAssessment: `draft → in_review → approved → archived`.
- SafetyAudit: `scheduled → in_progress → completed | cancelled`.
- ComplianceDocument: `draft → in_review → approved → effective → superseded`; one-shot Sign action emits an `ElectronicSignature` with the signer's typed-name + reason + role.
- WasteManifest: `draft → in_transit → disposed → reconciled` (+ `cancelled`); per-line `WasteDisposalRecord` CRUD.
- ProductRecall: `draft → in_progress → completed → closed` (+ `cancelled` with required reason); affected-lot add/remove triggers `recompute_affected_quantity` service that re-aggregates `affected_quantity / recovered_quantity` denorms.
- RecallNotice: `draft → sent → acknowledged`.

**Lessons applied** (cross-referenced in [.claude/tasks/lessons.md](.claude/tasks/lessons.md)):
- **L-01** — `unique_together` form `clean()` for tenant-scoped models with hidden tenant field (e.g., `IncidentTypeForm`, `WasteCategoryForm`).
- **L-02** — `MinValueValidator` on every Decimal quantity (recall `affected_quantity`, manifest line `quantity`, etc.).
- **L-03** — view + template status-gate parity via `is_*` model helpers (`is_investigatable`, `is_actionable`, `is_closeable`, `is_sendable`, `is_acknowledgable`, etc.).
- **L-04** — loud `messages.warning(...)` on workflow guard rejection.
- **L-12** — auto-numbered models retry on `IntegrityError` under contention.
- **L-13** — workflow status writes via `QuerySet.update()` inside `transaction.atomic()` for race-safety.
- **L-17** — `PROTECT` on every audit-trail child FK (`ElectronicSignature.document`, `RecallNotice.recall`, `WasteDisposalRecord.manifest`).
- **L-18** — status-audit signal factory connects with `weak=False` + unique `dispatch_uid`.
- **L-20** — `ElectronicSignature` immutability enforced at save / delete (the same pattern as `plm.ComplianceAuditLog` — see PLM Module 2).
- **L-22** — `ComplianceDocumentForm.clean_attachment` validates extension + content_type + 25 MiB size cap + magic-byte sniff; mirrors the utility-side CSV importer.
- **L-23** — `_audit()` helper logs `WARNING` (not silent `pass`) on `TenantAuditLog` failure, so audit-pipeline regressions are visible instead of structural-invisible.

**Service layer** ([apps/compliance/services/](apps/compliance/services/)):
- [`audit.py`](apps/compliance/services/audit.py) — `generate_archive(tenant, start, end)` collects matching audit rows, JSON-serializes, hashes (SHA-256), writes one `AuditLogArchive` row.
- [`document.py`](apps/compliance/services/document.py) — workflow transitions (`submit_document`, `approve_document`, `publish_document`, `supersede_document`) + e-sig writer.
- [`incident.py`](apps/compliance/services/incident.py) — workflow transitions for `IncidentReport`.
- [`recall.py`](apps/compliance/services/recall.py) — `recompute_affected_quantity(recall)`, add/remove affected lots, workflow transitions for `ProductRecall` + `RecallNotice`. **Phase C additions**: `sweep_lot_for_leaks(affected_lot)` recounts post-recall outbound movements (C.7) and `send_notice(notice)` actually delivers email via Django `send_mail` when channel=email (C.5).
- [`kpi.py`](apps/compliance/services/kpi.py) **(C.4)** — `compute_ehs_kpis(tenant, period_days)` computes OSHA TRIR / LTIR + near-miss ratio + period hours worked. Hours sourced from `apps.labor.AttendanceRecord.worked_minutes` with a documented 24,000 h fallback when labor data is missing.

**Tests** ([apps/compliance/tests/](apps/compliance/tests/)) — **140 tests** across 8 files: model invariants + e-sig immutability (test_models, 20), workflow status guards + L-01 unique-trap regression (test_forms, 16), CRUD + filters + pagination + tenant scoping (test_views, 29), cross-tenant IDOR + e-sig admin readonly (test_security, 38), status-audit signals + 3 cross-module hooks: `mes.AndonAlert(safety)` + `qms.NCR(critical)` + `inventory.StockMovement(out)` (test_signals, 18), TRIR/LTIR/near-miss KPI math + dashboard render (test_kpi, 7), `RecallNotice.send` email delivery (test_recall_email, 6), N+1 query budgets for the dashboard + 5 list views (test_performance, 6). PLM-side compliance regression suite adds 65 more tests across 8 files (test_compliance_audit_immutable, test_compliance_esignature, test_compliance_forms, test_compliance_models, test_compliance_performance, test_compliance_security, test_compliance_views, test_compliance_workflow). The Tenants suite adds 7 SHA-chain tests for `TenantAuditLog` (test_audit_chain). **Total: 212 tests across Compliance (140) + PLM compliance regression (65) + Tenants audit-chain (7), all green in ~107 s.**

**Phase C additions (2026-05-10):**
- **Per-row SHA-256 hash chain on `tenants.TenantAuditLog` + `plm.ComplianceAuditLog`** (D-GAP-05) — every audit row now stores `prev_hash` + `this_hash` computed at insert time by [`apps/core/services/audit_chain.py`](apps/core/services/audit_chain.py). Backfill data migrations chain pre-existing rows for all tenants. Verifier services at [`apps/tenants/services/audit_chain.verify_tenant_audit_chain`](apps/tenants/services/audit_chain.py) and [`apps/plm/services/audit_chain.verify_compliance_audit_chain`](apps/plm/services/audit_chain.py) recompute and report any tampering as a list of broken pks. **Verified across all 3 seeded tenants: 823 + 49 = 872 rows, 0 broken.** (FDA 21 CFR Part 11 alignment.)
- **EHS leading + lagging KPIs** — `/compliance/` dashboard now shows TRIR (Total Recordable Incident Rate), LTIR (Lost Time Incident Rate), Near-Miss Ratio, and total Hours Worked (last 90 days). Service: [`apps/compliance/services/kpi.compute_ehs_kpis`](apps/compliance/services/kpi.py). Hours sourced from `apps.labor.AttendanceRecord.worked_minutes`; falls back to a documented 24,000 h placeholder when labor data is missing (banner shown to operator).
- **Outbound email for `RecallNotice.send`** — channel=email notices now actually deliver via Django `send_mail` using the project email backend (console in DEBUG, SMTP in production). New `recipient_email` field on `RecallNotice`; form requires it when channel=email. Idempotent (status-guarded), failure-tolerant (SMTP exceptions log a warning but don't roll back the workflow transition).
- **Cross-module hook 2 — `qms.NonConformanceReport(severity='critical').post_save` → `IncidentReport`** (auto-created with `source_ncr` FK, idempotent on the partial unique constraint `compliance_incident_unique_ncr`). Mirrors the existing `mes.AndonAlert(safety)` hook.
- **Cross-module hook 3 — `inventory.StockMovement(outbound)` on a recalled lot → leak detection** — every issue / transfer / production_out / scrap movement on a lot in an active recall increments `RecallAffectedLot.post_recall_movement_count` and stamps `last_leak_at`. Recall detail page renders affected-lot rows in yellow with a warning banner so operators can see leakage at a glance. Sweep service [`apps/compliance/services/recall.sweep_lot_for_leaks`](apps/compliance/services/recall.py) is also exposed for manual backfill.
- **PLM ProductCompliance e-signature binding (opt-in per tenant)** — new `Tenant.require_compliance_e_signature` flag (off by default). When on, every transition of a `plm.ProductCompliance` record INTO `status='compliant'` requires the operator to type their name + role + reason; the view writes a new `plm.ProductComplianceSignature` row (immutable via `PermissionDenied` on save/delete) AND a `ComplianceAuditLog(event='note_added', meta={'kind': 'e_signature', ...})` entry, anchoring the e-sig into the SHA-256 audit chain.
- **Manual UAT walkthrough** at [.claude/manual-tests/compliance-manual-test.md](.claude/manual-tests/compliance-manual-test.md) — 95 atomic checks across 14 sections covering smoke, EHS lifecycles, KPIs, document workflow + e-sig, audit-chain tamper test, waste, recall + leak detection, all 3 cross-module hooks, RBAC, negative cases.

**Still deferred:**
- **EHS dashboards beyond the 4 KPIs** — period-over-period charts, drill-down by department / shift, OSHA Form 300 export — deferred to Module 16 (BI & Analytics).
- **SMS / phone / regulatory-portal delivery channels for `RecallNotice`** — deferred to Module 19 (Document & Knowledge Management). Email delivery shipped in Phase C.

---

## Module 14 — Energy & Utility Management

Module 14 is implemented in [`apps/utility/`](apps/utility/) with full CRUD across 5 sub-modules. Every model is `TenantAwareModel` (except the `BenchmarkSnapshot` industry-average row which is intentionally tenant-`NULL`) and every query is scoped via `request.tenant`. Utility cost flows reach the GL via the existing `cost.DriverActuals` → `cost.OverheadAllocation` pipeline; revenue-per-utility intensity ratios via [Module 17 (Sales)](#module-17--sales--customer-order-management) `SalesInvoiceLine` aggregates are a follow-up swap. All cross-module integration is additive — Module 14 owns no schema changes outside its own app.

### Sub-module 14.1 — Utility Meter Integration

- **`UtilityType`** — tenant catalog (electricity / water / natural_gas / steam / compressed_air / fuel_oil) with optional FK to `cost.CostDriver` so the allocation service can bridge into the existing overhead pipeline.
- **`UtilityMeter`** — auto-numbered **`MTR-00001`** with self-referencing `parent_meter` for sub-metering, optional `inventory.Warehouse` location FK, optional `eam.Asset` FK (enables the cross-module auto-feed signal), `labor.CostCenter` FK, multiplier (for transformers / scaling factors), `installed_at` + `last_calibrated_at`.
- **`UtilityConsumption`** — auto-numbered **`UC-00001`**, append-only ledger. `consumption = (end_reading − start_reading) × meter.multiplier` and `total_cost = consumption × unit_cost` are both computed in `save()`. A partial unique constraint on `source_meter_reading` makes the EAM auto-feed idempotent — a second `post_save` on the same `eam.AssetMeterReading` is a no-op.
- [`services/meters.post_consumption(meter, ...)`](apps/utility/services/meters.py) — atomic ledger writer used by the import path and the cross-module signal fall-back.
- [`services/meters.bulk_import_billing(meter, csv_file)`](apps/utility/services/meters.py) — CSV-driven bulk billing import endpoint surfaced at `/utility/consumption/import/`.

### Sub-module 14.2 — Energy Cost Allocation

- **`UtilityTariff`** — auto-numbered **`TRF-00001`**, effective-dated price-per-unit per `UtilityType` with `flat_rate` fall-back and `currency`. When `TOURateBand` rows exist they take precedence at billing time.
- **`UtilityAllocation`** — auto-numbered **`UAL-00001`**, period-scoped distribution of metered cost across `target_cost_center` / `target_product` / `target_production_order` (XOR enforced at the form layer). Methods: `meter_consumption / production_volume / floor_area / direct_assignment`. `share_pct` bounded `[0, 100]`.
- [`services/allocation.compute_allocation(period, meter, targets)`](apps/utility/services/allocation.py) — pure dict computation that aggregates the meter's consumption + cost for the period and slices it across targets by `share_pct`.
- [`services/allocation.post_allocation(period, meter, targets, ...)`](apps/utility/services/allocation.py) — materializes `UtilityAllocation` rows **and emits a matching `cost.DriverActuals` row** for each production-order target so the existing `cost.services.overhead.apply_overhead(period)` orchestrator sweeps utility cost into the Utilities pool with no special-case code in the cost app. Sets `is_posted_to_cost=True` + `posted_at` + `posted_by`.
- [`services/allocation.reverse_allocation(allocation, reason)`](apps/utility/services/allocation.py) — admin-only: marks the allocation as reversed and emits an offsetting `cost.DriverActuals` adjustment.

### Sub-module 14.3 — Peak Demand Management

- **`TOURateBand`** — Time-of-Use rate band attached to a `UtilityTariff` (`peak / shoulder / off_peak`) with `day_of_week` enum (`all / weekday / weekend / 0..6`), `start_time`, `end_time`, and `rate`.
- **`DemandResponseEvent`** — auto-numbered **`DRE-00001`** utility-declared curtailment window with workflow `scheduled → active → completed | cancelled` (guarded by `is_activatable() / is_completable() / is_cancellable()` helpers per Lesson L-03), `event_type` (`mandatory / voluntary / advisory`), `target_reduction_pct`, `incentive_amount`, and `source` (`utility_provider / manual`).
- **`PeakShavingSuggestion`** — auto-numbered **`PSS-00001`**, **read-only** recommendation flagged on a `pps.ScheduledOperation` that overlaps either an active TOU peak band or a scheduled DR event. Workflow `new → acknowledged → dismissed`. **Never mutates the PPS schedule** — operators see the suggestion and choose whether to manually reschedule via the existing PPS / MES UI. Idempotency is enforced by two partial unique constraints (`(scheduled_operation, event)` and `(scheduled_operation, tou_band)`).
- [`services/peak.scan_for_peak_overlap(tenant, horizon_days=14)`](apps/utility/services/peak.py) — pure-ish scanner that walks the next `horizon_days` of `pps.ScheduledOperation` rows, tests each against active electricity-tariff TOU peak bands and `scheduled` DR events, and upserts `PeakShavingSuggestion` rows with computed `suggested_start / end` (next off-peak window) and `estimated_savings = (peak_rate − off_peak_rate) × estimated_kwh`. Idempotent — re-running the scan never duplicates.
- [`services/peak.acknowledge / dismiss`](apps/utility/services/peak.py) — workflow helpers used by the action views.

### Sub-module 14.4 — Carbon & Sustainability Reporting

- **`EmissionFactor`** — kgCO2e factor catalog per `(source_type, scope, region, effective_from)` covering Scope 1 (direct combustion), Scope 2 (purchased electricity / steam), and Scope 3 (water, refrigerant leakage, employee commute, business travel, waste, supply chain). `source_reference` carries the IPCC / GHG-Protocol / DEFRA / EPA citation for audit.
- **`CarbonEmission`** — auto-numbered **`CE-00001`**, append-only ledger of CO2-equivalent emissions per accounting period. Auto-emitted via `UtilityConsumption.post_save` signal when an active `EmissionFactor` exists. Idempotent via a partial unique constraint on `source_consumption`. `factor` FK is `PROTECT` so the regulator audit trail (which factor was current when the emission was recorded) cannot be silently mutated.
- **`SustainabilityKPI`** — per-period snapshot of headline ESG KPIs (totals across Scope 1 / 2 / 3, kWh, water m³, gas m³, units produced, `kwh_per_unit_produced`, `co2e_per_unit_produced`). `total_co2e_kg` and the intensity ratios are computed in `save()`. Drives the dashboard tiles.
- [`services/carbon.emit_for_consumption(consumption)`](apps/utility/services/carbon.py) — idempotent emitter called from the `UtilityConsumption.post_save` signal; resolves the active factor + accounting period.
- [`services/carbon.recompute_emissions(period)`](apps/utility/services/carbon.py) — refreshes the ledger for an open period (no-op on locked / closed periods).
- [`services/carbon.generate_sustainability_kpi(period)`](apps/utility/services/carbon.py) — aggregates `CarbonEmission` + `UtilityConsumption` + `mes.ProductionReport.good_qty` for the period.

### Sub-module 14.5 — Utility Benchmarking

- **`BenchmarkSnapshot`** — per-period per-plant efficiency snapshot with totals (kWh / water m³ / gas m³ / CO2e kg / cost / units produced) and per-unit denorms (`kwh_per_unit / water_per_unit / co2e_per_unit / cost_per_unit`) computed in `save()`. The `tenant` FK is **nullable** to allow anonymized industry-average rows (`tenant=NULL`, `plant_label='industry_avg'`); a superuser-only management command materializes those rows from a cross-tenant aggregate (no raw per-tenant data exposed).
- **`BenchmarkComparison`** — auto-numbered **`BCR-00001`** one-shot report. `comparison_type` is one of `plant_to_plant / period_over_period / tenant_to_tenant`. Stores `kwh_delta_pct / water_delta_pct / co2e_delta_pct / cost_delta_pct` (all `SIGNED` so improvements show as negative deltas) and a free-text `winner` label.
- [`services/benchmark.generate_snapshot(period)`](apps/utility/services/benchmark.py) — aggregates the period's consumption, cost, emissions, and `mes.ProductionReport.good_qty` into a single snapshot row.
- [`services/benchmark.compare(from_snapshot, to_snapshot)`](apps/utility/services/benchmark.py) — pure dict math that returns the four delta percentages.
- [`services/benchmark.create_comparison(...)`](apps/utility/services/benchmark.py) — materializes a `BenchmarkComparison` row with the deltas pre-computed.

### Cross-module integration

| Touched | Bridge | Migration |
|---|---|---|
| `apps.eam.AssetMeterReading` | **Read-only consumer** — `UtilityConsumption.source_meter_reading` lives in the utility app. | — |
| `apps.cost.CostDriver` | **Read-only consumer** — `UtilityType.cost_driver` is an optional bridge FK. | — |
| `apps.cost.AccountingPeriod` | **Read-only consumer** — `UtilityAllocation.period`, `CarbonEmission.period`, `SustainabilityKPI.period`, `BenchmarkSnapshot.period` are all `PROTECT` FKs into the existing period table. | — |
| `apps.cost.DriverActuals` | **Write consumer** — `services/allocation.post_allocation` materializes `cost.DriverActuals` rows tagged `notes='utility:…'` so `cost.services.overhead.apply_overhead(period)` sweeps utility cost into the Utilities pool. Reversal emits an offsetting actuals row. | — |
| `apps.labor.CostCenter` | **Read-only consumer** — `UtilityMeter.cost_center` + `UtilityAllocation.target_cost_center`. | — |
| `apps.inventory.Warehouse` | **Read-only consumer** — `UtilityMeter.location`. | — |
| `apps.plm.Product` | **Read-only consumer** — `UtilityAllocation.target_product`. | — |
| `apps.pps.ProductionOrder` + `apps.pps.ScheduledOperation` | **Read-only consumer** — `UtilityAllocation.target_production_order`, `PeakShavingSuggestion.production_order` + `.scheduled_operation`. | — |
| `apps.mes.ProductionReport` | **Read-only consumer** — `services/carbon.generate_sustainability_kpi` + `services/benchmark.generate_snapshot` aggregate `good_qty` for intensity ratios. | — |
| Cross-module signal: `eam.AssetMeterReading.post_save (meter_type='kwh')` | Resolves `asset → UtilityMeter` (first active meter linked to the asset), calls `services/meters.post_consumption` to spawn a `UtilityConsumption(source_meter_reading=…)`. Idempotent via the partial unique constraint on `source_meter_reading`. | (signal in `apps/utility/signals.py`) |
| Cross-module signal: `eam.AssetMeterReading.pre_delete` | Reverses the matching `UtilityConsumption` (and the cascaded `CarbonEmission`). | (signal) |
| Cross-module signal: `utility.UtilityConsumption.post_save` | Resolves an active `EmissionFactor` for the consumption's `(source_type, scope)` + accounting period and posts a `CarbonEmission(source_consumption=…)`. Silently skipped when no active factor is configured. Idempotent via the partial unique constraint on `source_consumption`. | (signal) |
| Cross-module signal: `utility.UtilityConsumption.pre_delete` | Reverses the matching `CarbonEmission`. | (signal) |

All cross-module hooks live in [`apps/utility/signals.py`](apps/utility/signals.py) so removing the utility app cleanly disables the events without orphan code in `eam` / `cost` / `pps`.

### Audit signals

[`apps/utility/signals.py`](apps/utility/signals.py) wires `pre_save` + `post_save` audit emissions via the same `_mk_status_signals(model, action_prefix)` factory used by procurement / EAM / labor / cost. **All factory-registered handlers connect with `weak=False` and a unique `dispatch_uid`** (Lesson L-18). Audited models: `UtilityMeter`, `UtilityTariff`, `UtilityAllocation`, `DemandResponseEvent`, `PeakShavingSuggestion`. Audit actions follow `utility.<resource>.<status>` (e.g. `utility.dr_event.activated`, `utility.allocation.posted`, `utility.peak.acknowledged`).

### Validation guards (apply Lessons L-01, L-02, L-14, L-17, L-18)

- Every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check (Lesson L-01): `UtilityTypeForm` (on `code`), `UtilityMeterForm` (on `meter_number` and `(utility_type, name)`), `UtilityTariffForm` (on `tariff_number`), `EmissionFactorForm` (on `(source_type, scope, region, effective_from)`), `BenchmarkSnapshotForm` (on `(period, plant_label)`).
- Every `Decimal` field carries explicit validators (Lesson L-02): `MinValueValidator(Decimal('0'))` on consumption / cost / kgCO2e / share % / multiplier; `MaxValueValidator(Decimal('100'))` on `share_pct` and `target_reduction_pct`; `SIGNED` (`-99999999.9999` floor) on `BenchmarkComparison.*_delta_pct` so improvements show as negative deltas; `MinValueValidator(Decimal('0'))` on `EmissionFactor.factor` (kgCO2e / unit cannot be negative).
- Per-workflow forms enforce per-transition required fields (Lesson L-14): `DemandResponseEventCancelForm.clean_cancellation_reason()` requires non-empty reason; `UtilityAllocationReverseForm.clean_reversal_reason()` requires non-empty reason; `PeakShavingSuggestionDismissForm.clean_dismiss_reason()` requires non-empty reason.
- `UtilityAllocationForm` enforces XOR of `target_cost_center / target_product / target_production_order` (mirrors `cost.DriverActualsForm`).
- `PROTECT` on audit-trail children (Lesson L-17): `CarbonEmission.factor`, `UtilityConsumption.meter`, `UtilityAllocation.period` + `.meter`, `BenchmarkSnapshot.period`, `BenchmarkComparison.from_snapshot` + `.to_snapshot`. Manual deletes are blocked so the regulator audit trail cannot drift.
- Audit factory connects every receiver with `weak=False` and a unique `dispatch_uid` (Lesson L-18) so signals survive module-reload in dev and never fire twice.

### RBAC (L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, all list pages, detail pages, peak-suggestion read | Authenticated tenant user | `TenantRequiredMixin` |
| UtilityType / UtilityMeter / UtilityConsumption CRUD; UtilityTariff + TOURateBand CRUD; UtilityAllocation CRUD + post / reverse; DemandResponseEvent CRUD + activate / complete / cancel; PeakShavingSuggestion scan / ack / dismiss; EmissionFactor CRUD; CarbonEmission recompute; SustainabilityKPI generate; BenchmarkSnapshot generate; BenchmarkComparison CRUD; CSV billing import | Tenant admin | `TenantAdminRequiredMixin` |

### Test suite

Run the Utility test suite with `pytest apps/utility/tests/` — uses [`config/settings_test.py`](config/settings_test.py) (SQLite in-memory). Test files live in [`apps/utility/tests/`](apps/utility/tests/) — `conftest.py`, `test_models.py`, `test_forms.py`, `test_services.py`, `test_signals.py`, `test_views.py`, `test_security.py`, `test_dashboard.py`, `test_cost_integration.py`, `test_eam_integration.py`, plus four gap-filling files added in the **D-01..D-10 SQA remediation pass** (`test_effective_dated.py`, `test_security_extended.py`, `test_performance.py`, `test_audit_log.py`). **222 tests, ~102 s runtime.** Covers model invariants + auto-numbering (`MTR-`, `UC-`, `TRF-`, `UAL-`, `DRE-`, `PSS-`, `CE-`, `BCR-`), denorm computations (`UtilityConsumption.consumption / total_cost`, `CarbonEmission.co2e_kg`, `SustainabilityKPI.total_co2e_kg / kwh_per_unit_produced / co2e_per_unit_produced`, `BenchmarkSnapshot.kwh_per_unit / water_per_unit / co2e_per_unit / cost_per_unit`, `BenchmarkComparison.*_delta_pct`), form validation (L-01 unique_together for every tenant-scoped form, L-02 decimal bounds incl. `share_pct` 0-100, L-14 per-workflow required reasons, `UtilityAllocationForm` XOR, **L-22** CSV import file size/extension/content-type/magic-byte validators (D-03), TOU rate-band duplicate pre-check (D-04), ISO-4217 currency shape (D-05)), pure-function services (`post_consumption` + idempotent EAM cascade, `post_allocation` + `cost.DriverActuals` write-through + reversal, `scan_for_peak_overlap` idempotent rerun, `compute_estimated_savings`, `emit_for_consumption` idempotent, `recompute_emissions` no-op on locked periods, `generate_sustainability_kpi`, `generate_snapshot`, `compare`, `create_comparison`, **effective-dated lookup correctness** — D-01 `_resolve_unit_cost` skips expired tariffs, D-02 `_resolve_factor` skips expired emission factors, D-06 `bulk_import_billing` parses datetime before dedup so whitespace and `Z` vs `+00:00` drift no longer bypass the guard), cross-module signals (`eam.AssetMeterReading(meter_type='kwh').post_save → UtilityConsumption` with double-save idempotency + non-kWh skip + missing-meter skip, `UtilityConsumption.post_save → CarbonEmission` with missing-factor skip + idempotency, `pre_delete` reversal counterparts, **D-08** admin-only `CarbonEmissionReverseView` emits typed-reason reversal rows), audit factory + L-18 `dispatch_uid` presence guard + **D-09** `_audit()` failure logs `WARNING` (no longer silently swallowed), **D-10** `BenchmarkSnapshot.tenant_objects.for_tenant(t)` manager guards the tenant=NULL industry-average row from cross-tenant leakage, `TestRBACMatrix` (admin-only POST/GET endpoints redirect for staff), `TestMultiTenantIDOR` (cross-tenant 404 on every detail / edit / delete URL), `TestAnonymousRedirect` (login redirect on every list URL), **N+1 query budgets** for the four primary list views and the dashboard.

### Out of scope (deferred)

- **Live IoT / SCADA streaming** — v1 reads consumption from `eam.AssetMeterReading` writes (manual + EAM seed). Real OPC-UA / MQTT ingestion is deferred to **Module 15 (IoT & SCADA Integration)**.
- **Real revenue feed** — sustainability + benchmark intensity ratios use `mes.ProductionReport.good_qty` for the denominator. Revenue-per-kWh and cost-per-revenue intensity metrics can now be wired through [Module 17 (Sales)](#module-17--sales--customer-order-management) `SalesInvoiceLine` aggregates (follow-up).
- **Renewable / on-site generation accounting** — solar / wind / battery export rows (`generation = generated − exported`) are not modelled in v1; treat on-site generation as a negative `UtilityConsumption` for now and tighten when a dedicated `GenerationAsset` model lands.
- **Multi-currency tariffs** — `UtilityTariff.currency` is a 3-letter code but every tenant runs a single currency in v1; cross-currency conversion happens upstream of the cost app.
- **Regulatory disclosure rendering** — CDP / TCFD / GRI / ESG framework templates are out of scope; **Module 13 (Compliance & Regulatory)** owns the disclosure layer when it ships.
- **Demand-response auto-execution** — DR events are recorded but the system does not automatically pause / reschedule production. Operators acknowledge `PeakShavingSuggestion` rows and reschedule manually via existing PPS / MES UI.
- **Anonymized industry-average aggregator** — the `BenchmarkSnapshot(tenant=NULL)` rows exist but the cross-tenant aggregation management command is deferred until at least 5 production tenants are live (privacy / k-anonymity threshold).
- **TOU mid-period rate change** — `UtilityConsumption` snapshots `unit_cost` at the time of write; mid-period TOU re-pricing requires a re-import via the bulk billing CSV path.

---

## Module 15 — IoT & SCADA Integration

Module 15 unifies device connectivity, real-time data acquisition, digital-twin modeling, OEE monitoring, and heuristic anomaly detection into a single tenant-scoped surface. **Live broker integration (real `paho-mqtt` / `asyncua` / `pymodbus`) is a v2 concern** — v1 ships a DB-stub plus JSON/CSV bulk ingest endpoint that exercises every cross-module hook end-to-end, consistent with how Modules 5–14 demoed without external infrastructure.

### Sub-modules

| Sub-module | Models | Notes |
|---|---|---|
| **15.1 Device Connectivity Hub** | `DeviceProtocol` (shared catalog), `DeviceBroker`, `Device`, `DeviceTag` | Brokers carry `tls_enabled` / `auth_method` / `password_hash` (stop-gap; production should use KMS / Vault). Tags optionally link to `eam.ConditionMonitoringPoint` to drive the IoT→EAM cascade. |
| **15.2 Real-Time Data Acquisition** | `IoTReadingBatch`, `IoTReading` (append-only ledger, auto `IR-00001`), `EdgeProcessor`, `StreamMetric` (latest-value denorm) | `services/ingestion.bulk_ingest` accepts JSON arrays or CSV; `services/edge.apply_edge_transform` provides rolling avg / sum / min / max / threshold count / state machine / derivative — all pure functions. `StreamMetric` is refreshed by `IoTReading.post_save`. |
| **15.3 Digital Twin Configuration** | `DigitalTwin`, `TwinStateAttribute` (state / measurement / derived), `TwinSimulationScenario`, `TwinStateSnapshot` | Derived attributes evaluate via `services/twin._safe_eval` — a whitelist-only AST walker that allows decimal numbers, variable refs, `+ - * /`, parens, and `min / max / abs`. **`eval()` and `exec()` are NEVER called.** Simulator (`services/twin_simulation.run_simulation`) is pure and never mutates twin state. |
| **15.4 OEE Monitoring** | `LossReason`, `MachineStateLog` (append-only, idempotent on `eam.DowntimeEvent` cascade via unique constraint on `(tenant, source_downtime)`), `OEEPeriod` (auto `OEEP-00001`) | A × P × Q × OEE % computed in `OEEPeriod.save()`. `services/oee.compute_oee_period` aggregates run minutes from `MachineStateLog`, total/good/scrap counts from `mes.ProductionReport`, and ideal cycle from `pps.RoutingOperation.cycle_seconds`. Zero-division safe (returns 0 instead of NaN). |
| **15.5 Alert & Anomaly Detection** | `AlertRule`, `AnomalyDetection` (auto `AD-00001`), `AlertNotification` | Detectors: threshold_high / threshold_low / range_outside / rate_of_change / missing_data / rolling-z-score / IQR / Western-Electric runs rule (heuristic-only — no `scikit-learn` dependency). `AlertRule` enforces XOR scope (exactly one of device_tag / scope_device / scope_asset). `cooldown_seconds` suppresses duplicate firings. `resolution_notes` are required at `resolved` / `false_positive` transitions per Lesson L-14. |

### Cross-module signal hooks

| # | From | Trigger | To | Idempotency key |
|---|---|---|---|---|
| 1 | `iot.IoTReading.post_save` | every reading | `iot.StreamMetric` (1-to-1 denorm refresh) | `device_tag` |
| 2 | `iot.IoTReading.post_save` | tag has `condition_point` set | `eam.ConditionReading` | `source_iot_reading` (OneToOne, [`apps/eam/migrations/0003_conditionreading_source_iot_reading_and_more.py`](apps/eam/migrations/0003_conditionreading_source_iot_reading_and_more.py)) |
| 3 | `iot.IoTReading.post_save` | matching active `iot.AlertRule` (with cooldown guard) | `iot.AnomalyDetection` | `(rule, source_reading)` |
| 4 | `iot.AnomalyDetection.post_save` | every detection | `iot.AlertNotification` (one row per channel) | `(detection, channel)` |
| 5 | `iot.AnomalyDetection.post_save` | severity ≥ high & rule channels include `mes_andon` | `mes.AndonAlert` | `source_anomaly` (OneToOne, [`apps/mes/migrations/0004_andonalert_source_anomaly.py`](apps/mes/migrations/0004_andonalert_source_anomaly.py)) |
| 6 | `iot.AnomalyDetection.post_save` | severity = critical & tag.condition_point set | `eam.FailurePrediction` | `source_anomaly` (OneToOne, same `eam.0003` migration as Hook 2) |
| 7 | `mes.ProductionReport.post_save` | report has work_order.production_order.product link | `iot.OEEPeriod` denorm refresh | `(asset, shift, period_date)` |
| 8 | `eam.DowntimeEvent.post_save` | every event with asset | `iot.MachineStateLog` (state='down') | `source_downtime` |

Reverse `pre_delete` counterparts paired for Hooks 2 / 5 / 6 / 8.

All eight hooks are live. The cross-app FKs that anchor Hooks 2 / 5 / 6 ship in `apps/eam/migrations/0003_*` and `apps/mes/migrations/0004_*` (additive, nullable, `on_delete=SET_NULL`). The signal handlers retain `hasattr()` guards as a defensive belt-and-braces so a partially-migrated environment still degrades gracefully.

### Key routes

See the [Screenshots / UI Tour](#screenshotsui-tour) routes table — every `/iot/...` endpoint is listed there with its purpose.

### Security flags

- **`DeviceBroker.password_hash`** — stop-gap stable token for v1 demos. Production deployments **must** rotate to KMS / Vault / SecretsManager-backed lookup before storing real broker credentials. The model-level WARNING comment and the form template footer both surface this.
- **`TwinStateAttribute.formula`** — evaluated by `services/twin._safe_eval`, a custom AST walker that whitelists only numeric literals, variable refs, the four arithmetic operators, parens, and `min / max / abs`. Lambdas, attribute access, function calls outside the whitelist, the `**` (power) operator, and any other Python construct raise `FormulaError`. **`eval()` and `exec()` are never called on user-supplied formulas.** Regression tests in [apps/iot/tests/test_services.py](apps/iot/tests/test_services.py) cover `__import__`, `exec`, `lambda`, attribute access, unknown function, and undefined-variable rejection.

### Out of scope for v1 (deferred to v2+)

- **Live broker integration** — `paho-mqtt`, `asyncua`, and `pymodbus` clients running as background workers. v1 uses the JSON / CSV bulk ingest endpoint at `/iot/readings/ingest/` to demonstrate the full cascade pipeline without external infrastructure.
- **ML-based anomaly detection** — `scikit-learn` `IsolationForest` / `LocalOutlierFactor` are deferred. The current heuristic detectors (rolling z-score, IQR, runs rule) cover the common cases and have zero deploy weight.
- **TimescaleDB / TSDB backend** — `IoTReading` rows are stored in MySQL like every other ledger. For high-throughput production deployments this is a known scaling ceiling.
- **Real-time WebSocket / SSE push to the dashboard** — the dashboard polls on page load; live push of new readings / anomalies via Channels is deferred.

---

## Module 16 — Business Intelligence & Analytics

Module 16 is implemented in [`apps/bi/`](apps/bi/) with full CRUD across all 5 sub-modules. **Read-mostly** over the rest of the platform — it never writes back into modules it sources data from. Every model is `TenantAwareModel`; cross-module access uses string FKs (`'mes.ProductionReport'`, `'cost.GrossMarginReport'`, etc.) so the app can be unmounted without breaking other modules.

### Sub-module 16.1 — Manufacturing KPI Dashboards

- **`KPIDefinition`** — tenant catalog of KPI recipes. `code` ∈ `oee` / `throughput` / `yield` / `scrap_rate` / `on_time_delivery` / `supplier_otd` / `gross_margin` / `energy_intensity` / `carbon_intensity` is the dispatch key into the [`KPI_REGISTRY`](apps/bi/services/kpi.py) in `services/kpi.py`. Carries `direction` (`higher_is_better` / `lower_is_better`), `target_value`, `warning_threshold`, `critical_threshold` — the [`classify_value`](apps/bi/services/kpi.py) helper maps a Decimal into `on_target` / `warning` / `critical` honoring direction.
- **`KPIDashboard`** — a named dashboard surface scoped to a tenant (optional `owner` user, `is_shared` flag). `default_period` ∈ `last_7d` / `last_30d` / `mtd` / `qtd` / `ytd` / `custom`, `auto_refresh_minutes`. Slug unique per `(tenant, slug)`.
- **`KPIWidget`** — a placement of a KPI on a dashboard with `chart_type` (`kpi_card` / `line` / `bar` / `donut` / `gauge` / `sparkline`), `scope_filter` JSON, `compare_to_previous` flag, `position`.
- **`KPISnapshot`** — materialized per-period rollup `(kpi_definition, period_start, period_end, scope_type, scope_pk)` so dashboard widgets render in O(1). Carries `value`, `prior_period_value`, `status`, `sample_size`, `computed_at`. `delta_vs_prior` + `delta_pct_vs_prior` properties for percentage-change display. `PROTECT` on `kpi_definition` (Lesson L-17).
- **KPI calculators** (pure functions in [`services/kpi.py`](apps/bi/services/kpi.py)): aggregate `iot.OEEPeriod` for OEE, `mes.ProductionReport` for throughput / yield / scrap, `procurement.SupplierMetricEvent` for OTD, `cost.GrossMarginReport` for gross margin, `utility.UtilityConsumption + mes.ProductionReport` for energy intensity, `utility.CarbonEmission + mes.ProductionReport` for carbon intensity. Each returns `(Decimal, sample_size)`; `refresh_snapshot()` upserts the matching `KPISnapshot` row.

### Sub-module 16.2 — Ad-Hoc Report Builder

- **`ReportDataSource`** — tenant catalog binding a slug to a Django `model_label` plus `allowed_fields` JSON. The slug must exist in the static [`REGISTERED_SOURCES`](apps/bi/services/registry.py) whitelist — 12 sources are registered: `production_orders`, `production_reports`, `non_conformance_reports`, `supplier_invoices`, `supplier_metric_events`, `utility_consumption`, `carbon_emissions`, `failure_predictions`, `oee_periods`, `stock_movements`, `gross_margin_reports`, `cogm_reports`.
- **`ReportDefinition`** — auto-numbered `RPT-00001`. Carries `data_source` FK, `created_by`, `is_shared`, optional `group_by_field`, `sort_field` + `sort_direction`, `row_limit`. Unique per `(tenant, name)`.
- **`ReportField`** — per-report column selection with `aggregation` ∈ `none` / `sum` / `avg` / `count` / `min` / `max` and `position` for column order.
- **`ReportFilter`** — per-report where-clause with `operator` ∈ `eq` / `ne` / `gt` / `gte` / `lt` / `lte` / `contains` / `startswith` / `endswith` / `in` / `between` / `isnull`. `between` requires `value_to`.
- **`ReportRun`** — auto-numbered `RR-00001` ledger of every execution with `status`, `row_count`, `duration_ms`, `parameters`, `result_preview` (first 50 rows, Decimal/date coerced to JSON).
- **Safe executor** ([`services/reports.execute_report`](apps/bi/services/reports.py)) — reads the report definition + children, validates **every** field name (project, filter, group_by, sort) against the source's `allowed_fields` whitelist via [`assert_field_allowed`](apps/bi/services/registry.py), then builds a `QuerySet.filter(...).values(...).annotate(...)` programmatically. Never builds raw SQL. Always applies `tenant=request.tenant`. Prevents SQL injection and field-disclosure attacks. Result rows are coerced to JSON-safe shapes before being persisted as `result_preview`.

### Sub-module 16.3 — Predictive Analytics

- **`PredictiveModel`** — heuristic prediction recipe. `code` ∈ `demand_forecast` (linear regression on `mes.ProductionReport.good_qty` per product), `failure_likelihood` (rolling failure rate on `eam.MaintenanceWorkOrder(wo_type='breakdown')`), `quality_trend` (slope on `qms.ControlChartPoint` rows), plus `scrap_drift` / `cost_drift` / `energy_drift` (alias to the linear-regression core for v1). Carries `lookback_days`, `forecast_horizon_days`, `parameters` JSON, `is_active`. Unique per `(tenant, code, name)`.
- **`PredictionRun`** — auto-numbered `PR-00001` with `status` (`queued` / `running` / `completed` / `failed` / `cancelled`). Cancellable while `queued` or `running`; reason required (Lesson L-14).
- **`PredictionResult`** — one row per (target, period) projected by a run with `target_type` ∈ `product` / `asset` / `supplier` / `spc_chart` / `cost_center` / `tenant`, `predicted_value`, `lower_bound`, `upper_bound`, `confidence_pct` (0–100). `PROTECT` on the parent run (L-17).
- **`TrendAnalysis`** — auto-numbered `TA-00001` sliding-window slope summary. Carries `source_metric`, `slope`, `intercept`, `r_squared` (0–1), `direction` ∈ `improving` / `steady` / `worsening`. Reusable across KPIs and SPC series.
- **Heuristics** (pure functions, [`services/predictions.py`](apps/bi/services/predictions.py)) — `linear_regression(values) → (slope, intercept, r_squared)`, `linear_regression_forecast(values, horizon)` with residual-standard-error confidence bands, `rolling_average(values, window)`, `rolling_failure_rate(event_dates, window_days, anchor)`, `naive_seasonal(values, period_length, horizon)`, `chart_trend(points) → (slope, r2, last, direction)`. **No NumPy / pandas / scikit-learn dependency** — every routine uses `decimal.Decimal` arithmetic so behaviour is platform-stable and deploy-light.

### Sub-module 16.4 — Tenant-Isolated Data Warehouse

- **`DataMart`** — auto-numbered `DM-00001`. Carries `code`, `name`, `source_definition` JSON (declares `model_label`, `group_by`, `measures`, optional `date_field` + `lookback_days`), `refresh_frequency` (`on_demand` / `hourly` / `daily` / `weekly` / `monthly`), `last_refreshed_at`, `last_row_count`, optional `row_level_security_field` for an additional scope beyond tenant.
- **`DataMartColumn`** — typed column metadata (`text` / `int` / `decimal` / `date` / `datetime` / `bool`), `is_dimension` / `is_measure` discriminator, `aggregation_hint`, `position`.
- **`DataMartSnapshot`** — one refresh marker with `snapshot_at`, `row_count`, `duration_ms`, `triggered_by` (`manual` / `schedule` / `signal` / `seed`). `PROTECT` on `data_mart` (L-17).
- **`DataMartRow`** — one materialized row carrying `row_data` (full column → value dict), `dimension_keys` (denormalized for fast filtering), `measure_total` (pre-computed scalar for sort/filter speed). Every row is `TenantAwareModel` → cross-tenant queries auto-filter via the default manager. Cross-tenant industry-average rows (when implemented) follow the [`apps/utility/`](apps/utility/) `tenant=NULL` + custom `for_tenant` manager pattern (D-10 lesson).
- **Refresh service** ([`services/datamart.refresh_mart`](apps/bi/services/datamart.py)) — one atomic transaction: reads `mart.source_definition`, executes the aggregation against the source model scoped to `mart.tenant`, deletes every prior `DataMartRow` for the mart, creates a fresh `DataMartSnapshot`, bulk-inserts new rows. Idempotent. Decimal / date / datetime values are JSON-coerced before storage.

### Sub-module 16.5 — Automated Report Distribution

- **`ReportSchedule`** — auto-numbered `SCH-00001`. Binds exactly one of `report` FK / `dashboard` FK (XOR enforced in the form). `frequency` ∈ `daily` / `weekly` / `monthly` / `custom`; custom requires a 5-field `cron_expression`. Carries `timezone_name`, `next_run_at`, `last_run_at`, `last_status`, `format` (`csv` / `xlsx` / `pdf_html` / `inline_email`), `status` (`active` / `paused` / `disabled`), `disabled_reason`. Disable transition requires a reason (Lesson L-14).
- **`ReportRecipient`** — per-schedule recipient row with `email`, optional `user` FK + `name`, `notify_on_failure` flag. Unique per `(tenant, schedule, email)`.
- **`ReportExport`** — auto-numbered `EXP-00001` rendered artifact with `file` FileField (allowlist `.csv .xlsx .pdf .html`, 25 MB cap per Lesson L-22), `row_count`, `file_size_bytes`, `status` (`pending` / `rendering` / `ready` / `failed` / `expired`), `generated_at`, `generated_by`.
- **`ReportDelivery`** — auto-numbered `DLV-00001` ledger of every delivery attempt with `status` (`pending` / `sent` / `failed` / `cancelled` / `bounced`), `attempted_at`, `delivered_at`, `error_message`, `message_id`. `PROTECT` on `schedule`, `recipient`, `export` (L-17).
- **Distribution service** ([`services/scheduler.py`](apps/bi/services/scheduler.py)) — `due_schedules(now)` returns schedules whose `next_run_at <= now`; `run_schedule(schedule, now)` renders the bound report (or dashboard widget snapshot CSV), persists a `ReportExport`, fans out `ReportDelivery` rows, sends emails via Django `send_mail`, and advances `next_run_at` from the frequency. Idempotent at second-precision: a `last_run_at` within 1 s of `next_run_at` is treated as already-run. The management command `run_report_schedules` calls `sweep_due()`; intended for cron / Windows Task Scheduler — see [Management Commands](#management-commands).

### Cross-module hooks

| # | From | Trigger | To | Idempotency |
|---|---|---|---|---|
| 1 | `cost.AccountingPeriod.post_save (status='closed')` | period closes | refresh every active `KPISnapshot` for the period at tenant scope via [`services.kpi.refresh_snapshot`](apps/bi/services/kpi.py) | `(kpi_definition, period_start, scope_type, scope_pk)` |

Read-only against every other module — Module 16 **never writes back** into MES, IoT, Cost, Utility, Procurement, EAM, MRP, Inventory, or QMS.

### Audit signals

[`apps/bi/signals.py`](apps/bi/signals.py) wires the `_make_audit_handler` + `AUDITED_MODELS` factory used by IoT / Utility / EAM / Labor / Cost. **All factory-registered handlers connect with `weak=False` and a unique `dispatch_uid` per model** (Lesson L-18). Audited models: `KPIDefinition`, `KPIDashboard`, `KPIWidget`, `ReportDefinition`, `ReportRun`, `PredictiveModel`, `PredictionRun`, `DataMart`, `ReportSchedule`, `ReportDelivery`. Audit actions follow `bi.<ModelName>.<created|updated>`. The audit handler swallows exceptions (best-effort) so a BI save never fails because of audit-log issues — failures log a `WARNING` instead.

### Validation guards (apply Lessons L-01, L-02, L-14, L-17, L-22)

- L-01: every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, ...)` uniqueness check — `KPIDefinitionForm` (on `code`), `KPIDashboardForm` (on `slug`), `ReportDataSourceForm` (on `code`, also gated against the static `REGISTERED_SOURCES` whitelist), `ReportDefinitionForm` (on `name`), `ReportFilterForm` (between operator requires `value_to`), `PredictiveModelForm` (on `(code, name)`), `DataMartForm` (on `code` + `source_definition` JSON shape), `DataMartColumnForm` (on `(data_mart, code)`, also rejects `is_dimension=True` AND `is_measure=True`), `ReportScheduleForm` (XOR `report` / `dashboard`, on `name`, custom-frequency cron required), `ReportRecipientForm` (on `(schedule, email)`).
- L-02: every Decimal carries explicit validators — `target_value` / `warning_threshold` / `critical_threshold` (signed), `value` / `prior_period_value` (signed), `predicted_value` / `lower_bound` / `upper_bound` (signed), `confidence_pct` (0–100), `r_squared` (0–1), `slope` / `intercept` (signed).
- L-14: per-workflow required reasons — `PredictionRunCancelForm.clean_cancellation_reason()`, `ReportScheduleDisableForm.clean_disabled_reason()`.
- L-17: `PROTECT` on audit-trail children — `KPISnapshot.kpi_definition`, `KPIWidget.kpi_definition`, `ReportDefinition.data_source`, `ReportRun.report`, `PredictiveModel`-on-`PredictionRun`, `PredictionResult.run`, `DataMartSnapshot.data_mart`, `DataMartRow.snapshot`, `ReportSchedule.report` / `ReportSchedule.dashboard`, `ReportDelivery.schedule` / `.recipient` / `.export`.
- L-22: `ReportExportForm.clean_file()` enforces `.csv / .xlsx / .pdf / .html` allowlist + 25 MB upload cap.

### RBAC (L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, all list pages, detail pages, run-own-report | Authenticated tenant user | `TenantRequiredMixin` |
| KPI / Dashboard / Widget / Report / Data Source / Predictive / Mart / Schedule / Recipient CRUD; refresh + run-now + pause + resume + disable + cancel + export download | Tenant admin | `TenantAdminRequiredMixin` |

### Test suite

Run with `pytest apps/bi/tests/` — **93 tests, ~110 s** across [`test_models.py`](apps/bi/tests/test_models.py) (auto-numbering for RPT / RR / PR / TA / DM / SCH / EXP / DLV, snapshot delta math, unique-per-tenant constraints, cross-tenant slug reuse, workflow predicates), [`test_forms.py`](apps/bi/tests/test_forms.py) (L-01 dedup, L-14 required reasons, XOR Report-or-Dashboard, custom-cron requirement, registry-gated data-source code), [`test_services.py`](apps/bi/tests/test_services.py) (registry whitelist accept/reject, KPI classification both directions, linear regression on flat / perfect / short series, rolling average, chart trend improving / worsening / steady, naive_seasonal short-input fallback), [`test_signals.py`](apps/bi/tests/test_signals.py) (L-18 `dispatch_uid` presence, audit emit on save), [`test_views.py`](apps/bi/tests/test_views.py) (HTTP CRUD smoke on every list URL + 3 create handlers + KPI refresh), [`test_security.py`](apps/bi/tests/test_security.py) (anonymous-redirect on 14 list URLs, multi-tenant IDOR cross-tenant 404 on 6 detail URLs, RBAC matrix on 4 admin-only endpoints + staff-allowed list pages), [`test_seeder.py`](apps/bi/tests/test_seeder.py) (seed_bi creates the expected row counts, is idempotent across two runs, and re-populates after `--flush`).

### Out of scope (deferred to v2+)

- **Drag-and-drop report designer** — v1 ships a form-based builder. JS designer (Power BI / Looker style) is v2.
- **scikit-learn / ML models** — v1 is pure-Python heuristics. v2 can plug `IsolationForest` / `LinearRegression` behind the same `PredictiveModel.code` registry without schema change.
- **Real cron daemon** — `run_report_schedules` is a management command intended for cron / Task Scheduler. Celery / RQ workers are out of scope.
- **Real-time push to dashboards** — dashboards poll on `auto_refresh_minutes`; WebSocket / SSE is deferred.
- **Cross-tenant industry-average aggregator** — `DataMartRow(tenant=NULL)` rows are modelled but the aggregation command is gated on ≥ 5 production tenants (k-anonymity threshold), matching the [`apps/utility/`](apps/utility/) deferral.
- **True server-side PDF rendering** — exports use HTML "print to PDF" via browser print. WeasyPrint / wkhtmltopdf is v2.
- **Live data warehouse to external BI tool** — Tableau / Power BI / Looker connectors are v2. `DataMartRow` rows are Django-resident; export is via CSV / xlsx only.

---

## Module 17 — Sales & Customer Order Management

The customer-facing counterpart to Module 9 (Procurement). Sales lives in [apps/sales/](apps/sales/) and is mounted at `/sales/`.

### Sub-modules

| # | Sub-module | What you get |
|---|---|---|
| 17.1 | Customer Master & CRM Lite | Customer profiles, contacts, communication log, document repository, customer categories, price lists with tier breaks |
| 17.2 | Sales Order Processing | Auto-numbered SO with full draft → submitted → credit_check → confirmed → in_production → fulfilled → invoiced → closed workflow; immutable revisions; per-line make-to-order flag |
| 17.3 | Order Promising & ATP/CTP | Available-to-Promise (on-hand stock + open PO arrivals − committed) and Capable-to-Promise (BOM + routing capacity walk); pure-read snapshots |
| 17.4 | Delivery Scheduling & Dispatch | Shipments + lines, delivery routes, Proof-of-Delivery, sales invoices auto-generated from shipments, signal-driven `inventory.StockMovement(shipment_out)` emission |
| 17.5 | Customer Portal | `/sales/portal/...` self-service for users whose `customer_company` FK is set; sees their own orders, shipment tracking, and invoices only |

### Models

- **17.1** — `CustomerCategory` (hierarchical), `PriceList` (auto `PL-00001`), `PriceListItem` (tier breaks + effective window), `Customer` (auto `CUST-00001`), `CustomerContact`, `CommunicationLog` (auto `COMM-00001`, 24-hour edit lock), `CustomerDocument` (25 MB cap, L-22 allowlist).
- **17.2** — `SalesOrder` (auto `SO-00001`), `SalesOrderLine` (denorm money columns + qty_promised / qty_shipped / qty_invoiced denorms + `is_make_to_order` flag + `source_production_order` FK), `SalesOrderRevision` (immutable JSON snapshot), `SalesOrderApprovalLog` (append-only).
- **17.3** — `ATPCalculation` (auto `ATP-00001`), `CTPCalculation` (auto `CTP-00001`), `OrderPromise` (1-to-1 with SO line; `stock / production / mixed / partial / unfulfillable`).
- **17.4** — `DeliveryRoute` (auto `ROUTE-00001`), `Shipment` (auto `SHP-00001`), `ShipmentLine`, `ProofOfDelivery` (auto `POD-00001`), `SalesInvoice` (auto `SINV-00001`), `SalesInvoiceLine`.
- **17.5** — reuses `accounts.User` with new optional `customer_company` FK + `'customer'` role choice, mirroring the existing `supplier_company` / `'supplier'` pattern.

### Services (pure functions, no ORM at module scope)

- [`services/numbering.py`](apps/sales/services/numbering.py) — atomic auto-code helper.
- [`services/pricing.py`](apps/sales/services/pricing.py) — `resolve_price(customer, product, qty, on_date)` walks customer PL → tenant default PL → product list_price.
- [`services/credit.py`](apps/sales/services/credit.py) — `check_credit(customer, additional_amount)` enforces blacklist + status + over-credit-limit.
- [`services/workflow.py`](apps/sales/services/workflow.py) — race-safe SO workflow with conditional UPDATE.
- [`services/atp.py`](apps/sales/services/atp.py) — `compute_atp` reads on-hand + open PO arrivals − committed open SO; never writes.
- [`services/ctp.py`](apps/sales/services/ctp.py) — `compute_ctp` walks released routing + work-center capacity to estimate completion; never alters the schedule.
- [`services/shipping.py`](apps/sales/services/shipping.py) — `pick / pack / dispatch / confirm_delivery / cancel_shipment` with conditional UPDATE.
- [`services/invoicing.py`](apps/sales/services/invoicing.py) — `generate_invoice_from_shipment` (idempotent on `(shipment_id)`) + `issue_invoice` + `mark_invoice_paid`. Both transition services adjust `Customer.credit_used` (issue → add, paid → subtract) via conditional UPDATE so the denorm is touched at most once per real status change.

### Cross-module hooks (apps/sales/signals.py)

| # | Trigger | Effect | Idempotency key |
|---|---|---|---|
| 1 | `SalesOrder.post_save(status='confirmed')` | For each `SalesOrderLine.is_make_to_order=True` that hasn't already spawned one, draft a `pps.ProductionOrder` | `pps.ProductionOrder.source_sales_line` FK |
| 2 | `Shipment.post_save(status='delivered')` | Emit one `inventory.StockMovement(type='shipment_out')` per `ShipmentLine` | `StockMovement.source_shipment_line` FK |
| 3 | `Shipment.pre_delete` | Reverse every shipment_out movement before the row vanishes | same key |

> The previous post-save signal that decremented `Customer.credit_used` on `SalesInvoice.status='paid'` was removed during the D-01 → D-15 defect remediation pass — it re-fired on every save of an already-paid invoice and double-counted. Credit increments/decrements now live in [`services/invoicing.py`](apps/sales/services/invoicing.py) inside conditional-UPDATE guards so they run exactly once per real transition.

These additions are accompanied by:

- `apps/pps/ProductionOrder.source_sales_line` FK (nullable, `SET_NULL`).
- `apps/inventory/StockMovement.source_shipment` + `.source_shipment_line` FKs (nullable, `SET_NULL`) plus a new `'shipment_out'` choice in `MOVEMENT_TYPE_CHOICES` and matching reversal entry in `apps/inventory/services/movements.reverse_movement` swap dict.
- `apps/accounts/User.customer_company` FK + `'customer'` and `'sales'` role choices.

### Customer Portal scoping

Every view in the 17.5 group filters by `request.user.customer_company` BEFORE `request.tenant` — a portal user from one customer cannot see another customer's orders, shipments, or invoices even within the same tenant. Mirrors the existing `procurement.Supplier` / `supplier_company` portal pattern in [`apps/procurement/`](apps/procurement/).

### Routes (UI tour)

| Route | What you'll see |
|-------|----------------|
| `/sales/` | Sales dashboard — KPI cards (customers, communications, price lists) + recent activity |
| `/sales/customers/` | Customer list with status / class / category filters; Add Customer button |
| `/sales/customers/<pk>/` | Customer detail with Contacts / Communications / Documents tabs and credit panel |
| `/sales/categories/` | Customer category list with hierarchical parent display |
| `/sales/pricelists/` · `/sales/pricelists/<pk>/` | Price list list + detail with inline item CRUD |
| `/sales/communications/` | Global communication log with type / direction / status filters |
| `/sales/orders/` | Sales order list with status / priority / credit-hold / customer filters |
| `/sales/orders/<pk>/` | SO detail with line CRUD, totals tfoot, workflow sidebar (Submit / Confirm / Release credit hold / Hold / Resume / Cancel / Revise) and Workflow Log / Revisions tabs |
| `/sales/atp/` · `/sales/atp/new/` · `/sales/atp/<pk>/` | ATP request form + history + per-calc breakdown |
| `/sales/ctp/` · `/sales/ctp/new/` · `/sales/ctp/<pk>/` | CTP request form + history + operation trace |
| `/sales/shipments/` · `/sales/shipments/<pk>/` | Shipment list + detail with line CRUD, workflow buttons (pick / pack / dispatch / mark delivered / cancel) and POD link |
| `/sales/shipments/<pk>/pod/` | Record proof of delivery (signature + photo, L-22 25 MB cap) |
| `/sales/routes/` · `/sales/routes/<pk>/` | Delivery route list + detail with grouped shipments |
| `/sales/invoices/` · `/sales/invoices/<pk>/` | Sales invoice list + detail with Issue / Mark Paid actions |
| `/sales/invoices/from-shipment/<shipment_pk>/` | Idempotent draft-invoice generator from a delivered shipment |
| `/sales/portal/` | Customer-portal dashboard (only when `request.user.customer_company` is set) |
| `/sales/portal/orders/` · `/sales/portal/orders/<pk>/` | Customer-scoped order list + detail |
| `/sales/portal/shipments/<pk>/tracking/` | Visual stepper tracking page |
| `/sales/portal/invoices/` · `/sales/portal/invoices/<pk>/` | Customer-scoped invoice list + detail |
| `/sales/portal/documents/<pk>/download/` | Auth-gated, customer-scoped document download |

### Test suite

Run with `pytest apps/sales/tests/` — **~80+ test cases** spanning model auto-numbering and tenant isolation ([`test_models.py`](apps/sales/tests/test_models.py)), form L-22 file validation ([`test_forms.py`](apps/sales/tests/test_forms.py)), CRUD smoke + filter regression ([`test_views.py`](apps/sales/tests/test_views.py)), cross-tenant IDOR + 24-hour comm lock ([`test_security.py`](apps/sales/tests/test_security.py)), seed_sales idempotency ([`test_seeder.py`](apps/sales/tests/test_seeder.py)), full SO workflow + credit-check + MTO auto-PO signal + revision snapshots ([`test_workflow_so.py`](apps/sales/tests/test_workflow_so.py)), ATP edge cases incl. committed-SO subtraction ([`test_services_atp.py`](apps/sales/tests/test_services_atp.py)), CTP with / without released routing ([`test_services_ctp.py`](apps/sales/tests/test_services_ctp.py)), shipment workflow + StockMovement signal idempotency ([`test_services_shipping.py`](apps/sales/tests/test_services_shipping.py)), invoice generation idempotency + paid → credit_used denorm ([`test_services_invoicing.py`](apps/sales/tests/test_services_invoicing.py)), and portal scoping (cross-customer 404, unlinked user redirect) ([`test_portal.py`](apps/sales/tests/test_portal.py)).

### Out of scope (deferred per Module-17 plan)

- **`SalesQuotation`** (Quote → SO conversion) — deferred per plan §10. Direct SO entry only.
- **EDI / carrier API integration** (FedEx / UPS / DHL) — `carrier_name` + `tracking_number` remain free text.
- **Tax engine** — line `tax_pct` only; no jurisdiction-aware engine.
- **Multi-currency FX revaluation** — `currency` field is stored but no conversion.

---

## Module 18 — Returns & RMA Management

The reverse-logistics counterpart to Modules 8 (Inventory) + 9 (Procurement) + 17 (Sales). RMA lives in [apps/rma/](apps/rma/) and is mounted at `/rma/`.

### Sub-modules

| # | Sub-module | What you get |
|---|---|---|
| 18.1 | RMA Request & Authorization | Customer return initiation, approval workflow (`draft → submitted → approved | rejected → cancelled`), auto-numbered RMA + append-only approval audit log |
| 18.2 | Returns Receiving & Inspection | Physical receipt, per-line condition assessment, disposition routing — auto-emits inventory movement (restock) or auto-drafts a repair order (repair / refurbish) |
| 18.3 | Repair & Refurbishment Tracking | Rework tickets with workflow, append-only parts + labor ledgers, computed cost roll-up, signal-mirrored `labor.LaborBooking` |
| 18.4 | Warranty Management | Reusable policy templates, per-unit registrations with computed end date + expiry-soon highlight, claim workflow with replacement-SO auto-draft |
| 18.5 | Returns Analytics | Tenant catalogs of failure modes + root causes, per-line analysis with optional supplier attribution, supplier chargeback workflow |

### Models

- **18.1** — `RMAReason` (catalog, unique_together(tenant, name)), `RMARequest` (auto `RMA-00001`), `RMALine` (auto line_no, decimal validators), `RMAApproval` (append-only workflow audit log).
- **18.2** — `ReturnReceipt` (auto `RR-00001`), `ReturnReceiptLine` (condition + disposition enums + `disposition_done` idempotency latch + `stock_movement` FK).
- **18.3** — `RepairOrder` (auto `REP-00001`, denorm `actual_cost` + `labor_minutes`), `RepairPartUsage` (computed `line_cost` in `save()`), `RepairLaborLog` (computed `labor_cost` in `save()` + `labor_booking` FK).
- **18.4** — `WarrantyPolicy` (auto `WP-00001`, coverage enum + duration_months), `WarrantyRegistration` (auto `WR-00001`, computed `end_date` + `is_expiring_soon` property + `days_remaining`), `WarrantyClaim` (auto `WC-00001`, `replacement_order` FK).
- **18.5** — `FailureMode` (catalog), `RootCauseCategory` (catalog with responsible_area), `ReturnAnalysis` (auto `RA-00001`), `SupplierChargeback` (auto `SCB-00001`).

### Services (pure functions, no ORM at module scope)

- [`services/numbering.py`](apps/rma/services/numbering.py) — atomic auto-code helper (mirrors the sales pattern).
- [`services/warranty.py`](apps/rma/services/warranty.py) — `add_months` (month-end-clamped, no `dateutil`), `compute_warranty_end`, `is_under_warranty`.
- [`services/disposition.py`](apps/rma/services/disposition.py) — `route_disposition(value)` → `restock / repair_ticket / supplier_return / none` classifier.
- [`services/repair.py`](apps/rma/services/repair.py) — `recompute_repair_costs(repair_order)` aggregates the parts + labor ledgers onto the parent denorms (sole writer).
- [`services/chargeback.py`](apps/rma/services/chargeback.py) — `can_transition` / `apply_transition` enforce legal forward transitions; illegal jumps raise `ValueError`.

### Cross-module hooks (apps/rma/signals.py)

| # | Trigger | Effect | Idempotency key |
|---|---|---|---|
| 1 | `RMARequest.post_save(status='approved')` | Draft one `ReturnReceipt` for the approved RMA | One `ReturnReceipt.rma` FK per RMA |
| 2 | `ReturnReceiptLine.post_save(disposition='restock', not disposition_done)` | Emit `inventory.StockMovement(type='receipt')` into the receipt's warehouse | `disposition_done` latch + `stock_movement` FK |
| 3 | `ReturnReceiptLine.post_save(disposition in {repair, refurbish}, not disposition_done)` | Draft a `RepairOrder` for the receipt line | `RepairOrder.receipt_line` FK + `disposition_done` latch |
| 4 | `RepairLaborLog.post_save` | Mirror into `labor.LaborBooking(kind='indirect')` + refresh repair cost rollup | `RepairLaborLog.labor_booking` FK |
| 5 | `RepairPartUsage.post_save` / `pre_delete` | Refresh `RepairOrder.actual_cost` + `labor_minutes` denorms (via `on_commit` on delete to skip cascade-from-parent recomputes) | Single writer in `services/repair.recompute_repair_costs` |
| 6 | `WarrantyClaim.post_save(status='approved', resolution='replace')` | Draft a `sales.SalesOrder` replacement for the registered customer | `WarrantyClaim.replacement_order` FK |

Every handler is module-level (L-18 safe), carries a `dispatch_uid='rma.<action>'`, and best-effort logs failures at WARNING via `logger.warning(..., exc_info=True)` (L-23) so a downstream module's misconfiguration never blocks the RMA workflow.

### Time-driven status (L-21)

`WarrantyRegistration` has the time-driven terminal state `expired`. The daily `expire_warranties` management command race-safe-flips `active → expired` past `end_date` via a conditional `update()`, is idempotent on re-run, and supports `--dry-run` + `--tenant <slug>`.

### Routes (UI tour)

| Route | What you'll see |
|-------|----------------|
| `/rma/` | RMA dashboard — KPI cards (open RMAs, pending approval, receipts inspecting, open repairs, active warranties, open chargebacks) + recent RMAs + open repair orders + warranties expiring soon |
| `/rma/reasons/` | RMA reason code catalog with category + active filters |
| `/rma/requests/` · `/rma/requests/<pk>/` | RMA list with status / action / customer filters + detail with line CRUD + authorization log + workflow sidebar (Submit / Approve with notes / Reject with required reason / Cancel) |
| `/rma/receipts/` · `/rma/receipts/<pk>/` | Return receipt list + detail with inline inspection-line CRUD, disposition routing status badge per line, and workflow (Start Inspection / Complete / Cancel) |
| `/rma/repairs/` · `/rma/repairs/<pk>/` | Repair order list with status / type filters + detail with parts ledger, labor ledger (with booking badge), cost roll-up panel, and workflow (Start / Hold / Resume / Complete with required resolution notes / Cancel) |
| `/rma/warranty/policies/` | Warranty policy catalog with coverage filter |
| `/rma/warranty/registrations/` · `/rma/warranty/registrations/<pk>/` | Registrations with status + "expiring within 30 days" filter (yellow row tint) + detail with claims tab |
| `/rma/warranty/claims/` · `/rma/warranty/claims/<pk>/` | Claim list + detail with workflow (Validate / Approve / Reject with required reason / Mark Fulfilled) and replacement-SO banner when auto-drafted |
| `/rma/analytics/failure-modes/` · `/rma/analytics/root-causes/` | FMEA-style classification catalogs |
| `/rma/analytics/analyses/` · `/rma/analytics/analyses/<pk>/` | Return-analysis list (filter by failure mode / root cause) + detail with supplier-chargeback tab |
| `/rma/analytics/chargebacks/` · `/rma/analytics/chargebacks/<pk>/` | Chargeback list with status filter + amount total + detail with status-workflow buttons (only legal next states shown) |

### RBAC + multi-tenancy

Every view filters by `request.tenant` first. Workflow + delete mutations are guarded by the `@tenant_admin_required` decorator (L-10) — non-admin staff get a flash error and a redirect; the underlying state never changes. The RBAC matrix is asserted across 5 high-value endpoints (submit RMA, approve RMA, delete RMA, complete repair, transition chargeback) in [`test_security.py`](apps/rma/tests/test_security.py) along with cross-tenant IDOR (404 on every detail URL) and anonymous-redirect on every list URL.

### Test suite

Run with `pytest apps/rma/tests/` — **93 tests** spanning auto-numbering + computed fields + workflow helpers + validator regression ([`test_models.py`](apps/rma/tests/test_models.py)), L-01 `clean()` duplicate-check on every tenant catalog + tenant-scoped FK queryset isolation ([`test_forms.py`](apps/rma/tests/test_forms.py)), pure-function services (warranty period math incl. month-end clamping, disposition routing, repair cost rollup idempotency, chargeback transition guards) ([`test_services.py`](apps/rma/tests/test_services.py)), all 6 cross-module signal hooks + idempotency on re-save (incl. the `on_commit` rollup path which uses `@pytest.mark.django_db(transaction=True)`) ([`test_signals.py`](apps/rma/tests/test_signals.py)), full CRUD smoke + RMA submit/approve/reject workflow + repair complete with required resolution notes + chargeback transition + filter regression ([`test_views.py`](apps/rma/tests/test_views.py)), multi-tenant IDOR + RBAC matrix + anonymous-redirect ([`test_security.py`](apps/rma/tests/test_security.py)), and `seed_rma` idempotency + `--flush` consistency + `expire_warranties` dry-run safety ([`test_seeder.py`](apps/rma/tests/test_seeder.py)).

### Out of scope (deferred)

- **Customer-facing RMA self-service portal** — internal-only in v1; the sales-portal pattern can be replicated later (`request.user.customer_company`-scoped views).
- **EDI / carrier API integration for return labels** — `carrier_name` + `tracking_number` on `ReturnReceipt` remain free text.
- **Automated refund posting to `cost` / accounting** — refund amounts and chargeback amounts are tracked but not journaled.

---

## Module 19 — Document & Knowledge Management

The controlled-document backbone of the platform. DMS lives in [apps/dms/](apps/dms/) and is mounted at `/dms/`.

### Sub-modules

| # | Sub-module | What you get |
|---|---|---|
| 19.1 | Controlled Document Repository | Hierarchical category catalog, `Document` master with 10-type taxonomy, append-only `DocumentVersion` chain with application-level check-in/check-out optimistic lock, per-document RBAC overrides via `DocumentAccessRule` (XOR User / Department / Position) |
| 19.2 | SOP & Work Instruction Authoring | Reusable `DocumentTemplate` skeletons with `{{placeholder}}` body + typed `TemplateField` rows; `MediaAttachment` (image / video / audio / pdf, http(s)-only embed URLs, 25 MB cap + allowlist) |
| 19.3 | Document Approval Workflows | Multi-stage `ApprovalWorkflow` with per-stage `approver_role` + `min_approvals` + `requires_signature`; `DocumentApprovalRequest` walks the stages; append-only `ApprovalAction` log; **immutable `DocumentSignature` (FDA 21 CFR Part 11)** with `pre_save` UPDATE rejection + admin readonly enforcement |
| 19.4 | Training Document Assignment | `DocumentAssignment` campaigns with XOR-fan-out `AssignmentTarget` (role / department / position / employee / user); `ReadAcknowledgment` with typed-name e-sig pinned to the released version; user-facing "My Acknowledgments" view |
| 19.5 | Archive & Retention Policy | Reusable `RetentionPolicy` (years + archive / soft_delete / hard_delete action); `DocumentArchive` with restore workflow; `LegalHold` M2M pinning Documents + signal-driven `is_locked` cascade |

### Models (17 total)

- **19.1** — `DocumentCategory` (unique_together(tenant,code)), `Document` (auto `DOC-00001`, status `draft → in_review → approved → effective → superseded → archived`), `DocumentVersion` (status `draft → under_review → released → superseded`, `checked_out_by` lock, 25 MB FileField with allowlist), `DocumentAccessRule` (role + XOR User/Department/Position).
- **19.2** — `DocumentTemplate` (auto `TPL-00001`), `TemplateField` (typed; text / textarea / number / date / select / boolean), `MediaAttachment` (5 media types + http(s)-only `video_url`).
- **19.3** — `ApprovalWorkflow`, `ApprovalStage` (stage_no + min_approvals + requires_signature), `DocumentApprovalRequest` (auto `AR-00001`), append-only `ApprovalAction`, immutable `DocumentSignature`.
- **19.4** — `DocumentAssignment` (auto `DA-00001`), `AssignmentTarget` (XOR role/dept/position/employee/user), `ReadAcknowledgment` (auto `ACK-00001`, unique on `(assignment, acknowledger, document_version)`).
- **19.5** — `RetentionPolicy` (auto `RP-00001`), `DocumentArchive` (auto `ARC-00001`, status `archived → restored → purged`), `LegalHold` (auto `LH-00001`, status `active → released`, M2M `documents`).

### Services (pure / single-writer)

- [`services/numbering.py`](apps/dms/services/numbering.py) — atomic auto-code helper (mirrors the rma/sales pattern).
- [`services/checkout.py`](apps/dms/services/checkout.py) — `check_out` / `check_in` with conditional `UPDATE ... WHERE checked_out_by IS NULL` so two simultaneous check-outs cannot both win. Admins can force-release.
- [`services/approval.py`](apps/dms/services/approval.py) — `current_stage` / `advance_stage` walk the ordered `ApprovalStage` rows, return `None` to signal final approval.
- [`services/retention.py`](apps/dms/services/retention.py) — `compute_retention_until` (month-end-clamped, no `dateutil`), `is_due_for_archive`.
- [`services/legal_hold.py`](apps/dms/services/legal_hold.py) — `apply_hold` / `release_hold` (re-evaluates `is_locked` honoring any other still-active hold).
- [`services/assignment.py`](apps/dms/services/assignment.py) — `expected_users_for` / `pending_users_for` expand `AssignmentTarget` rows into a deduplicated set of Users.

### Cross-module signal hooks (apps/dms/signals.py)

| # | Trigger | Effect | Idempotency |
|---|---|---|---|
| 1 | `DocumentVersion.post_save(status='released')` | Supersede prior released versions on the same doc + bump `Document.current_version` | Re-save = no-op (status already superseded) |
| 2 | `DocumentApprovalRequest.post_save(status='approved')` | Flip `Document.status='effective'` + set `effective_date` | Skipped if Document already effective |
| 3 | `LegalHold_documents.m2m_changed(post_add)` (when hold is active) | Set `Document.is_locked=True` on every added doc | Direct conditional UPDATE |
| 4 | `LegalHold_documents.m2m_changed(post_remove)` | Re-evaluate `Document.is_locked`: clear unless another active hold still references the doc | Per-doc check against remaining active holds |
| 5 | `Document.post_save` / `RetentionPolicy.post_save` | Recompute `Document.retention_until` via `services/retention.compute_retention_until` | Compares `expected != current` before writing |
| 6 | `DocumentSignature.pre_save` (UPDATE only) | Raise `PermissionError` (FDA 21 CFR Part 11 immutability) | Insert always allowed; any field change on an existing row blocked |
| 7 | `Document.pre_delete` | Raise `PermissionError` when `is_locked=True` | Last-line defence beyond the view layer guard |

Every handler is module-level (L-18 safe), carries a `dispatch_uid='dms.<action>'`, and best-effort logs failures at WARNING via `logger.warning(..., exc_info=True)` (L-23).

### Time-driven status (L-21)

`Document` has the time-driven terminal state `archived`. The daily `archive_due_documents` management command race-safe-flips `effective → archived` past `retention_until` via a conditional `update()`, skips any Document under an active legal hold, supports `--dry-run` + `--tenant <slug>`, and emits one `DocumentArchive` row per flip. Schedule daily via cron / Task Scheduler.

`expire_assignments` is the companion read-only reporter — it surfaces `DocumentAssignment` rows past `due_date` with no full acknowledgment but does NOT mutate state (an overdue ask is still a valid ask).

### Routes (UI tour)

| Route | What you'll see |
|-------|----------------|
| `/dms/` | DMS dashboard — KPI cards (total docs, in_review, pending approvals, my pending acks, active legal holds, docs expiring ≤30d) + recent docs + open approval requests + my pending acks |
| `/dms/categories/` and CRUD | Document category catalog with hierarchical parent display |
| `/dms/documents/` | Document list with search + doc_type + status + category filters |
| `/dms/documents/<pk>/` | Document detail with Versions / Access Rules / Approvals / E-Signatures / Assignments tabs and check-in/check-out + release + archive workflow buttons |
| `/dms/documents/new/` · `/<pk>/edit/` · `/<pk>/delete/` | Document CRUD (delete refused when `is_locked`) |
| `/dms/documents/<pk>/submit/` · `/archive/` | POST — submit-for-review / archive workflow |
| `/dms/documents/<doc_pk>/versions/new/` · `/versions/<pk>/edit/` · `/versions/<pk>/delete/` | DocumentVersion CRUD with 25 MB FileField cap + extension allowlist |
| `/dms/versions/<pk>/check-out/` · `/check-in/` · `/release/` · `/download/` | POST — optimistic-lock check-in/check-out + release + auth-gated download |
| `/dms/documents/<doc_pk>/access/new/` · `/access/<pk>/delete/` | DocumentAccessRule CRUD (XOR User / Department / Position) |
| `/dms/templates/` and CRUD | Document template catalog with inline TemplateField CRUD |
| `/dms/versions/<version_pk>/media/new/` · `/media/<pk>/delete/` | MediaAttachment CRUD per version |
| `/dms/workflows/` and CRUD | ApprovalWorkflow with inline ApprovalStage CRUD |
| `/dms/approvals/` and CRUD | DocumentApprovalRequest list / detail with per-stage action form |
| `/dms/approvals/<pk>/action/` | POST — record approve / reject / return-for-revision action; final approval flips Document to effective + creates a DocumentSignature when the stage requires it |
| `/dms/approvals/<pk>/cancel/` | POST — cancel an open approval request |
| `/dms/assignments/` and CRUD | DocumentAssignment list / detail with inline AssignmentTarget XOR fan-out + ack ledger |
| `/dms/assignments/<pk>/ack/` | POST — record typed-name acknowledgment of the current released version |
| `/dms/assignments/<pk>/complete/` · `/cancel/` | POST — admin assignment workflow |
| `/dms/my-acknowledgments/` | Personal landing page — pending acks for the current user across the tenant |
| `/dms/retention/policies/` and CRUD | Retention policy catalog |
| `/dms/retention/archives/` · `/<pk>/` · `/<pk>/restore/` | DocumentArchive list / detail with admin restore (L-14 required notes) |
| `/dms/retention/legal-holds/` and CRUD + `/<pk>/release/` | LegalHold management; create / edit immediately cascade `Document.is_locked`; release requires L-14 release notes |

### RBAC + multi-tenancy

Every view filters by `request.tenant` first. Workflow + delete mutations are guarded by `@tenant_admin_required` (L-10) — non-admin staff get a flash error and a redirect; the underlying state never changes. Acknowledgment endpoints are per-user (every logged-in user can ack their own assignments). `DocumentSignature` rows are insert-only — UPDATE attempts raise `PermissionError` at the model layer (`pre_save` signal) and admin `readonly_fields = '__all__'`.

### Test suite

Run with `pytest apps/dms/tests/` — **116 tests** spanning auto-numbering + computed fields + L-22 validators ([`test_models.py`](apps/dms/tests/test_models.py)), L-01 `clean()` duplicate-check on every tenant catalog + L-22 file caps + XOR validators (access rule / target) + L-14 per-workflow required (legal hold release notes, archive restore notes, approval reject notes) ([`test_forms.py`](apps/dms/tests/test_forms.py)), pure-function services (checkout optimistic-lock incl. self-idempotency + admin override, retention math with leap-day clamp, legal-hold cascade with multi-hold safety, approval stage advancement) ([`test_services.py`](apps/dms/tests/test_services.py)), all 6 cross-module signal cascades + idempotency on re-save (version-released supersedes prior, approval-approved flips Document, legal-hold M2M cascades, retention recompute on policy change, signature immutability, locked-doc delete refusal) ([`test_signals.py`](apps/dms/tests/test_signals.py)), HTTP CRUD smoke on every list page + full approval workflow walk (multi-stage approve → effective) + ack idempotency + filter regression ([`test_views.py`](apps/dms/tests/test_views.py)), multi-tenant IDOR (cross-tenant 404 on every detail URL) + RBAC matrix (staff blocked from delete / archive / legal-hold mutations / approval-action — L-10) + anonymous-redirect on 11 list URLs ([`test_security.py`](apps/dms/tests/test_security.py)), and `seed_dms` idempotency + `--flush` consistency + `archive_due_documents` dry-run + locked-doc skip + `expire_assignments` read-only safety ([`test_seeder.py`](apps/dms/tests/test_seeder.py)).

### Out of scope (deferred)

- **Full-text search** over `Document.content_html` + uploaded file contents — keyword field only in v1; OpenSearch / Elasticsearch integration deferred.
- **WebSocket live-collaboration** on `content_html` — single-author check-out / check-in only.
- **External DMS integration** (SharePoint / Google Drive / Confluence) — not in v1.
- **DocuSign / Adobe Sign** integration — typed-name e-sig only (FDA 21 CFR Part 11 compliant for internal use).
- **WORM (write-once-read-many) storage** for archived docs — application-level read-only enforcement only.
- **Per-paragraph version diff** rendering — version list + `change_notes` only.
- **Public-link sharing** for external reviewers — internal users only.
- **Customer / supplier-portal document distribution** — internal staff only in v1.

> **Relationship to Module 13.** Module 13's `compliance.ComplianceDocument` is the **regulatory-only** artefact (FDA / ISO documents subject to compliance signatures and the existing tenant audit-chain). Module 19's `dms.Document` is the **operational** artefact (SOPs / work instructions / policies / manuals / forms). There is intentionally **no FK** between them; cross-link manually via the DMS `keywords` field when needed.

---

## Module 20 — Workflow & Business Process Automation

**App:** [`apps/wfa/`](apps/wfa/) · **URL prefix:** `/wfa/` · **Models:** 22 across 5 sub-modules · **Templates:** [`templates/wfa/`](templates/wfa/) · **Tests:** 98 in [`apps/wfa/tests/`](apps/wfa/tests/)

### Sub-modules

| # | Name | Highlights |
|---|------|-----------|
| 20.1 | Visual Workflow Designer | BPMN-style JSON model + indexed `ProcessNode` / `ProcessTransition` rows; runtime `ProcessInstance` bound to any business object; whitelisted condition evaluator (no `eval()`); server-side SVG diagram |
| 20.2 | Approval Engine | Multi-level policy + SLA-driven escalation; delegation; race-safe state machine; append-only `ApprovalActionLog` |
| 20.3 | Notification & Escalation Matrix | Email + in-app + SMS-stub + webhook channels; Django-template subject/body; per-channel delivery ledger |
| 20.4 | Integration Orchestration | Pre-seeded ERP / CRM connector catalog (SAP / Oracle / Dynamics / NetSuite / Salesforce / HubSpot); pure-function flow executor; webhook outbox |
| 20.5 | Process Mining & Optimization | Heuristic cycle-time + bottleneck detection; per-period `CycleTimeReport` with avg / p95 / min / max; ack/dismiss/apply workflow on suggestions |

### Cross-module signal hooks ([apps/wfa/signals.py](apps/wfa/signals.py))

| # | Trigger | Effect | Idempotency |
|---|---|---|---|
| 1 | `ProcessInstance.post_save` (status moves to terminal) | Append `ProcessActivity` log row | Skipped if entry for `(instance, event)` already exists |
| 2 | `ProcessInstance.post_save` (status='completed') | Refresh `ProcessMetric(cycle_time)` via `update_or_create` | Single row per (instance, metric_type) |
| 3 | `ApprovalRequest.post_save` (approved / rejected / escalated) | Create + dispatch `Notification` from matching rule | Skipped when no rule or no requester |
| 4 | `Notification.post_save(status='pending')` | Auto-dispatch via [`services/notification.dispatch`](apps/wfa/services/notification.py) when `delay_minutes==0` | `dispatch` itself short-circuits already-sent channels |
| 5 | `IntegrationRun.post_save(status='failed')` | Create + dispatch failure notification | Skipped if a notification with `run_code` already exists |
| 6 | `dms.DocumentApprovalRequest.post_save(status='approved')` | Auto-close any linked `wfa.ApprovalRequest` via conditional UPDATE | Idempotent (UPDATE WHERE status IN open-states) |
| 7 | `procurement.PurchaseOrder.post_save(status='submitted')` | Auto-create `wfa.ApprovalRequest` when an active matching policy exists | Skipped if open request already exists for (PO, policy) |
| 8 | Audit factory | Best-effort `TenantAuditLog` row for 8 status-tracked models (definition / instance / policy / request / rule / connector / flow / run) | Cached per (model_label, pk, status) to suppress repeat writes |

### Services (pure / single-writer)

- [`services/numbering.py`](apps/wfa/services/numbering.py) — atomic auto-code helper.
- [`services/bpmn_engine.py`](apps/wfa/services/bpmn_engine.py) — `evaluate_condition` + `next_node`; whitelisted AST walker rejects `__import__` / `lambda` / `**` / attribute access. Mirrors the `iot.twin` parser pattern.
- [`services/approval.py`](apps/wfa/services/approval.py) — `submit` / `approve` / `reject` / `delegate` / `escalate` / `recall` + `active_delegate_for` lookup.
- [`services/notification.py`](apps/wfa/services/notification.py) — `render_template`, `create_notification`, `dispatch` fanning to email / sms_stub / in_app / webhook outbox.
- [`services/integration.py`](apps/wfa/services/integration.py) — `execute_flow` with per-step executors (http_call / transform / branch / log / sleep). Uses `requests` library. Steps with `on_failure='abort'` short-circuit the flow.
- [`services/process_mining.py`](apps/wfa/services/process_mining.py) — `compute_cycle_seconds`, `per_node_wait_seconds`, `detect_bottleneck`, `classify_severity`, `cycle_time_stats`. No NumPy / scikit-learn deps.

### Time-driven cron (L-21)

- `escalate_approvals` — flips overdue `pending / in_progress` requests to `escalated` (race-safe per-row save so the post_save signal fires the notification).
- `run_notifications` — dispatches due pending `Notification` rows, honouring per-rule `delay_minutes`.
- `mine_processes` — regenerates `BottleneckAnalysis` + `CycleTimeReport` rows for every active `ProcessDefinition` over the last 30 days.

All three support `--dry-run` and `--tenant <slug>` flags. Schedule daily / hourly via cron (Linux) or Task Scheduler (Windows).

### Routes (UI tour)

| Route | What you'll see |
|-------|----------------|
| `/wfa/` | WFA dashboard — KPI cards (active processes, running instances, pending approvals, my pending, notifications today, failed integrations, open suggestions) + recent instances / approvals / integration runs |
| `/wfa/categories/` and CRUD | Process category catalog |
| `/wfa/processes/` and CRUD + `/<pk>/activate/` · `/archive/` | ProcessDefinition list + detail with inline node / transition CRUD; `draft → active → archived` workflow |
| `/wfa/processes/<pk>/diagram/` | Read-only server-side SVG diagram |
| `/wfa/processes/<pk>/nodes/new/` · `/transitions/new/` and edit/delete | Node + transition CRUD (gated to draft definitions) |
| `/wfa/instances/` and CRUD + `/<pk>/advance/` · `/cancel/` | ProcessInstance runtime list + detail with activity log / variables / metrics |
| `/wfa/approvals/policies/` and CRUD | ApprovalPolicy list + detail with inline ApprovalLevel + EscalationRule CRUD |
| `/wfa/approvals/policies/<pk>/levels/new/` · `/escalations/new/` and edit/delete | Level + escalation rule CRUD |
| `/wfa/approvals/requests/` and CRUD | ApprovalRequest list filterable by status / policy |
| `/wfa/approvals/my/` | My open / closed approval requests |
| `/wfa/approvals/requests/<pk>/approve/` · `/reject/` · `/delegate/` · `/escalate/` · `/recall/` | POST — workflow actions (reject + cancel require notes — L-14) |
| `/wfa/approvals/delegations/` and CRUD | Vacation / coverage delegation matrix |
| `/wfa/notifications/channels/` · `/templates/` · `/rules/` and CRUD | Channel catalog + Django-template body editor + rule binding |
| `/wfa/notifications/` and `<pk>/` | Notification list + detail with per-channel delivery rows |
| `/wfa/notifications/<pk>/dispatch/` | POST — manual re-dispatch |
| `/wfa/notifications/deliveries/` and `/sms/` | Append-only delivery / SMS-stub log |
| `/wfa/integrations/connectors/` and CRUD | Connector catalog with type / auth filters |
| `/wfa/integrations/connectors/<pk>/endpoints/new/` and edit/delete | Endpoint CRUD inline on connector detail |
| `/wfa/integrations/flows/` and CRUD | IntegrationFlow list + detail with inline FlowStep CRUD |
| `/wfa/integrations/flows/<pk>/run/` | POST — execute flow and persist `IntegrationRun` |
| `/wfa/integrations/runs/` and `<pk>/` | Run ledger with per-step results and error capture |
| `/wfa/integrations/outbox/` | Read-only `WebhookOutboxEntry` ledger |
| `/wfa/mining/bottlenecks/` and CRUD | BottleneckAnalysis list + detail with linked suggestions |
| `/wfa/mining/suggestions/` and CRUD + `/<pk>/ack/` · `/dismiss/` · `/apply/` | Optimization suggestion list + workflow (ack/dismiss/apply) |
| `/wfa/mining/cycle-time/` and `<pk>/` | CycleTimeReport list + detail |

### RBAC + multi-tenancy

Every view filters by `request.tenant` first. Workflow + delete mutations on **process / policy / connector / flow / template / rule / channel** are guarded by `@tenant_admin_required` (L-10) — non-admin staff get a flash error and a redirect; underlying state never changes. Approval **approve / reject / escalate** are admin-only; **recall** is permitted to the original requester (or an admin) so a user can withdraw their own request. Notification **dispatch** is callable by any logged-in user for their own notifications.

### Test suite

Run with `pytest apps/wfa/tests/` — **98 tests** spanning auto-numbering (BPM / PI / APR / NR / NTF / CON / IR / BA / POS / CTR) + computed fields + L-02 validators ([`test_models.py`](apps/wfa/tests/test_models.py)), L-01 unique_together `clean()` + L-14 per-workflow required (reject notes / cancel reason / dismiss notes) + JSON CSV parsing ([`test_forms.py`](apps/wfa/tests/test_forms.py)), pure-function services (BPMN whitelist parser rejecting `__import__` / `lambda` / `**` / attribute access, approval state machine with race-safe conditional UPDATE, notification dispatch + delivery ledger, integration flow log step, mining severity classification + cycle stats) ([`test_services.py`](apps/wfa/tests/test_services.py)), cross-module signal cascades + L-18 dispatch_uid + audit-log emission ([`test_signals.py`](apps/wfa/tests/test_signals.py)), full HTTP CRUD + multi-stage approval walk + flow run + instance advance ([`test_views.py`](apps/wfa/tests/test_views.py)), multi-tenant IDOR (cross-tenant 404 on every detail URL) + RBAC matrix (staff blocked from policy / process / connector mutations — L-10) + anonymous-redirect on 7 list URLs ([`test_security.py`](apps/wfa/tests/test_security.py)), and `seed_wfa` idempotency + `--flush` consistency + `run_notifications` / `escalate_approvals` dry-run safety + `mine_processes` report generation ([`test_seeder.py`](apps/wfa/tests/test_seeder.py)).

### Out of scope (deferred)

- **bpmn-js drag-and-drop canvas** — JSON model + read-only SVG only in v1; admin form-based node/edge CRUD.
- **Real SMS provider** — `SMSDelivery` is a stub-only ledger; swap in Twilio / equivalent in `services/notification._dispatch_sms`.
- **Live ERP adapters (SAP / Oracle / Dynamics / NetSuite)** — connector catalog rows ship `is_active=False`; you wire credentials and flip on per-tenant.
- **OAuth2 token refresh** for connectors — only auth metadata stored; refresh flow deferred.
- **ML / scikit-learn process mining** — heuristic averages + nearest-rank p95 only.
- **Visual rule editor** for `EscalationRule` — admin form only.

> **Security flag.** `Connector.auth_secret_hash` is stored as a stop-gap stable token (mirrors `iot.DeviceBroker.password_hash`). Rotate to a KMS / Vault-backed field for production. The condition evaluator in `services/bpmn_engine._safe_eval` is **whitelist-only** (numbers, strings, bool, `+ - * /`, `and / or / not`, comparisons, `min / max / abs`, variable refs) — `eval()` / `exec()` are never called.

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
| `python manage.py expire_compliance [--tenant <slug>] [--dry-run]` | Flip `ProductCompliance` rows from `compliant` to `expired` when their `expiry_date < today`; idempotent; emits one immutable `ComplianceAuditLog(event='expired')` per flip + a cross-cutting `tenants.TenantAuditLog` row. Schedule daily via cron / Task Scheduler. |
| `python manage.py seed_compliance [--flush]` | Seed Module 13 demo data per tenant (4 IncidentType rows, 3 IncidentReports, 2 RiskAssessments, 2 SafetyAuditChecklists + 1 scheduled SafetyAudit, 5 ComplianceDocuments incl. 1 effective with an ElectronicSignature, 4 WasteCategory + 1 in-transit WasteManifest with 2 disposal lines, 1 Class III ProductRecall in_progress on the first plm.Product). Idempotent — skips per-tenant if data exists. |
| `python manage.py seed_bom [--flush]` | Seed BOM demo data (BOMs, lines, alternates, substitution rules, cost elements, sync maps) per tenant |
| `python manage.py seed_pps [--flush]` | Seed PPS demo data (work centers, calendars, routings, MPS, production orders + scheduled operations, capacity load, scenario, optimizer run) per tenant |
| `python manage.py seed_mrp [--flush]` | Seed MRP demo data (forecast models + seasonality + completed forecast run, inventory snapshots, scheduled receipts, completed MRP run with planned orders / PRs / exceptions) per tenant |
| `python manage.py seed_mes [--flush]` | Seed MES demo data (operators, MES work orders fanned out from PPS production orders, time logs, production reports, andon alerts, work instructions with versions + acks) per tenant |
| `python manage.py seed_qms [--flush]` | Seed QMS demo data (IQC plans + inspections, IPQC plans + SPC chart with 25 points, FQC plans + inspections + CoAs, NCRs with RCA + CA + PA, equipment + calibration standards + records) per tenant |
| `python manage.py seed_inventory [--flush]` | Seed Inventory demo data (warehouses + zones + bins, lots + serials, initial stock via real movements, completed GRN with putaway, draft cycle-count sheet) per tenant |
| `python manage.py seed_procurement [--flush]` | Seed Procurement demo data (8 suppliers + 1 supplier-portal user, 4 RFQs incl. 1 awarded with 3 quotations, 6 POs across all statuses + 2 revisions, 2 ASNs, 2 invoices, 1 active blanket + 2 releases, ~80 metric events, 1 scorecard per supplier) per tenant |
| `python manage.py seed_eam [--flush]` | Seed EAM demo data (6 asset categories, 10 assets incl. 1 parent-child pair, spare parts linked to plm.Product, 30 days of meter readings per metered asset, 4 PM plans with 13 tasks + 3 schedules each, 6 monitoring points with 25 readings + 1 deliberately critical that auto-spawns a FailurePrediction, 3 MWOs incl. 1 completed breakdown with labor + material + downtime, 2 tools incl. 1 mold with 4 cavities) per tenant |
| `python manage.py seed_labor [--flush] [--tenant <slug>]` | Seed Labor & Workforce demo data per tenant (4 departments + Assembly sub-dept, 8 positions, 12 skills, 5 certifications, 20 employees with first 6 linked to mes.ShopFloorOperator, 3 shifts + 14-day roster + attendance, 5 leave types + 6 leave requests across statuses, 4 holidays, 5 cost centers, 20 labor rates, 30 labor bookings, 4 training programs + 8 plans + 2 sessions, 1 competency assessment with 5 results, 2 incentive schemes + 5 piece rates each + 1 open period + 1 completed run with 6 lines) |
| `python manage.py seed_cost [--flush] [--tenant <slug>]` | Seed Cost Management & Accounting demo data per tenant (3 accounting periods, 5 cost drivers, 5 overhead pools + 10 rates, 1 active `StandardCostVersion` with ~13 cost rows pulled from BOM rollups, JobCost + WIPEntry chains for every released/in-progress/completed PO, applied overhead allocations for the prior period, 1 CostVariance per closed job, ActualCost rollups, 1 COGMReport + 1 PlantPnLReport for the prior period) |
| `python manage.py seed_utility [--flush] [--tenant <slug>]` | Seed Energy & Utility Management demo data per tenant (6 utility types, 4 meters incl. 1 sub-meter, 5 tariffs, 4 TOU bands, 1 scheduled DemandResponseEvent, 5 emission factors, ~120 UtilityConsumption rows spanning prior + current periods — electricity meters route via `eam.AssetMeterReading` to prove the auto-feed signal — auto-cascaded CarbonEmission ledger, 1 UtilityAllocation per metered cost-center with matching `cost.DriverActuals` write-through, 2 SustainabilityKPI snapshots, 2 BenchmarkSnapshot rows, 1 period-over-period BenchmarkComparison) |
| `python manage.py seed_iot [--flush] [--tenant <slug>]` | Seed Module 15 (IoT & SCADA) demo data per tenant — 6 shared `DeviceProtocol` rows (MQTT / OPC-UA / Modbus TCP+RTU / HTTP / CoAP), 2 brokers, 6 devices linked to seeded `eam.Asset` rows, ~24 tags across temperature / vibration / pressure / electrical_load / state, 5 `LossReason` rows, 4 `AlertRule` rows (threshold, zscore, missing data), ~120 `IoTReading` rows + 2 deliberately anomalous rows that cascade into `AnomalyDetection` + `AlertNotification`, 3 `DigitalTwin` rows with attributes (incl. derived formulas) + 1 completed scenario + 1 snapshot, 7d × 3 assets of `OEEPeriod` rows, and ~5 `EdgeProcessor` rows. Idempotent — skips per-tenant if already seeded. |
| `python manage.py seed_sales [--flush] [--tenant <slug>]` | Seed Module 17 (Sales) 17.1 demo data per tenant — 4 customer categories, 2 price lists (default + VIP) with 6 tiered items where Products exist, 8 customers covering key / standard / distributor / one-time / on_hold classes with seeded credit limits, 24 contacts (3 per customer with primary flag), and 5 communication-log entries across call / email / meeting / note / sms. Idempotent. |
| `python manage.py seed_rma [--flush] [--tenant <slug>]` | Seed Module 18 (Returns & RMA) demo data per tenant covering all 5 sub-modules — 5 RMA reasons, 4 failure modes, 4 root-cause categories, 3 warranty policies, 5 RMA requests spanning every status (draft / submitted / approved / rejected / cancelled) with lines, the approved RMA's auto-drafted return receipt filled with inspection lines that route a real `inventory.StockMovement(receipt)` (restock) + an auto-spawned `RepairOrder` (repair) populated with parts + a labor log mirrored into `labor.LaborBooking`, 4 warranty registrations (1 aged + flipped to expired), 2 warranty claims (1 approved + replacement SO auto-drafted), 2 return analyses, and 1 pending supplier chargeback. Idempotent — skips per-tenant if data exists. |
| `python manage.py expire_warranties [--tenant <slug>] [--dry-run]` | Flip `WarrantyRegistration` rows from `active` to `expired` once `end_date < today` via a race-safe conditional `update()`. Idempotent. Schedule daily via cron (Linux) / Task Scheduler (Windows). |
| `python manage.py seed_dms [--flush] [--tenant <slug>]` | Seed Module 19 (Document & Knowledge Management) demo data per tenant covering all 5 sub-modules — 5 DocumentCategories, 2 RetentionPolicies (5-year, 7-year), 2 DocumentTemplates (SOP + Work Instruction) with typed TemplateFields, 5 Documents across every `doc_type` (sop / work_instruction / policy / form / manual) with 1-2 versions each (one released-and-current), 1 approved DocumentApprovalRequest with 2 ApprovalActions + 2 DocumentSignatures, 2 DocumentAssignments (role + dept based) with 2 seeded ReadAcknowledgments on the first, 1 archived Document (DocumentArchive row), and 1 active LegalHold cascading `is_locked` onto 1 Document. Idempotent. |
| `python manage.py archive_due_documents [--tenant <slug>] [--dry-run]` | Flip `Document` rows from `effective` to `archived` once `retention_until < today` via a race-safe conditional `update()` + emit one `DocumentArchive` row per flip. Skips any Document under an active legal hold. Idempotent. Schedule daily via cron (Linux) / Task Scheduler (Windows). |
| `python manage.py expire_assignments [--tenant <slug>] [--dry-run]` | Report (read-only) every `DocumentAssignment` past `due_date` with no full acknowledgment. Read-only — does NOT mutate state. Schedule daily as a notification-style cron. |
| `pytest apps/dms/tests/` | Run the Module 19 (Document & Knowledge Management) test suite (**116 tests, ~2 min**; covers model auto-numbering (DOC / TPL / AR / DA / ACK / RP / ARC / LH) + computed fields + L-22 validators ([`test_models.py`](apps/dms/tests/test_models.py)), L-01 unique_together `clean()` on every tenant catalog + L-22 file caps + XOR validators (access rule / target) + L-14 per-workflow required (legal hold release notes, archive restore notes, approval reject notes) ([`test_forms.py`](apps/dms/tests/test_forms.py)), pure-function services (checkout optimistic-lock incl. self-idempotency + admin override, retention math with leap-day clamp, legal-hold cascade with multi-hold safety, approval stage advancement) ([`test_services.py`](apps/dms/tests/test_services.py)), all 6 cross-module signal cascades + idempotency ([`test_signals.py`](apps/dms/tests/test_signals.py)), HTTP CRUD + workflow happy paths + ack idempotency + filter regression ([`test_views.py`](apps/dms/tests/test_views.py)), multi-tenant IDOR + RBAC matrix (staff blocked from delete / archive / legal-hold / approval-action — L-10) + anonymous-redirect on 11 list URLs ([`test_security.py`](apps/dms/tests/test_security.py)), and `seed_dms` idempotency + `--flush` consistency + cron dry-run safety ([`test_seeder.py`](apps/dms/tests/test_seeder.py))) |
| `python manage.py generate_pm_schedules [--tenant <slug>] [--horizon-days N]` | Idempotent next-due PMSchedule generator for every active MaintenancePlan; flips past-dated `scheduled` rows to `overdue` first |
| `python manage.py seed_wfa [--flush] [--tenant <slug>]` | Seed Module 20 (Workflow & Business Process Automation) demo data per tenant — 3 `ProcessCategory` rows, 2 `ProcessDefinition`s (Purchase Order Approval + RMA Triage) with full node/transition graphs, 1 running `ProcessInstance` per definition with sample activity log, 2 `ApprovalPolicy`s (PO + RMA) with 2 / 1 levels and 1 escalation rule, 3 sample `ApprovalRequest`s (in_progress + approved + rejected), 1 `ApprovalDelegation`, 4 `NotificationChannel` (email/sms/in_app/webhook), 5 `NotificationTemplate` + 5 matching `NotificationRule`, 6 `Connector` catalog rows (SAP/Oracle/Dynamics/NetSuite/Salesforce/HubSpot, all `is_active=False` for safety), 2 `IntegrationFlow`s with 3 steps each + 1 completed `IntegrationRun`, 4 `ProcessMetric` rows + 1 `BottleneckAnalysis` + 2 `ProcessOptimizationSuggestion` + 1 `CycleTimeReport`. Idempotent. |
| `python manage.py run_notifications [--tenant <slug>] [--dry-run]` | Dispatch pending `wfa.Notification` rows whose `triggered_at + rule.delay_minutes` is in the past. Idempotent within the second. Schedule every 5-15 minutes via cron / Task Scheduler. |
| `python manage.py escalate_approvals [--tenant <slug>] [--dry-run]` | Flip overdue `wfa.ApprovalRequest` rows (`status in pending/in_progress`, `due_at < now`) to `status='escalated'` so the post_save signal fires the escalation notification. Race-safe per-row. Schedule hourly. |
| `python manage.py mine_processes [--tenant <slug>] [--days N]` | Refresh `BottleneckAnalysis` + `CycleTimeReport` rows over a configurable window (default 30 days) for every active `ProcessDefinition`. Idempotent on `(tenant, definition, period_start, period_end)` for cycle-time rows. |
| `pytest apps/wfa/tests/` | Run the Module 20 (Workflow & Business Process Automation) test suite (**98 tests, ~4 min**; covers model auto-numbering (BPM / PI / APR / NR / NTF / CON / IR / BA / POS / CTR) + computed fields + L-02 validators ([`test_models.py`](apps/wfa/tests/test_models.py)), L-01 unique_together `clean()` + L-14 per-workflow required (reject notes / cancel reason / dismiss notes) + JSON CSV parsing ([`test_forms.py`](apps/wfa/tests/test_forms.py)), pure-function services — BPMN whitelist parser rejecting `__import__` / `lambda` / `**` / attribute access, approval state machine with race-safe conditional UPDATE, notification dispatch + delivery ledger, integration flow log step, mining severity classification + cycle stats ([`test_services.py`](apps/wfa/tests/test_services.py)), cross-module signal cascades + L-18 dispatch_uid + audit-log emission ([`test_signals.py`](apps/wfa/tests/test_signals.py)), full HTTP CRUD + multi-stage approval walk + flow run + instance advance ([`test_views.py`](apps/wfa/tests/test_views.py)), multi-tenant IDOR + RBAC matrix (staff blocked from policy / process / connector mutations — L-10) + anonymous-redirect ([`test_security.py`](apps/wfa/tests/test_security.py)), and `seed_wfa` idempotency + `--flush` consistency + `run_notifications` / `escalate_approvals` dry-run safety + `mine_processes` report generation ([`test_seeder.py`](apps/wfa/tests/test_seeder.py))). |
| `python manage.py seed_data [--flush]` | Orchestrator that runs `seed_plans` + `seed_tenants` + `seed_plm` + `seed_bom` + `seed_pps` + `seed_mrp` + `seed_mes` + `seed_qms` + `seed_inventory` + `seed_procurement` + `seed_eam` + `seed_labor` + `seed_cost` + `seed_utility` + `seed_compliance` + `seed_iot` + `seed_bi` + `seed_sales` + `seed_rma` + `seed_dms` + `seed_wfa` |
| `python manage.py capture_health` | Capture a fresh health snapshot for every active tenant (schedule via cron) |
| `python manage.py runserver` | Dev server on port 8000 |
| `pytest apps/plm/tests/` | Run the PLM test suite (122 tests, uses [`config/settings_test.py`](config/settings_test.py)) — includes 55 Phase A compliance regression tests (D-CR-01..08), 7 Phase C audit-chain tests (`test_audit_chain.py`), and 10 Phase C e-signature binding tests (`test_compliance_esignature.py`) |
| `pytest apps/compliance/tests/` | Run the Module 13 test suite (140 tests) — covers all 5 sub-modules + 3 cross-module signal hooks (mes.AndonAlert, qms.NCR, inventory.StockMovement), EHS KPI math, RecallNotice email delivery, and N+1 query budgets |
| `pytest apps/tenants/tests/` | Run the tenant test suite (7 tests) — currently scoped to the SHA-256 TenantAuditLog hash chain regression |
| `pytest apps/pps/tests/` | Run the PPS test suite (58 tests, ~6 s; covers model bounds, form validation, RBAC, workflow, scheduler/optimizer, audit-log emission, query budgets) |
| `pytest apps/mes/tests/` | Run the MES test suite (142 tests, ~9 s; covers model invariants, dispatcher / time-logging / reporting services, forms, workflow, audit-log emission, multi-tenant IDOR, CSRF, plus 8 seeder-regression tests for the 6 BUGs found during the manual-test walkthrough) |
| `pytest --cov=apps/plm` | Run with coverage report |
| `pytest --cov=apps/pps` | Run PPS coverage report (services + signals + forms + models ≥ 84% each) |
| `pytest apps/qms/tests/` | Run the QMS test suite (85 tests, ~19 s; covers AQL table, SPC math + Western Electric rules, model invariants, form validation, IQC/FQC/NCR/Calibration workflow, RBAC matrix, multi-tenant IDOR, audit-log emission) |
| `pytest apps/inventory/tests/` | Run the Inventory test suite (101 tests, ~23 s; covers model invariants, services (post_movement, allocation, cycle_count math, putaway), audit + MES auto-emit signals, form validation, full CRUD + workflow smoke, RBAC matrix, multi-tenant IDOR) |
| `pytest apps/procurement/tests/` | Run the Procurement test suite (70 tests, ~27 s; covers model invariants + decimal validators, form validation (L-01 unique_together, L-02 bounds, L-14 per-workflow required, blanket cumulative-consumption cap), pure-function services (snapshot_po, weighted compute_scorecard, consume_release with overdraw protection), audit + cross-module signals (GRN→SupplierMetricEvent, IQC→SupplierMetricEvent), CRUD smoke + workflow happy paths, RBAC matrix, multi-tenant IDOR, supplier-portal IDOR, anonymous-redirect) |
| `pytest apps/labor/tests/` | Run the Labor & Workforce test suite (145 tests, ~36 s; covers model invariants + auto-numbering (EMP / LR / LB / TS / CA / INC) + decimal validators (L-02), denorm computations (worked_minutes, total_cost, amount, gap, cert status), form validation (L-01 unique_together, L-02 bounds, L-14 per-workflow required), pure-function services (attendance / cost_allocation / competency / piece_rate / scheduling), audit + L-18 dispatch_uid presence guard, cross-module hooks (eam.MWOLaborLog -> indirect LaborBooking with idempotency), CRUD smoke + LeaveRequest workflow + Employee terminate/reactivate, RBAC matrix on 20 admin-only endpoints, multi-tenant IDOR, anonymous-redirect) |
| `pytest apps/cost/tests/` | Run the Cost Management & Accounting test suite (129 tests, ~50 s; covers model invariants + auto-numbering (SCV / JC / WIP / OHA / VAR / ACP / COGM) + denorm computations (StandardCost.total_cost / OverheadRate.rate_per_driver_unit / OverheadAllocation.applied_amount / JobCost.wip_balance / COGMReport.cogm / GrossMarginReport.gross_margin/margin_percent / PlantPnLReport.gross_profit/operating_income / CostVariance.total_variance), form validation (L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required, DriverActuals XOR, date range), pure-function services (recompute_from_bom, compare_versions, compute_actual, compute_variances, post_wip_entry, close_job, reverse_wip_entry, compute_operation_rollup, compute_rate, apply_overhead idempotent rerun + closed-period refusal, reverse_overhead, accumulate_indirect_labor, generate_cogm, generate_plant_pnl), cross-module hooks (labor.LaborBooking(direct) -> WIPEntry(labor_applied) with idempotency, mes.ProductionReport(good_qty) -> WIPEntry(completion) at standard cost), audit factory + L-18 dispatch_uid presence guard, RBAC matrix, multi-tenant IDOR, anonymous-redirect on 17 list URLs) |
| `pytest apps/eam/tests/` | Run the EAM test suite (119 tests, ~58 s; covers model invariants + auto-numbering + decimal validators, form validation (L-01 unique_together for category / spare part / plan / point / cavity, L-02 decimal bounds, L-14 per-workflow required for MWO complete + prediction resolve + PM completion), pure-function services (`generate_upcoming_pm`, `classify_reading`, `compute_downtime`, `bump_tool_life`), audit signals + L-18 dispatch_uid presence guard, ConditionReading-spawns-FailurePrediction signal path with idempotency, DowntimeEvent-refreshes-MWO denorm, cross-module hooks (`mes.AndonAlert` → breakdown MWO with no-asset-link skip + non-equipment-type skip), full CRUD smoke + MWO/PM/prediction workflow, RBAC matrix (staff blocked from create/delete/retire/cancel/resolve while still allowed to record readings + start work), multi-tenant IDOR, anonymous-redirect) |
| `pytest apps/utility/tests/` | Run the Energy & Utility test suite (**222 tests, ~102 s** after the D-01..D-10 remediation pass; covers everything in the original 188 PLUS effective-dated tariff/factor correctness (D-01, D-02), CSV import validation + datetime-parsed dedup (D-03, D-06), TOU band duplicate pre-check (D-04), ISO-4217 currency (D-05), `compute_estimated_savings` heuristic guard (D-07), admin-only `CarbonEmissionReverseView` (D-08), audit-emit failure logging (D-09), `BenchmarkSnapshot.tenant_objects.for_tenant` IDOR guard against the tenant=NULL industry-avg row (D-10), and N+1 query budgets for the four primary list views + dashboard) |
| `python manage.py seed_bi [--flush] [--tenant <slug>]` | Seed Module 16 (Business Intelligence) demo data per tenant — 9 `KPIDefinition` rows (OEE / throughput / yield / scrap_rate / on_time_delivery / supplier_otd / gross_margin / energy_intensity / carbon_intensity), 1 `KPIDashboard` (Plant Operations) with 6 `KPIWidget` placements, 9 tenant-scope `KPISnapshot` rows materialized for the last 30 days, 6 `ReportDataSource` catalog rows (production_orders / production_reports / non_conformance_reports / oee_periods / supplier_invoices / utility_consumption), 1 `ReportDefinition` (Daily Production Summary) with 4 fields + 1 completed `ReportRun`, 2 `PredictiveModel` rows (demand_forecast + failure_likelihood) with 1 completed `PredictionRun`, 1 `DataMart` (Production Daily) with 5 columns + 1 materialized `DataMartSnapshot`, 1 weekly `ReportSchedule` with 1 `ReportRecipient`. Idempotent — skips per-tenant if already seeded. |
| `python manage.py run_report_schedules [--tenant <slug>]` | Cron-style sweeper — executes every active `ReportSchedule` whose `next_run_at <= now`. Renders the bound report or dashboard, persists a `ReportExport`, fans out `ReportDelivery` rows, sends email via Django `send_mail` (console backend in dev). Idempotent within the second; advances `next_run_at` per the schedule's frequency. Intended for cron / Windows Task Scheduler. |
| `pytest apps/bi/tests/` | Run the Business Intelligence test suite (93 tests, ~110 s; covers model invariants + auto-numbering (RPT / RR / PR / TA / DM / SCH / EXP / DLV), snapshot delta math, KPI classification both directions, linear regression / rolling avg / chart trend / naive_seasonal pure-Python math, REGISTERED_SOURCES whitelist enforcement, form validation (L-01 unique_together for every tenant-scoped form, L-14 cancellation / disable reasons, XOR Report-or-Dashboard on `ReportScheduleForm`, custom-frequency cron requirement, registry-code gating on `ReportDataSourceForm`), audit factory + L-18 `dispatch_uid` presence guard, HTTP CRUD smoke on 14 list pages + 3 create handlers, multi-tenant IDOR (cross-tenant 404 on 6 detail URLs), RBAC matrix (staff blocked from 4 admin-only create endpoints), anonymous-redirect on 14 list URLs, `seed_bi` idempotency + count assertions) |
| `pytest apps/rma/tests/` | Run the Module 18 (Returns & RMA) test suite (93 tests, ~3 min; covers model auto-numbering + computed fields (warranty `end_date`, `RepairLaborLog.labor_cost`, `RepairPartUsage.line_cost`) + decimal validators + workflow helpers, L-01 unique_together `clean()` on every tenant catalog + tenant-scoped FK querysets, pure-function services (warranty period math incl. month-end clamping, disposition routing, repair cost rollup idempotency, chargeback transition guards), all 6 cross-module signal hooks + idempotency on re-save (RMA approved→ReturnReceipt, restock→`inventory.StockMovement`, repair→`RepairOrder`, RepairLaborLog→`labor.LaborBooking`, RepairPartUsage save/delete→cost rollup with `on_commit` test using `@pytest.mark.django_db(transaction=True)`, WarrantyClaim approved+replace→`sales.SalesOrder`), HTTP CRUD smoke + RMA submit/approve/reject workflow (reject requires notes — L-14) + repair complete (requires resolution notes — L-14) + chargeback transition + status filter regression, multi-tenant IDOR (cross-tenant 404 on every detail URL) + RBAC matrix (staff blocked from 5 admin-only workflow/delete endpoints — L-10) + anonymous-redirect on 9 list URLs, `seed_rma` idempotency + `--flush` consistency + `expire_warranties` dry-run safety) |
| `pytest apps/iot/tests/` | Run the IoT & SCADA test suite (~150 tests across 13 files: `test_models`, `test_forms`, `test_services`, `test_signals`, `test_views`, `test_views_workflow`, `test_views_crud`, `test_security`, `test_audit_log`, `test_performance`, `test_oee_service`, `test_anomaly_extras`, `test_seeder`. Covers model invariants + auto-numbering (BRK / DEV / IR / IRB / DT / TSC / OEEP / AR / AD), `OEEPeriod.recompute_pcts()` math (incl. zero-division safety), form validation (L-01 unique_together, L-14 resolution_notes required at resolve / false_positive, AlertRule XOR scope), pure-function services (anomaly z-score / IQR / runs_rule / threshold / range / rate-of-change branches, edge rolling_avg / sum / min / max / threshold_count / derivative, twin `_safe_eval` whitelist parser with explicit `__import__` / `exec` / `lambda` / attribute access / `**` operator / undefined-variable rejection), signal cascades (`IoTReading→StreamMetric` aggregates, `IoTReading→AnomalyDetection` with cooldown suppression and inactive-rule skip, fanout to `AlertNotification` per channel, idempotency on resave), audit factory + L-18 dispatch_uid presence guard for 8 audited models, full HTTP CRUD + every workflow POST handler (retire / reactivate / activate / archive / snapshot / scenario_run / rule activate / detection acknowledge-resolve-false_positive / OEE recompute / broker heartbeat), N+1 query budgets on dashboard + 4 list views, RBAC matrix (staff blocked from broker / device / rule mutations + anomaly resolve), multi-tenant IDOR (404 cross-tenant on every detail URL), broker password not exposed in list response, JSON bulk-ingest happy + error paths, `seed_iot` idempotency + fixture-count assertions) |

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

## Manual-Test Walkthroughs

Per-module click-through plans live in [.claude/manual-tests/](.claude/manual-tests/) (`bi`, `bom`, `compliance`, `eam`, `inventory`, `labor`, `mes`, `mrp`, `plm`, `qms`, `sales`). Four modules ship with stand-alone driver scripts that exercise the URL surface against seeded MySQL data and write JSON result digests:

- `python .claude/manual-tests/eam_walkthrough.py`
- `python .claude/manual-tests/inventory_walkthrough.py`
- `python .claude/manual-tests/plm_runner.py`
- `python .claude/manual-tests/qms_runner.py`

Cross-module smoke runner — `python .claude/manual-tests/smoke_all_modules.py` — enumerates every named URL across all 11 modules (zero-arg list + create-form GETs, single-pk detail/edit pages, and list pages under filter querystrings) and flags any 5xx / unexpected response. Writes `.claude/manual-tests/smoke_all_modules_results.json`.

Validation guards added during 2026-05-17 manual-test pass:
- [apps/plm/forms.py](apps/plm/forms.py) — `ProductCategoryForm.clean_code`, `ProductForm.clean_sku`, `CADDocumentForm.clean_drawing_number` surface tenant-scoped `unique_together` duplicates as friendly form errors instead of 500 IntegrityError.
- [apps/sales/views.py](apps/sales/views.py) + [apps/sales/admin.py](apps/sales/admin.py) — pricelist queries now order by `product__sku` (was `product__code`, which fails because Product has no `code` field).
- [apps/iot/models.py](apps/iot/models.py), [apps/iot/views.py](apps/iot/views.py), [apps/iot/management/commands/seed_iot.py](apps/iot/management/commands/seed_iot.py), [apps/bi/services/registry.py](apps/bi/services/registry.py), [apps/bi/services/predictions.py](apps/bi/services/predictions.py) — replaced stale `asset.asset_number` / `asset__asset_number` references with `asset.tag` / `asset__tag` so OEE `__str__` rendering, downtime charts, BI report-builder columns, and predictive analytics no longer raise `AttributeError` / `FieldError`.
- [apps/inventory/management/commands/seed_inventory.py](apps/inventory/management/commands/seed_inventory.py) — `--flush` now clears `compliance.RecallAffectedLot` rows before flushing `inventory.Lot`, so the cleanup no longer raises `ProtectedError` when `seed_compliance` has been run beforehand.

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

Phase 1 (this release) covers the platform + **Modules 1-20** — Tenant & Subscription, PLM, BOM, PPS, MRP, MES, QMS, Inventory, Procurement, EAM, Labor, Cost, Compliance, Energy & Utility, IoT & SCADA, Business Intelligence & Analytics, Sales & Customer Order Management, Returns & RMA Management, Document & Knowledge Management, and Workflow & Business Process Automation. The 2 upcoming modules are fully specified in [`MSM.md`](./MSM.md):

2. ~~Product Lifecycle Management (PLM)~~ ✅ shipped
3. ~~Bill of Materials (BOM)~~ ✅ shipped
4. ~~Production Planning & Scheduling~~ ✅ shipped
5. ~~Material Requirements Planning (MRP)~~ ✅ shipped
6. ~~Shop Floor Control (MES)~~ ✅ shipped
7. ~~Quality Management (QMS)~~ ✅ shipped
8. ~~Inventory & Warehouse~~ ✅ shipped
9. ~~Procurement & Supplier Portal~~ ✅ shipped
10. ~~Equipment & Asset Management (EAM)~~ ✅ shipped
11. ~~Labor & Workforce Management~~ ✅ shipped
12. ~~Cost Management & Accounting~~ ✅ shipped
13. ~~Compliance & Regulatory Management~~ ✅ shipped
14. ~~Energy & Utility Management~~ ✅ shipped
15. ~~IoT & SCADA Integration~~ ✅ shipped
16. ~~Business Intelligence & Analytics~~ ✅ shipped
17. ~~Sales & Customer Order Management~~ ✅ shipped
18. ~~Returns & RMA Management~~ ✅ shipped
19. ~~Document & Knowledge Management~~ ✅ shipped
20. ~~Workflow & Business Process Automation~~ ✅ shipped
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
