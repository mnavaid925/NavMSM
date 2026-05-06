# Module 11 — Labor & Workforce Management — Implementation Plan

> **Status:** DRAFT — awaiting user approval before any code is written.
>
> **Source spec:** [`MSM.md`](../../MSM.md) Module 11 + user message 2026-05-06.
>
> Mirrors the Module 10 (EAM) shape: 1 Django app (`apps/labor/`), 5 sub-modules, full CRUD + workflow, idempotent seeder, full pytest test suite, README updates, sidebar nav, cross-module hooks. Honors all existing lessons (esp. **L-01** unique_together with tenant excluded, **L-02** decimal validators, **L-03** view/template gate parity, **L-07** `json_script` for inline JS data, **L-09** ASCII stdout in seeders, **L-10** RBAC mixins, **L-12** sequence retry on auto-numbered fields, **L-13** inner-atomic transaction, **L-14** per-workflow required fields, **L-17** PROTECT on audit-trail children, **L-18** `weak=False` on factory-registered signal handlers).

---

## Sub-module breakdown (per user spec)

| # | Sub-module | Description |
|---|-----------|-------------|
| 11.1 | Employee Master & Skills Matrix | Employee profiles, departments, positions, skills catalog, employee-skill mapping, certifications, expiry tracking |
| 11.2 | Time & Attendance Integration | Shifts, shift rosters, attendance records (clock-in/out), leave types, leave requests, holidays |
| 11.3 | Labor Cost Allocation | Cost centers, labor rates (per employee/period), labor bookings (auto-emitted from MES + EAM), allocation reports |
| 11.4 | Training & Competency Management | Training programs, training plans (per employee), training sessions, attendance, competency assessments + results, gap analysis |
| 11.5 | Incentive & Piece-Rate Calculation | Incentive schemes, piece rates (per product / operation / employee), incentive periods, calculation runs, per-employee summaries |

---

## Decisions to confirm with user BEFORE building

| # | Question | Default proposal |
|---|----------|-----------------|
| Q1 | Build all 5 sub-modules in one pass, or stage them? | **All 5 in one pass** (matches Modules 9 + 10 cadence). |
| Q2 | Auto-number prefixes — `EMP-00001` (Employee), `LR-00001` (Leave Request), `LB-00001` (Labor Booking), `TS-00001` (Training Session), `CA-00001` (Competency Assessment), `INC-00001` (Incentive Run). Any collisions? | **None.** `LR` is unused; `LB` is unused; `TS` is unused; `INC` is unused; `CA` collides only with QMS "Corrective Action" (which is not auto-numbered, so safe). |
| Q3 | Relationship to existing `mes.ShopFloorOperator` — that model is already a thin profile over `accounts.User`. Should `labor.Employee` *replace* it, *coexist*, or have `ShopFloorOperator.employee` FK back to the new master? | **Coexist + soft link.** Add nullable FK `mes.ShopFloorOperator.employee → labor.Employee` (one-to-one). MES keeps working unchanged. New `labor.Employee` is the canonical HR master; `ShopFloorOperator` becomes the floor-identity overlay (badge, default work center). Existing seeded shop-floor operators auto-link in the labor seeder. |
| Q4 | Cross-module hooks — should `mes.OperatorTimeLog.post_save (action='stop_job')` auto-emit a `LaborBooking` for the elapsed minutes against the production order's product cost center? | **Yes** (idempotent via `(time_log, kind='direct')` uniqueness). Same shape as the EAM ↔ MES cross-module signals already shipped. |
| Q5 | Cross-module hook — `eam.MWOLaborLog.post_save` → emit a `LaborBooking` to the MWO asset's cost center as **indirect** labor? | **Yes** (idempotent via `(mwo_labor_log, kind='indirect')` uniqueness). Optional/opt-out by leaving `cost_center` blank on the asset. |
| Q6 | Cross-module hook — `mes.ProductionReport.post_save` → if an active piece-rate scheme covers `(product, operation, operator)`, accumulate into the open `IncentiveCalculation`? | **Yes**, but **idempotent**: `(production_report, scheme)` natural-key dedup. If no scheme matches, silently skip (no-op). |
| Q7 | `request.tenant` filter pattern — same as every other module? | **Yes.** Every view filters by `tenant=request.tenant`. Every model carries `tenant` FK. RBAC follows EAM matrix (Authenticated / TenantAdmin). |
| Q8 | Should an Employee be hard-linked to `accounts.User` (login required), or allow employee records without a User account (e.g., contractor / non-system worker)? | **Optional one-to-one** `Employee.user` (`null=True, blank=True, unique=True`). Allows tracking employees who don't have system access (machine operators on a shared kiosk login, contractors paid piece-rate, etc.). |

---

## Sub-module 11.1 — Employee Master & Skills Matrix

