# EAM (Module 10 — Equipment & Asset Management) — Manual Test Plan

> **Author:** Senior Manual QA — Claude · **Target build:** post-Module-10 (2026-05-06) · **App under test:** [`apps/eam/`](apps/eam/)
>
> A click-through script. Every step says exactly what to click, what to type, and what to expect on screen. The tester fills the **Pass/Fail** + **Notes** columns as they go.

---

## 1. Scope & Objectives

| Item | Value |
|---|---|
| Mode | **Module test** — every list / create / detail / edit / delete page in `apps/eam/` plus all custom actions and cross-module hooks |
| Module | EAM (`/eam/`) — 5 sub-modules: Asset Registry, Preventive Maintenance, Predictive Maintenance, Maintenance Work Orders, Tool & Die |
| Primary entities | `Asset`, `AssetCategory`, `MaintenancePlan` + `PMSchedule`, `ConditionMonitoringPoint`, `FailurePrediction`, `MaintenanceWorkOrder`, `Tool` |
| Cross-module surfaces | `mes.AndonAlert(equipment, asset)` → auto-creates breakdown MWO; `mes.ProductionReport` on a tooled op → auto-emits `ToolUsageLog` + bumps `Tool.current_cycles`; `qms.MeasurementEquipment.asset` FK |
| Auth model | `accounts.User` with role `tenant_admin` (full CRUD), `operator` (read-only + non-privileged actions) |
| Browser primary | Chrome 120+ desktop @ 1920×1080 |
| Browser secondary | Edge desktop, Chrome mobile @ 375×667, Chrome tablet @ 768×1024 |
| Total test cases | 121 across 14 sections |
| Estimated effort | ~3.5 hours for a full pass by one tester |

---

## 2. Pre-Test Setup

Run **once** before starting. PowerShell-safe — uses `;` not `&&`.

### 2.1 Reset & seed the DB (only if you need a clean baseline)

```powershell
python manage.py migrate
python manage.py seed_data --flush
```

