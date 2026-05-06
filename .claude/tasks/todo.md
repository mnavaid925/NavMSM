# Module 12 — Cost Management & Accounting — Implementation Plan

> **Status:** DRAFT — awaiting user approval before any code is written.
>
> **Source spec:** [`MSM.md`](../../MSM.md) §12 + user message 2026-05-06.
>
> Mirrors the Module 10 (EAM) / Module 11 (Labor) shape: 1 Django app (`apps/cost/`), 5 sub-modules, full CRUD + workflow, idempotent seeder, full pytest test suite, README updates, sidebar nav, cross-module hooks. Honors all existing lessons (esp. **L-01** unique_together with tenant excluded, **L-02** decimal validators, **L-03** view/template gate parity, **L-04** loud warnings on partial operations, **L-07** `json_script` for inline JS data, **L-08** seeder horizon overlap, **L-09** ASCII stdout in seeders, **L-10** RBAC mixins, **L-12** sequence retry on auto-numbered fields, **L-13** inner-atomic transaction, **L-14** per-workflow required fields, **L-17** PROTECT on audit-trail children, **L-18** `weak=False` on factory-registered signal handlers).

---

## Sub-module breakdown (per user spec)

| # | Sub-module | Description |
|---|-----------|-------------|
| 12.1 | Standard Costing | Material, labor, and overhead standard-cost establishment and revision |
| 12.2 | Actual Cost Tracking | Real-time WIP valuation, actual vs. standard variance analysis |
| 12.3 | Work in Process (WIP) Accounting | WIP ledger, operation-wise cost accumulation, and job costing |
| 12.4 | Overhead Allocation | Activity-based costing (ABC), cost driver definition, and apportionment |
| 12.5 | Manufacturing Financial Reports | Cost of goods manufactured (COGM), gross margin analysis, and plant P&L |

---

## Decisions to confirm with user BEFORE building