### Models (in [`apps/labor/models.py`](../../apps/labor/models.py))

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `Department` | Org-chart unit (HR, Production, QC, Maintenance) | `name`, `code`, `parent` (self-FK), `manager` (FK Employee, nullable to break circular dep at create), `is_active` | — |
| `Position` | Job title within a department | `title`, `code`, `department` FK, `level` (e.g. junior/mid/senior/lead), `description`, `is_active` | — |
| `Employee` | Workforce master record | `employee_number` (auto `EMP-00001`), `user` (one-to-one, nullable), `first_name`, `last_name`, `email`, `phone`, `department` FK, `position` FK, `employment_type` (`permanent / contract / temporary / intern`), `hire_date`, `termination_date` (nullable), `dob`, `gender` (with "prefer_not_to_say"), `address`, `emergency_contact_name`, `emergency_contact_phone`, `status` (`active / on_leave / suspended / terminated`), `notes` | `EMP-00001` |
| `Skill` | Tenant-level catalog of skills | `name`, `code`, `category` (e.g. operations / quality / safety / leadership), `description`, `is_active`. `unique_together=(tenant, code)` | — |
| `EmployeeSkill` | Mapping employee → skill with proficiency | `employee` FK, `skill` FK, `proficiency` (1–5 enum: novice / advanced_beginner / competent / proficient / expert), `assessed_at`, `assessor` FK Employee (nullable), `notes`. `unique_together=(employee, skill)` | — |
| `Certification` | Tenant-level catalog of certifications (e.g. ISO 9001 Lead Auditor, Forklift Op) | `name`, `code`, `issuing_authority`, `valid_period_days`, `is_active`. `unique_together=(tenant, code)` | — |
| `EmployeeCertification` | Per-employee certification record | `employee` FK, `certification` FK, `certificate_number`, `issued_at`, `expires_at`, `attachment` (PDF/JPG/PNG, 25 MB cap, allowlist), `status` (`active / expiring_soon / expired / revoked`). `unique_together=(employee, certification, certificate_number)` | — |
| `EmployeeDocument` | Generic uploads (contract, ID, training cert) | `employee` FK, `doc_type`, `file`, `description`, `uploaded_at` | — |

**Decimal validators (L-02):** none in 11.1 (no Decimal fields).

**unique_together with `tenant` excluded → form-level `clean()` (L-01):** `Department` (parent + name + code), `Position` (department + code), `Skill` (code), `Certification` (code), `EmployeeSkill` (already pure FK), `EmployeeCertification` (already pure FK).

**Computed status:** `EmployeeCertification.status` auto-computed in `save()` from `expires_at` → `active` (>30d), `expiring_soon` (≤30d), `expired` (past). Mirrors `ProductCompliance.status` pattern from PLM.

---

## Sub-module 11.2 — Time & Attendance Integration

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `Shift` | Shift template (Morning / Evening / Night) | `name`, `code`, `start_time`, `end_time`, `break_minutes`, `is_overnight` (when end < start), `color` (UI hex). `unique_together=(tenant, code)` | — |
| `ShiftRoster` | Per-employee shift assignment over a date range | `employee` FK, `shift` FK, `start_date`, `end_date`, `notes`. Overlap protection in `clean()`. | — |
| `AttendanceRecord` | One row per employee per work date | `employee` FK, `work_date`, `shift` FK (nullable — falls back to roster lookup), `clock_in_at`, `clock_out_at` (nullable until close-out), `worked_minutes` (denorm, computed), `status` (`present / absent / late / half_day / on_leave / holiday`), `notes`. `unique_together=(employee, work_date)` | — |
| `LeaveType` | Tenant catalog of leave types | `name`, `code`, `paid` (bool), `default_annual_quota_days` (int, 0 = unlimited), `requires_attachment` (bool), `is_active`. `unique_together=(tenant, code)` | — |
| `LeaveRequest` | Per-employee leave request | `request_number` (auto `LR-00001`), `employee` FK, `leave_type` FK, `start_date`, `end_date`, `days_requested` (Decimal, ≥ 0.5), `reason`, `attachment` (optional, allowlist + 25 MB cap), `status` (`draft / submitted / approved / rejected / cancelled`), `submitted_at`, `decided_by` FK User, `decided_at`, `decision_notes`. Workflow form (L-14): reject + cancel both require non-empty reason. | `LR-00001` |
| `Holiday` | Tenant calendar of paid holidays | `name`, `holiday_date`, `is_recurring` (yearly), `description`. `unique_together=(tenant, holiday_date)` | — |

### Services (in [`apps/labor/services/`](../../apps/labor/services/))

- `services/attendance.py`:
  - `compute_worked_minutes(clock_in, clock_out, break_minutes)` — pure, returns `int` minutes.
  - `derive_status(record, shift, holiday)` — pure, returns `present / late / absent / half_day / holiday`.
- `services/scheduling.py`:
  - `generate_roster(employee, shift, start_date, end_date)` — emits `ShiftRoster` rows (idempotent, skip overlapping ranges with the same shift).

### Cross-module hook

- `mes.OperatorTimeLog.post_save (action='clock_in')` and `'clock_out'` → upsert today's `AttendanceRecord` for the linked Employee (via `ShopFloorOperator.employee`). Idempotent. Skip silently if no Employee link.

---

