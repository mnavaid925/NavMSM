# Plan — Module 4: Production Planning & Scheduling

> Status: **COMPLETE — all 5 sub-modules implemented, migrated, seeded across 3 tenants, smoke-tested**
> Created: 2026-04-26
> Completed: 2026-04-27
> Pattern reference: Module 3 (BOM) — newest, cleanest example in the repo. Mirror its layout exactly.

## Goal
Build **Module 4 — Production Planning & Scheduling** as a new Django app `apps/pps/`, following the conventions established by `apps/plm/` and `apps/bom/` (multi-tenant, full CRUD, signals, idempotent seeder, sidebar entry, README update).

## Sub-modules to Implement
| # | Sub-Module | Core Capability |
|---|---|---|
| 4.1 | Master Production Schedule (MPS) | Demand forecasts + firm/planned production lines per product per period |
| 4.2 | Capacity Planning | Work centers, calendars, capacity load chart, bottleneck flagging |
| 4.3 | Finite & Infinite Scheduling | Routings, production orders, forward/backward/infinite scheduling, Gantt view |
| 4.4 | What-If Simulation | Scenario clone of MPS with changes, computed KPI deltas, apply/discard |
| 4.5 | Advanced Planning & Optimization | Objective-weighted greedy optimizer (changeover/idle/lateness/priority); deterministic stub |

---

## 0. Open questions for user approval (please confirm before I start coding)

1. **App label** — `pps` (Production Planning & Scheduling), URL prefix `/pps/`. **OK?**
2. **AI/ML in 4.5** — ship as a **deterministic, rules-based optimizer stub** (greedy heuristic that minimizes changeovers + lateness), not a trained model. The data model + UI is real; the algorithm is a pluggable heuristic. **OK to defer real ML to a follow-up phase, same way the payment gateway is mock-only?**
3. **Gantt rendering** — use the existing **ApexCharts `rangeBar`** chart type (already loaded in base.html). No new dependencies. **OK?**
4. **Pytest test suite** — **defer to a follow-up** (matches how PLM and BOM shipped — manual test plan only at v1). **OK?**
5. **Currency** — single `USD` field on `WorkCenter.cost_per_hour` (matches BOM cost elements). **OK?**
6. **Reuse vs duplication** — production orders link to `plm.Product` and (optionally) `bom.BillOfMaterials`. We do **not** rebuild the part master or BOM. **OK?**

If you reply "do what you think best" I'll proceed with all six defaults.

---

## 1. Models — `apps/pps/models.py` (~14 models, sectioned banners like BOM)

All inherit from `TenantAwareModel, TimeStampedModel`. Reuse `apps.plm.models.Product` and `apps.bom.models.BillOfMaterials`.

### 4.1 MPS
- **`DemandForecast`**
  - `product` FK→`plm.Product`, `period_start`, `period_end`, `forecast_qty` decimal, `source` (`manual`/`sales_order`/`historical`), `confidence_pct` decimal, `notes`
- **`MasterProductionSchedule`** (header)
  - `mps_number` auto `MPS-00001` per tenant, `name`, `horizon_start`, `horizon_end`, `time_bucket` (`day`/`week`/`month`), `status` (`draft`/`under_review`/`approved`/`released`/`obsolete`), `description`, `created_by`, `approved_by`, `approved_at`, `released_at`
  - Unique: `(tenant, mps_number)`
- **`MPSLine`**
  - `mps` FK, `product` FK→`plm.Product`, `period_start`, `period_end`, `forecast_qty`, `firm_planned_qty`, `scheduled_qty`, `available_to_promise`, `notes`
  - Unique: `(mps, product, period_start)`

### 4.2 Capacity
- **`WorkCenter`**
  - `code` (unique per tenant), `name`, `work_center_type` (`machine`/`labor`/`cell`/`assembly_line`), `capacity_per_hour` decimal, `efficiency_pct` decimal default 100, `cost_per_hour` decimal, `description`, `is_active`
- **`CapacityCalendar`** (one row per shift per weekday per work center)
  - `work_center` FK, `day_of_week` 0–6, `shift_start` Time, `shift_end` Time, `is_working` bool
  - Unique: `(work_center, day_of_week, shift_start)`
- **`CapacityLoad`** (computed snapshot — recomputable)
  - `work_center` FK, `period_date`, `available_minutes`, `planned_minutes`, `utilization_pct` decimal, `is_bottleneck` bool, `computed_at`