| # | Question | Default proposal |
|---|----------|-----------------|
| Q1 | Build all 5 sub-modules in one pass, or stage them? | **All 5 in one pass** (matches Modules 9 / 10 / 11 cadence). |
| Q2 | App name — `cost`? `accounting`? `costing`? | **`cost`** (short, no collision with `core`, mirrors `mrp` / `eam` brevity). Routes mounted at `/cost/`. |
| Q3 | Auto-number prefixes — `SCV-00001` (Standard Cost Version), `JC-00001` (Job Cost / WIP job), `WIP-00001` (WIP entry — append-only ledger row), `OHA-00001` (Overhead Allocation), `VAR-00001` (Variance), `ACP-00001` (Accounting Period), `COGM-00001` (COGM Report). Any collisions? | **None.** Verified against existing prefixes (`EMP/LR/LB/TS/CA/INC/EM*`, `PUR/RFQ/BPO/REL/ASN/SUPINV`, `GRN/TRF/ADJ/CC`, `ASSET/PMS/MWO/TOOL`, `WO/PR/NCR`, `BOM/ECO/NPI/CAD`). |
| Q4 | Costing method per BOM / Product — Standard, Actual, Average, FIFO? | **Standard costing as the canonical method in v1**, with **Actual** computed alongside for variance reporting. Average / FIFO / LIFO deferred. (`plm.Product.costing_method` is *not* added in v1 — implicit single-method = standard.) |
| Q5 | Cross-module — should `inventory.StockMovement.post_save` (issue type, when linked to a `pps.ProductionOrder`) auto-emit a `WIPEntry(type='material_issued')` against the order's job? | **Yes** (idempotent via `(source_movement, entry_type)` natural key). Same shape as the existing Inventory ↔ MES auto-emit for `production_in`. |
| Q6 | Cross-module — should `labor.LaborBooking.post_save` auto-emit a `WIPEntry(type='labor_applied')` against the booking's production order (direct) **and** against the asset's cost-center pool (indirect, awaits monthly absorption)? | **Yes for direct** (idempotent via `(source_labor_booking, entry_type='labor_applied')`); **indirect** rolls into `OverheadActualPool` and is absorbed monthly via `apply_overhead(period)`. |
| Q7 | Cross-module — should `mes.ProductionReport.post_save` (good qty > 0) auto-emit a `WIPEntry(type='completion')` at standard cost (to credit WIP and debit Finished Goods)? | **Yes**, idempotent via `(source_production_report, entry_type='completion')`. Reverses on `pre_delete` (mirrors the existing `production_in` reversal in `apps/inventory/signals.py`). |
| Q8 | Should we extend `bom.BOMCostRollup` with a `cost_version` FK so multiple **active vs. proposed** standard cost runs can co-exist on the same BOM? | **No — keep `BOMCostRollup` as the live engineering rollup.** Module 12's `StandardCost` snapshot is the *frozen* version per product per period; rollback is a recompute, not a versioned BOM rollup. Avoids invasive BOM schema changes. |
| Q9 | Period ledger — should we model double-entry (debit / credit), or single-side WIP entries with explicit type tagging? | **Single-sided typed entries** in v1 (matches the append-only ledger pattern already used by `inventory.StockMovement` and `labor.LaborBooking`). Double-entry GL integration deferred to Module 21 (API & Integration Gateway). |
| Q10 | Revenue side — gross-margin analysis needs sale price. Module 17 (Sales) is not built yet. Use a `plm.Product.standard_sale_price` placeholder? | **Yes** — add nullable `standard_sale_price` (Decimal, validators ≥ 0) to `plm.Product` (one migration), so `GrossMarginReport` can compute even before Sales ships. When Module 17 lands, replace the placeholder with real `SalesOrderLine` aggregates. |
| Q11 | RBAC pattern? | **Same as Modules 9/10/11.** Authenticated tenant users can read; **TenantAdmin** required for create / edit / delete / workflow / recompute / lock-period actions. |
| Q12 | Reports — render server-side HTML tables with ApexCharts visuals? | **Yes**, identical to existing dashboards. CoGM stack chart, gross-margin column chart, P&L waterfall (rendered as a simple bar). All inline data via `json_script` (L-07). PDF export = browser print (mirrors QMS CoA pattern). |

---

## Sub-module 12.1 — Standard Costing

### Models (in [`apps/cost/models.py`](../../apps/cost/models.py))

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `StandardCostVersion` | Effective-dated container for a frozen set of standard costs | `version_number` (auto `SCV-00001`), `name`, `effective_from`, `effective_to` (nullable), `status` (`draft / approved / active / archived`), `notes`, `created_by`, `approved_by`, `approved_at`. `unique_together=(tenant, version_number)` | `SCV-00001` |
| `StandardCost` | Per-product frozen standard cost inside a version | `version` FK, `product` FK (`plm.Product`), `material_cost`, `labor_cost`, `overhead_cost`, `tooling_cost`, `subassembly_cost`, `total_cost` (denorm), `source` (`bom_rollup / manual / imported`), `currency` (3-char ISO, default tenant). `unique_together=(version, product)` | — |
| `StandardCostHistory` | Immutable revision log of changes to active versions | `cost` FK, `field`, `old_value`, `new_value`, `changed_by`, `changed_at`, `change_reason` | — |

**Decimal validators (L-02):** every cost field — `MinValueValidator(0)`. `total_cost` denorm computed in `save()`. Currency string validated 3-char.

**Workflow (L-03 / L-14):**
- `draft → approved` (admin only; sets `approved_by`, `approved_at`)
- `approved → active` (admin only; auto-archives any prior `active` version that overlaps `effective_from`)
- `active → archived` (terminal)
- Edit / delete only while `draft`.

**Service:** `services/standard_costing.py`
- `recompute_from_bom(version)` — pure-ish: reads `bom.BOMCostRollup`, `pps.RoutingOperation.minutes`, `labor.LaborRate`, current `OverheadRate` for the period; populates `StandardCost` rows. Idempotent.
- `compare_versions(v1, v2)` — pure dict diff for the UI side-by-side.

