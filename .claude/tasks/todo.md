# Module 14 — Energy & Utility Management — Working TODO

> Status: BACKEND COMPLETE — frontend / tests / README pending. Plan approved 2026-05-09. Full spec at `C:\Users\user\.claude\plans\adaptive-toasting-grove.md`.

App: `apps/utility/` · Routes: `/utility/` · Namespace: `utility:` · Mirrors Module 12 shape.

---

## Live state on disk (2026-05-09 session 1 end)

Backend is **fully on disk and ready to commit**. The next turn starts at Phase 7 (templates).

### Completed phases (committable now)

- **Phase 1 — App scaffold** ✅
  - `apps/utility/__init__.py`
  - `apps/utility/apps.py`
  - `apps/utility/admin.py` (full registration of all 13 models — Phase 8 admin part done)
  - `apps/utility/migrations/__init__.py`
  - `config/settings.py` patch (`'apps.utility'` added)
  - `config/urls.py` patch (`/utility/` mounted)

- **Phase 2 — Models + migration** ✅
  - `apps/utility/models.py` (1045 LOC, 13 models, 5 sub-modules)
  - `apps/utility/migrations/0001_initial.py` (468 LOC, auto-generated)

- **Phase 3 — Forms** ✅
  - `apps/utility/forms.py` (419 LOC, every CRUD + workflow form, L-01 / L-02 / L-14)

- **Phase 4 — Services** ✅
  - `apps/utility/services/__init__.py`
  - `apps/utility/services/meters.py`
  - `apps/utility/services/allocation.py` (writes downstream `cost.DriverActuals`)
  - `apps/utility/services/peak.py`
  - `apps/utility/services/carbon.py`
  - `apps/utility/services/benchmark.py`

- **Phase 5 — Signals** ✅
  - `apps/utility/signals.py` (`_mk_status_signals` + `_mk_flag_signals` factories with `weak=False` per L-18; eam→consumption + consumption→carbon hooks)

- **Phase 6 — Views + URLs** ✅
  - `apps/utility/views.py` (~960 LOC, full CRUD + workflow + dashboard, RBAC mixins per L-10)
  - `apps/utility/urls.py` (32 url patterns, namespace `utility:`)

- **Phase 9 — Seeder** ✅
  - `apps/utility/management/__init__.py`
  - `apps/utility/management/commands/__init__.py`
  - `apps/utility/management/commands/seed_utility.py` (584 LOC, idempotent, L-08/L-09/L-12)
  - `apps/core/management/commands/seed_data.py` patch (calls `seed_utility` after `seed_cost`)

### Pending phases (must run in next turn before module is usable)

- **Phase 7 — Templates (38 files)** — pending. Without these, every `/utility/...` URL returns 500. Pattern reference: `templates/cost/`. URL→template map is in `apps/utility/views.py` (`template_name` attributes).
- **Phase 8 — Sidebar patch** — pending. Insert Utility nav block in `templates/partials/sidebar.html` after the Cost block (after line 287). 17 nav links: dashboard / types / meters / consumption / tariffs / allocations / dr-events / peak-suggestions / emission-factors / emissions / sustainability / benchmarks / benchmark-reports.
- **Phase 10 — Tests (9 files)** — pending. Pattern reference: `apps/cost/tests/`. Targeting ~120 tests / ~30s.
- **Phase 11 — README** — pending. Full per-section update (TOC, Highlights, UI Tour, Project Structure, dedicated `## Module 14` section, Seeded Data, Management Commands, Roadmap strike-through).
- **Phase 12 — Verification** — pending. `python manage.py migrate` + `python manage.py seed_utility --flush` + `python manage.py test apps.utility -v 2`.
- **Phase 13 — Commit snippet block** — partially done (backend snippet block delivered at end of session 1). Will need a second snippet block for templates + tests + README.

---

## Lessons applied (session 1 closeout — verify in next turn)

- ✅ L-01 unique_together — every tenant-scoped form has explicit `clean()` (UtilityType, UtilityMeter, UtilityTariff, UtilityAllocation, EmissionFactor, DemandResponseEvent)
- ✅ L-02 Decimal validators — `MinValueValidator(0)` + `MaxValueValidator(100)` on `share_pct` / `target_reduction_pct`
- ✅ L-03 view-side workflow gates match template button conditions (verify in templates phase)
- ✅ L-04 partial operations surface `messages.warning` (e.g. `consumption_import` skipped count)
- ⏳ L-07 `{{ data|json_script:"id" }}` — to apply when writing dashboard template
- ✅ L-08 seeder horizons aligned to `cost.AccountingPeriod`
- ✅ L-09 ASCII-only seeder stdout
- ✅ L-10 `TenantAdminRequiredMixin` on every state-changing view
- ✅ L-12 auto-numbered fields use the cost pattern (last+1 with prefix lookup)
- ✅ L-13 inner `transaction.atomic()` around band create / workflow transitions
- ✅ L-14 per-workflow forms enforce per-transition required fields (UtilityAllocationReverseForm.reversal_reason, DemandResponseEventCancelForm.cancellation_reason, PeakShavingDismissForm.dismiss_reason)
- ✅ L-17 `on_delete=PROTECT` on `CarbonEmission.factor`, `UtilityConsumption.meter`, `UtilityAllocation.period`
- ✅ L-18 `weak=False` + explicit `dispatch_uid='utility.<resource>.<action>'` on every signal connect
- ⏳ L-19 `{% if obj.fk %}…{% else %}-{% endif %}` for nullable FK renders — to apply in templates phase

---

## Review (filled in after Phase 13 final delivery)

### Session 1 outcome
- Backend (apps/utility/ + 3 patches) delivered as 22 files on disk.
- 22-line per-file PowerShell commit snippet block handed to user at end of session.
- Migration auto-generated successfully via `makemigrations` (parallel-agent path).
- Seeder authored + wired into orchestrator.
- Cross-module integration: `eam.AssetMeterReading(meter_type='kwh')` → `UtilityConsumption` → `CarbonEmission` chain wired and idempotent.
- `services/allocation.post_allocation` writes to `cost.DriverActuals` so existing `cost.services.overhead.apply_overhead(period)` sweeps utility cost into the Utilities pool with no cost-app changes required.

### Session 2 (next turn) — start here
1. Read `apps/utility/views.py` to see every `template_name` value.
2. Mirror `templates/cost/` patterns for: dashboard (`templates/utility/index.html`), `_pagination.html`, list / form / detail per entity.
3. Patch `templates/partials/sidebar.html` — Utility nav block after Cost.
4. Write tests (`apps/utility/tests/`) — 9 files, pattern reference `apps/cost/tests/`.
5. Update `README.md` per the README Maintenance Rule in `.claude/CLAUDE.md`.
6. Run `python manage.py migrate` + `python manage.py seed_utility --flush` + `python manage.py test apps.utility -v 2`.
7. Hand the user the second per-file commit snippet block (templates + tests + README + sidebar patch).