### 4.3 Scheduling
- **`Routing`**
  - `routing_number` auto `ROUT-00001` per tenant, `product` FK→`plm.Product`, `version`, `is_default`, `status` (`draft`/`active`/`obsolete`), `description`, `created_by`
  - Unique: `(tenant, product, version)`
- **`RoutingOperation`**
  - `routing` FK, `sequence` int, `operation_name`, `work_center` FK, `setup_minutes`, `run_minutes_per_unit`, `queue_minutes`, `move_minutes`, `instructions`
- **`ProductionOrder`**
  - `order_number` auto `PO-00001` per tenant, `mps_line` nullable FK, `product` FK, `routing` nullable FK, `bom` nullable FK→`bom.BillOfMaterials`, `quantity`, `status` (`planned`/`released`/`in_progress`/`completed`/`cancelled`), `priority` (`low`/`normal`/`high`/`rush`), `scheduling_method` (`forward`/`backward`/`infinite`), `requested_start`, `requested_end`, `scheduled_start`, `scheduled_end`, `actual_start`, `actual_end`, `created_by`, `notes`
- **`ScheduledOperation`** (created/destroyed by scheduler service)
  - `production_order` FK, `routing_operation` FK, `work_center` FK (denormalized for queries), `sequence`, `planned_start`, `planned_end`, `planned_minutes`, `status` (`pending`/`in_progress`/`completed`/`skipped`), `notes`

### 4.4 Simulation
- **`Scenario`**
  - `name`, `description`, `base_mps` FK, `status` (`draft`/`running`/`completed`/`applied`/`discarded`), `created_by`, `ran_at`, `applied_at`, `applied_by`
- **`ScenarioChange`**
  - `scenario` FK, `change_type` (`add_order`/`remove_order`/`change_qty`/`change_date`/`change_priority`/`shift_resource`), `target_ref` (e.g. `mps_line:42`), `payload` JSON, `sequence`
- **`ScenarioResult`** (OneToOne)
  - `scenario` OneToOne, `on_time_pct`, `total_load_minutes`, `total_idle_minutes`, `bottleneck_count`, `summary_json`, `computed_at`

### 4.5 APO
- **`OptimizationObjective`**
  - `name`, `weight_changeovers`, `weight_idle`, `weight_lateness`, `weight_priority`, `is_default`
- **`OptimizationRun`**
  - `name`, `mps` FK, `objective` FK, `status` (`queued`/`running`/`completed`/`failed`), `started_at`, `finished_at`, `started_by`, `error_message`
- **`OptimizationResult`** (OneToOne)
  - `run` OneToOne, `before_total_minutes`, `after_total_minutes`, `before_changeovers`, `after_changeovers`, `before_lateness`, `after_lateness`, `improvement_pct`, `suggestion_json`, `applied_at`, `applied_by`

### Helper methods
- `MasterProductionSchedule.is_editable()` — True for draft/under_review.
- `ProductionOrder.schedule_forward()` / `schedule_backward()` — call into `services/scheduler.py`.
- `WorkCenter.recompute_load(date_from, date_to)` — refresh `CapacityLoad` rows.

---

## 2. Services (small, isolated, testable)

- **`apps/pps/services/scheduler.py`**
  - `schedule_forward(order, *, start)` — pure function, walks `RoutingOperation`s in sequence, allocates minutes onto the work center's calendar, returns a list of `ScheduledOperation` payloads. Caller persists.
  - `schedule_backward(order, *, end)` — symmetric.
  - `compute_load(work_center, date_from, date_to)` — returns dict per date: `{available, planned, utilization, is_bottleneck}`.
  - No ORM imports at module level — querysets passed in. Keeps the algorithm unit-testable later.
- **`apps/pps/services/simulator.py`**
  - `apply_scenario(scenario)` — clones MPS lines into scratch dicts, applies `ScenarioChange`s, runs `compute_load` against scratch, returns a `ScenarioResult` payload. Never mutates real data.
- **`apps/pps/services/optimizer.py`**
  - `run_optimization(run)` — greedy heuristic for v1: groups production orders by product to minimize changeovers, left-shifts to minimize idle, respects priority. Returns `OptimizationResult` payload + suggestion JSON. Caller persists.

---

## 3. Forms — `apps/pps/forms.py`
ModelForms with crispy bootstrap5 for every model with a user-facing form. Cross-field validation:
- `MasterProductionSchedule.horizon_end > horizon_start`
- `RoutingOperation.work_center` must be `is_active=True`
- `ScenarioChange.target_ref` must reference an existing `MPSLine` of the scenario's `base_mps`.
- `OptimizationObjective`: at least one weight > 0.

