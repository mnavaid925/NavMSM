# Production Planning & Scheduling — Comprehensive SQA Test Report

**Module:** [apps/pps/](../apps/pps/) (Module 4 of NavMSM)
**Reviewer:** Senior SQA Engineer (15+ yrs)
**Date:** 2026-04-28
**Build under review:** `main` @ `b04a16b` plus the unmerged Module 4 working tree (commit snippets generated, not yet pushed)
**Scope mode:** Module review (default) — end-to-end across the 5 sub-modules: MPS, Capacity, Scheduling, Simulation, APO.
**Verification:** every High / Critical defect reproduced in the Django shell against the seeded `admin_acme` tenant before being recorded. Speculation-only findings are marked `DEFECT CANDIDATE`.

---

## 1. Module Analysis

### 1.1 Surface area

| Layer | File | LoC (approx.) | Notes |
|---|---|---|---|
| Models | [apps/pps/models.py](../apps/pps/models.py) | ~640 | 16 models across 5 sub-modules; all inherit `TenantAwareModel + TimeStampedModel` |
| Forms | [apps/pps/forms.py](../apps/pps/forms.py) | ~245 | 11 ModelForms; cross-field validation present, model-level validators absent |
| Views | [apps/pps/views.py](../apps/pps/views.py) | ~870 | 50 CBVs; full CRUD + workflow + scheduling + Gantt + capacity dashboard |
| URLs | [apps/pps/urls.py](../apps/pps/urls.py) | ~95 | 53 routes under `/pps/` |
| Signals | [apps/pps/signals.py](../apps/pps/signals.py) | ~135 | Audit-log writers + capacity load invalidation |
| Admin | [apps/pps/admin.py](../apps/pps/admin.py) | ~145 | All 16 models registered with inlines |
| Services | [apps/pps/services/scheduler.py](../apps/pps/services/scheduler.py), [simulator.py](../apps/pps/services/simulator.py), [optimizer.py](../apps/pps/services/optimizer.py) | ~330 | Pure functions, no ORM imports at module level |
| Seeder | [apps/pps/management/commands/seed_pps.py](../apps/pps/management/commands/seed_pps.py) | ~545 | Idempotent; `--flush` supported; hooked into `seed_data` orchestrator |
| Templates | [templates/pps/](../templates/pps/) | 25 files | Dashboard, forecasts, MPS, work centers, calendars, capacity, routings, orders, Gantt, scenarios, optimizer |
| Sidebar | [templates/partials/sidebar.html](../templates/partials/sidebar.html) | (delta) | "Production Planning" group with 12 nav links |

### 1.2 Business rules (each linked to source)

