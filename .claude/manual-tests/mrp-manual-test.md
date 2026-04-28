# Material Requirements Planning (MRP) — Manual Test Plan

**Module:** Module 5 — Material Requirements Planning ([apps/mrp/](apps/mrp/))
**Tester role:** Senior manual QA — execute step-by-step in a browser
**Persona this is written for:** A non-developer tester (or the project owner) clicking through the live app.
**Latest companion automation report:** [.claude/reviews/mrp-sqa-review.md](.claude/reviews/mrp-sqa-review.md)
**Date:** 2026-04-29

---

## 1. Scope & Objectives

### 1.1 In scope

| Sub-module | Pages covered |
|---|---|
| 5.1 Demand Forecasting | Forecast Models (CRUD + Run), Seasonality Profiles (CRUD), Forecast Runs (list / detail / delete) |
| 5.2 Net Requirements | Inventory Snapshots (CRUD), Scheduled Receipts (CRUD), MRP Calculations (list / detail / delete) |
| 5.3 PR Auto-Generation | Purchase Requisitions (list / detail / edit / approve / cancel / delete) |
| 5.4 Exception Management | Exceptions (list / detail / acknowledge / resolve / ignore / delete) |
| 5.5 MRP Run & Simulation | Runs (CRUD + Start / Apply / Discard) |

### 1.2 Out of scope

- Module 8 Inventory aggregation (uses `InventorySnapshot` placeholder)
- Module 9 Procurement PR-to-PO conversion (PRs stay in `draft` / `approved` / `cancelled`)
- Module 17 Sales-driven forecast history (run uses synthetic history)
- Background workers (MRP runs are synchronous within the request)

### 1.3 Pass criteria

- All TC-AUTH / TC-TENANT / CRUD / SEARCH / PAGINATION / FILTER cases pass on the primary browser.
- No 500 errors during any step (front-end shows validation; the run row captures engine errors).
- All status-gated buttons hide/show correctly.
- All workflow mutations (Approve, Apply, Resolve, Ignore, Discard) reject non-admin POSTs.

---

## 2. Pre-Test Setup

> Run these once at the start of a test session. PowerShell on Windows.

| # | Action | Command / URL | Expected |
|---|---|---|---|
| S-01 | Activate venv (if used) | `.\venv\Scripts\Activate.ps1` | Prompt prefix shows `(venv)` |
| S-02 | Run migrations | `python manage.py migrate` | "No migrations to apply" or applied list ending in `mrp.0002_mrprun_protect_calculation` |
| S-03 | Seed prerequisites in order | `python manage.py seed_plm; python manage.py seed_bom; python manage.py seed_pps; python manage.py seed_mrp` | Each command ends "complete." with no tracebacks |
| S-04 | Start dev server | `python manage.py runserver` | "Starting development server at http://127.0.0.1:8000/" |
| S-05 | Open Chrome | navigate to `http://127.0.0.1:8000/` | App login page renders |
| S-06 | Log in as **tenant admin** (NOT superuser) | username `admin_acme` · password `Welcome@123` | Redirect to dashboard; sidebar shows Acme branding |
| S-07 | Open the MRP module | `http://127.0.0.1:8000/mrp/` | Index dashboard with KPI cards (Open Runs, Open Exceptions, etc.) |

**Critical reminders:**

- **Do NOT log in as `admin` (the Django superuser).** Superuser has `tenant=None` and every MRP list will be empty by design. The `admin_acme` account is the seeded Tenant Admin for the Acme tenant.
- Other seeded tenant admins: `admin_globex`, `admin_stark` — same password.
- A non-admin staff user is needed for the RBAC tests in §4.1 / §4.11. If one isn't seeded, create one via Django admin OR via the Users page at `/users/` after logging in as the tenant admin.
- The seeder is idempotent — re-running `seed_mrp` is safe. Use `python manage.py seed_mrp --flush` only when you want to re-seed from scratch (Acme / Globex / Stark only).

### 2.1 Browser / viewport matrix

| Browser | Viewport | Priority |
|---|---|---|
| Chrome (latest) | 1920 × 1080 | **Primary** |
| Edge (latest) | 1920 × 1080 | Secondary |
| Chrome | 768 × 1024 (iPad portrait) | Secondary |
| Chrome | 375 × 667 (iPhone SE) | Secondary |

Run all sections on Chrome desktop first. Run §4.12 (UI/UX) on every viewport.

### 2.2 Reset between runs

- After workflow tests (Approve PRs, Apply runs), re-run `python manage.py seed_mrp --flush` to reset to a clean state.
- For PR / Exception delete tests on resolved/ignored items, re-run `seed_mrp --flush`.

---

## 3. Test Surface Inventory

### 3.1 URL routes (from [apps/mrp/urls.py](apps/mrp/urls.py))

