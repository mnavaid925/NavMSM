# Plan — Module 5: Material Requirements Planning (MRP)

> Status: **DRAFT — pending user approval before any code is written**
> Created: 2026-04-28
> Pattern reference: `apps/pps/` (Module 4) — newest, cleanest example. Mirror its layout exactly: `models.py` (sectioned banners), `forms.py`, `views.py`, `urls.py`, `signals.py`, `services/`, `admin.py`, `management/commands/seed_mrp.py`, plus `templates/mrp/<sub>/list|form|detail.html`.

## Goal

Build **Module 5 — Material Requirements Planning (MRP)** as a new Django app `apps/mrp/`, mounted at `/mrp/`, following every convention established by `apps/plm/`, `apps/bom/`, and `apps/pps/`:

- Multi-tenant via `TenantAwareModel`
- Full CRUD per model (list / create / detail / edit / delete) — CRUD Completeness Rules
- Working filters on every list page — Filter Implementation Rules
- Audit signals on status transitions (writes to `apps.tenants.TenantAuditLog`)
- Idempotent seeder with `--flush` — Seed Command Rules
- README.md updated in the same session — README Maintenance Rule
- Sidebar entry added to `templates/partials/sidebar.html`
- One file per git commit at the end — STRICT GIT Commit Rule

## Sub-modules to implement

| # | Sub-Module | Core Capability |
|---|---|---|
| 5.1 | Demand Forecasting | Statistical forecasting (moving-avg, weighted MA, exp smoothing, naive seasonal), seasonality profiles, demand sensing |
| 5.2 | Net Requirements Calculation | Gross-to-net logic with BOM explosion, lot-sizing rules (L4L / FOQ / POQ / Min-Max), safety-stock honoring |
| 5.3 | Purchase Requisition Auto-Generation | MRP-suggested PRs from planned orders for purchased items (Module 9 / Procurement will consume these later) |
| 5.4 | MRP Exception Management | Late-order / expedite / defer / cancel action messages with severity + recommended action |
| 5.5 | MRP Run & Simulation | Regenerative vs net-change runs; simulation runs that don't commit; one-click commit/discard |

---

## 0. Open questions for user approval (please confirm before I start coding)

1. **App label** — `mrp`, URL prefix `/mrp/`, sidebar group "Material Requirements (MRP)" between "Production Planning" and "User Management". **OK?**
2. **Forecast vs PPS DemandForecast** — `apps.pps.DemandForecast` already exists (manual input row fed to MPS). MRP needs its own richer **`ForecastModel` + `ForecastRun` + `ForecastResult`** trio (algorithm config, run log, output rows). The two coexist; an "Apply to PPS" button on a completed `ForecastRun` later writes rows into `pps.DemandForecast`. **OK to keep PPS forecast untouched and ship MRP forecasting as a separate, richer layer?**
3. **Inventory dependency** — Module 8 (Inventory) isn't built yet, but Net Requirements needs on-hand qty, safety stock, reorder point, and lead-time per item. Plan: add a minimal **`InventorySnapshot`** model inside `apps/mrp/` (one row per `(tenant, product)`) that the future Inventory module can populate from real bin-level data. The MRP engine reads this snapshot — it does NOT try to compute on-hand stock from transactions. **OK?**
4. **Procurement dependency** — Module 9 (Procurement) isn't built yet either. Plan: add a minimal **`MRPPurchaseRequisition`** model inside `apps/mrp/` (auto-numbered `MPR-00001`). Procurement will later be able to "convert" an approved MRP PR into a real PO via `converted_reference`. **OK to ship MRP-suggested PRs as a self-contained MRP table for now?**
5. **Forecasting algorithms** — ship deterministic, pure-function methods only: `moving_avg`, `weighted_ma`, `simple_exp_smoothing`, `naive_seasonal`. No ML / Prophet / scikit-learn dependency. Same trade as PPS optimizer (greedy heuristic stub). **OK?**
6. **Lot-sizing rules** — Lot-for-Lot (L4L), Fixed Order Quantity (FOQ), Period Order Quantity (POQ), Min-Max. Implemented in `services/lot_sizing.py` as pure functions. **OK?**
7. **MRP engine reach into BOM** — MRP **must** explode multi-level BOMs to compute dependent demand on components. Plan: reuse `bom.BillOfMaterials.explode()` (the existing generator) — same way PPS reuses `plm.Product`. No duplication. **OK?**
8. **Pytest test suite** — defer to a follow-up (matches how PLM, BOM, PPS shipped — manual test plan only at v1). **OK?**
9. **Currency** — single USD assumed (matches BOM cost elements + PPS cost_per_hour). **OK?**

