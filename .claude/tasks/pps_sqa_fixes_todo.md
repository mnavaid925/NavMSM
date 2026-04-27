# PPS SQA Fixes + Automation Plan

> Source: [.claude/Test.md](../Test.md) — full SQA review of [apps/pps/](../../apps/pps/) (Module 4).
> Status: **IN PROGRESS** — 2026-04-28 session.
> Pattern reference: [.claude/tasks/bom_sqa_fixes_todo.md](bom_sqa_fixes_todo.md) (last cycle's BOM remediation + automation).

## Goal

1. Fix every High and Medium severity defect from the SQA report (D-01, D-02, D-03, D-04, D-05, D-07, D-11). Defer D-06 (race), D-08 (cascade clear), D-09 (UX softening), D-10 (weight_idle), D-12 (seed gate) to a follow-up cycle.
2. Scaffold and run the pytest suite for `apps/pps/` per §5 of the report. Target: green `pytest apps/pps/tests/` in <30s, plus the `xfail(strict=True)` regression guards converting to PASS once each defect is fixed.

## Defects in scope (verified in §6.1 of the SQA report)

| ID | Severity | Action |
|---|---|---|
| D-01 | High (XSS / A03) | Switch `chart_series_json\|safe` to `\|json_script` in [templates/pps/orders/gantt.html](../../templates/pps/orders/gantt.html) and [templates/pps/capacity/dashboard.html](../../templates/pps/capacity/dashboard.html); update view context shape; update inline JS to read from the rendered `<script type="application/json">`. |
| D-02 | High (L-01) | Add tenant-scoped uniqueness `clean()` to `WorkCenterForm` and `OptimizationObjectiveForm`; stash tenant in `__init__`; update views to pass `tenant=request.tenant` (already do for some). Wrap `WorkCenterEditView.save()` in `try/except IntegrityError` as belt-and-braces. |
| D-03 | High (L-01) | Add tenant-scoped uniqueness `clean()` to `RoutingForm` for `(tenant, product, version)`; ensure `_save_with_unique_number` retry only catches `routing_number` collisions. |
| D-04 | High (L-02) | Add `MinValueValidator` / `MaxValueValidator` on every numeric model field across [apps/pps/models.py](../../apps/pps/models.py). Fields: see Defect Register. Generate migration. Mirror in form widgets where possible. |
| D-05 | Medium | Add `clean()` to `ProductionOrderForm` validating `requested_end > requested_start` (when both provided). |
| D-07 | High (A01) | Apply `TenantAdminRequiredMixin` (already exists in [apps/accounts/views.py](../../apps/accounts/views.py)) to: all workflow transition views (Submit/Approve/Release/Obsolete on MPS; Release/Start/Complete/Cancel/Schedule on orders; Run/Apply/Discard on scenarios; Start/Apply/Discard on optimization runs); all delete views; all create/edit views. Read-only list / detail / dashboard views remain on `TenantRequiredMixin`. |
| D-11 | Medium (A09) | Extend [apps/pps/signals.py](../../apps/pps/signals.py) with `post_save` + `post_delete` audit emitters for `Routing`, `RoutingOperation`, `WorkCenter`, `CapacityCalendar`. Action names: `routing.created/updated/deleted`, etc. |

## Deferred to follow-up cycle

- D-06 (race window in ScenarioRunView / OptimizationStartView) — atomic transition refactor.
- D-08 (routing edit doesn't cascade-clear scheduled operations) — needs design decision (warn vs auto-clear vs refuse).
- D-09 (UX softening on "Apply" toasts) — small polish; no functional risk.
- D-10 (`weight_idle` unused) — needs either heuristic enhancement or schema removal.
- D-12 (seed gate too coarse) — operational nit; `--flush` works.

## Implementation order (each step verified before moving on)

1. **F-01: D-01 XSS** — switch to `json_script`; verify in shell that `</script>` in a SKU is HTML-escaped in the rendered Gantt.
2. **F-02: D-02 / D-03 L-01 trifecta** — form `clean()` methods; verify via shell that duplicate POSTs return 200 with form errors, not 500.
3. **F-03: D-04 L-02 numeric validators** — model + migration; verify negative POST is rejected.
4. **F-04: D-05 date validation** — form `clean()`; verify `requested_end < requested_start` returns 200 with form error.
5. **F-05: D-07 RBAC** — mixin sweep across views.py; verify non-admin staff is redirected to dashboard with a flash error.
6. **F-06: D-11 audit coverage** — signals; verify create/update/delete emit `TenantAuditLog` rows.
7. **A-01: tests scaffolding** — `apps/pps/tests/__init__.py`, `conftest.py`, then test files in dependency order.
8. **A-02: run pytest** — iterate until green. Convert `xfail(strict=True)` markers to plain pass once each defect is fixed.
9. **Docs** — append a Review block here; update [.claude/tasks/lessons.md](lessons.md) with anything novel; bump README's Module 4 section to mention the RBAC matrix.
10. **Commits** — one file per commit in PowerShell-safe form (per [CLAUDE.md GIT Commit Rule](../CLAUDE.md)).

## Verification protocol

For each fix:

1. Reproduce the defect once in the Django shell against seeded `admin_acme` data.
2. Apply the fix.
3. Reproduce the SAME shell command — confirm the new behaviour matches the SQA report's "Expected result".
4. Then write the regression test with `xfail` removed (or invert it).

## Out of scope

- Real ML optimizer (still v1 stub).
- WebSocket Gantt updates.
- Real "apply" — Scenario / Optimizer apply still records intent only (D-09 deferred).
- E2E / Playwright tests — pytest only at v1.
- Locust load tests — sample file shipped, not run.

---

## Review

**Outcome:** all 7 in-scope defects fixed and verified by automated tests. Test suite green: **58 passed in 6.19s**. Module overall coverage **61%** (services + signals + forms + models all ≥ 84% each; views.py at 36% by design — the SQA report's automation §5 prescribed a representative cut, not exhaustive view coverage).

| Defect | Severity | Fix landed in | Regression test |
|---|---|---|---|
| D-01 (XSS) | High | [templates/pps/orders/gantt.html](../../templates/pps/orders/gantt.html), [templates/pps/capacity/dashboard.html](../../templates/pps/capacity/dashboard.html), [apps/pps/views.py](../../apps/pps/views.py) — `OrderGanttView`, `CapacityDashboardView` now pass raw `chart_series` lists; templates use `{{ chart_series\|json_script:"id" }}`. | `test_security.TestA03_XSS_D01::test_gantt_escapes_user_controlled_sku` ✓ |
| D-02 (form/DB unique) | High | [apps/pps/forms.py](../../apps/pps/forms.py) — `_tenant_unique_check` helper + `clean()` on `WorkCenterForm` and `OptimizationObjectiveForm`; `WorkCenterEditView` and `OptimizationObjectiveEditView` wrap `form.save()` in `try/except IntegrityError` as belt-and-braces. | `test_forms.TestUniqueTrifectaD02::test_workcenter_form_catches_duplicate_code` ✓ + `test_security.TestA04_InsecureDesign::test_workcenter_edit_to_duplicate_code_does_not_500` ✓ |
| D-03 (Routing unique) | High | [apps/pps/forms.py](../../apps/pps/forms.py) — `RoutingForm.clean()` validates `(tenant, product, version)` triplet before save. | `test_forms.TestUniqueTrifectaD02::test_routing_form_catches_duplicate_product_version` ✓ |
| D-04 (numeric validators) | High | [apps/pps/models.py](../../apps/pps/models.py) — module-level `NON_NEGATIVE`, `POSITIVE`, `PERCENT` validator constants applied to 17 numeric fields across 5 models. Migration `0002_alter_demandforecast_confidence_pct_and_more.py` generated cleanly. | `test_models.TestModelLevelBoundsD04` (6 cases) ✓ + `test_forms.TestWorkCenterFormBoundsD04` (3 cases) ✓ |
| D-05 (order date) | Medium | [apps/pps/forms.py](../../apps/pps/forms.py) — `ProductionOrderForm.clean()` rejects `requested_end <= requested_start`. | `test_forms.TestProductionOrderDateValidationD05` (2 cases) ✓ |
| D-07 (RBAC) | High | [apps/pps/views.py](../../apps/pps/views.py) — 50 mutating CBVs swapped from `TenantRequiredMixin` to `TenantAdminRequiredMixin`. 10 read-only views (dashboard, list, detail, Gantt) remain on `TenantRequiredMixin` per the operator/admin matrix. | `test_security.TestA01_BrokenAccessControl` (5 cases) ✓ |
| D-11 (audit coverage) | Medium | [apps/pps/signals.py](../../apps/pps/signals.py) — `post_save` + `post_delete` audit emitters for `Routing`, `RoutingOperation`, `WorkCenter`, `CapacityCalendar` writing `<entity>.created/updated/deleted` rows to `TenantAuditLog`. | `test_audit_signals.TestConfigAuditCoverageD11` (6 cases) ✓ |

**Test suite shape:**

| File | Tests | Notes |
|---|---|---|
| [conftest.py](../../apps/pps/tests/conftest.py) | (fixtures) | `acme`, `globex`, `acme_admin`, `acme_staff`, `globex_admin`, `admin_client`, `staff_client`, `globex_client`, `product`, `work_center`, `routing`, `draft_mps`, `planned_order` |
| [test_models.py](../../apps/pps/tests/test_models.py) | 12 | Status helpers + D-04 model-level bounds |
| [test_forms.py](../../apps/pps/tests/test_forms.py) | 12 | Cross-field validation + D-02/D-03/D-04/D-05 regression |
| [test_views_orders.py](../../apps/pps/tests/test_views_orders.py) | 6 | Workflow + tenant isolation |
| [test_security.py](../../apps/pps/tests/test_security.py) | 10 | OWASP A01/A03/A04 + CSRF |
| [test_services.py](../../apps/pps/tests/test_services.py) | 9 | Pure-function scheduler/optimizer (incl. L-05 aware-tz regression) |
| [test_audit_signals.py](../../apps/pps/tests/test_audit_signals.py) | 6 | D-11 audit emission |
| [test_performance.py](../../apps/pps/tests/test_performance.py) | 3 | Query budget on list views |
| **Total** | **58** | |

**Things deferred to a follow-up cycle (per plan):**

- D-06: race window in `ScenarioRunView` / `OptimizationStartView` — needs atomic transition refactor to `_atomic_status_transition` with a temp `running` state.
- D-08: routing edit doesn't cascade-clear scheduled operations — needs design call.
- D-09: "Apply" UX softening — small copy tweak; can ride alongside the real apply when it's built.
- D-10: `weight_idle` unused — needs heuristic enhancement.
- D-12: seed gate too coarse — operational nit.

These were marked "deferred" in the SQA report's recommended sequencing and remain so.

**New lesson captured:** L-07 in [lessons.md](lessons.md) — "use `{{ data|json_script:"id" }}`, never `{{ json_dumps_string|safe }}` for inline JS data".

**Release Exit Gate progress (from [.claude/Test.md](../Test.md) §7.3):**

- [x] D-01 fixed; XSS regression test passes
- [x] D-02, D-03 fixed; unique-trifecta regression tests pass
- [x] D-04 fixed; numeric bounds tests pass
- [x] D-05 fixed; date validation tests pass
- [x] D-07 fixed; RBAC tests pass
- [x] No open Critical defects; 0 open High defects (all 5 verified-High items shipped)
- [x] `pytest apps/pps/tests/` runs green in **6.19s** (target was < 30s)
- [x] Coverage on the high-risk surface ≥ 84% (services/signals/forms/models)
- [ ] `bandit -r apps/pps/` — not run in this cycle (defer)
- [ ] OWASP Top-10 matrix — D-09 (UX softening) remains as the only ⚠ row, deferred by design
- [ ] README RBAC matrix — covered below
- [x] 26-URL smoke test still 200 across detail pages — verified during build session
- [x] Cross-tenant guard returns 404 (or 302 with no state change) — `test_views_orders.TestTenantIsolation` ✓