Component dropdowns filtered to `Product.objects.filter(tenant=…, status='active')`.

---

## 4. Views — `apps/pps/views.py` (CBVs, mirrors `apps/bom/views.py`)

Full CRUD per the project's CRUD Completeness Rules for: `DemandForecast`, `MasterProductionSchedule`, `MPSLine`, `WorkCenter`, `CapacityCalendar`, `Routing`, `RoutingOperation`, `ProductionOrder`, `Scenario`, `ScenarioChange`, `OptimizationObjective`, `OptimizationRun`.

Workflow / action views:
- `MPSSubmitView`, `MPSApproveView`, `MPSReleaseView`, `MPSObsoleteView`
- `OrderReleaseView`, `OrderStartView`, `OrderCompleteView`, `OrderCancelView`
- `OrderScheduleView` (POST: forward/backward/infinite)
- `CapacityRecomputeView`
- `ScenarioRunView`, `ScenarioApplyView`, `ScenarioDiscardView`
- `OptimizationStartView`, `OptimizationApplyView`, `OptimizationDiscardView`

Special views:
- `PPSIndexView` — KPI dashboard (open MPS, planned vs released orders, bottleneck count, last optimization gain)
- `CapacityDashboardView` — per-work-center load chart (ApexCharts column)
- `OrderGanttView` — Gantt page (ApexCharts rangeBar) filterable by work center + date range

All views use `LoginRequiredMixin`, filter by `tenant=request.tenant`, and follow the Filter Implementation Rules:
- Pass `status_choices`, FK querysets, type/method choice lists to templates.
- Apply filters before pagination.
- Use `|stringformat:"d"` for FK pk comparisons in templates.

---

## 5. URLs — `apps/pps/urls.py`

App namespace `pps`, mounted at `/pps/` in `config/urls.py`. Full list in §3 of the working spec — covers list / create / detail / edit / delete for every CRUD model plus all workflow/action endpoints (POST-only) plus Gantt + capacity dashboard.

---

## 6. Signals — `apps/pps/signals.py`

`pre_save` + `post_save` writers writing to `apps.tenants.TenantAuditLog`:
- `MasterProductionSchedule` — `mps.created`, `mps.status.<new>`
- `ProductionOrder` — `order.created`, `order.status.<new>`
- `Scenario` — `scenario.applied`, `scenario.discarded`
- `OptimizationRun` — `optimization.started`, `optimization.completed`, `optimization.failed`

Plus: `post_save`/`post_delete` on `ScheduledOperation` invalidates the relevant `CapacityLoad.computed_at` (UI shows it as stale until recomputed — same pattern as BOM rollup staleness).

---

## 7. Admin — `apps/pps/admin.py`
Register all models with `list_display` / `list_filter` / `search_fields`.

---

## 8. Templates — `templates/pps/`

Mirroring BOM:
- `index.html` — KPI dashboard
- `forecasts/list.html`, `form.html`, `detail.html`
- `mps/list.html`, `form.html`, `detail.html` (tabs: Lines / Status History)
- `mps_lines/form.html`
- `work_centers/list.html`, `form.html`, `detail.html`
- `capacity/dashboard.html` — load chart
- `calendars/list.html`, `form.html`
- `routings/list.html`, `form.html`, `detail.html`
- `routing_operations/form.html`
- `orders/list.html`, `form.html`, `detail.html`, `gantt.html`
- `scenarios/list.html`, `form.html`, `detail.html`
- `scenario_changes/form.html`
- `optimizer/objective_list.html`, `objective_form.html`, `run_list.html`, `run_form.html`, `run_detail.html`

Every list template carries Actions column; every detail template carries Actions sidebar — per CRUD Completeness Rules.

---

## 9. Seeder — `apps/pps/management/commands/seed_pps.py`

Idempotent (per CLAUDE.md seed rules — gate on `MasterProductionSchedule.objects.filter(tenant=tenant).exists()`). Per tenant:
- 4 work centers (one each: machine / labor / cell / assembly_line) + Mon–Fri 08:00–17:00 calendars.
- 1 routing per seeded finished-good with 3–5 operations.
- 8 demand forecasts spanning 4 weeks across 4 products.
- 1 MPS (`released`) covering 4 weeks with 8 lines.
- 6 production orders in mixed statuses (planned / released / in_progress / completed); `services/scheduler.schedule_forward()` populates `ScheduledOperation` rows for the released ones.
- 1 capacity load snapshot computed via `services/scheduler.compute_load()`.
- 1 scenario with 2 changes + computed result (`completed`).
- 1 default `OptimizationObjective` + 1 completed `OptimizationRun` with result.