| URL | View | RBAC |
|---|---|---|
| `/mrp/` | `MRPIndexView` | tenant required |
| `/mrp/forecast-models/` | `ForecastModelListView` | tenant required |
| `/mrp/forecast-models/new/` | `ForecastModelCreateView` | tenant required |
| `/mrp/forecast-models/<pk>/` | `ForecastModelDetailView` | tenant required |
| `/mrp/forecast-models/<pk>/edit/` | `ForecastModelEditView` | tenant required |
| `/mrp/forecast-models/<pk>/delete/` | `ForecastModelDeleteView` | tenant required |
| `/mrp/forecast-models/<pk>/run/` | `ForecastModelRunView` | tenant required |
| `/mrp/seasonality/` | `SeasonalityListView` | tenant required |
| `/mrp/seasonality/new/` | `SeasonalityCreateView` | tenant required |
| `/mrp/seasonality/<pk>/edit/` | `SeasonalityEditView` | tenant required |
| `/mrp/seasonality/<pk>/delete/` | `SeasonalityDeleteView` | tenant required |
| `/mrp/forecast-runs/` | `ForecastRunListView` | tenant required |
| `/mrp/forecast-runs/<pk>/` | `ForecastRunDetailView` | tenant required |
| `/mrp/forecast-runs/<pk>/delete/` | `ForecastRunDeleteView` | tenant required |
| `/mrp/inventory/` | `InventoryListView` | tenant required |
| `/mrp/inventory/new/` | `InventoryCreateView` | tenant required |
| `/mrp/inventory/<pk>/` | `InventoryDetailView` | tenant required |
| `/mrp/inventory/<pk>/edit/` | `InventoryEditView` | tenant required |
| `/mrp/inventory/<pk>/delete/` | `InventoryDeleteView` | tenant required |
| `/mrp/receipts/` | `ReceiptListView` | tenant required |
| `/mrp/receipts/new/` | `ReceiptCreateView` | tenant required |
| `/mrp/receipts/<pk>/edit/` | `ReceiptEditView` | tenant required |
| `/mrp/receipts/<pk>/delete/` | `ReceiptDeleteView` | tenant required |
| `/mrp/calculations/` | `CalculationListView` | tenant required |
| `/mrp/calculations/<pk>/` | `CalculationDetailView` | tenant required |
| `/mrp/calculations/<pk>/delete/` | `CalculationDeleteView` | **admin** required |
| `/mrp/runs/` | `RunListView` | tenant required |
| `/mrp/runs/new/` | `RunCreateView` | tenant required |
| `/mrp/runs/<pk>/` | `RunDetailView` | tenant required |
| `/mrp/runs/<pk>/start/` | `RunStartView` | tenant required |
| `/mrp/runs/<pk>/apply/` | `RunApplyView` | **admin** required |
| `/mrp/runs/<pk>/discard/` | `RunDiscardView` | **admin** required |
| `/mrp/runs/<pk>/delete/` | `RunDeleteView` | tenant required |
| `/mrp/requisitions/` | `PRListView` | tenant required |
| `/mrp/requisitions/<pk>/` | `PRDetailView` | tenant required |
| `/mrp/requisitions/<pk>/edit/` | `PREditView` | tenant required |
| `/mrp/requisitions/<pk>/approve/` | `PRApproveView` | **admin** required |
| `/mrp/requisitions/<pk>/cancel/` | `PRCancelView` | **admin** required |
| `/mrp/requisitions/<pk>/delete/` | `PRDeleteView` | tenant required |
| `/mrp/exceptions/` | `ExceptionListView` | tenant required |
| `/mrp/exceptions/<pk>/` | `ExceptionDetailView` | tenant required |
| `/mrp/exceptions/<pk>/acknowledge/` | `ExceptionAckView` | tenant required |
| `/mrp/exceptions/<pk>/resolve/` | `ExceptionResolveView` | **admin** required |
| `/mrp/exceptions/<pk>/ignore/` | `ExceptionIgnoreView` | **admin** required |
| `/mrp/exceptions/<pk>/delete/` | `ExceptionDeleteView` | **admin** required |

### 3.2 Search / filter params per list page

| List page | Search field (`q=`) | Filters |
|---|---|---|
| Forecast Models | name, description | method, period_type, active |
| Seasonality | product__sku, product__name | product, period_type |
| Forecast Runs | run_number, forecast_model__name | status, forecast_model |
| Inventory | product__sku, product__name | lot_size_method |
| Receipts | product__sku, reference | receipt_type, product |
| MRP Calculations | mrp_number, name | status |
| MRP Runs | run_number, name | status, run_type |
| Purchase Requisitions | pr_number, product__sku | status, priority, product |
| Exceptions | product__sku, message | exception_type, severity, status |

### 3.3 Pagination

- Forecast Models: 20 per page
- Seasonality: 30 per page
- Forecast Runs: 20 per page
- Inventory: 20 per page
- Receipts: 20 per page
- Calculations: 20 per page
- Runs: 20 per page
- PRs: 20 per page
- Exceptions: 25 per page

### 3.4 Status workflows

| Entity | States | Privileged actions (admin only) |
|---|---|---|
| MRPCalculation | draft → running → completed → committed / discarded; failed | delete (any state except committed) |
| MRPRun | queued → running → completed → applied; failed; discarded | apply, discard |
| MRPPurchaseRequisition | draft → approved → cancelled / converted | approve, cancel |
| MRPException | open → acknowledged → resolved / ignored | resolve, ignore, delete |

### 3.5 Seeded data (per tenant, after `seed_mrp`)

| Item | Acme | Globex | Stark |
|---|---|---|---|
| Forecast Models | 2 | 2 | 2 |
| Seasonality Profiles | 24 (12 × 2 SKUs) | 24 | 24 |
| Forecast Runs (completed) | 1 | 1 | 1 |
| Forecast Results | ~16 | ~16 | ~16 |
| Inventory Snapshots | up to 8 | up to 8 | up to 8 |
| Scheduled Receipts | up to 5 | up to 5 | up to 5 |
| MRP Calculations (completed) | 1 | 1 | 1 |
| MRP Runs (completed) | 1 | 1 | 1 |
| MRPPurchaseRequisitions (draft) | varies | varies | varies |
| MRPExceptions | varies | varies | varies |

---

## 4. Test Cases

> Tester fills the **Pass/Fail** and **Notes** columns. Steps inside a cell are numbered with `<br>` line breaks for readability.

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous user blocked from MRP index | logged out | 1. Navigate to `http://127.0.0.1:8000/mrp/` | none | Browser redirects to `/login/?next=/mrp/`. The MRP page never renders. |  |  |
| TC-AUTH-02 | Anonymous blocked from inner page (deep-link) | logged out | 1. Navigate to `http://127.0.0.1:8000/mrp/runs/` | none | Redirect to `/login/?next=/mrp/runs/` |  |  |
| TC-AUTH-03 | Superuser (no tenant) sees friendly redirect | logged in as `admin` (Django superuser) | 1. Navigate to `/mrp/` | none | Redirect to `/dashboard` with a yellow toast: "You are signed in as a user without a tenant…" |  |  |
| TC-AUTH-04 | Tenant admin can access MRP | logged in as `admin_acme` / `Welcome@123` | 1. Navigate to `/mrp/` | none | Index renders with KPI cards; sidebar shows MRP active |  |  |
| TC-AUTH-05 | CSRF protection on POST | logged in as `admin_acme` | 1. In DevTools, copy `csrfmiddlewaretoken` value 2. Strip it from a Resolve POST and resubmit via curl/devtools | exception_resolve URL | Server returns 403 |  |  |
| TC-AUTH-06 | Tenant staff (non-admin) blocked from privileged POST | logged in as a non-admin tenant user | 1. Navigate to a draft PR detail 2. Attempt `Approve` (button may be visible or absent depending on template) 3. POST `/mrp/requisitions/<pk>/approve/` | none | Redirect to `/dashboard` with a red flash "Only tenant administrators can access that page." PR.status remains `draft`. |  |  |