## Sub-module 11.3 — Labor Cost Allocation

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `CostCenter` | Production / cost center for booking labor + overhead | `name`, `code`, `parent` (self-FK), `cc_type` (`production / quality / maintenance / admin`), `is_active`. `unique_together=(tenant, code)` | — |
| `LaborRate` | Hourly rate for an employee for a date range | `employee` FK, `hourly_rate` (Decimal, > 0), `overtime_multiplier` (Decimal, 1.0–3.0), `effective_from`, `effective_to` (nullable for "open"). Overlap protection in `clean()`. | — |
| `LaborBooking` | Append-only labor cost ledger | `booking_number` (auto `LB-00001`), `employee` FK, `kind` (`direct / indirect / overtime / idle`), `cost_center` FK (nullable for unallocated), `worked_at` (datetime), `minutes` (positive int), `hourly_rate_snapshot` (Decimal), `total_cost` (Decimal, computed `minutes * rate / 60`), `source_type` (`manual / mes_time_log / eam_mwo_labor`), `source_time_log` FK (nullable, → `mes.OperatorTimeLog`), `source_mwo_labor` FK (nullable, → `eam.MWOLaborLog`), `notes`. PROTECT FK on Employee (L-17). Indexed on `(tenant, employee, -worked_at)` and `(tenant, cost_center, -worked_at)`. | `LB-00001` |

### Services

- `services/cost_allocation.py`:
  - `lookup_rate(employee, at_dt)` — pure (given a list of LaborRate rows). Returns the rate effective at `at_dt`.
  - `book_labor(employee, kind, minutes, worked_at, cost_center, source=…)` — atomic write of `LaborBooking` with rate snapshot. Idempotent via `(source_time_log, kind)` or `(source_mwo_labor, kind)` natural keys when source is set.
  - `summarize_by_cost_center(start, end, tenant)` — pure aggregation for the dashboard.

### Cross-module hooks (in `apps/labor/signals.py`)

- `mes.OperatorTimeLog.post_save` (action `stop_job`) → resolve elapsed minutes from the matching `start_job` / `resume_job` event(s), book as **direct** labor against the production order's product cost center (or unallocated if none configured). Idempotent.
- `eam.MWOLaborLog.post_save` → book as **indirect** labor against the asset's cost center (or unallocated). Idempotent. Live-recompute on `MWOLaborLog.minutes` updates is out of scope (manual adjustment).

---

## Sub-module 11.4 — Training & Competency Management

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `TrainingProgram` | Catalog of programs | `name`, `code`, `description`, `delivery_mode` (`classroom / online / on_the_job / external`), `duration_hours` (Decimal ≥ 0.5), `competency_target` FK Skill (nullable — what skill this trains), `is_active`. `unique_together=(tenant, code)` | — |
| `TrainingPlan` | Per-employee training assignment | `employee` FK, `program` FK, `target_completion_date`, `status` (`assigned / in_progress / completed / waived / overdue`), `assigned_by` FK User, `notes`. `unique_together=(employee, program, target_completion_date)` | — |
| `TrainingSession` | A scheduled instance of a program | `session_number` (auto `TS-00001`), `program` FK, `start_at`, `end_at`, `location`, `instructor` FK Employee (nullable), `capacity` (int ≥ 1), `status` (`scheduled / in_progress / completed / cancelled`), `notes`. | `TS-00001` |
| `TrainingAttendance` | Per-attendee record | `session` FK, `employee` FK, `attended` (bool), `score` (Decimal 0–100, optional), `feedback`, `recorded_by` FK User. `unique_together=(session, employee)` | — |
| `CompetencyAssessment` | Per-employee competency evaluation event | `assessment_number` (auto `CA-00001`), `employee` FK, `position` FK (the role being assessed for), `assessed_at`, `assessor` FK User, `overall_score` (Decimal 0–100, computed), `status` (`draft / completed`), `notes`. | `CA-00001` |
| `CompetencyResult` | Per-skill row inside an assessment | `assessment` FK, `skill` FK, `expected_level` (1–5), `actual_level` (1–5), `gap` (computed `expected - actual`), `comments`. `unique_together=(assessment, skill)` | — |

### Services

- `services/competency.py`:
  - `compute_gap(assessment)` — pure: returns list of `(skill, gap)` tuples + overall avg gap.
  - `expiring_certifications(tenant, horizon_days=30)` — pure: returns expiring `EmployeeCertification` rows for dashboard alert.
  - `recompute_assessment_score(assessment)` — pure, called from `CompetencyResult.save()`.

### UI / dashboard hooks

- Skills-matrix grid view at `/labor/skills-matrix/` — employees vs skills heatmap (color-coded by proficiency). Uses ApexCharts or simple Bootstrap table.
- Certification-expiry alert panel on `/labor/` dashboard (≤30d red, ≤90d yellow).

---

## Sub-module 11.5 — Incentive & Piece-Rate Calculation

### Models