Hook `seed_pps` into `apps/core/management/commands/seed_data.py`'s orchestrator (after `seed_bom`).

Print: tenant admin login + superuser-has-no-tenant warning.

---

## 10. Migrations
- `python manage.py makemigrations pps`
- `python manage.py migrate`

## 11. Sidebar — `templates/partials/sidebar.html`
New `<li>` block "Production Planning" between BOM and User Management. Icon `ri-calendar-schedule-line`. Sub-links:
PPS Dashboard · Demand Forecasts · Master Production Schedule · Work Centers · Capacity Calendars · Capacity Load · Routings · Production Orders · Gantt Schedule · Scenarios · Optimizer

## 12. Settings — `config/settings.py`
Add `'apps.pps'` to `INSTALLED_APPS` (after `'apps.bom'`).

## 13. Root URL — `config/urls.py`
Add `path('pps/', include('apps.pps.urls'))`.

## 14. README.md (MANDATORY per project rules)
- Update intro line: "Phase 1 ... Module 4 — Production Planning & Scheduling"
- Highlights bullet for Module 4
- Mark Module 4 as ✅ shipped in Roadmap
- New dedicated **Module 4 — Production Planning & Scheduling** section between Module 3 and "UI / Theme Customization"
- Project Structure tree: add `apps/pps/` and `templates/pps/`
- Screenshots / UI Tour table: add all `/pps/...` routes
- Management Commands table: add `seed_pps`
- Seeded Demo Data: per-tenant PPS bullet (work centers, MPS, orders, scenario, optimization run)
- Update Table of Contents

## 15. Per-File Git Commit Snippets
Provide a copy-paste block at the end (PowerShell-safe with `;`), one commit per file.

---

## Out of Scope (v1)
- Real ML/AI optimizer (4.5 is a deterministic heuristic stub).
- WebSocket-driven Gantt updates (refresh on action).
- ERP / MES integration.
- Drag-to-reschedule on the Gantt (POST-only reschedule action).
- CSV / Excel import / export.
- Pytest test suite (matches PLM/BOM v1; can follow up).
- Multi-currency on work-center costs.

---

## Verification Steps Before Marking Done
1. `python manage.py makemigrations pps` → single clean migration.
2. `python manage.py migrate` → succeeds.
3. `python manage.py seed_pps` → first run seeds; second run idempotent.
4. `python manage.py seed_data` orchestrator runs end-to-end.
5. Log in as `admin_acme` → sidebar shows Production Planning group → every link 200s.
6. Capacity dashboard renders ApexCharts column chart.
7. Gantt page renders ApexCharts rangeBar.
8. Forward-schedule one production order → `ScheduledOperation` rows visible on the order detail.
9. Run one scenario → `ScenarioResult` created, KPI deltas displayed.
10. Run one optimization → `improvement_pct` populated; suggestion JSON viewable.
11. Cross-tenant test: `admin_globex` cannot see `admin_acme` MPS / orders.
12. README renders correctly; TOC matches; per-file commit snippets generated.

---

## Implementation Checklist (for tracking once approved)
- [ ] Create `apps/pps/` skeleton (`__init__.py`, `apps.py`, `migrations/`, `management/commands/`, `services/`)
- [ ] Add `'apps.pps'` to `INSTALLED_APPS`
- [ ] Write `models.py` (~14 models)
- [ ] Write `services/scheduler.py`, `simulator.py`, `optimizer.py`
- [ ] Write `forms.py`
- [ ] Write `views.py`
- [ ] Write `urls.py`
- [ ] Write `signals.py` + wire in `apps.py.ready()`
- [ ] Write `admin.py`
- [ ] Mount `pps/` in `config/urls.py`
- [ ] Build templates in `templates/pps/`
- [ ] Add sidebar entry
- [ ] Write `seed_pps.py`
- [ ] Hook `seed_pps` into `seed_data.py`
- [ ] `makemigrations` + `migrate`
- [ ] Run `seed_pps` end-to-end (twice — idempotency check)
- [ ] Smoke-test in browser as `admin_acme`
- [ ] Update `README.md`
- [ ] Hand user per-file PowerShell-safe git commit snippets

---

## Review