### 4.2 Multi-Tenancy Isolation

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Tenant A admin sees only Tenant A forecast models | logged in as `admin_acme` | 1. Open `/mrp/forecast-models/` 2. Note the count and names | none | Only Acme's forecast models listed. `Default Moving Avg (3-period)` and `Naive Seasonal (12-month)` should appear. |  |  |
| TC-TENANT-02 | Cross-tenant calc detail PK → 404 | logged in as `admin_acme`; have noted a Globex calc pk via `admin_globex` first | 1. Log in as `admin_globex`, open `/mrp/calculations/`, copy a Globex calc pk (e.g. 4) 2. Log out 3. Log in as `admin_acme` 4. Navigate to `/mrp/calculations/4/` (Globex pk) | Globex calc pk | 404 page |  |  |
| TC-TENANT-03 | Cross-tenant inventory edit → 404 | as TC-TENANT-02 with an inventory snapshot pk from Globex | 1. Visit `/mrp/inventory/<globex-pk>/edit/` while logged in as Acme | Globex snapshot pk | 404 |  |  |
| TC-TENANT-04 | Cross-tenant run apply rejected | as TC-TENANT-02 with a Globex completed run pk | 1. Visit `/mrp/runs/<globex-pk>/apply/` (POST via DevTools form) while logged in as Acme | Globex run pk | 404 OR redirect with no state change on the run |  |  |
| TC-TENANT-05 | Tenant A list URL shows zero results when DB has only Tenant B data | logged in as `admin_acme` after `seed_mrp --flush; seed_mrp` then deleting all Acme rows manually | 1. Navigate to `/mrp/runs/` | none | Empty state; "No runs yet" or empty table; pagination not shown |  |  |

### 4.3 CREATE

#### 4.3.1 ForecastModel

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-FM-01 | Create — happy path | logged in as `admin_acme`; on `/mrp/forecast-models/` | 1. Click **+ New Forecast Model** in top-right<br>2. Fill **Name**: `Manual SMA-3`<br>3. **Method**: `Moving Average`<br>4. **Params**: `{"window": 3}`<br>5. **Period type**: `Weekly`<br>6. **Horizon periods**: `12`<br>7. **Active** checkbox: ON<br>8. Click **Save** | as listed | Redirect to list; green toast "Forecast model 'Manual SMA-3' created."; new row visible at the top of the list |  |  |
| TC-CREATE-FM-02 | Create — duplicate name blocked (D-01 lesson) | TC-CREATE-FM-01 done | 1. Click **+ New Forecast Model**<br>2. Enter the same Name `Manual SMA-3`<br>3. Submit | as listed | Form re-renders with a red error under **Name**: "A forecast model with this name already exists." NO 500. |  |  |
| TC-CREATE-FM-03 | Create — required field missing | on create form | 1. Leave Name blank<br>2. Click Save | empty name | Red error under Name "This field is required." |  |  |
| TC-CREATE-FM-04 | Create — horizon over max | on create form | 1. Set **Horizon periods** to `200`<br>2. Submit | 200 | Red field error: "Ensure this value is less than or equal to 104." |  |  |
| TC-CREATE-FM-05 | Create — XSS in description | on create form | 1. Description: `<script>alert(1)</script>`<br>2. Submit | XSS payload | Save succeeds. Open detail — payload renders as escaped text, no JS executes, no DevTools console error. |  |  |

#### 4.3.2 SeasonalityProfile

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-SP-01 | Create — happy path | on `/mrp/seasonality/` | 1. Click **+ New**<br>2. Pick a Product (e.g. `SKU-4001`)<br>3. **Period type**: `Monthly`<br>4. **Period index**: `1`<br>5. **Seasonal index**: `1.10`<br>6. Save | listed | Redirect to list; green toast; new row visible filtered to the chosen product |  |  |
| TC-CREATE-SP-02 | Monthly index > 12 blocked | on create form | 1. Period type `Monthly`, Period index `13` 2. Submit | 13 | Red error under period_index: "Monthly index must be 1–12." |  |  |
| TC-CREATE-SP-03 | Weekly index > 52 blocked (D-14) | on create form | 1. Period type `Weekly`, Period index `53` 2. Submit | 53 | Red error: "Weekly index must be 1–52." |  |  |
| TC-CREATE-SP-04 | Duplicate (product, period_type, period_index) blocked | seeded data already has month 1 for SKU-4001 | 1. Pick `SKU-4001`, Period type `Monthly`, Period index `1`, save | dup | Form-level red error: "This product already has a seasonality entry for this period." NO 500. |  |  |

#### 4.3.3 InventorySnapshot

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-IS-01 | Create — L4L happy path | on `/mrp/inventory/new/`; pick a product not yet snapshotted (e.g. `SKU-3003` if it exists, else create one in PLM first) | 1. Fill Product, On-hand `25`, Safety `10`, Reorder `20`, Lead time `14`, Lot rule `Lot-for-Lot`, As-of `today`<br>2. Save | as listed | Redirect to list; green toast; row visible |  |  |
| TC-CREATE-IS-02 | FOQ with lot_size_value=0 rejected | on create form | 1. Lot rule `Fixed Order Quantity`, Lot value `0` 2. Submit | 0 | Red error under lot_size_value: "FOQ size must be greater than zero." |  |  |
| TC-CREATE-IS-03 | Min-Max with max ≤ min rejected | on create form | 1. Lot rule `Min-Max`, Lot value `50`, Lot max `50` 2. Submit | 50/50 | Red error under lot_size_max: "Max must be greater than Min." |  |  |
| TC-CREATE-IS-04 | Duplicate snapshot for same product blocked | the product already has a snapshot | 1. Pick same product 2. Submit | duplicate | Red error under Product: "This product already has an inventory snapshot." NO 500. |  |  |
| TC-CREATE-IS-05 | Lead time > 365 rejected | on create form | 1. Lead time `400` 2. Submit | 400 | Field-level validator error |  |  |