| Model | Purpose | Key fields | Auto-# |
|---|---|---|---|
| `IncentiveScheme` | Tenant-level incentive scheme | `name`, `code`, `scheme_type` (`piece_rate / production_bonus / quality_bonus / attendance_bonus`), `applicable_employees` (M2M Employee, optional — empty = all), `applicable_products` (M2M `plm.Product`, optional), `applicable_positions` (M2M Position, optional), `effective_from`, `effective_to` (nullable), `is_active`, `notes`. `unique_together=(tenant, code)` | — |
| `PieceRate` | Per-product (or per-operation) rate row inside a scheme | `scheme` FK, `product` FK (nullable), `operation` FK `pps.RoutingOperation` (nullable), `rate_per_unit` (Decimal, > 0), `min_quantity` (Decimal ≥ 0, default 0), `max_quantity` (Decimal, nullable), `notes`. Either `product` or `operation` must be set (not both NULL); model `clean()` enforces. | — |
| `IncentivePeriod` | Calculation window (typically monthly) | `name`, `start_date`, `end_date`, `status` (`open / locked / paid`), `notes`. `unique_together=(tenant, start_date, end_date)`. | — |
| `IncentiveRun` | Per-period batch calculation | `run_number` (auto `INC-00001`), `period` FK, `scheme` FK, `status` (`draft / running / completed / discarded`), `started_at`, `completed_at`, `total_amount` (Decimal, computed), `notes`. | `INC-00001` |
| `IncentiveLine` | Per-employee line within a run | `run` FK, `employee` FK, `qualifying_units` (Decimal ≥ 0), `rate_applied` (Decimal), `amount` (Decimal, computed `units * rate`), `production_reports` (M2M `mes.ProductionReport` — for traceability of which reports rolled up). `unique_together=(run, employee)`. | — |

### Services

- `services/piece_rate.py`:
  - `lookup_rate(scheme, product, operation, qty)` — pure: returns the matching `PieceRate.rate_per_unit` (preferring operation-level over product-level when both exist).
  - `compute_run(run)` — main engine: scans `mes.ProductionReport` rows in the period, groups by employee, applies rates, materializes `IncentiveLine` rows. Idempotent: `discarded` and re-run cleans out the prior `IncentiveLine` set inside an atomic block.
  - `summarize_employee(employee, period)` — pure helper for the per-employee earnings widget.

### Cross-module hook

- `mes.ProductionReport.post_save` → if an open `IncentiveRun(scheme matches)` exists for the report's period and the report is positive (`good_qty > 0`), bump or create the matching `IncentiveLine` atomically. Idempotent via M2M `production_reports` membership check. Silently skip when no scheme matches.

---

## Workflow & button gates (L-03 view/template parity)

| Resource | Workflow | Template buttons | View gates |
|---|---|---|---|
| `LeaveRequest` | `draft → submitted → approved / rejected → cancelled` | Submit (draft), Approve (submitted, admin), Reject (submitted, admin), Cancel (draft / submitted / approved owner) | Reject + cancel require non-empty `decision_notes` (L-14). |
| `IncentiveRun` | `draft → running → completed / discarded` | Run (draft, admin), Discard (draft / completed, admin) | Run executes `compute_run` inside `transaction.atomic()`. |
| `CompetencyAssessment` | `draft → completed` | Complete (draft, admin) | Complete requires ≥ 1 `CompetencyResult` row (L-14). |
| `TrainingPlan` | `assigned → in_progress → completed / waived / overdue` | Start (assigned), Complete (in_progress), Waive (assigned / in_progress, admin) | Waive requires non-empty `notes` (L-14). |
| `IncentivePeriod` | `open → locked → paid` | Lock (open, admin), Mark Paid (locked, admin) | Locked period rejects new bookings; paid period is read-only. |

---

## Cross-module migrations

| Touched | Bridge | Migration file (planned) |
|---|---|---|
| `mes.ShopFloorOperator` | Add nullable FK `employee → labor.Employee` (one-to-one). | `apps/mes/migrations/0003_shopfloor_operator_employee.py` |
| `eam.Asset` | Add nullable FK `cost_center → labor.CostCenter` (drives indirect-labor allocation when MWO labor is logged). | `apps/eam/migrations/0003_asset_cost_center.py` |
| `plm.Product` | Add nullable FK `cost_center → labor.CostCenter` (drives direct-labor allocation when MES production is reported). | `apps/plm/migrations/0002_product_cost_center.py` |

(All three FKs are nullable — existing rows continue to work; allocation simply lands on `cost_center=None` if not set.)

---

## URL surface (in [`apps/labor/urls.py`](../../apps/labor/urls.py), mounted at `/labor/`)

