# Plan — Module 6: Shop Floor Control (MES)

> Status: **DRAFT — pending user approval before any code is written**
> Created: 2026-04-29
> Pattern reference: `apps/mrp/` (Module 5) — newest, cleanest example. Mirror its layout exactly: `models.py` (sectioned banners), `forms.py`, `views.py`, `urls.py`, `signals.py`, `services/`, `admin.py`, `management/commands/seed_mes.py`, plus `templates/mes/<sub>/list|form|detail.html`.

## Goal

Build **Module 6 — Shop Floor Control (MES)** as a new Django app `apps/mes/`, mounted at `/mes/`, following every convention established by `apps/plm/`, `apps/bom/`, `apps/pps/`, and `apps/mrp/`:

- Multi-tenant via `TenantAwareModel`
- Full CRUD per model (list / create / detail / edit / delete) — CRUD Completeness Rules
- Working filters on every list page — Filter Implementation Rules
- Audit signals on status transitions (writes to `apps.tenants.TenantAuditLog`)
- Idempotent seeder with `--flush` — Seed Command Rules
- README.md updated in the same session — README Maintenance Rule
- Sidebar entry added to `templates/partials/sidebar.html`
- One file per git commit at the end — STRICT GIT Commit Rule (Lesson L-06)
- Decimal fields carry explicit `MinValueValidator` / `MaxValueValidator` (Lesson L-02)
- Tenant-scoped forms perform manual `unique_together` checks in `clean()` (Lesson L-01)
- View-side status gates match template button visibility via model `is_*()` helpers (Lesson L-03)
- Seeder horizons align with consumer modules; output is ASCII-only (Lessons L-08, L-09)
- Inline JS server data uses `{{ data|json_script:"id" }}` — never `|safe` json.dumps (Lesson L-07)

## Sub-modules to implement (matches user-supplied spec)

| # | Sub-Module | Core Capability |
|---|---|---|
| 6.1 | Work Order Execution | Digital work order dispatch from `pps.ProductionOrder`; per-operation sequencing & real-time status; routing op → work-order-op fan-out |
| 6.2 | Operator Terminal Interface | Touchscreen kiosk: clock-in / clock-out, job start / pause / stop, time entries against work-order operations |
| 6.3 | Production Reporting | Good qty / scrap / rework qty per operation; cycle-time capture; first-pass yield rollups feeding back to `pps.ProductionOrder` |
| 6.4 | Andon & Alert Management | Real-time visual alerts (quality / material / equipment / safety / other), severity, acknowledge / resolve workflow |
| 6.5 | Paperless Work Instructions | Digital SOP cards with multimedia (PDF / image / video link), version history, per-operator acknowledgement tracking |

---

## 0. Open questions for user approval (please confirm before I start coding)