#### 4.3.4 ScheduledReceipt

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-RC-01 | Create — happy path | on `/mrp/receipts/new/` | 1. Pick Product, Type `Open Purchase Order`, Quantity `100`, Date `today + 7 days`, Reference `PO-MAN-001`<br>2. Save | as listed | Redirect to list; green toast; row visible ordered by expected_date |  |  |
| TC-CREATE-RC-02 | Quantity 0 rejected | on create form | 1. Quantity `0` 2. Submit | 0 | Red field-level error (MinValueValidator(0.0001)) |  |  |
| TC-CREATE-RC-03 | Past expected date allowed (back-dated) | on create form | 1. Expected date = yesterday 2. Save | past date | Save succeeds; row visible (back-dated by design — used to record receipts already in transit) |  |  |

#### 4.3.5 MRP Run + Calculation (combined)

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-RN-01 | Create new MRP run + calc pair | on `/mrp/runs/new/` | 1. Run name `Manual run #1`<br>2. Run type `Regenerative`<br>3. Source MPS — pick the seeded MPS<br>4. Calc name `Manual calc #1`<br>5. Horizon start `today`<br>6. Horizon end `today + 28d`<br>7. Time bucket `Weekly`<br>8. Submit | as listed | Redirect to run detail page; green toast `MRP run MRPRUN-NNNNN created. Click Start to execute.` Run shows status **Queued**. Calc visible at linked URL with status **Draft**. |  |  |
| TC-CREATE-RN-02 | Horizon end ≤ start rejected | on form | 1. Horizon start `today`, Horizon end `today` 2. Submit | same date | Red error under horizon_end: "Horizon end must be after horizon start." |  |  |

#### 4.3.6 MRP Purchase Requisition (manual, not auto-generated)

PRs are normally auto-generated by the engine. There is no `/mrp/requisitions/new/` route for manual creation by design — confirm that the PR list does NOT show a **+ New** button, only the Edit / Approve / Cancel / Delete actions on existing rows.

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-PR-01 | No "+ New PR" button on list | on `/mrp/requisitions/` | 1. Inspect top-right of list page | none | No "+ New" button visible. Action description in the page subtitle says PRs are auto-generated by MRP runs. |  |  |