---

## Sub-module 12.2 — Actual Cost Tracking & Variance

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `ActualCost` | Computed actual cost rollup per production order | `production_order` FK (`pps.ProductionOrder`), `material_cost`, `labor_cost`, `overhead_cost`, `total_cost`, `as_of_date`, `is_locked` (period closed). `unique_together=(production_order, as_of_date)` | — |
| `CostVariance` | Per-PO variance breakdown vs. standard | `variance_number` (auto `VAR-00001`), `production_order` FK, `version` FK (`StandardCostVersion`), `material_price_variance`, `material_usage_variance`, `labor_rate_variance`, `labor_efficiency_variance`, `overhead_spending_variance`, `overhead_volume_variance`, `total_variance`, `analysis_notes`, `analyzed_by`, `analyzed_at`. `unique_together=(production_order, version)` | `VAR-00001` |

**Service:** `services/actual_costing.py`
- `compute_actual(production_order, as_of_date)` — pure-ish: aggregates `inventory.StockMovement` issues (PO-linked), `labor.LaborBooking` rows (PO-linked, `kind='direct'`), `OverheadAllocation` rows applied, returns rollup dict. Idempotent — overwrites the row.
- `compute_variances(production_order)` — pure: pulls latest active `StandardCost` for the order's product, returns the 6-axis variance dict (price, usage, rate, efficiency, spending, volume).