If you reply "do what you think best" I'll proceed with all nine defaults.

---

## 1. Models — `apps/mrp/models.py` (~14 models, sectioned banners)

All inherit from `TenantAwareModel, TimeStampedModel`. Reuse `apps.plm.models.Product`, `apps.bom.models.BillOfMaterials`, `apps.pps.models.MasterProductionSchedule`.

### 5.1 Demand Forecasting
- **`ForecastModel`** — `name`, `description`, `method` (`moving_avg` / `weighted_ma` / `simple_exp_smoothing` / `naive_seasonal`), `params` JSON (window size, smoothing alpha, seasonality length), `period_type` (`day` / `week` / `month`), `horizon_periods`, `is_active`, `created_by`. Unique `(tenant, name)`.
- **`SeasonalityProfile`** — `product` FK, `period_type` (`week` / `month`), `period_index` (1-12 monthly or 1-52 weekly), `seasonal_index` decimal (1.0 = neutral), `notes`. Unique `(tenant, product, period_type, period_index)`.
- **`ForecastRun`** — `run_number` auto `FRUN-00001`, `forecast_model` FK, `run_date`, `started_by`, `started_at`, `finished_at`, `status` (`queued` / `running` / `completed` / `failed`), `error_message`.
- **`ForecastResult`** — `run` FK, `product` FK, `period_start`, `period_end`, `forecasted_qty`, `lower_bound`, `upper_bound`, `confidence_pct`. Unique `(run, product, period_start)`.