### 4.4 READ — List Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-01 | Forecast Models list renders | on `/mrp/forecast-models/` | 1. Inspect table header columns 2. Inspect first row | seeded data | Columns: Name · Method · Period · Horizon · Active · Actions. At least 2 seeded rows. No `None` literals anywhere. |  |  |
| TC-LIST-02 | Seasonality list renders | on `/mrp/seasonality/` | 1. Inspect rows | seeded data | Up to 30 rows; Period column shows `Monthly · #N`; Index column shows decimals like `1.1000` |  |  |
| TC-LIST-03 | Forecast Runs list renders | on `/mrp/forecast-runs/` | 1. Inspect status badges | seeded data | At least 1 row with **Completed** green badge; result_count column populated |  |  |
| TC-LIST-04 | Inventory list renders | on `/mrp/inventory/` | 1. Inspect table | seeded data | Up to 8 rows. Lot rule shown as info badge. As-of date in `Apr j` shape. Actions column has View / Edit / Delete icons. |  |  |
| TC-LIST-05 | Receipts list ordered by expected date | on `/mrp/receipts/` | 1. Inspect order of rows | seeded | Rows ordered ascending by expected_date |  |  |
| TC-LIST-06 | Calculations list renders | on `/mrp/calculations/` | 1. Inspect | seeded | Status badge **Completed** for the seeded calc; net_count + exc_count columns are integers (0 or higher) |  |  |
| TC-LIST-07 | Runs list renders | on `/mrp/runs/` | 1. Inspect | seeded | Run number, name, run_type **Regenerative**, status **Completed** |  |  |
| TC-LIST-08 | Purchase Requisitions list renders | on `/mrp/requisitions/` | 1. Inspect | seeded | Auto-generated PRs `MPR-NNNNN`. Status badge **Draft** for new ones. |  |  |
| TC-LIST-09 | Exceptions list ordered by severity | on `/mrp/exceptions/` | 1. Inspect | seeded | Critical first, then High, Medium, Low. Severity badge color matches: red (Critical), orange (High), blue (Medium), grey (Low). |  |  |
| TC-LIST-10 | Empty state | tenant with seed wiped | 1. Run `seed_mrp --flush` + log in as a tenant whose data was wiped 2. Navigate `/mrp/calculations/` | none | Table shows empty placeholder row "No data yet" or similar; no traceback |  |  |

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DETAIL-01 | Forecast Model detail | from forecast model list, click first row Name link | as seeded | 1. Inspect tabs / sidebar | Forecast Model summary card; "Recent Runs" sub-section listing the 1 seeded run linked to that model |  |
| TC-DETAIL-02 | Forecast Run detail | from forecast runs list, click any run number | seeded run | 1. Scroll Results table | Per-period forecast points grouped by product; 4 weeks × N products visible |  |
| TC-DETAIL-03 | Inventory snapshot detail | from inventory list, click first SKU link | seeded | 1. Inspect right panel | "Upcoming Receipts" panel populated with up to 10 future receipts for that product |  |
| TC-DETAIL-04 | Calculation detail | from calculations list, click first MRP number | seeded calc | 1. Inspect three tabs / sections | Net Requirements, Purchase Requisitions, Exceptions all listed for this calc; counts on the summary card match the lists |  |
| TC-DETAIL-05 | Run detail with KPI summary | from runs list, click first run number | seeded | 1. Inspect KPI panel right side | Coverage %, Planned orders, PR suggestions, Exceptions, Late orders counters all show numbers (not blank) |  |
| TC-DETAIL-06 | PR detail | click a draft PR number | seeded PR | 1. Inspect Actions sidebar | If logged in as tenant admin: Edit / Approve / Cancel buttons visible. Status badge **Draft**. |  |
| TC-DETAIL-07 | Exception detail | click a critical exception | seeded | 1. Inspect detail card | Type, Severity, Status, Recommended Action, Recommended Date all populated; Resolve form on the right side |  |
| TC-DETAIL-08 | ScheduledReceipt — N/A no detail page | — | — | — | **N/A** — receipts have no dedicated detail view; list + edit + delete only. |  |
| TC-DETAIL-09 | Seasonality — N/A no detail page | — | — | — | **N/A** — seasonality entries have list + edit + delete only. |  |

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit ForecastModel — pre-fills | on a FM detail page | 1. Click **Edit** | seeded | Form opens with Name / Method / Params / Period / Horizon / Active all pre-filled with current values |  |  |
| TC-EDIT-02 | Edit FM save persists | from edit form | 1. Change Description to `Updated description` 2. Save | new desc | Redirect to detail; green toast; description text updated on detail card |  |  |
| TC-EDIT-03 | Edit FM with name conflict | from edit form | 1. Change Name to another existing FM name 2. Save | dup | Form re-renders with red error "A forecast model with this name already exists." Description still shows the unsaved value (not lost). |  |  |
| TC-EDIT-04 | Edit InventorySnapshot — change to FOQ | from snapshot edit form | 1. Switch Lot rule to `Fixed Order Quantity` 2. Lot value `100` 3. Save | as listed | Redirect to detail; green toast; method now shows `Fixed Order Quantity` badge |  |  |
| TC-EDIT-05 | Edit Receipt — change quantity | from receipt edit form | 1. Quantity `999` 2. Save | 999 | Redirect to list; green toast; new value visible |  |  |
| TC-EDIT-06 | Edit draft PR — quantity | from PR detail (draft) | 1. Click **Edit** 2. Change Quantity to `15` 3. Save | 15 | Redirect to detail; green toast `PR updated.`; new qty visible |  |  |
| TC-EDIT-07 | Edit approved PR rejected | a PR with status `approved` | 1. Click Edit (if visible) OR navigate `/mrp/requisitions/<pk>/edit/` | none | Redirect to detail with yellow toast "PR can only be edited in Draft status." |  |  |
| TC-EDIT-08 | Edit Seasonality — change index | from seasonality list | 1. Click pencil icon 2. Change Seasonal index to `0.7500` 3. Save | 0.7500 | Redirect to list; new value visible |  |  |

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete confirmation dialog | on inventory list | 1. Click bin icon on a row | none | Browser native confirm: "Delete this snapshot?" with OK / Cancel |  |  |
| TC-DELETE-02 | Delete cancel does nothing | TC-DELETE-01 | 1. Click Cancel | none | No request fired; row still in list |  |  |
| TC-DELETE-03 | Delete confirm removes record | TC-DELETE-01 | 1. Click OK | none | Redirect to list; green toast `Inventory snapshot deleted.`; row gone |  |  |
| TC-DELETE-04 | Delete ForecastModel referenced by run rejected | a FM that has at least 1 ForecastRun (the seeded model) | 1. Open FM detail 2. Click bin icon 3. Confirm | none | Redirect to FM detail with red flash "Cannot delete — forecast model is referenced by past runs." Row still exists. |  |  |
| TC-DELETE-05 | Delete ForecastRun cascades results | open the seeded run | 1. Click delete icon (top-right) 2. Confirm | none | Redirect to runs list with green toast; the run AND its `ForecastResult` rows are gone (open Django admin to verify if needed) |  |  |
| TC-DELETE-06 | Delete committed calc rejected | force a calc to `committed` (apply a run first) | 1. Open the calc 2. Attempt delete | none | Red flash "Committed calculations cannot be deleted." |  |  |
| TC-DELETE-07 | Delete calc with runs surfaces friendly error (D-05) | calc has ≥ 1 run | 1. Open calc detail 2. Attempt delete | none | Redirect with red flash "Cannot delete — one or more MRP runs reference this calculation. Delete the runs first." |  |  |
| TC-DELETE-08 | Delete PR (draft only) allowed | draft PR exists | 1. PR list, click bin icon, confirm | none | Green toast `PR deleted.`; row gone |  |  |
| TC-DELETE-09 | Delete approved PR rejected | a PR with `approved` status | 1. PR detail, attempt delete | none | Red flash "Only Draft or Cancelled PRs can be deleted." |  |  |
| TC-DELETE-10 | Delete open exception rejected (D-07) | a critical exception with status `open` | 1. Exception detail, click bin icon, confirm | none | Red flash "Only resolved or ignored exceptions can be deleted. Resolve or ignore this exception first." Row still exists. |  |  |
| TC-DELETE-11 | Delete resolved exception allowed | resolve an exception first | 1. After TC-ACTION-EX-02, click bin icon, confirm | none | Green toast; row gone |  |  |
| TC-DELETE-12 | Delete applied run rejected | a run flipped to `applied` | 1. Run detail, attempt delete | none | Red flash "Applied runs cannot be deleted." |  |  |
| TC-DELETE-13 | Staff cannot delete calculation | logged in as a non-admin staff user | 1. Navigate `/mrp/calculations/<pk>/`, attempt delete | none | Redirect to dashboard with red flash "Only tenant administrators can access that page." Calc still exists. |  |  |

### 4.8 SEARCH

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-SEARCH-01 | Empty search returns all | on `/mrp/forecast-models/?q=` | 1. Submit empty search | none | Full list shown |  |  |
| TC-SEARCH-02 | Single character match | on FM list | 1. Type `S` in search 2. Submit | `S` | List narrows to names containing 'S' (case-insensitive) |  |  |
| TC-SEARCH-03 | Search by exact run number | on `/mrp/forecast-runs/` | 1. Type `FRUN-00001` 2. Submit | `FRUN-00001` | Single row visible |  |  |
| TC-SEARCH-04 | Search by SKU on inventory list | on `/mrp/inventory/` | 1. Type `4001` 2. Submit | `4001` | List narrows to SKUs containing 4001 |  |  |
| TC-SEARCH-05 | No-match shows empty state | on FM list | 1. Type `xyzzy_nope` 2. Submit | `xyzzy_nope` | Empty placeholder; no error |  |  |
| TC-SEARCH-06 | Special chars do not 500 | on PR list | 1. Type `'%_<>` 2. Submit | special | Clean empty result; URL contains URL-encoded chars; no 500 |  |  |
| TC-SEARCH-07 | Whitespace trim | on FM list | 1. Type `   SMA   ` 2. Submit | padded | Same result as `SMA` (no left/right whitespace) |  |  |
| TC-SEARCH-08 | Search retains across pagination | on a list with > 1 page | 1. Search for term that yields > 20 results 2. Click page 2 in pagination | n/a | URL query string preserves both `q=` and `page=2`; result rows still match the search |  |  |
| TC-SEARCH-09 | Search by exception message snippet | on `/mrp/exceptions/` | 1. Type `lead time` 2. Submit | message snippet | List narrows to expedite exceptions |  |  |

