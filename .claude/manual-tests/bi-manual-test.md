# Business Intelligence & Analytics (BI) — Manual Test Plan

> Generated 2026-05-14 · Target module: `apps.bi` (Module 16 — KPI Dashboards, Ad-Hoc Report Builder, Predictive Analytics, Data Warehouse, Automated Report Distribution)
> Tester fills the **Pass/Fail** and **Notes** columns as they go. Use the [Bug Log](#5-bug-log) to record defects.

---

## 1. Scope & Objectives

This plan validates the BI module shipped under [apps/bi/](apps/bi/) — every page, button, filter, search input, action, and workflow surface defined in [apps/bi/urls.py](apps/bi/urls.py). It is a **complete module test** (not smoke-only) covering CRUD, search, pagination, filters, status workflows, file upload validation, multi-tenant isolation, frontend UI/UX, and negative/edge cases.

**In scope (5 sub-modules, 17 models, 60+ URL routes):**

| # | Sub-module | Models tested | Primary surfaces |
|---|---|---|---|
| 16.1 | Manufacturing KPI Dashboards | `KPIDefinition`, `KPIDashboard`, `KPIWidget`, `KPISnapshot` | KPI Definitions CRUD + Refresh · Dashboards CRUD + Refresh · Widgets create/edit/delete · Snapshots read-only |
| 16.2 | Ad-Hoc Report Builder | `ReportDataSource`, `ReportDefinition`, `ReportField`, `ReportFilter`, `ReportRun` | Data Sources CRUD · Reports CRUD + Run Now · Fields + Filters child CRUD · Runs read-only |
| 16.3 | Predictive Analytics | `PredictiveModel`, `PredictionRun`, `PredictionResult`, `TrendAnalysis` | Models CRUD + Run · Runs read + Cancel · Trends read-only |
| 16.4 | Tenant-Isolated Data Warehouse | `DataMart`, `DataMartColumn`, `DataMartSnapshot`, `DataMartRow` | Marts CRUD + Refresh · Columns child CRUD · Snapshots read-only |
| 16.5 | Automated Report Distribution | `ReportSchedule`, `ReportRecipient`, `ReportDelivery`, `ReportExport` | Schedules CRUD + Run Now / Pause / Resume / Disable · Recipients child CRUD · Deliveries read-only · Exports read-only + Download |

**Out of scope:** automated tests, performance/load, accessibility audit, email-delivery integration testing (no live SMTP).

**Acceptance bar:** every TC in §4 passes on Chrome desktop, no console errors, no 500s, multi-tenant isolation holds, file-upload allowlist + 25 MB cap enforced, ReportSchedule XOR (report vs dashboard) enforced, status-gated actions (pause/resume/cancel) behave correctly.

---

## 2. Pre-Test Setup

Run these once before the test session.

### 2.1 Start the server (PowerShell)

```powershell
python manage.py migrate
python manage.py seed_data
python manage.py seed_bi
python manage.py runserver
```

> If BI data has previously been seeded and you want a clean re-seed, use `python manage.py seed_bi --flush` ([apps/bi/management/commands/seed_bi.py:25](apps/bi/management/commands/seed_bi.py#L25)). The base `seed_data` command does NOT auto-include BI today — invoke `seed_bi` separately.

### 2.2 Open the app

- Root URL: `http://127.0.0.1:8000/`
- Login URL: `http://127.0.0.1:8000/accounts/login/`
- BI landing: `http://127.0.0.1:8000/bi/`

### 2.3 Login credentials (seeded by [apps/tenants/management/commands/seed_tenants.py:23-27](apps/tenants/management/commands/seed_tenants.py#L23-L27))

| Tenant | Username | Password | Role |
|---|---|---|---|
| Acme Manufacturing | `admin_acme` | `Welcome@123` | Tenant admin (**PRIMARY** for this run) |
| Globex Industries | `admin_globex` | `Welcome@123` | Tenant admin (used for cross-tenant IDOR tests) |
| Stark Production Co. | `admin_stark` | `Welcome@123` | Tenant admin (alternate) |
| Acme non-admin staff | `acme_supervisor_1` | `Welcome@123` | Used for `TenantAdminRequiredMixin` gate tests |
| Superuser | `admin` | (superuser pwd) | **DO NOT USE** for BI tests — `tenant=None`, BI screens render empty by design ([apps/bi/views.py:74-79](apps/bi/views.py#L74-L79)) |

### 2.4 Verify seed data

After login as `admin_acme`, navigate to `http://127.0.0.1:8000/bi/`. The dashboard cards at the top should show non-zero counts:

- **KPI Definitions**: ≥ 8 (oee, throughput, yield, scrap_rate, on_time_delivery, supplier_otd, gross_margin, energy_intensity per [apps/bi/management/commands/seed_bi.py:72-83](apps/bi/management/commands/seed_bi.py#L72-L83))
- **Dashboards**: ≥ 1
- **Reports**: ≥ 1
- **Active Schedules**: ≥ 0 (acceptable to be 0)
- **Runs (30d)**: ≥ 0
- **Active Marts**: ≥ 1

If any are zero, re-run `python manage.py seed_bi --flush`.

### 2.5 Browser/viewport matrix

| Profile | Browser | Viewport | Priority |
|---|---|---|---|
| Desktop primary | Chrome (latest) | 1920×1080 | P0 — run every TC here |
| Desktop secondary | Edge / Firefox | 1366×768 | P1 — spot-check |
| Tablet | Chrome DevTools "iPad" | 768×1024 | P1 — §4.12 UI section only |
| Mobile | Chrome DevTools "iPhone SE" | 375×667 | P1 — §4.12 UI section only |

### 2.6 Reset between runs

- Most TCs are non-destructive (read-only). Destructive TCs (Create, Edit, Delete, Refresh, Run, Pause) modify Acme's tenant data.
- To restore a clean state between full passes, run `python manage.py seed_bi --flush`.
- For a single test run, leave seed data intact and let cleanup be ad-hoc (delete what you create).

### 2.7 Test data files

For §4.13 file-upload negative cases, prepare these on the tester's desktop:
- `good.csv` — any small CSV (< 1 MB).
- `good.xlsx` — any small Excel file (< 1 MB).
- `bad.docx` — any small Word doc (extension not in allowlist).
- `huge.csv` — > 25 MB CSV (e.g. dump a large query, or generate one with `python -c "open('huge.csv','w').write('a,b\n' + 'x,1\n'*5000000)"`).

The allowlist is `{.csv, .xlsx, .pdf, .html}` and the cap is 25 MB ([apps/bi/forms.py:22-23](apps/bi/forms.py#L22-L23)).

---

## 3. Test Surface Inventory

### 3.1 URL routes (verified against [apps/bi/urls.py](apps/bi/urls.py))

| # | Path | View | Method | Gate |
|---|---|---|---|---|
| — | `/bi/` | IndexView | GET | TenantRequired |
| 16.1 | `/bi/kpi/definitions/` | KPIDefinitionListView | GET | TenantRequired |
| 16.1 | `/bi/kpi/definitions/new/` | KPIDefinitionCreateView | GET/POST | TenantAdmin |
| 16.1 | `/bi/kpi/definitions/<pk>/` | KPIDefinitionDetailView | GET | TenantRequired |
| 16.1 | `/bi/kpi/definitions/<pk>/edit/` | KPIDefinitionEditView | GET/POST | TenantAdmin |
| 16.1 | `/bi/kpi/definitions/<pk>/delete/` | KPIDefinitionDeleteView | POST | TenantAdmin |
| 16.1 | `/bi/kpi/definitions/<pk>/refresh/` | KPIDefinitionRefreshView | POST | TenantAdmin |
| 16.1 | `/bi/kpi/snapshots/` | KPISnapshotListView | GET | TenantRequired |
| 16.1 | `/bi/dashboards/`, `…/new/`, `…/<pk>/`, `…/<pk>/edit/`, `…/<pk>/delete/`, `…/<pk>/refresh/` | KPIDashboard* | GET/POST | TenantRequired (R) / TenantAdmin (W) |
| 16.1 | `/bi/dashboards/<dash_pk>/widgets/new/`, `/bi/widgets/<pk>/edit/`, `/bi/widgets/<pk>/delete/` | KPIWidget* | GET/POST | TenantAdmin |
| 16.2 | `/bi/reports/data-sources/`, `…/new/`, `…/<pk>/edit/`, `…/<pk>/delete/` | ReportDataSource* | GET/POST | TenantRequired (R) / TenantAdmin (W) |
| 16.2 | `/bi/reports/`, `…/new/`, `…/<pk>/`, `…/<pk>/edit/`, `…/<pk>/delete/`, `…/<pk>/run/` | ReportDefinition* | GET/POST | TenantRequired (R) / TenantAdmin (W) |
| 16.2 | `/bi/reports/<rpt_pk>/fields/new/`, `/bi/reports/fields/<pk>/delete/` | ReportField* | GET/POST | TenantAdmin |
| 16.2 | `/bi/reports/<rpt_pk>/filters/new/`, `/bi/reports/filters/<pk>/delete/` | ReportFilter* | GET/POST | TenantAdmin |
| 16.2 | `/bi/reports/runs/`, `…/<pk>/` | ReportRun* | GET | TenantRequired |
| 16.3 | `/bi/predictive/models/`, `…/new/`, `…/<pk>/`, `…/<pk>/edit/`, `…/<pk>/delete/`, `…/<pk>/run/` | PredictiveModel* | GET/POST | TenantRequired (R) / TenantAdmin (W) |
| 16.3 | `/bi/predictive/runs/`, `…/<pk>/`, `…/<pk>/cancel/` | PredictionRun* | GET/POST | TenantRequired (R) / TenantAdmin (cancel) |
| 16.3 | `/bi/predictive/trends/` | TrendAnalysisListView | GET | TenantRequired |
| 16.4 | `/bi/marts/`, `…/new/`, `…/<pk>/`, `…/<pk>/edit/`, `…/<pk>/delete/`, `…/<pk>/refresh/` | DataMart* | GET/POST | TenantRequired (R) / TenantAdmin (W) |
| 16.4 | `/bi/marts/<mart_pk>/columns/new/`, `/bi/marts/columns/<pk>/delete/` | DataMartColumn* | GET/POST | TenantAdmin |
| 16.5 | `/bi/schedules/`, `…/new/`, `…/<pk>/`, `…/<pk>/edit/`, `…/<pk>/delete/`, `…/<pk>/run/`, `…/<pk>/disable/`, `…/<pk>/pause/`, `…/<pk>/resume/` | ReportSchedule* | GET/POST | TenantRequired (R) / TenantAdmin (W/action) |
| 16.5 | `/bi/schedules/<sched_pk>/recipients/new/`, `/bi/schedules/recipients/<pk>/delete/` | ReportRecipient* | GET/POST | TenantAdmin |
| 16.5 | `/bi/deliveries/`, `…/<pk>/` | ReportDelivery* | GET | TenantRequired |
| 16.5 | `/bi/exports/`, `…/<pk>/download/` | ReportExport* | GET | TenantRequired |

### 3.2 Search / filter / pagination matrix

| List view | Pagination | `?q=` searches | Other GET filters |
|---|---|---|---|
| KPIDefinitionList | 25/page | code, name | `active=active\|inactive` |
| KPISnapshotList | 25/page | — | `code`, `status`, `scope_type` |
| KPIDashboardList | 25/page | name, slug | `shared=shared\|private` |
| ReportDataSourceList | 25/page | code, name, model_label | `active=active\|inactive` |
| ReportDefinitionList | 25/page | report_number, name | `data_source=<pk>` |
| ReportRunList | 25/page | — | `report=<pk>`, `status` |
| PredictiveModelList | 25/page | code, name | `code`, `active=active\|inactive` |
| PredictionRunList | 25/page | — | `status` |
| TrendAnalysisList | 25/page | trend_number, name | `source_metric`, `direction` |
| DataMartList | 25/page | mart_number, code, name | `refresh_frequency`, `active=active\|inactive` |
| ReportScheduleList | 25/page | schedule_number, name | `status`, `frequency` |
| ReportDeliveryList | 25/page | — | `status` |
| ReportExportList | 25/page | — | `format`, `status` |

Pagination implementation: `PAGE_SIZE=25` in [apps/bi/views.py:35](apps/bi/views.py#L35); helper `_paginate()` clamps invalid `?page=` to first page and out-of-range to last page ([apps/bi/views.py:38-46](apps/bi/views.py#L38-L46)).

### 3.3 Form-layer validation rules (verified against [apps/bi/forms.py](apps/bi/forms.py))

| Form | Rule | Why this matters for QA |
|---|---|---|
| KPIDefinitionForm | `clean_code()` rejects duplicate (tenant, code) | Test creating two definitions with code=`oee` → form error, not 500 |
| KPIDashboardForm | `clean()` auto-slugifies name if slug empty + dedup | Test omitting slug → form auto-fills it |
| ReportDataSourceForm | `clean_code()` enforces (a) code in `REGISTERED_SOURCES` whitelist; (b) tenant dedup | Test unknown code → form error |
| ReportDefinitionForm | `clean_name()` tenant-scoped dedup | Test duplicate report name within Acme → form error |
| ReportFilterForm | `clean()` requires `value_to` when `operator='between'` | Test between without value_to → form error |
| PredictiveModelForm | `clean()` dedups (tenant, code, name) triple | — |
| PredictionRunCancelForm | requires non-empty `cancellation_reason` | Test empty reason → form error |
| DataMartForm | `clean_source_definition()` requires JSON dict with `model_label` key | Test malformed JSON → form error |
| DataMartColumnForm | rejects (is_dimension=True AND is_measure=True) simultaneously | Test both checkboxes → form error |
| **ReportScheduleForm** | **`clean()` enforces XOR: exactly one of report/dashboard** | Test both / neither selected → form error ([apps/bi/forms.py:304-309](apps/bi/forms.py#L304-L309)) |
| ReportScheduleForm | `cron_expression` required when `frequency='custom'` | Test custom + blank cron → form error |
| ReportScheduleDisableForm | requires non-empty `disabled_reason` | Test empty reason → form error |
| ReportRecipientForm | dedups (tenant, schedule, email) triple | Test adding same email twice to a schedule → form error |
| **ReportExportForm** | **`clean_file()` allowlist `{.csv,.xlsx,.pdf,.html}` + 25 MB cap** | Test .docx → rejected; >25 MB → rejected ([apps/bi/forms.py:373-386](apps/bi/forms.py#L373-L386)) |

---

## 4. Test Cases

> Tester runs each case in order within its section. Fill **Pass/Fail** as `P` / `F` / `B` (blocked) / `S` (skipped). Log defects in §5 referencing the TC ID.

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous user redirected to login | Logged out | 1. Visit `http://127.0.0.1:8000/bi/` directly. | — | Browser redirected to `/accounts/login/?next=/bi/`. No BI content rendered. | | |
| TC-AUTH-02 | Anonymous user blocked from KPI definitions list | Logged out | 1. Visit `/bi/kpi/definitions/`. | — | Redirected to `/accounts/login/?next=/bi/kpi/definitions/`. | | |
| TC-AUTH-03 | Anonymous POST to delete is blocked | Logged out | 1. In a fresh DevTools console, run `fetch('/bi/kpi/definitions/1/delete/', {method:'POST', headers:{'X-CSRFToken':'x'}})`. | — | 302 redirect to login or 403; record not deleted. | | |
| TC-AUTH-04 | Superuser logged in sees empty BI dashboard (by design) | Logged in as `admin` | 1. Visit `/bi/`. | — | Page renders without error; all stat cards show `0`; no snapshots/runs listed; no 500. (Per [apps/bi/views.py:74-79](apps/bi/views.py#L74-L79).) | | |
| TC-AUTH-05 | Non-admin staff cannot create a KPI definition | Logged in as `acme_supervisor_1` | 1. Visit `/bi/kpi/definitions/new/`. | — | Either 403 / redirect to login (per `TenantAdminRequiredMixin` in [apps/bi/views.py:23](apps/bi/views.py#L23)). | | |
| TC-AUTH-06 | Non-admin staff CAN read KPI definitions list | Logged in as `acme_supervisor_1` | 1. Visit `/bi/kpi/definitions/`. | — | Page loads (read surface uses `TenantRequiredMixin`); rows visible. | | |
| TC-AUTH-07 | Non-admin staff cannot run a report | Logged in as `acme_supervisor_1` | 1. Open any report detail page. 2. Submit `POST /bi/reports/<pk>/run/`. | — | Blocked by `TenantAdminRequiredMixin`; no new ReportRun row created. | | |
| TC-AUTH-08 | Non-admin staff cannot pause a schedule | Logged in as `acme_supervisor_1` | 1. POST `/bi/schedules/<pk>/pause/`. | — | Blocked; status unchanged. | | |

### 4.2 Multi-Tenancy Isolation

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Acme admin only sees Acme KPI definitions | Logged in as `admin_acme` | 1. Visit `/bi/kpi/definitions/`. 2. Note the row count and codes. 3. Log out. 4. Log in as `admin_globex`. 5. Visit same URL. | — | Globex's list is independent of Acme's. No Acme rows appear under Globex. (Auto-filtered by `Model.objects.filter(tenant=request.tenant)` in `_TenantListBase` at [apps/bi/views.py:147](apps/bi/views.py#L147).) | | |
| TC-TENANT-02 | Globex admin cannot open Acme KPI definition detail (IDOR) | Logged in as `admin_acme`; in the BI tab note the integer pk of any KPI from `/bi/kpi/definitions/`. Log out, log in as `admin_globex`. | 1. Manually visit `/bi/kpi/definitions/<acme-pk>/` in the URL bar. | Use a pk that exists for Acme but not Globex. | 404 Not Found. (`get_object_or_404(..., tenant=request.tenant)` pattern.) | | |
| TC-TENANT-03 | Cross-tenant IDOR on report detail | As above setup but for a ReportDefinition | 1. Visit `/bi/reports/<acme-pk>/` while logged in as `admin_globex`. | — | 404. No Acme report leaked. | | |
| TC-TENANT-04 | Cross-tenant IDOR on schedule detail | Setup as above | 1. Visit `/bi/schedules/<acme-pk>/` while logged in as `admin_globex`. | — | 404. | | |
| TC-TENANT-05 | Cross-tenant IDOR on data mart | Setup as above | 1. Visit `/bi/marts/<acme-pk>/` while logged in as `admin_globex`. | — | 404. | | |
| TC-TENANT-06 | Cross-tenant POST to delete fails | Logged in as `admin_globex`; have Acme pk in hand | 1. Build a form (via DevTools or curl with CSRF cookie) that POSTs to `/bi/kpi/definitions/<acme-pk>/delete/`. | — | 404 or redirect; Acme record still present (verify by re-logging in as `admin_acme`). | | |
| TC-TENANT-07 | Cross-tenant POST to refresh KPI fails | Logged in as `admin_globex`; Acme pk in hand | 1. POST `/bi/kpi/definitions/<acme-pk>/refresh/`. | — | 404. Acme snapshot not created by Globex's session. | | |
| TC-TENANT-08 | Cross-tenant export download fails | Logged in as `admin_globex`; have Acme export pk | 1. Visit `/bi/exports/<acme-pk>/download/`. | — | 404. File not streamed. | | |

### 4.3 CREATE (representative entities)

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-01 | Create a KPI Definition with all fields | Logged in as `admin_acme`. Delete the existing `oee` row first (so we can re-add it cleanly), OR pick a non-seeded code such as `carbon_intensity`. | 1. Click **BI** in sidebar. 2. Click **KPI Definitions** sub-link (or visit `/bi/kpi/definitions/`). 3. Click **+ New KPI** button (top-right). 4. Select Code = `carbon_intensity`. 5. Type Name = `Carbon Intensity Test`. 6. Type Description = `Manual QA fixture`. 7. Type Unit = `kgCO2e/unit`. 8. Select Direction = `Lower is better`. 9. Type Target = `0.5`, Warning = `0.8`, Critical = `1.2`. 10. Tick **Active**. 11. Click **Save**. | (above) | Redirected to KPI Definitions list. Green toast: `KPI definition created.` (or similar). New row visible with code `carbon_intensity` and Active badge. | | |
| TC-CREATE-02 | Create a KPI Definition with only required fields | Logged in as `admin_acme` | 1. `/bi/kpi/definitions/new/`. 2. Code = `quality_trend`-equivalent unused choice (or pick any free code). 3. Name = `Min Test KPI`. 4. Leave description, unit, target, warning, critical blank. 5. Save. | — | Created successfully. Row shows `-` in Target column. | | |
| TC-CREATE-03 | Create a Dashboard (slug auto-filled) | Logged in as `admin_acme` | 1. `/bi/dashboards/new/`. 2. Name = `QA Test Dashboard`. 3. Leave Slug blank. 4. Default Period = `Last 30 days`. 5. Auto-refresh = `15`. 6. Save. | — | Created. List page shows the new row; the slug column reads `qa-test-dashboard` (auto-slugified per [apps/bi/forms.py:74](apps/bi/forms.py#L74)). | | |
| TC-CREATE-04 | Create a Widget on the new dashboard | Pre-req: TC-CREATE-03 created `QA Test Dashboard` | 1. Open the dashboard detail. 2. Click **Add Widget**. 3. Select an active KPI Definition. 4. Position = `0`. 5. Chart Type = `KPI Card`. 6. Tick **Compare to previous**. 7. Save. | — | Redirected back to dashboard detail. New widget visible in the widget list with the chosen KPI's code. | | |
| TC-CREATE-05 | Create a Report Data Source (whitelisted code) | Logged in as `admin_acme` | 1. `/bi/reports/data-sources/new/`. 2. Pick any **whitelisted** code from `services/registry.py` REGISTERED_SOURCES (try `production_reports` or a known one; tester should inspect the dropdown — it's a free text input so use a known good slug). 3. Name = `Production Reports QA`. 4. Model = `mes.ProductionReport`. 5. Tick **Active**. 6. Save. | — | Created. Row visible in Data Sources list. | | |
| TC-CREATE-06 | Create a Report Definition (auto-numbered) | Pre-req: at least one active Data Source. | 1. `/bi/reports/new/`. 2. Name = `QA Test Report`. 3. Data Source = (the one from TC-CREATE-05). 4. Sort direction = `Descending`. 5. Row limit = `100`. 6. Save. | — | Created. Number column on list page shows `RPT-NNNNN` (auto-numbered per [apps/bi/models.py:325-333](apps/bi/models.py#L325-L333)). | | |
| TC-CREATE-07 | Create a Report Field on the new report | Pre-req: TC-CREATE-06 created the report. | 1. Open the report detail. 2. Click **+ Add Field**. 3. Field name = a valid field on the source model (e.g. `quantity_produced`). 4. Display name = `Qty`. 5. Aggregation = `Sum`. 6. Position = `0`. 7. Save. | — | Field appears in the report's Fields section. | | |
| TC-CREATE-08 | Create a Report Filter (between requires value_to) | Pre-req: TC-CREATE-06 created the report. | 1. On report detail, click **+ Add Filter**. 2. Field = a date field, e.g. `created_at`. 3. Operator = `Between`. 4. Value = `2026-01-01`. 5. Leave **Value to** blank. 6. Save. | — | Form re-renders with red error under **Value to** reading "Value to is required when operator is Between" (per [apps/bi/forms.py:163-178](apps/bi/forms.py#L163-L178) cross-field clean). No row created. | | |
| TC-CREATE-09 | Create a Predictive Model | Logged in as `admin_acme` | 1. `/bi/predictive/models/new/`. 2. Code = `demand_forecast`. 3. Name = `Demand QA`. 4. Lookback days = `90`. 5. Forecast horizon = `30`. 6. Tick **Active**. 7. Save. | — | Created. List page shows new row. | | |
| TC-CREATE-10 | Create a Data Mart with valid source_definition JSON | Logged in as `admin_acme` | 1. `/bi/marts/new/`. 2. Code = `qa_mart`. 3. Name = `QA Test Mart`. 4. Source Definition (JSON) = `{"model_label": "mes.ProductionReport", "fields": ["quantity_produced"]}`. 5. Refresh frequency = `Daily`. 6. Tick **Active**. 7. Save. | — | Created. Number `DM-NNNNN` auto-generated. | | |
| TC-CREATE-11 | Create a Data Mart Column | Pre-req: TC-CREATE-10 | 1. Open the mart detail. 2. **+ Add Column**. 3. Code = `qty`. 4. Display name = `Quantity`. 5. Data type = `Decimal`. 6. Tick **Is measure** only (NOT both). 7. Save. | — | Column added. | | |
| TC-CREATE-12 | Create a Report Schedule (XOR — only report selected) | Pre-req: TC-CREATE-06 created `QA Test Report`. | 1. `/bi/schedules/new/`. 2. Name = `QA Daily Schedule`. 3. Report = `QA Test Report`. Leave Dashboard blank. 4. Frequency = `Daily`. 5. Leave cron blank. 6. Timezone = `UTC`. 7. Next run at = today 09:00. 8. Format = `CSV file`. 9. Save. | — | Created. Number `SCH-NNNNN`. Status `Active`. | | |
| TC-CREATE-13 | Create a Schedule with NEITHER report nor dashboard (negative) | Logged in as `admin_acme` | 1. `/bi/schedules/new/`. 2. Name = `Bad Schedule 1`. 3. Leave both Report and Dashboard blank. 4. Pick any Frequency. 5. Save. | — | Form re-renders with red form-level error: "Exactly one of report or dashboard must be selected." (per [apps/bi/forms.py:308-309](apps/bi/forms.py#L308-L309)). No row created. | | |
| TC-CREATE-14 | Create a Schedule with BOTH report and dashboard (negative) | Pre-req: TC-CREATE-03 + TC-CREATE-06 | 1. `/bi/schedules/new/`. 2. Name = `Bad Schedule 2`. 3. Pick Report = QA Test Report. 4. Pick Dashboard = QA Test Dashboard. 5. Save. | — | Same form-level error as TC-CREATE-13. | | |
| TC-CREATE-15 | Create a Schedule with frequency=Custom and blank cron (negative) | Logged in as `admin_acme` | 1. `/bi/schedules/new/`. 2. Name = `Bad Schedule 3`. 3. Report = some valid report. 4. Frequency = `Custom cron`. 5. Cron expression = (leave blank). 6. Save. | — | Red error under **Cron expression** reading "A cron expression is required when frequency is 'custom'." (per [apps/bi/forms.py:319-320](apps/bi/forms.py#L319-L320)). | | |
| TC-CREATE-16 | Create a Recipient on a schedule | Pre-req: TC-CREATE-12 | 1. Open the schedule detail. 2. **+ Add Recipient**. 3. Name = `QA Tester`. 4. Email = `qa@example.com`. 5. Tick Notify on failure + Active. 6. Save. | — | Recipient row appears in schedule detail. | | |
| TC-CREATE-17 | Create duplicate KPI code (tenant-scoped uniqueness) | Pre-req: `oee` already exists in Acme | 1. `/bi/kpi/definitions/new/`. 2. Code = `oee`. 3. Name = `Duplicate OEE`. 4. Save. | — | Form re-renders with red error under **Code** reading along lines of "A KPI with code 'oee' already exists for this tenant." (per `clean_code` in [apps/bi/forms.py:44-56](apps/bi/forms.py#L44-L56)). NO 500. | | |
| TC-CREATE-18 | Create duplicate Report name (tenant-scoped) | Pre-req: TC-CREATE-06 created `QA Test Report` | 1. `/bi/reports/new/`. 2. Name = `QA Test Report` (same). 3. Other fields valid. 4. Save. | — | Red error under **Name**. No 500. | | |
| TC-CREATE-19 | Create a Column with BOTH is_dimension and is_measure (negative) | Pre-req: TC-CREATE-10 | 1. Open mart detail. 2. **+ Add Column**. 3. Code = `bad`. 4. Tick BOTH `Is dimension` and `Is measure`. 5. Save. | — | Red form-level error (per [apps/bi/forms.py:253-279](apps/bi/forms.py#L253-L279)). | | |

### 4.4 READ — List Page

> Apply the **CRUD list checklist** below to each of the 13 list pages enumerated in §3.2. Don't write 13×many rows — instead spot-check 3 representative pages in detail, then use TC-LIST-COVERAGE to attest the rest.

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-01 | KPI Definitions list renders with seeded data | Logged in as `admin_acme`; seeded | 1. Visit `/bi/kpi/definitions/`. | — | Page title in tab = `KPI Definitions`. Header `H4 = KPI Definitions`. ≥ 8 rows. Columns visible: Code, Name, Unit, Direction, Target (right-aligned), Active (badge), Actions. Search + Active filter widgets visible. | | |
| TC-LIST-02 | Pagination renders correctly on KPI Snapshots (large set) | Logged in as `admin_acme`; seed produces multiple snapshots | 1. Visit `/bi/kpi/snapshots/`. 2. Check the pagination footer. | — | "Showing X of Y" or "Page 1 / N" text appears. Page nav prev/next links present at bottom (if rows > 25). | | |
| TC-LIST-03 | Dashboards list shows visibility badge correctly | Logged in as `admin_acme` | 1. Visit `/bi/dashboards/`. 2. Inspect the Visibility column. | — | Shared dashboards show `Shared` (info-subtle). Private dashboards (if any) show `Private` (secondary-subtle). | | |
| TC-LIST-04 | Reports list shows auto-generated number | Logged in as `admin_acme` | 1. Visit `/bi/reports/`. 2. Inspect Number column. | — | Each row's Number column starts with `RPT-` followed by 5 digits. | | |
| TC-LIST-05 | Report Runs list shows status badge in correct color | Logged in as `admin_acme`. Pre-req: TC-ACTION-01 (Run Now) executed earlier so at least one Completed run exists. | 1. Visit `/bi/reports/runs/`. | — | Rows with status `Completed` show **green** badge; `Failed` show **red**; `Queued`/`Running` show grey. | | |
| TC-LIST-06 | Predictive Trends list shows direction with correct color | Logged in as `admin_acme`. Pre-req: TC-ACTION-04 (Run a predictive model) executed. | 1. Visit `/bi/predictive/trends/`. | — | `Improving` rows show green badge; `Worsening` red; `Steady` grey. | | |
| TC-LIST-07 | Schedules list shows status badge correctly | Logged in as `admin_acme` | 1. Visit `/bi/schedules/`. | — | `Active` rows show green; `Paused` yellow; `Disabled` grey. | | |
| TC-LIST-COVERAGE | Spot-check the remaining list pages | Logged in as `admin_acme` | Visit each in turn and verify no 500, no console error, columns populated, pagination footer present, action column (where applicable) shows correct buttons: `/bi/reports/data-sources/`, `/bi/predictive/models/`, `/bi/predictive/runs/`, `/bi/marts/`, `/bi/deliveries/`, `/bi/exports/`. | — | Every page renders. | | |

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-DETAIL-01 | KPI Definition detail renders all model fields | Pre-req: a KPI exists (e.g. `oee`) | 1. From KPI list, click the **eye icon** on row `oee`. | URL ends `/bi/kpi/definitions/<pk>/`. Page shows: code, name, description, unit, direction, target, warning, critical, active. Sidebar shows Edit + Delete + Back to List. Refresh button visible. | | |
| TC-DETAIL-02 | Dashboard detail lists widgets | Pre-req: TC-CREATE-04 added a widget | 1. From Dashboard list click the dashboard name. | Page shows the dashboard metadata + a widget table including the widget added in TC-CREATE-04. Each widget has Edit and Delete buttons. | | |
| TC-DETAIL-03 | Report detail lists fields + filters | Pre-req: TC-CREATE-07 added a field | 1. From Reports list click the report number. | Page shows report metadata, Fields section with the added field, Filters section, **Run Now** button, **+ Add Field**, **+ Add Filter**. Each row has a delete button. | | |
| TC-DETAIL-04 | Predictive Model detail | Pre-req: TC-CREATE-09 | 1. From Predictive Models list click the code. | Page shows code, name, description, target_model_label, lookback_days, forecast_horizon_days, active. **Run Now** button visible. | | |
| TC-DETAIL-05 | Data Mart detail lists columns | Pre-req: TC-CREATE-11 added a column | 1. From Marts list click the number. | Page shows mart metadata, Columns section, **+ Add Column**, **Refresh** button. | | |
| TC-DETAIL-06 | Schedule detail shows recipients + action buttons | Pre-req: TC-CREATE-16 | 1. From Schedules list click the number. | Page shows schedule metadata, Recipients section with the recipient added, action buttons appropriate to status (`Pause` if Active; `Resume` if Paused; `Run Now`; `Disable`). | | |

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit KPI Definition (all fields pre-filled) | Pre-req: TC-CREATE-01 created `Carbon Intensity Test` | 1. From list click the **pencil icon** on the row. | Edit form opens with every field pre-populated to the current saved value. | | |
| TC-EDIT-02 | Edit KPI Definition saves correctly | Continuing TC-EDIT-01 | 1. Change Name to `Carbon Intensity Test (edited)`. 2. Save. | Redirected to list. Toast `KPI definition updated.`. Row shows the new name. | | |
| TC-EDIT-03 | Edit KPI Definition with blank required field | TC-EDIT-01 form open | 1. Clear the **Name** field. 2. Save. | Form re-renders with red error under Name reading "This field is required." Original DB row unchanged. | | |
| TC-EDIT-04 | Edit Dashboard slug to one already taken (negative) | Pre-req: two dashboards exist | 1. Edit the second dashboard. 2. Change Slug to match the first dashboard's slug. 3. Save. | Red error: "A dashboard with slug 'X' already exists for this tenant." No 500. (Per [apps/bi/forms.py:67-78](apps/bi/forms.py#L67-L78).) | | |
| TC-EDIT-05 | Edit Report row_limit to 0 | Pre-req: TC-CREATE-06 | 1. Edit `QA Test Report`. 2. Set row_limit = `0`. 3. Save. | Either accepted (PositiveIntegerField allows 0) or rejected with a graceful error — **no 500**. Whichever the form's behavior, record it in Notes. | | |
| TC-EDIT-06 | Edit Schedule from Daily to Custom without cron | Pre-req: TC-CREATE-12 | 1. Edit the schedule. 2. Change Frequency to `Custom cron`. 3. Leave cron blank. 4. Save. | Red error under Cron expression. | | |
| TC-EDIT-07 | Edit Schedule to switch from report → dashboard | Pre-req: TC-CREATE-12 (report-based) + TC-CREATE-03 (dashboard exists) | 1. Edit the schedule. 2. Clear Report. 3. Select Dashboard = QA Test Dashboard. 4. Save. | Saves successfully (XOR satisfied — exactly one set). | | |
| TC-EDIT-08 | Edit Report Definition Name to a duplicate of another | Pre-req: two reports exist | 1. Edit report B. 2. Change Name to report A's name. 3. Save. | Red error under Name. | | |

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete confirmation dialog appears | Pre-req: any KPI Definition exists | 1. On KPI list, click the **trash icon** on a row. | Browser-native confirm dialog appears reading "Delete KPI <code>?". | | |
| TC-DELETE-02 | Cancel on confirmation does nothing | TC-DELETE-01 dialog open | 1. Click **Cancel**. | No POST sent. Row still present after page refresh. | | |
| TC-DELETE-03 | Confirm delete removes the row | Pre-req: TC-CREATE-01 created `Carbon Intensity Test` | 1. Click trash on that row. 2. Click **OK** on confirm. | Redirected to list. Green toast `Deleted successfully.` Row gone. | | |
| TC-DELETE-04 | Delete a Widget | Pre-req: TC-CREATE-04 | 1. From dashboard detail, click trash on the widget row. 2. Confirm. | Widget removed. Dashboard detail re-renders. | | |
| TC-DELETE-05 | Delete a Report Field | Pre-req: TC-CREATE-07 | 1. From report detail, click trash on the field row. 2. Confirm. | Field removed. | | |
| TC-DELETE-06 | Delete a Recipient | Pre-req: TC-CREATE-16 | 1. From schedule detail, click trash on the recipient row. 2. Confirm. | Recipient removed. | | |
| TC-DELETE-07 | Delete a KPI Definition that is referenced by a Widget (PROTECT) | Pre-req: a KPI is referenced by a widget. | 1. Try to delete that KPI from KPI Definitions list. | Either: (a) the deletion is blocked with an error toast like "Cannot delete: this KPI is used by N widget(s)." (because `KPIWidget.kpi_definition` is `on_delete=PROTECT` at [apps/bi/models.py:178](apps/bi/models.py#L178)), OR the view catches `ProtectedError` and shows a clean message. **There must be NO 500.** | | |
| TC-DELETE-08 | Delete a DataMart that has snapshots (PROTECT chain) | Pre-req: a mart has at least one snapshot (refresh run). | 1. Try to delete that mart. | Same expectation as TC-DELETE-07 — clean error, no 500. | | |
| TC-DELETE-09 | Delete a Report Definition referenced by a Schedule | Pre-req: TC-CREATE-06 + TC-CREATE-12 (schedule points at QA Test Report) | 1. Try to delete `QA Test Report`. | Blocked with clean error message (PROTECT on `ReportSchedule.report` per [apps/bi/models.py:828](apps/bi/models.py#L828)). | | |
| TC-DELETE-10 | Delete URL only accepts POST | Pre-req: any record exists | 1. Manually visit `/bi/kpi/definitions/<pk>/delete/` (GET) in the browser. | NOT a 500; either 405 Method Not Allowed or a redirect / safe handler. Record unchanged. | | |

### 4.8 SEARCH

Apply to each list page with a `?q=` field per §3.2.

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-SEARCH-01 | Empty search returns all rows | Logged in as `admin_acme` | 1. `/bi/kpi/definitions/`. 2. Clear the q field. 3. Apply. | All rows returned (unfiltered). | | |
| TC-SEARCH-02 | Single character search | — | 1. q = `o`. Apply. | Rows containing `o` in code or name returned. | | |
| TC-SEARCH-03 | Search by KPI code | — | 1. q = `oee`. Apply. | At least one row returned, all matching `oee`. | | |
| TC-SEARCH-04 | Search by KPI name (case-insensitive) | — | 1. q = `EQUIPMENT`. Apply. | Returns the OEE row (`Overall Equipment Effectiveness`) — case-insensitive `icontains`. | | |
| TC-SEARCH-05 | Search trims leading/trailing whitespace | — | 1. q = `   oee   `. Apply. | Same result as TC-SEARCH-03 (per `.strip()` in [apps/bi/views.py:150](apps/bi/views.py#L150)). | | |
| TC-SEARCH-06 | No-match search shows empty state | — | 1. q = `zzzzzznotfound`. Apply. | Empty state row: "No KPI definitions yet. Add one." (acceptable to show the generic empty state). | | |
| TC-SEARCH-07 | Special characters do not 500 | — | 1. q = `'; DROP TABLE bi_kpidefinition;--`. Apply. | Page loads with zero or filtered results. No 500. | | |
| TC-SEARCH-08 | `%` in search does not break LIKE | — | 1. q = `100%`. Apply. | Page loads. No 500. | | |
| TC-SEARCH-09 | Search by Report number | — | 1. Visit `/bi/reports/`. 2. q = `RPT-`. Apply. | All seeded reports (RPT-NNNNN) matched. | | |
| TC-SEARCH-10 | Search by Schedule name | — | 1. `/bi/schedules/`. 2. q = a known schedule fragment. Apply. | Matches returned. | | |
| TC-SEARCH-11 | Search persists across pagination | Pre-req: q-filtered results span > 1 page (or use a tenant with many rows) | 1. q = `a`. Apply. 2. Click page 2 in pagination. | URL contains both `?q=a&page=2`. Filtered results still applied on page 2 (per `querystring_replace` in _pagination.html). | | |
| TC-SEARCH-12 | Search on DataMarts list works on 3 fields | — | 1. `/bi/marts/`. 2. q = `DM-`. Apply. | Returns by mart_number. 3. q = a code fragment. 4. q = a name fragment. | All three return matching results (search covers `mart_number, code, name`). | | |

### 4.9 PAGINATION

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-PAGE-01 | Default page size is 25 | Pre-req: list with > 25 rows (KPI Snapshots typically qualifies after seed) | 1. Visit `/bi/kpi/snapshots/`. 2. Count rows. | At most 25 data rows visible. | | |
| TC-PAGE-02 | Page nav prev/next | Pre-req: > 25 rows | 1. Click **Next**. | URL contains `?page=2`. Different rows shown. | | |
| TC-PAGE-03 | "Page X / Y" text accuracy | — | 1. On page 2, read the pagination footer. | Text reads "Page 2 / Y" where Y matches `ceil(total / 25)`. | | |
| TC-PAGE-04 | Last page may be partial | — | 1. Click **Last**. | Final page shows the remainder (1..25 rows). | | |
| TC-PAGE-05 | Out-of-range page redirects to last | — | 1. Manually edit URL to `?page=9999`. | Last page shown (per `EmptyPage` handling in [apps/bi/views.py:45-46](apps/bi/views.py#L45-L46)). No 500. | | |
| TC-PAGE-06 | Invalid page param falls back to page 1 | — | 1. Manually edit URL to `?page=abc`. | Page 1 shown (per `PageNotAnInteger` handling). | | |
| TC-PAGE-07 | Filters retained across pagination | Pre-req: `?status=active` returns > 25 rows on Schedules (use seed) | 1. `/bi/schedules/?status=active`. 2. Click Next. | URL becomes `?status=active&page=2`. Filter still applied. | | |
| TC-PAGE-08 | Search retained across pagination | Covered by TC-SEARCH-11 | — | — | | |

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-FILTER-01 | KPI Definitions Active filter | — | 1. `/bi/kpi/definitions/?active=active`. | Only `is_active=True` rows returned. | | |
| TC-FILTER-02 | KPI Definitions Inactive filter | — | 1. `?active=inactive`. | Only `is_active=False` rows. | | |
| TC-FILTER-03 | KPI Snapshots filter by code | — | 1. `/bi/kpi/snapshots/?code=oee`. | Only oee snapshots. | | |
| TC-FILTER-04 | KPI Snapshots filter by status | — | 1. `?status=warning`. | Only warning rows. Badge colors match. | | |
| TC-FILTER-05 | KPI Snapshots filter by scope_type | — | 1. `?scope_type=tenant`. | Only tenant-scope rows. | | |
| TC-FILTER-06 | Reports filter by data source | — | 1. `/bi/reports/?data_source=<pk>`. | Only reports for that source. | | |
| TC-FILTER-07 | Report Runs filter by status | — | 1. `/bi/reports/runs/?status=completed`. | Only completed runs. | | |
| TC-FILTER-08 | Predictive Models filter by code | — | 1. `/bi/predictive/models/?code=demand_forecast`. | Only that code. | | |
| TC-FILTER-09 | Prediction Runs filter by status | — | 1. `/bi/predictive/runs/?status=cancelled`. | Only cancelled. | | |
| TC-FILTER-10 | Trends filter by direction | — | 1. `/bi/predictive/trends/?direction=worsening`. | Only worsening rows. | | |
| TC-FILTER-11 | DataMarts filter by refresh_frequency | — | 1. `/bi/marts/?refresh_frequency=daily`. | Only daily marts. | | |
| TC-FILTER-12 | Schedules filter by status + frequency combined | — | 1. `/bi/schedules/?status=active&frequency=daily`. | AND-combined filter. | | |
| TC-FILTER-13 | Deliveries filter by status | — | 1. `/bi/deliveries/?status=sent`. | Only sent rows. | | |
| TC-FILTER-14 | Exports filter by format + status | — | 1. `/bi/exports/?format=csv&status=ready`. | Only ready CSV exports. | | |
| TC-FILTER-15 | Reset link clears all filters | — | 1. Apply any filter. 2. Click **Reset** button. | URL becomes the bare list URL. All rows shown. | | |
| TC-FILTER-16 | Selected filter is highlighted after Apply | — | 1. Apply `?active=inactive` on KPI Definitions. | The dropdown shows `Inactive` (currently selected), not the default `All`. (Per `selected` markup in [templates/bi/kpi/definitions_list.html:14-15](templates/bi/kpi/definitions_list.html#L14-L15).) | | |
| TC-FILTER-17 | Filter for zero results shows empty state | — | 1. Pick a code with no snapshots, e.g. `gross_margin` if not seeded. | Empty state row: "No snapshots yet." | | |
| TC-FILTER-18 | Filter combined with search | — | 1. `/bi/kpi/definitions/?q=oee&active=active`. | Rows matching BOTH conditions. URL preserved across pagination. | | |

### 4.11 Status Transitions / Custom Actions

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-ACTION-01 | Refresh a KPI Definition creates a Snapshot | Pre-req: `oee` exists | 1. Visit KPI definition detail for `oee`. 2. Click **Refresh** button. | POST to `/bi/kpi/definitions/<pk>/refresh/`. Redirected back. Green toast: `KPI oee refreshed: <value>` (per [apps/bi/views.py:264-266](apps/bi/views.py#L264-L266)). New row visible at `/bi/kpi/snapshots/`. | | |
| TC-ACTION-02 | Refresh a Dashboard runs every widget's KPI | Pre-req: TC-CREATE-04 | 1. Visit dashboard detail. 2. Click **Refresh**. | Toast: `Refreshed N widget(s)`. | | |
| TC-ACTION-03 | Run Now executes a Report | Pre-req: TC-CREATE-06 + TC-CREATE-07 (at least one field) | 1. Visit report detail. 2. Click **Run Now**. | Toast: `Report executed: N rows, X ms`. New row in `/bi/reports/runs/` with status `Completed`. | | |
| TC-ACTION-04 | Run a Predictive Model creates a PredictionRun | Pre-req: TC-CREATE-09 | 1. Visit predictive model detail. 2. Click **Run Now**. | Toast: `Prediction run: N result(s)`. New row visible at `/bi/predictive/runs/` with status `Completed` (or `Failed` if no upstream data — record which). | | |
| TC-ACTION-05 | Cancel a Prediction Run (requires reason) | Pre-req: a `queued` or `running` prediction run exists. If none, create one by stalling — or test the reachable case by entering the cancel form even on a completed run and observing the gate. | 1. From `/bi/predictive/runs/?status=running` (or queued), click the **stop** icon on the row. 2. On the cancel form, leave reason blank. 3. Submit. | Red error: "Reason is required to cancel this run." (per [apps/bi/forms.py:213-218](apps/bi/forms.py#L213-L218)). | | |
| TC-ACTION-06 | Cancel a Prediction Run with valid reason | Continuing TC-ACTION-05 | 1. Enter reason = `Manual QA cancel test`. 2. Submit. | Status → `Cancelled`. Toast: `Run cancelled`. Cancel button no longer shown on that row. | | |
| TC-ACTION-07 | Pause a Schedule (only if Active) | Pre-req: TC-CREATE-12 created an Active schedule | 1. From schedule detail, click **Pause**. | POST to `/bi/schedules/<pk>/pause/`. Status → `Paused`. Badge changes to yellow. Toast: `Schedule paused`. (Per `is_pausable()` at [apps/bi/models.py:876](apps/bi/models.py#L876).) | | |
| TC-ACTION-08 | Resume a Paused Schedule | Continuing TC-ACTION-07 | 1. Click **Resume**. | Status → `Active`. Toast: `Schedule resumed`. | | |
| TC-ACTION-09 | Pause already-paused schedule (negative) | Continuing TC-ACTION-07 then re-pause attempt | 1. While Paused, manually POST to `…/pause/`. | Either: no-op with a graceful error message, OR redirect with no status change. **No 500.** | | |
| TC-ACTION-10 | Disable a Schedule requires reason | Pre-req: TC-CREATE-12 | 1. From schedule detail, click **Disable**. 2. On the disable form, leave reason blank. Submit. | Red error: "Reason is required to disable a schedule." (per [apps/bi/forms.py:332-336](apps/bi/forms.py#L332-L336)). | | |
| TC-ACTION-11 | Disable a Schedule with valid reason | Continuing TC-ACTION-10 | 1. Reason = `Manual QA disable test`. Submit. | Status → `Disabled`. Toast: `Schedule disabled`. | | |
| TC-ACTION-12 | Resume a Disabled Schedule (negative) | TC-ACTION-11 done | 1. Try POST to `…/resume/`. | Blocked — `is_resumable()` is False for Disabled (per [apps/bi/models.py:878-879](apps/bi/models.py#L878-L879)). | | |
| TC-ACTION-13 | Run a Schedule Now | Pre-req: an Active schedule | 1. From schedule detail click **Run now**. | Toast: `Schedule executed. N delivery(s) created.` New rows in `/bi/deliveries/`. | | |
| TC-ACTION-14 | Refresh a DataMart | Pre-req: TC-CREATE-10 | 1. From mart detail click **Refresh**. | Toast: `Refreshed: N row(s) in X ms`. `last_refreshed_at` updated. New snapshot visible (if a detail snapshot list exists). | | |
| TC-ACTION-15 | Download an Export when file is present | Pre-req: an Export with `file` set (run TC-ACTION-13 first; if it produces files) | 1. From `/bi/exports/`, click the **download** icon on a `ready` row. | File downloads via `FileResponse` (auth-gated per [apps/bi/views.py:1283-1296](apps/bi/views.py#L1283-L1296)). | | |
| TC-ACTION-16 | Download Export not allowed when file missing | Pre-req: an Export with status `pending` and no file. | 1. Manually visit `/bi/exports/<pk>/download/`. | 404 or graceful error. | | |

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-UI-01 | Browser tab title is correct | — | 1. Visit `/bi/`. 2. Inspect the tab. | Tab title = `Business Intelligence & Analytics`. | | |
| TC-UI-02 | Tab title on KPI list | — | 1. `/bi/kpi/definitions/`. | Tab title = `KPI Definitions`. | | |
| TC-UI-03 | Sidebar highlights "BI" group | — | 1. Visit any BI page. | The BI sidebar entry is active/highlighted (matches `request.resolver_match.app_name == 'bi'`). | | |
| TC-UI-04 | BI landing page renders stat cards | — | 1. `/bi/`. | 6 stat cards (KPI Definitions / Dashboards / Reports / Active Schedules / Runs (30d) / Active Marts). None show `None` literal — `0` minimum. | | |
| TC-UI-05 | OEE trend chart renders | Pre-req: at least one tenant-scope OEE snapshot exists. | 1. `/bi/`. 2. Inspect the "OEE Trend" card. | An ApexCharts area chart renders inside `#oee-chart`. No console error. If no OEE snapshots, the chart area is empty but the page does not crash. | | |
| TC-UI-06 | Status badge colors match CHOICES | — | 1. `/bi/predictive/runs/`. | Completed=green, Failed=red, Cancelled=yellow, Queued/Running=grey (per `[templates/bi/predictive/run_list.html:29](templates/bi/predictive/run_list.html#L29)`). | | |
| TC-UI-07 | Action buttons aligned in Actions column | — | 1. `/bi/kpi/definitions/`. | View / Edit / Delete buttons aligned right, equal spacing. Hover tooltips: "View", "Edit", "Delete". | | |
| TC-UI-08 | Empty state on a freshly-flushed module | Pre-req: `python manage.py seed_bi --flush` then DO NOT re-seed; log in as `admin_acme`. | 1. `/bi/kpi/definitions/`. | Empty state row: "No KPI definitions yet. Add one." with link. (Per [templates/bi/kpi/definitions_list.html:41](templates/bi/kpi/definitions_list.html#L41).) After this test, re-run `seed_bi` to restore. | | |
| TC-UI-09 | Toast auto-dismisses | Pre-req: TC-CREATE-01 just done | 1. Watch the green toast after save. | Toast disappears within ~5 seconds (base.html toast settings). | | |
| TC-UI-10 | Confirm dialog shows entity identifier | TC-DELETE-01 setup | 1. Click trash on row with code `oee`. | Confirm dialog text reads `Delete KPI oee?` — not a generic `Delete?`. | | |
| TC-UI-11 | Form errors render under offending field | TC-CREATE-13 setup | 1. Trigger the XOR violation. | Red helper text appears under the relevant section / form-level alert, not just a flash. | | |
| TC-UI-12 | Required field markers on KPI form | — | 1. Visit `/bi/kpi/definitions/new/`. | `*` or `required` attribute on Code + Name fields. | | |
| TC-UI-13 | Long description wraps in detail page | Pre-req: a KPI with a long description (paste 500 chars during edit) | 1. View its detail page. | Text wraps within the card; no horizontal scrollbar appears on the page. | | |
| TC-UI-14 | Mobile viewport 375×667 — KPI list | — | 1. DevTools, set iPhone SE viewport. 2. Visit `/bi/kpi/definitions/`. | Table is horizontally scrollable inside `.table-responsive` (per base markup). No content cut off. Sidebar collapses. | | |
| TC-UI-15 | Tablet viewport 768×1024 — BI landing | — | 1. Set iPad viewport. 2. Visit `/bi/`. | Stat cards reflow into 2 or 3 per row. Charts resize. No overflow. | | |
| TC-UI-16 | Keyboard navigation through KPI form | — | 1. Visit `/bi/kpi/definitions/new/`. 2. Press Tab repeatedly. | Focus order: Code → Name → Description → Unit → Direction → Target → Warning → Critical → Active → Save. Focus visible (outline). | | |
| TC-UI-17 | No console errors when navigating each top-level page | DevTools Console open | 1. Visit each of the 13 list URLs in §3.2 in turn. | No red errors in the console at any step. ApexCharts on `/bi/` is acceptable provided no error. | | |
| TC-UI-18 | Breadcrumb / page header text | — | 1. Visit KPI detail. | H4 reads the entity title; muted small text reads a short description. | | |

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-NEG-01 | Submit KPI create with everything blank | — | 1. `/bi/kpi/definitions/new/`. 2. Click Save without filling anything. | Multiple red errors at once: Code, Name required. | | |
| TC-NEG-02 | Submit target value with letters | — | 1. KPI create. 2. Target = `abc`. 3. Save. | Graceful error under Target ("Enter a number."). | | |
| TC-NEG-03 | Submit very large decimal | — | 1. KPI create. 2. Target = `99999999999.99999`. | Either accepted (max_digits=14, decimal_places=4 → max ~9999999999.9999) or rejected with clear error. No 500. | | |
| TC-NEG-04 | Submit negative warning threshold for higher-is-better KPI | — | 1. KPI create. 2. Direction = `Higher is better`. 3. Warning = `-50`. | Saved (no semantic guard exists; signed bound allows it). Recommend filing a Cosmetic bug if the UX is misleading. | | |
| TC-NEG-05 | XSS attempt in description | — | 1. KPI create. 2. Description = `<script>alert(1)</script>`. 3. Save. | Saved row's description displays as escaped text on detail page; no alert fires. (Django auto-escapes templates.) | | |
| TC-NEG-06 | Unicode + emoji in name | — | 1. Create dashboard with Name = `测试 仪表板 🚀`. | Saved + displayed correctly in list. | | |
| TC-NEG-07 | Whitespace-only name | — | 1. KPI create. 2. Name = `   `. | Either rejected (preferred) or saved with leading spaces — record actual. | | |
| TC-NEG-08 | Decimal precision overflow (carbon target with 5 decimals) | — | 1. KPI create. 2. Target = `0.12345`. | Either rounded to 4 places or rejected with clean error. No 500. | | |
| TC-NEG-09 | Double-submit on Save (rapid double-click) | — | 1. KPI create, fill valid data. 2. Double-click **Save** quickly. | Only one row created; or graceful duplicate-key error. No two rows. | | |
| TC-NEG-10 | Browser back after create | — | 1. Create a KPI. 2. Press browser **Back**. 3. Press **Forward**. | Form not silently re-submitted. (Standard Django POST-Redirect-GET.) | | |
| TC-NEG-11 | Refresh on POST | — | 1. After save, press **F5** on the redirected page. | List page reloads. No "Confirm form resubmission" prompt. | | |
| TC-NEG-12 | Cron expression with 3 fields (invalid) | — | 1. Schedule create. 2. Frequency = Custom. 3. Cron = `* * *`. 4. Save. | Either accepted by the form (no syntactic validation today — record), or rejected with clean error. No 500. | | |
| TC-NEG-13 | Email field rejects malformed input | — | 1. Recipient create. 2. Email = `not-an-email`. | Standard Django EmailField error. | | |
| TC-NEG-14 | Data Mart source_definition with non-JSON | — | 1. Mart create. 2. Source Definition = `not valid json`. | Red form error (per [apps/bi/forms.py:244-250](apps/bi/forms.py#L244-L250)). | | |
| TC-NEG-15 | Data Mart source_definition without model_label | — | 1. Mart create. 2. Source Definition = `{"foo": "bar"}`. | Red error: "source_definition must include a model_label key." | | |
| TC-NEG-16 | Add column with neither dimension nor measure | — | 1. Column create. 2. Both checkboxes unticked. | Either accepted (allows pure descriptive) or rejected per form rule — record. | | |
| TC-NEG-17 | Upload `.docx` to ReportExport (if form is reachable in UI) | The ReportExport form is typically internal but if a manual upload UI exists | 1. Upload `bad.docx`. | Red error: `File type ".docx" is not allowed. Allowed: .csv, .html, .pdf, .xlsx.` (per [apps/bi/forms.py:378-381](apps/bi/forms.py#L378-L381)). | | |
| TC-NEG-18 | Upload > 25 MB file | Same condition as TC-NEG-17 | 1. Upload `huge.csv` (>25 MB). | Red error: `File too large (… bytes). Limit: 25 MB.` (per [apps/bi/forms.py:382-385](apps/bi/forms.py#L382-L385)). | | |
| TC-NEG-19 | Add duplicate recipient (same email twice on same schedule) | Pre-req: TC-CREATE-16 added `qa@example.com` | 1. Add another recipient with the same email on the same schedule. | Red error: `This recipient is already on the schedule.` (per [apps/bi/forms.py:349-361](apps/bi/forms.py#L349-L361)). | | |
| TC-NEG-20 | Direct GET to a POST-only action | — | 1. Visit `/bi/kpi/definitions/<pk>/refresh/` via GET. | 405 Method Not Allowed OR redirect — **not** 500. | | |
| TC-NEG-21 | DataMartColumn dimension + measure both true | TC-CREATE-19 already covers | — | — | | |

### 4.14 Cross-Module Integration

The BI module is read-mostly over the rest of the platform (see [apps/bi/models.py:15-18](apps/bi/models.py#L15-L18)). Most cross-module dependencies are server-side. The user-visible touchpoints are limited to a few read paths.

| ID | Title | Pre-condition | Steps | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| TC-INT-01 | KPI Refresh reads upstream production data | Pre-req: `seed_data` ran (MES production reports exist). | 1. Refresh the `oee` KPI definition. | A KPISnapshot row is inserted whose `value` is a non-zero number derived from MES data, not always `0`. | | |
| TC-INT-02 | Data Source `mes.ProductionReport` resolves correctly | Pre-req: at least one MES production report exists. | 1. Create a Report against a Data Source pointing at `mes.ProductionReport`. 2. Add a field that exists on that model (e.g. `quantity_produced`). 3. Run the report. | Run status `Completed`. `result_preview` shows up to 50 rows. Row count > 0. | | |
| TC-INT-03 | Report against a model with NO rows for tenant | Pre-req: a Data Source pointing to a model with zero rows for Acme. | 1. Run that report. | Run status `Completed`. Row count = 0. No 500. | | |
| TC-INT-04 | Sidebar BI nav link is present for tenant admin | Logged in as `admin_acme` | 1. Inspect the sidebar. | A `BI` group exists with links to Dashboards / Reports / Schedules (matches [templates/bi/index.html:10-12](templates/bi/index.html#L10-L12) at minimum on the landing page). | | |

---

## 5. Bug Log

Use IDs `BUG-01`, `BUG-02`, … as you find issues. Severity: **C** = Critical, **H** = High, **M** = Medium, **L** = Low, **X** = Cosmetic.

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Screenshot | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | | | | | | | | |
| BUG-02 | | | | | | | | |
| BUG-03 | | | | | | | | |
| BUG-04 | | | | | | | | |
| BUG-05 | | | | | | | | |

---

## 6. Sign-off & Release Recommendation

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---|---|---|---|---|
| 4.1 Authentication & Access | 8 | | | | |
| 4.2 Multi-Tenancy Isolation | 8 | | | | |
| 4.3 CREATE | 19 | | | | |
| 4.4 READ — List Page | 8 | | | | |
| 4.5 READ — Detail Page | 6 | | | | |
| 4.6 UPDATE | 8 | | | | |
| 4.7 DELETE | 10 | | | | |
| 4.8 SEARCH | 12 | | | | |
| 4.9 PAGINATION | 8 | | | | |
| 4.10 FILTERS | 18 | | | | |
| 4.11 Status Transitions / Custom Actions | 16 | | | | |
| 4.12 Frontend UI / UX | 18 | | | | |
| 4.13 Negative & Edge Cases | 21 | | | | |
| 4.14 Cross-Module Integration | 4 | | | | |
| **TOTAL** | **164** | | | | |

**Release Recommendation:** ☐ GO  ☐ GO-with-fixes  ☐ NO-GO

Rationale (one sentence): _________________________________________________________________________

Signed: ________________________________  Date: __________________

---

### Appendix A — Verification provenance

Every test case in this plan is verifiable against source. The high-trust references:

- URL routes: [apps/bi/urls.py](apps/bi/urls.py)
- Models / choices / unique constraints / PROTECT cascades: [apps/bi/models.py](apps/bi/models.py)
- View gates / search fields / filter params / action handlers: [apps/bi/views.py](apps/bi/views.py)
- Form validation rules / file upload allowlist / XOR / cross-field cleans: [apps/bi/forms.py](apps/bi/forms.py)
- List/detail/form templates: [templates/bi/](templates/bi/)
- Seed fixtures + tenant admin credentials: [apps/bi/management/commands/seed_bi.py](apps/bi/management/commands/seed_bi.py), [apps/tenants/management/commands/seed_tenants.py](apps/tenants/management/commands/seed_tenants.py)