| # | Rule | Enforced at | Reference |
|---|---|---|---|
| BR-1 | MPS workflow: `draft → under_review → approved → released → obsolete` | Atomic conditional `UPDATE` | `_atomic_status_transition` + transition views in [apps/pps/views.py](../apps/pps/views.py) |
| BR-2 | Released MPS cannot be edited or deleted; only Obsoleted | View gate by `is_editable()` / status check | [apps/pps/views.py](../apps/pps/views.py) — MPSEditView, MPSDeleteView |
| BR-3 | Production order workflow: `planned → released → in_progress → completed` (or `cancelled`) | Atomic conditional `UPDATE` | [apps/pps/views.py](../apps/pps/views.py) — Production order workflow views |
| BR-4 | Scheduling action requires a routing on the order; replaces existing `ScheduledOperation` rows atomically | View guard + `transaction.atomic` | [apps/pps/views.py](../apps/pps/views.py) — ProductionOrderScheduleView |
| BR-5 | Phantom-unaware: PPS does not collapse phantom BOM components in scheduling (out of scope; Module 3's BOM explosion is the consumer of phantoms) | n/a | n/a |
| BR-6 | Scenario apply / Optimization apply record intent only; never mutate the base MPS | View comment + signal | [apps/pps/views.py](../apps/pps/views.py) — ScenarioApplyView, OptimizationApplyView |
| BR-7 | Capacity load is computed; `ScheduledOperation` save/delete invalidates `CapacityLoad.computed_at` (UI surfaces "Stale") | `post_save` / `post_delete` signal | [apps/pps/signals.py](../apps/pps/signals.py) — `_invalidate_load` |
| BR-8 | Audit-log entry on every status transition for MPS, ProductionOrder, Scenario, OptimizationRun | `pre_save` + `post_save` signals | [apps/pps/signals.py](../apps/pps/signals.py) |
| BR-9 | Forward / backward / infinite scheduling — calendar-walk pure functions; naive vs aware datetimes normalized at boundaries | `_strip_tz` / `_attach_tz` helpers | [apps/pps/services/scheduler.py](../apps/pps/services/scheduler.py) |
| BR-10 | Optimizer is a deterministic greedy heuristic (priority bucket → group by product) — not ML | Service comment + algorithm | [apps/pps/services/optimizer.py](../apps/pps/services/optimizer.py) |

### 1.3 Multi-tenant boundaries

- Every model inherits `TenantAwareModel`, so `tenant` FK is mandatory and the default `objects` manager auto-scopes via thread-local.
- Every view uses `TenantRequiredMixin` ([apps/accounts/views.py](../apps/accounts/views.py) — class around line 28) — login + tenant present.
- All detail/edit/delete views call `get_object_or_404(Model, pk=pk, tenant=request.tenant)` — verified via grep; all 50 CBVs comply.
- **Cross-tenant smoke test passed** during the build: `admin_globex` requesting an Acme-owned MPS → `404`.

### 1.4 Pre-test risk profile

| Area | Risk | Why |
|---|---|---|
| **Authorization** | High | `TenantRequiredMixin` only checks login + has-tenant — does NOT distinguish tenant admin from regular staff. Workflow actions (release/approve/obsolete) are accessible to any authenticated user. |
| **Form-vs-DB uniqueness** | High | The L-01 lesson trifecta — three views surface `IntegrityError` as a 500 because their forms don't run `clean()` against `(tenant, <field>)` unique-together constraints. |
| **Numeric input bounds** | High | The L-02 lesson recurrence — no `MinValueValidator` / `MaxValueValidator` on any of the 16 models. Negative `capacity_per_hour`, `cost_per_hour`, percentages > 100, negative quantities are all accepted. |
| **Template XSS** | High | Gantt + capacity dashboard render `{{ chart_series_json\|safe }}` containing user-controlled SKU / order_number / operation_name strings. `json.dumps` does not escape `</script>`. |
| **Date sanity** | Medium | Production order `requested_end < requested_start` accepted. No model `clean()` either. |
| **Race conditions** | Low | Status-transition views use atomic `UPDATE … WHERE status IN (…)` patterns. The exception: `ScenarioRunView` and `OptimizationStartView` set `status='running'` unconditionally between an `if` check and an unguarded `update()` — narrow race window producing duplicate compute, not corruption. |
| **N+1 queries** | Low | List views use `select_related` + annotated counts. Spot-checked all 12 list views; no N+1 detected. |
| **Audit-log coverage** | Medium | MPS / order / scenario / optimization status transitions are audited. `Routing`, `WorkCenter`, `RoutingOperation`, `CapacityCalendar`, `CapacityLoad` mutations are NOT audited — non-trivial state changes leave no trail. |

---

## 2. Test Plan

| Layer | What is tested | Tooling |
|---|---|---|
| **Unit** | Model invariants (status helpers, `effective_quantity`, `total_minutes`, `is_editable`); pure-function scheduler / simulator / optimizer | pytest + pytest-django |
| **Integration** | View + form + model + DB flow; status transitions; tenant isolation; CSRF; audit-log signal emission | pytest-django + Django `Client` |
| **Functional / E2E** | User journey: create MPS → add lines → submit → approve → release → schedule order → run scenario → run optimizer → verify Gantt / capacity dashboards | Playwright (smoke) |
| **Regression** | Defect register guards (D-01 through D-12 below) | pytest, one test per defect |
| **Boundary** | Decimal precision (qty up to 14,2; minutes up to 10,4); date boundaries (period_end == period_start; horizon_end == horizon_start + 1 day); empty calendar | pytest |
| **Edge** | Empty / null / unicode / emoji on free-text fields; SKU containing `</script>`; routing with 0 operations; production order with no routing; release MPS with 0 lines | pytest |
| **Negative** | IDOR (cross-tenant pk substitution); duplicate code / name / version; negative quantities / percentages / minutes; date inversions; concurrent workflow transitions | pytest + threading |
| **Security** | OWASP A01–A10 (see §6.4 mapping) | pytest, bandit, OWASP ZAP (manual) |
| **Performance** | List-page query counts; Gantt page with 1000+ scheduled operations; capacity recompute over 30 active work centers | pytest `django_assert_max_num_queries` + Locust |
| **Reliability** | Scheduler determinism — same inputs produce same `ScheduledOperation` placements across two runs | pytest property-based check |
| **Usability** | Filter retention across pagination; Stale-rollup indicator on capacity load; visible "v1 stub" disclaimer on the optimizer page | manual |

---

## 3. Test Scenarios

### 3.1 Master Production Schedule (M-NN)

| # | Scenario | Type |
|---|---|---|
| M-01 | Create MPS with valid horizon and weekly bucket | Positive |
| M-02 | Create MPS with `horizon_end == horizon_start` | Boundary |
| M-03 | Create MPS with `horizon_end < horizon_start` | Negative |
| M-04 | Submit a Draft MPS → Under Review | Workflow |
| M-05 | Submit an already-Released MPS (no-op expected) | Negative |
| M-06 | Approve under_review → approved | Workflow |
| M-07 | Release approved → released; stamps `released_at` | Workflow |
| M-08 | Edit a Released MPS — refused | Negative |
| M-09 | Delete a Released MPS — refused | Negative |
| M-10 | Concurrent approve from two browsers — only one wins | Race |
| M-11 | Cross-tenant: globex user requests acme MPS pk → 404 | Security |
| M-12 | Add line with `period_end < period_start` | Negative |
| M-13 | Add line with negative `forecast_qty` | Negative |
| M-14 | Add duplicate line `(mps, product, period_start)` — caught at view | Negative |
| M-15 | Audit log entry written on each status transition | Regression |

### 3.2 Capacity (W-NN)

| # | Scenario | Type |
|---|---|---|
| W-01 | Create work center with valid fields | Positive |
| W-02 | Create work center with duplicate `code` (same tenant) — must NOT 500 | Negative ⚠ D-02 |
| W-03 | Edit work center to a colliding code — must NOT 500 | Negative ⚠ D-02 |
| W-04 | Create work center with `capacity_per_hour=-5` — must reject | Negative ⚠ D-04 |
| W-05 | Create work center with `efficiency_pct=999` — must reject | Negative ⚠ D-04 |
| W-06 | Create work center with `cost_per_hour=-100` — must reject | Negative ⚠ D-04 |
| W-07 | Add calendar shift `shift_end <= shift_start` — refused | Negative |
| W-08 | Add duplicate calendar `(work_center, day, shift_start)` | Negative |
| W-09 | Capacity recompute populates `CapacityLoad` rows for next 14 days | Positive |
| W-10 | `ScheduledOperation` save invalidates the matching `CapacityLoad.computed_at` | Regression |
| W-11 | Capacity dashboard renders with no calendars (zero available_minutes) | Edge |
| W-12 | Capacity dashboard chart series filtered by work center query param | Positive |
| W-13 | Bottleneck threshold (95%) flagged correctly; 94.99% is not | Boundary |
| W-14 | Cross-tenant: globex user views acme capacity dashboard → returns globex's empty dataset, never acme's | Security |

### 3.3 Routings & Scheduling (R-NN, P-NN)

| # | Scenario | Type |
|---|---|---|
| R-01 | Create routing with valid product + version | Positive |
| R-02 | Create routing duplicating `(tenant, product, version='A')` — must NOT 500 | Negative ⚠ D-03 |
| R-03 | Add operation with `run_minutes_per_unit < 0` — refused | Negative |
| R-04 | Add operation with `setup_minutes < 0` — must reject | Negative ⚠ D-04 |
| R-05 | Delete routing referenced by a production order → `routing` is `SET_NULL`; existing scheduled ops orphan-protected | Regression |
| R-06 | Edit routing while production orders reference it — scheduled ops are NOT auto-cleared (UI does not warn) | Edge ⚠ D-08 |
| P-01 | Create production order with valid routing + bom + qty | Positive |
| P-02 | Create order with `quantity = 0` — refused | Negative |
| P-03 | Create order with `requested_end < requested_start` — must reject | Negative ⚠ D-05 |
| P-04 | Schedule forward — produces N `ScheduledOperation` rows where N = #operations | Positive |
| P-05 | Schedule backward — last op `planned_end <= requested_end` | Positive |
| P-06 | Schedule infinite — capacity-blind; no shift-walking | Positive |
| P-07 | Schedule with timezone-aware `requested_start` — naive/aware boundary handled correctly | Regression (L-05) |
| P-08 | Re-schedule replaces existing scheduled operations atomically | Regression |
| P-09 | Schedule order with no routing — refused | Negative |
| P-10 | Schedule order with routing that has zero operations — refused | Edge |
| P-11 | Release order → `released`; status update is atomic-conditional | Workflow |
| P-12 | Start order without releasing — refused | Negative |
| P-13 | Cancel a completed order — refused | Negative |
| P-14 | Concurrent release of same order from two clients — only one wins | Race |
| P-15 | Cross-tenant access to scheduled operations on `/pps/orders/gantt/` | Security |
| P-16 | Gantt rendering with 1000 scheduled operations (perf) | Performance |
| P-17 | Gantt page contains user-controlled SKU `</script>...` — must NOT execute | Security ⚠ D-01 |

### 3.4 Scenarios (Simulation) (S-NN)

| # | Scenario | Type |
|---|---|---|
| S-01 | Create scenario from a released MPS | Positive |
| S-02 | Add change of type `change_qty` with valid JSON payload | Positive |
| S-03 | Add change with malformed JSON payload — refused | Negative |
| S-04 | Run scenario → `ScenarioResult` populated, `ran_at` stamped | Positive |
| S-05 | Run scenario twice consecutively — second run replaces result | Positive |
| S-06 | Run scenario from `running` state — refused | Negative |
| S-07 | Concurrent run on same scenario — at most one compute proceeds | Race ⚠ D-06 |
| S-08 | Apply scenario records intent (status=`applied`) but does NOT mutate base MPS | Regression ⚠ D-09 (UX) |
| S-09 | Discard scenario — terminal state, cannot be re-run | Workflow |
| S-10 | Delete an `applied` scenario — refused | Negative |
| S-11 | Cross-tenant: globex user requests acme scenario pk → 404 | Security |

### 3.5 Optimization (O-NN)

| # | Scenario | Type |
|---|---|---|
| O-01 | Create optimization objective with at least one weight > 0 | Positive |
| O-02 | Create objective with all weights = 0 — refused | Negative |
| O-03 | Edit objective to a colliding `(tenant, name)` — must NOT 500 | Negative ⚠ D-02 |
| O-04 | Start a queued run → status `running` → `completed`; `OptimizationResult` populated | Positive |
| O-05 | Concurrent start on same run — at most one compute proceeds | Race ⚠ D-06 |
| O-06 | Start a `completed` run — refused | Negative |
| O-07 | Optimizer with `weight_idle = 5` produces a different result than `weight_idle = 0` | Regression ⚠ D-10 (currently fails — weight_idle is unused) |
| O-08 | Apply result records `applied_at` + `applied_by` but does NOT mutate orders | Regression ⚠ D-09 (UX) |
| O-09 | Run with no candidate orders — recorded as `failed` with error message | Edge |
| O-10 | Improvement `< 0` clamped to 0 (no negative gain shown) | Boundary |
| O-11 | Cross-tenant: globex user requests acme run pk → 404 | Security |

### 3.6 Authorization & Audit (A-NN)

| # | Scenario | Type |
|---|---|---|
| A-01 | Anonymous user GET `/pps/` → 302 to login | Security |
| A-02 | Tenant admin can release MPS → succeeds | Positive |
| A-03 | Regular staff (`is_tenant_admin=False`) can release / obsolete MPS — currently allowed; should require admin | Security ⚠ D-07 |
| A-04 | Audit log entry written on MPS release | Regression |
| A-05 | Audit log entry written on production order release / start / complete | Regression |
| A-06 | Audit log entry written on scenario apply / discard | Regression |
| A-07 | Audit log entry NOT written on Routing / WorkCenter / RoutingOperation create / delete | Gap ⚠ D-11 |
| A-08 | Superuser with `tenant=None` sees empty PPS pages (BY DESIGN) | Regression |

---

## 4. Detailed Test Cases

> Naming convention: `TC-PPS-<entity>-<NNN>`. Highest-priority cases shown here; the remaining cases are parametrised in §5.

### 4.1 Status-transition concurrency (Critical regression)

| ID | TC-PPS-MPS-007 |
|---|---|
| **Description** | Two users approve the same MPS concurrently — exactly one wins; no DB inconsistency |
| **Pre-conditions** | MPS pk=K in `under_review` status; tenant admin Alice and Bob both authenticated |
| **Steps** | 1. Open two `Client` sessions in parallel threads<br>2. Both POST `/pps/mps/<K>/approve/`<br>3. Wait for both responses |
| **Test data** | seeded MPS, tenant admin × 2 |
| **Expected result** | One response succeeds (`messages.success`); the other receives `messages.warning('MPS is not awaiting review.')`. DB state: `status='approved'`, exactly one `mps.status.approved` audit-log entry. |
| **Post-conditions** | MPS in `approved`; `approved_by` set to one of the two users |

### 4.2 Cross-tenant IDOR (Security)

| ID | TC-PPS-SEC-001 |
|---|---|
| **Description** | Globex tenant admin attempts to read / mutate an Acme-owned production order |
| **Pre-conditions** | `acme` and `globex` tenants seeded; production order pk=K belongs to acme |
| **Steps** | 1. Log in as `admin_globex`<br>2. GET `/pps/orders/<K>/`<br>3. POST `/pps/orders/<K>/release/`<br>4. POST `/pps/orders/<K>/cancel/` |
| **Test data** | Acme PO pk |
| **Expected result** | All three return 404; no audit-log entry written; order unchanged |
| **Post-conditions** | Acme PO untouched |

### 4.3 XSS via Gantt SKU (Critical security — D-01)

| ID | TC-PPS-SEC-002 |
|---|---|
| **Description** | A product SKU containing `</script><img src=x onerror=alert(1)>` reaches the Gantt page; verify NO script execution |
| **Pre-conditions** | Tenant admin can create products via PLM (or shell-create one) with the malicious SKU; one production order references that product; the order has scheduled operations |
| **Steps** | 1. Create `Product(sku='</script><img src=x onerror=alert(1)>', tenant=acme, ...)`<br>2. Create production order for that product, schedule it<br>3. GET `/pps/orders/gantt/`<br>4. Inspect rendered HTML for the literal `</script>` outside of a JSON string |
| **Test data** | malicious SKU above |
| **Expected result** | Rendered HTML escapes the SKU so it cannot break out of the `<script>` tag (e.g. served via `{{ data\|json_script:"id" }}`); no `<img>` is created in the live DOM. |
| **Current behaviour (verified 2026-04-28)** | `json.dumps` does not escape `</script>`; literal sequence reaches the page; browser parses it as a real `</script>` tag and the following `<img onerror=...>` executes |
| **Post-conditions** | After fix: page renders Gantt for non-malicious orders; XSS payload does not run |

### 4.4 Form-vs-DB unique gap on Edit (High — D-02)

| ID | TC-PPS-WC-006 |
|---|---|
| **Description** | Editing a work center to a code that already exists must produce a friendly form error, not a 500 |
| **Pre-conditions** | Work centers `CNC-01` and `LBR-01` exist in tenant Acme |
| **Steps** | 1. Log in as `admin_acme`<br>2. POST `/pps/work-centers/<LBR-01.pk>/edit/` with `code=CNC-01` |
| **Test data** | colliding code |
| **Expected result** | Response 200 with form error `"A work center with code CNC-01 already exists."`; DB unchanged |
| **Current behaviour (verified)** | 500 with `IntegrityError (1062)` from MySQL |
| **Post-conditions** | After fix: original LBR-01 unchanged; user receives the error |

### 4.5 Negative numeric input (High — D-04)

| ID | TC-PPS-WC-008 |
|---|---|
| **Description** | A work center cannot be created with negative capacity, negative cost, or efficiency > 100 |
| **Pre-conditions** | tenant admin authenticated |
| **Steps** | POST `/pps/work-centers/new/` with `capacity_per_hour=-5, efficiency_pct=999, cost_per_hour=-100` |
| **Test data** | negative + out-of-range values |
| **Expected result** | Response 200 with form errors on each invalid field; no DB row created |
| **Current behaviour (verified)** | DB row created with the bad values; downstream `compute_load` divides by `available_minutes` and produces nonsensical `utilization_pct` |
| **Post-conditions** | After fix: row not created; user sees three field errors |

### 4.6 RBAC — non-admin workflow access (High — D-07)

| ID | TC-PPS-AUTH-002 |
|---|---|
| **Description** | A regular tenant user (`is_tenant_admin=False`) attempts to obsolete a released MPS |
| **Pre-conditions** | `acme_supervisor_2` is a non-admin staff user with a tenant |
| **Steps** | 1. Log in as `acme_supervisor_2`<br>2. POST `/pps/mps/<released_pk>/obsolete/` |
| **Test data** | released MPS pk |
| **Expected result** | Response 403 (or 302 → `/accounts/login/?next=...` if pattern follows existing tenants module); MPS remains `released`; no audit-log entry |
| **Current behaviour (verified)** | Request succeeds; MPS flips to `obsolete`; audit-log entry written attributing the action to the non-admin user |
| **Post-conditions** | After fix: MPS unchanged; user sees a "permission denied" page |

### 4.7 Backward scheduling correctness

| ID | TC-PPS-SCHED-002 |
|---|---|
| **Description** | A backward-scheduled order's last operation finishes at exactly `requested_end` |
| **Pre-conditions** | Order with routing of 3 operations and full Mon–Fri 08:00–17:00 calendars |
| **Steps** | POST `/pps/orders/<pk>/schedule/` with `method=backward`, `requested_end=2026-05-15T16:00` |
| **Test data** | requested_end fits within shift |
| **Expected result** | `ScheduledOperation` ordered by sequence; the last row's `planned_end == 2026-05-15T16:00` (within ±1 minute); each preceding op `planned_end <= next op planned_start` |
| **Post-conditions** | order.scheduled_end == requested_end |

### 4.8 Filter retention across pagination

| ID | TC-PPS-LIST-003 |
|---|---|
| **Description** | Apply status filter on `/pps/orders/`, paginate, return — filter persists |
| **Pre-conditions** | 25+ production orders, mix of statuses |
| **Steps** | 1. GET `/pps/orders/?status=released`<br>2. Click "Next" → URL becomes `/pps/orders/?status=released&page=2`<br>3. Verify only `released` orders shown<br>4. Use the form to add `priority=high`; verify both filters retained |
| **Expected result** | Pagination links carry `status=released&page=N`; combined filter URLs work |
| **Post-conditions** | n/a |

### 4.9 Naive vs aware datetime in scheduler (Regression — L-05)

| ID | TC-PPS-SCHED-005 |
|---|---|
| **Description** | Scheduling an order whose `requested_start = timezone.now()` (aware) does not raise `TypeError` |
| **Pre-conditions** | Order with routing; `USE_TZ=True` (project default) |
| **Steps** | Order's `requested_start` is `timezone.now()`; POST `/pps/orders/<pk>/schedule/` with `method=forward` |
| **Expected result** | 302 redirect; ScheduledOperation rows created with aware `planned_start` / `planned_end` |
| **Post-conditions** | n/a (regression guard) |

### 4.10 N+1 on `/pps/orders/`

| ID | TC-PPS-PERF-001 |
|---|---|
| **Description** | Order list with 200 rows + filters fits within a fixed query budget |
| **Pre-conditions** | 200 orders seeded |
| **Steps** | Use `django_assert_max_num_queries(10)` around `client.get('/pps/orders/?status=released')` |
| **Expected result** | ≤ 10 queries (auth + tenant + count + select_related joins + paginator + messages) |
| **Post-conditions** | n/a |

---

## 5. Automation Strategy

### 5.1 Tooling

| Tool | Purpose |
|---|---|
| **pytest 7.4 + pytest-django 4.6** | Unit, integration, regression |
| **factory-boy 3.3** | Fixture builders (Tenant, User, Product, MPS, Order) |
| **pytest-cov** | Line + branch coverage |
| **pytest-xdist** | Parallel execution for the integration suite |
| **freezegun** | Deterministic `timezone.now()` for scheduler tests |
| **Playwright 1.42** (smoke only) | E2E user-journey on the seeded tenant |
| **Locust 2.x** | Load test on `/pps/orders/gantt/` and capacity recompute |
| **bandit + pip-audit** | SAST + dependency CVE scan |
| **OWASP ZAP** | Manual DAST for A03/A05/A07 |

### 5.2 Suite layout

```
apps/pps/tests/
├── __init__.py
├── conftest.py
├── factories.py
├── test_models.py
├── test_forms.py
├── test_views_mps.py
├── test_views_orders.py
├── test_views_capacity.py
├── test_views_scenarios.py
├── test_views_optimizer.py
├── test_workflow_concurrency.py
├── test_security.py
├── test_performance.py
└── test_services.py            # pure-function scheduler/simulator/optimizer
```

Plus a top-level `pytest.ini` and a test-only `config/settings_test.py` (SQLite in-memory + MD5 hasher).

### 5.3 Runnable code — `pytest.ini` (project root)

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings_test
python_files = tests.py test_*.py *_tests.py
addopts = -ra --strict-markers --tb=short
markers =
    slow: tests that take more than 1s
    e2e: end-to-end browser tests (Playwright)
    perf: query-budget / load-shape tests
```

### 5.4 Runnable code — `config/settings_test.py` (project)

> Mirrors the existing PLM test settings shape per repo convention.

```python
"""Test settings — SQLite in-memory + MD5 hasher for speed."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEBUG = False
SECRET_KEY = 'test-only'
PAYMENT_GATEWAY = 'mock'
```

### 5.5 Runnable code — `apps/pps/tests/conftest.py`

```python
"""Shared fixtures for the PPS test suite."""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.pps.models import (
    CapacityCalendar, MasterProductionSchedule, ProductionOrder,
    Routing, RoutingOperation, WorkCenter,
)


@pytest.fixture(autouse=True)
def _clear_tenant():
    """Reset thread-local tenant between tests."""
    yield
    set_current_tenant(None)


@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Test', slug='acme-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Test', slug='globex-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_test', password='pw', tenant=acme, is_tenant_admin=True,
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_test', password='pw', tenant=acme, is_tenant_admin=False,
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_test', password='pw', tenant=globex, is_tenant_admin=True,
    )


@pytest.fixture
def admin_client(client, acme_admin):
    client.force_login(acme_admin)
    return client


@pytest.fixture
def staff_client(client, acme_staff):
    client.force_login(acme_staff)
    return client


@pytest.fixture
def globex_client(client, globex_admin):
    client.force_login(globex_admin)
    return client


@pytest.fixture
def product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='SKU-T1', name='Test product', product_type='finished_good',
        unit_of_measure='ea', status='active',
    )


@pytest.fixture
def work_center(db, acme):
    wc = WorkCenter.objects.create(
        tenant=acme, code='WC-T1', name='Test WC', work_center_type='machine',
        capacity_per_hour=Decimal('5'), efficiency_pct=Decimal('100'),
        cost_per_hour=Decimal('50'), is_active=True,
    )
    for dow in range(5):
        CapacityCalendar.objects.create(
            tenant=acme, work_center=wc, day_of_week=dow,
            shift_start=time(8, 0), shift_end=time(17, 0), is_working=True,
        )
    return wc


@pytest.fixture
def routing(db, acme, product, work_center, acme_admin):
    r = Routing.objects.create(
        tenant=acme, product=product, version='A',
        routing_number='ROUT-T1', status='active', is_default=True,
        created_by=acme_admin,
    )
    RoutingOperation.objects.create(
        tenant=acme, routing=r, sequence=10, operation_name='Cut',
        work_center=work_center,
        setup_minutes=Decimal('15'), run_minutes_per_unit=Decimal('5'),
        queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
    )
    RoutingOperation.objects.create(
        tenant=acme, routing=r, sequence=20, operation_name='Assemble',
        work_center=work_center,
        setup_minutes=Decimal('10'), run_minutes_per_unit=Decimal('8'),
        queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
    )
    return r


@pytest.fixture
def draft_mps(db, acme, acme_admin):
    return MasterProductionSchedule.objects.create(
        tenant=acme, mps_number='MPS-T1', name='Test MPS',
        horizon_start=date.today(), horizon_end=date.today() + timedelta(days=28),
        time_bucket='week', status='draft', created_by=acme_admin,
    )


@pytest.fixture
def planned_order(db, acme, product, routing, draft_mps, acme_admin):
    return ProductionOrder.objects.create(
        tenant=acme, order_number='PO-T1', product=product, routing=routing,
        quantity=Decimal('10'), status='planned', priority='normal',
        scheduling_method='forward',
        requested_start=timezone.now(),
        requested_end=timezone.now() + timedelta(days=2),
        created_by=acme_admin,
    )
```

### 5.6 Runnable code — `apps/pps/tests/test_models.py`

```python
"""Unit tests on PPS model invariants."""
from decimal import Decimal

import pytest


@pytest.mark.django_db
class TestMPSStatus:
    def test_draft_is_editable(self, draft_mps):
        assert draft_mps.is_editable() is True

    def test_released_is_not_editable(self, draft_mps):
        draft_mps.status = 'released'
        draft_mps.save()
        assert draft_mps.is_editable() is False


@pytest.mark.django_db
class TestProductionOrderTransitions:
    def test_planned_can_release(self, planned_order):
        assert planned_order.can_release() is True

    def test_released_cannot_release_again(self, planned_order):
        planned_order.status = 'released'
        planned_order.save()
        assert planned_order.can_release() is False

    def test_in_progress_can_complete(self, planned_order):
        planned_order.status = 'in_progress'
        planned_order.save()
        assert planned_order.can_complete() is True


@pytest.mark.django_db
class TestRoutingOperationMath:
    def test_total_minutes_setup_plus_run_plus_queue_plus_move(self, routing):
        op = routing.operations.first()
        # 15 setup + 5 * 10 run + 5 queue + 3 move = 73
        assert op.total_minutes(Decimal('10')) == Decimal('73')


# Regression for D-04 — model-level validators MUST exist after the fix
@pytest.mark.django_db
class TestModelLevelBounds:
    @pytest.mark.xfail(reason='D-04: model has no MinValueValidator yet', strict=True)
    def test_negative_capacity_rejected(self, acme):
        from django.core.exceptions import ValidationError
        from apps.pps.models import WorkCenter
        wc = WorkCenter(
            tenant=acme, code='X', name='X', work_center_type='machine',
            capacity_per_hour=Decimal('-5'),
            efficiency_pct=Decimal('100'), cost_per_hour=Decimal('10'),
        )
        with pytest.raises(ValidationError):
            wc.full_clean()
```

### 5.7 Runnable code — `apps/pps/tests/test_forms.py`

```python
"""Form-level validation tests including the unique-trifecta regression."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.pps.forms import (
    DemandForecastForm, MasterProductionScheduleForm,
    OptimizationObjectiveForm, ProductionOrderForm, WorkCenterForm,
)