### 4.9 PAGINATION

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-PAGE-01 | Pagination shows when > page-size rows | a list with ≥ 21 rows (e.g. seasonality has 24 per tenant on Acme) | 1. Open `/mrp/seasonality/` | none | Pagination control visible at bottom: `1 / 1` initially. Increase data via repeated seed if needed. |  |  |
| TC-PAGE-02 | Click page 2 | a list with > 30 rows | 1. Click `»` or `2` | none | URL becomes `?page=2`; rows 31-60 shown |  |  |
| TC-PAGE-03 | Beyond last page graceful | URL `?page=999` | 1. Manually edit URL 2. Submit | `?page=999` | 404 OR last page shown gracefully — NOT a 500 |  |  |
| TC-PAGE-04 | Filter retained across pages | on PR list with status `draft` selected and > 20 results | 1. Apply filter Status `Draft` 2. Click page 2 | n/a | URL contains both `status=draft&page=2`; rows still match filter |  |  |
| TC-PAGE-05 | `?page=abc` graceful | URL `?page=abc` | 1. Visit | `abc` | 404 OR first page shown — NOT a 500 |  |  |

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-FILTER-01 | FM filter by Method | on `/mrp/forecast-models/` | 1. Method dropdown → `Naive Seasonal` 2. Submit | `naive_seasonal` | Only Naive Seasonal model shown |  |  |
| TC-FILTER-02 | FM filter by Active | on FM list | 1. Active dropdown → `Inactive` 2. Submit | `inactive` | Only inactive models shown (likely zero in seeded data) |  |  |
| TC-FILTER-03 | FM combined filters | FM list | 1. Method `Moving Average` AND Period `Weekly` 2. Submit | n/a | AND-filtering — only models matching BOTH |  |  |
| TC-FILTER-04 | Inventory filter by Lot rule | on `/mrp/inventory/` | 1. Lot rule dropdown → `Fixed Order Quantity` 2. Submit | `foq` | Only FOQ snapshots shown |  |  |
| TC-FILTER-05 | Receipts filter by Type | on `/mrp/receipts/` | 1. Type → `Open Purchase Order` 2. Submit | `open_po` | Only PO receipts shown |  |  |
| TC-FILTER-06 | PR filter by Status | on PR list | 1. Status → `Draft` 2. Submit | `draft` | Only draft PRs shown |  |  |
| TC-FILTER-07 | Exceptions filter by Severity | on exceptions list | 1. Severity → `Critical` 2. Submit | `critical` | Only critical exceptions (no_bom typically) |  |  |
| TC-FILTER-08 | Filter selection retained after Apply | TC-FILTER-06 | 1. Inspect dropdown after submit | n/a | Selected option still highlighted (`Draft`), not reset |  |  |
| TC-FILTER-09 | Filter for empty result | on PR list | 1. Status → `Converted` 2. Submit | `converted` | Empty state — no rows (PRs are not converted yet pre-Module 9) |  |  |
| TC-FILTER-10 | Filter + search combine | on PR list | 1. Status `Draft` 2. Search `MPR` 3. Submit | n/a | Both AND-applied; URL has both query params |  |  |

### 4.11 Status Transitions / Custom Actions

#### 4.11.1 Forecast model run

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-FM-01 | Run forecast — happy path | on a FM detail page | 1. Click **Run forecast** button | none | Redirect to a new ForecastRun detail. Status **Completed**. Results table populated for up to 8 active products. |  |  |
| TC-ACTION-FM-02 | Run flash warns when products truncated (D-12) | tenant has > 8 active products | 1. Click Run | none | After run, an additional yellow toast appears: "Forecast covered the first 8 of N active products. The remaining N-8 will be picked up when sales-order history (Module 17) drives the forecast." |  |  |

#### 4.11.2 MRP Run lifecycle

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-RN-01 | Start queued run | a freshly-created run with status **Queued** | 1. Run detail → click **Start Run** | none | Redirect back to detail; status flips to **Completed**; KPI panel populated; success flash naming the planned-orders / PR / exception counts |  |  |
| TC-ACTION-RN-02 | Start run when calc has no demand | run pointing to a calc with horizon outside any MPS / forecast window | 1. Click Start | none | Run completes with 0 planned orders; flash mentions 0 counts |  |  |
| TC-ACTION-RN-03 | Apply completed regenerative run | a completed regenerative run, logged in as `admin_acme` | 1. Click **Apply (commit)** | none | Status flips to **Applied**; calc status flips to **Committed**; green flash `MRP run applied — calculation committed.` Apply button no longer visible. |  |  |
| TC-ACTION-RN-04 | Apply simulation run rejected | a run with run_type `Simulation`, status `Completed` | 1. Click Apply (button may be hidden — try POST via /apply/) | none | Yellow flash "Only completed Regenerative or Net-Change runs can be applied. Simulations are read-only." Status still Completed. |  |  |
| TC-ACTION-RN-05 | Discard completed run | a completed run | 1. Click **Discard**, confirm | none | Status flips to **Discarded**; calc to **Discarded** |  |  |
| TC-ACTION-RN-06 | Apply blocked for non-admin (D-01) | logged in as non-admin staff user; a completed regenerative run | 1. Visit run detail 2. Attempt Apply (POST `/runs/<pk>/apply/`) | none | Redirect to dashboard with red flash "Only tenant administrators can access that page." Run stays Completed. |  |  |
| TC-ACTION-RN-07 | Concurrent apply double-submit | an admin opens two browser tabs on the same completed run | 1. Click Apply in tab 1 (success) 2. Quickly click Apply in tab 2 | n/a | Tab 1 succeeds (Applied/Committed). Tab 2 redirects with yellow flash "Run is not in Completed state." NO error 500, NO duplicate state. |  |  |