1. **App label** — `mes`, URL prefix `/mes/`, sidebar group **"Shop Floor (MES)"** between "Material Requirements (MRP)" and "User Management". **OK?**
2. **Source of dispatched work orders** — MES dispatches from already-released `pps.ProductionOrder`. Plan: **`MESWorkOrder`** is a child record of a `ProductionOrder`, auto-numbered `WO-00001`, that carries the shop-floor lifecycle (`dispatched → in_progress → on_hold → completed`). The PPS production order remains the system-of-record for "what to build"; MES owns "who built it, when, and how it went". **OK to leave PPS untouched and add MES as a downstream consumer?**
3. **Operations on the work order** — fan out from `pps.RoutingOperation` rows at dispatch time into **`MESWorkOrderOperation`** (one per routing op) with start / stop / pause timestamps and good / scrap / rework qty. Mirrors how `pps.ScheduledOperation` clones routing ops at scheduling time. **OK?**
4. **Operator clock-in model** — add **`ShopFloorOperator`** as a thin layer on top of `accounts.User` (one-to-one, `badge_number` unique per tenant, `default_work_center` FK→`pps.WorkCenter`). NOT a new auth user — every floor operator already has a `User`. **OK?** (Without this, kiosk badge-scan login becomes impossible later.)
5. **Time tracking** — **`OperatorTimeLog`** rows: `(operator, work_order_operation, action, timestamp)` where action is `clock_in / clock_out / start_job / pause_job / resume_job / stop_job`. Append-only. The current state of an operation is derived from its latest log row + cached fields on the op itself. **OK?**
6. **Production report** — **`ProductionReport`** rows attached to a `MESWorkOrderOperation`: `(good_qty, scrap_qty, rework_qty, scrap_reason, reported_by, reported_at)`. A single op can have multiple reports (multi-shift, partial-completion). Op-level `total_good / total_scrap / total_rework` are denormalized on the op for fast list views. **OK?**
7. **Andon model** — **`AndonAlert`** with `(alert_type, severity, title, message, work_center FK, work_order FK nullable, raised_by, raised_at, acknowledged_by, acknowledged_at, resolved_by, resolved_at, resolution_notes)`. Status workflow `open → acknowledged → resolved` (or `cancelled`). **OK?**
8. **Work instruction storage** — **`WorkInstruction`** model carrying `(title, doc_type, version, content text, attachment FileField, video_url URLField, status)` plus an FK to `pps.RoutingOperation` (so "the SOP for this op" is a one-FK lookup) AND optional FK to `plm.Product` (general product-level SOPs). File allowlist mirrors PLM ECO attachments (`.pdf .png .jpg .jpeg .mp4 .docx .xlsx .txt`), 25 MB cap, served via auth-gated `WorkInstructionDownloadView` (same pattern as `apps/plm/views.py`). **OK?**
9. **Acknowledgement tracking** — **`WorkInstructionAcknowledgement`** rows: `(instruction, instruction_version_string, user, acknowledged_at, signature_text)`. Every release of a new version invalidates prior acknowledgements; the operator must re-ack. Unique per `(instruction, user, instruction_version_string)`. **OK?**
10. **Operator Terminal page** — single full-screen page at `/mes/terminal/` rendered as a touchscreen kiosk: badge-scan input (CharField, autofocus), shows the operator's open jobs, big buttons for Start / Pause / Stop / Report Qty / Raise Andon. No printed SOP — clicking a job opens its work instruction in a panel. **OK that this lives behind the standard `LoginRequiredMixin` for v1, and badge-only auth (no password) is deferred?**
11. **Pytest test suite** — defer to a follow-up (matches how PLM, BOM, MRP shipped — manual test plan only at v1). PPS shipped a 58-test suite, but that was driven by the SQA review *after* the module landed. Same path here. **OK?**
12. **Currency / units** — single USD assumed for any cost roll-ups; `unit_of_measure` strings copied from the underlying `pps.RoutingOperation` / `plm.Product`, not re-validated. **OK?**

If you reply **"do what you think best"** I'll proceed with all twelve defaults.

---

## 1. Models — `apps/mes/models.py` (~10 models, sectioned banners)

All inherit from `TenantAwareModel, TimeStampedModel`. Reuse `apps.plm.models.Product`, `apps.bom.models.BillOfMaterials`, `apps.pps.models.{ProductionOrder, RoutingOperation, WorkCenter}`, `apps.accounts.models.User`.

### 6.1 Work Order Execution
- **`MESWorkOrder`** — `wo_number` auto `WO-00001` per tenant; FK to `pps.ProductionOrder`; FK to `plm.Product` (denormalized, read at dispatch); `quantity_to_build` decimal; `quantity_completed` decimal (rolled up from operations); `quantity_scrapped` decimal; `status` (`dispatched` / `in_progress` / `on_hold` / `completed` / `cancelled`); `priority` (inherits from production order at dispatch but can be raised); `dispatched_at` / `dispatched_by`; `completed_at` / `completed_by`; `notes`. Unique `(tenant, wo_number)`. **`is_editable()`**, **`can_start()`**, **`can_complete()`**, **`can_cancel()`** helpers.
- **`MESWorkOrderOperation`** — `work_order` FK; `routing_operation` FK→`pps.RoutingOperation` (the source); `sequence` PositiveSmallInt (copied from routing op); `work_center` FK→`pps.WorkCenter` (copied); `setup_minutes` / `run_minutes_per_unit` (copied — used to seed planned_minutes); `planned_minutes` decimal; `actual_minutes` decimal (sum of time logs while running); `total_good_qty` / `total_scrap_qty` / `total_rework_qty` decimals (denormalized); `status` (`pending` / `setup` / `running` / `paused` / `completed` / `skipped`); `started_at` / `completed_at`; `current_operator` FK→`accounts.User` nullable. Unique `(work_order, sequence)`.

