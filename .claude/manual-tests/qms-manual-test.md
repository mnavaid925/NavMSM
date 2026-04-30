# QMS — Manual Test Plan

> Module 7 — Quality Management. Senior-QA click-through script. Runnable in a browser by any tester (or the user).
> Source code: [apps/qms/](apps/qms/), [templates/qms/](templates/qms/).

## 1. Scope & Objectives

| Field | Value |
|---|---|
| Module under test | Quality Management (QMS) — 5 sub-modules |
| Sub-modules | 7.1 IQC, 7.2 IPQC + SPC, 7.3 FQC + CoA, 7.4 NCR & CAPA, 7.5 Calibration Management |
| Top-level URL prefix | `/qms/` mounted in [config/urls.py:17](config/urls.py#L17) |
| Models in scope | 22 — see [apps/qms/models.py](apps/qms/models.py) |
| Test scope mode | **Module test** (default) — every list / create / detail / edit / delete page across 5 sub-modules + workflow + SPC chart + CoA + auth-gated downloads |
| Out of scope | Procurement FK on IQC (Module 9), server-side PDF CoA, MES Andon auto-raise on critical NCR, p / np / c / u attribute charts, Cp/Cpk indices, Gage R&R, 8D template, CSV bulk import |
| Tester profile | Junior-to-mid manual QA on Windows + Chrome 1920×1080 primary; Edge + 375×667 mobile secondary |
| Expected duration | 6–8 hours for full pass; 1.5 h for smoke subset |

**Goals**: Verify (a) every CRUD page across 5 sub-modules works end-to-end as `admin_acme`, (b) workflow transitions follow the documented gates, (c) the SPC chart and CoA generation render correctly, (d) RBAC + tenant isolation cannot be bypassed by URL guessing, (e) form validation surfaces clean errors (no 500s), (f) the equipment due-tracker red/yellow highlighting works.

---

## 2. Pre-Test Setup

Run **once** at the start of the test session.

| # | Step | Expected |
|---|---|---|
| 1 | Open PowerShell, `cd c:\xampp\htdocs\NavMSM` | Working directory set |
| 2 | Confirm XAMPP MySQL is running (Control Panel → MySQL "Running") | Database reachable |
| 3 | Apply migrations (idempotent): `python manage.py migrate` | "Migrations applied" or "no migrations to apply" |
| 4 | Seed the QMS demo data: `python manage.py seed_qms` | Output ends with `QMS seed complete.` and 3 tenant blocks each showing `iqc: 3 plans, 9 chars, 6 inspections, 8 measurements`, `ipqc: 3 plans, 8 inspections, 25 chart points`, `fqc: 2 plans, 6 specs, 5 inspections, 3 CoAs`, `ncrs: 4 NCRs, 4 RCAs, 6 CAs, 6 PAs`, `equipment: 6 items`, `calibrations: 8 records, 16 tolerance checks` |
| 5 | Start dev server: `python manage.py runserver` | "Starting development server at http://127.0.0.1:8000/" |
| 6 | Open Chrome to `http://127.0.0.1:8000/accounts/login/` | Split-card login page renders |
| 7 | Log in as `admin_acme` / `Welcome@123` | Redirect to `/` dashboard, no error toast |
| 8 | Confirm sidebar shows the **Quality (QMS)** group with shield-check icon and 12 sub-links | If missing, STOP — sidebar wiring failed |
| 9 | Click **QMS Dashboard** in the sidebar | KPI cards: open NCRs ≥ 4, IQC pending ≥ 1, FQC pending ≥ 1, equipment due (≤7d or overdue) ≥ 2 |
| 10 | Open Chrome DevTools (F12) → Console tab → leave it open | Watch for JS errors during the run |

> ⚠️ **Critical**: Do NOT log in as `admin` (Django superuser). Superuser has `tenant=None` so every QMS query returns empty by design.
>
> ⚠️ **Reset between runs**: To re-seed clean, run `python manage.py seed_qms --flush`. Do not use bare `--flush` on `seed_data` unless you want to wipe all 7 modules.

**Browser/viewport matrix**: Chrome desktop 1920×1080 (primary). Repeat smoke subset on Edge + 375×667 phone viewport.

---

## 3. Test Surface Inventory

| Surface | Count | URL prefix | Key file |
|---|---|---|---|
| Dashboard | 1 | `/qms/` | [apps/qms/views.py:107](apps/qms/views.py#L107) |
| IQC plans CRUD | 5 routes | `/qms/iqc/plans/` | [apps/qms/views.py:154](apps/qms/views.py#L154) |
| IQC inspections CRUD + 4 actions | 9 routes | `/qms/iqc/inspections/` | [apps/qms/views.py:272](apps/qms/views.py#L272) |
| IQC characteristics inline | 2 routes | `/qms/iqc/plans/<id>/characteristics/...` | [apps/qms/views.py:241](apps/qms/views.py#L241) |
| IQC measurements inline | 1 route | `/qms/iqc/inspections/<id>/measurements/new/` | [apps/qms/views.py:439](apps/qms/views.py#L439) |
| IPQC plans CRUD | 5 routes | `/qms/ipqc/plans/` | [apps/qms/views.py:489](apps/qms/views.py#L489) |
| IPQC inspections CRUD | 5 routes | `/qms/ipqc/inspections/` | [apps/qms/views.py:595](apps/qms/views.py#L595) |
| SPC charts | 3 routes | `/qms/ipqc/charts/` | [apps/qms/views.py:719](apps/qms/views.py#L719) |
| FQC plans CRUD | 5 routes + 2 spec inline | `/qms/fqc/plans/` | [apps/qms/views.py:803](apps/qms/views.py#L803) |
| FQC inspections CRUD + 4 actions | 9 routes + result inline | `/qms/fqc/inspections/` | [apps/qms/views.py:909](apps/qms/views.py#L909) |
| CoA | 2 routes | `/qms/fqc/inspections/<pk>/coa/` | [apps/qms/views.py:1099](apps/qms/views.py#L1099) |
| NCR + CAPA | 7 NCR + 4 CA + 4 PA + 3 attachment routes | `/qms/ncr/` | [apps/qms/views.py:1171](apps/qms/views.py#L1171) |
| Equipment | 6 routes | `/qms/equipment/` | [apps/qms/views.py:1535](apps/qms/views.py#L1535) |
| Calibrations | 6 routes | `/qms/calibrations/` | [apps/qms/views.py:1655](apps/qms/views.py#L1655) |
| Calibration standards | 4 routes | `/qms/calibration-standards/` | [apps/qms/views.py:1808](apps/qms/views.py#L1808) |
| **Total routes** | **89** | | [apps/qms/urls.py](apps/qms/urls.py) |

**Pagination sizes** (per [apps/qms/views.py](apps/qms/views.py)):
- 20: IQC plans, IPQC plans, FQC plans, SPC charts, calibration standards
- 25: IQC inspections, IPQC inspections, FQC inspections, NCRs, equipment, calibrations

**Auth-gated downloads**: `NCRAttachmentDownloadView`, `CalibrationCertificateDownloadView`, `InspectionAttachment` (IPQC).

**Status-workflow models**:
- `IncomingInspection`: `pending → in_inspection → accepted / rejected / accepted_with_deviation`
- `FinalInspection`: `pending → in_inspection → passed / failed / released_with_deviation`
- `NonConformanceReport`: `open → investigating → awaiting_capa → resolved → closed` (`cancelled` from any non-terminal)
- `MeasurementEquipment`: `active ↔ out_of_service`, `retired` is terminal
- `CorrectiveAction` / `PreventiveAction`: `open → in_progress → completed` (`cancelled`)

---

## 4. Test Cases

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous user redirected from QMS dashboard | Logged out (incognito tab) | 1. Open `http://127.0.0.1:8000/qms/` directly | URL pasted | Browser redirects to `/accounts/login/?next=/qms/`. Login form visible. | | |
| TC-AUTH-02 | Anonymous user redirected from list page | Logged out | 1. Open `/qms/iqc/inspections/` directly | URL pasted | Redirect to `/accounts/login/?next=/qms/iqc/inspections/` | | |
| TC-AUTH-03 | Anonymous POST blocked | Logged out | 1. Use DevTools → Network → manually craft a POST to `/qms/iqc/plans/new/` | Empty body | 302 to login. No row created in DB. | | |
| TC-AUTH-04 | Superuser sees empty QMS dashboard | Superuser `admin` exists with tenant=None | 1. Log out 2. Log in as `admin` (the Django superuser) 3. Navigate to `/qms/` | superuser creds | Dashboard renders but every KPI count is `0`, every "Recent X" panel says empty. **This is BY DESIGN — superuser has no tenant.** | | |
| TC-AUTH-05 | Tenant admin can access full QMS | `admin_acme` / `Welcome@123` | 1. Log in as admin_acme 2. Click each of the 12 sidebar links under Quality (QMS) | Click each link | Each page returns HTTP 200, no `NoReverseMatch`, no 500. | | |
| TC-AUTH-06 | Staff user (non-admin) sees lists but cannot create plan | A non-admin tenant user exists | 1. Log in as `acme_supervisor_1` (non-admin staff per [seed_tenants](apps/tenants/management/commands/seed_tenants.py)) 2. Visit `/qms/iqc/plans/new/` | Staff creds | Redirected back to dashboard with red error toast `Only tenant administrators can access that page.` | | |
| TC-AUTH-07 | Staff user CAN file an inspection (operator role) | Logged in as staff | 1. Visit `/qms/iqc/inspections/new/` | Staff creds | Page loads (200) — inspection filing is operator-level, not admin-only | | |

### 4.2 Multi-Tenancy Isolation

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Acme admin sees only Acme NCRs | Logged in as `admin_acme` | 1. Visit `/qms/ncr/` 2. Note all 4 NCR numbers shown | NCR-00001..NCR-00004 | Only Acme's 4 NCRs are visible. None show Globex / Stark data. | | |
| TC-TENANT-02 | Cross-tenant NCR detail returns 404 | DB has Globex NCRs (slug `globex`) | 1. As `admin_acme`, find a Globex NCR pk via Django admin (`/admin/qms/nonconformancereport/` filter by tenant=Globex) 2. Note pk = X 3. Visit `/qms/ncr/X/` directly | A Globex NCR pk | HTTP 404 (or "Not Found"). The NCR is NOT shown. | | |
| TC-TENANT-03 | Cross-tenant equipment detail returns 404 | DB has Globex equipment | 1. As `admin_acme`, get a Globex equipment pk from `/admin/` 2. Visit `/qms/equipment/<globex-pk>/` | Globex equipment pk | HTTP 404 | | |
| TC-TENANT-04 | Cross-tenant IQC plan delete blocked | Logged in as `admin_acme` | 1. Get a Globex IQC plan pk from admin 2. Construct a POST manually to `/qms/iqc/plans/<globex-pk>/delete/` (use DevTools fetch + CSRF token) | Globex pk | 404 returned. The Globex plan is NOT deleted. | | |
| TC-TENANT-05 | Auth-gated NCR attachment download cross-tenant 404 | Globex NCR has an attachment | 1. As `admin_acme`, visit `/qms/ncr/attachments/<globex-attachment-pk>/download/` | Globex attachment pk | HTTP 404. File NOT served. | | |
| TC-TENANT-06 | Auth-gated calibration certificate cross-tenant 404 | Globex calibration with cert exists | 1. As `admin_acme`, visit `/qms/calibrations/<globex-pk>/certificate/` | Globex pk | HTTP 404 | | |

### 4.3 CREATE

#### 4.3.1 IQC Plan

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-01 | Create IQC plan with all fields | At least 1 raw_material/component product exists | 1. Click **IQC Plans** in sidebar 2. Click **+ New Plan** 3. Pick a Product 4. AQL Level: `II` 5. Sample Method: `single` 6. AQL Value: `2.5` 7. Version: `1.0-test` 8. Description: `Manual test plan` 9. Tick `Is active` 10. Click **Save** | Form data above | Redirect to `/qms/iqc/plans/<pk>/`. Green toast `IQC plan created.` Plan appears in list. | | |
| TC-CREATE-02 | Create IQC plan with required only | Same | 1. **+ New Plan** 2. Pick product, leave description blank 3. Save | Required only | 200 → detail page. Optional fields blank. | | |
| TC-CREATE-03 | Create IQC plan duplicate version (Lesson L-01) | Plan with version `1.0-test` exists for product X | 1. **+ New Plan** 2. Pick same product X, version `1.0-test` 3. Save | Same product + version | Form re-renders with red error under **Version**: `A plan with this product + version already exists.` **NOT a 500.** | | |
| TC-CREATE-04 | Create IQC plan with negative AQL | Same | 1. **+ New Plan** 2. AQL Value `-1` 3. Save | aql_value=-1 | Red error under **AQL value**. (HTML5 + server-side validator both catch.) | | |
| TC-CREATE-05 | Create IQC plan with AQL > 100 | Same | 1. AQL value `150` 2. Save | aql_value=150 | Red error under **AQL value**. | | |
| TC-CREATE-06 | Special chars in description | Same | 1. Description: `<script>alert(1)</script> & 'quote' "double" emoji 🛠` 2. Save | XSS payload | Saved successfully. On detail page, `<script>` is rendered as escaped text — NO alert popup. | | |

#### 4.3.2 IQC Inspection

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-10 | Create IQC inspection auto-numbers | At least 1 IQC plan exists | 1. **IQC Inspections** sidebar 2. Click **+ New Inspection** 3. Pick product, plan 4. Supplier: `Supplier QA` 5. PO: `PO-MAN-001` 6. Lot: `LOT-MAN-001` 7. Received qty: `500` 8. Save | qty=500 | Redirect to detail. Toast: `IQC inspection IQC-NNNNN created (sample size 50, accept up to 5).` Sample/Ac/Re computed from AQL service. | | |
| TC-CREATE-11 | AQL plan applies sample size | Plan AQL=2.5, level=II, qty=500 → sample=50 Ac=5 | After TC-CREATE-10 detail page | Verify | "Sample / Accept / Reject" row shows `50 / 5 / 6` | | |
| TC-CREATE-12 | Negative received qty rejected | Same | 1. Same form, received_qty `-10` 2. Save | qty=-10 | Form error. NO row created. | | |
| TC-CREATE-13 | Required field missing | Same | 1. Leave Product blank 2. Save | empty product | Red `This field is required` under Product. | | |

#### 4.3.3 NCR

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-20 | Raise NCR auto-numbers + creates RCA shell | Logged in as admin_acme | 1. **NCRs & CAPA** sidebar 2. Click **Raise NCR** 3. Source: `customer` 4. Severity: `major` 5. Title: `Manual test NCR` 6. Description: `Customer reported defect` 7. Pick a product 8. Lot: `LOT-NCR-MAN` 9. Quantity affected: `1` 10. Save | Form above | Redirect to detail. Toast `NCR NCR-NNNNN raised.` In Root Cause tab, the empty RCA form is already present (auto-created shell). | | |
| TC-CREATE-21 | NCR title required | Same | 1. **Raise NCR** 2. Leave Title blank 3. Save | empty title | Red error under Title. | | |

#### 4.3.4 Equipment

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-30 | Add equipment auto-numbers | Logged in as admin_acme | 1. **Equipment** sidebar 2. Click **+ Add Equipment** 3. Name: `Manual Test Caliper` 4. Type: `caliper` 5. Serial: `SN-MAN-001` 6. Manufacturer: `TestMfg` 7. Calibration interval: `365` 8. Status: `active` 9. Save | Form above | Redirect to detail. Toast `Equipment EQP-NNNNN added.` | | |
| TC-CREATE-31 | Duplicate serial blocked (Lesson L-01) | Equipment with serial `SN-MAN-001` exists | 1. **+ Add Equipment** 2. Serial: `SN-MAN-001` 3. Save | Dup serial | Red error under **Serial number**: `Serial number already used in this tenant.` **NOT a 500.** | | |
| TC-CREATE-32 | Calibration interval below min | Same | 1. Interval: `0` 2. Save | interval=0 | Red error. | | |
| TC-CREATE-33 | Calibration interval above max | Same | 1. Interval: `10000` 2. Save | interval=10000 | Red error (max 3650). | | |

#### 4.3.5 IPQC Plan + auto-create SPC chart

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-40 | Create IPQC plan with X-bar/R auto-creates chart | At least 1 routing operation exists | 1. **IPQC Plans** sidebar 2. **+ New Plan** 3. Product, Routing operation, Name `Manual IPQC` 4. Frequency `every_n_parts`, value 10 5. Chart type `x_bar_r`, subgroup size 5 6. Nominal 100, USL 100.5, LSL 99.5 7. Save | x_bar_r | Redirect to plan detail. Detail shows **SPC Chart** button in header (chart auto-created). | | |
| TC-CREATE-41 | Create IPQC plan with `none` chart | Same | 1. Same form but chart_type `none` 2. Save | chart_type=none | Redirect. **SPC Chart** button NOT shown (no chart created). | | |
| TC-CREATE-42 | Duplicate product+op pair blocked | Plan exists for (P, op) | 1. **+ New Plan** 2. Same product, same routing operation 3. Save | dup pair | Red error under Routing operation: `An IPQC plan already exists for this product + operation.` | | |

#### 4.3.6 FQC Plan + Test Specs

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-50 | Create FQC plan + add test specs inline | Finished good exists | 1. **FQC Plans** sidebar 2. **+ New Plan** 3. Pick FG product, name `Manual FQC`, version `1.0-m` 4. Save 5. On detail, scroll to **Add Test Spec** 6. Sequence 10, Test name `Visual`, method `visual` 7. Click **Add** | Plan + spec | Plan saved. After spec add, table shows new spec row. | | |

#### 4.3.7 Calibration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-60 | File calibration record auto-numbers | Equipment exists with interval=365 | 1. **Calibrations** sidebar 2. **File Calibration** 3. Pick equipment 4. Calibrated at: today 14:00 5. Result: `pass` 6. Notes: `Manual cal test` 7. Save | Form above | Redirect to record detail. Toast `Calibration CAL-NNNNN recorded.` | | |
| TC-CREATE-61 | Equipment next_due_at updated by signal (Lesson L-15) | TC-CREATE-60 just done | 1. Visit equipment detail | Check sidebar | "Last calibrated" = today 14:00. "Next due" = today 14:00 + 365 days. | | |
| TC-CREATE-62 | Result=fail without notes blocked (Lesson L-14) | Same | 1. **File Calibration** 2. Result `fail`, notes blank 3. Save | result=fail, notes='' | Red error under Notes: `Notes are required when result is Fail.` | | |
| TC-CREATE-63 | Result=fail WITH notes accepted | Same | 1. **File Calibration** 2. Result `fail`, notes `Tool damaged - sent for repair.` 3. Save | result=fail, notes='..' | Saved successfully. | | |

### 4.4 READ — List Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-01 | IQC inspection list shows columns | Seed data present | 1. Visit `/qms/iqc/inspections/` | — | Columns: IQC#, Product, Supplier, Lot, Received, Sample (with Ac/Re), Status, Actions. No `None` literals. | | |
| TC-LIST-02 | IQC inspection status badges colored | Seed produces all 5 statuses | 1. Same page | — | `Accepted` = green, `Rejected` = red, `Deviation` = yellow, `In Inspection` = blue, `Pending` = grey. | | |
| TC-LIST-03 | NCR list shows severity badges | Seed has minor/major/critical | 1. Visit `/qms/ncr/` | — | `Critical` = red, `Major` = yellow, `Minor` = grey. | | |
| TC-LIST-04 | Equipment list shows due-soon RED row | Seeded equipment "Micrometer 0-25mm" overdue, "Digital caliper" due in 5 days | 1. Visit `/qms/equipment/` | — | Caliper row has yellow background (≤ 7d). Micrometer row has red background (overdue). | | |
| TC-LIST-05 | Equipment due tracker filter `?due=overdue` | Same | 1. Use Due dropdown → `Overdue` 2. **Filter** | due=overdue | Only the overdue Micrometer row shown. | | |
| TC-LIST-06 | Calibration record list shows result badges | Seeded includes pass / pass_with_adjustment / fail | 1. Visit `/qms/calibrations/` | — | Pass=green, Pass w/Adj=yellow, Fail=red. | | |
| TC-LIST-07 | SPC chart list shows UCL/CL/LCL summary | Seed populates 1 chart | 1. Visit `/qms/ipqc/charts/` | — | Row shows numeric UCL / CL / LCL values (computed from compute_xbar_r). | | |
| TC-LIST-08 | Empty list state | Tenant with no data (e.g., new tenant) | 1. Create a tenant via Django admin with no QMS data 2. Log in as that tenant admin 3. Visit `/qms/iqc/plans/` | empty list | Empty-state message: `No IQC plans yet.` Centered grey text under empty table. | | |

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DETAIL-01 | IQC inspection detail shows AQL plan + measurements | Inspection IQC-00001 from seed | 1. Visit `/qms/iqc/inspections/1/` | — | Sample/Ac/Re visible. If accepted, measurements section populated. Linked NCRs panel in sidebar. | | |
| TC-DETAIL-02 | IPQC inspection detail with linked SPC point | Seed populates 25 points | 1. Visit `/qms/ipqc/inspections/1/` | — | Detail page renders. Result badge correct. Plan link works. | | |
| TC-DETAIL-03 | SPC chart renders ApexCharts UCL/LCL annotations | Chart with 25 points seeded | 1. Visit `/qms/ipqc/charts/1/` | — | Apex line chart visible with: blue line + markers, red dashed UCL line, green dashed CL, red dashed LCL. The OOC point (subgroup 13, value ~103) has different (red) color. Out-of-control points table on right shows that subgroup with rule violations. | | |
| TC-DETAIL-04 | SPC chart no JS console errors (Lesson L-07) | Same | 1. F12 → Console tab 2. Visit chart detail | — | No `Uncaught` errors. Specifically: no `JSON.parse` errors. Series data was passed via `{% json_script %}`. | | |
| TC-DETAIL-05 | NCR detail tabs work | Seed NCR with RCA + 1 CA + 1 PA | 1. Visit `/qms/ncr/1/` 2. Click each of: Root Cause, Corrective Actions, Preventive Actions, Attachments tabs | — | Each tab content panel becomes visible. Badge counts on tab labels match data. | | |
| TC-DETAIL-06 | Equipment detail shows calibration history | Equipment with 1+ calibration records | 1. Visit `/qms/equipment/1/` | — | History table shows record numbers, dates, results, certificate download buttons (if cert uploaded). | | |
| TC-DETAIL-07 | FQC inspection passed shows CoA card | Seeded FQC-00001 passed with CoA | 1. Visit `/qms/fqc/inspections/<passed-pk>/` | — | "Certificate of Analysis" card in sidebar with COA-NNNN, issued date, customer, View CoA link. | | |

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit IQC plan pre-fills fields | Plan exists | 1. List → Pencil icon on plan row | — | Form shows current values: product selected, AQL level/value/version pre-filled. | | |
| TC-EDIT-02 | Save edit persists | Same | 1. Change Description to `Edited` 2. Save | — | Redirect to detail. New description shown. Toast `IQC plan updated.` | | |
| TC-EDIT-03 | Edit IQC inspection blocked when accepted | An accepted IQC inspection (status='accepted') | 1. Visit detail page of the accepted inspection | — | Edit pencil icon NOT shown. URL `/qms/iqc/inspections/<pk>/edit/` redirects with warning toast `Inspection is no longer editable in this status.` | | |
| TC-EDIT-04 | Edit NCR blocked when closed | Closed NCR exists (e.g., NCR-00004 from seed) | 1. Visit `/qms/ncr/<closed-pk>/` | — | Edit button hidden. URL `/qms/ncr/<closed-pk>/edit/` redirects with warning. | | |
| TC-EDIT-05 | Edit equipment | Active equipment exists | 1. Visit equipment detail → **Edit** 2. Change name 3. Save | — | Persists. Toast. | | |
| TC-EDIT-06 | Edit calibration record | Cal record exists | 1. List → Pencil icon 2. Update notes 3. Save | — | Persists. | | |
| TC-EDIT-07 | Edit FQC inspection blocked when passed | Passed FQC exists | 1. Visit detail | — | Edit button hidden. | | |
| TC-EDIT-08 | Browser back after edit does not resubmit | TC-EDIT-02 just done | 1. Press browser **Back** | — | Returns to edit form (or list) without a duplicate save. No extra toast. | | |

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete IQC plan with confirm | Plan with no inspections | 1. List → Bin icon 2. JS confirm: `Delete this plan?` → **OK** | — | Redirect to list. Toast `IQC plan deleted.` Row gone. | | |
| TC-DELETE-02 | Cancel delete dialog does nothing | Same | 1. Bin icon 2. JS confirm → **Cancel** | — | Page unchanged. Plan still in list. | | |
| TC-DELETE-03 | Delete IQC plan with inspections blocked | Plan referenced by an inspection | 1. List → Bin icon 2. **OK** | — | Redirect to detail. Red toast `Cannot delete - plan is referenced by inspections.` | | |
| TC-DELETE-04 | Delete IQC inspection blocked when accepted | Accepted inspection | 1. List row of accepted: bin icon should NOT be visible (status=accepted) | — | Bin icon hidden. Direct POST returns redirect with red error `Cannot delete a completed IQC inspection.` | | |
| TC-DELETE-05 | Delete NCR blocked unless open/cancelled | NCR with status `investigating` | 1. List row | — | Bin icon hidden (status not in `open` / `cancelled`). | | |
| TC-DELETE-06 | Delete NCR open works | NCR with status `open` | 1. Bin icon → confirm | — | Deleted. Toast. | | |
| TC-DELETE-07 | Delete equipment with cal history blocked | Equipment with at least 1 cal record | 1. List → bin icon → confirm | — | Red toast `Cannot delete - equipment has calibration history.` (ProtectedError) | | |
| TC-DELETE-08 | Delete calibration record | Record exists | 1. Detail → Delete (or list bin) → confirm | — | Deleted. Returns to list. | | |

### 4.8 SEARCH

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-SEARCH-01 | Empty search returns all | List page | 1. Visit `/qms/ncr/` 2. Empty `q` → Filter | — | All NCRs shown. | | |
| TC-SEARCH-02 | Search NCR by number | Seed NCR-00001 | 1. Search box: `NCR-00001` 2. Filter | q=NCR-00001 | Only NCR-00001 shown. | | |
| TC-SEARCH-03 | Search NCR by partial title | Seeded NCR title contains "drift" | 1. Search: `drift` 2. Filter | q=drift | NCR with "drift" in title shown. | | |
| TC-SEARCH-04 | Search case-insensitive | Same | 1. Search: `DRIFT` 2. Filter | q=DRIFT (uppercase) | Same row matched. | | |
| TC-SEARCH-05 | Search trims whitespace | Same | 1. Search: `   drift   ` 2. Filter | q=' drift ' | Same row matched (per `request.GET.get('q', '').strip()`). | | |
| TC-SEARCH-06 | Special chars don't 500 | Same | 1. Search: `<script>'%_` 2. Filter | malicious chars | List empty (no match). NO 500. NO XSS in echoed search box. | | |
| TC-SEARCH-07 | Search no match shows empty | Same | 1. Search: `zzzzz-no-match` | — | Empty body row: `No NCRs yet.` (or list-specific empty). | | |
| TC-SEARCH-08 | Search by IQC supplier | IQC inspection seeded with supplier "Supplier A Co." | 1. `/qms/iqc/inspections/?q=Supplier A` | q=Supplier+A | Inspection(s) with that supplier shown. | | |
| TC-SEARCH-09 | Search equipment by serial | Seeded equipment | 1. `/qms/equipment/?q=CALIPER-001` | q=CALIPER-001 | Equipment row shown. | | |

### 4.9 PAGINATION

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-PAGE-01 | Default page size 25 (NCR list) | At least 26 NCRs (across all 3 tenants — single tenant only has 4 in seed; create 26 via repeated POST or use Django admin to insert) | 1. Visit `/qms/ncr/` 2. Count rows | — | 25 rows on page 1. Pagination footer `1 / 2`. | | |
| TC-PAGE-02 | Click page 2 | Same | 1. Click `»` arrow | — | Remaining rows shown. URL has `?page=2`. | | |
| TC-PAGE-03 | Pagination retains filter (CLAUDE.md rule) | More than one page of NCRs with status=open | 1. Filter status=open 2. Click page 2 | — | URL has `?status=open&page=2`. Status dropdown retains `Open` selected. | | |
| TC-PAGE-04 | Invalid page number | Same | 1. Manually edit URL `?page=abc` | page=abc | Graceful — does NOT 500. (Django ListView raises 404 for invalid integer; or shows page 1.) | | |
| TC-PAGE-05 | Beyond last page | Same | 1. Manually edit URL `?page=999` | page=999 | 404 (not 500). Or shows last page gracefully. | | |
| TC-PAGE-06 | Pagination retains search | More than 25 records | 1. Search: `LOT` 2. Click page 2 | — | URL has `?q=LOT&page=2`. Search box still shows `LOT`. | | |

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-FILTER-01 | NCR severity filter | Seed has critical/major/minor | 1. `/qms/ncr/` → Severity dropdown → `Critical` → Filter | — | Only critical NCRs shown. Dropdown still says `Critical`. | | |
| TC-FILTER-02 | NCR source filter | Seed has 4 sources | 1. Source → `Customer Complaint` → Filter | — | Only customer-source NCRs shown. | | |
| TC-FILTER-03 | NCR combined filters AND | Same | 1. Severity=`Major` + Status=`Investigating` 2. Filter | — | Only major + investigating. | | |
| TC-FILTER-04 | IQC inspection status filter | Seed mix | 1. `/qms/iqc/inspections/?status=accepted` | — | Only accepted shown. | | |
| TC-FILTER-05 | IPQC plan chart_type filter | Seeded with `x_bar_r` and `none` | 1. `/qms/ipqc/plans/?chart_type=x_bar_r` | — | Only X-bar/R plans shown. | | |
| TC-FILTER-06 | Equipment due-soon filter | Seeded 1 due-in-5d, 1 overdue | 1. `/qms/equipment/?due=soon` | — | Both rows shown (`overdue` is also `≤7d`). | | |
| TC-FILTER-07 | Equipment type filter | Seed has caliper / micrometer / etc. | 1. Type dropdown → `Caliper` → Filter | — | Only caliper rows. | | |
| TC-FILTER-08 | Calibration result filter | Seed has pass/fail/with-adj | 1. `/qms/calibrations/?result=fail` | — | Only fail rows (1 per tenant). | | |
| TC-FILTER-09 | Filter retains across pagination | TC-PAGE-03 verified | 1. Filter + page 2 | — | URL preserves both `?status=...&page=2`. | | |
| TC-FILTER-10 | Filter for empty match | Same | 1. Filter status=`cancelled` (NCR has no cancelled in seed) | — | Empty body. List header still shows. | | |
| TC-FILTER-11 | Calibration standard active filter | Standards exist | 1. `/qms/calibration-standards/?active=active` | — | Only active. | | |

### 4.11 Status Transitions / Custom Actions

#### IQC inspection workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-01 | Pending → in_inspection | Pending IQC inspection exists | 1. Detail page 2. Click **Start** | — | Status badge `In Inspection`. Toast `Inspection started.` Inspector + inspected_at populated. | | |
| TC-ACTION-02 | In_inspection → accepted | TC-ACTION-01 done | 1. **Accept** | — | Status badge `Accepted`. Toast. Acccept/Reject/Deviation buttons gone. | | |
| TC-ACTION-03 | In_inspection → rejected | Another in_inspection | 1. **Reject** → confirm | — | Status `Rejected`. | | |
| TC-ACTION-04 | In_inspection → released-with-deviation (admin only) | Same | 1. As admin: **Deviation** → confirm | — | Status `Released with Deviation`. | | |
| TC-ACTION-05 | Skip transition rejected (Lesson L-03) | Pending IQC | 1. As DevTools, manually POST to `/qms/iqc/inspections/<pk>/accept/` (skipping start) | crafted POST | Redirect with warning. Status remains `pending`. | | |

#### FQC inspection workflow + CoA

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-10 | Pending → in_inspection → passed | Pending FQC | 1. **Start** 2. **Pass** | — | Status `Passed`. CoA generation button now visible. | | |
| TC-ACTION-11 | Generate CoA | Just-passed FQC | 1. Click **Generate CoA** | — | New page at `/qms/fqc/inspections/<pk>/coa/`. CoA renders with header, customer fields, test result table, signature lines. | | |
| TC-ACTION-12 | Print CoA | On CoA page | 1. Click **Print / Save as PDF** | — | Browser print dialog opens. Print preview shows ONLY CoA content (chrome hidden by `@media print`). | | |
| TC-ACTION-13 | Update CoA customer info | Same | 1. Bottom form: Customer Name `Test Customer`, Reference `PO-123` → Save | — | Page reloads with values populated in body. Toast `CoA updated.` | | |
| TC-ACTION-14 | Release CoA to customer | TC-ACTION-13 done | 1. **Release to Customer** → confirm | — | Green badge `Released to customer`. Form below disappears. | | |
| TC-ACTION-15 | CoA blocked for failed FQC | Failed FQC | 1. Visit `/qms/fqc/inspections/<failed-pk>/coa/` directly | — | Redirect to detail with warning `CoA can only be generated for passed or release-with-deviation inspections.` | | |
| TC-ACTION-16 | Failed FQC | Pending FQC | 1. Start → Fail → confirm | — | Status `Failed`. CoA button NOT shown. | | |

#### NCR workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-20 | open → investigating | Open NCR | 1. **Investigate** | — | Status badge `Investigating`. | | |
| TC-ACTION-21 | investigating → awaiting_capa | TC-ACTION-20 done | 1. **Awaiting CAPA** | — | Status `Awaiting CAPA`. | | |
| TC-ACTION-22 | awaiting_capa → resolved | Same | 1. **Resolve** | — | Status `Resolved`. **Close NCR** card appears in sidebar. | | |
| TC-ACTION-23 | Close requires summary (Lesson L-14) | Resolved NCR | 1. Sidebar "Close NCR" form: leave summary blank 2. **Close NCR** | — | Form re-renders with red error `A resolution summary is required when closing an NCR.` Status remains `Resolved`. | | |
| TC-ACTION-24 | Close with summary works | Same | 1. Summary `All actions verified effective.` 2. **Close NCR** | — | Status `Closed`. closed_by + closed_at stamped. Toast `NCR closed.` | | |
| TC-ACTION-25 | Cancel NCR from any non-terminal | Open NCR | 1. **Cancel** → confirm | — | Status `Cancelled`. Edit/Delete buttons hidden. | | |

#### Corrective / Preventive Actions

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-30 | Add corrective action | NCR open | 1. NCR detail → CA tab → fill action_text, owner, due_date 2. **Add** | — | Row added. Status badge `Open`. | | |
| TC-ACTION-31 | Edit CA | TC-ACTION-30 done | 1. CA row → Pencil → change text → Save | — | Persists. Redirect to NCR detail. | | |
| TC-ACTION-32 | Complete CA | Same | 1. Green check icon | — | Status `Done`. completed_at stamped. | | |
| TC-ACTION-33 | Delete CA | Same | 1. Bin icon → confirm | — | Removed. Count badge decrements. | | |
| TC-ACTION-34 | Same flow for PA | Same | Repeat 30-33 on Preventive Actions tab | — | All work. | | |

#### NCR Attachment

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-40 | Upload PDF attachment | Open NCR | 1. Attachments tab → choose `report.pdf` (small file) → description `Lab report` → **Upload** | small.pdf | Row appears with description. | | |
| TC-ACTION-41 | Reject .exe upload (allowlist) | Same | 1. Choose `virus.exe` → **Upload** | virus.exe | Form error `Unsupported file type. Allowed: .pdf .png ...` | | |
| TC-ACTION-42 | Reject 26 MB upload | Same | 1. Choose 26 MB file → **Upload** | big.pdf | Form error `File exceeds the 25 MB limit.` | | |
| TC-ACTION-43 | Auth-gated download | TC-ACTION-40 done | 1. Click attachment link in row | — | File downloads (200 + Content-Disposition: attachment). | | |

#### Equipment retire

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-50 | Retire equipment | Active equipment | 1. Detail → **Retire** → confirm | — | Status `Retired`. Edit/Calibrate/Retire buttons gone. is_active=False. | | |

#### SPC chart recompute

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-60 | Recompute SPC limits | Chart with 25+ inspections | 1. Chart detail → **Recompute Limits** | — | Page reloads. Toast `Recomputed limits from N subgroups.` UCL/CL/LCL values updated. recomputed_at timestamp updated. | | |
| TC-ACTION-61 | Recompute with too few subgroups | Chart with < subgroup_size measurements | 1. **Recompute Limits** | — | Yellow toast `Need at least N measurements to compute limits.` Limits unchanged. | | |

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-UI-01 | Browser tab title | Each page | 1. Look at browser tab | — | Reads e.g. `IQC Inspections`, `NCR-00001`, `SPC Chart - <plan>`. | | |
| TC-UI-02 | Sidebar active state | On any QMS page | 1. Visual check | — | "Quality (QMS)" group is expanded; current sub-link is highlighted. | | |
| TC-UI-03 | Empty state CTA | New tenant, IQC plans empty | 1. `/qms/iqc/plans/` 2. List body | — | Centered grey text `No IQC plans yet.` (no icon — acceptable for v1). | | |
| TC-UI-04 | Toasts auto-dismiss | After any save | 1. Save anything 2. Wait | — | Green toast appears for ~3s and auto-dismisses. (Or persists till page nav — verify UX matches MES pattern.) | | |
| TC-UI-05 | Confirm dialog shows entity name | Delete prompt | 1. Click bin icon | — | JS `confirm()` shows `Delete this plan?` (or similar). | | |
| TC-UI-06 | Required field markers | Create form | 1. Visit `/qms/iqc/plans/new/` | — | Required fields (Product, AQL Level, Sample Method, AQL Value, Version) have `*` rendered by crispy-forms. | | |
| TC-UI-07 | Mobile viewport — list page | Chrome DevTools 375×667 | 1. Toggle device toolbar 2. Visit `/qms/ncr/` | — | Table is scrollable horizontally (`.table-responsive`). No content cut off. Sidebar collapses into burger. | | |
| TC-UI-08 | Mobile viewport — SPC chart | Same | 1. Visit chart detail | — | ApexCharts shrinks to width. UCL/LCL annotations visible. | | |
| TC-UI-09 | Tablet viewport (768×1024) | Same | 1. Test 3 random pages | — | No overlap, no horizontal page scroll. | | |
| TC-UI-10 | Long text wraps in NCR description | Create NCR with 500-char description | 1. Detail page | — | Description wraps cleanly inside the card. No horizontal overflow. | | |
| TC-UI-11 | Keyboard nav | On create form | 1. Tab through fields | — | Focus moves field → field → submit button in document order. Focus ring visible. | | |
| TC-UI-12 | Form submits on Enter | NCR form | 1. From last field, press Enter | — | Form submits (does NOT only submit on Save click). | | |
| TC-UI-13 | No DevTools console errors | Walk every page | 1. Console open 2. Visit each of 21 routes | — | No `Uncaught` errors. (Network 4xx for missing favicon is OK.) | | |
| TC-UI-14 | NCR detail tab badges show counts | NCR with 2 CAs and 1 PA | 1. Detail page | — | Tab labels show `Corrective Actions (2)` and `Preventive Actions (1)`. | | |
| TC-UI-15 | Equipment due-soon yellow + overdue red | Seeded mix | 1. `/qms/equipment/` | — | Two distinct row colors visible. Yellow = warning class, red = danger class. | | |

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-NEG-01 | All required blanks → all errors at once | New IQC plan form | 1. Click Save with everything blank | empty form | Multiple red `This field is required.` errors. Form not submitted. | | |
| TC-NEG-02 | Decimal field with letters | New equipment | 1. Tolerance: `abc` 2. Save | tolerance=abc | Browser blocks (HTML5 number input) OR server-side `Enter a number` error. | | |
| TC-NEG-03 | Negative quantity affected on NCR | Same | 1. Quantity affected: `-5` 2. Save | qty=-5 | Form error (MinValueValidator). | | |
| TC-NEG-04 | Future calibration date | New cal record | 1. Calibrated at: `2099-01-01 12:00` 2. Save | future date | Saves (no future-block enforced — note as NOT a defect, just behavior). | | |
| TC-NEG-05 | Submit form twice rapidly | Create NCR | 1. Click Save twice fast | double-click | Either: only one NCR created (idempotent), or duplicate detected (form-level error). NEVER 2 identical rows. | | |
| TC-NEG-06 | Refresh after POST | After saving | 1. Save → on detail/list 2. F5 | — | No duplicate save toast. (GET-after-POST pattern in views.) | | |
| TC-NEG-07 | XSS in NCR title | Create NCR | 1. Title: `<img src=x onerror=alert(1)>` | XSS payload | Saved. On detail, rendered as escaped text. NO alert popup. | | |
| TC-NEG-08 | SQL meta in search | Any list page | 1. Search: `' OR 1=1 --` | SQLi attempt | Empty result (no match), no 500. Django ORM uses params. | | |
| TC-NEG-09 | URL pk = 0 | Any detail | 1. Visit `/qms/ncr/0/` | pk=0 | 404. | | |
| TC-NEG-10 | URL pk = abc | Any detail | 1. Visit `/qms/ncr/abc/` | pk=abc | 404 (path converter `<int:pk>` rejects). | | |
| TC-NEG-11 | Whitespace-only resolution summary | Resolved NCR close | 1. Summary: `   ` (spaces) 2. Close | whitespace | Form error (Lesson L-14: `clean_resolution_summary` strips). | | |
| TC-NEG-12 | Concurrent close race (Lesson L-03) | Two browser tabs on resolved NCR | 1. Tab 1: Close with summary 2. Tab 2: Click Cancel without refresh | concurrent | Tab 1 closes successfully. Tab 2 returns warning `NCR cannot be cancelled now.` (already closed). NO 500. | | |
| TC-NEG-13 | Recompute SPC chart with all-identical values | Plan + 5 inspections all value=100 | 1. Recompute | identical | Limits compute (R=0). Toast green. Chart limits all equal CL. | | |
| TC-NEG-14 | Calibration result=fail without notes | Cal form | 1. Result fail, notes empty 2. Save | (Lesson L-14) | Red error `Notes are required when result is Fail.` | | |
| TC-NEG-15 | Equipment status retired then edited | Retired equipment | 1. Visit edit | — | Form loads but `status` dropdown does not include retired again. (Or accept v1 behavior — note observed.) | | |
| TC-NEG-16 | NCR delete blocked for closed | Closed NCR | 1. Manually craft POST to `/qms/ncr/<closed-pk>/delete/` | crafted | Red toast `Only open or cancelled NCRs can be deleted - cancel first.` Status unchanged. | | |

### 4.14 Cross-Module Integration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-INT-01 | NCR raised from IQC inspection links back | Any IQC inspection | 1. Inspection detail → Raise NCR (sidebar button) 2. Fill form, leave the URL `?source=iqc` query param | — | NCR `source` defaults sensibly. After save, NCR detail's IQC source row links back. | | |
| TC-INT-02 | IPQC inspection links to MES op | Seed has IPQC tied to MES op | 1. IPQC inspection detail | — | "Work Order Op" row links to `/mes/operations/<pk>/` and is clickable. | | |
| TC-INT-03 | FQC inspection links to MES work order | Seed has FQC tied to WO | 1. FQC detail | — | "Work Order" row links to `/mes/work-orders/<pk>/`. | | |
| TC-INT-04 | IPQC plan links to PPS routing op | Seed plan tied to routing | 1. Plan detail | — | Operation header shows `#NN <name>` (text only — no link required). | | |
| TC-INT-05 | Equipment assigned work_center | Seed equipment | 1. Equipment list | — | Location column shows work-center code. | | |
| TC-INT-06 | NCR product link goes to PLM | NCR with product | 1. NCR detail | — | Product field shows SKU. (No deep link required in v1; verify SKU text accuracy.) | | |
| TC-INT-07 | Calibration record propagates to equipment.next_due_at (Lesson L-15) | Equipment + new cal | 1. File cal record 2. Visit equipment detail | — | last_calibrated_at = cal date. next_due_at = cal date + interval_days. Verified by signal. | | |
| TC-INT-08 | Audit log entry on NCR creation (signals) | Open `/admin/tenants/tenantauditlog/` after NCR creation | 1. Filter by action=`qms_ncr.created` | — | At least 1 row exists for the new NCR. | | |
| TC-INT-09 | Audit log on NCR close | After TC-ACTION-24 | 1. Filter audit log for `qms_ncr.closed` | — | Row exists with from→to in meta. | | |
| TC-INT-10 | Audit log on calibration creation | After TC-CREATE-60 | 1. Filter for `qms_calibration.created` | — | Row exists. | | |

---

## 5. Bug Log

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Screenshot | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | | | | | | | | |
| BUG-02 | | | | | | | | |
| BUG-03 | | | | | | | | |
| BUG-04 | | | | | | | | |
| BUG-05 | | | | | | | | |

> Severity definitions:
> - **Critical** — data loss, security hole (XSS / IDOR / privilege escalation), 500 on golden path, blocker for release
> - **High** — broken core CRUD, broken workflow transition, broken multi-tenant isolation
> - **Medium** — broken filter, broken pagination, missing validation, wrong status badge color
> - **Low** — UX inconsistency, copy issue, layout glitch
> - **Cosmetic** — typo, alignment-by-1px, missing icon

---

## 6. Sign-off & Release Recommendation

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---|---|---|---|---|
| 4.1 Authentication & Access | 7 | | | | |
| 4.2 Multi-Tenancy Isolation | 6 | | | | |
| 4.3 CREATE | 22 | | | | |
| 4.4 READ — List | 8 | | | | |
| 4.5 READ — Detail | 7 | | | | |
| 4.6 UPDATE | 8 | | | | |
| 4.7 DELETE | 8 | | | | |
| 4.8 SEARCH | 9 | | | | |
| 4.9 PAGINATION | 6 | | | | |
| 4.10 FILTERS | 11 | | | | |
| 4.11 Status / Custom Actions | 30 | | | | |
| 4.12 Frontend UI/UX | 15 | | | | |
| 4.13 Negative & Edge | 16 | | | | |
| 4.14 Cross-Module Integration | 10 | | | | |
| **TOTAL** | **163** | | | | |

**Release Recommendation**:
☐ **GO** — all critical/high pass, no blockers
☐ **GO-with-fixes** — non-blocking issues filed, scheduled for next sprint
☐ **NO-GO** — at least one critical fail, must re-test before release

**Rationale (one sentence)**: ____________________________________________

Tester signature: __________________ Date: __________

---

## Appendix — Quick smoke subset (90 minutes)

If short on time, run **only** these test IDs for a smoke pass:

- TC-AUTH-05 (admin can access full QMS)
- TC-TENANT-02 (cross-tenant 404)
- TC-CREATE-10, TC-CREATE-11 (IQC inspection auto-AQL)
- TC-CREATE-20 (NCR raise + auto RCA shell)
- TC-CREATE-30, TC-CREATE-60, TC-CREATE-61 (equipment + calibration + L-15 propagation)
- TC-LIST-04, TC-LIST-05 (equipment due-tracker red/yellow + filter)
- TC-DETAIL-03, TC-DETAIL-04 (SPC chart renders + no JS errors)
- TC-DETAIL-07 (FQC CoA card)
- TC-EDIT-03, TC-EDIT-04 (status-gated edit blocked)
- TC-DELETE-03, TC-DELETE-07 (ProtectedError surfaces cleanly)
- TC-ACTION-10, TC-ACTION-11, TC-ACTION-13, TC-ACTION-14 (FQC → CoA → release)
- TC-ACTION-20, TC-ACTION-21, TC-ACTION-22, TC-ACTION-23, TC-ACTION-24 (NCR full lifecycle + L-14 close-requires-summary)
- TC-ACTION-41 (allowlist rejects .exe)
- TC-ACTION-60 (SPC recompute)
- TC-NEG-07 (XSS escaped)
- TC-INT-07 (L-15 calibration → equipment propagation)

That's **22 test cases** covering the riskiest surfaces. ~90 minutes for a focused tester.