```
/labor/                                                          → dashboard
/labor/employees/                                                → list (search + filter dept/position/status/active)
/labor/employees/new/ · <pk>/ · <pk>/edit/ · <pk>/delete/ · <pk>/terminate/ · <pk>/reactivate/
/labor/departments/    + CRUD
/labor/positions/      + CRUD
/labor/skills/         + CRUD
/labor/skills-matrix/                                            → employees-vs-skills grid
/labor/employee-skills/<emp_id>/  + CRUD inline
/labor/certifications/ + CRUD
/labor/employee-certifications/<emp_id>/ + CRUD inline
/labor/employee-documents/<emp_id>/ + CRUD inline
/labor/shifts/         + CRUD
/labor/shift-rosters/  + CRUD
/labor/attendance/     + CRUD (per-day, per-employee)
/labor/attendance/import/                                        → CSV import (deferred to v2 — placeholder route)
/labor/leave-types/    + CRUD
/labor/leave-requests/ + CRUD + workflow (submit/approve/reject/cancel)
/labor/holidays/       + CRUD
/labor/cost-centers/   + CRUD
/labor/labor-rates/    + CRUD
/labor/labor-bookings/ + list (read-only) + detail + manual-create
/labor/labor-bookings/summary/                                   → cost-center allocation report
/labor/training-programs/ + CRUD
/labor/training-plans/ + CRUD + workflow
/labor/training-sessions/ + CRUD
/labor/training-attendance/<session_id>/ + CRUD inline
/labor/competency-assessments/ + CRUD + complete workflow
/labor/incentive-schemes/ + CRUD
/labor/piece-rates/<scheme_id>/ + CRUD inline
/labor/incentive-periods/ + CRUD + lock/pay workflow
/labor/incentive-runs/ + CRUD + run/discard workflow
/labor/incentive-lines/<run_id>/                                 → per-employee detail inside a run
```

---

## Templates (in [`templates/labor/`](../../templates/labor/))

```
templates/labor/
├── _pagination.html
├── index.html                                   # dashboard with KPI cards + ApexCharts
├── employees/{list,form,detail}.html
├── departments/{list,form}.html
├── positions/{list,form}.html
├── skills/{list,form}.html
├── skills_matrix/index.html                     # employee × skill grid
├── certifications/{list,form}.html
├── employee_certifications/{list,form}.html
├── employee_documents/{list,form}.html
├── shifts/{list,form}.html
├── shift_rosters/{list,form}.html
├── attendance/{list,form,detail}.html
├── leave_types/{list,form}.html
├── leave_requests/{list,form,detail}.html
├── holidays/{list,form}.html
├── cost_centers/{list,form}.html
├── labor_rates/{list,form}.html
├── labor_bookings/{list,form,detail}.html
├── labor_bookings/summary.html
├── training_programs/{list,form}.html
├── training_plans/{list,form,detail}.html
├── training_sessions/{list,form,detail}.html
├── training_attendance/form.html
├── competency_assessments/{list,form,detail}.html
├── incentive_schemes/{list,form,detail}.html
├── piece_rates/form.html
├── incentive_periods/{list,form}.html
├── incentive_runs/{list,form,detail}.html
└── incentive_lines/list.html
```

All chart payloads use `{{ data|json_script:"id" }}` per **L-07** (no `|safe` on `json.dumps()`).

---

## Sidebar navigation

Add a new "Labor & Workforce" group to [`templates/partials/sidebar.html`](../../templates/partials/sidebar.html) below "Equipment & Asset Management":

- Dashboard → `/labor/`
- Employees → `/labor/employees/`
- Skills Matrix → `/labor/skills-matrix/`
- Certifications → `/labor/certifications/`
- Time & Attendance → submenu (Shifts, Rosters, Attendance, Holidays)
- Leave → submenu (Leave Types, Leave Requests)
- Cost Centers → `/labor/cost-centers/`
- Labor Bookings → `/labor/labor-bookings/`
- Training → submenu (Programs, Plans, Sessions, Competency Assessments)
- Incentives → submenu (Schemes, Piece Rates, Periods, Runs)

---

## Audit signals (in [`apps/labor/signals.py`](../../apps/labor/signals.py))

Apply the same `_mk_status_signals(model, action_prefix)` factory pattern as procurement + EAM, registered with `weak=False` (**L-18**):

- `Employee` → `labor.employee.<status>` on hire / terminate / reactivate / suspend.
- `LeaveRequest` → `labor.leave.<status>` on every state transition.
- `IncentiveRun` → `labor.incentive_run.<status>`.
- `IncentivePeriod` → `labor.period.<status>`.
- `CompetencyAssessment` → `labor.assessment.<status>`.
- `TrainingPlan` → `labor.training_plan.<status>`.
- `EmployeeCertification` → `labor.cert.<status>` on `expires_at` flip-driven transitions (computed in save()).

A regression-guard test in `apps/labor/tests/test_signals.py — TestL18DispatchUIDPresence` asserts every required `dispatch_uid` remains attached.

---

## RBAC matrix (L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, own profile, own attendance, own leave list, own training plan list | Authenticated tenant user | `TenantRequiredMixin` |
| Submit own LeaveRequest, cancel own LeaveRequest (draft/submitted), record own attendance close-out (if not auto-emitted) | Authenticated tenant user | `TenantRequiredMixin` |
| Employee CRUD + terminate / reactivate; Department / Position / Skill / Certification CRUD; LeaveRequest approve / reject; Shift / ShiftRoster / Holiday CRUD; CostCenter / LaborRate CRUD; manual LaborBooking create / delete; TrainingProgram / TrainingPlan / TrainingSession / TrainingAttendance CRUD; CompetencyAssessment CRUD + complete; IncentiveScheme / PieceRate / IncentivePeriod CRUD; IncentiveRun create + run + discard; IncentivePeriod lock + pay | Tenant admin | `TenantAdminRequiredMixin` |