### 6.2 Operator Terminal Interface
- **`ShopFloorOperator`** — OneToOne `accounts.User`; `badge_number` (15-char) unique per tenant; `default_work_center` FK→`pps.WorkCenter` nullable; `is_active` bool; `notes`. Use `OneToOneField` so `user.shop_floor_operator` always works.
- **`OperatorTimeLog`** — `operator` FK→`ShopFloorOperator`; `work_order_operation` FK→`MESWorkOrderOperation` nullable (clock-in/out are not tied to an op); `action` (`clock_in` / `clock_out` / `start_job` / `pause_job` / `resume_job` / `stop_job`); `recorded_at` DateTime; `notes` CharField. Append-only — no edit / delete via admin UI for tenant users (only superuser edit, and even that is logged in admin history). Index `(tenant, operator, recorded_at)`.

### 6.3 Production Reporting
- **`ProductionReport`** — `work_order_operation` FK→`MESWorkOrderOperation`; `good_qty` / `scrap_qty` / `rework_qty` decimals (each `>=0`); `scrap_reason` CharField w/ choices (`material_defect` / `setup_error` / `tooling` / `process` / `operator_error` / `other`); `cycle_time_minutes` decimal nullable (computed if both timestamps set); `reported_by` FK→`accounts.User`; `reported_at` DateTime; `notes`. Adding a report bumps the parent op's `total_good_qty / total_scrap_qty / total_rework_qty` via `post_save` signal.

### 6.4 Andon & Alert Management
- **`AndonAlert`** — `alert_number` auto `AND-00001`; `alert_type` (`quality` / `material` / `equipment` / `safety` / `other`); `severity` (`low` / `medium` / `high` / `critical`); `title` / `message`; `work_center` FK→`pps.WorkCenter`; `work_order` FK→`MESWorkOrder` nullable; `work_order_operation` FK→`MESWorkOrderOperation` nullable; `status` (`open` / `acknowledged` / `resolved` / `cancelled`); `raised_by` FK→`accounts.User`; `raised_at` DateTime; `acknowledged_by` / `acknowledged_at`; `resolved_by` / `resolved_at`; `resolution_notes`. Unique `(tenant, alert_number)`. **`can_acknowledge()`**, **`can_resolve()`**, **`can_cancel()`** helpers.

### 6.5 Paperless Work Instructions
- **`WorkInstruction`** — `instruction_number` auto `SOP-00001`; `title`; `doc_type` (`sop` / `setup_sheet` / `quality_check` / `safety` / `other`); `routing_operation` FK→`pps.RoutingOperation` nullable; `product` FK→`plm.Product` nullable (must have at least one of the two — enforced in `Form.clean()` and a model `clean()`); `current_version` FK→`WorkInstructionVersion` nullable; `status` (`draft` / `released` / `obsolete`); `created_by`; `released_at` / `released_by`. Unique `(tenant, instruction_number)`.
- **`WorkInstructionVersion`** — `instruction` FK; `version` CharField (e.g. `1.0`, `1.1`, `2.0`); `content` TextField (rendered as Markdown — same renderer as PLM `change_summary`); `attachment` FileField (allowlist `.pdf .png .jpg .jpeg .mp4 .docx .xlsx .txt`, 25 MB cap); `video_url` URLField blank; `change_notes`; `status` (`draft` / `released` / `obsolete`); `uploaded_by`; `uploaded_at`. Unique `(instruction, version)`.
- **`WorkInstructionAcknowledgement`** — `instruction` FK; `instruction_version` CharField (snapshot — survives version deletion); `user` FK; `acknowledged_at` DateTime auto_now_add; `signature_text` CharField (typed name). Unique `(tenant, instruction, user, instruction_version)`.

---

## 2. Services — `apps/mes/services/` (3 pure-function modules)

### `dispatcher.py`
- `dispatch_production_order(production_order) -> MESWorkOrder` — creates a `MESWorkOrder` plus one `MESWorkOrderOperation` per routing op. Idempotent: returns the existing `MESWorkOrder` if one is already linked to this `ProductionOrder` and is not cancelled.
- Pure function aside from the persistence at the end — no signals fired beyond Django's normal model save chain.
- Validates: production order must be `released`; routing must be set; operations must be `> 0`. Otherwise raises a `DispatchError` exception that the calling view converts to a `messages.error(...)`.