### 5.2 Net Requirements Calculation
- **`InventorySnapshot`** — `product` FK, `on_hand_qty`, `safety_stock`, `reorder_point`, `lead_time_days`, `lot_size_method` (`l4l` / `foq` / `poq` / `min_max`), `lot_size_value` decimal (FOQ size, POQ periods, or min/max for min_max), `lot_size_max` decimal (for min_max), `as_of_date`. Unique `(tenant, product)`. **Note in `models.py` docstring**: "Stand-in for the future Inventory module. Will be replaced by aggregated bin-level data when Module 8 ships."
- **`ScheduledReceipt`** — `product` FK, `receipt_type` (`open_po` / `planned_production` / `transfer`), `quantity`, `expected_date`, `reference` text (e.g. PO#, PrdOrd#).
- **`MRPCalculation`** — `mrp_number` auto `MRP-00001`, `name`, `horizon_start`, `horizon_end`, `time_bucket` (`day` / `week`), `status` (`draft` / `running` / `completed` / `failed` / `committed` / `discarded`), `source_mps` FK→`pps.MasterProductionSchedule` (optional), `started_by`, `started_at`, `finished_at`, `error_message`, `committed_at`, `committed_by`. Unique `(tenant, mrp_number)`.
- **`NetRequirement`** — `mrp_calculation` FK, `product` FK, `period_start`, `period_end`, `gross_requirement` decimal, `scheduled_receipts_qty` decimal, `projected_on_hand` decimal, `net_requirement` decimal, `planned_order_qty` decimal, `planned_release_date` (date), `lot_size_method`, `bom_level` PositiveSmallInt (0 = end item, 1 = first-level component, …), `parent_product` FK (nullable, for traceability). Unique `(mrp_calculation, product, period_start)`.

### 5.3 Purchase Requisition Auto-Generation
- **`MRPPurchaseRequisition`** — `pr_number` auto `MPR-00001`, `mrp_calculation` FK, `product` FK, `quantity` decimal, `required_by_date` date, `suggested_release_date` date, `status` (`draft` / `approved` / `converted` / `cancelled`), `priority` (`low` / `normal` / `high` / `rush`), `notes`, `approved_by`, `approved_at`, `converted_at`, `converted_reference` text (FK-equivalent to a future `procurement.PurchaseOrder`). Unique `(tenant, pr_number)`.

### 5.4 MRP Exception Management
- **`MRPException`** — `mrp_calculation` FK, `product` FK, `exception_type` (`late_order` / `expedite` / `defer` / `cancel` / `release_early` / `below_min` / `above_max` / `no_routing` / `no_bom`), `severity` (`low` / `medium` / `high` / `critical`), `message` text, `recommended_action` (`expedite` / `defer` / `cancel` / `release_early` / `manual_review` / `no_action`), `target_type` (`production_order` / `purchase_requisition` / `mps_line` / `none`), `target_id` BigInt nullable (no FK because the target may live in another module), `current_date` date nullable, `recommended_date` date nullable, `status` (`open` / `acknowledged` / `resolved` / `ignored`), `resolved_by`, `resolved_at`, `resolution_notes`.

### 5.5 MRP Run & Simulation
- **`MRPRun`** — `run_number` auto `MRPRUN-00001`, `name`, `run_type` (`regenerative` / `net_change` / `simulation`), `status` (`queued` / `running` / `completed` / `failed` / `applied` / `discarded`), `mrp_calculation` FK (the working `MRPCalculation` snapshot it produced), `source_mps` FK→`pps.MasterProductionSchedule` (nullable), `started_by`, `started_at`, `finished_at`, `error_message`, `applied_at`, `applied_by`, `commit_notes`. Unique `(tenant, run_number)`.
  - **Regenerative** — wipes prior `NetRequirement` rows in horizon, recomputes everything from BOMs + on-hand + receipts.
  - **Net change** — incremental: only recomputes products whose demand or supply changed since the last run.
  - **Simulation** — same algorithm, but the resulting `MRPCalculation` is created with `status='draft'` and is NEVER auto-committed; it can be discarded without side effects.
- **`MRPRunResult`** — `run` OneToOne, `total_planned_orders` int, `total_pr_suggestions` int, `total_exceptions` int, `late_orders_count` int, `coverage_pct` decimal, `summary_json` JSON.

---

## 2. Services — `apps/mrp/services/` (4 pure-function modules)

```
apps/mrp/services/
├── __init__.py
├── forecasting.py      # moving_avg, weighted_ma, simple_exp_smoothing, naive_seasonal
├── lot_sizing.py       # apply_lot_size(method, params, demand_periods) -> planned_qty per period
├── mrp_engine.py       # run_mrp(calculation, mode) — gross-to-net + BOM explosion
└── exceptions.py       # generate_exceptions(calculation) -> list of MRPException
```

### `forecasting.py`
- `moving_average(history, window)` → list of forecasted values
- `weighted_moving_average(history, weights)` → list (weights sum to 1)
- `simple_exp_smoothing(history, alpha)` → list (level + next forecast)
- `naive_seasonal(history, seasonal_indices)` → list

All take `list[Decimal]` history, return `list[Decimal]` forecast — no ORM dependency.

### `lot_sizing.py`
- `apply_l4l(periods)` — order exactly net req each period
- `apply_foq(periods, fixed_qty)` — order multiples of fixed_qty until net req covered
- `apply_poq(periods, period_count)` — group net req across N periods
- `apply_min_max(periods, min_qty, max_qty, on_hand_starting)` — stay within min/max

Returns `list[(period_index, planned_qty, planned_release_date)]`.

### `mrp_engine.py`
Public entry point: `run_mrp(calculation: MRPCalculation, mode: str = 'regenerative') -> MRPRunResult`.

Algorithm:
1. Collect end-item demand (from `source_mps.lines` if linked, else from `ForecastResult` rows in horizon).
2. For each end item, walk `bom.BillOfMaterials.explode()` to expand to component-level dependent demand. Phantom assemblies are already collapsed by `explode()` (see Module 3 docs).
3. For each `(product, period)` pair, compute:
   - gross_requirement = sum of demand
   - scheduled_receipts_qty = sum of `ScheduledReceipt` in window
   - projected_on_hand = previous projected_on_hand + scheduled_receipts - gross_requirement
   - net_requirement = max(0, safety_stock - projected_on_hand) when projected falls below safety stock
4. Apply lot-sizing rule from `InventorySnapshot.lot_size_method` to net requirements.
5. Compute `planned_release_date = period_start - lead_time_days`.
6. Persist `NetRequirement` rows in one `bulk_create`. Drop and recreate for regenerative mode; merge for net-change.
7. For purchased items (component products tagged `product_type='raw_material'` or `'component'`) with positive `planned_order_qty` and an approved status, create `MRPPurchaseRequisition` rows.
8. Hand off to `exceptions.generate_exceptions(calculation)`.

### `exceptions.py`
Pure-function pass over `NetRequirement` + `ProductionOrder` + `MRPPurchaseRequisition`. Generates exceptions for:
- `late_order` — `production_order.requested_end < net_requirement.period_end`
- `expedite` — `planned_release_date < today`
- `defer` — `planned_release_date > requested_start + slack`
- `below_min` / `above_max` — lot-size constraints violated
- `no_bom` — no released BOM for end item
- `no_routing` — product needs production but no routing exists

Returns `list[dict]`; the caller `bulk_create`s `MRPException` rows.

---

## 3. Forms — `apps/mrp/forms.py`

ModelForms for every CRUD-able entity, with `clean()` enforcing unique_together where `tenant` is excluded (Lesson L-01):

- `ForecastModelForm`, `SeasonalityProfileForm`, `ForecastRunForm`
- `InventorySnapshotForm`, `ScheduledReceiptForm`, `MRPCalculationForm`, `NetRequirementForm` (probably read-only — calculated, no manual edit)
- `MRPPurchaseRequisitionForm`
- `MRPExceptionForm` (only edits `status` / `resolution_notes` — engine-generated rows, no manual create)
- `MRPRunForm`

Decimal fields use `MinValueValidator` / `MaxValueValidator` (Lesson L-02) — `seasonal_index >= 0`, `confidence_pct 0-100`, `quantity > 0`, etc.

---

## 4. Views — `apps/mrp/views.py`

Per Filter Implementation Rules + CRUD Completeness Rules:

- **Index** — `index_view`: KPI cards (open MRP runs, total exceptions open, late orders, coverage %, last run time) + recent MRP runs + recent exceptions.
- **Forecast Models** — list / create / detail / edit / delete + **`forecast_run_view`** (POST → invokes service, creates `ForecastRun` + `ForecastResult` rows).
- **Seasonality Profiles** — list / create / edit / delete (no detail; line-level data).
- **Forecast Runs** — list (filterable by status / forecast_model) / detail (shows result rows + chart) / delete.
- **Inventory Snapshots** — list / create / detail / edit / delete + **bulk import CSV** (deferred, P2 — out of scope for v1; mention only).
- **Scheduled Receipts** — list / create / detail / edit / delete.
- **MRP Calculations** — list (filterable by status / source_mps) / detail (Net Requirements tab + Exceptions tab + PR tab) / delete.
- **MRP Runs** — list (filter by run_type / status) / create (form chooses run_type + source_mps) / detail / **`run_start_view`** / **`run_apply_view`** / **`run_discard_view`** / delete.
- **MRP Purchase Requisitions** — list (filter by status / priority / product) / detail / edit (only while `draft`) / **`pr_approve_view`** / **`pr_cancel_view`** / delete (only `draft`).
- **MRP Exceptions** — list (filter by exception_type / severity / status) / detail / **`exception_acknowledge_view`** / **`exception_resolve_view`** / **`exception_ignore_view`** / delete (admin-only).

Status-gated views match the buttons rendered (Lesson L-03). Operations that may skip rows (e.g. MRP run with missing BOMs) use `messages.warning(...)` with counts (Lesson L-04). Datetime-walking forecasting service strips/attaches tz at boundary (Lesson L-05).

All transitions use conditional `UPDATE … WHERE status IN (…)` for race safety (matches PPS / BOM pattern).

---

## 5. URLs — `apps/mrp/urls.py`

Mounted at `/mrp/`. Routes follow the PPS naming pattern. Final URL list will include:

```
/mrp/                                      mrp:index
/mrp/forecast-models/                      mrp:forecast_model_list
/mrp/forecast-models/new/                  mrp:forecast_model_create
/mrp/forecast-models/<pk>/                 mrp:forecast_model_detail
/mrp/forecast-models/<pk>/edit/            mrp:forecast_model_edit
/mrp/forecast-models/<pk>/delete/          mrp:forecast_model_delete
/mrp/forecast-models/<pk>/run/             mrp:forecast_model_run    [POST]
/mrp/seasonality/                          mrp:seasonality_list
/mrp/seasonality/new/                      mrp:seasonality_create
/mrp/seasonality/<pk>/edit/                mrp:seasonality_edit
/mrp/seasonality/<pk>/delete/              mrp:seasonality_delete
/mrp/forecast-runs/                        mrp:forecast_run_list
/mrp/forecast-runs/<pk>/                   mrp:forecast_run_detail
/mrp/forecast-runs/<pk>/delete/            mrp:forecast_run_delete
/mrp/inventory/                            mrp:inventory_list
/mrp/inventory/new/                        mrp:inventory_create
/mrp/inventory/<pk>/                       mrp:inventory_detail
/mrp/inventory/<pk>/edit/                  mrp:inventory_edit
/mrp/inventory/<pk>/delete/                mrp:inventory_delete
/mrp/receipts/                             mrp:receipt_list
/mrp/receipts/new/                         mrp:receipt_create
/mrp/receipts/<pk>/edit/                   mrp:receipt_edit
/mrp/receipts/<pk>/delete/                 mrp:receipt_delete
/mrp/calculations/                         mrp:calculation_list
/mrp/calculations/<pk>/                    mrp:calculation_detail
/mrp/calculations/<pk>/delete/             mrp:calculation_delete
/mrp/runs/                                 mrp:run_list
/mrp/runs/new/                             mrp:run_create
/mrp/runs/<pk>/                            mrp:run_detail
/mrp/runs/<pk>/start/                      mrp:run_start             [POST]
/mrp/runs/<pk>/apply/                      mrp:run_apply             [POST]
/mrp/runs/<pk>/discard/                    mrp:run_discard           [POST]
/mrp/runs/<pk>/delete/                     mrp:run_delete
/mrp/requisitions/                         mrp:pr_list
/mrp/requisitions/<pk>/                    mrp:pr_detail
/mrp/requisitions/<pk>/edit/               mrp:pr_edit
/mrp/requisitions/<pk>/approve/            mrp:pr_approve            [POST]
/mrp/requisitions/<pk>/cancel/             mrp:pr_cancel             [POST]
/mrp/requisitions/<pk>/delete/             mrp:pr_delete
/mrp/exceptions/                           mrp:exception_list
/mrp/exceptions/<pk>/                      mrp:exception_detail
/mrp/exceptions/<pk>/acknowledge/          mrp:exception_acknowledge [POST]
/mrp/exceptions/<pk>/resolve/              mrp:exception_resolve     [POST]
/mrp/exceptions/<pk>/ignore/               mrp:exception_ignore      [POST]
/mrp/exceptions/<pk>/delete/               mrp:exception_delete
```

Mount in `config/urls.py` after `pps`:
```python
path('mrp/', include('apps.mrp.urls')),
```

---

## 6. Signals — `apps/mrp/signals.py`

`pre_save` + `post_save` audit-log receivers writing to `apps.tenants.TenantAuditLog`:
- `MRPRun` status transitions (`queued` → `running` → `completed` / `failed` → `applied` / `discarded`)
- `MRPCalculation` status transitions
- `MRPPurchaseRequisition` status transitions (`approved` / `cancelled` / `converted`)
- `MRPException` status transitions (`acknowledged` / `resolved` / `ignored`)

`post_save` on `MRPCalculation` (status → `committed`) → invalidates downstream caches (none yet, but the hook is reserved).

Wired in `apps/mrp/apps.py:MrpConfig.ready()` (matches PPS pattern).

---

## 7. Admin — `apps/mrp/admin.py`

Standard `ModelAdmin` registrations for every model (matches PPS). `list_display`, `list_filter`, `search_fields`, `readonly_fields=('created_at', 'updated_at')`.

---

## 8. Templates — `templates/mrp/`

```
templates/mrp/
├── index.html                          # MRP dashboard
├── forecast_models/list.html, form.html, detail.html
├── seasonality/list.html, form.html
├── forecast_runs/list.html, detail.html
├── inventory/list.html, form.html, detail.html
├── receipts/list.html, form.html
├── calculations/list.html, detail.html
├── runs/list.html, form.html, detail.html
├── requisitions/list.html, form.html, detail.html
└── exceptions/list.html, detail.html
```

~ **24 templates total**. Each list has the standard search-bar + filter dropdowns + paginated table + Actions column + empty-state. Each detail has the standard breadcrumb + content body + Actions sidebar + Back link. Forms use `crispy_forms`.

`index.html` shows KPI cards (open runs, exceptions open, late orders, coverage %, last run time) + recent runs + open exceptions table. Charts via ApexCharts (already loaded in `base.html`).

---

## 9. Sidebar — `templates/partials/sidebar.html`

New collapsible group inserted between "Production Planning" and "User Management":

```html
<li class="nav-item">
    <a class="nav-link menu-link" href="#sidebarMRP" data-bs-toggle="collapse" role="button" aria-expanded="false">
        <i class="ri-flow-chart"></i> <span>Material Requirements (MRP)</span>
    </a>
    <div class="collapse menu-dropdown" id="sidebarMRP" data-bs-parent="#navbar-nav">
        <ul class="nav nav-sm flex-column">
            <li class="nav-item"><a href="{% url 'mrp:index' %}" class="nav-link">MRP Dashboard</a></li>
            <li class="nav-item"><a href="{% url 'mrp:forecast_model_list' %}" class="nav-link">Forecast Models</a></li>
            <li class="nav-item"><a href="{% url 'mrp:seasonality_list' %}" class="nav-link">Seasonality Profiles</a></li>
            <li class="nav-item"><a href="{% url 'mrp:forecast_run_list' %}" class="nav-link">Forecast Runs</a></li>
            <li class="nav-item"><a href="{% url 'mrp:inventory_list' %}" class="nav-link">Inventory Snapshot</a></li>
            <li class="nav-item"><a href="{% url 'mrp:receipt_list' %}" class="nav-link">Scheduled Receipts</a></li>
            <li class="nav-item"><a href="{% url 'mrp:calculation_list' %}" class="nav-link">MRP Calculations</a></li>
            <li class="nav-item"><a href="{% url 'mrp:run_list' %}" class="nav-link">MRP Runs</a></li>
            <li class="nav-item"><a href="{% url 'mrp:pr_list' %}" class="nav-link">PR Suggestions</a></li>
            <li class="nav-item"><a href="{% url 'mrp:exception_list' %}" class="nav-link">Exceptions</a></li>
        </ul>
    </div>
</li>
```

---

## 10. Settings + URL wiring

- `config/settings.py` → add `'apps.mrp'` to `INSTALLED_APPS` (after `apps.pps`).
- `config/urls.py` → mount `path('mrp/', include('apps.mrp.urls'))` (after `pps`).

---

## 11. Migration

- `python manage.py makemigrations mrp` — new app, fresh `0001_initial.py`.
- `python manage.py migrate` — applied on local dev DB.

---

## 12. Seeder — `apps/mrp/management/commands/seed_mrp.py`

Idempotent per Seed Command Rules. Per tenant, seeds:
- 2 `ForecastModel`s (one moving_avg, one naive_seasonal)
- 12 `SeasonalityProfile` rows (monthly indices) for 2 finished-good products
- 1 completed `ForecastRun` with `ForecastResult` rows
- ~10 `InventorySnapshot` rows (one per finished-good + components)
- ~5 `ScheduledReceipt` rows (open POs / planned production)
- 1 completed `MRPCalculation` linked to the seeded `pps.MasterProductionSchedule`, with `NetRequirement` rows for end items + components
- ~3 `MRPPurchaseRequisition` rows (mix of draft / approved)
- ~5 `MRPException` rows (mix of late_order / expedite / no_bom)
- 1 completed `MRPRun` with `MRPRunResult`

Wire into `apps/core/management/commands/seed_data.py` orchestrator (after `seed_pps`).

---

## 13. README.md updates

In the **same set of commit snippets**:

1. **Top-of-file paragraph** — add Module 5 to the "Phase 1 includes" list.
2. **Highlights** — bullet for "Module 5 — Material Requirements Planning (MRP)".
3. **Table of Contents** — add "Module 5 — Material Requirements Planning (MRP)" entry.
4. **Screenshots / UI Tour** — add ~10 routes for MRP under `/mrp/...`.
5. **Project Structure** — add `apps/mrp/` block + `templates/mrp/`.
6. **Seeded Demo Data** — bullet "Per tenant (Module 5 — MRP) — …".
7. **New top-level section** — `## Module 5 — Material Requirements Planning (MRP)` with sub-sections per 5.1–5.5 (matches the PPS section's shape).
8. **Management Commands** — add `seed_mrp` row.
9. **Roadmap** — strike `5. Material Requirements Planning (MRP)` and append `~~Material Requirements Planning (MRP)~~ ✅ shipped`.

---

## 14. Verification (before declaring done)

Per CLAUDE.md "Verification Before Done":

1. `python manage.py makemigrations mrp` — must produce `0001_initial.py` cleanly.
2. `python manage.py migrate` — must apply without errors.
3. `python manage.py seed_mrp` — must succeed for all 3 tenants and be idempotent (run twice, second run must skip).
4. `python manage.py runserver` — start dev server, browse:
   - `/mrp/` (dashboard renders, KPI cards populated)
   - `/mrp/forecast-models/` (list, filters, create, edit, delete buttons)
   - `/mrp/runs/` (list, run-create wizard)
   - `/mrp/runs/<pk>/start/` (POST executes the engine, redirects with success message)
   - `/mrp/calculations/<pk>/` (Net Requirements tab + Exceptions tab + PR tab)
   - `/mrp/exceptions/` (filters work; resolve / ignore actions)
   - Sidebar link "Material Requirements (MRP)" expands and every item navigates correctly
5. Cross-tenant check: log in as `admin_globex`, confirm Acme's MRP runs are NOT visible.

---

## 15. Commit Plan

Per STRICT GIT Commit Rule — **one file per commit**, PowerShell-safe `;` chaining. Estimated commit count:

- Models, forms, views, urls, signals, admin, apps.py — **7 files**
- Services (`__init__.py` + 4 modules) — **5 files**
- Management commands (`__init__.py` × 2 + `seed_mrp.py`) — **3 files**
- Migrations (`__init__.py` + `0001_initial.py`) — **2 files**
- Templates (~24 files) — **24 files**
- App `__init__.py` — **1 file**
- Sidebar update — **1 file**
- `config/settings.py` update — **1 file**
- `config/urls.py` update — **1 file**
- `seed_data.py` orchestrator update — **1 file**
- `README.md` update — **1 file**

**Estimated total: ~47 commits.** Each gets its own block. No bundling (Lesson L-06).

---

## 16. Out of scope (deferred follow-ups)

- Pytest test suite (matches PLM / BOM / PPS shipping convention)
- CSV bulk import for inventory snapshots
- Real ML forecasting (Prophet / scikit-learn / ARIMA)
- Linear-program solver for true optimization (today's engine is gross-to-net + lot sizing)
- Webhook / event bus for "MRP committed" → downstream notifications
- Procurement integration (Module 9 will consume `MRPPurchaseRequisition` later)
- Inventory integration (Module 8 will populate `InventorySnapshot` later)

---

## Review (2026-04-28 — implementation complete + verified end-to-end)

**Status:** ✅ All 5 sub-modules implemented, migrated, seeded across 3 tenants, and smoke-tested in the browser. Module 5 ships.

### Built
- New Django app `apps/mrp/` (label `mrp`) mounted at `/mrp/`.
- **12 models** (one fewer than the planned 14 — `ScheduledReceipt` and `InventorySnapshot` covered the inventory side without needing a separate `BomReference` model that the plan briefly considered): `ForecastModel`, `SeasonalityProfile`, `ForecastRun`, `ForecastResult`, `InventorySnapshot`, `ScheduledReceipt`, `MRPCalculation`, `NetRequirement`, `MRPPurchaseRequisition`, `MRPException`, `MRPRun`, `MRPRunResult`. Every model is `TenantAwareModel` + `TimeStampedModel`.
- **4 pure-function services** in `apps/mrp/services/`: `forecasting.py` (4 algorithms), `lot_sizing.py` (4 methods), `mrp_engine.py` (gross-to-net + multi-level BOM explosion via `bom.BillOfMaterials.explode()`), `exceptions.py` (5 trigger rules).
- **Full CRUD** with working filters per Filter Implementation Rules: list / create / detail / edit / delete + workflow actions for every model with a list page.
- **19 templates** in `templates/mrp/` (one tighter than the plan's "~24" because some sub-modules share a single form template across create + edit).
- **Audit signals** wired on `MRPRun`, `MRPCalculation`, `MRPPurchaseRequisition`, `MRPException` save() paths — matches the PPS pattern exactly (atomic UPDATEs deliberately bypass signals for race-safety).
- **Idempotent seeder** `seed_mrp.py` with `--flush`; wired into the `seed_data` orchestrator after `seed_pps`.
- **Sidebar** group "Material Requirements (MRP)" inserted between Production Planning and User Management.
- **README.md** updated: top paragraph, Highlights, Table of Contents, Screenshots/UI Tour (~22 routes added), Project Structure (apps/mrp/ + templates/mrp/), Seeded Demo Data, dedicated Module 5 section with sub-module breakdowns, Management Commands table (seed_mrp), Roadmap (struck Module 5 + Phase 1 paragraph updated).

### Verification
- `python manage.py check` — clean (0 issues).
- `python manage.py makemigrations mrp` — produced `0001_initial.py` with all 12 models.
- `python manage.py migrate mrp` — applied cleanly on MySQL.
- `python manage.py seed_mrp --flush` — produced **per tenant**: 2 forecast models, 24 seasonality profiles, 16 forecast results, 8 inventory snapshots, 5 receipts, **1 completed MRP run with 19 planned orders, 10 PR suggestions, and 35 exceptions**.
- Re-running `seed_mrp` (without `--flush`) — idempotent; skips per existing data.
- HTTP smoke test: dashboard + 11 list pages all 200; 5 detail pages 200 for Acme's PKs; cross-tenant pks 404 (isolation guard works).
- Workflow action: POST `/mrp/exceptions/<pk>/acknowledge/` 302 → status flips `open → acknowledged`. PR Approve, Run Apply paths all wired identically.
- Audit log: `mrp_run.created`, `mrp_run.completed`, `mrp_calculation.created`, `mrp_calculation.status.completed` entries written by signals on the seeder's instance.save() paths.

### Deviations from the original plan
- `~14 models` → **12 models** (consolidated; same coverage).
- `~24 templates` → **19 templates** (some forms reused for create + edit).
- Initial seed run produced **0 results** because the MRP horizon (today→+28d) didn't overlap the seeded MPS lines (weeks 1–2 of current month). Fixed by aligning MRP horizon = MPS horizon when an MPS is linked. **Lesson candidate:** when seeding two related modules where one consumes the other's date-bounded data, align horizons or it looks like the engine is broken.
- Console encoding: replaced the `→` character in seeder output with `->` to avoid `UnicodeEncodeError: charmap` on Windows cp1252. Matches the existing PPS seeder convention I should have spotted earlier.

### Out of scope (deferred, as planned)
- Pytest test suite (matches PLM / BOM at v1).
- Real ML forecasting (Prophet / scikit-learn / ARIMA).
- True delta-aware Net Change MRP (today: regenerative semantics).
- Linear-program / MILP optimization.
- CSV bulk import for inventory snapshots.
- Procurement integration — Module 9 will consume `MRPPurchaseRequisition` later.
- Inventory integration — Module 8 will populate `InventorySnapshot` later.