A `TestRBACMatrix` regression test in `apps/labor/tests/test_security.py` asserts redirect + state-not-changed for every admin-gated POST. `TestMultiTenantIDOR` confirms cross-tenant reads/writes 404. `TestAnonymousRedirect` confirms unauthenticated requests redirect to login.

---

## Validation guards (L-01, L-02, L-14)

- **L-01** — every form whose `Meta.fields` excludes `tenant` performs its own `(tenant, …)` `unique_together` check (full list per sub-module above).
- **L-02** — every Decimal field carries explicit `MinValueValidator` (and `MaxValueValidator` where natural):
  - `LaborRate.hourly_rate > 0`, `overtime_multiplier 1.0–3.0`
  - `LaborBooking.minutes > 0`, `total_cost ≥ 0`
  - `LeaveRequest.days_requested ≥ 0.5`
  - `TrainingProgram.duration_hours ≥ 0.5`
  - `TrainingAttendance.score 0–100`
  - `CompetencyResult.expected_level 1–5`, `actual_level 1–5`
  - `PieceRate.rate_per_unit > 0`, `min_quantity ≥ 0`, `max_quantity > min_quantity` when set
  - `IncentiveLine.qualifying_units ≥ 0`, `rate_applied > 0`, `amount ≥ 0`
- **L-14** — per-workflow forms enforce per-transition required fields:
  - `LeaveRequestRejectForm.clean_decision_notes()` → required.
  - `LeaveRequestCancelForm.clean_decision_notes()` → required when status was already `approved`.
  - `CompetencyAssessmentCompleteForm.clean()` → ≥ 1 `CompetencyResult` row required.
  - `TrainingPlanWaiveForm.clean_notes()` → required.
  - `IncentiveRunRunForm.clean()` → period must be `open` AND ≥ 1 production report exists in the window.
  - `EmployeeCertificationForm.clean_attachment()` → extension allowlist + 25 MB cap.

---

## Seeder (in `apps/labor/management/commands/seed_labor.py`)

Idempotent. Skip if `Employee.objects.filter(tenant=tenant).exists()` and `--flush` not set. ASCII-only stdout (L-09). Per tenant, generate:

- 4 departments (Production / Quality / Maintenance / Admin) + 1 self-FK Production sub-dept "Assembly".
- 8 positions (Operator / Senior Operator / QC Inspector / Maintenance Technician / Shift Supervisor / Production Manager / HR Officer / Plant Manager).
- 12 skills (5 operations, 3 quality, 2 safety, 2 leadership) + 5 certifications.
- 20 employees with `EMP-00001 … EMP-00020`, distributed across departments + positions; first 6 are linked to the existing `mes.ShopFloorOperator` records (so cross-module hooks immediately have something to fire on); 14 employee-skill rows (≈3 per employee); 5 certification records; 2 deliberately near-expiry to populate the dashboard alert panel.
- 3 shifts (Morning 06–14, Evening 14–22, Night 22–06) + a 14-day shift roster across all employees.
- 14 days of `AttendanceRecord` rows for each shop-floor operator (95% present + 5% sick).
- 5 leave types (Annual / Sick / Casual / Maternity / Bereavement) + 6 leave requests across statuses (1 draft, 2 submitted, 1 approved, 1 rejected, 1 cancelled).
- 4 holidays in the next 60 days.
- 5 cost centers (Production_Main / Production_Assembly / Quality / Maintenance / Admin) + 20 employee labor rates (1 per employee, $15–$45/hr range).
- 30 days of `LaborBooking` rows back-fed from the existing seeded `mes.OperatorTimeLog` and `eam.MWOLaborLog` data (call the same cross-module signal handler directly to backfill — exercises the entire path).
- 4 training programs + 8 training plans + 2 training sessions + 6 attendance rows.
- 1 competency assessment (with 5 result rows) per supervisor employee → covers the gap-analysis dashboard widget.
- 2 incentive schemes (1 piece-rate Active, 1 production-bonus Inactive) + 5 piece rates per scheme + 1 open period + 1 completed run with 6 incentive lines.

Print a summary count line: `Created 20 employees, 30 attendance days, 30 labor bookings, 6 leave requests, 4 training programs, 1 incentive run.`

---

## Tests (in `apps/labor/tests/`)

Mirror the EAM test suite shape. Target ~120 tests, ≤ 60 s runtime under `config/settings_test.py` (SQLite in-memory):

- `test_models.py` — model invariants, auto-numbering (`EMP-00001` etc.), decimal validators (L-02), denorm computations (`AttendanceRecord.worked_minutes`, `LaborBooking.total_cost`, `IncentiveLine.amount`).
- `test_forms.py` — L-01 unique_together for every form, L-02 decimal bounds, L-14 per-workflow required fields, file-attachment validators.
- `test_services.py` — pure functions (`compute_worked_minutes`, `derive_status`, `lookup_rate`, `compute_gap`, `compute_run`).
- `test_signals.py` — audit-emission per status transition, **L-18 dispatch_uid presence guard**, cross-module hooks (mes time-log → labor booking, eam mwo labor → labor booking, mes production report → incentive line) + idempotency.
- `test_views.py` — full CRUD smoke + workflow happy paths.
- `test_security.py` — RBAC matrix, multi-tenant IDOR, anonymous-redirect on every URL.