### `time_logging.py`
- `record_event(operator, action, *, work_order_operation=None, notes='', now=None) -> OperatorTimeLog` — appends a log row, recomputes `MESWorkOrderOperation.actual_minutes` from accumulated start/pause/resume/stop pairs, and flips the op's `status` according to the action. Pure aside from the writes.
- `compute_actual_minutes(time_logs: list[OperatorTimeLog]) -> Decimal` — pure helper; iterates start/pause/resume/stop sequence pairs and sums elapsed minutes. Handles paused-open intervals by clamping to `now` (or the supplied `now`). Unit-testable without any database fixture.

### `reporting.py`
- `record_production(work_order_operation, *, good, scrap, rework, scrap_reason, reported_by, notes='') -> ProductionReport` — creates the report row and bumps the op denorms in a single `transaction.atomic` block; if the resulting `total_good_qty >= work_order.quantity_to_build`, the op flips to `completed` and the parent work order's `quantity_completed` is recomputed.
- `rollup_work_order(work_order) -> dict` — pure summary helper used by the work-order detail page: returns `{good, scrap, rework, completed_pct, hours_actual, hours_planned}`.

> Why pure functions: matches `apps/pps/services/scheduler.py` (forward / backward / infinite scheduler) and `apps/mrp/services/{forecasting, lot_sizing, mrp_engine, exceptions}.py` — keeps the algorithms unit-testable and ORM-light, so a future cross-app reorg (e.g. extracting MES into a microservice) doesn't require rewriting them.

---

## 3. Forms — `apps/mes/forms.py`

One ModelForm per user-edited model. Lessons L-01 / L-02 applied:

- `MESWorkOrderForm` — manual `(tenant, wo_number)` check in `clean()`.
- `ShopFloorOperatorForm` — manual `(tenant, badge_number)` check; rejects badge collisions across deactivated operators too (different from `User.username`).
- `ProductionReportForm` — `clean()` rejects `good + scrap + rework == 0` and any negative.
- `AndonAlertForm` — `clean()` requires at least `title` if `alert_type=other`.
- `WorkInstructionForm` — `clean()` requires `routing_operation` OR `product`.
- `WorkInstructionVersionForm` — file allowlist + 25 MB cap (same helper used in `apps/plm/forms.py`).
- `WorkInstructionAcknowledgementForm` — `signature_text` must non-empty match the user's full name OR username (case-insensitive).

All forms stash the tenant in `__init__` (`self._tenant = kwargs.pop('tenant', None)`) so `clean()` can scope the unique check.

---

## 4. Views — `apps/mes/views.py`

Mirror MRP. Class-based mixins:
- `TenantRequiredMixin` (read) — list, detail, dashboard, terminal kiosk read.
- `TenantAdminRequiredMixin` (write/admin) — create/edit/delete forms, dispatch, work-instruction release / obsolete actions, andon resolve.
- Floor operators (regular tenant users) can: clock-in/out, start/pause/stop jobs they're assigned, file production reports against their open ops, raise andon alerts. These are POST endpoints with explicit "current user is operator" guards (not the admin mixin).

Per-sub-module list-page columns and filters explicitly enumerated in `views.py` so the "Filter Implementation Rules" checklist passes from day one.

Status-transition POSTs use the conditional `UPDATE … WHERE status IN (…)` pattern (race-safety) — same as PPS / MRP. Helper named `_atomic_status_transition` lifted into `apps/core/utils.py` if it's not already there (check first; PPS has its own copy today).

### Special routes
- `/mes/terminal/` — kiosk landing page for the operator. Reads `request.user.shop_floor_operator` (404 if missing — admins are redirected to the operator-create form). Renders open ops grouped by status, with big buttons.
- `/mes/dispatch/<production_order_pk>/` — POST-only dispatch endpoint that creates the `MESWorkOrder`. Redirects back to the PPS production order detail with a flash. (Listed on PPS production order detail page as "Dispatch to Shop Floor" once `released` — small README note about this cross-module link.)
- `/mes/instructions/<pk>/release/` — POST-only release; auto-obsoletes prior released versions for the same instruction.
- `/mes/instructions/<pk>/ack/` — POST-only operator acknowledgement.
- `/mes/instructions/versions/<pk>/download/` — auth-gated download view (mirrors `apps/plm/views.py CADVersionDownloadView`).