#### 4.11.3 Purchase Requisition workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-PR-01 | Approve draft PR | a draft PR, logged in as admin | 1. PR detail → click **Approve** | none | Status → Approved; approved_by + approved_at populated; green flash `PR approved.` |  |  |
| TC-ACTION-PR-02 | Approve already-approved no-op | TC-ACTION-PR-01 done | 1. POST `/requisitions/<pk>/approve/` again | none | Yellow flash "Only Draft PRs can be approved." Status unchanged. |  |  |
| TC-ACTION-PR-03 | Cancel approved PR | an approved PR | 1. Click **Cancel**, confirm | none | Status → Cancelled; flash `PR cancelled.` |  |  |
| TC-ACTION-PR-04 | Approve blocked for non-admin (D-01) | non-admin staff | 1. Open draft PR detail 2. POST approve via the form | none | Redirect to dashboard with red flash. Status still `draft`. |  |  |

#### 4.11.4 Exception workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-EX-01 | Acknowledge open exception | open exception | 1. Click **Acknowledge** | none | Status → Acknowledged; flash `Exception acknowledged.` |  |  |
| TC-ACTION-EX-02 | Resolve with notes | open or acknowledged exception | 1. Type a note in the Resolution Notes textarea: `Expedited via vendor call.`<br>2. Click **Mark Resolved** | note | Status → Resolved; resolved_by + resolved_at populated; flash `Exception marked resolved.` |  |  |
| TC-ACTION-EX-03 | Resolve with empty notes blocked (D-06) | open exception | 1. Leave Resolution Notes blank<br>2. Click Mark Resolved | empty | Red form error "Please add a resolution note." Status still `open`. |  |  |
| TC-ACTION-EX-04 | Resolve with whitespace-only notes blocked (D-06) | open exception | 1. Type `   ` (spaces only) 2. Submit | spaces | Red form error; status unchanged |  |  |
| TC-ACTION-EX-05 | Ignore acknowledged exception | acknowledged exception | 1. Click **Ignore**, confirm | none | Status → Ignored; flash `Exception ignored.` |  |  |
| TC-ACTION-EX-06 | Resolve blocked for non-admin (D-01) | logged in as staff non-admin; open exception | 1. POST resolve | note | Redirect to dashboard with red flash. Status still `open`. |  |  |

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-UI-01 | Browser tab title accurate | each MRP page | 1. Inspect tab title | n/a | Title contains the relevant entity (e.g. "MRP — Forecast Models", "MRP Run — MRPRUN-00001") |  |  |
| TC-UI-02 | Sidebar active state | navigate to any MRP sub-page | 1. Inspect sidebar | n/a | "Material Requirements Planning" group is highlighted; active sub-link is bold or coloured |  |  |
| TC-UI-03 | Status badges colour-coded correctly | runs list | 1. Inspect badges | n/a | Completed = green, Running = orange, Failed = red, Discarded = grey, Applied = blue |  |  |
| TC-UI-04 | Severity badges colour-coded | exceptions list | 1. Inspect | n/a | Critical = red, High = orange, Medium = blue, Low = grey |  |  |
| TC-UI-05 | Confirm dialog names the action | bin icon click | 1. Inspect dialog text | n/a | Dialog text mentions the entity (e.g. "Delete this snapshot?", "Delete this PR?") |  |  |
| TC-UI-06 | Toasts auto-dismiss | submit any form | 1. Note the toast 2. Wait ~5s | n/a | Toast fades or auto-dismisses |  |  |
| TC-UI-07 | Required field markers | open any create form | 1. Inspect labels | n/a | Required fields show `*` or "required" marker |  |  |
| TC-UI-08 | Long text wrap | enter very long description (300 chars) on FM | 1. Submit, view detail | 300 chars | Description wraps cleanly; no horizontal page scroll |  |  |
| TC-UI-09 | Mobile viewport (375×667) | open Chrome DevTools, set viewport | 1. Navigate the runs list and run detail | n/a | Layout reflows to a single column; tables scroll horizontally; no offscreen content; sidebar collapses to hamburger |  |  |
| TC-UI-10 | Tablet viewport (768×1024) | DevTools | 1. Navigate calc detail | n/a | Layout uses 2-column shape; KPI panel beside details panel |  |  |
| TC-UI-11 | Keyboard nav | on FM create form | 1. Tab through fields | n/a | Tab order is logical; focus ring visible on each input; Enter from last field submits |  |  |
| TC-UI-12 | No console errors | open DevTools console, navigate every MRP page | 1. Inspect console after each navigation | n/a | No red errors; warnings tolerated only if known (e.g. deprecation notices from third-party scripts) |  |  |
| TC-UI-13 | Breadcrumb / page title bar | on FM detail | 1. Inspect top of page | n/a | Page title shows entity name; back link visible |  |  |
| TC-UI-14 | Empty state has CTA | on a tenant with no FMs | 1. Open FM list | n/a | Empty placeholder + "+ New Forecast Model" CTA visible |  |  |
| TC-UI-15 | KPI cards on index | on `/mrp/` | 1. Inspect cards | n/a | Six metric cards: Open Runs, Completed Runs, Open Exceptions, Critical Exceptions, Late Orders, Pending PRs. Numbers match the lists. Last coverage % visible if a run completed. |  |  |

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-NEG-01 | Submit FM form all blank | on create form | 1. Click Save without entering anything | empty | Multiple field errors shown at once (Name, Method, Period, Horizon) |  |  |
| TC-NEG-02 | Decimal field with letters | on receipt create | 1. Type `abc` in Quantity 2. Submit | `abc` | Field error "Enter a number." (or similar). NO 500. |  |  |
| TC-NEG-03 | Negative quantity rejected | receipt create | 1. Quantity `-5` 2. Submit | `-5` | Field error (MinValueValidator(0.0001)). |  |  |
| TC-NEG-04 | Date in invalid format | receipt create | 1. Type `not-a-date` 2. Submit | `not-a-date` | Browser HTML5 date input rejects OR Django rejects. NO 500. |  |  |
| TC-NEG-05 | XSS in run commit_notes | run create form | 1. Commit notes `<img src=x onerror=alert(1)>` 2. Save 3. Open run detail | XSS payload | Payload rendered escaped; no JS executes; no console error |  |  |
| TC-NEG-06 | Large pagination value | URL `?page=99999` on PR list | 1. Visit | `99999` | 404 page (graceful) |  |  |
| TC-NEG-07 | Run start when not Queued | a run already Completed | 1. POST `/runs/<pk>/start/` | none | Yellow flash "Run is not in Queued state." Status unchanged. |  |  |
| TC-NEG-08 | Refresh after POST | after creating a snapshot, hit F5 | 1. F5 | n/a | Browser prompts "Resend?" — clicking Resend MUST NOT create a duplicate (form has unique-product clean guard) |  |  |
| TC-NEG-09 | Browser back after delete | delete a record, then click back | 1. Click browser back | n/a | List page refreshes; deleted row stays gone (no resurrection) |  |  |
| TC-NEG-10 | Double-submit form | run create form, double-click Save quickly | 1. Click Save twice | n/a | Only one Run created (auto-numbered with retry); no IntegrityError surfaced |  |  |
| TC-NEG-11 | Forecast run with engine error | force a failure (e.g. stop DB mid-run is hard manually — alternatively mark a model with bad params) | 1. Edit a FM and set `params` to `{"window": "abc"}` 2. Run | bad params | Run row created with status **Failed**; error_message persisted; flash says "Forecast FRUN-... failed — see the run detail for the captured error message." (D-18 — generic to the user) |  |  |
| TC-NEG-12 | URL with non-numeric pk | `/mrp/runs/abc/` | 1. Visit | `abc` | 404 (Django int converter rejects) |  |  |

