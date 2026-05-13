# Module 16 — Business Intelligence & Analytics — Implementation Plan

**Status:** in progress · **Started:** 2026-05-14
**Plan file:** [C:\Users\user\.claude\plans\piped-hugging-castle.md](C:/Users/user/.claude/plans/piped-hugging-castle.md)
**Module spec:** [MSM.md](../../MSM.md) Module 16

## Sub-modules

- 16.1 Manufacturing KPI Dashboards
- 16.2 Ad-Hoc Report Builder
- 16.3 Predictive Analytics
- 16.4 Tenant-Isolated Data Warehouse
- 16.5 Automated Report Distribution

## Checklist

### Skeleton + Settings
- [ ] apps/bi/__init__.py
- [ ] apps/bi/apps.py
- [ ] Register `apps.bi` in [config/settings.py](../../config/settings.py) INSTALLED_APPS

### Models + Migration
- [ ] apps/bi/models.py (~22 models)
- [ ] apps/bi/migrations/__init__.py
- [ ] apps/bi/migrations/0001_initial.py

### Admin
- [ ] apps/bi/admin.py

### Services (pure functions, no ORM at module scope)
- [ ] apps/bi/services/__init__.py
- [ ] apps/bi/services/registry.py — REGISTERED_SOURCES whitelist
- [ ] apps/bi/services/kpi.py — 9 KPI calculators + KPI_REGISTRY
- [ ] apps/bi/services/reports.py — safe ORM report executor
- [ ] apps/bi/services/predictions.py — heuristic forecasters
- [ ] apps/bi/services/datamart.py — refresh_mart + materialize_rows
- [ ] apps/bi/services/scheduler.py — due_schedules + run_schedule + render_export

### Signals
- [ ] apps/bi/signals.py — audit factory + cost.AccountingPeriod hook

### Forms (L-01 / L-02 / L-14 / L-17 / L-22)
- [ ] apps/bi/forms.py

### Views (~50 CBVs)
- [ ] apps/bi/views.py

### URLs
- [ ] apps/bi/urls.py
- [ ] Mount in [config/urls.py](../../config/urls.py): `path('bi/', include('apps.bi.urls'))`

### Templates (~35 files)
- [ ] templates/bi/index.html (dashboard)
- [ ] templates/bi/_pagination.html
- [ ] templates/bi/kpi/*.html
- [ ] templates/bi/dashboards/*.html
- [ ] templates/bi/widgets/*.html
- [ ] templates/bi/reports/*.html
- [ ] templates/bi/predictive/*.html
- [ ] templates/bi/datamarts/*.html
- [ ] templates/bi/distribution/*.html

### Sidebar
- [ ] Add "Business Intelligence" menu group in [templates/partials/sidebar.html](../../templates/partials/sidebar.html) after IoT

### Management Commands
- [ ] apps/bi/management/__init__.py
- [ ] apps/bi/management/commands/__init__.py
- [ ] apps/bi/management/commands/seed_bi.py — idempotent demo seeder
- [ ] apps/bi/management/commands/run_report_schedules.py — cron sweeper
- [ ] Register `seed_bi` in [apps/core/management/commands/seed_data.py](../../apps/core/management/commands/seed_data.py) orchestrator

### Tests (~13 files, target ≥85% coverage on services/forms/signals)
- [ ] apps/bi/tests/__init__.py
- [ ] apps/bi/tests/conftest.py
- [ ] apps/bi/tests/test_models.py
- [ ] apps/bi/tests/test_forms.py
- [ ] apps/bi/tests/test_views.py
- [ ] apps/bi/tests/test_services.py
- [ ] apps/bi/tests/test_kpi.py
- [ ] apps/bi/tests/test_reports.py
- [ ] apps/bi/tests/test_predictions.py
- [ ] apps/bi/tests/test_datamart.py
- [ ] apps/bi/tests/test_scheduler.py
- [ ] apps/bi/tests/test_signals.py
- [ ] apps/bi/tests/test_security.py
- [ ] apps/bi/tests/test_seeder.py

### README
- [ ] Update [README.md](../../README.md) per README Maintenance Rule

### Final
- [ ] Output one-file-per-commit PowerShell snippets

## Review

(To be added after implementation completes.)