Run via: `pytest apps/labor/tests/`

---

## README updates (per CLAUDE.md README Maintenance Rule)

In the same commit batch:

1. Update intro paragraph and Highlights bullet for Module 11.
2. Add Module 11 row to the Roadmap (mark as ✅ shipped).
3. Add the Module 11 routes to "Screenshots / UI Tour".
4. Add the new app entry under "Project Structure" (`apps/labor/` block + `templates/labor/` block).
5. Add a dedicated "Module 11 — Labor & Workforce Management" section after the EAM section: 5 sub-module sections with model bullet lists + cross-module hooks + audit + RBAC + tests + out-of-scope.
6. Add `seed_labor` to "Management Commands" table; update `seed_data` orchestrator entry to include it.
7. Add `pytest apps/labor/tests/` row to the test commands.

---

## Implementation phases (checkable items)

> One file per commit per [.claude/CLAUDE.md → STRICT — ONE FILE PER COMMIT](../../.claude/CLAUDE.md). Commit snippets are PowerShell-safe (use `;` not `&&`).

### Phase 0 — Scaffold the Django app
- [ ] `apps/labor/__init__.py`
- [ ] `apps/labor/apps.py` — `default_auto_field` + `ready()` wiring `signals.py`
- [ ] `apps/labor/admin.py` — minimal admin registration
- [ ] `apps/labor/management/__init__.py`
- [ ] `apps/labor/management/commands/__init__.py`
- [ ] `apps/labor/services/__init__.py`
- [ ] `apps/labor/tests/__init__.py`
- [ ] `apps/labor/migrations/__init__.py`
- [ ] Register `apps.labor` in `config/settings.py:INSTALLED_APPS`
- [ ] Mount `path('labor/', include('apps.labor.urls'))` in `config/urls.py`

### Phase 1 — Sub-module 11.1 Employee Master & Skills Matrix
- [ ] `apps/labor/models.py` — Department, Position, Employee, Skill, EmployeeSkill, Certification, EmployeeCertification, EmployeeDocument
- [ ] `apps/labor/forms.py` — corresponding forms with L-01 / L-02 / L-14 guards
- [ ] `apps/labor/views.py` — full CRUD for above
- [ ] `apps/labor/urls.py` — Phase-1 routes
- [ ] Templates for Phase 1

### Phase 2 — Sub-module 11.2 Time & Attendance
- [ ] Append models (Shift, ShiftRoster, AttendanceRecord, LeaveType, LeaveRequest, Holiday)
- [ ] `apps/labor/services/attendance.py` + `scheduling.py`
- [ ] Append forms + views + urls + templates
- [ ] Cross-module hook stub (mes.OperatorTimeLog → AttendanceRecord)

### Phase 3 — Sub-module 11.3 Labor Cost Allocation
- [ ] Append models (CostCenter, LaborRate, LaborBooking)
- [ ] Cross-module migrations: `mes.ShopFloorOperator.employee`, `eam.Asset.cost_center`, `plm.Product.cost_center`
- [ ] `apps/labor/services/cost_allocation.py`
- [ ] Cross-module signals (mes.OperatorTimeLog stop_job → LaborBooking ; eam.MWOLaborLog → LaborBooking)
- [ ] Append forms + views + urls + templates + summary report view

### Phase 4 — Sub-module 11.4 Training & Competency
- [ ] Append models (TrainingProgram, TrainingPlan, TrainingSession, TrainingAttendance, CompetencyAssessment, CompetencyResult)
- [ ] `apps/labor/services/competency.py`
- [ ] Append forms + views + urls + templates + gap-analysis chart

### Phase 5 — Sub-module 11.5 Incentive & Piece-Rate
- [ ] Append models (IncentiveScheme, PieceRate, IncentivePeriod, IncentiveRun, IncentiveLine)
- [ ] `apps/labor/services/piece_rate.py`
- [ ] Cross-module signal (mes.ProductionReport → IncentiveLine accumulation)
- [ ] Append forms + views + urls + templates + run/discard workflow

### Phase 6 — Audit, dashboard, sidebar
- [ ] `apps/labor/signals.py` — full audit factory + L-18 weak=False
- [ ] `apps/labor/views.py:dashboard()` — KPI cards (active employees, on leave today, certifications expiring ≤30d, open leave requests, current-period incentive total) + ApexCharts (attendance % trend 30d + labor cost by cost-center pie)
- [ ] `templates/labor/index.html` (uses `json_script` per L-07)
- [ ] `templates/partials/sidebar.html` — add Labor & Workforce group

### Phase 7 — Seeder
- [ ] `apps/labor/management/commands/seed_labor.py` — idempotent, ASCII-only stdout
- [ ] Update `apps/core/management/commands/seed_data.py` orchestrator to include `seed_labor`

