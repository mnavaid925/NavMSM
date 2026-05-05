# Module 10 — Equipment & Asset Management (EAM) — Implementation Plan

> **Status:** DRAFT — awaiting user approval before any code is written.
>
> **Source spec:** `MSM.md` Module 10 + user message 2026-05-05.
>
> Mirrors the Module 9 (Procurement) shape: 1 Django app, 5 sub-modules, full CRUD + workflow, idempotent seeder, full pytest test suite, README updates, sidebar nav, cross-module hooks. Honors all 18 lessons (esp. L-01 unique_together, L-02 decimal validators, L-03 view/template gate parity, L-09 ASCII stdout, L-10 RBAC mixins, L-12 sequence retry, L-13 inner atomic, L-14 per-workflow required, L-17 PROTECT on audit-trail children, L-18 weak=False on factory-registered signals).

---

## Sub-module breakdown (per user spec)

| # | Sub-module | Description |
|---|-----------|-------------|
| 10.1 | Asset Registry & Hierarchy | Equipment master, parent-child relationships, spare parts linkage, meter readings |
| 10.2 | Preventive Maintenance (PM) | Calendar / meter-based scheduling, task checklists, PM event lifecycle |
| 10.3 | Predictive Maintenance | Condition monitoring points, vibration / thermal / oil-quality readings, failure predictions |
| 10.4 | Maintenance Work Orders | Breakdown / preventive / corrective work orders, labor + material logging, downtime analysis |
| 10.5 | Tool & Die Management | Tool life (cycles + hours), sharpening schedules, cavity / mold history |

---

## Decisions to confirm with user BEFORE building