---

## 5. URLs — `apps/mes/urls.py`

`app_name = 'mes'`. Routes:

```
/mes/                                       index (dashboard)
/mes/terminal/                              terminal_view
/mes/work-orders/                           work_order_list / new / <pk> / <pk>/edit / <pk>/delete
/mes/work-orders/<pk>/start/                start
/mes/work-orders/<pk>/hold/                 hold
/mes/work-orders/<pk>/complete/             complete
/mes/work-orders/<pk>/cancel/               cancel
/mes/work-orders/operations/<pk>/           op detail
/mes/work-orders/operations/<pk>/start/     op start
/mes/work-orders/operations/<pk>/pause/     op pause
/mes/work-orders/operations/<pk>/resume/    op resume
/mes/work-orders/operations/<pk>/stop/      op stop
/mes/dispatch/<production_order_pk>/        dispatch
/mes/operators/                             list / new / <pk> / edit / delete
/mes/operators/<pk>/clock-in/  /clock-out/  POST
/mes/time-logs/                             list (filter by operator/op/action)
/mes/reports/                               list / new / <pk> / edit / delete
/mes/andon/                                 list / new / <pk> / edit / delete
/mes/andon/<pk>/acknowledge/                POST
/mes/andon/<pk>/resolve/                    POST
/mes/andon/<pk>/cancel/                     POST
/mes/instructions/                          list / new / <pk> / edit / delete
/mes/instructions/<pk>/versions/new/        new version
/mes/instructions/versions/<pk>/release/    POST
/mes/instructions/versions/<pk>/obsolete/   POST
/mes/instructions/versions/<pk>/download/   auth-gated download
/mes/instructions/<pk>/ack/                 POST
```

Mounted in `config/urls.py`: `path('mes/', include('apps.mes.urls'))`.

---

## 6. Signals — `apps/mes/signals.py`

Wires `apps.tenants.TenantAuditLog` entries on:
- `MESWorkOrder` — create, status transitions (`mes_work_order.created`, `mes_work_order.status.<new>` with `meta={'from': old, 'to': new}`).
- `MESWorkOrderOperation` — status transitions only (high-frequency model; no per-create entry).
- `AndonAlert` — create, status transitions.
- `WorkInstruction` — status transitions.
- `WorkInstructionVersion` — status transitions.

Plus:
- `post_save` on `ProductionReport` → bumps parent op denorms (`total_good_qty / total_scrap_qty / total_rework_qty`) AND parent work order `quantity_completed`. Skips if `raw=True` (fixture loading).
- `post_save` on `OperatorTimeLog` → recomputes parent op's `actual_minutes` from accumulated logs.
- `pre_save` on `WorkInstructionAcknowledgement` → snapshot the version string at ack time so a deleted version row does not orphan the ack.

Connected via the standard `apps/mes/apps.py → ready()` hook.

---

## 7. Admin — `apps/mes/admin.py`

Standard `ModelAdmin` per model with `list_display`, `list_filter`, `search_fields`, `readonly_fields = ('tenant', 'created_at', 'updated_at')`. The append-only `OperatorTimeLog` and `ProductionReport` admins set `has_change_permission = lambda self, request, obj=None: request.user.is_superuser` so non-superusers can read but not mutate.

---

## 8. Templates — `templates/mes/`

Mirror MRP layout. Each list/form/detail follows the existing pattern:
- `index.html` — dashboard (KPI cards: open WOs, in-progress ops, open andon alerts, today's good qty, today's scrap qty)
- `work_orders/list.html | form.html | detail.html`
- `work_orders/operations/detail.html`
- `terminal/index.html` — kiosk page with grouped open ops + action buttons
- `operators/list.html | form.html | detail.html`
- `time_logs/list.html`
- `reports/list.html | form.html | detail.html`
- `andon/list.html | form.html | detail.html`
- `instructions/list.html | form.html | detail.html`
- `instructions/versions/form.html`