`seed_data` orchestrates `seed_plans + seed_tenants + seed_plm + seed_bom + seed_pps + seed_mrp + seed_mes + seed_qms + seed_inventory + seed_procurement + seed_eam` ([apps/core/management/commands/seed_data.py:11-33](apps/core/management/commands/seed_data.py#L11)).

### 2.2 Start the dev server

```powershell
python manage.py runserver
```

Wait for `Starting development server at http://127.0.0.1:8000/`.

### 2.3 Open the browser & log in as a tenant admin

Open Chrome (or whichever browser you're testing) and navigate to **http://127.0.0.1:8000/accounts/login/**.

| Field | Value |
|---|---|
| Username | `admin_acme` |
| Password | `Welcome@123` |

> ⚠️ **Do NOT** use the Django superuser `admin`. Per the *Multi-Tenancy Rules* in [.claude/CLAUDE.md](.claude/CLAUDE.md), the superuser has `tenant=None` and **every EAM page will be empty** for it. Always log in as a tenant admin (`admin_acme`, `admin_globex`, or `admin_stark`).

After login you should land on the dashboard at `/`. Click **Equipment & Assets** in the left sidebar — it should expand and show 13 menu items: EAM Dashboard, Assets, Asset Categories, Meter Readings, PM Plans, PM Schedule, Monitoring Points, Condition Readings, Failure Predictions, Maintenance WOs, Downtime Events, Tools & Dies, Tool Maintenance ([templates/partials/sidebar.html:203-226](templates/partials/sidebar.html#L203)).

### 2.4 Verify seed data exists

Click **Equipment & Assets → EAM Dashboard**. You should see:

- **KPI cards**: Active Assets ≥ 10, Critical Assets ≥ 2, Open MWOs ≥ 2, Open Predictions = 1
- **Recent Work Orders**: 3 rows (1 completed pump breakdown, 1 scheduled motor seal, 1 in-progress CNC PM)
- **Upcoming PM**: at least 4 rows
- **Open Failure Predictions**: 1 row (auto-spawned from a critical seeded reading — proves Lesson L-18 `weak=False` works)

If any of those numbers are zero, the seeder didn't run for this tenant — re-run `python manage.py seed_eam` and refresh.

### 2.5 Open a second browser profile for cross-tenant tests

Open a second Chrome profile (or an Incognito window) and log in as **`admin_globex` / `Welcome@123`**. You'll need this for §4.2 Multi-Tenancy Isolation.

### 2.6 Open a third browser profile for RBAC tests

Open a third profile / Incognito and log in as a **non-admin tenant user** — by default the seeded staff usernames follow the pattern `<tenant>_<role>_<n>`, e.g. `acme_production_manager_1` / `Welcome@123` ([apps/tenants/management/commands/seed_tenants.py](apps/tenants/management/commands/seed_tenants.py)). Confirm the user has `is_tenant_admin=False` by visiting `/accounts/profile/` — the role label should not say "Tenant Admin".

> If the staff fixture doesn't exist on your DB (e.g. you partially seeded), create one quickly:
> ```powershell
> python manage.py shell -c "from apps.accounts.models import User; from apps.core.models import Tenant; t=Tenant.objects.get(slug='acme-manufacturing'); u=User.objects.create_user(username='acme_op_qa', password='Welcome@123', tenant=t, is_tenant_admin=False, role='operator'); print(u.username)"
> ```

### 2.7 Ground rules

- **All toasts** appear top-right, auto-dismiss after ~5 seconds.
- **Form errors** render in red below the offending field.
- **Confirm dialogs** are native browser `confirm()` — click **OK** to proceed, **Cancel** to abort.
- **Status badges** colour code: success (green), info (blue), warning (yellow/amber), danger (red), secondary (grey).
- **Required field markers** (`*`) come from crispy-forms.

### 2.8 Tooling

- DevTools open the entire session (`F12`) — keep the **Console** tab visible to catch JS errors.
- **Network** tab in DevTools — verify no 500 / 404 responses on healthy paths.
- Take screenshots (`Win + Shift + S`) of any unexpected behaviour — attach to the Bug Log in §5.

---

## 3. Test Surface Inventory

### 3.1 URL routes (verified against [apps/eam/urls.py](apps/eam/urls.py))

| Group | List | Create | Detail | Edit | Delete | Custom actions |
|---|---|---|---|---|---|---|
| Dashboard | `/eam/` | — | — | — | — | — |
| Asset Categories | `/eam/categories/` | `/eam/categories/new/` | (n/a — list-only) | `/eam/categories/<pk>/edit/` | `/eam/categories/<pk>/delete/` | — |
| Assets | `/eam/assets/` | `/eam/assets/new/` | `/eam/assets/<pk>/` | `/eam/assets/<pk>/edit/` | `/eam/assets/<pk>/delete/` | retire, reactivate |
| Asset Spares (inline) | — | `/eam/assets/<pk>/spares/new/` | — | — | `/eam/spares/<pk>/delete/` | — |
| Meter Readings | `/eam/meter-readings/` | `/eam/assets/<pk>/readings/new/` (inline) | — | — | — | — |
| Documents (inline) | — | `/eam/assets/<pk>/documents/new/` | — | — | `/eam/documents/<pk>/delete/` | — |
| PM Plans | `/eam/pm-plans/` | `/eam/pm-plans/new/` | `/eam/pm-plans/<pk>/` | `/eam/pm-plans/<pk>/edit/` | `/eam/pm-plans/<pk>/delete/` | generate (POST) |
| PM Tasks (inline) | — | `/eam/pm-plans/<pk>/tasks/new/` | — | — | `/eam/pm-tasks/<pk>/delete/` | — |
| PM Schedules | `/eam/pm-schedules/` | `/eam/pm-schedules/new/` | `/eam/pm-schedules/<pk>/` | — | — | start, complete, skip, task_create |
| Monitoring Points | `/eam/monitoring-points/` | `/eam/monitoring-points/new/` | `/eam/monitoring-points/<pk>/` | `/eam/monitoring-points/<pk>/edit/` | `/eam/monitoring-points/<pk>/delete/` | reading_create |
| Condition Readings | `/eam/readings/` | `/eam/readings/new/` (top-level) | — | — | — | — |
| Failure Predictions | `/eam/predictions/` | (auto-spawned by signal) | `/eam/predictions/<pk>/` | — | — | investigate, resolve |
| Maintenance WOs | `/eam/mwo/` | `/eam/mwo/new/` | `/eam/mwo/<pk>/` | `/eam/mwo/<pk>/edit/` | `/eam/mwo/<pk>/delete/` | schedule, start, hold, resume, complete, cancel + labor/material logs |
| Downtime | `/eam/downtime/` | `/eam/downtime/new/` (inline) | — | — | `/eam/downtime/<pk>/delete/` | — |
| Tools | `/eam/tools/` | `/eam/tools/new/` | `/eam/tools/<pk>/` | `/eam/tools/<pk>/edit/` | `/eam/tools/<pk>/delete/` | retire, reactivate, usage_create, maintenance_create, cavity_create |
| Tool Maintenance | `/eam/tool-maintenance/` | (inline on tool detail) | — | — | — | — |

### 3.2 Filters (verified in [apps/eam/views.py](apps/eam/views.py))

| Page | Search (`q`) | Filter dropdowns |
|---|---|---|
| Asset list | tag, name, serial_number, model_number | status, criticality, category, active |
| Category list | name | active |
| PM Plan list | name, asset.tag | trigger, asset, active |
| PM Schedule list | schedule_number, plan.name, plan.asset.tag | status |
| Monitoring Point list | name, asset.tag | parameter, active |
| Condition Reading list | — | status, point |
| Failure Prediction list | — | status, asset |
| MWO list | mwo_number, title, asset.tag | status, wo_type, priority, asset |
| Downtime list | — | asset, downtime_type |
| Tool list | tool_id, name | tool_type, status, active |
| Tool Maintenance list | — | record_type, tool |
| Meter Reading list | — | asset, meter_type |

### 3.3 Status-gated UI (verified in template + view)

| Entity | Buttons that respect status |
|---|---|
| Asset | **Retire** hidden when `status='retired'`; **Reactivate** shown only when `status='retired'` |
| MWO | **Edit** only when `status ∈ (draft, scheduled, on_hold)`; **Delete** only when `status ∈ (draft, cancelled)`; **Schedule** only when `draft`; **Start** when `(draft, scheduled, on_hold)`; **Hold** when `in_progress`; **Resume** when `on_hold`; **Complete** when `in_progress`; **Cancel** when `(draft, scheduled, in_progress, on_hold)` |
| PM Schedule | **Start** when `(scheduled, overdue)`; **Complete** form when `(scheduled, in_progress, overdue)`; **Skip** when `(scheduled, overdue)` |
| Failure Prediction | **Investigate** when `status='open'`; **Resolve** when `status ∈ (open, investigating)` |
| Tool | **Retire** when `status != 'retired'`; **Reactivate** when `status='retired'` |
| PM Plan | **Generate Upcoming** only when `is_active=True` |

### 3.4 Auto-numbering (per L-12 retry-on-IntegrityError)

| Model | Format |
|---|---|
| `Asset.tag` | `ASSET-00001`, `ASSET-00002`, ... |
| `MaintenanceWorkOrder.mwo_number` | `MWO-00001`, ... |
| `PMSchedule.schedule_number` | `PMS-00001`, ... |
| `Tool.tool_id` | `TOOL-00001`, ... |

### 3.5 File upload constraints (per L-14)

| Form | Allowlist | Cap |
|---|---|---|
| `AssetDocumentForm` | `.pdf .png .jpg .jpeg .dwg .dxf` | 25 MB |
| `ToolMaintenanceRecordForm` | `.pdf .png .jpg .jpeg` | 25 MB |

---

## 4. Test Cases

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous redirect — dashboard | Logged out | 1. Navigate to `/eam/` | — | Browser redirects to `/accounts/login/?next=/eam/`. No EAM content visible. | | |
| TC-AUTH-02 | Anonymous redirect — every list page | Logged out | 1. In an Incognito window, attempt to GET each of the 12 list URLs in §3.1 one at a time | — | Each request 302-redirects to `/accounts/login/?next=...`. No 500s, no leaked data. | | |
| TC-AUTH-03 | Anonymous POST is rejected | Logged out | 1. Open DevTools → Console<br>2. Run `fetch('/eam/assets/new/', {method:'POST'})` | — | Response status 302 (redirect to login). DB unchanged. | | |
| TC-AUTH-04 | Login as superuser shows empty EAM | Logged out | 1. Log in as `admin` / superuser password<br>2. Navigate to `/eam/` | superuser | Dashboard loads but **all KPI counts are 0** and lists show "No assets yet" / "No work orders yet". This is BY DESIGN — superuser has `tenant=None`. | | |
| TC-AUTH-05 | Tenant admin sees full EAM | Logged out | 1. Log in as `admin_acme` / `Welcome@123`<br>2. Navigate to `/eam/` | seeded | Dashboard shows non-zero KPIs. Sidebar shows **Equipment & Assets** group expanded or collapsable. | | |

### 4.2 Multi-Tenancy Isolation

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Cross-tenant asset read → 404 | Logged in as `admin_acme` in Profile A; logged in as `admin_globex` in Profile B | 1. In Profile B, copy the URL of any Globex asset detail (e.g. `/eam/assets/45/`)<br>2. Paste that URL into Profile A's address bar | URL of a Globex `Asset` | Profile A receives **HTTP 404**. No asset content rendered. | | |
| TC-TENANT-02 | Cross-tenant asset edit POST → 404 | Same as above | 1. In Profile A's DevTools Network tab, copy a CSRF token from any form<br>2. Issue a POST to `/eam/assets/<globex-pk>/edit/` with valid form data | Globex pk | 404 response. The Globex asset's name is unchanged when verified in Profile B. | | |
| TC-TENANT-03 | Cross-tenant MWO delete → 404 | Logged in as `admin_acme` | 1. Find a Globex MWO pk from Profile B (e.g. `MWO-00002`, pk=12)<br>2. From Profile A, submit `POST /eam/mwo/12/delete/` with CSRF | Globex MWO pk | 404. The Globex MWO is still listed in Profile B. | | |
| TC-TENANT-04 | Cross-tenant tool retire → 404 | Logged in as `admin_acme` | 1. Find a Globex Tool pk from Profile B<br>2. From Profile A, POST `/eam/tools/<globex-pk>/retire/` | Globex Tool pk | 404. The Globex tool's status is unchanged. | | |
| TC-TENANT-05 | List queryset is tenant-scoped | Logged in as `admin_acme` | 1. Navigate to `/eam/assets/`<br>2. Note the tags of every visible asset<br>3. Switch to Profile B (`admin_globex`)<br>4. Navigate to `/eam/assets/`<br>5. Note the tags there | seeded | The two lists share the same auto-generated tag prefixes (`ASSET-00001`, etc.) but represent **different rows** — Profile A's list never shows Globex assets and vice versa. Counts in the bottom-right pagination block differ from the dashboard's count if you applied a filter. | | |
| TC-TENANT-06 | qms.MeasurementEquipment cross-link respects tenant | Logged in as `admin_acme` | 1. Navigate to `/qms/equipment/` and click any equipment row<br>2. Open the Asset FK dropdown (if exposed via edit form) | seeded | The Asset dropdown ONLY shows Acme assets. Globex assets are never listed. | | |

### 4.3 CREATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-01 | Create Asset Category — happy path | `admin_acme` logged in | 1. Sidebar → **Asset Categories** → **+ Add Category**<br>2. Fill **Name** = `Hydraulics`<br>3. Leave Parent blank<br>4. Tick **Is Active**<br>5. Click **Save** | Name=Hydraulics | Redirect to `/eam/categories/`. Green toast `Category "Hydraulics" created.`. New row visible in the list. | | |
| TC-CREATE-02 | Create Asset Category — duplicate name same parent | TC-CREATE-01 passed | 1. Click **+ Add Category**<br>2. Fill **Name** = `Hydraulics`, Parent = blank<br>3. Click **Save** | dup name | Form re-renders with red error under Name: `A category with this name already exists at the same level.`. **No 500.** No duplicate created. | | |
| TC-CREATE-03 | Create Asset — happy path with auto-tag | logged in | 1. Sidebar → **Assets** → **+ Add Asset**<br>2. Fill **Name** = `Manual QA Pump`, Category = `Pumps`, Criticality = `Medium`, Status = `Operational`<br>3. Leave **Tag** blank (auto)<br>4. Fill `Purchase cost` = `12000`, `Current value` = `9000`<br>5. Click **Save** | name=Manual QA Pump | Redirect to `/eam/assets/<pk>/`. Tag is auto-assigned `ASSET-NNNNN`. Detail page shows the entered profile. | | |
| TC-CREATE-04 | Create Asset — required fields missing | logged in | 1. Click **+ Add Asset**<br>2. Leave **Name** blank<br>3. Click **Save** | empty form | Form re-renders. Red error under Name: `This field is required.`. No 500. | | |
| TC-CREATE-05 | Create Asset — commission before install rejected | logged in | 1. Click **+ Add Asset**<br>2. Name = `Bad Dates`, Category = `Pumps`, Criticality = `Medium`<br>3. Installation date = `2026-01-15`, Commissioning date = `2026-01-10`<br>4. Click **Save** | install > commission | Red error under Commissioning Date: `Commissioning date cannot be before installation date.`. | | |
| TC-CREATE-06 | Create Asset — XSS attempt in name | logged in | 1. Click **+ Add Asset**<br>2. Name = `<script>alert('xss')</script>`<br>3. Criticality = `Low`<br>4. Click **Save** | XSS payload | Asset is created. Detail page renders the name with the literal `<script>...</script>` tags shown as text — **no popup, no execution**. | | |
| TC-CREATE-07 | Create PM Plan — calendar trigger | Acme has at least 1 active asset | 1. Sidebar → **PM Plans** → **+ Add Plan**<br>2. Name = `QA Lubrication`, Asset = (any), Trigger = `Calendar`, Frequency days = `30`<br>3. Click **Save** | calendar plan | Redirect to plan detail. Tasks table is empty. Generate Upcoming button is visible. | | |
| TC-CREATE-08 | Create PM Plan — calendar without frequency_days | logged in | 1. Click **+ Add Plan**<br>2. Trigger = `Calendar`, leave Frequency days blank<br>3. Click **Save** | missing freq | Red error under Frequency days: `Required for calendar / both triggers.` | | |
| TC-CREATE-09 | Create PM Plan — meter requires meter_type | logged in | 1. Click **+ Add Plan**<br>2. Trigger = `Meter`, Frequency meter = `1000`, leave Meter type blank<br>3. Click **Save** | missing meter_type | Red error under Meter type: `Required for meter / both triggers.` | | |
| TC-CREATE-10 | Create Monitoring Point — alarm bands valid | active asset exists | 1. Sidebar → **Monitoring Points** → **+ Add Point**<br>2. Asset = (any), Name = `QA Vibration`, Parameter = `vibration`, Unit = `mm/s`, Low alarm = `1`, High alarm = `5`<br>3. Click **Save** | low<high | Redirect to point detail. Alarm Band card shows Low = 1, High = 5. | | |
| TC-CREATE-11 | Create Monitoring Point — low ≥ high rejected | logged in | 1. Click **+ Add Point**<br>2. Low alarm = `5`, High alarm = `1`<br>3. Click **Save** | low>high | Red error under High alarm: `High alarm must be greater than low alarm.` | | |
| TC-CREATE-12 | Create MWO — auto-numbered | active asset exists | 1. Sidebar → **Maintenance WOs** → **+ Add MWO**<br>2. Asset = (any), Type = `Corrective`, Priority = `Medium`, Title = `QA noise complaint`<br>3. Click **Save** | minimal MWO | Redirect to `/eam/mwo/<pk>/`. Number is `MWO-NNNNN`. Status = Draft. | | |
| TC-CREATE-13 | Create Tool — cutting tool happy path | logged in | 1. Sidebar → **Tools & Dies** → **+ Add Tool**<br>2. Name = `QA End Mill`, Type = `Cutting Tool`, Status = `Available`, Expected life cycles = `5000`, Cavity count = `0`<br>3. Click **Save** | cutter | Redirect to tool detail. ID is `TOOL-NNNNN`. Cycles row shows `0 / 5000`. | | |
| TC-CREATE-14 | Create Tool — mold without cavity_count | logged in | 1. Click **+ Add Tool**<br>2. Type = `Mold`, Cavity count = `0`<br>3. Click **Save** | mold no cav | Red error under Cavity count: `Mold tools require a cavity count of at least 1.` | | |
| TC-CREATE-15 | Create Tool — non-mold with cavity_count | logged in | 1. Click **+ Add Tool**<br>2. Type = `Cutting Tool`, Cavity count = `4`<br>3. Click **Save** | cutter w/ cav | Red error under Cavity count: `Cavity count is only meaningful for mold-type tools.` | | |

### 4.4 READ — List Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-01 | EAM dashboard renders | logged in | 1. Navigate to `/eam/` | seed | 6 KPI cards: Active Assets, Critical Assets, Down Assets, Open MWOs, Overdue PM, Open Predictions. All numeric. Recent Work Orders table populated. Upcoming PM table populated. | | |
| TC-LIST-02 | Asset list — columns + actions | logged in | 1. Navigate to `/eam/assets/` | seed | Columns: Tag, Name, Category, Criticality, Status, Actions. Each row carries 3 action icons: Eye (view), Pencil (edit), Bin (delete). No `None` literal anywhere. | | |
| TC-LIST-03 | Asset list — badge colours | logged in | 1. Navigate to `/eam/assets/`<br>2. Inspect badge colour per row | seed | `critical` → red; `high` → amber; `medium` → blue; `low` → grey. Status `down` → red; `maintenance` → amber; `retired` → grey; `operational` → green. | | |
| TC-LIST-04 | Asset list — empty state | tenant has no assets | 1. As `admin_globex` (or after deleting all), navigate to `/eam/assets/` | empty | Table shows a single row: "No assets yet." centred, muted text. No JS error. | | |
| TC-LIST-05 | PM Plan list renders | logged in | 1. Sidebar → **PM Plans** | seed | Columns: Plan, Asset, Trigger, Next Due, Status, Actions. Plan column links to detail. | | |
| TC-LIST-06 | PM Schedule list renders | logged in | 1. Sidebar → **PM Schedule** | seed | Columns: Number, Plan, Asset, Date, Assignee, Status. Status badges: completed → green; overdue → red; in_progress → blue; scheduled → grey. | | |
| TC-LIST-07 | Monitoring Point list renders | logged in | 1. Sidebar → **Monitoring Points** | seed | Columns: Asset, Name, Parameter, Range, Status, Actions. Range shows `low / high` (or `-` if NULL). | | |
| TC-LIST-08 | MWO list renders | logged in | 1. Sidebar → **Maintenance WOs** | seed | Columns: MWO, Asset, Title, Type, Priority, Reported, Status, Actions. Truncated title (≤50 chars). | | |
| TC-LIST-09 | MWO list — Edit/Delete hidden on completed row | seeded MWO `MWO-00001` is completed | 1. Open `/eam/mwo/`<br>2. Find the completed breakdown row<br>3. Inspect the Actions column | completed | Only the **Eye (view)** icon is visible. **Edit (pencil)** and **Delete (bin)** are hidden. | | |
| TC-LIST-10 | Downtime list renders | logged in | 1. Sidebar → **Downtime Events** | seed | Columns: Asset, Started, Ended, Min, Type, MWO, Reason, Actions. Type badge: unplanned → red; planned → blue. | | |
| TC-LIST-11 | Tool list renders + life columns | logged in | 1. Sidebar → **Tools & Dies** | seed | Columns: ID, Name, Type, Cycles, Hours, Status, Actions. Cycles column shows `<current> / <expected>` when expected is set. | | |
| TC-LIST-12 | Failure Prediction list renders | seed includes 1 critical reading | 1. Sidebar → **Failure Predictions** | seed | At least 1 row, status badge **red** for `Open`. Confidence shows `70 %`. | | |

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DETAIL-01 | Asset detail — profile + tabs | logged in | 1. From `/eam/assets/`, click `ASSET-00001` (or any) | seed | Page shows the asset name + tag in title, profile card with 12 fields, 5 tabs (Spare Parts, Meter Readings, Documents, Open Work Orders, Sub-assets) — clicking each tab swaps the inner content without page reload. | | |
| TC-DETAIL-02 | Asset detail — Spare Parts tab populated | seeded asset has spares | 1. Open the seeded `Process Pump 1` detail<br>2. Click **Spare Parts** tab | seed | Table lists 1+ spare parts with Product, Min Qty, On Hand, Delete icon (admin only). | | |
| TC-DETAIL-03 | Asset detail — Meter Readings tab | seeded | 1. Click **Meter Readings** tab | seed | Last 10 readings shown with When, Meter, Value, Recorded By. Inline form at top with Meter type / Reading value / Recorded at / Notes. | | |
| TC-DETAIL-04 | Asset detail — Sub-assets tab shows children | seeded `CNC-LATHE-01` has child `SPINDLE-01` | 1. Open the seeded `CNC Lathe Bay 1` detail<br>2. Click **Sub-assets** tab | seed | Sub-assets table shows 1+ child row(s) with link to child's detail page. | | |
| TC-DETAIL-05 | PM Schedule detail — task checklist | seeded plan has tasks | 1. Open any seeded PM schedule | seed | Page shows status, plan link, asset link. Task Checklist table lists each task with `Pending` text in Result column (no completion yet). | | |
| TC-DETAIL-06 | MWO detail — 3 tabs + workflow buttons | seeded scheduled MWO | 1. Open the seeded scheduled motor MWO | seed | Profile card visible with Status=Scheduled. Three tabs (Labor, Material, Downtime) below. Action buttons in header: **Edit**, **Schedule** (hidden because already scheduled), **Start**, **Cancel**. | | |
| TC-DETAIL-07 | MWO detail — completed view | seeded breakdown MWO is completed | 1. Open the seeded completed pump breakdown MWO | seed | Status=Completed badge. Resolution Notes section visible. Labor, Material, Downtime tabs all populated with rows. **Complete form is hidden.** | | |
| TC-DETAIL-08 | Tool detail — mold cavities tab visible | seeded mold has 4 cavities | 1. Open the seeded `Cover Plate Mold (4-cavity)` | seed | Cavities tab is visible (only for `tool_type='mold'`). Table lists 4 cavities with cycles, defects, status. Cavity 4 shows status `Repaired`. | | |
| TC-DETAIL-09 | Tool detail — non-mold hides cavities tab | seeded cutting tool | 1. Open the seeded `Carbide End Mill 12mm` | seed | Only **Usage Logs** and **Maintenance** tabs are present. **Cavities** tab is **NOT shown** (because tool_type ≠ mold). | | |
| TC-DETAIL-10 | Failure Prediction detail | seeded critical reading exists | 1. Sidebar → **Failure Predictions** → click any row | seed | Detail page shows summary, confidence (70%), Triggered By card with the source reading + value. Investigate / Resolve buttons in the right rail. | | |

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit Asset — pre-fill | logged in | 1. From asset list, click **Pencil** icon on `ASSET-00001`<br>2. Inspect every form field | seed | Every field is pre-populated with the current value. Tag is read-only or hidden (auto-managed). | | |
| TC-EDIT-02 | Edit Asset — save changes | TC-EDIT-01 passed | 1. Change Manufacturer to `QA Mfg`<br>2. Click **Save** | new mfg | Redirect to detail. Green toast `Asset updated.`. Manufacturer field shows `QA Mfg`. | | |
| TC-EDIT-03 | Edit Asset Category — happy path | logged in | 1. From category list, click **Pencil**<br>2. Change Description<br>3. Click **Save** | new desc | Redirect to list. Green toast `Category updated.`. | | |
| TC-EDIT-04 | Edit MWO — only on draft/scheduled/on_hold | seeded scheduled MWO | 1. Open scheduled motor MWO<br>2. Click **Edit**<br>3. Change Title to `QA edited title`<br>4. Save | scheduled | Saved successfully. Detail shows new title. | | |
| TC-EDIT-05 | Edit MWO — completed shows error | seeded completed MWO | 1. Open the completed pump MWO<br>2. Manually visit `/eam/mwo/<pk>/edit/` | completed | Red toast `Only draft / scheduled / on-hold MWOs can be edited.`. Redirect back to detail. | | |
| TC-EDIT-06 | Edit Tool — change life budget | seeded cutting tool | 1. Open Carbide End Mill detail<br>2. Click **Edit**<br>3. Change Expected life cycles from `10000` to `15000`<br>4. Save | new budget | Saved. Tool detail shows `2400 / 15000`. Cycles Remaining = `12600`. | | |
| TC-EDIT-07 | Edit Monitoring Point — alarm change | seeded point | 1. Open Spindle Bearing X detail<br>2. Click **Edit**<br>3. Change High alarm from `4.5` to `5.0`<br>4. Save | new high | Saved. Detail card shows new value. | | |
| TC-EDIT-08 | Edit PM Plan — toggle is_active | seeded plan | 1. Open Quarterly Lubrication plan<br>2. Click **Edit**<br>3. Untick **Is Active**<br>4. Save | inactive | Plan list shows `Inactive` badge. Audit log records `eam.plan.deactivated` (verify via `/tenants/audit/`). | | |

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete Asset Category — confirm dialog | logged in | 1. From category list, click **Bin** icon on a category that has no assets | unused cat | Browser confirm: `Delete category <name>?`. Click **Cancel** → no action. Click again → click **OK** → row disappears, toast `Category deleted.`. | | |
| TC-DELETE-02 | Delete Asset Category — protected when in use | seeded category `Pumps` has assets | 1. Try to delete the `Pumps` category | in-use | Red toast: `Cannot delete category: ...`. Row remains in list. | | |
| TC-DELETE-03 | Delete Asset — happy path | create a throwaway asset first | 1. Create a new asset `Manual QA Pump 2`<br>2. Open its detail<br>3. Click **Delete** in the header | new asset | Confirm: `Delete <tag>? This cannot be undone.`. OK → redirect to list, toast `Asset deleted.`. | | |
| TC-DELETE-04 | Delete Asset — protected by audit children | seeded `PUMP-01` has meter readings (audit) | 1. Open `PUMP-01` detail<br>2. Click **Delete** | seeded | Red toast: `Cannot delete asset: ...` (PROTECT FK from `AssetMeterReading`). Detail page reloads — asset still there. | | |
| TC-DELETE-05 | Delete MWO — only when draft/cancelled | logged in | 1. Open the completed pump breakdown MWO<br>2. Look for Delete button | completed | **No Delete button visible** in header (status-gated). Trying `POST /eam/mwo/<pk>/delete/` directly redirects with toast `Only draft / cancelled MWOs can be deleted.` | | |
| TC-DELETE-06 | Delete MWO — draft happy path | create draft MWO | 1. Create a fresh draft MWO<br>2. Click **Delete** in header | draft | Confirm dialog → OK → redirect to MWO list, toast `Work order deleted.`. | | |
| TC-DELETE-07 | Delete Spare Part inline | seeded asset has spares | 1. Open asset detail → Spare Parts tab<br>2. Click **Bin** on a spare row | seed | Confirm `Remove?`. OK → row removed, toast `Spare part link removed.`. | | |
| TC-DELETE-08 | Delete Tool — happy path | create throwaway tool | 1. Create a fresh tool<br>2. Open detail<br>3. Click **Delete** in header | new tool | Confirm dialog → OK → redirect to list, toast `Tool deleted.`. | | |

### 4.8 SEARCH

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-SEARCH-01 | Asset search — by tag | seed | 1. `/eam/assets/`<br>2. Type `ASSET-00001` into search box<br>3. Click **Filter** | tag | Only the matching asset row shown. Other rows hidden. URL shows `?q=ASSET-00001`. | | |
| TC-SEARCH-02 | Asset search — partial name | seed | 1. Search `Pump` | partial | All assets with `Pump` in name shown (the 2 seeded process pumps + any QA pumps). | | |
| TC-SEARCH-03 | Asset search — case insensitive | seed | 1. Search `pump`<br>2. Note results<br>3. Search `PUMP` | case | Identical result set. | | |
| TC-SEARCH-04 | Asset search — by serial number | seed | 1. Search `SN-PUMP-01` | serial | Process Pump 1 row only. | | |
| TC-SEARCH-05 | Asset search — no match | seed | 1. Search `nonexistent_xyz_qa` | no match | Empty table with `No assets yet.` row. URL retains `?q=nonexistent_xyz_qa`. No 500. | | |
| TC-SEARCH-06 | Asset search — special chars | seed | 1. Search `'; DROP TABLE eam_asset; --` | sql inj | Empty result. **No 500.** No DB damage. Row count for `Asset.objects.count()` is unchanged. | | |
| TC-SEARCH-07 | Asset search — leading/trailing whitespace | seed | 1. Search `   Pump   ` (spaces) | ws | Same result as `Pump` — view trims (`.strip()`). | | |
| TC-SEARCH-08 | MWO search — by number | seed | 1. `/eam/mwo/`, search `MWO-00001` | number | Only the seeded breakdown MWO. | | |
| TC-SEARCH-09 | PM Plan search retains across page nav | seed (or after creating ≥26 plans) | 1. Search `Lub`<br>2. Click page 2 (if pagination present) | search+page | URL becomes `?q=Lub&page=2` and the search remains active. | | |
| TC-SEARCH-10 | Tool search — by tool_id | seed | 1. `/eam/tools/`, search `TOOL-00001` | tool id | Only the cutting tool row. | | |

### 4.9 PAGINATION

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-PAGE-01 | Default page size = 25 | tenant has < 26 of any entity | 1. `/eam/assets/`<br>2. Inspect bottom of card | seed | All 10 seeded assets visible on page 1. Pagination block hidden (`has_other_pages=False`). | | |
| TC-PAGE-02 | Pagination appears at >25 rows | seed many assets | 1. Create 16 throwaway assets via shell:<br>`for i in $(seq 1 16); do ...`<br>2. `/eam/assets/`<br>3. Inspect bottom | 26 rows | Pagination block visible: `1 / 2`. Click `»` → URL becomes `?page=2`, page 2 shows the remaining rows. | | |
| TC-PAGE-03 | Last page partial set | per TC-PAGE-02 | 1. On page 2, observe row count | 26 rows | Page 2 shows ≤ 25 rows. No empty state. | | |
| TC-PAGE-04 | Page beyond max → graceful | logged in | 1. Manually visit `/eam/assets/?page=999` | beyond | View paginates to the last page (per `_paginate()` helper) — does NOT 500. URL still has `?page=999` but content is the last page. | | |
| TC-PAGE-05 | Page invalid → graceful | logged in | 1. Manually visit `/eam/assets/?page=abc` | invalid | First page returned. No 500. | | |
| TC-PAGE-06 | Filter retained across pages | per TC-PAGE-02 | 1. Apply Status = `Operational` filter<br>2. Click page 2 | filter+page | URL `?status=operational&page=2` — Status dropdown still shows `Operational` selected on page 2. | | |
| TC-PAGE-07 | Search retained across pages | per TC-PAGE-02 | 1. Search `Pump`<br>2. Click page 2 if available | q+page | Search box retains `Pump`; page 2 shows next batch of matches. | | |

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-FILTER-01 | Asset status filter | seed | 1. `/eam/assets/`<br>2. Status dropdown → `Operational` → Filter | status | Only operational rows shown. Dropdown retains `Operational`. URL `?status=operational`. | | |
| TC-FILTER-02 | Asset criticality filter | seed | 1. Criticality dropdown → `Critical` → Filter | crit | Only `CNC-LATHE-01` and `CNC-MILL-01` (the seeded critical ones). | | |
| TC-FILTER-03 | Asset category filter | seed | 1. Category dropdown → `Pumps` → Filter | category | Both seeded pumps visible. | | |
| TC-FILTER-04 | Asset combined filters | seed | 1. Status = `Operational`, Criticality = `High`<br>2. Filter | combo | AND of both filters; URL `?status=operational&criticality=high`. | | |
| TC-FILTER-05 | Asset filter + search | seed | 1. Status = `Operational`<br>2. Search `Pump`<br>3. Filter | filter+q | Both filters AND-applied; URL `?q=Pump&status=operational`. | | |
| TC-FILTER-06 | Asset filter clear | seed | 1. Apply filters per above<br>2. Manually delete `?status=...` from URL → press Enter | clear | Full list returned. Dropdowns reset. | | |
| TC-FILTER-07 | MWO type filter | seed | 1. `/eam/mwo/`, Type = `Breakdown` | type | Only the breakdown row. | | |
| TC-FILTER-08 | MWO status filter | seed | 1. Status = `Completed` | status | Only the completed pump breakdown. | | |
| TC-FILTER-09 | PM Plan trigger filter | seed | 1. `/eam/pm-plans/`, Trigger = `Calendar` | trigger | Only calendar-triggered plans. | | |
| TC-FILTER-10 | Monitoring Point parameter filter | seed | 1. `/eam/monitoring-points/`, Parameter = `Vibration` | param | Only vibration points (3 seeded — 2 spindle bearings + pump bearing). | | |
| TC-FILTER-11 | Condition Reading status filter | seed | 1. `/eam/readings/`, Status = `Critical` | crit reading | Exactly 1 row (the seeded deliberate critical reading). | | |
| TC-FILTER-12 | Failure Prediction status filter | seed | 1. `/eam/predictions/`, Status = `Open` | open | The seeded auto-spawned prediction visible. | | |
| TC-FILTER-13 | Tool type filter | seed | 1. `/eam/tools/`, Type = `Mold` | mold | Only the seeded mold. | | |
| TC-FILTER-14 | Downtime type filter | seed | 1. `/eam/downtime/`, Type = `Unplanned` | unplanned | The breakdown's unplanned downtime row. | | |
| TC-FILTER-15 | Filter for zero-result combo | seed | 1. `/eam/mwo/`, Type = `Inspection` | empty result | Empty table with `No work orders yet.` row. URL retains the filter. | | |

### 4.11 Status Transitions / Custom Actions

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-01 | Asset Retire | seed | 1. Open `PUMP-02` detail<br>2. Click **Retire** in header<br>3. Confirm | operational asset | Status badge flips to `Retired`. Header now shows **Reactivate** button (Retire hidden). | | |
| TC-ACTION-02 | Asset Reactivate | TC-ACTION-01 passed | 1. Click **Reactivate** | retired asset | Status flips to `Operational`. Retire button reappears. | | |
| TC-ACTION-03 | Tool Retire / Reactivate | seed | 1. Open Carbide End Mill detail<br>2. Click **Retire** → Confirm<br>3. Click **Reactivate** | tool | Status `Available` → `Retired` → `Available`. is_active flips along. | | |
| TC-ACTION-04 | PM Schedule Start | seed | 1. Open any scheduled PM schedule<br>2. Click **Start** | scheduled | Status badge flips to `In Progress`. `started_at` populated. Complete form appears. | | |
| TC-ACTION-05 | PM Schedule Complete — happy path | TC-ACTION-04 passed; plan has tasks | 1. Use Record Task Result form to record at least one completion (Task = first task, Result = `Pass`)<br>2. Submit Complete form with Notes = `Done.` | task results recorded | Toast `PM <number> completed.`. Status flips to `Completed`. `completed_at` + `completed_by` populated. | | |
| TC-ACTION-06 | PM Schedule Complete — without task results blocked | TC-ACTION-04 passed; plan has tasks; no completions yet | 1. Submit Complete form with Notes blank | no task results | Red error: `Record at least one task completion before completing this PM.`. Status remains `In Progress`. | | |
| TC-ACTION-07 | PM Schedule Skip | scheduled PM | 1. Open scheduled PM schedule<br>2. Click **Skip** → Confirm | scheduled | Status flips to `Skipped`. Toast `PM skipped.` | | |
| TC-ACTION-08 | PM Plan Generate Upcoming | active plan | 1. Open any active PM plan<br>2. Click **Generate Upcoming** | active calendar plan | Toast `Generated N upcoming PM schedule(s).` (or `No new schedules to generate (already covered).` on second click). New rows appear in Upcoming Schedules card. | | |
| TC-ACTION-09 | MWO full lifecycle | seed (or fresh draft) | 1. Open a draft MWO<br>2. Click **Schedule** → status `Scheduled`<br>3. Click **Start** → `In Progress`<br>4. Click **Hold** → `On Hold`<br>5. Click **Resume** → `In Progress`<br>6. Submit **Complete** form with Resolution Notes = `Done.` | draft MWO | Each click triggers a status flip. Final state: `Completed`. Detail page Completion section appears with Resolution Notes. | | |
| TC-ACTION-10 | MWO Complete blocked without notes | in-progress MWO | 1. Submit Complete form with Resolution Notes = `   ` (whitespace only) | empty notes | Red error: `Resolution notes are required to complete a work order.`. Status remains `In Progress`. | | |
| TC-ACTION-11 | MWO Cancel | scheduled MWO | 1. Open the seeded scheduled motor MWO<br>2. Click **Cancel** in header → Confirm | scheduled | Status flips to `Cancelled`. All workflow buttons except **View** are gone. | | |
| TC-ACTION-12 | Failure Prediction Investigate | open prediction | 1. `/eam/predictions/`<br>2. Click the seeded prediction<br>3. Click **Investigate** | open | Status flips to `Investigating`. Investigate button gone; Resolve form remains. | | |
| TC-ACTION-13 | Failure Prediction Resolve — happy path | open or investigating | 1. Resolve form: Outcome = `Resolved`, Resolution Notes = `Bearing was wear-related; replaced.`<br>2. Submit | valid notes | Status flips to `Resolved`. Detail shows Resolution Notes section. | | |
| TC-ACTION-14 | Failure Prediction Resolve blocked without notes | open prediction | 1. Submit Resolve form with notes blank | empty | Red error `Resolution notes are required for traceability.` | | |
| TC-ACTION-15 | Record Condition Reading — normal | seeded point | 1. Open Spindle Bearing X detail<br>2. Reading form: Value = `2.0`<br>3. Submit | normal | Reading appears in table with status `Normal` (green badge). No FailurePrediction spawned. | | |
| TC-ACTION-16 | Record Condition Reading — critical auto-spawns prediction | seeded point with `high_alarm=4.5` | 1. Reading value = `15` (well above 20% margin)<br>2. Submit | critical | Reading row shows **Critical** (red). Visit `/eam/predictions/` — a NEW prediction row appears for the asset (idempotent: 2nd critical reading does NOT create a 2nd prediction while the first is open). | | |
| TC-ACTION-17 | Record Meter Reading | seeded asset | 1. Open `PUMP-01` detail → Meter Readings tab<br>2. Form: Meter type = `hours`, Reading value = `9999.5`, Recorded at = now<br>3. Submit | hours reading | Toast `Meter reading recorded.`. New row at top of table. Visible in `/eam/meter-readings/` list. | | |
| TC-ACTION-18 | Add MWO Labor Log | open MWO | 1. Open in-progress CNC PM MWO<br>2. Labor tab → form: Technician = `admin_acme`, Started = now, Ended = now+1h, Hourly rate = `45`<br>3. Submit | labor | New row in Labor table. `Min` shows `60.00`. `Cost` shows `45.00`. | | |
| TC-ACTION-19 | Add MWO Material Log | open MWO + plm.Product exists | 1. Open same MWO → Material tab<br>2. Form: Product = (any), Qty = `2`, Unit cost = `15.00`<br>3. Submit | material | New row. Total = `30.00`. | | |
| TC-ACTION-20 | Record Downtime against MWO refreshes denorm | open MWO | 1. Open MWO → Downtime tab<br>2. Form: Started = now, Ended = now+30min, Type = `Unplanned`, Reason = `QA test`<br>3. Submit | downtime | New row with `30.00` minutes. **MWO header KPI** `Downtime: 30 min` updates (refresh page to confirm denorm). | | |
| TC-ACTION-21 | Tool Usage Log bumps denorm | seed cutting tool | 1. Open Carbide End Mill detail<br>2. Usage form: Used at = now, Cycles added = `100`, Hours added = `1.5`<br>3. Submit | usage | New row in Usage Logs. Tool detail header `Cycles` row jumps from `2400 / 10000` → `2500 / 10000`. Hours row similarly updates. | | |
| TC-ACTION-22 | Tool Maintenance Record + sharpen date sync | seed cutting tool | 1. Maintenance form: Type = `Sharpening`, Performed at = today, Cost = `40`, Notes = `QA regrind`<br>2. Submit | sharpening | New maintenance row. Tool profile `Last Sharpened` updates to today. | | |
| TC-ACTION-23 | Mold Cavity History add | seeded mold | 1. Open mold detail → Cavities tab<br>2. Add cavity #5 (or duplicate cavity #4) | new cav | If cavity 5 (within tool's cavity_count): success. If 99: red error `Cavity number exceeds the tool cavity count`. If 4 (already exists): red error `A history entry already exists for this cavity.` | | |

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-UI-01 | Page titles | logged in | 1. Visit each list URL<br>2. Inspect browser tab | — | Tab title for `/eam/assets/` reads `Assets | NavMSM`; `/eam/mwo/` reads `Maintenance Work Orders | NavMSM`; etc. Pattern: `<page> | NavMSM`. | | |
| TC-UI-02 | Sidebar active highlight | logged in | 1. Navigate to `/eam/mwo/`<br>2. Inspect sidebar | — | **Equipment & Assets** group is expanded. **Maintenance WOs** link has the active style (left-bar accent or bolded). | | |
| TC-UI-03 | Toast colours | logged in | 1. Trigger a success action (e.g. create asset)<br>2. Trigger an error (e.g. delete an asset that has audit children) | — | Success toast: green/blue background with check icon. Error toast: red with warning icon. Both auto-dismiss after ~5s. | | |
| TC-UI-04 | Confirm dialog text includes entity | logged in | 1. Click Bin on an asset row | — | Dialog text reads `Delete asset <tag>?` (substituted with the actual tag). | | |
| TC-UI-05 | Form errors render below field | logged in | 1. Submit a Create form with one invalid field | — | Error message appears in red, directly under the offending input (crispy-forms standard). Other fields keep entered values. | | |
| TC-UI-06 | Required markers visible | logged in | 1. Open `/eam/assets/new/` | — | Required fields (Name, Criticality, Status) display a red `*` next to label. | | |
| TC-UI-07 | Long text wraps cleanly | logged in | 1. Create an asset with `Description` of 500 chars Lorem Ipsum<br>2. View detail | long text | Description wraps inside its card; no horizontal scroll on the page. | | |
| TC-UI-08 | Mobile viewport 375×667 | logged in | 1. DevTools → Toggle device toolbar → iPhone SE (375×667)<br>2. Visit `/eam/`<br>3. Visit `/eam/mwo/`<br>4. Visit MWO detail | — | Sidebar collapses behind the hamburger. Tables overflow horizontally with a visible scrollbar — no off-screen content. KPI cards stack 1-per-row. | | |
| TC-UI-09 | Tablet viewport 768×1024 | logged in | 1. DevTools → iPad → Visit `/eam/assets/<pk>/` | — | Asset detail tabs render in a single row. Profile + sidebar arrange in 2 columns or stack cleanly. | | |
| TC-UI-10 | Keyboard navigation | logged in | 1. Open `/eam/assets/new/`<br>2. Use Tab to walk every input | — | Tab order is logical (top to bottom, left to right). Each focused element shows a visible focus ring. | | |
| TC-UI-11 | Form submits on Enter | logged in | 1. Open `/eam/assets/new/`<br>2. Fill required fields<br>3. Press Enter from any text input | — | Form submits as if Save was clicked. | | |
| TC-UI-12 | DevTools Console clean | logged in | 1. Visit each top-level page (dashboard, every list, every detail of a seeded record)<br>2. Watch Console | — | **Zero errors** from EAM templates. Some 3rd-party warnings (jQuery, Bootstrap) tolerated. | | |
| TC-UI-13 | Empty-state UX | tenant has 0 of an entity | 1. Visit a page where the tenant truly has nothing (e.g. `/eam/predictions/` after manually clearing the seeded one) | — | Single muted row reading `No predictions yet.` (or similar). Centered. No broken icons. | | |
| TC-UI-14 | Status badge colour matches CHOICES | seeded data | 1. Verify on each list page: every status badge uses the colour mapped to that exact status string | — | E.g. `MWO.status='completed'` → `bg-success-subtle text-success`. `MWO.status='cancelled'` → `bg-secondary-subtle text-secondary`. Inspect via DevTools → Elements. | | |
| TC-UI-15 | Sidebar hidden for supplier role | log in as a supplier-portal user | 1. Log in as `supplier_acme_demo` / `Welcome@123`<br>2. Inspect sidebar | supplier role | The **Equipment & Assets** group is **NOT visible** (hidden by `{% if request.user.role != 'supplier' %}`). The supplier sees only the Supplier Portal group. | | |

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-NEG-01 | Submit Asset form with all required blank | logged in | 1. `/eam/assets/new/`<br>2. Click **Save** without typing anything | empty | Multiple red errors: under Name, Criticality, Status. No 500. | | |
| TC-NEG-02 | Negative purchase_cost rejected | logged in | 1. `/eam/assets/new/`<br>2. Name = `QA neg`, Purchase cost = `-100`, Criticality = `Low`<br>3. Save | negative | Red error under Purchase cost: `Ensure this value is greater than or equal to 0.` | | |
| TC-NEG-03 | Letters in decimal field | logged in | 1. Asset form, Purchase cost = `abc`<br>2. Save | non-numeric | Red error: `Enter a number.` (or similar). No 500. | | |
| TC-NEG-04 | Frequency days > 3650 rejected | logged in | 1. PM plan form, Frequency days = `99999`<br>2. Save | over max | Red error: `Ensure this value is less than or equal to 3650.` | | |
| TC-NEG-05 | Confidence pct > 100 rejected | manually crafted POST | 1. Open DevTools → Network → grab CSRF<br>2. POST to `/eam/predictions/<pk>/` with `confidence_pct=150` (this isn't possible via UI — but the model validator should still catch it if exposed) | over 100 | Form rejects (or model `full_clean` raises ValidationError). No 500, no DB write. | | |
| TC-NEG-06 | Upload .exe to AssetDocument blocked | logged in | 1. Open asset detail → Documents tab<br>2. Choose any `.exe` file<br>3. Submit | bad ext | Red error: `Unsupported file type. Allowed: .dwg, .dxf, .jpeg, .jpg, .pdf, .png` (sorted). | | |
| TC-NEG-07 | Upload >25 MB file blocked | logged in | 1. Create a >25 MB PDF locally<br>2. Try to upload | oversized | Red error: `File exceeds 25 MB cap.` | | |
| TC-NEG-08 | Upload .exe to ToolMaintenanceRecord blocked | logged in | 1. Open tool detail → Maintenance tab<br>2. Try to upload `evil.exe` | bad ext | Same allowlist error (different list — only PDF/PNG/JPG/JPEG). | | |
| TC-NEG-09 | Double-submit asset create | logged in | 1. Fill asset form<br>2. Spam-click Save 5 times in 1 second | double-click | **Exactly one** asset is created. Database row count for `Asset.objects.filter(name=...)` = 1. | | |
| TC-NEG-10 | Browser back after create does not resubmit | logged in | 1. Create an asset<br>2. After redirect, click browser **Back**<br>3. Click **Forward** | back/forward | Form is shown again on Back, but the resubmission warning appears or no duplicate row is created on Forward. | | |
| TC-NEG-11 | Refresh on POST → no duplicate | logged in | 1. Create an asset<br>2. After redirect, click **Refresh** | refresh | Detail page reloads cleanly. No duplicate row created. | | |
| TC-NEG-12 | Mold cavity_number > tool.cavity_count | seeded mold (cavity_count=4) | 1. Open mold detail → Cavities tab<br>2. Try to add cavity #99 | over | Red error `Cavity number exceeds the tool cavity count (4).` | | |
| TC-NEG-13 | Duplicate cavity_number rejected | seeded mold | 1. Try to add cavity #1 again | dup | Red error `A history entry already exists for this cavity.` | | |
| TC-NEG-14 | RBAC — operator cannot create Asset | logged in as `acme_op_qa` | 1. Click **+ Add Asset** | non-admin | Either button is hidden, OR clicking redirects with red toast `Only tenant administrators can access that page.`. No asset created. | | |
| TC-NEG-15 | RBAC — operator cannot delete MWO | logged in as `acme_op_qa` | 1. Open a draft MWO<br>2. Try `POST /eam/mwo/<pk>/delete/` via DevTools | non-admin | Redirect with toast. MWO is **NOT deleted** — verify in admin profile. | | |
| TC-NEG-16 | RBAC — operator can record meter reading | logged in as `acme_op_qa` | 1. Open `PUMP-01` detail → Meter Readings tab<br>2. Submit a reading | non-admin | Successfully created (operators are allowed to log non-privileged data). | | |
| TC-NEG-17 | RBAC — operator can start MWO | logged in as `acme_op_qa` | 1. Open seeded scheduled motor MWO<br>2. Click **Start** | non-admin | Status flips to `In Progress`. Operators are allowed to drive workflow on MWOs they're assigned. | | |

### 4.14 Cross-Module Integration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-INT-01 | Andon equipment alert auto-spawns breakdown MWO | seeded asset + work center | 1. Sidebar → **Operations → Andon** (`/mes/andon/`)<br>2. Click **+ New Alert**<br>3. Fill: Type = `Equipment`, Severity = `High`, Title = `QA test andon`, Work Center = (any), Asset = (any seeded asset)<br>4. Submit | equipment+asset | Andon row created. Visit `/eam/mwo/` — a **new draft MWO** appears with `wo_type=Breakdown`, `priority=High`, title containing `Equipment andon: QA test andon`, and a `source_andon` link in the MWO detail. | | |
| TC-INT-02 | Andon equipment alert WITHOUT asset link → no MWO spawned | logged in | 1. Create another andon: Type = `Equipment`, Severity = `Medium`, **leave Asset blank**<br>2. Submit | no asset | Andon created. **No new MWO** appears in `/eam/mwo/`. | | |
| TC-INT-03 | Andon QUALITY alert with asset → no MWO spawned | logged in | 1. Create andon: Type = `Quality`, Asset = (any) | non-equipment | No MWO spawned (the auto-spawn only fires for `alert_type='equipment'`). | | |
| TC-INT-04 | Andon → MWO is idempotent | TC-INT-01 passed | 1. Re-save the same andon (e.g. edit notes and save again) | re-save | **No duplicate MWO** created — `source_andon` lookup prevents respawn. | | |
| TC-INT-05 | Production Report on tooled MWO emits ToolUsageLog | a `mes.MESWorkOrder` with `tool` set + an in-progress operation | 1. Set the tool on a MES work order: open Django admin `/admin/mes/mesworkorder/<pk>/change/`, set Tool to `TOOL-00001`, save<br>2. Sidebar → **Production → Reports** → **+ Production Report**<br>3. Submit a report with `good_qty=10, scrap_qty=0` against an op of that work order | tooled MWO | Visit `/eam/tools/<TOOL-00001-pk>/` → Usage Logs tab now shows a NEW row `cycles_added=10`. Tool's Current Cycles bumps by 10. | | |
| TC-INT-06 | qms.MeasurementEquipment.asset FK link | logged in | 1. Sidebar → **Quality → Equipment**<br>2. Click any equipment → **Edit**<br>3. Asset dropdown — select any seeded asset → Save | linked | Equipment detail (or admin) shows the linked asset. Reverse: open `/eam/assets/<pk>/` → no UI surface for this link in v1, but the FK is queryable via `asset.measurement_equipment.all()`. | | |

---

## 5. Bug Log

> Populated 2026-05-06 from the automated walkthrough at [.claude/manual-tests/eam_walkthrough.py](.claude/manual-tests/eam_walkthrough.py) (54 OK / 1 BUG before fix).
>
> **Walkthrough scope:** 13 list pages + 7 form GETs + 10 detail pages + 8 status-gated button presence checks + 2 RBAC + 1 cross-tenant 404 + 4 cross-module signal cases + 2 idempotency cases + 4 filter scoping + 1 form POST + 1 status-gated edit + 1 PROTECT delete = **54 assertions** against the live MySQL-backed seed data.

| Bug ID | TC ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Status | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | TC-LIST-06 (and 8 sibling pages) | **High** | `/eam/pm-schedules/` (also `/eam/assets/<pk>/`, `/eam/mwo/<pk>/`, `/eam/condition-points/<pk>/`, `/eam/tools/<pk>/`, `/eam/predictions/<pk>/`, `/eam/pm-schedules/<pk>/`) | 1. Run `seed_eam` to populate the seeded tenant<br>2. Run `python manage.py generate_pm_schedules` (or any path that creates a `PMSchedule` with `assignee=None`)<br>3. Open `/eam/pm-schedules/` | Page renders 200 with the schedule's assignee column showing `-` | **HTTP 500** with `django.template.base.VariableDoesNotExist: Failed lookup for key [username] in None`. Template chain `{{ s.assignee.get_full_name\|default:s.assignee.username\|default:"-" }}` evaluates the second operand even when `s.assignee` is None, which raises during attribute lookup on None. | **FIXED** (2026-05-06). 9 templates updated to use `{% if fk %}{{ fk.get_full_name\|default:fk.username }}{% else %}-{% endif %}`. Regression test added in [apps/eam/tests/test_views.py — TestNullableFKRendersGracefully](apps/eam/tests/test_views.py). Lesson captured as L-19. | All — root cause was Django template engine, browser-agnostic. |

**Severity definitions**

- **Critical** — data loss, security breach, or app crash; blocks release.
- **High** — major feature broken, no workaround.
- **Medium** — feature partially broken, workaround exists.
- **Low** — minor issue; cosmetic with functional impact (mis-aligned text on action button, badge wrong colour).
- **Cosmetic** — purely visual; no functional impact.

---

## 6. Sign-off & Release Recommendation

### 6.1 Section roll-up

| Section | Total cases | Pass | Fail | Blocked | Notes |
|---|---:|---:|---:|---:|---|
| §4.1  Authentication & Access | 5 | | | | |
| §4.2  Multi-Tenancy Isolation | 6 | | | | |
| §4.3  CREATE | 15 | | | | |
| §4.4  READ — List Page | 12 | | | | |
| §4.5  READ — Detail Page | 10 | | | | |
| §4.6  UPDATE | 8 | | | | |
| §4.7  DELETE | 8 | | | | |
| §4.8  SEARCH | 10 | | | | |
| §4.9  PAGINATION | 7 | | | | |
| §4.10 FILTERS | 15 | | | | |
| §4.11 Status Transitions / Custom Actions | 23 | | | | |
| §4.12 Frontend UI / UX | 15 | | | | |
| §4.13 Negative & Edge Cases | 17 | | | | |
| §4.14 Cross-Module Integration | 6 | | | | |
| **TOTAL** | **121** | | | | |

### 6.2 Release recommendation

| Field | Value |
|---|---|
| Tester | _________ |
| Date executed | _________ |
| Build commit / tag | _________ |
| Browsers verified | Chrome ☐  Edge ☐  Firefox ☐  Mobile ☐ |
| Critical bugs open | _________ |
| High bugs open | _________ |
| **Recommendation** | ☐ **GO**  ☐ **NO-GO**  ☐ **GO-with-fixes** |
| Rationale (one sentence) | _________________________________________________________ |

---

### Appendix A — Quick reference: cross-module signal verification via Django shell

If a TC-INT case is ambiguous, drop into the shell to confirm the signal fired:

```powershell
python manage.py shell -c "from apps.eam.models import MaintenanceWorkOrder; print([m.mwo_number for m in MaintenanceWorkOrder.all_objects.filter(source_andon__isnull=False)])"
python manage.py shell -c "from apps.eam.models import ToolUsageLog; print(ToolUsageLog.all_objects.filter(mes_work_order__isnull=False).count())"
python manage.py shell -c "from apps.eam.models import FailurePrediction; print([(p.asset.tag, p.status) for p in FailurePrediction.all_objects.all()])"
```

### Appendix B — Reset between runs

If the test data state diverges from the seed:

```powershell
python manage.py shell -c "from apps.eam.models import *; [m.all_objects.all().delete() for m in [ToolUsageLog,ToolMaintenanceRecord,MoldCavityHistory,Tool,MWOMaterialLog,MWOLaborLog,DowntimeEvent,PMTaskCompletion,PMSchedule,MaintenanceTask,MaintenancePlan,ConditionReading,ConditionMonitoringPoint,FailurePrediction,MaintenanceWorkOrder,AssetMeterReading,AssetSparePart,Asset,AssetCategory]]"
python manage.py seed_eam
```

The seeder is idempotent — bare `seed_eam` is safe to re-run; `--flush` only needed when state is corrupted.

---

**End of plan.**