**Validation:** L-02 every Decimal field has `MinValueValidator(-1e10)` (variances can be negative, costs can't).

---

## Sub-module 12.3 — Work in Process (WIP) Accounting

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `JobCost` | One per `pps.ProductionOrder` — the "job" in job costing | `job_number` (auto `JC-00001`), `production_order` FK (one-to-one), `status` (`open / closed`), `opened_at`, `closed_at`, `total_material`, `total_labor`, `total_overhead`, `total_completion_credit`, `wip_balance` (denorm). `unique_together=(tenant, production_order)` | `JC-00001` |
| `WIPEntry` | Append-only per-job ledger | `entry_number` (auto `WIP-00001`), `job` FK, `entry_type` (`material_issued / labor_applied / overhead_applied / completion / variance / adjustment`), `amount` (signed Decimal — credits negative), `quantity` (optional, for completion entries), `unit_of_measure`, `cost_center` FK (`labor.CostCenter`, nullable), `routing_operation` FK (`pps.RoutingOperation`, nullable — enables operation-wise accumulation), `source_movement` FK (`inventory.StockMovement`, nullable), `source_labor_booking` FK (`labor.LaborBooking`, nullable), `source_production_report` FK (`mes.ProductionReport`, nullable), `source_overhead_allocation` FK (`OverheadAllocation`, nullable), `entry_date`, `posted_by`, `notes`, `is_reversal` (bool, for `pre_delete` reversal entries). | `WIP-00001` |

**Idempotency keys (cross-module hooks):**
- `(source_movement, entry_type='material_issued')` unique
- `(source_labor_booking, entry_type='labor_applied')` unique
- `(source_production_report, entry_type='completion')` unique
- `(source_overhead_allocation, entry_type='overhead_applied')` unique

**Denorm:** every `WIPEntry.save()` bumps `JobCost.total_<bucket>` and recomputes `JobCost.wip_balance` inside `transaction.atomic()` (L-13). `pre_delete` reverses.

**Service:** `services/wip.py`
- `post_wip_entry(job, **kwargs)` — atomic ledger writer (mirror of `inventory.services.movements.post_movement`).
- `close_job(job)` — checks `wip_balance ≈ 0` (within $0.01); flips status to `closed`. Refuses if non-zero (raises with diff in message; admin must post `adjustment` entry first).
- `compute_operation_rollup(job)` — pure aggregation: `WIPEntry` rows grouped by `routing_operation` for the operation-wise cost accumulation report.

---

## Sub-module 12.4 — Overhead Allocation

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `CostDriver` | Tenant-level activity driver catalog | `name`, `code`, `unit_of_measure` (e.g. machine_hours, labor_hours, units, sq_ft, kwh), `description`, `is_active`. `unique_together=(tenant, code)` | — |
| `OverheadPool` | Pool of indirect costs (Factory Rent, Utilities, Supervision, Indirect Materials, Plant Insurance, …) | `name`, `code`, `pool_type` (`fixed / variable / semi_variable`), `default_driver` FK (`CostDriver`), `allocation_method` (`abc / volume / direct_labor_hours / direct_labor_cost / machine_hours`), `is_active`, `notes`. `unique_together=(tenant, code)` | — |
| `OverheadRate` | Period-scoped rate per pool | `pool` FK, `period` FK (`AccountingPeriod`), `driver` FK (`CostDriver`), `budgeted_amount`, `budgeted_driver_qty`, `rate_per_driver_unit` (computed = budgeted_amount / budgeted_driver_qty), `is_active`. `unique_together=(pool, period)` | — |
| `OverheadActualPool` | Period rollup of actual indirect spend per pool | `pool` FK, `period` FK, `actual_amount` (Decimal), `last_updated_at`. `unique_together=(pool, period)` | — |
| `DriverActuals` | Recorded driver consumption per period per cost center / production order | `driver` FK, `period` FK, `cost_center` FK (nullable), `production_order` FK (nullable), `quantity` (Decimal), `recorded_by`, `recorded_at`. Either `cost_center` or `production_order` must be non-null (form-level XOR). | — |
| `OverheadAllocation` | Materialized allocation: pool × period × target × applied amount | `allocation_number` (auto `OHA-00001`), `pool` FK, `period` FK, `target_cost_center` FK (nullable), `target_production_order` FK (nullable), `driver_qty`, `rate_applied`, `applied_amount` (computed), `posted_at`, `posted_by`, `is_reversed` (bool). `unique_together=(pool, period, target_cost_center, target_production_order)` (NULL-safe via partial unique index using `Q(target_cost_center__isnull=False)` etc.). | `OHA-00001` |

**Service:** `services/overhead.py`
- `compute_rate(pool, period)` — pure: `budgeted_amount / budgeted_driver_qty`.
- `apply_overhead(period)` — orchestrator: for each active pool, scan `DriverActuals` for the period, multiply by rate, emit `OverheadAllocation` rows; auto-emit corresponding `WIPEntry(type='overhead_applied')` rows for production-order targets. Idempotent (re-running clears prior allocations for the period and re-emits).
- `reverse_overhead(period)` — admin-only: marks allocations `is_reversed=True` and emits offsetting `WIPEntry` rows. Refused if period status is `closed`.

**Validation:** L-02 every Decimal ≥ 0 except `applied_amount` which can be negative on reversal entries.

---

## Sub-module 12.5 — Manufacturing Financial Reports

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `AccountingPeriod` | Monthly period with workflow | `period_number` (auto `ACP-00001`), `name` (e.g. "FY26 Apr"), `period_type` (`monthly / quarterly`), `start_date`, `end_date`, `status` (`open / locked / closed`), `locked_at`, `locked_by`, `closed_at`, `closed_by`. `unique_together=(tenant, start_date, end_date)` | `ACP-00001` |
| `COGMReport` | Per-period Cost of Goods Manufactured | `report_number` (auto `COGM-00001`), `period` FK, `opening_wip`, `direct_materials`, `direct_labor`, `overhead_applied`, `closing_wip`, `cogm` (computed = opening + DM + DL + OH − closing), `generated_at`, `generated_by`. `unique_together=(period,)` | `COGM-00001` |
| `GrossMarginReport` | Per-product per-period margin | `period` FK, `product` FK (`plm.Product`), `units_completed`, `standard_cost_per_unit`, `actual_cost_per_unit`, `unit_sale_price` (denorm from `plm.Product.standard_sale_price`), `revenue` (computed = units × price), `cogs` (= units × actual_cost), `gross_margin` (= revenue − cogs), `margin_percent` (computed). `unique_together=(period, product)` | — |
| `PlantPnLReport` | Plant-level P&L per period | `period` FK, `revenue`, `cogm`, `gross_profit` (= revenue − cogm), `selling_expense`, `general_admin_expense`, `unallocated_overhead`, `operating_income` (computed), `generated_at`, `generated_by`. `unique_together=(period,)` | — |

**Service:** `services/reporting.py`
- `generate_cogm(period)` — pure aggregate: scans `JobCost.opening_wip / closing_wip` snapshots + `WIPEntry` aggregates by type for the period. Emits `COGMReport`.
- `generate_gross_margin(period)` — pure: scans completed `mes.ProductionReport.good_qty` × `ActualCost` per product. Emits per-product rows.
- `generate_plant_pnl(period)` — orchestrator: pulls `COGMReport` + `GrossMarginReport` aggregates + manual SG&A entries.

**Workflow (L-03):**
- Period `open → locked` (admin) — refuses new `WIPEntry` posts after lock; reports become refreshable but data is frozen.
- Period `locked → closed` (admin) — irreversible; emits final `COGMReport` + `GrossMarginReport` + `PlantPnLReport` rows.

---

## Cross-module integration

| Touched | Bridge | Migration |
|---|---|---|
| `apps.plm.Product` | Add nullable `standard_sale_price` (Decimal 14,4 ≥ 0) for revenue placeholder. | [`apps/plm/migrations/0004_product_standard_sale_price.py`](../../apps/plm/migrations/) |
| `apps.bom.BOMCostRollup` | **No schema change** — read-only consumer. | — |
| `apps.pps.ProductionOrder` | **No schema change** — `JobCost` references via one-to-one in cost app. | — |
| `apps.inventory.StockMovement` | **No schema change** — `WIPEntry.source_movement` FK lives in cost app. | — |
| `apps.labor.LaborBooking` | **No schema change** — `WIPEntry.source_labor_booking` FK lives in cost app. | — |
| `apps.mes.ProductionReport` | **No schema change** — `WIPEntry.source_production_report` FK lives in cost app. | — |
| `apps.eam.MWOLaborLog` / `MWOMaterialLog` | **Indirect cost feed** — already routed through `labor.LaborBooking(kind='indirect')` (existing); we just consume that. | — |
| Cross-module signal: `inventory.StockMovement.post_save` (movement_type='issue', destination is a PO) | Emit `WIPEntry(type='material_issued', source_movement=…)`. Idempotent. | (signal in `apps/cost/signals.py`) |
| Cross-module signal: `inventory.StockMovement.pre_delete` (same predicate) | Emit reversal `WIPEntry(is_reversal=True)`. | (signal) |
| Cross-module signal: `labor.LaborBooking.post_save` (kind='direct', PO-linked) | Emit `WIPEntry(type='labor_applied', source_labor_booking=…)`. | (signal) |
| Cross-module signal: `labor.LaborBooking.post_save` (kind='indirect') | Accumulate into `OverheadActualPool` (NOT WIPEntry directly — absorbed at month-end). | (signal) |
| Cross-module signal: `mes.ProductionReport.post_save` (good_qty > 0) | Emit `WIPEntry(type='completion', source_production_report=…)` at standard cost. | (signal) |
| Cross-module signal: `mes.ProductionReport.pre_delete` | Emit reversal completion entry. | (signal) |

All cross-module hooks live in [`apps/cost/signals.py`](../../apps/cost/signals.py) so removing the cost app cleanly disables the events without orphan code in other apps.

---

## Validation guards (apply Lessons L-01, L-02, L-14)

- Every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check (L-01): `CostDriverForm` / `OverheadPoolForm` / `AccountingPeriodForm` / `StandardCostVersionForm`.
- Every Decimal field carries explicit `MinValueValidator(0)` except variance / signed-amount fields which use `MinValueValidator(-1e10)` (L-02).
- Per-workflow forms enforce per-transition required fields (L-14):
  - `StandardCostVersionApproveForm` — requires `notes` when transitioning to `approved`.
  - `AccountingPeriodLockForm` — requires `lock_reason` if there are open variances (≥ 1 unanalyzed `CostVariance` exposes a `confirm` checkbox).
  - `OverheadAllocationReverseForm` — requires `reversal_reason`.
  - `JobCostCloseForm` — refuses if `wip_balance ≠ 0`; admin must post explicit `adjustment` entry first.

---

## RBAC (L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, period read | Authenticated tenant user | `TenantRequiredMixin` |
| StandardCostVersion CRUD + approve / activate / archive; StandardCost recompute; CostVariance create / delete; OverheadPool / Driver / Rate CRUD; DriverActuals CRUD; apply / reverse overhead; AccountingPeriod CRUD + lock / close; COGMReport / GrossMargin / PlantPnL generate; JobCost close; WIPEntry create / adjustment / reversal | Tenant admin | `TenantAdminRequiredMixin` |

---

## URL & template surface (mirrors EAM / Labor index)

```
/cost/                                    # dashboard
/cost/standard-versions/                  # SCV list + CRUD + approve / activate / archive
/cost/standard-versions/<pk>/             # detail with StandardCost rows + Recompute / Compare buttons
/cost/standard-costs/                     # flat StandardCost list (filter by version / product)
/cost/standard-costs/compare/?v1=&v2=     # side-by-side diff
/cost/actual-costs/                       # ActualCost list (per PO)
/cost/actual-costs/<pk>/                  # detail with variance breakdown
/cost/variances/                          # CostVariance list + analyze
/cost/jobs/                               # JobCost list (open / closed filter)
/cost/jobs/<pk>/                          # detail with WIPEntry table + operation-wise rollup
/cost/jobs/<pk>/close/                    # POST close
/cost/wip-entries/                        # full ledger (filter by job / type / cost center)
/cost/cost-drivers/                       # CRUD
/cost/overhead-pools/                     # CRUD
/cost/overhead-rates/                     # CRUD
/cost/driver-actuals/                     # CRUD
/cost/overhead-allocations/               # list (filter by period / pool)
/cost/overhead-allocations/apply/         # POST run apply_overhead(period)
/cost/overhead-allocations/<pk>/reverse/  # POST reverse
/cost/periods/                            # AccountingPeriod CRUD + lock / close
/cost/cogm/                               # COGMReport list + generate
/cost/cogm/<pk>/                          # COGM detail with stacked-bar ApexChart
/cost/gross-margin/                       # GrossMarginReport list (filter by period / product)
/cost/gross-margin/<pk>/                  # detail
/cost/plant-pnl/                          # PlantPnLReport list
/cost/plant-pnl/<pk>/                     # detail with waterfall-style chart
```

Template tree (per file): `templates/cost/{index, standard_versions, standard_costs, actual_costs, variances, jobs, wip_entries, cost_drivers, overhead_pools, overhead_rates, driver_actuals, overhead_allocations, periods, cogm, gross_margin, plant_pnl}/{list,form,detail,*}.html`

---

## Idempotent seeder ([`apps/cost/management/commands/seed_cost.py`](../../apps/cost/management/commands/seed_cost.py))

Per-tenant fixtures (mirrors Module 11 cadence):
- 3 `AccountingPeriod` rows — previous month (`closed`), current month (`open`), next month (`open`)
- 5 `CostDriver` rows — machine_hours / direct_labor_hours / units_produced / sq_ft / kwh
- 5 `OverheadPool` rows — Factory Rent (fixed) / Utilities (variable) / Supervision (fixed) / Indirect Materials (variable) / Plant Insurance (fixed)
- 5 `OverheadRate` rows for the **current** period — one per pool, with budgeted amount + driver qty so rate is deterministic
- 1 `StandardCostVersion` (`SCV-00001`, status `active`) covering current + prior period — 1 `StandardCost` row per seeded `plm.Product` (pulled from `bom.BOMCostRollup` where present, else fallback `material=10, labor=5, overhead=3, tooling=1`)
- For each released `pps.ProductionOrder` in the prior period:
  - 1 `JobCost` (status `closed` for those whose PO is `completed`, else `open`)
  - WIPEntry rows back-filled from existing `inventory.StockMovement` issues + `labor.LaborBooking` direct + a synthesized `overhead_applied` entry
  - For closed jobs: 1 `CostVariance` row with non-zero values across all 6 axes for visual variety
- For the **prior** (closed) period: 1 `OverheadActualPool` per pool (slightly off from budget so allocation has spending variance), `apply_overhead(prior_period)` invoked, 1 `COGMReport`, per-finished-product `GrossMarginReport` rows, 1 `PlantPnLReport`
- L-08 horizon overlap — periods explicitly aligned to `pps.MasterProductionSchedule.horizon_start` / `+30d` so jobs and overheads align.
- L-09 ASCII stdout — never print non-ASCII (Windows cp1252 PowerShell).

Print summary at end:
```
[seed_cost] tenant=acme periods=3 drivers=5 pools=5 std_costs=20 jobs=12 wip_entries=84 variances=8 cogm=1 plant_pnl=1
[seed_cost] LOGIN as admin_acme / Welcome@123
```

Add to `seed_data` orchestrator and to README "Management Commands" + "Seeded Demo Data" tables.

---

## Test plan ([`apps/cost/tests/`](../../apps/cost/tests/))

Targeting **~120 tests, ~30 s** runtime (matches Labor / Procurement). Files:

- `test_models.py` — auto-numbering (SCV / JC / WIP / OHA / VAR / ACP / COGM), `unique_together` integrity, decimal validators (L-02), denorm computations (`JobCost.wip_balance`, `StandardCost.total_cost`, `OverheadRate.rate_per_driver_unit`, `OverheadAllocation.applied_amount`, `GrossMarginReport.gross_margin / margin_percent`).
- `test_forms.py` — L-01 unique_together for every tenant-scoped form, L-02 bounds, L-14 per-workflow required fields (approve / lock / reverse / close / generate), `DriverActualsForm` XOR (cost_center XOR production_order).
- `test_services.py` — pure-function coverage:
  - `services/standard_costing.recompute_from_bom` — happy path + missing BOM rollup + missing labor rate.
  - `services/actual_costing.compute_actual` + `compute_variances` — six-axis variance math against fixtures.
  - `services/wip.post_wip_entry` + `close_job` (refuses non-zero balance with descriptive error).
  - `services/overhead.compute_rate` + `apply_overhead` (idempotent rerun) + `reverse_overhead` (refuses on closed period).
  - `services/reporting.generate_cogm` + `generate_gross_margin` + `generate_plant_pnl`.
- `test_signals.py` — every cross-module hook: idempotency under double-fire, reversal on `pre_delete`, silent skip when no PO link / no scheme / no cost center. **L-18 dispatch_uid presence guard** asserts every required `dispatch_uid` remains attached after `apps.ready()`.
- `test_audit.py` — `_mk_status_signals(model, action_prefix)` pattern for `StandardCostVersion`, `AccountingPeriod`, `CostVariance`, `OverheadAllocation`, `JobCost` — emits `cost.<resource>.<status>` audit entries with `weak=False` (L-18).
- `test_security.py` — `TestRBACMatrix` (~24 admin-only endpoints redirect for staff), `TestMultiTenantIDOR` (cross-tenant 404 on every detail / edit / delete URL), `TestAnonymousRedirect` (login redirect on every list URL).
- `test_views.py` — full CRUD smoke + workflow happy paths (approve / activate version / lock period / close period / close job / reverse overhead / generate reports).
- `test_dashboard.py` — KPI cards, ApexCharts series shape (json_script payload format per L-07).

---

## README updates (mandatory — same session)

- TOC entry "Module 12 — Cost Management & Accounting"
- Highlights bullet
- Screenshots / UI Tour rows for every `/cost/` URL
- Project Structure entry under `apps/cost/`
- Dedicated "## Module 12 — Cost Management & Accounting" section with all 5 sub-modules + cross-module integration table + RBAC table + audit-signals table + tests-summary line + out-of-scope (deferred)
- Seeded Demo Data line "Per tenant (Module 12 — Cost) — …"
- Management Commands row for `seed_cost`
- Roadmap — strike `12. Cost Management & Accounting` and replace with `~~Cost Management & Accounting~~ ✅ shipped`

---

## File list (commit count estimate)

Estimated **~80–95 files** in total (Labor was ~110, EAM ~120). Bundled into per-file commits per CLAUDE.md "ONE FILE PER COMMIT" rule.

Approximate breakdown:
- `apps/cost/__init__.py`, `apps.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, `signals.py`, `admin.py` (8 commits)
- `apps/cost/services/__init__.py` + 5 service files (6 commits)
- `apps/cost/management/__init__.py` + `commands/__init__.py` + `seed_cost.py` (3 commits)
- `apps/cost/migrations/__init__.py` + `0001_initial.py` (2 commits)
- `apps/plm/migrations/0004_product_standard_sale_price.py` + `apps/plm/models.py` patch (2 commits)
- `templates/cost/index.html` + ~50 list / form / detail templates (~50 commits)
- `apps/cost/tests/__init__.py` + 8 test files (9 commits)
- `static/css/style.css` patch (if needed for dashboard cards — likely 0)
- `templates/partials/sidebar.html` patch (1 commit)
- `config/urls.py` patch (1 commit)
- `config/settings.py` patch (add `apps.cost` to `INSTALLED_APPS`) (1 commit)
- `README.md` patch (1 commit — single file even though many sections updated)

---

## Build sequence (suggested order — verify before code)

1. **Plan approval** ← we are here
2. App scaffold: `apps/cost/__init__.py`, `apps.py`, empty `models.py`, register in `INSTALLED_APPS`, create migrations stub
3. Sub-module 12.1 — Standard Costing models + form + view + URL + template + service
4. Sub-module 12.4 — Overhead Allocation models (needed by 12.2 / 12.3 cross-module signals)
5. Sub-module 12.3 — WIP Accounting models + service + signals (cross-module hooks for inventory / labor / mes)
6. Sub-module 12.2 — Actual Cost Tracking + Variance
7. Sub-module 12.5 — Reports
8. PLM migration — `Product.standard_sale_price`
9. Audit signals (`_mk_status_signals` factory) + L-18 guard
10. Sidebar nav + dashboard
11. Seeder + orchestrator wiring
12. Tests
13. README updates
14. Per-file commit snippet block

---

## Open questions back to user

Please confirm or amend the **defaults** in the table at the top (Q1–Q12). In particular:

1. **Q2** — App name `cost` vs. `accounting` vs. `costing`. Default: `cost`.
2. **Q4** — Standard costing only in v1, with Actual computed alongside for variance. Defer FIFO / Average. Confirm?
3. **Q9** — Single-sided typed entries (no double-entry GL) in v1. Confirm?
4. **Q10** — Add nullable `standard_sale_price` to `plm.Product` so margin reports can compute now. Confirm? (One small migration on plm.)
5. **Anything missing** from the 5 sub-modules — extra reports, currency / multi-currency, budgeting (capex / opex)?

Once you confirm, I will proceed with the build sequence above, hand commits per-file per CLAUDE.md, update the README in the same session, and ship the test suite.