User approved with "go ahead", proceeded with all 6 default decisions:
1. App label `pps` at `/pps/`.
2. 4.5 ships as a deterministic greedy heuristic stub (priority-bucket sort, group-by-product within bucket).
3. Gantt via existing ApexCharts `rangeBar`, no new dependencies.
4. No pytest suite in v1 (matches PLM/BOM v1).
5. Single `USD` cost field on `WorkCenter`.
6. Reuse `plm.Product` and `bom.BillOfMaterials` — no parallel data layer.

**Verification results (run against the seeded `admin_acme` tenant):**

| Check | Result |
|---|---|
| `makemigrations pps` | clean — single `0001_initial.py` covering 16 models |
| `migrate` | applied without warnings |
| `seed_pps` first run | per tenant: 4 work centers + 5 routings + 8 forecasts + 8 MPS lines + 6 production orders + 11 scheduled ops + 56 capacity-load snapshots + 1 scenario + 1 default objective + 1 completed optimizer run |
| `seed_pps` second run | idempotent — "PPS data already exists, skipping" per tenant |
| `seed_data` orchestrator | runs end-to-end; `seed_pps` registered after `seed_bom` |
| `python manage.py check` | no issues |
| Smoke test — 21 list/create URLs | 21/21 return 200 |
| Smoke test — 5 detail URLs | 5/5 return 200 (filtered by Acme tenant) |
| Cross-tenant guard | `admin_globex` requesting `admin_acme` MPS → 404 (expected) |
| Forward scheduling | released `PO-00003` carries 3 `ScheduledOperation` rows laid down across CNC-01 / LBR-01 / LINE-01 |
| Capacity dashboard | ApexCharts column chart + 95% bottleneck threshold annotation render |
| Gantt page | ApexCharts `rangeBar` renders for the 14-day window |
| Scenario simulation | seeded scenario carries `on_time_pct=92.50`, 2 changes, 1 result |
| Optimizer run | seeded run completed successfully (0% gain on the seeded set — orders already grouped by product, which is the correct heuristic outcome) |
| Sidebar | new "Production Planning" group expanded between BOM and User Management with 12 nav links |
| README | TOC + Highlights + UI Tour + Project Structure + Module 4 section + Mgmt Commands + Seeded Demo Data + Roadmap all updated; Phase 1 description now lists Modules 1-4; remaining-modules count corrected from 19 to 18 |

**What got built:**

- 16 models in [`apps/pps/models.py`](apps/pps/models.py) (~640 LOC)
- 3 pure-function services in [`apps/pps/services/`](apps/pps/services/) — scheduler (forward / backward / infinite + load summary), simulator (apply_scenario, never mutates), optimizer (greedy heuristic)
- Full CRUD + workflow + Gantt + capacity dashboard views in [`apps/pps/views.py`](apps/pps/views.py) (~870 LOC)
- 25+ templates in [`templates/pps/`](templates/pps/) covering dashboard, forecasts, MPS, work centers, calendars, capacity, routings, orders, Gantt, scenarios, optimizer
- Idempotent [`seed_pps.py`](apps/pps/management/commands/seed_pps.py) seeder with `--flush` support, hooked into the `seed_data` orchestrator
- New "Production Planning" sidebar group with 12 nav links

**One issue caught & fixed during verification:**

- Initial scheduler seed run failed with `TypeError: can't compare offset-naive and offset-aware datetimes` because `timezone.now()` produces aware datetimes (USE_TZ=True) but the calendar arithmetic operated on naive `datetime.combine(date, time)` values. Fix: added `_strip_tz()` / `_attach_tz()` helpers at the public entry/exit points of `schedule_forward` / `schedule_infinite` so the calendar walk stays in naive-time and the persisted slots come back as aware datetimes. Captured the lesson in `.claude/tasks/lessons.md`.

**Things deferred to a follow-up (per the v1 scope agreed in the plan):**

- Real ML/AI optimizer (4.5 is a deterministic heuristic stub; the data model + UI is forward-compatible).
- WebSocket-driven Gantt updates (refresh on action only for now).
- Drag-to-reschedule on the Gantt (POST-only `/orders/<pk>/schedule/` endpoint for now).
- ERP / MES integration.
- CSV / Excel import / export.
- Pytest test suite (matches PLM v1 cadence — manual test plan only at v1).
- Multi-currency on work-center costs (single `USD` for now).
- Real MPS apply (apply scenario / optimization currently records intent in `applied_at` / `applied_by` but does not push changes into the base MPS).

These can be tracked individually whenever you want to schedule them.