### Phase 8 — Tests
- [ ] `apps/labor/tests/test_models.py`
- [ ] `apps/labor/tests/test_forms.py`
- [ ] `apps/labor/tests/test_services.py`
- [ ] `apps/labor/tests/test_signals.py` (incl. L-18 dispatch_uid presence + cross-module hooks)
- [ ] `apps/labor/tests/test_views.py`
- [ ] `apps/labor/tests/test_security.py` (RBAC + IDOR + anonymous redirect)

### Phase 9 — README + final commits
- [ ] Update [`README.md`](../../README.md) per Maintenance Rule (intro, Highlights, Roadmap, Routes, Project Structure, dedicated Module 11 section, Management Commands, test commands).
- [ ] Hand the user a per-file PowerShell commit snippet block (one `git add` + one `git commit` per file — including `__init__.py` files, migrations, every template, every test, README, sidebar, settings, root urls).

---

## Risks & open questions surfaced during planning

1. **Circular FK at create-time** — `Department.manager → Employee` and `Employee.department → Department` form a cycle. Mitigation: `Department.manager` is **nullable**, and the seeder creates departments first (manager = NULL), then employees, then back-fills the manager FK in a second pass.
2. **`LaborBooking` history of MES time logs** — at module-install time there are already seeded `mes.OperatorTimeLog` rows. The seeder backfills bookings explicitly; the signal does NOT backfill on module install (would be expensive + non-idempotent on fresh data). Documented in the `seed_labor` summary line.
3. **Piece-rate calculation ordering** — if `IncentiveRun.compute_run` is invoked while an `IncentivePeriod` is still receiving new `ProductionReport` rows, the M2M membership check guarantees we don't double-count, but a **late-arriving** report after `completed` status will need a manual "rerun" by the admin (admin button: Discard → Run again). Documented in the workflow gates table.
4. **Employee privacy** — `Employee.dob`, `address`, `emergency_contact_*` are PII. View-level RBAC restricts non-admins to their own record (`get_object_or_404(Employee, pk=request.user.employee.pk)`). Documented in security section. **Out-of-scope:** field-level encryption (deferred to Module 22 — System Administration & Security).
5. **No-User Employees** — when `Employee.user IS NULL`, attendance + leave + incentive flows still work (admin records on their behalf). Self-service routes (`my profile`, `my leave`) are gated by `request.user.employee_set.exists()`.

---

## Out of scope (deferred)

- **Payroll computation** — labor bookings + incentive lines feed *into* payroll but the actual payslip generation, tax math, and bank-disbursement integration are scoped to Module 12 (Cost Management & Accounting).
- **Biometric / RFID badge integration** — clock-in/out comes via the existing MES kiosk `OperatorTimeLog`; new biometric devices are deferred to Module 15 (IoT & SCADA Integration).
- **Mobile self-service app** — desktop-only in v1; touch-optimized employee terminal deferred.
- **Multi-currency labor rates** — single tenant currency in v1.
- **Workflow approval chains** — flat 1-level approval (admin approves) in v1; multi-level (manager → HR → finance) deferred to Module 20 (Workflow & Process Automation).
- **Skill-gap-driven auto-training** — competency assessment surfaces gaps but does NOT auto-create training plans in v1; the admin reviews + creates manually. Auto-creation is a v2 elegance pass.
- **Federated identity / SSO for employee login** — deferred to Module 22.

---

## Total file count estimate

| Bucket | Files |
|---|---|
| `apps/labor/` Python | 1 `__init__.py`, `apps.py`, `admin.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, `signals.py` = **8** |
| `apps/labor/services/` | `__init__.py`, `attendance.py`, `scheduling.py`, `cost_allocation.py`, `competency.py`, `piece_rate.py` = **6** |
| `apps/labor/management/` | 2 `__init__.py` + `seed_labor.py` = **3** |
| `apps/labor/migrations/` | `__init__.py` + ~3 numbered migrations (initial + 2 incremental) = **4** |
| `apps/labor/tests/` | `__init__.py` + 6 test modules = **7** |
| Cross-module migrations | `mes/0003_*.py`, `eam/0003_*.py`, `plm/0002_*.py` = **3** |
| Modified existing files | `config/settings.py`, `config/urls.py`, `templates/partials/sidebar.html`, `apps/core/management/commands/seed_data.py`, `README.md` = **5** |
| Templates | `_pagination.html`, `index.html` + ~50 list/form/detail HTMLs across 5 sub-modules = **~55** |
| **Total** | **~91 files** |

That's ~91 separate `git add` + `git commit` snippets at the end (matches the EAM cadence; user has approved this volume before).

---

## Awaiting user approval

**Please confirm:**
1. Approve the 8 default decisions in the "Decisions to confirm" table (or override).
2. Approve the implementation order (Phases 0 → 9, all 5 sub-modules in one pass).
3. Approve the cross-module migrations on `mes`, `eam`, `plm` (all are nullable additions — zero breaking change).
4. Approve the auto-number prefixes (`EMP / LR / LB / TS / CA / INC`).
5. Confirm scope cuts in "Out of scope" are acceptable for v1.

Once approved, I will start at Phase 0 and proceed sequentially, marking each `[ ]` as `[x]` as it ships, with one-file-per-commit snippets handed over at the end of each phase.