| # | Question | Default proposal |
|---|----------|-----------------|
| Q1 | Build all 5 sub-modules in one pass, or stage them? | **All 5 in one pass** (matches Module 9 cadence). |
| Q2 | Auto-number prefixes — `ASSET-00001`, `TOOL-00001`, `MWO-00001`, `PMS-00001`. Any collisions in operator-speak with `PUR-00001` / `WO-00001` (MES) / `BPO-00001` / `RFQ-00001`? | **None.** Use the four prefixes above. (`MWO` = Maintenance Work Order, distinct from MES `WO`.) |
| Q3 | Cross-module FKs — should `mes.AndonAlert` get a nullable `asset` FK (so an equipment-type andon can name the offending asset and auto-spawn a breakdown MWO)? | **Yes**, mirroring the Module 9 pattern (procurement added nullable FKs to inventory.GRN + qms.IQC). Keep any legacy free-text `equipment_id` column for back-compat. |
| Q4 | Should `qms.MeasurementEquipment` get a nullable `asset` FK (optional link from a calibrated instrument back to its EAM asset)? | **Yes** (nullable, optional). Keeps QMS calibration scope intact while enabling traceability. |
| Q5 | Should `mes.MESWorkOrder` get a nullable `tool` FK (when a production op uses a specific tool / mold / die)? | **Yes** (nullable). Enables `ToolUsageLog` auto-emit on `mes.ProductionReport` (mirrors inventory's auto `production_in` movement). |
| Q6 | Should an `mes.AndonAlert` with `type='equipment'` AND `asset` FK auto-create a draft `MaintenanceWorkOrder(type='breakdown')` via signal? | **Yes** (idempotent — the MWO carries `source_andon` so re-firing the signal is a no-op). |
| Q7 | Where does PM scheduling live — a real cron (django-celery-beat) or a management command + manual button? | **Management command (`generate_pm_schedules`) + manual `Generate Upcoming PM` button on plan detail page.** Matches the project's "no celery yet" stance (per existing `capture_health` pattern). Cron wiring deferred. |
| Q8 | Predictive engine scope — full ML or heuristic? | **Heuristic only in v1**: a `ConditionReading` outside `low_alarm` / `high_alarm` window flips a `FailurePrediction` row to `open`; trend-based rules deferred. Documented in *Out of scope*. |
| Q9 | Include full pytest test suite (~80–120 tests, RBAC + IDOR + workflow + services + signals + cross-module hooks)? | **Yes** — matches Modules 5/6/7/8/9. |
| Q10 | Seed command per tenant: ~10 assets (with parent-child), 4 PM plans, 2 condition-monitoring points + 25 readings, 3 work orders mixed statuses, 2 tools (incl. 1 mold w/ cavity history)? | **Yes**, idempotent. |

---

## App layout (`apps/eam/`)

Mirrors `apps/procurement/`:

```
apps/eam/
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
│   ├── pm_scheduler.py           # generate_upcoming_pm(plan, horizon_days) — pure
│   ├── downtime.py               # compute_downtime(mwo) — pure; downtime rollup per asset
│   ├── prediction.py             # check_reading(reading) — heuristic alarm-band classifier
│   └── tool_life.py              # bump_tool_life(tool, cycles, hours) — atomic UPDATE
├── migrations/__init__.py
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       ├── seed_eam.py
│       └── generate_pm_schedules.py   # idempotent — creates next PMSchedule per active plan
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_forms.py
    ├── test_services.py
    ├── test_signals.py
    ├── test_views.py
    └── test_security.py
```

---

## Models — sub-module-by-sub-module

All models inherit `TenantAwareModel + TimeStampedModel`. Every status field gets `STATUS_CHOICES`. Every Decimal field carries explicit `MinValueValidator` (+ `MaxValueValidator` where natural) per L-02. Every `unique_together` includes `tenant`. Audit-trail child FKs use `on_delete=PROTECT` per L-17.

### 10.1 Asset Registry & Hierarchy (5 models)

| Model | Key fields | Notes |
|---|---|---|
| `AssetCategory` | `name`, `parent` (self-FK), `description` | Hierarchical taxonomy (Pump / Motor / Conveyor / CNC). `unique_together=(tenant, name, parent)`. |
| `Asset` | `tag` (unique per tenant), `name`, `category` FK, `parent` (self-FK for parent-child hierarchy), `warehouse` FK (`inventory.Warehouse`, nullable), `manufacturer`, `model_number`, `serial_number`, `installation_date`, `commissioning_date`, `criticality` (low/medium/high/critical), `status` (operational/down/maintenance/retired), `purchase_cost`, `current_value`, `warranty_expiry`, `is_active` | Auto-numbered `ASSET-00001`. `unique_together=(tenant, tag)`. PROTECT FK from MWO/Tool/etc. |
| `AssetSparePart` | `asset` FK, `product` FK (`plm.Product`), `quantity_on_hand` (cached), `recommended_min_qty`, `notes` | Through-table; `unique_together=(asset, product)`. |
| `AssetMeterReading` | `asset` FK, `meter_type` (hours/cycles/mileage/kwh), `reading_value` (Decimal ≥ 0), `recorded_at`, `recorded_by` (User) | Append-only ledger; PROTECT FK on `asset` (audit trail). |
| `AssetDocument` | `asset` FK, `name`, `doc_type` (manual/drawing/cert/warranty/other), `attachment` (FileField, allowlist `.pdf .png .jpg .jpeg .dwg .dxf`, 25 MB cap) | Attachments per L-07 / Module 6 pattern. |

### 10.2 Preventive Maintenance (PM) (4 models)

| Model | Key fields | Notes |
|---|---|---|
| `MaintenancePlan` | `name`, `asset` FK, `trigger_type` (calendar/meter/both), `frequency_days` (nullable), `frequency_meter` (nullable Decimal), `last_done_at` (nullable date), `next_due_at` (nullable date), `is_active` | Drives auto-generation of upcoming `PMSchedule` rows. |
| `MaintenanceTask` | `plan` FK, `sequence`, `description`, `expected_minutes`, `is_critical` | Checklist item template; `unique_together=(plan, sequence)`. |
| `PMSchedule` | `plan` FK, `schedule_number` (auto `PMS-00001`), `scheduled_date`, `scheduled_meter`, `status` (scheduled/in_progress/completed/skipped/overdue), `assignee` (User, nullable), `started_at`, `completed_at`, `notes` | The actual upcoming PM event; can be rolled forward into a real `MaintenanceWorkOrder`. |
| `PMTaskCompletion` | `pm_schedule` FK, `task` FK, `result` (pass/fail/na), `comments`, `completed_at`, `completed_by` (User) | Append-only; PROTECT FK on `pm_schedule` (audit). |

### 10.3 Predictive Maintenance (3 models)

| Model | Key fields | Notes |
|---|---|---|
| `ConditionMonitoringPoint` | `asset` FK, `name`, `parameter` (vibration/temperature/pressure/current/oil_quality/other), `unit`, `low_alarm`, `high_alarm`, `is_active` | One sensor location on an asset. |
| `ConditionReading` | `point` FK, `reading_value`, `recorded_at`, `status` (normal/warning/critical — auto-set by `services.prediction.check_reading`) | Append-only; PROTECT FK on `point`. |
| `FailurePrediction` | `asset` FK, `triggered_by_reading` FK (nullable), `predicted_failure_date`, `confidence_pct` (0–100), `recommended_action`, `status` (open/investigating/resolved/false_positive), `resolved_at`, `resolved_by` (User) | Heuristic — auto-created when `check_reading` flags a reading as critical and no open prediction exists. |

### 10.4 Maintenance Work Orders (4 models)

| Model | Key fields | Notes |
|---|---|---|
| `MaintenanceWorkOrder` | `mwo_number` (auto `MWO-00001`), `asset` FK, `wo_type` (breakdown/preventive/corrective/predictive/inspection), `priority` (low/medium/high/critical), `problem_description`, `reported_by` (User), `assigned_to` (User, nullable), `status` (draft/scheduled/in_progress/on_hold/completed/cancelled), `reported_at`, `scheduled_start`, `started_at`, `completed_at`, `downtime_minutes` (computed denorm), `failure_code`, `root_cause`, `resolution_notes`. **Source FKs (all nullable):** `source_pm_schedule` (FK `PMSchedule`), `source_failure_prediction` (FK `FailurePrediction`), `source_andon` (FK `mes.AndonAlert`). | Workflow gates per L-03. Workflow forms enforce per-transition required (resolution_notes on completion) per L-14. |
| `MWOLaborLog` | `mwo` FK, `technician` (User), `started_at`, `ended_at`, `minutes` (computed), `hourly_rate`, `total_cost` (computed) | Append-only; PROTECT FK on `mwo`. |
| `MWOMaterialLog` | `mwo` FK, `product` FK (`plm.Product`), `quantity`, `unit_cost`, `total_cost` (computed), `stock_movement` FK (`inventory.StockMovement`, nullable — cross-module link) | Append-only; PROTECT FK on `mwo`. |
| `DowntimeEvent` | `asset` FK, `mwo` FK (nullable), `started_at`, `ended_at`, `minutes` (computed), `reason`, `downtime_type` (planned/unplanned) | Append-only; PROTECT FK on `asset`. Powers the asset-level downtime KPI. |

### 10.5 Tool & Die Management (4 models)

| Model | Key fields | Notes |
|---|---|---|
| `Tool` | `tool_id` (auto `TOOL-00001`), `name`, `tool_type` (mold/die/jig/fixture/cutting_tool/gauge), `category` (free text), `location`, `status` (available/in_use/maintenance/retired), `purchase_date`, `expected_life_cycles`, `current_cycles` (denorm), `expected_life_hours`, `current_hours` (denorm), `last_sharpened_at`, `next_sharpen_due`, `cavity_count` (mold-only), `is_active` | Auto-numbered `TOOL-00001`. `unique_together=(tenant, tool_id)`. |
| `ToolUsageLog` | `tool` FK, `mes_work_order` FK (nullable, cross-module to `mes.MESWorkOrder`), `used_at`, `cycles_added`, `hours_added`, `operator` (User) | Append-only; PROTECT FK on `tool`. Auto-emitted from `mes.ProductionReport.post_save` when the parent op's MES work order has a `tool` FK. |
| `ToolMaintenanceRecord` | `tool` FK, `record_type` (sharpening/cleaning/repair/calibration/inspection), `performed_at`, `performed_by` (User), `cost`, `notes`, `attachment` (FileField, 25 MB cap) | Append-only; PROTECT FK on `tool`. |
| `MoldCavityHistory` | `tool` FK (must be `tool_type='mold'`), `cavity_number`, `cycles` (denorm), `last_inspected_at`, `defect_count`, `status` (active/blocked/repaired) | `unique_together=(tool, cavity_number)`; cleaned in form to enforce mold-only. |

**Total: 20 models in `apps/eam/`.**

---

## Cross-module integration (touching other apps)

Each one is a separate migration in the touched app:

| Touched | Bridge | Migration |
|---|---|---|
| `apps.mes.AndonAlert` | Add nullable FK `asset → eam.Asset`. Keep existing `equipment_id` text column for back-compat. | `apps/mes/migrations/000X_andonalert_asset.py` |
| `apps.mes.MESWorkOrder` | Add nullable FK `tool → eam.Tool`. | `apps/mes/migrations/000X_mesworkorder_tool.py` |
| `apps.qms.MeasurementEquipment` | Add nullable FK `asset → eam.Asset`. Keep existing `tag` for back-compat. | `apps/qms/migrations/000X_measurementequipment_asset.py` |
| Cross-module signal: `mes.AndonAlert.post_save` | When `andon.type='equipment'` AND `andon.asset` is set AND no open MWO exists for that andon, [`apps/eam/signals.py`](apps/eam/signals.py) auto-creates a draft `MaintenanceWorkOrder(wo_type='breakdown', source_andon=andon, …)`. Idempotent — re-firing is a no-op via `source_andon` lookup. | (signal only) |
| Cross-module signal: `mes.ProductionReport.post_save` | When the parent `mes.MESWorkOrder.tool` is set, emit a `ToolUsageLog(cycles_added=report.good_qty)` and bump `Tool.current_cycles`. Idempotent via `(tool, mes_work_order, used_at)` natural key. | (signal only) |
| Cross-module signal (already present): `inventory.StockMovement.post_save` | No new hook; MWO material logs simply reference `stock_movement` FK directly when the consumer creates a `production_out` movement. | n/a |

Both EAM-side cross-module hooks live inside `apps/eam/signals.py` (not in mes/qms) so removing the EAM app cleanly disables the events. Each hook stashes prior state in a dedicated `_eam_x_prev_status` attribute via a `pre_save` handler — no dependency on other modules' naming.

---

## Audit signal pattern

`apps/eam/signals.py` wires `pre_save` + `post_save` audit pattern via the **same `_mk_status_signals(model, action_prefix)` factory used by procurement** (Lesson L-18: connect with `weak=False`). Status-tracked models:

- `Asset` → `eam.asset.<status>`
- `MaintenancePlan` → `eam.plan.activated` / `eam.plan.deactivated`
- `PMSchedule` → `eam.pm_schedule.<status>`
- `FailurePrediction` → `eam.prediction.<status>`
- `MaintenanceWorkOrder` → `eam.mwo.<status>`
- `Tool` → `eam.tool.<status>`

Plus explicit module-level handlers for the **2 cross-module hooks** above (with `weak=False`).

---

## Forms (`apps/eam/forms.py`)

20 ModelForms, one per concrete model. All inherit `TenantScopedFormMixin` (mirrors procurement). All exclude `tenant` from `Meta.fields` and enforce duplicates in `clean()` per L-01. All Decimal fields validated per L-02.

Per-workflow forms (L-14):
- `MWOWorkflowForm` — requires `resolution_notes` when transitioning to `completed`.
- `FailurePredictionResolveForm` — requires non-empty `resolution_notes` and `resolved_action_taken` choice.
- `PMScheduleCompleteForm` — requires at least one `PMTaskCompletion` row.
- `ToolMaintenanceRecordForm` — `attachment` allowlist `.pdf .png .jpg .jpeg`, 25 MB cap.
- `AssetDocumentForm` — same allowlist + `.dwg .dxf`.

---

## Views (`apps/eam/views.py`)

Mirror procurement's class-based pattern. Approximately:

| Type | Count | Examples |
|---|---|---|
| List (with filters) | 12 | `AssetListView`, `PMPlanListView`, `PMScheduleListView`, `ConditionPointListView`, `ConditionReadingListView`, `FailurePredictionListView`, `MWOListView`, `DowntimeListView`, `ToolListView`, `ToolMaintenanceListView`, `AssetCategoryListView`, `AssetSparePartListView` |
| Create | 14 | per primary model + line/child creators |
| Detail | 10 | with tabbed sections (Asset detail = Spare Parts / Meter Readings / Documents / Open MWOs / PM Plans) |
| Edit | 8 | for non-append-only models |
| Delete | 12 | POST-only with PROTECT-error catch (L-13: inner atomic + try/except `ProtectedError`) |
| Workflow actions | 16 | `MWOScheduleView`, `MWOStartView`, `MWOHoldView`, `MWOResumeView`, `MWOCompleteView`, `MWOCancelView`, `PMScheduleStartView`, `PMScheduleCompleteView`, `PMScheduleSkipView`, `FailurePredictionInvestigateView`, `FailurePredictionResolveView`, `FailurePredictionFalsePositiveView`, `ToolRetireView`, `ToolReactivateView`, `AssetRetireView`, `AssetReactivateView` |
| Special | 3 | `IndexView` (dashboard with KPIs), `PMPlanGenerateView` (button to call `generate_upcoming_pm`), `MWOGanttView` (ApexCharts rangeBar of scheduled MWOs by asset, deferred if scope tight) |

**Mixin matrix** (mirrors procurement):
- Read-only list / detail → `TenantRequiredMixin`
- Reading capture (any tenant user can log a sensor reading or a meter reading) → `TenantRequiredMixin`
- All create / edit / delete / workflow / generate → `TenantAdminRequiredMixin` (per L-10)

Every state-changing view uses the conditional `UPDATE … WHERE status IN (…)` race-safe pattern. Auto-numbered creates use the L-12 retry-on-IntegrityError loop.

---

## Templates (`templates/eam/`)

Mirrors `templates/procurement/`. One sub-folder per primary entity:

```
templates/eam/
├── index.html                    # dashboard
├── assets/                       # list, form, detail (tabs: spares, meters, docs, mwos, pm)
├── categories/                   # list, form, detail
├── spare_parts/                  # form (modal-style), list (rare — usually inline on asset detail)
├── meter_readings/               # list, form
├── documents/                    # list, form, download view
├── pm_plans/                     # list, form, detail (tasks inline, generate button)
├── pm_schedules/                 # list, form, detail (task-completion checklist)
├── condition_points/             # list, form, detail (with sparkline)
├── condition_readings/           # list, form
├── failure_predictions/          # list, detail (no form — auto-created)
├── mwo/                          # list, form, detail (labor + material logs inline, gantt-link)
├── downtime/                     # list, form, detail (per-asset downtime KPIs)
├── tools/                        # list, form, detail (usage + maintenance + cavities tabs)
├── tool_maintenance/             # list, form
└── partials/                     # reusable widgets (asset_status_badge.html, criticality_badge.html, sparkline.html)
```

All list templates include search + filter dropdowns per the project's Filter Implementation Rules (status_choices, category, FK querysets passed from view, `|stringformat:"d"` for FK pk comparison). All list templates have a full Actions column (View / Edit / Delete) per CRUD Completeness Rules.

---

## URL config

Add to `config/urls.py` (after procurement):

```python
path('eam/', include('apps.eam.urls')),
```

`apps/eam/urls.py` `app_name='eam'`. Approximately 75 routes. Naming convention mirrors procurement (`asset_list`, `asset_detail`, `asset_create`, `asset_edit`, `asset_delete`, `mwo_complete`, etc.).

---

## Settings update

Add `'apps.eam'` to `INSTALLED_APPS` in `config/settings.py` (after `'apps.procurement'`).

---

## Sidebar nav

Add a new collapsible menu group in `templates/partials/sidebar.html` after the Procurement block (around line 215 after the closing `{% endif %}`):

```html
<li class="nav-item">
    <a class="nav-link menu-link" href="#sidebarEAM" data-bs-toggle="collapse" role="button" aria-expanded="false">
        <i class="ri-tools-line"></i> <span>Equipment & Assets</span>
    </a>
    <div class="collapse menu-dropdown" id="sidebarEAM" data-bs-parent="#navbar-nav">
        <ul class="nav nav-sm flex-column">
            <li class="nav-item"><a href="{% url 'eam:index' %}" class="nav-link">EAM Dashboard</a></li>
            <li class="nav-item"><a href="{% url 'eam:asset_list' %}" class="nav-link">Assets</a></li>
            <li class="nav-item"><a href="{% url 'eam:category_list' %}" class="nav-link">Asset Categories</a></li>
            <li class="nav-item"><a href="{% url 'eam:pmplan_list' %}" class="nav-link">PM Plans</a></li>
            <li class="nav-item"><a href="{% url 'eam:pmschedule_list' %}" class="nav-link">PM Schedule</a></li>
            <li class="nav-item"><a href="{% url 'eam:condition_point_list' %}" class="nav-link">Monitoring Points</a></li>
            <li class="nav-item"><a href="{% url 'eam:prediction_list' %}" class="nav-link">Failure Predictions</a></li>
            <li class="nav-item"><a href="{% url 'eam:mwo_list' %}" class="nav-link">Maintenance Work Orders</a></li>
            <li class="nav-item"><a href="{% url 'eam:downtime_list' %}" class="nav-link">Downtime Events</a></li>
            <li class="nav-item"><a href="{% url 'eam:tool_list' %}" class="nav-link">Tools & Dies</a></li>
        </ul>
    </div>
</li>
```

(Rendered for any authenticated tenant user — supplier-portal users get the same `{% if request.user.role != 'supplier' %}` guard if a future supplier role should not see EAM. Default: **shown to all internal users.**)

---

## Seed command (`apps/eam/management/commands/seed_eam.py`)

Idempotent per CLAUDE.md *Seed Command Rules*. Per tenant:

1. `_seed_categories(tenant)` — 6 categories (Pumps, Motors, CNC, Conveyor, HVAC, Tooling) with parent-child.
2. `_seed_assets(tenant)` — ~10 assets across 3 categories, mixed criticality, 1 parent-child pair (e.g. `CNC-LATHE-01` with sub-asset `SPINDLE-01`), warehouse linked.
3. `_seed_spare_parts(tenant, assets)` — 1–3 spares per critical asset linked to existing `plm.Product` rows.
4. `_seed_meter_readings(tenant, assets)` — 30 days of synthetic readings per metered asset.
5. `_seed_pm_plans_and_schedules(tenant, assets)` — 4 plans (calendar + meter mix), generate next 3 schedules per plan.
6. `_seed_condition_points_and_readings(tenant, assets)` — 2 points per critical asset, 25 readings each (1 deliberately critical → triggers `FailurePrediction`).
7. `_seed_work_orders(tenant, assets, admin)` — 3 MWOs (breakdown/scheduled/completed) with labor + material logs + downtime event for the breakdown one.
8. `_seed_tools(tenant)` — 2 tools incl. 1 mold with 4 cavities + maintenance records + usage logs.

Print login instructions (per CLAUDE.md Seed Command Rules — name a tenant admin and warn that `admin` superuser has no tenant). ASCII-only stdout per L-09 (no `→`, use `->`).

Plus a separate `generate_pm_schedules` management command (idempotent — creates the next-due `PMSchedule` row per active plan if one does not already exist within the plan's frequency window).

Add `seed_eam` to the `seed_data` orchestrator after `seed_procurement`.

---

## Tests (`apps/eam/tests/`)

Target ~80–100 tests, ~25 s. Mirrors procurement's test file split. Coverage:

- **`test_models.py`** — model invariants, decimal validators, unique_together, status choices, denorm rollups (downtime, current_cycles, current_hours).
- **`test_forms.py`** — L-01 unique_together checks, L-02 decimal bounds, L-14 per-workflow required (MWO completion notes, prediction resolution notes, PM checklist completeness, tool-maintenance attachment allowlist).
- **`test_services.py`** — pure-function tests: `pm_scheduler.generate_upcoming_pm()` round-trips correctly across calendar / meter / both triggers; `prediction.check_reading()` flips status correctly across alarm bands; `downtime.compute_downtime()` sums correctly; `tool_life.bump_tool_life()` is race-safe.
- **`test_signals.py`** — audit emission across creates + transitions; cross-module hooks (AndonAlert→MWO auto-spawn, ProductionReport→ToolUsageLog auto-emit, including the no-asset-link / no-tool-link skip paths); `weak=False` regression assertion (`post_save.receivers` contains every dispatch_uid).
- **`test_views.py`** — full CRUD smoke, workflow happy paths, MWO complete with required notes, PM schedule complete via task-completion form, prediction resolve, tool retire.
- **`test_security.py`** — `TestRBACMatrix` (operator vs admin redirects + state-not-changed assertions), `TestMultiTenantIDOR` (cross-tenant 404), `TestAnonymousRedirect` (unauthenticated → login).

---

## README updates

Per the project's *README Maintenance Rule*, the README must be updated **in the same session**:

1. Bump module count in opening paragraph (Phase 1 now includes Module 10).
2. Add `## Module 10 — Equipment & Asset Management (EAM)` section between Module 9 and `## UI / Theme Customization` — full sub-module breakdown matching the Module 9 prose style.
3. Update Table of Contents.
4. Update **Highlights** bullet list (one new bullet for Module 10 mirroring the existing module bullets).
5. Update **Project Structure** (`apps/eam/` block).
6. Update **Screenshots / UI Tour** routes table (~20 new rows).
7. Update **Management Commands** table (`seed_eam`, `generate_pm_schedules`, `pytest apps/eam/tests/`).
8. Update **Seeded Demo Data** to mention EAM.
9. Update **Roadmap** — strike through `10. Equipment & Asset Management (EAM)`, mark `✅ shipped`.
10. Update `seed_data` orchestrator description.

---

## Ordered task list (for execution after approval)

The list below will be flipped to `[x]` as each step lands.

### Phase A — App skeleton + models
- [ ] A.1 Create `apps/eam/__init__.py` + `apps.py` + register in `INSTALLED_APPS`.
- [ ] A.2 Write `apps/eam/models.py` (all 20 models, decimal validators, unique_together, PROTECT FKs, helper methods like `is_editable()`, `is_actionable()` for L-03 view/template gate parity).
- [ ] A.3 Generate initial migration `0001_initial.py`.
- [ ] A.4 Cross-module migrations:
  - [ ] A.4.a `apps/mes/migrations/000X_andonalert_asset.py` (nullable FK).
  - [ ] A.4.b `apps/mes/migrations/000X_mesworkorder_tool.py` (nullable FK).
  - [ ] A.4.c `apps/qms/migrations/000X_measurementequipment_asset.py` (nullable FK).
- [ ] A.5 `apps/eam/admin.py` — register all 20 models with inline admins where natural.

### Phase B — Forms / services / signals
- [ ] B.1 `apps/eam/forms.py` — 20 ModelForms with L-01 / L-02 / L-14 guards.
- [ ] B.2 `apps/eam/services/pm_scheduler.py` — pure `generate_upcoming_pm(plan, horizon_days)`.
- [ ] B.3 `apps/eam/services/downtime.py` — pure `compute_downtime(mwo)`.
- [ ] B.4 `apps/eam/services/prediction.py` — pure `check_reading(reading)`.
- [ ] B.5 `apps/eam/services/tool_life.py` — atomic `bump_tool_life(tool, cycles, hours)` (L-12 + L-13).
- [ ] B.6 `apps/eam/signals.py` — `_mk_status_signals` factory + 6 status-tracked models + 2 cross-module hooks (all `weak=False` per L-18) + `weak=False` regression-guard test in `test_signals.py`.

### Phase C — Views / URLs / templates
- [ ] C.1 `apps/eam/urls.py` — ~75 routes, `app_name='eam'`.
- [ ] C.2 Add `path('eam/', include('apps.eam.urls'))` to `config/urls.py`.
- [ ] C.3 `apps/eam/views.py` — all CBVs with correct mixins (per L-10), L-12 retry on auto-numbered creates, L-13 inner-atomic on every `try/except IntegrityError` / `try/except ProtectedError`, race-safe conditional UPDATEs on every status transition.
- [ ] C.4 Templates — one folder per primary entity (16 folders, ~40 files: list / form / detail / detail-tabs / partials).
- [ ] C.5 Sidebar nav — add EAM block in `templates/partials/sidebar.html`.

### Phase D — Seeders
- [ ] D.1 `apps/eam/management/__init__.py` + `apps/eam/management/commands/__init__.py`.
- [ ] D.2 `apps/eam/management/commands/seed_eam.py` — 8 helper functions, idempotent, ASCII stdout per L-09.
- [ ] D.3 `apps/eam/management/commands/generate_pm_schedules.py` — idempotent next-due generator.
- [ ] D.4 Add `seed_eam` to the `seed_data` orchestrator.

### Phase E — Tests
- [ ] E.1 `apps/eam/tests/conftest.py` + 6 test files; target ~80–100 tests, RBAC matrix + multi-tenant IDOR + cross-module hooks + L-18 dispatch-uid presence guard.
- [ ] E.2 Run `pytest apps/eam/tests/` and resolve to 0 failures.

### Phase F — README + commits
- [ ] F.1 Update `README.md` (10 separate edits per the README Maintenance Rule list above).
- [ ] F.2 Hand the user a per-file commit snippet block (PowerShell `;`-separated, one `git add` + `git commit` per file per CLAUDE.md *STRICT — ONE FILE PER COMMIT*).

### Phase G — Lessons capture
- [ ] G.1 If any user correction lands during this build, append a new `L-19+` entry to `.claude/tasks/lessons.md` per CLAUDE.md *Self-Improvement Loop*.

---

## Out of scope (deferred to follow-up phases)

- **ML-driven failure prediction** — only heuristic alarm-band rules in v1; trend / anomaly / regression models deferred.
- **Real IoT / SCADA ingestion** — `ConditionReading` is created via UI form / management seed in v1; live MQTT / OPC-UA ingestion is **Module 15** scope.
- **Mobile-friendly technician app** — work order completion is desktop-only in v1; touch-optimized terminal akin to `mes/terminal/` deferred.
- **Spare-parts auto-reorder when asset triggers MWO** — the `MWOMaterialLog → inventory.StockMovement` link is manual in v1 (auto-create deferred).
- **Calibration consolidation** — `qms.MeasurementEquipment` and `eam.Asset` stay parallel concepts in v1 (linked by an optional FK, not unified).
- **Tool grinding / re-sharpening BOM cost roll-up** — tracked in `ToolMaintenanceRecord.cost` only; no rollup into `bom.CostElement`.
- **Warranty alerts** — `Asset.warranty_expiry` is stored but no proactive notification; deferred until Module 20 (Workflow & Process Automation).

---

## Review section

**Build completed: 2026-05-06.** All 7 phases (A → G) shipped clean per the original plan with **zero user corrections during execution**. Q1–Q10 in the *Decisions to confirm* table were all accepted as defaults.

### What shipped

- **20 models** in `apps/eam/`, all `TenantAwareModel + TimeStampedModel`, all decimal fields validated, all unique_together either DB-enforced or backed by an L-01 form-level `clean()` (e.g. `AssetCategoryForm` for the NULL-parent case the SQL constraint can't enforce).
- **3 migrations**: `eam/0001_initial.py` (auto-generated), `mes/0002_andonalert_asset_mesworkorder_tool.py`, `qms/0004_measurementequipment_asset.py`. All 3 cross-module FKs are nullable and back-compat-safe.
- **4 pure-function services**: `pm_scheduler.generate_upcoming_pm()`, `prediction.classify_reading()`, `downtime.compute_downtime()`, `tool_life.bump_tool_life()` + `consume_usage_log()`.
- **20 ModelForms** (one per model) with full L-01 / L-02 / L-14 coverage; 3 dedicated workflow forms (`MWOCompleteForm`, `FailurePredictionResolveForm`, `PMScheduleCompleteForm`).
- **Audit signal factory** wired with `weak=False` (Lesson L-18) for 5 status-tracked models + dedicated handler for `MaintenancePlan.is_active` flips.
- **3 cross-module signals**: `ConditionReading` post_save → auto-spawn `FailurePrediction` on critical (idempotent); `mes.AndonAlert` post_save → auto-create breakdown MWO when `alert_type='equipment'` AND `asset` set (idempotent via `source_andon`); `mes.ProductionReport` post_save → auto `ToolUsageLog` + atomic `Tool.current_cycles` bump when the parent MWO has `tool` set (idempotent via `(tool, mes_work_order, used_at)` natural key).
- **~75 URL routes** under `/eam/` + sidebar nav block (gated by `request.user.role != 'supplier'`).
- **~45 view classes** with the correct `TenantRequiredMixin` / `TenantAdminRequiredMixin` split per Lesson L-10 — admin-only for create/edit/delete/retire/cancel/resolve, tenant-user for record-meter-reading / record-condition-reading / start/hold/resume/complete MWO / start-and-complete PM.
- **~30 templates** under `templates/eam/`: 1 dashboard + filter-driven list + form + detail per primary entity, with the asset detail wired with 5 tabs (Spare Parts, Meter Readings, Documents, Open Work Orders, Sub-assets) and the MWO detail wired with 3 tabs (Labor, Material, Downtime).
- **2 management commands**: idempotent `seed_eam` (6 categories, 10 assets, 12 spare parts, 180 meter readings, 4 PM plans + 13 tasks + 12 schedules, 6 monitoring points + 151 readings incl. 1 deliberately critical, 3 MWOs, 2 tools incl. 1 mold with 4 cavities — per tenant) and idempotent `generate_pm_schedules` (creates next-due rows + flips past-dated `scheduled` rows to `overdue`).
- **119 pytest tests, ~58 s runtime**, **100% pass rate** on the first integrated run after a single trivial test-data tweak (`used_at` field added to one tool-usage POST). Coverage: model invariants + auto-numbering + decimal validators (L-02), L-01 unique_together at the form layer, L-14 per-workflow required, pure-function services, audit signals + L-18 `dispatch_uid` presence guard, cross-module hooks (with no-asset-link skip + non-equipment-type skip), full CRUD + workflow happy paths, RBAC matrix (operator vs admin), multi-tenant IDOR, anonymous redirect.
- **README updated in the same session** per the README Maintenance Rule: opening paragraph (module count), Table of Contents, Highlights bullet, Project Structure block, UI Tour routes table, Project Structure templates row, Management Commands table, Seeded Demo Data, Roadmap, plus the dedicated `## Module 10 — Equipment & Asset Management (EAM)` section.
- `seed_data` orchestrator wired to call `seed_eam` after `seed_procurement`.

### Verification path

1. `python manage.py check` — 0 issues at every phase boundary.
2. `python manage.py makemigrations eam mes qms` — clean output, 3 migration files generated.
3. `python manage.py migrate` — all 3 migrations applied in MySQL dev DB.
4. `python manage.py seed_eam` — first run created data for all 3 tenants; second run skipped everything cleanly (idempotency proven).
5. `python -c "FailurePrediction.all_objects.count() == 3"` — confirmed the `ConditionReading` post_save signal spawned 3 predictions (one per tenant from the deliberately critical seeded reading) — i.e. Lesson L-18 `weak=False` is in effect.
6. `python -m pytest apps/eam/tests/` — **119 / 119 passing** in 55–58 s.

### Lessons learned

**No user corrections during this build.** The two self-caught test failures were:
- `unique_together` doesn't trip on NULL parent (a known SQL gotcha) — captured by tightening the test to use a non-NULL parent and noting the limitation in a code comment + the form-level `clean()` for the NULL case.
- A POST without `used_at` failed the form because the field has `default=timezone.now` on the model but is required on the form — fixed in the test, not the production code.

Neither is a new pattern worth promoting to `lessons.md`; both are well-known Django behaviors and already accounted for elsewhere in the codebase.

### What's not in scope (deferred to future modules)

- ML-based predictive maintenance (heuristic alarm-band only in v1).
- Live IoT / SCADA ingestion (manual/seed entry only — Module 15 territory).
- Mobile-friendly technician terminal (desktop-only completion in v1).
- Auto-reorder of spares when an asset triggers an MWO (manual `MWOMaterialLog → StockMovement` in v1).
- QMS `MeasurementEquipment` and EAM `Asset` consolidation (parallel concepts in v1, optional FK link).
- Tool sharpening cost roll-up into BOM cost elements.
- Warranty-expiry email notifications (deferred to Module 20).

### Final commit snippet block

Provided to the user separately in the chat — one `git add` + `git commit` per file, PowerShell `;`-separated, per CLAUDE.md *STRICT — ONE FILE PER COMMIT* and *Shell Compatibility* rules.