### Filter Implementation Rules per template (Lesson L-03 + Filter Rules in CLAUDE.md):
- **Work orders list** — search (`q`: wo_number, product sku/name) + status + priority + work_center filters. View passes `status_choices = MESWorkOrder.STATUS_CHOICES`, `priority_choices = MESWorkOrder.PRIORITY_CHOICES`, `work_centers = WorkCenter.objects.filter(tenant=...)`.
- **Andon list** — search + alert_type + severity + status + work_center filters.
- **Reports list** — search + scrap_reason + work_center + reported_by filters.
- **Operators list** — search (badge / name / username) + active filter.
- **Time logs list** — operator + action + work_order_operation filters.
- **Instructions list** — search + doc_type + status + product + routing_operation filters.

---

## 9. Sidebar — `templates/partials/sidebar.html`

Add a new collapse group **"Shop Floor (MES)"** between MRP and User Management:

```
- MES Dashboard
- Operator Terminal
- Work Orders
- Operations (read-only list)
- Operators
- Time Logs
- Production Reports
- Andon Alerts
- Work Instructions
```

Icon: `ri-tools-line` (factory / wrench — visually distinct from MRP's `ri-flow-chart`).

---

## 10. Seed command — `apps/mes/management/commands/seed_mes.py`

Idempotent (Lesson + Seed Rules). Per tenant:
- 5 `ShopFloorOperator`s linked to existing seeded staff users (`acme_supervisor_1`, `acme_production_manager_1`, etc.) with badge numbers `B0001 – B0005`.
- 6 `MESWorkOrder`s — 1 per seeded `pps.ProductionOrder` that is `released` or `in_progress` (existing PPS seed creates these). Status spread: 2 dispatched, 2 in_progress, 1 on_hold, 1 completed.
- Per work order, one `MESWorkOrderOperation` per source routing op (typically 2-4).
- 12 `OperatorTimeLog` rows across the in-progress and completed work orders so the terminal page has plausible content.
- 8 `ProductionReport` rows on the in-progress + completed ops with mixed good / scrap / rework numbers and 3 different scrap reasons.
- 4 `AndonAlert`s — 1 open, 1 acknowledged, 1 resolved, 1 cancelled, spread across alert_types.
- 3 `WorkInstruction`s with 1-2 `WorkInstructionVersion`s each (one released, one draft) attached to seeded routing ops; one carries a `video_url` placeholder. Files are seeded WITHOUT binary content (matches PLM CAD seeder pattern — operators upload real PDFs via the UI).
- 4 `WorkInstructionAcknowledgement` rows across 2 operators on the released versions.

Output: ASCII-only (Lesson L-09); print non-zero summary counts (Lesson L-08); print "log in as `admin_<slug>`" reminder; warn about superuser tenant=None.

Add to `seed_data` orchestrator: append `seed_mes` after `seed_mrp`.

---

## 11. Cross-module hooks (minimal — no PPS/MRP changes)

- **PPS production order detail page** — add a "Dispatch to Shop Floor" button when `status == 'released'` and no MES work order exists yet (or the existing one is `cancelled`). One template tweak in `templates/pps/orders/detail.html`. Existing PPS code path unchanged.
- **PLM product detail / Routing detail (PPS)** — add a "Work Instructions" tab/section listing related `WorkInstruction` rows. Read-only — purely informational.

These are the only existing-file mutations outside the new `apps/mes/` directory and `templates/mes/`. Three files total: `templates/pps/orders/detail.html`, `templates/pps/routings/detail.html`, `templates/plm/products/detail.html` (and `templates/partials/sidebar.html` + `config/urls.py` + `README.md`).

---

## 12. README — sections to add / update

- Add Module 6 to the **Phase 1** intro paragraph (currently lists 1-5).
- **Table of Contents** — insert "Module 6 — Shop Floor Control (MES)" entry.
- **Highlights** — one-bullet summary mirroring the existing Module 5 entry.
- **Screenshots / UI Tour** — add the `/mes/...` route table.
- **Project Structure** — add the `apps/mes/` and `templates/mes/` blocks.
- **Seeded Demo Data** — append per-tenant MES counts.
- **New top-level section** — "Module 6 — Shop Floor Control (MES)" with sub-module breakdown identical in shape to the Module 5 section.
- **Management Commands** — add `seed_mes` row.
- **Roadmap** — strikethrough Module 6 (mark shipped).

---

## 13. Migration plan

1. `python manage.py makemigrations mes` (one initial migration covering all 10 models)
2. `python manage.py migrate`
3. `python manage.py seed_mes` (or `seed_data` — runs the orchestrator)

---

## 14. File inventory & per-file commit list (preview — final block at session end)

Roughly 40-45 files will be created or touched. Per Lesson L-06 / GIT Commit Rule, the commit snippet block at the end will list **one `git add` + `git commit` per file**, no bundling, PowerShell `;` separator. Example shape:

```
git add 'apps/mes/__init__.py'; git commit -m 'feat(mes): add app package'
git add 'apps/mes/apps.py'; git commit -m 'feat(mes): app config with signals ready hook'
git add 'apps/mes/models.py'; git commit -m 'feat(mes): all 10 models with sectioned banners'
... (continues for every file)
git add 'README.md'; git commit -m 'docs(readme): add Module 6 (MES) section, routes, structure, seed data, roadmap'
```

---

## 15. Verification checklist (before I claim done)

- [ ] `python manage.py makemigrations mes` produces ONE migration; no spurious "did you rename?" prompts
- [ ] `python manage.py migrate` runs clean
- [ ] `python manage.py seed_data --flush` runs clean for all 3 tenants and prints non-zero MES counts
- [ ] `/mes/` (dashboard) loads logged in as `admin_acme`
- [ ] All 9 list pages load and filters narrow results correctly
- [ ] Dispatch button on a `released` PPS production order creates a `MESWorkOrder` and redirects with a flash
- [ ] Operator terminal page renders open ops for an operator and Start/Stop buttons flip statuses
- [ ] Production report bumps op + work order denorms; sums match
- [ ] Andon raise → acknowledge → resolve workflow walks cleanly
- [ ] Work instruction release auto-obsoletes prior versions; acknowledgements survive a version delete
- [ ] Cross-tenant test: log in as `admin_acme`, manually edit URL to a `globex` work order PK → 404
- [ ] All POST forms carry `{% csrf_token %}` and use POST methods
- [ ] Sidebar entry visible and links resolve
- [ ] README updated with all sections listed in §12
- [ ] Per-file commit snippet block produced at the very end (no bundling)

---

## REVIEW (post-build, 2026-04-29)

### What shipped

- New Django app `apps/mes/` mounted at `/mes/`, registered in `config/settings.py` and `config/urls.py`.
- 9 models across 5 sub-modules (the plan named 10 — `WorkInstructionVersion` and `WorkInstructionAcknowledgement` count separately, the plan listed `MESWorkOrder` and `MESWorkOrderOperation` as 2 — net 9 distinct user-facing models, plus the `WorkInstructionVersion` self-FK glue).
- 3 pure-function services (`dispatcher`, `time_logging`, `reporting`) — keeps algorithms ORM-light and unit-testable.
- 46 named URL routes (verified by `reverse()` on every name).
- Per-tenant audit signals on every status transition (work order, op, andon, instruction, version).
- Idempotent seeder with `--flush`, ASCII-only stdout (Lesson L-09).
- Templates for all 9 list / form / detail surfaces + the touchscreen terminal.
- Cross-module hooks: PPS production-order detail "Dispatch to Shop Floor" button, sidebar nav group.
- README.md updated end-to-end (intro, ToC, highlights, route table, project structure, seeded data, dedicated section, mgmt commands, roadmap).

### Verification done

- `python manage.py makemigrations mes` produced one clean initial migration; rerun reports `No changes detected`.
- `python manage.py check` returns `System check identified no issues (0 silenced)`.
- All 46 MES URL names successfully `reverse()` to a path.
- Every `.py` under `apps/mes/` imports without error after `django.setup()`.
- Lessons L-01 (manual `unique_together` clean), L-02 (decimal validators), L-03 (`is_*` helpers shared between view + template), L-06 (one file per commit — see snippet block below), L-07 (no `|safe` JSON in templates), L-09 (ASCII-only stdout) are all observed.

### Open follow-ups (not blocking)

- MySQL is not reachable from the build sandbox, so `python manage.py migrate` and `python manage.py seed_mes` were not executed end-to-end. The user should run these locally — instructions are in the per-file snippet block.
- Pytest coverage suite (mirroring PPS's 58-test bundle) is deliberately deferred to a follow-up SQA pass, matching how PLM / BOM / MRP shipped.
- Badge-scan kiosk authentication is out of scope for v1 — `request.user.shop_floor_operator` lookup is the v1 binding.