### 4.14 Cross-Module Integration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-INT-01 | MRP Run consumes seeded MPS | seeded MPS released; new run created with that MPS as source | 1. Create run with source MPS 2. Start | seeded MPS | NetRequirement rows produced for end items in MPS lines; lower BOM levels exploded |  |  |
| TC-INT-02 | MRP Run uses BOM module's `.explode()` | seeded BOM with `bom_type='mbom', status='released', is_default=True` | 1. Run engine 2. Open calc detail 3. Inspect Net Requirements | seeded | Component rows visible with `bom_level >= 1` and `parent_product` populated |  |  |
| TC-INT-03 | MRP exception links back to PPS MPS | a run with source_mps | 1. Open run detail 2. Click MPS link | seeded | Navigates to PPS MPS detail page |  |  |
| TC-INT-04 | Auto-generated PR product_type filter | seeded PRs | 1. PR list 2. Inspect product types | n/a | Auto-generated PRs only for `raw_material` and `component` products (no `finished_good` PRs) |  |  |
| TC-INT-05 | Seeder is idempotent | already-seeded tenant | 1. Re-run `python manage.py seed_mrp` | n/a | No errors; output indicates "skipped (already seeded)" lines |  |  |
| TC-INT-06 | Seeder --flush rebuilds | already-seeded | 1. `python manage.py seed_mrp --flush` | n/a | Output starts with "Flushing MRP data for 3 demo tenants...", then re-creates all rows. App pages render fine afterwards. |  |  |
| TC-INT-07 | Audit log captures actions | after running TC-ACTION-RN-03 (apply) | 1. Open Django admin → Tenants → Audit Logs (or `/admin/tenants/tenantauditlog/`) | n/a | Entries: `mrp_run.applied`, `mrp_calculation.status.committed`, etc. |  |  |
| TC-INT-08 | Audit log captures deletes (D-10) | delete a PR via TC-DELETE-08 | 1. Open audit log filtered by tenant + action `mrp_pr.deleted` | n/a | Row appears with the deleted PR's number in the meta payload |  |  |

---

## 5. Bug Log

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Screenshot | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 |  |  |  |  |  |  |  |  |
| BUG-02 |  |  |  |  |  |  |  |  |
| BUG-03 |  |  |  |  |  |  |  |  |
| BUG-04 |  |  |  |  |  |  |  |  |
| BUG-05 |  |  |  |  |  |  |  |  |
| BUG-06 |  |  |  |  |  |  |  |  |
| BUG-07 |  |  |  |  |  |  |  |  |
| BUG-08 |  |  |  |  |  |  |  |  |

> Severity guide: **Critical** = data loss / security breach / blocks release · **High** = major feature broken · **Medium** = workaround exists · **Low** = minor visual / UX · **Cosmetic** = pixel / copy.

---

## 6. Sign-off & Release Recommendation

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---|---|---|---|---|
| 4.1 Authentication & Access | 6 |  |  |  |  |
| 4.2 Multi-Tenancy Isolation | 5 |  |  |  |  |
| 4.3 CREATE | 17 |  |  |  |  |
| 4.4 READ — List Page | 10 |  |  |  |  |
| 4.5 READ — Detail Page | 9 |  |  |  |  |
| 4.6 UPDATE | 8 |  |  |  |  |
| 4.7 DELETE | 13 |  |  |  |  |
| 4.8 SEARCH | 9 |  |  |  |  |
| 4.9 PAGINATION | 5 |  |  |  |  |
| 4.10 FILTERS | 10 |  |  |  |  |
| 4.11 Status Transitions / Custom Actions | 19 |  |  |  |  |
| 4.12 Frontend UI / UX | 15 |  |  |  |  |
| 4.13 Negative & Edge Cases | 12 |  |  |  |  |
| 4.14 Cross-Module Integration | 8 |  |  |  |  |
| **Total** | **146** |  |  |  |  |

### Release recommendation

**Tester decision:** ☐ GO ☐ NO-GO ☐ GO-with-fixes

**Rationale (1 sentence):**

```
[ tester writes here ]
```

**Tester name:**  ___________________________
**Date completed:** ___________________________
**Build / commit SHA tested:**  ___________________________

---

### Appendix A — Quick reference

- **Tenant admins:** `admin_acme` / `admin_globex` / `admin_stark` — password `Welcome@123`
- **Superuser (do NOT use for MRP):** `admin` — has `tenant=None`, sees empty lists by design
- **Seed command:** `python manage.py seed_mrp` (idempotent), `python manage.py seed_mrp --flush` (re-seed)
- **Server start:** `python manage.py runserver`
- **MRP module entrypoint:** `http://127.0.0.1:8000/mrp/`
- **Per-page widgets reference:** see §3 Test Surface Inventory

### Appendix B — When to re-flush

Re-run `python manage.py seed_mrp --flush` between sessions if:

- You applied a run (calc → committed) — the seeder won't reset it without flush
- You approved or cancelled PRs and want them back to draft
- You resolved or ignored exceptions and want a fresh open queue
- You deleted any seeded entity

---

*End of plan. Tester is encouraged to log every observation, however minor, into §5 Bug Log so the dev team can triage even cosmetic issues.*
