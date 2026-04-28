# Shop Floor Control (MES) — Manual Test Plan

> Generated 2026-04-29 · Target module: `apps.mes` (Module 6 — Work Order Execution, Operator Terminal, Production Reporting, Andon, Paperless Work Instructions)
> Tester fills the **Pass/Fail** and **Notes** columns as they go. Use the [Bug Log](#5-bug-log) to record defects.

---

## 1. Scope & Objectives

This plan validates the full MES module shipped under [apps/mes/](apps/mes/) — every page, button, filter, and workflow action defined in [apps/mes/urls.py](apps/mes/urls.py). It is a **complete module test** (not smoke-only) covering CRUD, search, pagination, filters, status workflows, multi-tenant isolation, frontend UI/UX, and negative/edge cases.

**In scope (5 sub-modules):**

| # | Sub-module | Models tested | Pages |
|---|---|---|---|
| 6.1 | Work Order Execution | `MESWorkOrder`, `MESWorkOrderOperation` | List/Detail/Edit/Delete + Start/Hold/Complete/Cancel + Operation Detail + Op Start/Pause/Resume/Stop + Dispatch from PPS |
| 6.2 | Operator Terminal Interface | `ShopFloorOperator`, `OperatorTimeLog` | Terminal kiosk · Operator CRUD · Clock-in / Clock-out · Time-log read-only list |
| 6.3 | Production Reporting | `ProductionReport` | List · Create · Detail · Delete (rollup-aware) |
| 6.4 | Andon & Alert Management | `AndonAlert` | List/Create/Detail/Edit/Delete + Acknowledge/Resolve/Cancel |
| 6.5 | Paperless Work Instructions | `WorkInstruction`, `WorkInstructionVersion`, `WorkInstructionAcknowledgement` | Instruction CRUD + Version add/release/obsolete + auth-gated download + typed-signature acknowledgement |

**Out of scope:** automated tests, performance/load, accessibility audit (covered separately by `/sqa-review`).

**Acceptance bar:** every TC in §4 passes on Chrome desktop, no console errors, no 500s, multi-tenant isolation holds, status-gated buttons behave correctly.

---

## 2. Pre-Test Setup

Run these once before the test session.

### 2.1 Start the server (PowerShell)

```powershell
cd c:\xampp\htdocs\NavMSM
python manage.py migrate
python manage.py seed_data --flush
python manage.py runserver
```

> `seed_data` with `--flush` runs the orchestrator: plans + tenants + PLM + BOM + PPS + MRP + MES, in that order ([apps/core/management/commands/seed_data.py:11-25](apps/core/management/commands/seed_data.py#L11-L25)). MES depends on PPS production orders + routings being seeded first.

### 2.2 Open the app

- URL: `http://127.0.0.1:8000/`
- Login URL: `http://127.0.0.1:8000/accounts/login/`

### 2.3 Login credentials (seeded by [apps/tenants/management/commands/seed_tenants.py](apps/tenants/management/commands/seed_tenants.py))

| Tenant | Username | Password | Role |
|---|---|---|---|
| Acme Manufacturing | `admin_acme` | `Welcome@123` | Tenant admin (PRIMARY for this test run) |
| Globex Industries | `admin_globex` | `Welcome@123` | Tenant admin (used for cross-tenant isolation tests) |
| Stark Production Co. | `admin_stark` | `Welcome@123` | Tenant admin (alternate) |
| Acme staff | `acme_supervisor_1` | `Welcome@123` | Tenant non-admin user (for operator-vs-admin role tests) |
| — | `admin` | superuser pwd | **DO NOT USE** for MES tests — `tenant=None`, will see empty pages by design ([apps/accounts/views.py:39-45](apps/accounts/views.py#L39-L45)). |

### 2.4 Verify seed data

After login as `admin_acme`, navigate to `http://127.0.0.1:8000/mes/`. You should see the MES dashboard with:

- **5 operators** (badges `B0001`–`B0005`) per [apps/mes/management/commands/seed_mes.py:51-78](apps/mes/management/commands/seed_mes.py#L51-L78)
- **Up to 6 work orders** dispatched from released / in-progress production orders, with status spread (2 dispatched, 2 in-progress, 1 on-hold, 1 completed) per [apps/mes/management/commands/seed_mes.py:84-130](apps/mes/management/commands/seed_mes.py#L84-L130)
- **~12 time logs** + **~8 production reports** on in-progress / completed work orders
- **4 andon alerts** spanning Open / Acknowledged / Resolved / Cancelled
- **3 work instructions** with **1–2 versions each** + **4 acknowledgements** on the released versions

If any of these are zero, re-run `python manage.py seed_mes --flush`.

### 2.5 Browser/viewport matrix

| Profile | Browser | Viewport | Priority |
|---|---|---|---|
| Desktop primary | Chrome (latest) | 1920×1080 | P0 — run every TC here |
| Desktop secondary | Edge / Firefox | 1366×768 | P1 — spot-check |
| Tablet | Chrome DevTools "iPad" | 768×1024 | P1 — UI section only |
| Mobile | Chrome DevTools "iPhone SE" | 375×667 | P1 — Terminal kiosk + UI section |

### 2.6 Reset between runs

Most workflow TCs leave seed records in a transformed state (running → completed, open → acknowledged, draft → released, etc.). To restart:

```powershell
python manage.py seed_mes --flush
```

This wipes all MES rows for demo tenants and re-seeds. (PPS / PLM / BOM / MRP data is left untouched.)

---

## 3. Test Surface Inventory

### 3.1 URL routes — verified against [apps/mes/urls.py](apps/mes/urls.py)

| # | URL | View | Notes |
|---|---|---|---|
| 1 | `/mes/` | `MESIndexView` | Dashboard — KPI cards + recent WOs + recent Andon |
| 2 | `/mes/terminal/` | `TerminalView` | Touchscreen kiosk — needs `ShopFloorOperator` profile |
| 3 | `/mes/work-orders/` | `WorkOrderListView` | Filters: `q`, `status`, `priority`. Page size 20. |
| 4 | `/mes/work-orders/<pk>/` | `WorkOrderDetailView` | Rollup + ops table + recent reports + andon alerts |
| 5 | `/mes/work-orders/<pk>/edit/` | `WorkOrderEditView` | Editable only when `status in ('dispatched','on_hold')`. **Admin-only.** |
| 6 | `/mes/work-orders/<pk>/delete/` | `WorkOrderDeleteView` | POST. In-progress blocked. **Admin-only.** |
| 7 | `/mes/work-orders/<pk>/start/` | `WorkOrderStartView` | dispatched/on_hold → in_progress |
| 8 | `/mes/work-orders/<pk>/hold/` | `WorkOrderHoldView` | in_progress → on_hold |
| 9 | `/mes/work-orders/<pk>/complete/` | `WorkOrderCompleteView` | in_progress → completed |
| 10 | `/mes/work-orders/<pk>/cancel/` | `WorkOrderCancelView` | non-terminal → cancelled. **Admin-only.** |
| 11 | `/mes/operations/<pk>/` | `OperationDetailView` | Per-op time logs + production reports |
| 12 | `/mes/operations/<pk>/start/` | `OperationStartView` | Records `start_job` log + flips op status |
| 13 | `/mes/operations/<pk>/pause/` | `OperationPauseView` | Records `pause_job` |
| 14 | `/mes/operations/<pk>/resume/` | `OperationResumeView` | Records `resume_job` |
| 15 | `/mes/operations/<pk>/stop/` | `OperationStopView` | Records `stop_job` + completes op |
| 16 | `/mes/dispatch/<production_order_pk>/` | `DispatchView` | POST. **Admin-only.** Idempotent. |
| 17 | `/mes/operators/` | `OperatorListView` | Filters: `q`, `active`. Page size 25. |
| 18 | `/mes/operators/new/` | `OperatorCreateView` | **Admin-only.** |
| 19 | `/mes/operators/<pk>/` | `OperatorDetailView` | |
| 20 | `/mes/operators/<pk>/edit/` | `OperatorEditView` | **Admin-only.** |
| 21 | `/mes/operators/<pk>/delete/` | `OperatorDeleteView` | POST. **Admin-only.** |
| 22 | `/mes/operators/<pk>/clock-in/` | `OperatorClockInView` | POST. Self-only unless tenant admin. |
| 23 | `/mes/operators/<pk>/clock-out/` | `OperatorClockOutView` | POST. Self-only unless tenant admin. |
| 24 | `/mes/time-logs/` | `TimeLogListView` | Filters: `operator`, `action`. Page size 30. Read-only. |
| 25 | `/mes/reports/` | `ReportListView` | Filters: `q`, `scrap_reason`. Page size 25. |
| 26 | `/mes/reports/new/` | `ReportCreateView` | Optional `?op=<pk>` query param preselects the operation |
| 27 | `/mes/reports/<pk>/` | `ReportDetailView` | |
| 28 | `/mes/reports/<pk>/delete/` | `ReportDeleteView` | POST. Adjusts op + work-order denorms. **Admin-only.** |
| 29 | `/mes/andon/` | `AndonListView` | Filters: `q`, `alert_type`, `severity`, `status`. Page size 25. |
| 30 | `/mes/andon/new/` | `AndonCreateView` | Auto-numbers `AND-00001` |
| 31 | `/mes/andon/<pk>/` | `AndonDetailView` | |
| 32 | `/mes/andon/<pk>/edit/` | `AndonEditView` | Editable only when `status in ('open','acknowledged')`. **Admin-only.** |
| 33 | `/mes/andon/<pk>/acknowledge/` | `AndonAcknowledgeView` | open → acknowledged |
| 34 | `/mes/andon/<pk>/resolve/` | `AndonResolveView` | open/acknowledged → resolved (notes required) |
| 35 | `/mes/andon/<pk>/cancel/` | `AndonCancelView` | open/acknowledged → cancelled. **Admin-only.** |
| 36 | `/mes/andon/<pk>/delete/` | `AndonDeleteView` | POST. **Admin-only.** |
| 37 | `/mes/instructions/` | `InstructionListView` | Filters: `q`, `doc_type`, `status`, `product`. Page size 20. |
| 38 | `/mes/instructions/new/` | `InstructionCreateView` | **Admin-only.** Auto-numbers `SOP-00001` |
| 39 | `/mes/instructions/<pk>/` | `InstructionDetailView` | Versions + ack form |
| 40 | `/mes/instructions/<pk>/edit/` | `InstructionEditView` | **Admin-only.** |
| 41 | `/mes/instructions/<pk>/delete/` | `InstructionDeleteView` | POST. **Admin-only.** |
| 42 | `/mes/instructions/<pk>/versions/new/` | `InstructionVersionCreateView` | **Admin-only.** |
| 43 | `/mes/instructions/versions/<pk>/release/` | `InstructionVersionReleaseView` | POST. Auto-obsoletes prior released version. **Admin-only.** |
| 44 | `/mes/instructions/versions/<pk>/obsolete/` | `InstructionVersionObsoleteView` | POST. **Admin-only.** |
| 45 | `/mes/instructions/versions/<pk>/download/` | `InstructionVersionDownloadView` | Auth-gated `FileResponse` |
| 46 | `/mes/instructions/<pk>/ack/` | `InstructionAcknowledgeView` | POST. Typed-signature acknowledgement. |

### 3.2 Sidebar navigation — verified against [templates/partials/sidebar.html:118-130](templates/partials/sidebar.html#L118-L130)

The "**Shop Floor (MES)**" group sits between "Material Requirements (MRP)" and "User Management" and contains 8 links: MES Dashboard, Operator Terminal, Work Orders, Operators, Time Logs, Production Reports, Andon Alerts, Work Instructions.

### 3.3 Cross-module hooks

| Surface | What was added | Reference |
|---|---|---|
| PPS Production Order detail page | "Dispatch to Shop Floor" button (visible when `status == 'released'`) | [templates/pps/orders/detail.html:24-29](templates/pps/orders/detail.html#L24-L29) |
| Sidebar | New collapse group `#sidebarMES` | [templates/partials/sidebar.html:118-130](templates/partials/sidebar.html#L118-L130) |

---

## 4. Test Cases

> Legend: `Pass / Fail / Blocked / N/A` for the **Pass/Fail** column. Use the **Notes** column for screenshots, error text, and follow-ups.

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous redirect on dashboard | Logged out | 1. Open `http://127.0.0.1:8000/mes/`<br>2. Observe redirect | — | Browser navigates to `/accounts/login/?next=/mes/` |  |  |
| TC-AUTH-02 | Anonymous redirect on terminal | Logged out | 1. Open `http://127.0.0.1:8000/mes/terminal/` | — | Redirect to `/accounts/login/?next=/mes/terminal/` |  |  |
| TC-AUTH-03 | Anonymous redirect on work-order list | Logged out | 1. Open `http://127.0.0.1:8000/mes/work-orders/` | — | Redirect to login |  |  |
| TC-AUTH-04 | Superuser sees empty MES (BY DESIGN) | Logged in as `admin` (superuser, `tenant=None`) | 1. Open `/mes/`<br>2. Open `/mes/work-orders/`<br>3. Open `/mes/operators/` | — | A yellow info banner appears: "You are signed in as a user without a tenant... Log in as a tenant admin (e.g. admin_acme) to access this page." Redirect to dashboard. ([apps/accounts/views.py:39-45](apps/accounts/views.py#L39-L45)) |  |  |
| TC-AUTH-05 | Tenant admin login renders MES | Logged in as `admin_acme` | 1. Open `/mes/`<br>2. Verify dashboard renders with seeded data | — | Dashboard shows non-zero "Open Work Orders" KPI |  |  |
| TC-AUTH-06 | Non-admin user can read MES but cannot access admin-gated forms | Logged in as `acme_supervisor_1` (tenant non-admin) | 1. Open `/mes/work-orders/` (read OK)<br>2. Click any **Edit** action button — observe access<br>3. Open `/mes/operators/new/` directly | — | Step 1: list page renders. Step 2 + 3: redirect to dashboard with a warning toast (admin-required mixin) |  |  |
| TC-AUTH-07 | Non-admin user CAN clock in/out + start/stop their own jobs | Logged in as `acme_supervisor_1` (with seeded operator profile) | 1. Open `/mes/terminal/`<br>2. Click **Clock In** → toast<br>3. Click any open op's **Start Job** → toast | — | Both POSTs succeed (operator-level actions allowed under `TenantRequiredMixin`) |  |  |

### 4.2 Multi-Tenancy Isolation

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Acme list excludes Globex work orders | Logged in as `admin_acme` | 1. Open `/mes/work-orders/`<br>2. Note the `WO-XXXXX` numbers shown<br>3. Logout, login as `admin_globex`, open `/mes/work-orders/`<br>4. Note Globex WO numbers | — | The two sets of `wo_number` values are disjoint — no overlap |  |  |
| TC-TENANT-02 | IDOR — direct URL to other tenant's WO | Logged in as `admin_acme`. Note any Globex `WO-NNNNN` pk from step 1 of TC-TENANT-01 (open `/admin/mes/mesworkorder/` as superuser to see PKs across tenants) | 1. While logged in as `admin_acme`, manually visit `/mes/work-orders/<globex-pk>/` | URL with another tenant's PK | HTTP 404 (Page not found) — `get_object_or_404(..., tenant=request.tenant)` |  |  |
| TC-TENANT-03 | IDOR — direct URL to other tenant's andon alert | Logged in as `admin_acme`, know one Globex andon alert pk | 1. Visit `/mes/andon/<globex-pk>/` | — | 404 |  |  |
| TC-TENANT-04 | IDOR — direct URL to other tenant's work instruction download | Logged in as `admin_acme`, know one Globex work-instruction-version pk that has an attachment | 1. Visit `/mes/instructions/versions/<globex-pk>/download/` | — | 404 — never streams the file |  |  |
| TC-TENANT-05 | Cross-tenant operator clock-in attempt | Logged in as `admin_acme`, know a Globex operator pk | 1. POST to `/mes/operators/<globex-pk>/clock-in/` (use a form on the Acme page after editing the action URL in DevTools) | — | 404 (operator scoped by tenant) |  |  |

### 4.3 CREATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-01 | Dispatch a released production order | Logged in as `admin_acme`. Have at least one PPS production order in `released` status (or temporarily release one from `/pps/orders/`) | 1. Open the released production order's detail page in PPS<br>2. Click **Dispatch to Shop Floor**<br>3. Confirm the dialog | — | Redirect to `/mes/work-orders/<new-pk>/`. Green toast: `Production order PO-XXXXX dispatched as WO-XXXXX.`. The work order has one `MESWorkOrderOperation` per source routing operation (verify count matches `Routing.operations.count()`). |  |  |
| TC-CREATE-02 | Re-dispatch same PO is idempotent | TC-CREATE-01 just succeeded | 1. Click **Dispatch to Shop Floor** on the same PPS order again | — | Redirect to the SAME work order detail page (no duplicate created). Toast still says dispatched, but no new `MESWorkOrderOperation` rows appeared. |  |  |
| TC-CREATE-03 | Dispatch fails when PO has no routing | Logged in as `admin_acme`. Find a PPS production order in `released` status with `routing=None` (or temporarily clear the routing) | 1. Click **Dispatch to Shop Floor** | — | Red error toast: `Dispatch failed: ...`. No work order created. |  |  |
| TC-CREATE-04 | Dispatch is blocked when PO is not released | Logged in as `admin_acme`. Open a PPS PO in `planned` status | 1. Look for the **Dispatch to Shop Floor** button | — | Button is NOT rendered ([templates/pps/orders/detail.html:24-29](templates/pps/orders/detail.html#L24-L29) — only shown under `status == 'released'`) |  |  |
| TC-CREATE-05 | Create operator profile (happy path) | Logged in as `admin_acme` | 1. Open `/mes/operators/`<br>2. Click **+ New Operator**<br>3. Pick a User without an operator profile<br>4. Type `B0099` in **Badge number**<br>5. Pick any active Work Center<br>6. Tick **Is active**<br>7. Click **Save** | User: any tenant user without an operator. Badge: `B0099` | Redirect to `/mes/operators/`. Green toast: `Operator profile created.`. New row visible. |  |  |
| TC-CREATE-06 | Create operator with duplicate badge | A user already has badge `B0001` | 1. Open `/mes/operators/new/`<br>2. Pick a *different* user<br>3. Type `B0001` (existing badge)<br>4. Click **Save** | Badge: `B0001` | Form re-renders with a red error under **Badge number**: `Badge number already issued in this tenant.`. NOT a 500 error. (Lesson L-01) |  |  |
| TC-CREATE-07 | Create operator with duplicate user | A seeded operator already exists for the chosen user | 1. Open `/mes/operators/new/`<br>2. Pick a user that already has an operator profile<br>3. Type `B0123` (unused badge)<br>4. Click **Save** | — | Form re-renders with red error under **User**: `This user already has a shop-floor operator profile.` |  |  |
| TC-CREATE-08 | Create operator with no badge | Logged in as `admin_acme` | 1. Open `/mes/operators/new/`<br>2. Leave **Badge number** blank<br>3. Click **Save** | — | Form re-renders with `This field is required.` under **Badge number** |  |  |
| TC-CREATE-09 | Raise andon alert (happy path) | Logged in as `admin_acme` | 1. Open `/mes/andon/`<br>2. Click **+ Raise Alert**<br>3. Type: `Test surface defect on output`<br>4. Pick severity `High`<br>5. Pick alert type `Quality`<br>6. Pick any work center<br>7. Click **Raise Alert** | Title: `Test surface defect on output` | Redirect to `/mes/andon/<new-pk>/`. Toast: `Andon alert AND-XXXXX raised.`. Status badge shows **Open**. |  |  |
| TC-CREATE-10 | Raise andon alert with type=Other and blank title | Logged in as `admin_acme` | 1. `/mes/andon/new/`<br>2. Pick alert type `Other`<br>3. Leave **Title** blank<br>4. Pick a work center<br>5. Click **Raise Alert** | Title: blank, type: Other | Form re-renders with red error under **Title**: `Title is required when alert type is Other.` ([apps/mes/forms.py:107-110](apps/mes/forms.py#L107-L110)) |  |  |
| TC-CREATE-11 | Create work instruction (happy path) | Logged in as `admin_acme` | 1. Open `/mes/instructions/`<br>2. Click **+ New Instruction**<br>3. Type `Test SOP — Drilling`<br>4. Pick doc type `SOP`<br>5. Pick any routing operation<br>6. Leave product blank<br>7. Click **Save** | Title: `Test SOP — Drilling` | Redirect to detail page. Toast: `Instruction SOP-XXXXX created. Add a version to release it.` |  |  |
| TC-CREATE-12 | Create work instruction with neither routing op nor product | Logged in as `admin_acme` | 1. `/mes/instructions/new/`<br>2. Type a title<br>3. Pick doc type<br>4. Leave routing op AND product blank<br>5. Click **Save** | — | Form re-renders with form-level error: `Link the instruction to a routing operation, a product, or both.` |  |  |
| TC-CREATE-13 | Create work instruction version with valid PDF | An instruction exists | 1. Open the instruction detail page<br>2. Click **Add Version**<br>3. Type `1.0`<br>4. Type some content<br>5. Upload a small `.pdf` file (any sample PDF)<br>6. Click **Save Draft** | Version: `1.0`, file: any PDF < 25 MB | Redirect to instruction detail. Toast says version added (draft). New version row visible in the **All Versions** table. |  |  |
| TC-CREATE-14 | Reject disallowed file extension | An instruction exists | 1. Add Version → upload a `.exe` file | — | Form error under **Attachment**: `Unsupported file type. Allowed: .pdf .png .jpg .jpeg .mp4 .docx .xlsx .txt.` |  |  |
| TC-CREATE-15 | Reject oversized file (>25 MB) | An instruction exists, have a >25 MB file (e.g. `dd if=/dev/zero of=big.pdf bs=1M count=30` on Linux, or a real large PDF) | 1. Add Version → upload the >25 MB file | — | Form error: `File exceeds the 25 MB limit.` |  |  |
| TC-CREATE-16 | Duplicate version label rejected | An instruction has version `1.0` already | 1. Add Version → version `1.0` again | — | Form error under **Version**: `A version with this label already exists for this instruction.` |  |  |
| TC-CREATE-17 | File a production report (happy path) | A work order has at least one operation | 1. Open `/mes/reports/new/?op=<op-pk>` (use the **Report Quantities** button on the terminal or work-order detail)<br>2. Verify operation pre-selected<br>3. Type `5` in **Good qty**<br>4. Type `1` in **Scrap qty**<br>5. Pick scrap reason `Material Defect`<br>6. Click **Save Report** | good=5, scrap=1, reason=material_defect | Redirect to `/mes/operations/<pk>/`. Toast: `Production report filed.`. The op's **Good qty** and **Scrap qty** denorms increment. The parent work order's **Completed** rollup reflects the new totals. |  |  |
| TC-CREATE-18 | File report with all zeros | An operation pre-selected | 1. `/mes/reports/new/?op=<pk>`<br>2. Leave good/scrap/rework all `0`<br>3. Click **Save Report** | all zeros | Form-level error: `At least one of good / scrap / rework must be greater than zero.` |  |  |
| TC-CREATE-19 | File report with scrap >0 but no reason | An operation pre-selected | 1. `/mes/reports/new/?op=<pk>`<br>2. good=`0`, scrap=`3`, reason=blank<br>3. Click **Save Report** | scrap=3, reason=blank | Field error under **Scrap reason**: `Pick a scrap reason when scrap > 0.` |  |  |

### 4.4 READ — List Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-01 | Work order list loads | Seeded data present | 1. Open `/mes/work-orders/` | — | Table renders with columns: WO#, Product, Qty, Status, Priority, Source PO, Dispatched, Actions. ≥1 row from seed. No `None` literals. |  |  |
| TC-LIST-02 | Work order list — Source PO links to PPS | TC-LIST-01 passes | 1. Click any **Source PO** link (e.g. `PO-00003`) | — | Navigates to `/pps/orders/<pk>/` |  |  |
| TC-LIST-03 | Operator list loads | Seeded operators present | 1. Open `/mes/operators/` | — | Table shows 5 seeded operators (`B0001`–`B0005`) with username + Active badge |  |  |
| TC-LIST-04 | Time-log list loads | Seeded time logs present | 1. Open `/mes/time-logs/` | — | Table shows ≥12 rows with When / Operator / Action / Operation / Notes columns. Newest first. |  |  |
| TC-LIST-05 | Production reports list loads | Seeded reports present | 1. Open `/mes/reports/` | — | Table shows ≥8 rows with all columns populated |  |  |
| TC-LIST-06 | Andon list loads | 4 seeded alerts present | 1. Open `/mes/andon/` | — | 4 rows. Severity badges color-coded (critical=red, high=orange, medium=blue, low=gray). Status badges show Open/Acknowledged/Resolved/Cancelled. Sorted highest-severity first. |  |  |
| TC-LIST-07 | Work instructions list loads | 3 seeded instructions present | 1. Open `/mes/instructions/` | — | 3 rows. **Released** status visible on at least 3 (current_version released by seeder). Doc-type badge shown. |  |  |
| TC-LIST-08 | Empty state on time-logs (filter that returns 0) | TC-LIST-04 passes | 1. `/mes/time-logs/?action=clock_out` and verify if any clock-outs exist; if not, observe empty state | If filter returns 0 | Table shows: `No time logs yet.` text-muted row |  |  |
| TC-LIST-09 | Dashboard KPI cards | Seeded data present | 1. Open `/mes/`<br>2. Inspect 4 KPI cards | — | Open Work Orders, Open Andon, Today's Good Qty, Completed Today all show numeric values (not "None" / blank). Counts match what is visible in the seed output. |  |  |
| TC-LIST-10 | Dashboard recent tables | TC-LIST-09 passes | 1. Inspect "Recent Work Orders" + "Open Andon Alerts" cards | — | Both tables populated with seeded rows. WO# and AND# values link to the corresponding detail pages. |  |  |

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DETAIL-01 | Work order detail (in-progress, with reports) | A seeded WO is in_progress | 1. Open `/mes/work-orders/<pk>/`<br>2. Inspect left card (state) and right column (operations + reports + andon) | — | Status badge `In Progress`. Rollup shows `good / target` ratio + `completed_pct`. Operations table lists every routing op with status. Reports table shows the seeded report rows. Source PO link goes to PPS. |  |  |
| TC-DETAIL-02 | Operation detail (running) | A seeded op is `running` | 1. Click any operation row's **eye** action<br>2. Inspect time logs + reports tables | — | Time logs newest-first; the latest is `Start Job` from a seeded operator. Op status badge says `Running`. |  |  |
| TC-DETAIL-03 | Operator detail | A seeded operator (e.g. `B0001`) | 1. Open `/mes/operators/<pk>/` | — | Profile card shows username, email, default work center. Time-log table populated (only operators with logs will have rows; primary seeded operator does). |  |  |
| TC-DETAIL-04 | Andon detail (resolved) | The `resolved` seeded andon | 1. Open the resolved andon detail | — | Status badge `Resolved`. **Acknowledged** + **Resolved** rows in metadata list show timestamps + actor. Resolution notes block shown. **Resolve** form NOT rendered (status is terminal). |  |  |
| TC-DETAIL-05 | Andon detail (open) shows Acknowledge + Cancel buttons | The `open` seeded andon | 1. Open the open andon detail | — | Top action bar shows **Acknowledge** + **Cancel** buttons. **Resolve** form rendered in right column. |  |  |
| TC-DETAIL-06 | Work instruction detail with current version | A released instruction | 1. Open `/mes/instructions/<pk>/` | — | "Current version" card shows v1.0 with status badge **Released**. Versions table shows all versions. **Acknowledge** form on right column. |  |  |
| TC-DETAIL-07 | Work instruction detail with no released version | An instruction with only a draft | 1. Create a new instruction (TC-CREATE-11)<br>2. Skip releasing the new version<br>3. Open the detail page | — | Yellow warning banner: `No released version yet — add a version and release it.` Acknowledge form NOT rendered. |  |  |
| TC-DETAIL-08 | Production report detail | A seeded report | 1. Open `/mes/reports/<pk>/` | — | All fields rendered, including Cycle time, Notes, Reported by/at. Delete button visible. |  |  |

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit work order priority | A work order is `dispatched` or `on_hold` | 1. Open WO detail<br>2. Click **Edit**<br>3. Change priority to `Rush`<br>4. Click **Save** | priority: rush | Redirect to detail. Toast: `Work order updated.`. Priority badge now `Rush`. |  |  |
| TC-EDIT-02 | Edit work order is blocked when in_progress | A WO is in_progress | 1. Open WO detail | — | **Edit** button NOT shown ([templates/mes/work_orders/detail.html](templates/mes/work_orders/detail.html) — gated on `wo.is_editable`). Manually visit `/mes/work-orders/<pk>/edit/` → redirect with warning toast. |  |  |
| TC-EDIT-03 | Edit operator | Any operator | 1. Open operator detail<br>2. Click **Edit**<br>3. Change badge from `B0001` to `B9001`<br>4. Click **Save** | badge: B9001 | Redirect with toast `Operator profile updated.`. List page now shows `B9001`. |  |  |
| TC-EDIT-04 | Edit andon alert | An open or acknowledged andon | 1. Open andon detail<br>2. Click **Edit**<br>3. Change severity to `Critical`<br>4. Click **Save** | severity: critical | Redirect with toast. Severity badge updated. |  |  |
| TC-EDIT-05 | Edit andon is blocked once resolved | The `resolved` seeded andon | 1. Open andon detail | — | **Edit** button NOT shown. URL hit `/mes/andon/<pk>/edit/` → redirect with warning. |  |  |
| TC-EDIT-06 | Edit instruction | Any instruction | 1. Open instruction detail<br>2. Click **Edit**<br>3. Change title<br>4. Click **Save** | new title | Redirect to detail with toast `Instruction updated.`. |  |  |

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete confirm dialog appears | Any deletable WO | 1. From `/mes/work-orders/`, click the bin icon | — | Browser confirm dialog appears. Cancel → no change. |  |  |
| TC-DELETE-02 | Delete work order (dispatched) | A `dispatched` WO | 1. Click bin icon → **OK**<br>2. Observe redirect | — | Redirect to `/mes/work-orders/`. Toast `Work order deleted.`. Row gone. The PPS production order parent is unaffected. |  |  |
| TC-DELETE-03 | Delete work order is blocked when in_progress | An in_progress WO | 1. From WO list, observe Actions column<br>2. Manually POST to `/mes/work-orders/<pk>/delete/` (use form on dispatched WO whose action URL has been swapped via DevTools) | — | List shows no bin icon (Actions column omits it for in_progress WOs). The forged POST returns redirect to detail with red toast `In-progress work orders cannot be deleted - cancel first.` |  |  |
| TC-DELETE-04 | Delete operator that has time logs | An operator with logs | 1. Click bin icon on `B0001` | — | Toast: `Cannot delete - operator has time-log history.` (PROTECT FK to OperatorTimeLog) |  |  |
| TC-DELETE-05 | Delete operator without logs | A freshly-created operator (TC-CREATE-05) | 1. Click bin icon → **OK** | — | Toast `Operator deleted.`. Row gone. |  |  |
| TC-DELETE-06 | Delete production report adjusts denorms | A seeded report on an in-progress op | 1. Note the parent op's `total_good_qty` BEFORE delete (visit op detail)<br>2. Open `/mes/reports/<pk>/`<br>3. Click **Delete** → **OK**<br>4. Re-open the op detail | — | The op's `total_good_qty` decreased by exactly the deleted report's `good_qty`. The parent work order's `quantity_completed` also adjusted. |  |  |
| TC-DELETE-07 | Delete instruction cascades versions | The created instruction from TC-CREATE-11 | 1. Add a version (TC-CREATE-13)<br>2. From list, click bin icon on the instruction → **OK** | — | Instruction + its versions are deleted. Acknowledgements (if any) remain (no FK PROTECT — they cascade because of the FK on `WorkInstructionAcknowledgement.instruction`). |  |  |
| TC-DELETE-08 | Delete andon | Any andon | 1. Bin icon on andon list → **OK** | — | Toast `Andon alert deleted.` Row gone. |  |  |

### 4.8 SEARCH

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-SEARCH-01 | Empty search returns all | `/mes/work-orders/` open | 1. Submit empty `q=` | q: empty | All seeded WOs visible |  |  |
| TC-SEARCH-02 | Single-char search | WO list | 1. Type `W` in search → submit | q: `W` | Matches every `WO-`-prefixed row (case-insensitive substring) |  |  |
| TC-SEARCH-03 | Search by exact WO number | WO list, know one wo_number | 1. Type the full `WO-00001` (or whatever exists) → submit | q: `WO-00001` | Exactly that row, no others |  |  |
| TC-SEARCH-04 | Search by SKU substring | WO list | 1. Type a partial SKU (e.g. `SKU-4`) → submit | q: `SKU-4` | All WOs whose product SKU contains `SKU-4` |  |  |
| TC-SEARCH-05 | Search by source PO number | WO list | 1. Type `PO-00001` → submit | q: `PO-00001` | The matching WO appears (the search field includes `production_order__order_number__icontains`) |  |  |
| TC-SEARCH-06 | Search trims whitespace | WO list | 1. Type `   WO   ` (with leading/trailing spaces) → submit | q: `   WO   ` | Same results as `WO` (view calls `.strip()` ([apps/mes/views.py:130](apps/mes/views.py#L130))) |  |  |
| TC-SEARCH-07 | No-match shows empty state | WO list | 1. Type `ZZZZZ_NOMATCH_99` → submit | q: nonsense | Table empty: `No work orders yet - dispatch one from a released production order.` |  |  |
| TC-SEARCH-08 | XSS-safe search | WO list | 1. Paste `<script>alert(1)</script>` into search → submit | q: `<script>alert(1)</script>` | No JS alert. Empty table. URL has the literal escaped string. |  |  |
| TC-SEARCH-09 | SQL-special chars don't 500 | WO list | 1. Type `'; drop table mes_mesworkorder; --` → submit | q: malicious | No 500. Empty result table. |  |  |
| TC-SEARCH-10 | Search retained across pagination | WO list. Add ≥21 WOs (use admin or temporarily lower paginate_by) OR test on whichever module has >20 records | 1. `/mes/andon/?q=alert` (when there are enough) → click **2** in pagination | — | `?q=alert&page=2` URL retained, results still filtered |  |  |
| TC-SEARCH-11 | Andon search across title + message | Andon list | 1. Type `defect` (matches a seeded message text) | q: `defect` | Matching alert(s) shown |  |  |
| TC-SEARCH-12 | Instructions search by title | Instructions list | 1. Type `Inspection` (matches "Quality Inspection Checklist") | q: `Inspection` | The matching instruction shown |  |  |
| TC-SEARCH-13 | Reports search by SKU substring | Reports list | 1. Type a partial SKU | q: SKU-4 | Reports whose op's parent product matches |  |  |

### 4.9 PAGINATION

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-PAGE-01 | WO list default page size | WO list with seeded 6 rows | 1. Open `/mes/work-orders/`<br>2. Note pagination | — | Single page (≤20 rows). No page links. |  |  |
| TC-PAGE-02 | Time-log list pagination triggers when >30 rows | Run `seed_mes` 2-3× without flush, OR manually clock-in/out a few times | 1. Open `/mes/time-logs/` | — | Pagination renders with `1 / N` indicator and `«` `»` buttons |  |  |
| TC-PAGE-03 | Click page 2 retains filters | Time-log list with multiple pages, filter applied | 1. `/mes/time-logs/?action=start_job`<br>2. Click `»` | — | URL becomes `/mes/time-logs/?action=start_job&page=2`. Filter preserved (operator + action dropdowns retain selection). |  |  |
| TC-PAGE-04 | Page beyond last → graceful | Time-log list paginated | 1. Manually visit `?page=999` | — | Either empty page rendered or HTTP 404. NEVER a 500. |  |  |
| TC-PAGE-05 | Invalid page param → graceful | Any paginated list | 1. Manually visit `?page=abc` | — | Default page 1 shown OR 404. NEVER 500. |  |  |

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-FILTER-01 | WO filter by status `in_progress` | WO list with status spread | 1. Pick `In Progress` in status dropdown<br>2. Click **Filter** | — | Only in-progress rows shown. Dropdown retains `In Progress`. URL has `?status=in_progress`. |  |  |
| TC-FILTER-02 | WO filter by priority `Rush` | WO list | 1. Pick `Rush` priority<br>2. Filter | — | Only rush WOs (may be empty if seeder didn't seed any rush — verify) |  |  |
| TC-FILTER-03 | WO combined filter | WO list | 1. status=`In Progress` + priority=`Normal`<br>2. Filter | — | AND-applied. Both selections retained in dropdowns. |  |  |
| TC-FILTER-04 | WO filter cleared | WO list | 1. Apply status filter → Filter<br>2. Manually remove `?status=...` from URL | — | All rows back |  |  |
| TC-FILTER-05 | Operator active filter | Operator list | 1. Pick `Active` → Filter | — | All seeded operators (active=True) shown. |  |  |
| TC-FILTER-06 | Operator inactive filter | Mark one operator inactive via Edit | 1. Pick `Inactive` → Filter | — | Only the deactivated operator shown |  |  |
| TC-FILTER-07 | Time-log operator filter | Time-log list | 1. Pick a specific operator → Filter | operator: B0001 | Only logs from that operator |  |  |
| TC-FILTER-08 | Time-log action filter | Time-log list | 1. Pick `Start Job` → Filter | action: start_job | Only `start_job` rows |  |  |
| TC-FILTER-09 | Reports scrap_reason filter | Reports list | 1. Pick `Material Defect` → Filter | scrap_reason: material_defect | Only reports with that reason |  |  |
| TC-FILTER-10 | Andon type filter | Andon list | 1. Pick `Quality` → Filter | alert_type: quality | Only quality alerts (1 of 4 seeded). |  |  |
| TC-FILTER-11 | Andon severity filter | Andon list | 1. Pick `Critical` → Filter | severity: critical | Only the 1 critical seeded alert |  |  |
| TC-FILTER-12 | Andon status filter | Andon list | 1. Pick `Open` → Filter | status: open | Only the open seeded alert |  |  |
| TC-FILTER-13 | Andon combined filters | Andon list | 1. status=`Resolved` + alert_type=`Equipment` + severity=`Critical` → Filter | — | Exactly the 1 row that matches all 3 (per seed fixture row #3). All 3 dropdowns retain selection. |  |  |
| TC-FILTER-14 | Instructions doc_type filter | Instructions list | 1. Pick `Quality Check` → Filter | doc_type: quality_check | Only quality_check instructions |  |  |
| TC-FILTER-15 | Instructions status filter | Instructions list | 1. Pick `Released` → Filter | status: released | All 3 seeded instructions (each had its first version released) |  |  |
| TC-FILTER-16 | Instructions product filter | Instructions list | 1. Pick a product → Filter | product: pk | Only instructions with that product FK |  |  |
| TC-FILTER-17 | Filter by value with zero records | Andon list | 1. Pick severity=`Low` AND status=`Open` (no match in seed) → Filter | — | Empty table with `No alerts.` empty state. No 500. |  |  |
| TC-FILTER-18 | Filter `?status=invalid` ignored cleanly | WO list | 1. Manually visit `/mes/work-orders/?status=zzz_invalid` | — | All rows shown OR empty list — never a 500. (Django ORM rejects unknown choice values silently.) |  |  |

### 4.11 Status Transitions / Custom Actions

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-01 | Start a dispatched work order | A WO in `dispatched` | 1. Open WO detail<br>2. Click **Start** → confirm | — | Status badge flips to `In Progress`. Toast `Work order started.` |  |  |
| TC-ACTION-02 | Hold an in-progress work order | A WO in `in_progress` | 1. Click **Hold** | — | Status `On Hold`. Toast `Work order placed on hold.` |  |  |
| TC-ACTION-03 | Resume from hold (start) | A WO in `on_hold` | 1. Click **Start** → confirm | — | Status `In Progress` |  |  |
| TC-ACTION-04 | Complete in-progress WO | A WO in `in_progress` | 1. Click **Complete** → confirm | — | Status `Completed`. `completed_at` and `completed_by` populated. |  |  |
| TC-ACTION-05 | Cancel a dispatched WO | A WO in `dispatched` (admin) | 1. Click **Cancel** → confirm | — | Status `Cancelled`. Edit/Start actions disappear. |  |  |
| TC-ACTION-06 | Op start records a time log | An op in `pending` (current user has operator profile) | 1. Open op detail<br>2. Click **Start** | — | New `start_job` row appears in **Recent Time Logs** table. Op status `Running`. Parent WO auto-promoted to `In Progress` if it was `Dispatched`. |  |  |
| TC-ACTION-07 | Op pause + resume cycle | Op currently `Running` | 1. Click **Pause** → toast<br>2. Click **Resume** → toast | — | Time logs show `pause_job` then `resume_job`. `actual_minutes` increments only during running intervals. |  |  |
| TC-ACTION-08 | Op stop completes the op + auto-completes WO | An op `running` and the LAST remaining open op of its parent WO | 1. Click **Stop** → confirm | — | Op status `Completed`. Parent WO status auto-flips to `Completed` (services/time_logging logic). Toast confirms. |  |  |
| TC-ACTION-09 | Op start without operator profile | Logged-in user has NO `ShopFloorOperator` row | 1. Click op **Start** | — | Red toast: `You need a shop-floor operator profile to start jobs.` |  |  |
| TC-ACTION-10 | Andon acknowledge | An open andon | 1. Click **Acknowledge** | — | Status flips `Acknowledged`. `acknowledged_at` + `acknowledged_by` populated. Edit + Cancel still visible; Acknowledge button gone. |  |  |
| TC-ACTION-11 | Andon resolve with notes | An open or acknowledged andon | 1. Type `Replaced cutting tool` in resolution notes<br>2. Click **Mark Resolved** | notes: provided | Status `Resolved`. Resolution-notes block visible on detail. |  |  |
| TC-ACTION-12 | Andon resolve with empty notes | An open andon | 1. Click **Mark Resolved** with notes blank | notes: blank | Red toast: `Please add a resolution note.` Status NOT changed. |  |  |
| TC-ACTION-13 | Andon cancel | An open andon (admin) | 1. Click **Cancel** → confirm | — | Status `Cancelled`. |  |  |
| TC-ACTION-14 | Release work-instruction version | An instruction with a draft version | 1. Click **Release** on the draft row | — | Status `Released`. Any prior released version flips to `Obsolete`. Instruction's `current_version` updates. |  |  |
| TC-ACTION-15 | Release supersedes prior released | An instruction with one released v1.0 + a draft v1.1 | 1. Click **Release** on v1.1 | — | v1.1 = Released. v1.0 auto-flips to Obsolete. |  |  |
| TC-ACTION-16 | Obsolete a released version | Any released version | 1. Click **Obsolete** → confirm | — | Status `Obsolete`. If it was the `current_version`, instruction status flips to `Obsolete` and `current_version` is cleared. |  |  |
| TC-ACTION-17 | Acknowledge work instruction with typed signature | An instruction with a released version + ack form rendered | 1. Type the user's full name in **Signature text**<br>2. Click **Acknowledge vX.Y** | signature: `Test User` | Toast: `Acknowledgement recorded.` Detail page now shows green "You acknowledged vX.Y on ..." banner. Form replaced. |  |  |
| TC-ACTION-18 | Acknowledge with blank signature | Instruction with released version | 1. Click **Acknowledge** with blank signature | — | Form renders error / toast: `Type your name to confirm acknowledgement.` |  |  |
| TC-ACTION-19 | Duplicate acknowledgement is idempotent | Instruction + version already acked by current user | 1. (Manually re-POST to `/mes/instructions/<pk>/ack/` via DevTools, the UI hides the form once acked) | — | Info toast: `You have already acknowledged this version.` No duplicate row. |  |  |
| TC-ACTION-20 | Auth-gated download succeeds | A version with an attachment | 1. Click **Download attachment** on the current-version card | — | Browser downloads the file (PDF / image / etc). |  |  |
| TC-ACTION-21 | Cross-tenant download blocked | TC-TENANT-04 | — | — | 404 |  |  |
| TC-ACTION-22 | Operator clock-in toggles state | Logged in user with operator profile | 1. `/mes/terminal/`<br>2. Click **Clock In** | — | Banner flips to `Clocked In` (green). Time-log row added with `clock_in`. |  |  |
| TC-ACTION-23 | Operator clock-out toggles state | Just clocked in | 1. Click **Clock Out** | — | Banner flips to `Clocked Out` (gray). `clock_out` log row added. |  |  |

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-UI-01 | Browser tab title is descriptive | Open each MES page | 1. `/mes/` → `/mes/work-orders/` → `/mes/terminal/` → `/mes/operators/` → `/mes/andon/` | — | Tab titles show "Shop Floor Dashboard", "Work Orders", "Operator Terminal", "Operators", "Andon Alerts" — not generic "MES" or blank |  |  |
| TC-UI-02 | Sidebar Shop Floor group expands | Logged in | 1. Click sidebar group header `Shop Floor (MES)` | — | Group expands showing 8 child links (Dashboard, Terminal, Work Orders, Operators, Time Logs, Production Reports, Andon Alerts, Work Instructions) |  |  |
| TC-UI-03 | Sidebar active-link state | On `/mes/work-orders/` | 1. Inspect sidebar | — | The "Work Orders" sub-link has the active visual state (color / background) |  |  |
| TC-UI-04 | Status badges color-coded correctly | WO list with mixed statuses | 1. Inspect badge colors | — | Completed=green, In Progress=yellow, On Hold=gray, Dispatched=info-blue, Cancelled=secondary |  |  |
| TC-UI-05 | Severity badges color-coded | Andon list | 1. Inspect | — | critical=red, high=orange, medium=blue, low=gray |  |  |
| TC-UI-06 | Empty state on dashboard | New tenant with no MES data (e.g. flush only the andon table or visit `admin_stark` if no data) | 1. Open `/mes/` | — | KPI cards show `0`. Recent tables show empty-state messages. |  |  |
| TC-UI-07 | Toasts auto-dismiss | Trigger any toast (e.g. delete a row) | 1. Watch the toast | — | Toast disappears after a few seconds (Bootstrap default ≈5s) or on click |  |  |
| TC-UI-08 | Confirm dialog names the action | Click **Delete** in WO list | 1. Read dialog text | — | Dialog reads `Delete this work order?` (or similar — context-specific). Cancel returns no-op. |  |  |
| TC-UI-09 | Form errors red and per-field | TC-CREATE-06 (duplicate badge) | 1. Inspect error placement | — | Error text in red, sits directly under the **Badge number** field (crispy_forms layout). |  |  |
| TC-UI-10 | Required-field markers shown | Open `/mes/operators/new/` | 1. Inspect labels | — | Required fields have `*` (crispy_forms convention) |  |  |
| TC-UI-11 | Long text wraps cleanly | Long product names / long andon titles | 1. Resize the WO table to narrow viewport | — | Cells wrap; no horizontal scroll on the table beyond intentional `table-responsive` scroll |  |  |
| TC-UI-12 | Mobile viewport (375×667) terminal usable | Chrome DevTools iPhone SE | 1. Open `/mes/terminal/`<br>2. Inspect cards | — | Each open-op card stacks vertically. Big buttons remain readable + tappable. No content offscreen. |  |  |
| TC-UI-13 | Mobile viewport WO list usable | Same | 1. Open `/mes/work-orders/` on mobile | — | Table is horizontally scrollable (`table-responsive`). Filter form stacks. |  |  |
| TC-UI-14 | Tablet viewport (768×1024) | Chrome DevTools iPad | 1. Tour MES pages | — | Layout fits — sidebar collapsible, content readable, tables not clipped |  |  |
| TC-UI-15 | Keyboard tab order on andon form | `/mes/andon/new/` | 1. Click **Title** field<br>2. Tab through fields | — | Tab order matches form layout (no jumping back/forth). Each focused element shows a visible focus ring. |  |  |
| TC-UI-16 | Form submits on Enter from last field | Andon form | 1. Fill all fields, focus the last input, press Enter | — | Form submits |  |  |
| TC-UI-17 | DevTools console clean | Tour every MES page | 1. Open DevTools Console<br>2. Visit each MES URL | — | No JS errors logged. Warnings about missing favicons / etc. are acceptable. |  |  |
| TC-UI-18 | Andon severity badge background-subtle on detail | Andon detail | 1. Inspect status block | — | Severity badge uses Bootstrap `bg-{severity}-subtle` class (verified [templates/mes/andon/detail.html](templates/mes/andon/detail.html)) |  |  |
| TC-UI-19 | Production-report list shows `-` for blank scrap reason | Reports list | 1. Inspect rows where good=N, scrap=0 | — | Scrap reason cell renders `-`, not `None` |  |  |
| TC-UI-20 | Terminal "no jobs" empty state | Operator with no open ops | 1. Mark all that operator's ops `completed`<br>2. Open terminal | — | Empty state card with success icon + message: `No open jobs assigned to your work center...` |  |  |

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-NEG-01 | Submit operator form fully blank | Logged in as admin | 1. `/mes/operators/new/`<br>2. Submit empty | — | Errors under **User**, **Badge number**. No 500. |  |  |
| TC-NEG-02 | Decimal field with letters | Production report form | 1. `/mes/reports/new/?op=<pk>`<br>2. Type `abc` in **Good qty** | — | Browser-level error or form re-renders with error under **Good qty** |  |  |
| TC-NEG-03 | Negative qty rejected | Report form | 1. Type `-5` in **Good qty** | good=-5 | Form error: validators reject (`MinValueValidator(0)` — model-level) |  |  |
| TC-NEG-04 | Bad badge collision in same form | Two staff create operators concurrently | 1. Open two browser tabs at `/mes/operators/new/`<br>2. Pick same badge `B0500` in both<br>3. Submit one, then the other | — | First succeeds. Second rejected with `Badge number already issued in this tenant.` (form clean uses `ShopFloorOperator.all_objects.filter(...)`). NOT a 500. |  |  |
| TC-NEG-05 | Double-submit dispatch | A released PPS order | 1. Open the PPS order detail<br>2. Click **Dispatch to Shop Floor** twice rapidly | — | Only one MESWorkOrder created (idempotent service — see TC-CREATE-02). Second click returns the same WO. |  |  |
| TC-NEG-06 | Browser back after create | Just created an instruction | 1. Click browser **Back** to the form<br>2. Browser shows "resubmit form" prompt → cancel | — | No second instruction created |  |  |
| TC-NEG-07 | Unicode in andon title | Andon form | 1. Title: `Líne défect — émergency 🚨` | unicode + emoji | Saves successfully. Detail page shows the literal string, escaped properly (no JS exec). |  |  |
| TC-NEG-08 | Cross-tenant op start blocked | Logged in as Acme operator, know Globex op pk | 1. Manually POST `/mes/operations/<globex-pk>/start/` via DevTools form | — | 404 |  |  |
| TC-NEG-09 | Op stop without operator profile | Logged in as `admin_acme` (NO operator profile) | 1. `/mes/operations/<pk>/stop/` POST | — | Red toast `You need a shop-floor operator profile to stop jobs.` Status unchanged. |  |  |
| TC-NEG-10 | Filter `?page=99999` on time logs | Time-log list | 1. Visit `?page=99999` | — | 404 (Django paginator). Not 500. |  |  |
| TC-NEG-11 | Race: two reviewers acknowledge same andon | Two browsers logged in as admin_acme | 1. Both load the same open andon detail<br>2. Both click **Acknowledge** simultaneously | — | First wins (atomic UPDATE). Second sees yellow toast `Only open alerts can be acknowledged.` No 500. |  |  |
| TC-NEG-12 | Edit andon while it has been resolved by another user | Two browsers | 1. Browser A: open the open andon edit form<br>2. Browser B: resolve the same andon<br>3. Browser A: submit the edit | — | Browser A is redirected with warning `Andon alert can only be edited while open.` (status check on POST) |  |  |
| TC-NEG-13 | XSS in instruction content | Instruction version form | 1. Content: `<img src=x onerror=alert(1)>` | xss attempt | Detail page renders the literal text — no JS executed (Django auto-escape) |  |  |
| TC-NEG-14 | XSS in scrap notes | Report form | 1. Notes: `<script>alert(1)</script>` | xss attempt | Detail page renders escaped, no JS exec |  |  |
| TC-NEG-15 | CSRF protection on every POST | DevTools | 1. Inspect any POST form (Delete, Start, Acknowledge, etc.) | — | Each form contains `<input type="hidden" name="csrfmiddlewaretoken" ...>`. Manually crafting a POST without the token returns 403. |  |  |
| TC-NEG-16 | Date-of-creation server-side stamp | Create an andon | 1. Note `Raised at` on detail page | — | Reflects the server's current time in tenant TZ; never blank |  |  |

### 4.14 Cross-Module Integration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-INT-01 | Dispatch button visibility on PPS PO | A PPS PO in `released` | 1. Open PPS order detail | — | The **Dispatch to Shop Floor** button is rendered (info-colored) next to **Start** ([templates/pps/orders/detail.html:24-29](templates/pps/orders/detail.html#L24-L29)) |  |  |
| TC-INT-02 | Dispatch button hidden on planned PO | A PPS PO in `planned` | 1. Open PPS order detail | — | Button NOT rendered |  |  |
| TC-INT-03 | Dispatch links back to source PPS order | After TC-CREATE-01 | 1. On the new MES WO detail, click the **Source PO** link | — | Navigates to `/pps/orders/<pk>/` |  |  |
| TC-INT-04 | Work order ops mirror source routing operations | TC-CREATE-01 | 1. Open the dispatched WO<br>2. Compare op count + names to the routing on the PPS order | — | Same number of operations, same names + sequences. Each `MESWorkOrderOperation.routing_operation` FK points at the corresponding `pps.RoutingOperation`. |  |  |
| TC-INT-05 | Work-instruction routing-op link to PPS routing | Open a seeded instruction with a routing-op FK | 1. On detail page, click the routing-op link | — | Navigates to `/pps/routings/<pk>/` |  |  |
| TC-INT-06 | Work-instruction product link to PLM | An instruction with a product FK | 1. Click the product link on detail | — | Navigates to `/plm/products/<pk>/` |  |  |
| TC-INT-07 | Andon work-center link to PPS | Any andon | 1. Click the work-center code link | — | Navigates to `/pps/work-centers/<pk>/` |  |  |
| TC-INT-08 | WO operation work-center link to PPS | Any WO operation | 1. Click the work-center code link in the operations table | — | Navigates to `/pps/work-centers/<pk>/` |  |  |
| TC-INT-09 | Audit log entries written | Trigger TC-ACTION-01 (start a WO) | 1. After triggering, log in as the same admin and open `/tenants/audit-log/` | — | A row exists with action `mes_work_order.in_progress`, target_type `MESWorkOrder`, meta `{"from": "dispatched", "to": "in_progress"}` ([apps/mes/signals.py:53-67](apps/mes/signals.py#L53-L67)) |  |  |
| TC-INT-10 | Audit log on andon resolve | Trigger TC-ACTION-11 | 1. After triggering, open audit log | — | Row with action `andon.resolved` |  |  |
| TC-INT-11 | Audit log on instruction release | Trigger TC-ACTION-14 | 1. After triggering, open audit log | — | Row with action `work_instruction.released` |  |  |

---

## 5. Bug Log

> Tester adds rows here as defects are found. Severity guide: **Critical** = data loss / 500 / security; **High** = blocks workflow; **Medium** = wrong behavior with workaround; **Low** = polish; **Cosmetic** = minor visual.

> **2026-04-29 walk-through results (static code review + pytest):** 6 defects surfaced and fixed. Each is locked in by a regression in [apps/mes/tests/test_seeder.py](../../apps/mes/tests/test_seeder.py). All 142 MES tests + 109 cross-module tests pass.

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Fix | Status |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | (seed setup) | Medium | `python manage.py seed_mes` | Run the seeder on a Windows PowerShell console | ASCII-only stdout per Lesson L-09 | Unicode `·` (U+00B7) at [`seed_mes.py:240`](../../apps/mes/management/commands/seed_mes.py#L240) crashed the seeder mid-tenant on cp1252 consoles | Replaced `·` with ` - ` | **Fixed** |
| BUG-02 | TC-DETAIL-01 (completed WO) | High | `/mes/work-orders/<pk>/` | Run `seed_mes`, log in as `admin_acme`, open the completed WO detail | `quantity_completed` should equal `quantity_to_build` (matches the seeded production report) | `quantity_completed = 0` because [`seed_mes.py:235`](../../apps/mes/management/commands/seed_mes.py#L235) read `first_op.total_good_qty` from a stale Python variable BEFORE the `.update()` flushed the new value to DB | Refactored seeder to use one local variable for the value and write it consistently to report + op denorm + WO rollup | **Fixed** |
| BUG-03 | TC-DETAIL-02 (in-progress op) | High | `/mes/operations/<pk>/` | Run `seed_mes`, open the running op | The op's `total_good_qty` should match the report's `good_qty` (5) | Op showed `total_good_qty=0` while the seeded `ProductionReport` said `good_qty=5` — internally inconsistent | Same refactor as BUG-02 — explicit `good_qty` / `scrap_qty` locals shared between op denorm + report row | **Fixed** |
| BUG-04 | (seed corner case) | Low | seed runtime | Run `seed_mes` against a PPS PO that is in `in_progress` and has `routing=None` | Seeder restores the original PO status after the dispatch attempt | The `if po.routing_id is None: continue` branch at [`seed_mes.py:111-113`](../../apps/mes/management/commands/seed_mes.py#L111-L113) skipped the restore — the PO would be left as `released` | Added `if original_status != 'released': ProductionOrder.all_objects.filter(...).update(status=original_status)` to the early-continue branch | **Fixed** |
| BUG-05 | TC-ACTION-12 | Medium | `/mes/andon/<pk>/resolve/` | Open an open andon → click **Mark Resolved** with blank notes | Form-level error: `A resolution note is required when resolving an alert.`; status NOT changed | View accepted blank notes and flipped the andon to `resolved`. Root cause: `resolution_notes` is `TextField(blank=True)` on the model; ModelForm inherited that, so empty input was valid | Added explicit `clean_resolution_notes` on `AndonResolveForm` ([`apps/mes/forms.py:118-126`](../../apps/mes/forms.py#L118-L126)) | **Fixed** |
| BUG-06 | TC-ACTION-19 | Medium (test-only manifestation, latent in prod) | `/mes/instructions/<pk>/ack/` | POST a duplicate acknowledgement; in pytest, downstream queries crash with `TransactionManagementError` | Idempotent: second POST shows an info toast, no second row created, no transaction breakage | Without a savepoint, the `IntegrityError` poisoned the surrounding transaction (visible only under `ATOMIC_REQUESTS=True` or pytest atomic-wrap) | Wrapped the `WorkInstructionAcknowledgement.objects.create(...)` call in `with transaction.atomic():` so the unique-constraint failure stays inside an inner savepoint ([`apps/mes/views.py:541-554`](../../apps/mes/views.py#L541-L554)) | **Fixed** |

---

## 6. Sign-off & Release Recommendation

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---|---|---|---|---|
| 4.1 Authentication & Access | 7 |  |  |  |  |
| 4.2 Multi-Tenancy Isolation | 5 |  |  |  |  |
| 4.3 CREATE | 19 |  |  |  |  |
| 4.4 READ — List Page | 10 |  |  |  |  |
| 4.5 READ — Detail Page | 8 |  |  |  |  |
| 4.6 UPDATE | 6 |  |  |  |  |
| 4.7 DELETE | 8 |  |  |  |  |
| 4.8 SEARCH | 13 |  |  |  |  |
| 4.9 PAGINATION | 5 |  |  |  |  |
| 4.10 FILTERS | 18 |  |  |  |  |
| 4.11 Status Transitions / Custom Actions | 23 |  |  |  |  |
| 4.12 Frontend UI / UX | 20 |  |  |  |  |
| 4.13 Negative & Edge Cases | 16 |  |  |  |  |
| 4.14 Cross-Module Integration | 11 |  |  |  |  |
| **Total** | **169** |  |  |  |  |

**Release Recommendation:** ☐ GO &nbsp; ☐ NO-GO &nbsp; ☐ GO-with-fixes

Rationale (one sentence):

___________________________________________________________________________

**Tester:** _________________ **Date:** _________________ **Build:** _________________