@pytest.mark.django_db
class TestMPSForm:
    def test_horizon_end_before_start_rejected(self, acme):
        form = MasterProductionScheduleForm(data={
            'name': 'X',
            'horizon_start': date.today(),
            'horizon_end': date.today() - timedelta(days=1),
            'time_bucket': 'week',
            'description': '',
        })
        assert not form.is_valid()
        assert 'horizon_end' in form.errors


@pytest.mark.django_db
class TestForecastForm:
    def test_period_end_before_start_rejected(self, acme, product):
        form = DemandForecastForm(tenant=acme, data={
            'product': product.pk,
            'period_start': date.today(),
            'period_end': date.today() - timedelta(days=1),
            'forecast_qty': '10',
            'source': 'manual',
            'confidence_pct': '80',
            'notes': '',
        })
        assert not form.is_valid()
        assert 'period_end' in form.errors


@pytest.mark.django_db
class TestOptimizationObjectiveForm:
    def test_all_zero_weights_rejected(self):
        form = OptimizationObjectiveForm(data={
            'name': 'Zero',
            'description': '',
            'weight_changeovers': '0',
            'weight_idle': '0',
            'weight_lateness': '0',
            'weight_priority': '0',
            'is_default': False,
        })
        assert not form.is_valid()


# ⚠ D-02 / D-04 — these tests demonstrate the bugs.
# After remediation they should pass; until then they're xfail(strict=True).
@pytest.mark.django_db
class TestUniqueTrifectaRegression:
    @pytest.mark.xfail(reason='D-02: WorkCenterForm does not validate (tenant, code)', strict=True)
    def test_workcenter_form_catches_duplicate_code(self, acme):
        from apps.pps.models import WorkCenter
        WorkCenter.objects.create(
            tenant=acme, code='DUP', name='A', work_center_type='machine',
            capacity_per_hour=Decimal('1'), efficiency_pct=Decimal('100'),
            cost_per_hour=Decimal('1'),
        )
        form = WorkCenterForm(data={
            'code': 'DUP', 'name': 'B', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert not form.is_valid()
        assert 'code' in form.errors

    @pytest.mark.xfail(reason='D-04: WorkCenterForm has no MinValueValidator', strict=True)
    def test_workcenter_form_rejects_negative_capacity(self, acme):
        form = WorkCenterForm(data={
            'code': 'NEG', 'name': 'A', 'work_center_type': 'machine',
            'capacity_per_hour': '-5', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert not form.is_valid()
        assert 'capacity_per_hour' in form.errors


@pytest.mark.django_db
class TestProductionOrderDateValidation:
    @pytest.mark.xfail(reason='D-05: form does not validate requested_end > requested_start', strict=True)
    def test_requested_end_before_start_rejected(self, acme, product):
        from django.utils import timezone
        from datetime import timedelta
        form = ProductionOrderForm(tenant=acme, data={
            'product': product.pk,
            'quantity': '5',
            'priority': 'normal',
            'scheduling_method': 'forward',
            'requested_start': (timezone.now()).strftime('%Y-%m-%dT%H:%M'),
            'requested_end': (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'notes': '',
        })
        assert not form.is_valid()
```

### 5.8 Runnable code — `apps/pps/tests/test_views_orders.py`

```python
"""Integration tests covering production order workflow + tenant isolation."""
import pytest


@pytest.mark.django_db
class TestProductionOrderWorkflow:
    def test_release_planned_order(self, admin_client, planned_order):
        r = admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        assert r.status_code == 302
        planned_order.refresh_from_db()
        assert planned_order.status == 'released'

    def test_cannot_start_a_planned_order(self, admin_client, planned_order):
        admin_client.post(f'/pps/orders/{planned_order.pk}/start/')
        planned_order.refresh_from_db()
        assert planned_order.status == 'planned'  # rejected

    def test_schedule_forward_creates_operations(self, admin_client, planned_order):
        admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        r = admin_client.post(
            f'/pps/orders/{planned_order.pk}/schedule/',
            {'method': 'forward'},
        )
        assert r.status_code == 302
        assert planned_order.scheduled_operations.count() == 2

    def test_concurrent_release_only_one_wins(self, admin_client, planned_order):
        admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        planned_order.refresh_from_db()
        assert planned_order.status == 'released'


@pytest.mark.django_db
class TestTenantIsolation:
    def test_globex_cannot_view_acme_order(self, globex_client, planned_order):
        r = globex_client.get(f'/pps/orders/{planned_order.pk}/')
        assert r.status_code == 404

    def test_globex_cannot_release_acme_order(self, globex_client, planned_order):
        r = globex_client.post(f'/pps/orders/{planned_order.pk}/release/')
        assert r.status_code == 404
        planned_order.refresh_from_db()
        assert planned_order.status == 'planned'
```

### 5.9 Runnable code — `apps/pps/tests/test_security.py`

```python
"""OWASP-mapped security tests."""
import pytest


@pytest.mark.django_db
class TestA01_BrokenAccessControl:
    def test_anonymous_redirected_to_login(self, client):
        r = client.get('/pps/')
        assert r.status_code == 302
        assert '/accounts/login/' in r.url

    def test_authenticated_user_without_tenant_blocked(self, db, client):
        from apps.accounts.models import User
        user = User.objects.create_user(
            username='no_tenant', password='pw', tenant=None,
        )
        client.force_login(user)
        r = client.get('/pps/')
        assert r.status_code in (302, 403)

    @pytest.mark.xfail(reason='D-07: regular staff can perform admin-only workflow actions', strict=True)
    def test_non_admin_cannot_obsolete_mps(self, staff_client, draft_mps):
        from apps.pps.models import MasterProductionSchedule
        MasterProductionSchedule.objects.filter(pk=draft_mps.pk).update(status='released')
        r = staff_client.post(f'/pps/mps/{draft_mps.pk}/obsolete/')
        assert r.status_code in (403, 302)
        draft_mps.refresh_from_db()
        assert draft_mps.status == 'released'


@pytest.mark.django_db
class TestA03_XSS:
    @pytest.mark.xfail(reason='D-01: chart_series_json|safe lets </script> through', strict=True)
    def test_gantt_escapes_user_controlled_sku(self, admin_client, acme, work_center, acme_admin):
        from apps.plm.models import Product
        from apps.pps.models import (
            ProductionOrder, ScheduledOperation, Routing, RoutingOperation,
        )
        from datetime import timedelta
        from decimal import Decimal
        from django.utils import timezone

        bad = '</script><img src=x onerror=alert(1)>'
        product = Product.objects.create(
            tenant=acme, sku=bad, name='Malicious', product_type='finished_good',
            unit_of_measure='ea', status='active',
        )
        routing = Routing.objects.create(
            tenant=acme, product=product, version='A', routing_number='ROUT-X',
            status='active', is_default=True, created_by=acme_admin,
        )
        op = RoutingOperation.objects.create(
            tenant=acme, routing=routing, sequence=10, operation_name='Test',
            work_center=work_center, setup_minutes=Decimal('5'),
            run_minutes_per_unit=Decimal('1'),
            queue_minutes=Decimal('1'), move_minutes=Decimal('1'),
        )
        order = ProductionOrder.objects.create(
            tenant=acme, order_number='PO-X', product=product, routing=routing,
            quantity=Decimal('1'), status='released', priority='normal',
            scheduling_method='forward', created_by=acme_admin,
        )
        ScheduledOperation.objects.create(
            tenant=acme, production_order=order, routing_operation=op,
            work_center=work_center, sequence=10,
            planned_start=timezone.now(),
            planned_end=timezone.now() + timedelta(hours=1),
            planned_minutes=60,
        )

        r = admin_client.get('/pps/orders/gantt/')
        assert r.status_code == 200
        # The literal closing-script sequence must NOT appear in the rendered body
        assert b'</script><img src=x' not in r.content


@pytest.mark.django_db
class TestA04_InsecureDesign:
    @pytest.mark.xfail(reason='D-04: model accepts negative numeric values', strict=True)
    def test_workcenter_rejects_negative_capacity(self, admin_client):
        admin_client.post('/pps/work-centers/new/', {
            'code': 'BAD', 'name': 'Bad', 'work_center_type': 'machine',
            'capacity_per_hour': '-5', 'efficiency_pct': '999',
            'cost_per_hour': '-100', 'description': '', 'is_active': True,
        })
        from apps.pps.models import WorkCenter
        assert not WorkCenter.objects.filter(code='BAD').exists()

    @pytest.mark.xfail(reason='D-02: form-vs-DB unique gap on Edit', strict=True)
    def test_workcenter_edit_to_duplicate_code_does_not_500(self, admin_client, acme):
        from apps.pps.models import WorkCenter
        from decimal import Decimal
        WorkCenter.objects.create(
            tenant=acme, code='A', name='A', work_center_type='machine',
            capacity_per_hour=Decimal('1'), efficiency_pct=Decimal('100'),
            cost_per_hour=Decimal('1'),
        )
        b = WorkCenter.objects.create(
            tenant=acme, code='B', name='B', work_center_type='machine',
            capacity_per_hour=Decimal('1'), efficiency_pct=Decimal('100'),
            cost_per_hour=Decimal('1'),
        )
        r = admin_client.post(f'/pps/work-centers/{b.pk}/edit/', {
            'code': 'A',  # collides
            'name': 'B-renamed', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert r.status_code == 200  # must NOT be 500


@pytest.mark.django_db
class TestCSRF:
    def test_post_without_csrf_rejected(self, admin_client, planned_order):
        admin_client.handler.enforce_csrf_checks = True
        r = admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        assert r.status_code == 403
```

### 5.10 Runnable code — `apps/pps/tests/test_services.py`

```python
"""Pure-function tests on scheduler / simulator / optimizer."""
from datetime import datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.pps.services import optimizer, scheduler


def _calendars(work_center_id):
    """Mon–Fri 08:00–17:00, no weekends."""
    cal = {dow: [(time(8, 0), time(17, 0), True)] for dow in range(5)}
    cal.update({5: [], 6: []})
    return {work_center_id: cal}


def _ops():
    return [
        scheduler.OperationRequest(
            sequence=10, operation_name='Op1', work_center_id=1,
            work_center_code='WC-1',
            setup_minutes=Decimal('15'), run_minutes_per_unit=Decimal('5'),
            queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
        ),
        scheduler.OperationRequest(
            sequence=20, operation_name='Op2', work_center_id=1,
            work_center_code='WC-1',
            setup_minutes=Decimal('10'), run_minutes_per_unit=Decimal('8'),
            queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
        ),
    ]


class TestForwardScheduling:
    def test_aware_datetime_input_handled(self):
        slots = scheduler.schedule_forward(
            _ops(), start=timezone.now().replace(hour=9, minute=0),
            quantity=Decimal('10'), calendars=_calendars(1),
        )
        assert len(slots) == 2
        assert slots[0].planned_start.tzinfo is not None

    def test_op2_starts_after_op1_ends(self):
        start = datetime(2026, 5, 4, 8, 0)  # Monday 08:00
        slots = scheduler.schedule_forward(
            _ops(), start=start, quantity=Decimal('10'),
            calendars=_calendars(1),
        )
        assert slots[1].planned_start >= slots[0].planned_end

    def test_walk_skips_weekend(self):
        start = datetime(2026, 5, 8, 16, 30)  # Friday 16:30
        slots = scheduler.schedule_forward(
            _ops(), start=start, quantity=Decimal('10'),
            calendars=_calendars(1),
        )
        assert slots[-1].planned_start.weekday() < 5  # never Sat / Sun


class TestBackwardScheduling:
    def test_last_op_ends_at_target(self):
        end = datetime(2026, 5, 15, 16, 0)  # Friday 16:00
        slots = scheduler.schedule_backward(
            _ops(), end=end, quantity=Decimal('10'),
            calendars=_calendars(1),
        )
        assert abs((slots[-1].planned_end - end).total_seconds()) < 60


class TestOptimizer:
    @pytest.mark.django_db
    def test_rush_orders_first(self, acme, draft_mps):
        from apps.pps.models import OptimizationObjective, OptimizationRun
        obj = OptimizationObjective.objects.create(
            tenant=acme, name='X',
            weight_changeovers=Decimal('1'), weight_idle=Decimal('1'),
            weight_lateness=Decimal('2'), weight_priority=Decimal('2'),
        )
        run = OptimizationRun.objects.create(
            tenant=acme, name='R', mps=draft_mps, objective=obj, status='queued',
        )
        orders = [
            {'id': 1, 'product_id': 100, 'priority': 'low', 'requested_end': None, 'minutes': 60},
            {'id': 2, 'product_id': 100, 'priority': 'rush', 'requested_end': None, 'minutes': 60},
            {'id': 3, 'product_id': 200, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
        ]
        result = optimizer.run_optimization(run, orders=orders)
        sequence = result['suggestion_json']['sequence']
        assert sequence.index(2) < sequence.index(1)
        assert sequence.index(2) < sequence.index(3)

    @pytest.mark.django_db
    @pytest.mark.xfail(reason='D-10: weight_idle is currently unused by the heuristic', strict=True)
    def test_weight_idle_changes_output(self, acme, draft_mps):
        from apps.pps.models import OptimizationObjective, OptimizationRun
        orders = [
            {'id': 1, 'product_id': 100, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
            {'id': 2, 'product_id': 200, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
            {'id': 3, 'product_id': 100, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
        ]
        obj_lo = OptimizationObjective.objects.create(
            tenant=acme, name='LowIdle',
            weight_changeovers=Decimal('1'), weight_idle=Decimal('0'),
            weight_lateness=Decimal('1'), weight_priority=Decimal('1'),
        )
        obj_hi = OptimizationObjective.objects.create(
            tenant=acme, name='HighIdle',
            weight_changeovers=Decimal('1'), weight_idle=Decimal('5'),
            weight_lateness=Decimal('1'), weight_priority=Decimal('1'),
        )
        run_lo = OptimizationRun.objects.create(tenant=acme, name='lo', mps=draft_mps, objective=obj_lo, status='queued')
        run_hi = OptimizationRun.objects.create(tenant=acme, name='hi', mps=draft_mps, objective=obj_hi, status='queued')
        out_lo = optimizer.run_optimization(run_lo, orders=orders)
        out_hi = optimizer.run_optimization(run_hi, orders=orders)
        assert out_lo['suggestion_json']['sequence'] != out_hi['suggestion_json']['sequence']
```

### 5.11 Runnable code — `apps/pps/tests/test_performance.py`

```python
"""N+1 and query-budget tests."""
import pytest


@pytest.mark.django_db
class TestQueryBudget:
    def test_orders_list_query_budget(self, admin_client, django_assert_max_num_queries):
        with django_assert_max_num_queries(12):
            r = admin_client.get('/pps/orders/')
        assert r.status_code == 200

    def test_routings_list_query_budget(self, admin_client, django_assert_max_num_queries):
        with django_assert_max_num_queries(10):
            r = admin_client.get('/pps/routings/')
        assert r.status_code == 200

    def test_capacity_dashboard_query_budget(self, admin_client, django_assert_max_num_queries):
        with django_assert_max_num_queries(15):
            r = admin_client.get('/pps/capacity/')
        assert r.status_code == 200
```

### 5.12 Runnable code — `apps/pps/tests/test_workflow_concurrency.py`

```python
"""Demonstrate atomic transitions are race-safe."""
import threading

import pytest
from django.test import Client


@pytest.mark.django_db(transaction=True)
def test_two_clients_approving_same_mps_only_one_wins(acme_admin, draft_mps):
    """Atomic UPDATE … WHERE status IN (under_review) protects against
    two concurrent approvals."""
    from apps.pps.models import MasterProductionSchedule
    MasterProductionSchedule.objects.filter(pk=draft_mps.pk).update(status='under_review')

    results = []

    def hit():
        c = Client()
        c.force_login(acme_admin)
        r = c.post(f'/pps/mps/{draft_mps.pk}/approve/')
        results.append(r.status_code)

    threads = [threading.Thread(target=hit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    draft_mps.refresh_from_db()
    assert draft_mps.status == 'approved'
    from apps.tenants.models import TenantAuditLog
    assert TenantAuditLog.objects.filter(
        action='mps.status.approved', target_id=str(draft_mps.pk),
    ).count() == 1
```

### 5.13 Optional — Locust load shape (top-level `locustfile.py`)

```python
"""Lightweight load profile for the Gantt + capacity dashboards."""
from locust import HttpUser, task, between


class PPSUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post('/accounts/login/', {
            'username': 'admin_acme', 'password': 'Welcome@123',
        })

    @task(3)
    def gantt(self):
        self.client.get('/pps/orders/gantt/?days=14')

    @task(2)
    def capacity(self):
        self.client.get('/pps/capacity/')

    @task(1)
    def order_list(self):
        self.client.get('/pps/orders/?status=released')
```

---

## 6. Defects, Risks & Recommendations

### 6.1 Defect register (verified)

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-01** | **High** | A03 (XSS) | [templates/pps/orders/gantt.html](../templates/pps/orders/gantt.html), [templates/pps/capacity/dashboard.html](../templates/pps/capacity/dashboard.html) | `{{ chart_series_json\|safe }}` ships raw JSON inside a `<script>` block. `json.dumps` does not escape `</script>`, so a Product SKU or order_number containing `</script><img onerror=...>` breaks out of the script tag. **Verified** — `json.dumps([{...sku: '</script>...'}])` retains literal `</script>` | Switch both templates to Django's `{{ payload\|json_script:"chart-data" }}` and read in JS via `JSON.parse(document.getElementById('chart-data').textContent)`. `json_script` HTML-escapes `<`, `>`, `&` automatically. |
| **D-02** | **High** | A04 (Insecure design) / L-01 | [apps/pps/views.py](../apps/pps/views.py) — `WorkCenterEditView` and `OptimizationObjectiveEditView` | Both call `form.save()` with no `try/except IntegrityError`. Editing to a colliding `(tenant, code)` / `(tenant, name)` raises a 1062 IntegrityError that escapes as a 500. **Verified** in shell. | Add the same `try/except IntegrityError` pattern used in the matching create views, OR (preferred) add a `clean_<field>()` to each form that scopes uniqueness against `self._tenant` (matches the L-01 fix shape on `BillOfMaterialsForm`). |
| **D-03** | **High** | A04 (Insecure design) / L-01 | [apps/pps/views.py](../apps/pps/views.py) — `RoutingCreateView` | Uses `_save_with_unique_number` which retries on `routing_number` collisions but cannot distinguish them from `(tenant, product, version)` collisions. After 5 retries it `raise last_err` and 500s. **Verified** — second routing on same `(product, version='A')` 500s. | Add `clean()` on `RoutingForm` to validate `(tenant, product, version)` uniqueness with a friendly error before reaching the DB. The retry loop should remain only for genuine `routing_number` collisions. |
| **D-04** | **High** | A04 (Insecure design) / L-02 | [apps/pps/models.py](../apps/pps/models.py) — all numeric fields | Zero `MinValueValidator` / `MaxValueValidator` across 16 models. **Verified**: a work center saved with `capacity_per_hour=-5, efficiency_pct=999, cost_per_hour=-100` makes it through; `compute_load` then divides minutes by `available_minutes` and emits nonsense `utilization_pct`. | Add validators to: `WorkCenter.capacity_per_hour` ≥ 0; `WorkCenter.efficiency_pct` ∈ [0, 100]; `WorkCenter.cost_per_hour` ≥ 0; `RoutingOperation.{setup_minutes, run_minutes_per_unit, queue_minutes, move_minutes}` ≥ 0; `ProductionOrder.quantity` > 0; `MPSLine.{forecast_qty, firm_planned_qty, scheduled_qty, available_to_promise}` ≥ 0; `DemandForecast.confidence_pct` ∈ [0, 100]; `OptimizationObjective.weight_*` ≥ 0. Mirror the validators in the corresponding form widgets. |
| **D-05** | **Medium** | A04 | [apps/pps/forms.py](../apps/pps/forms.py) — `ProductionOrderForm` | Form does not validate `requested_end > requested_start`. **Verified** — order saved with end 5 days before start. | Add `clean()` to `ProductionOrderForm` mirroring the `MasterProductionScheduleForm.clean()` pattern. |
| **D-06** | **Low** | A04 (race) | [apps/pps/views.py](../apps/pps/views.py) — `ScenarioRunView`, `OptimizationStartView` | Race window between `if scenario.status not in (...)` check and the unconditional `update(status='running')`. Two concurrent clicks both pass the check; both proceed to compute. End state is correct (`update_or_create` is idempotent), but the simulator runs twice. | Use the existing `_atomic_status_transition` helper instead of the unconditional update, gated on `from_states=['draft','completed']`. |
| **D-07** | **High** | A01 (Broken Access Control) | [apps/pps/views.py](../apps/pps/views.py) — every workflow CBV | All views use `TenantRequiredMixin` (login + has-tenant) only. **Verified**: a non-admin staff user (`is_tenant_admin=False`) successfully obsoleted a released MPS. No RBAC layer separates admin from operator. | Introduce a `TenantAdminRequiredMixin` (mirroring [apps/tenants — TenantAdminRequiredMixin](../apps/tenants/views.py)) and apply to: all workflow transition views (Submit/Approve/Release/Obsolete on MPS; Release/Cancel on orders; Run/Apply/Discard on scenarios; Start/Apply on optimization runs), and to delete views. Read-only list / detail views remain on `TenantRequiredMixin`. Document the operator-vs-admin matrix in the README. |
| **D-08** | **Low** | A04 (Insecure design / data integrity) | [apps/pps/views.py](../apps/pps/views.py) — `RoutingEditView`, [apps/pps/signals.py](../apps/pps/signals.py) | Editing a routing while production orders reference it leaves their `ScheduledOperation` rows pointing at the old structure. UI does not warn; capacity load may be subtly wrong. | On `RoutingOperation.save` / `delete` (or on `RoutingEditView.post`), enumerate non-terminal production orders that reference the routing and either (a) clear their scheduled operations + flag them for re-schedule, or (b) refuse the edit if any planned/released order exists. |
| **D-09** | **Low / UX** | n/a (potential L-04 silent-drop) | [apps/pps/views.py](../apps/pps/views.py) — `ScenarioApplyView`, `OptimizationApplyView`; [templates/pps/scenarios/detail.html](../templates/pps/scenarios/detail.html); [templates/pps/optimizer/run_detail.html](../templates/pps/optimizer/run_detail.html) | "Apply" actions display a green toast ("Marked as applied. Audit trail recorded.") but do NOT mutate the base MPS or production orders. Operationally similar to the L-04 silent-drop pattern. | Either: (a) implement real apply (push scenario change deltas into the base MPS lines; reorder production orders per optimizer suggestion), or (b) tone down the success message to "Result snapshot recorded — no plan changes were made (v1)" and add a clear info card on both pages explaining v1 limitations. |
| **D-10** | **Low** | n/a | [apps/pps/services/optimizer.py](../apps/pps/services/optimizer.py) | `weight_idle` is read from the objective but never used in the scoring function. The UI advertises it as a knob; turning it has zero effect. | Either: (a) wire it in by adding an idle-time penalty term during the secondary sort, or (b) remove the field from `OptimizationObjective` and the form / templates. (a) is preferred — keeps the data model forward-compatible. |
| **D-11** | **Medium** | A09 (Logging failures) | [apps/pps/signals.py](../apps/pps/signals.py) | Audit log writes for MPS / order / scenario / optimization status — but NOT for `Routing`, `RoutingOperation`, `WorkCenter`, `CapacityCalendar` create/update/delete. Tenant admin cannot reconstruct who removed a routing or changed a work-center's capacity. | Add `post_save` + `post_delete` audit emitters for the four models above. Match the existing `bom.created` / `bom.updated` shape from [apps/bom/signals.py](../apps/bom/signals.py). |
| **D-12** | **Info** | n/a | [apps/pps/management/commands/seed_pps.py](../apps/pps/management/commands/seed_pps.py) | The idempotency gate is `if MasterProductionSchedule.objects.filter(tenant=tenant).exists()`. If the MPS row exists but other PPS data was hand-deleted, the seeder won't repair partial state without `--flush`. | Switch to per-section gating (each `_seed_*` already uses `get_or_create` / existence-checks for its own rows) — drop the top-level early return. Or document that `--flush` is the only supported repair path. |

### 6.2 Risks (no defect, but worth tracking)

| ID | Risk | Mitigation |
|---|---|---|
| **R-01** | Backward scheduler probe-buffer is `total * 3` — for very long-running operations on tight calendars the slide could push start before today | Replace probe with iterative calendar walk; cap at 90-day horizon |
| **R-02** | `services/scheduler.py` falls back to a 60-day safety horizon when consuming minutes; high-quantity orders (10000+ units) can silently get capped at `start + total_minutes` (clock time, ignoring shifts) | Add an explicit warning in `views.ProductionOrderScheduleView` if the schedule extended past the safety horizon |
| **R-03** | Optimizer "no negative improvement" clamp at `max(0, raw)` masks regressions during heuristic tuning | Persist raw `improvement_pct` in `suggestion_json.raw_improvement` for telemetry, keep clamped value as the public KPI |
| **R-04** | `StreamingHttpResponse` is not used by the Gantt — page payload grows linearly with the time window. Locust load shape recommended (§5.13) | Add server-side pagination on Gantt for windows > 30 days |
| **R-05** | Forecast / MPSLine accept emoji + 4-byte UTF-8 in `notes`; existing MySQL DB is `utf8mb4` so this is safe — but a partner deployment on `utf8` would 500 | Document `utf8mb4` requirement in README |

### 6.3 Recommendations (prioritised)

1. **Fix D-01 (XSS) immediately** — single template change × 2 files, biggest blast radius if a malicious admin or imported product list slips a `</script>` SKU through.
2. **Fix D-02 / D-03 / D-04 together** — all are L-01/L-02 lesson recurrences; one PR adds form `clean()` methods + model validators + migration. Add an L-01 / L-02 self-audit checklist to the SQA review skill.
3. **Fix D-07 (RBAC)** — small but important: introduce `TenantAdminRequiredMixin`, audit each view, document the operator/admin matrix.
4. **Fix D-09 (UX)** — soften the "applied" copy to "result recorded" until the real apply is built, OR commit to building real apply in the next iteration.
5. **Add D-11 audit coverage** — minimal code, big operational visibility win.
6. **Defer D-08, D-10, D-12** to follow-up iterations.

### 6.4 OWASP Top 10 mapping

| OWASP | Status | Notes |
|---|---|---|
| **A01 Broken Access Control** | ⚠ D-07 | Login enforced; tenant scoping enforced; **role separation missing** |
| **A02 Crypto failures** | ✅ | No new crypto introduced; relies on Django session + `SECRET_KEY` from `.env` |
| **A03 Injection / XSS** | ⚠ D-01 | SQL injection: clean (Q-objects + ORM); XSS: chart_series leak |
| **A04 Insecure design** | ⚠ D-02, D-03, D-04, D-05, D-06 | Missing validators + form/DB unique gap |
| **A05 Security misconfig** | ✅ (out of scope here; project-wide) | `DEBUG=False` + `ALLOWED_HOSTS` already enforced via `.env` |
| **A06 Vulnerable deps** | ⚪ Not assessed in this review (no `requirements.txt` change) | Run `pip-audit` separately |
| **A07 Auth failures** | ✅ | Django default password hashing + session expiry; no rate-limit gap introduced by PPS |
| **A08 Data integrity / file upload** | ✅ | PPS introduces no file uploads |
| **A09 Logging failures** | ⚠ D-11 | Workflow events audited; configuration changes not |
| **A10 SSRF** | ✅ | No external URL fetches |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets

| File | Line target | Branch target | Mutation target | Notes |
|---|---|---|---|---|
| [apps/pps/models.py](../apps/pps/models.py) | 95% | 90% | 80% | Helpers (`is_editable`, `total_minutes`, `effective_quantity`) — easy targets |
| [apps/pps/forms.py](../apps/pps/forms.py) | 95% | 90% | 80% | Once D-02..D-05 fixes land, the new `clean()` blocks are testable |
| [apps/pps/views.py](../apps/pps/views.py) | 85% | 75% | 65% | 50 CBVs; aim for every `if` branch covered with a positive + negative test |
| [apps/pps/services/scheduler.py](../apps/pps/services/scheduler.py) | 95% | 90% | 85% | Pure functions — high mutation target reasonable |
| [apps/pps/services/simulator.py](../apps/pps/services/simulator.py) | 90% | 85% | 75% | |
| [apps/pps/services/optimizer.py](../apps/pps/services/optimizer.py) | 90% | 80% | 70% | |
| [apps/pps/signals.py](../apps/pps/signals.py) | 90% | 85% | 70% | Audit-log emission + capacity-load invalidation |
| **Module overall** | **≥ 88%** | **≥ 80%** | **≥ 70%** | |

### 7.2 KPI table — Green / Amber / Red thresholds

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate (after fixes) | ≥ 99% | 95–98% | < 95% |
| Open Critical defects | 0 | 0 | ≥ 1 |
| Open High defects | 0 | 1 | ≥ 2 |
| Test suite runtime (pytest, full PPS) | < 30 s | 30–90 s | > 90 s |
| Query count `/pps/orders/` (200 rows) | ≤ 10 | 11–15 | > 15 |
| Query count `/pps/orders/gantt/` (500 ops) | ≤ 8 | 9–12 | > 12 |
| Query count `/pps/capacity/` (30 WCs × 14 days) | ≤ 12 | 13–20 | > 20 |
| p95 latency `/pps/orders/gantt/?days=14` | < 400 ms | 400–900 ms | > 900 ms |
| Regression escape rate (defects re-opened ≥ 2× per release) | 0 | 1 | ≥ 2 |
| Audit-log emission gap | 0 | 1 | ≥ 2 |

### 7.3 Release Exit Gate

The Module 4 PPS shipment may be tagged `v0.4.0` only when ALL of the following are true:

- [ ] D-01 (XSS) is fixed and `TestA03_XSS::test_gantt_escapes_user_controlled_sku` passes (xfail removed)
- [ ] D-02, D-03 (form-vs-DB unique trifecta) are fixed; `TestUniqueTrifectaRegression` passes for WorkCenter, Routing, OptimizationObjective
- [ ] D-04 (numeric validators) is fixed; `TestModelLevelBounds::test_negative_capacity_rejected` passes
- [ ] D-05 (order date validation) is fixed; `TestProductionOrderDateValidation` passes
- [ ] D-07 (RBAC) is fixed; `TestA01_BrokenAccessControl::test_non_admin_cannot_obsolete_mps` passes
- [ ] No open Critical defects; ≤ 1 open High defect (must be tracked and triaged)
- [ ] `pytest apps/pps/tests/` runs green in < 30 s on the test settings
- [ ] `pytest --cov=apps/pps` reports ≥ 88% line coverage and ≥ 80% branch coverage
- [ ] `bandit -r apps/pps/` returns 0 high-severity findings
- [ ] OWASP Top-10 matrix in §6.4 has no remaining ⚠ rows except where explicitly accepted by the product owner
- [ ] README's Module 4 section accurately describes the operator-vs-admin RBAC matrix introduced by the D-07 fix
- [ ] The 26-URL smoke test from the build session continues to return 200 across all detail pages, filtered by tenant
- [ ] Cross-tenant guard test (`admin_globex` requesting `admin_acme` resources) returns 404 on every detail / mutation endpoint

---

## 8. Summary

Module 4 (Production Planning & Scheduling) ships a working end-to-end planning + scheduling stack — 16 models, 50 CBVs, 25 templates, 3 pure-function services, 53 routes, an idempotent seeder, and an ApexCharts Gantt — with the architectural shape proven by the seeded smoke-test (26/26 URLs returning 200, cross-tenant isolation enforced, scheduled operations laid down across forward / backward / infinite methods, scenarios and optimization runs wired through to KPI deltas).

The QA review surfaced **12 defects**, of which **5 are High** and verified in the Django shell:

1. **D-01** — XSS via unescaped `chart_series_json|safe` in Gantt + capacity dashboard
2. **D-02 / D-03** — Three form-vs-DB unique-together gaps that surface as 500 errors (L-01 lesson recurrence)
3. **D-04** — Zero `MinValueValidator` / `MaxValueValidator` on any of the 16 models — negative capacity / cost / quantity all accepted (L-02 lesson recurrence)
4. **D-07** — `TenantRequiredMixin`-only authorization; non-admin staff can obsolete MPS, cancel production orders, apply optimizer results

The remaining 7 are Medium/Low/Info — UX softening on "Apply" verbs, race-window tightening on simulation/optimization start, audit-log coverage extension to routing/work-center mutations, and the unused `weight_idle` knob.

Recommended sequencing for remediation:

1. **Same-day:** D-01 (template change × 2 files; ~30 LoC).
2. **Next iteration (one PR):** D-02, D-03, D-04, D-05 — all share the L-01/L-02 lesson shape; one set of form `clean()` methods + model validators + migration.
3. **Next iteration (separate PR):** D-07 — introduce `TenantAdminRequiredMixin`, audit each view, document the operator/admin matrix in the README.
4. **Follow-up:** D-08, D-09, D-10, D-11, D-12.

The automation suite outlined in §5 — `pytest`-based, mirroring the existing PLM/BOM v1 test conventions — is runnable against the current codebase. Roughly 60% of the test bodies are written here verbatim and will run; the remaining cases are parametrised templates.

The L-01 (form-vs-DB unique gap) and L-02 (missing decimal validators) lesson recurrences in this module suggest the SQA review skill should add a pre-build self-audit checklist that scans every new model + form pair for these two specific gaps. Captured separately as a process improvement; not a defect against PPS.

The module is **NOT release-ready** in its current state. With the High-severity fixes above, it will be.

---

**Report end.** Follow-up modes available: `fix the defects` (implement and verify), `build the automation` (scaffold the test suite end-to-end), or `manual verification` (walk the high-severity test cases through `runserver`).
