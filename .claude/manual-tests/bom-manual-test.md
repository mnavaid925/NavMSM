# Bill of Materials (BOM) Management — Manual Test Plan

> Generated 2026-04-26 · Target module: `apps.bom` (Module 3 — Multi-Level BOM, Versioning, Alternates, Cost Roll-Up, EBOM/MBOM/SBOM Sync)
> Tester fills the **Pass/Fail** and **Notes** columns as they go. Use the [Bug Log](#5-bug-log) to record defects.

---

## 1. Scope & Objectives

This plan validates the full BOM module shipped under [apps/bom/](apps/bom/) — every page, button, filter, and workflow action defined in [apps/bom/urls.py](apps/bom/urls.py). It is a **complete module test** (not smoke-only) covering CRUD, search, pagination, filters, status workflows, multi-tenant isolation, frontend UI/UX, and negative/edge cases.

**In scope (5 sub-modules):**

| # | Sub-module | Models tested | Pages |
|---|---|---|---|
| 3.1 | Multi-Level BOM | `BillOfMaterials`, `BOMLine` | List/Create/Detail/Edit/Delete + Submit/Approve/Reject/Release/Obsolete + Lines + Explode |
| 3.2 | Versioning & Revision | `BOMRevision` | Capture revision · Revision detail · Rollback |
| 3.3 | Alternates & Substitution | `AlternateMaterial`, `SubstitutionRule` | Per-line alternates (CRUD + Approve/Reject) · Substitution Rules CRUD |
| 3.4 | Cost Roll-Up | `CostElement`, `BOMCostRollup` | Cost Elements CRUD · Recompute rollup on BOM detail |
| 3.5 | EBOM/MBOM/SBOM Sync | `BOMSyncMap`, `BOMSyncLog` | Sync Maps CRUD + Run drift detection |

**Out of scope:** automated tests, performance/load, accessibility audit (covered separately by `/sqa-review`).

**Acceptance bar:** every TC in §4 passes on Chrome desktop, no console errors, no 500s, multi-tenant isolation holds, status-gated buttons behave correctly.

---

## 2. Pre-Test Setup

Run these once before the test session.

### 2.1 Start the server (PowerShell)

```powershell
cd c:\xampp\htdocs\NavMSM
python manage.py migrate
python manage.py seed_tenants
python manage.py seed_plm
python manage.py seed_bom
python manage.py runserver
```

> If you already seeded earlier and want a clean BOM dataset, run `python manage.py seed_bom --flush` (other module seeds are idempotent).

### 2.2 Open the app

- URL: `http://127.0.0.1:8000/`
- Login URL: `http://127.0.0.1:8000/accounts/login/` (defined in [apps/accounts/urls.py:8](apps/accounts/urls.py#L8))

### 2.3 Login credentials (seeded by [apps/tenants/management/commands/seed_tenants.py:23](apps/tenants/management/commands/seed_tenants.py#L23))

| Tenant | Username | Password | Role |
|---|---|---|---|
| Acme Manufacturing | `admin_acme` | `Welcome@123` | Tenant admin (PRIMARY for this test run) |
| Globex Industries | `admin_globex` | `Welcome@123` | Tenant admin (used for cross-tenant isolation tests) |
| Stark Production Co. | `admin_stark` | `Welcome@123` | Tenant admin (alternate) |
| — | `admin` | superuser pwd | **DO NOT USE** for BOM tests — `tenant=None`, will see empty pages by design ([apps/accounts/views.py:39-45](apps/accounts/views.py#L39-L45)). |

### 2.4 Verify seed data

After login as `admin_acme`, navigate to `http://127.0.0.1:8000/bom/`. You should see the BOM dashboard with:

- **5 BOMs** (4 with status badges Released/Approved, 1 Draft) per [apps/bom/management/commands/seed_bom.py:127-163](apps/bom/management/commands/seed_bom.py#L127-L163)
- **2 substitution rules**
- **2 sync maps** (1 in-sync, 1 drift-detected) per [apps/bom/management/commands/seed_bom.py:249-296](apps/bom/management/commands/seed_bom.py#L249-L296)
- **15 cost elements**

If any of these are zero, re-run `python manage.py seed_bom --flush`.

### 2.5 Browser/viewport matrix

| Profile | Browser | Viewport | Priority |
|---|---|---|---|
| Desktop primary | Chrome (latest) | 1920×1080 | P0 — run every TC here |
| Desktop secondary | Edge / Firefox | 1366×768 | P1 — spot-check |
| Tablet | Chrome DevTools "iPad" | 768×1024 | P1 — UI section only |
| Mobile | Chrome DevTools "iPhone SE" | 375×667 | P1 — UI section only |

### 2.6 Reset between runs

Most workflow TCs leave seed BOMs in a transformed state (released → obsolete, draft → approved, etc.). To restart:

```powershell
python manage.py seed_bom --flush
```

This wipes all BOM rows for demo tenants and re-seeds.

---

## 3. Test Surface Inventory

### 3.1 URL routes — verified against [apps/bom/urls.py](apps/bom/urls.py)

| # | URL | View | Notes |
|---|---|---|---|
| 1 | `/bom/` | `BOMIndexView` | Dashboard (counts + recent) |
| 2 | `/bom/boms/` | `BOMListView` | Filters: `q`, `status`, `bom_type`, `product`. Page size 20. |
| 3 | `/bom/boms/new/` | `BOMCreateView` | |
| 4 | `/bom/boms/<pk>/` | `BOMDetailView` | Tabs: Overview · Lines · Revisions · Sync |
| 5 | `/bom/boms/<pk>/edit/` | `BOMEditView` | Editable only when `status in ('draft','under_review')` |
| 6 | `/bom/boms/<pk>/delete/` | `BOMDeleteView` | POST. Released BOMs blocked. |
| 7 | `/bom/boms/<pk>/submit/` | `BOMSubmitView` | draft → under_review |
| 8 | `/bom/boms/<pk>/approve/` | `BOMApproveView` | under_review → approved |
| 9 | `/bom/boms/<pk>/reject/` | `BOMRejectView` | under_review → draft |
| 10 | `/bom/boms/<pk>/release/` | `BOMReleaseView` | approved → released, supersedes prior |
| 11 | `/bom/boms/<pk>/obsolete/` | `BOMObsoleteView` | approved/released → obsolete |
| 12 | `/bom/boms/<pk>/recompute/` | `BOMRecomputeRollupView` | POST |
| 13 | `/bom/boms/<pk>/explode/` | `BOMExplodeView` | Multi-level explosion |
| 14 | `/bom/boms/<bom_id>/lines/new/` | `BOMLineCreateView` | POST only — form lives on BOM detail |
| 15 | `/bom/lines/<pk>/edit/` | `BOMLineEditView` | |
| 16 | `/bom/lines/<pk>/delete/` | `BOMLineDeleteView` | POST |
| 17 | `/bom/boms/<bom_id>/revisions/new/` | `BOMRevisionCreateView` | POST |
| 18 | `/bom/revisions/<pk>/` | `BOMRevisionDetailView` | |
| 19 | `/bom/revisions/<pk>/rollback/` | `BOMRollbackView` | Editable BOMs only |
| 20 | `/bom/lines/<line_id>/alternates/new/` | `AlternateCreateView` | |
| 21 | `/bom/alternates/<pk>/edit/` | `AlternateEditView` | |
| 22 | `/bom/alternates/<pk>/delete/` | `AlternateDeleteView` | POST |
| 23 | `/bom/alternates/<pk>/approve/` | `AlternateApproveView` | POST |
| 24 | `/bom/alternates/<pk>/reject/` | `AlternateRejectView` | POST |
| 25 | `/bom/rules/` | `SubstitutionRuleListView` | Filters: `q`, `active` |
| 26 | `/bom/rules/new/` | `SubstitutionRuleCreateView` | |
| 27 | `/bom/rules/<pk>/edit/` | `SubstitutionRuleEditView` | |
| 28 | `/bom/rules/<pk>/delete/` | `SubstitutionRuleDeleteView` | POST |
| 29 | `/bom/costs/` | `CostElementListView` | Filters: `q`, `cost_type`, `source` |
| 30 | `/bom/costs/new/` | `CostElementCreateView` | |
| 31 | `/bom/costs/<pk>/edit/` | `CostElementEditView` | |
| 32 | `/bom/costs/<pk>/delete/` | `CostElementDeleteView` | POST |
| 33 | `/bom/sync/` | `BOMSyncMapListView` | Filter: `sync_status` |
| 34 | `/bom/sync/new/` | `BOMSyncMapCreateView` | |
| 35 | `/bom/sync/<pk>/` | `BOMSyncMapDetailView` | Includes log entries |
| 36 | `/bom/sync/<pk>/edit/` | `BOMSyncMapEditView` | |
| 37 | `/bom/sync/<pk>/delete/` | `BOMSyncMapDeleteView` | POST |
| 38 | `/bom/sync/<pk>/run/` | `BOMSyncRunView` | POST — drift detection |

### 3.2 Form-level constraints

| Form | Validation | Source |
|---|---|---|
| `BillOfMaterialsForm` | `unique_together = ('tenant','product','bom_type','version','revision')` | [apps/bom/models.py:74](apps/bom/models.py#L74) |
| `BOMLineForm` | `parent_line` queryset filtered to same BOM, excluding self | [apps/bom/forms.py:50-58](apps/bom/forms.py#L50-L58) |
| `SubstitutionRuleForm` | `original ≠ substitute` — surfaces as form error on `substitute_component` | [apps/bom/forms.py:114-120](apps/bom/forms.py#L114-L120) |
| `BOMSyncMapForm` | `source ≠ target`; `source.bom_type ≠ target.bom_type` | [apps/bom/forms.py:158-168](apps/bom/forms.py#L158-L168) |
| `CostElementForm` | `unique_together = ('tenant','product','cost_type')` — duplicate caught and shown as friendly message | [apps/bom/views.py:661-668](apps/bom/views.py#L661-L668) |
| `BOMSyncMap` | `unique_together = ('source_bom','target_bom')` — duplicate caught by view | [apps/bom/views.py:737-740](apps/bom/views.py#L737-L740) |

### 3.3 Status-gated UI

Edit / Delete / line-add / line-delete / line-edit / revision rollback are visible **only** when the BOM `is_editable()` returns `True`, i.e., status is `draft` or `under_review` ([apps/bom/models.py:81-82](apps/bom/models.py#L81-L82)). Verified in [templates/bom/boms/list.html:60](templates/bom/boms/list.html#L60) and [templates/bom/boms/detail.html:18,118-125,158-164,190-194](templates/bom/boms/detail.html#L18).

---

## 4. Test Cases

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous redirect — BOM list | Logged out | 1. Open browser private window<br>2. Visit `/bom/boms/` | — | Redirected to `/accounts/login/?next=/bom/boms/`. Login form rendered. | | |
| TC-AUTH-02 | Anonymous redirect — BOM dashboard | Logged out | 1. Visit `/bom/` | — | Redirected to `/accounts/login/?next=/bom/`. | | |
| TC-AUTH-03 | Anonymous redirect — sub-pages | Logged out | 1. Visit each: `/bom/rules/`, `/bom/costs/`, `/bom/sync/`, `/bom/boms/new/` | — | Each redirects to login with correct `?next=…`. | | |
| TC-AUTH-04 | Login as tenant admin | At login form | 1. Username `admin_acme`<br>2. Password `Welcome@123`<br>3. Submit | `admin_acme` / `Welcome@123` | Redirected to dashboard. Top-right shows tenant name "Acme Manufacturing". | | |
| TC-AUTH-05 | Superuser sees empty BOM data (BY DESIGN) | Logged in as Django superuser (no tenant) | 1. Visit `/bom/`<br>2. Visit `/bom/boms/` | — | Yellow flash: "You are signed in as a user without a tenant…". Redirected to dashboard. **Or** if mixin is bypassed, list shows zero rows. | | |
| TC-AUTH-06 | Logout | Logged in | 1. Click avatar → Logout | — | Redirected to login page. Visiting `/bom/boms/` requires login again. | | |

### 4.2 Multi-Tenancy Isolation (mandatory IDOR test)

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | List shows only own tenant BOMs | Logged in as `admin_acme` | 1. Visit `/bom/boms/`<br>2. Note all BOM numbers and primary keys (hover URL)<br>3. Logout, log in as `admin_globex`<br>4. Visit `/bom/boms/` | — | Globex BOM list contains different `pk`s. None of Acme's BOM numbers appear. | | |
| TC-TENANT-02 | Cross-tenant detail IDOR — BOM | Logged in as `admin_acme`, know a Globex BOM pk (from TC-TENANT-01) | 1. Manually visit `/bom/boms/<globex-bom-pk>/` while still logged in as `admin_acme` | e.g. `/bom/boms/<X>/` | **404 Not Found**. NOT 200, NOT 403. | | |
| TC-TENANT-03 | Cross-tenant detail IDOR — sync map | Same as above, with a Globex sync map pk | 1. Visit `/bom/sync/<globex-sync-pk>/` as Acme admin | — | 404 Not Found. | | |
| TC-TENANT-04 | Cross-tenant detail IDOR — cost element | Same as above, with a Globex cost element pk | 1. Visit `/bom/costs/<globex-cost-pk>/edit/` as Acme admin | — | 404 Not Found. | | |
| TC-TENANT-05 | Cross-tenant detail IDOR — substitution rule | Same as above | 1. Visit `/bom/rules/<globex-rule-pk>/edit/` as Acme admin | — | 404 Not Found. | | |
| TC-TENANT-06 | Cross-tenant POST IDOR — BOM submit | Logged in as Acme admin | 1. Open DevTools, copy CSRF cookie<br>2. POST to `/bom/boms/<globex-bom-pk>/submit/` (curl or DevTools) | — | 404 Not Found, no state change in DB. | | |
| TC-TENANT-07 | BOM line cross-tenant FK leakage | Logged in as `admin_acme`, on draft BOM line edit form | 1. Open `/bom/lines/<acme-line-pk>/edit/`<br>2. Inspect `<select name="component">` options | — | Only Acme products visible. No Globex SKUs in dropdown. | | |
| TC-TENANT-08 | Sync map BOM dropdown isolation | Acme admin, `/bom/sync/new/` | 1. Inspect `source_bom` dropdown | — | Only Acme BOMs listed. No Globex BOM numbers. | | |

### 4.3 CREATE — `/bom/boms/new/`

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-01 | Create BOM with all fields | Logged in as `admin_acme`, on `/bom/boms/`. | 1. Click **+ New BOM**<br>2. Name: `QA Smoke BOM 1`<br>3. Product: `SKU-4001 — Industrial Controller Mk-3`<br>4. BOM Type: `Engineering BOM (EBOM)`<br>5. Version: `B`, Revision: `01`<br>6. Description: `Test BOM created by QA`<br>7. Effective from: today<br>8. Submit | See steps | Redirected to detail page `/bom/boms/<new-pk>/`. Green toast: `BOM BOM-NNNNN created.`. Detail shows status badge **Draft**. `bom_number` follows pattern `BOM-NNNNN`. | | |
| TC-CREATE-02 | Create with only required fields | On create form | 1. Name: `Minimal BOM`<br>2. Product: `SKU-4003`<br>3. Leave others default<br>4. Submit | — | Created. BOM type defaults to `EBOM`, version `A`, revision `01`, status `draft`. | | |
| TC-CREATE-03 | Required field missing — name blank | On create form | 1. Leave Name empty<br>2. Pick a product<br>3. Submit | — | Form re-renders with red error under Name field: "This field is required.". No DB write. | | |
| TC-CREATE-04 | Required field missing — product blank | On create form | 1. Name: `No Product`<br>2. Leave Product blank<br>3. Submit | — | Red error under Product field. | | |
| TC-CREATE-05 | Duplicate of unique_together set | First create a BOM (Product=SKU-4001, type=ebom, version=A, revision=01) — note: seed already has this | 1. Create new BOM with the same Product+Type+Version+Revision combo | — | Form-level error OR friendly message. Should NOT 500. (Verifies the trap from [.claude/tasks/lessons.md](.claude/tasks/lessons.md) — `tenant` excluded from form, `validate_unique` may not catch tenant-scoped collisions; the view's `_save_with_unique_number` retry catches `bom_number` collisions but not the unique_together — **CANDIDATE: confirm behavior**.) | | |
| TC-CREATE-06 | Max-length name (255 chars) | On create form | 1. Name: paste 255-char string `aaaa…`<br>2. Product: any<br>3. Submit | 255 × `a` | Created successfully. Detail page renders without truncation. | | |
| TC-CREATE-07 | Over-length name (256 chars) | On create form | 1. Name: paste 256-char string<br>2. Submit | 256 × `a` | Form error "Ensure this value has at most 255 characters". No DB write. | | |
| TC-CREATE-08 | XSS attempt in description | On create form | 1. Name: `XSS Test`<br>2. Description: `<script>alert('XSS')</script>`<br>3. Submit | — | Created. Detail page **shows the literal string** — no JS alert fires. View source: `<script>` is HTML-escaped. | | |
| TC-CREATE-09 | Special chars in name | On create form | 1. Name: `BOM "with" 'quotes' & emoji 🔧 unicode 中文`<br>2. Product: any<br>3. Submit | — | Created. Detail page renders all chars correctly. List page shows them in row. | | |
| TC-CREATE-10 | Effective_to before effective_from | On create form | 1. Name: `Date Test`<br>2. Effective from: `2026-04-30`<br>3. Effective to: `2026-04-25`<br>4. Submit | — | **CANDIDATE — model has no clean to enforce date order**. Currently saves both. Log as a future enhancement, not a bug per se; expected: saves successfully today. | | |
| TC-CREATE-11 | Obsolete product NOT in dropdown | A product is marked `status='obsolete'` in `/plm/products/` | 1. Open `/bom/boms/new/`<br>2. Inspect Product dropdown | — | Obsolete product is excluded ([apps/bom/forms.py:30-32](apps/bom/forms.py#L30-L32)). | | |
| TC-CREATE-12 | bom_number is auto-allocated | Create 3 BOMs in succession | 1. Create BOM #1 → note number<br>2. Create BOM #2 → note number<br>3. Create BOM #3 → note number | — | Numbers follow `BOM-00006`, `BOM-00007`, `BOM-00008` (or whatever ++1 from existing max). Field is NOT shown on the form. | | |

### 4.4 READ — List Page (`/bom/boms/`)

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-01 | List loads | Acme admin | 1. Visit `/bom/boms/` | — | Page 200. Title `Bills of Materials`. At least 5 seeded rows + any TC-CREATE-NN rows. Columns: Number / Product / Type / Version / Lines / Default / Status / Actions. | | |
| TC-LIST-02 | All columns populated | On list page | 1. Inspect each row | — | No `None` literals. Number is bold link. Product cell shows `SKU + truncated name`. Type badge has correct label (e.g. "Engineering BOM (EBOM)"). Lines shows an integer. Default shows badge or em-dash. Status badge color matches the value (see TC-UI-04). | | |
| TC-LIST-03 | Number column links to detail | On list page | 1. Click on a BOM number link | — | Lands on `/bom/boms/<pk>/`. | | |
| TC-LIST-04 | Default badge appears for `is_default=True` | Seed includes default BOMs | 1. Find row for SKU-4001 EBOM | — | `Default` badge appears in Default column. | | |
| TC-LIST-05 | Status-gated Edit/Delete buttons | On list page | 1. Compare a `Released` row to a `Draft` row | — | Released row Actions column has only **View (eye)** icon. Draft row has View + Edit (pencil) + Delete (bin). | | |
| TC-LIST-06 | Empty state | Apply a filter that returns zero rows (e.g. status=`obsolete` when no obsolete BOMs exist) | 1. Choose status `Obsolete` and click Filter | — | Single row reading "No BOMs yet." with `colspan=8`. | | |

### 4.5 READ — Detail Page (`/bom/boms/<pk>/`)

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DETAIL-01 | Detail loads for Released BOM | Acme admin, click a Released BOM (e.g. SKU-4001 MBOM) | 1. Land on detail page | — | Page title is the BOM number. Status pill green = Released. Side card lists Number, Product (links to PLM detail), Type, Version, Effective dates, Created/Approved/Released by + at. Cost roll-up card shows totals (since seed computed it). | | |
| TC-DETAIL-02 | Tabs work | On detail page | 1. Click Overview / Lines / Revisions / Sync tabs in succession | — | Each tab swaps content without reload. URL fragment may update. | | |
| TC-DETAIL-03 | Lines tab renders rows | Detail of any seeded BOM | 1. Click Lines tab | — | Table populated. Component column links to PLM product detail. Phantom column shows "Phantom" badge for SKU-2002 row in SKU-4001 EBOM. | | |
| TC-DETAIL-04 | Released BOM hides line-add form | On Released BOM detail → Lines tab | 1. Look for "Add line" form above table | — | Form is hidden (`{% if bom.is_editable %}` is False). | | |
| TC-DETAIL-05 | Draft BOM shows line-add form | Draft BOM detail (SKU-4003 EBOM) → Lines tab | 1. Inspect | — | Form rendered with crispy-styled fields and "Add line" button. | | |
| TC-DETAIL-06 | Released BOM hides Edit/Delete buttons in header | Released BOM detail | 1. Inspect header right-side | — | Edit button absent. No Delete form. Only Back, Explode, and Obsolete buttons. | | |
| TC-DETAIL-07 | Approved BOM shows Release + Obsolete | Approved BOM (SKU-4002 SBOM) | 1. Inspect header | — | Release (success button) + Obsolete (outline) shown. | | |
| TC-DETAIL-08 | Under-review BOM shows Approve + Reject | After running TC-ACTION-01 | 1. Inspect header | — | Approve and Reject buttons shown. | | |
| TC-DETAIL-09 | Cost rollup card shows totals | On Released BOM detail | 1. Inspect Cost Roll-Up card | — | Material/Labor/Overhead/Tooling/Other rows + Total row in primary-subtle. Footer line "Computed {date} by {user}". No "Stale" warning. | | |
| TC-DETAIL-10 | Revisions tab — major release captured | SKU-4001 EBOM (Released) | 1. Click Revisions tab | — | At least one row of type **Major**. Click v.r link → `/bom/revisions/<pk>/` opens. | | |
| TC-DETAIL-11 | Sync tab counts | SKU-4001 EBOM detail | 1. Click Sync tab | — | "Sync targets" table has 1 row to MBOM. Status badge "Drift". Last-sync date shows. | | |
| TC-DETAIL-12 | Explode page works | On Released BOM detail | 1. Click **Explode** button | — | Opens `/bom/boms/<pk>/explode/`. Multi-level rows shown. SKU-4001 EBOM phantom row (SKU-2002) is **collapsed** — its child SKU-1001 appears at level 1, not level 2 (per phantom logic in [apps/bom/models.py:158-169](apps/bom/models.py#L158-L169)). | | |

### 4.6 UPDATE — `/bom/boms/<pk>/edit/`

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit Draft BOM | Logged in, on Draft BOM detail (SKU-4003 EBOM) | 1. Click **Edit** button<br>2. Change Name to `Robotic Arm Joint — UPDATED`<br>3. Submit | — | Redirect to detail. Toast: "BOM updated.". Header shows new name. | | |
| TC-EDIT-02 | Edit form pre-fills all fields | Open edit form for any draft BOM | 1. Inspect every input | — | Every input has the current value (Name, Product selected, BOM Type selected, Version, Revision, Description, is_default checkbox state, dates). | | |
| TC-EDIT-03 | Edit Released BOM blocked | On Released BOM detail | 1. Manually visit `/bom/boms/<released-pk>/edit/` | — | Yellow toast "BOM can only be edited in Draft or Under Review status." Redirected to detail. | | |
| TC-EDIT-04 | Edit Released BOM POST blocked | DevTools console, get CSRF token, submit POST to `/bom/boms/<released-pk>/edit/` | 1. Run a fetch with valid token | — | Same as TC-EDIT-03 — POST is short-circuited by `is_editable()` check. No DB write. | | |
| TC-EDIT-05 | Edit invalid data preserves entry | On edit form | 1. Clear Name<br>2. Submit | — | Form re-renders with error. Other fields retain their entered values. Original BOM in DB unchanged. | | |
| TC-EDIT-06 | Edit toggle is_default | On Draft BOM (SKU-4003 EBOM) | 1. Tick **Is default**<br>2. Submit | — | Saved. List page Default column shows "Default" badge. (No model-level check enforces single-default; tester documents observed behavior.) | | |

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete Draft BOM from list | Draft BOM (e.g. SKU-4003) on list page | 1. Click bin icon in Actions column<br>2. Click **OK** in confirm dialog | confirm "Delete BOM BOM-NNNNN?" | Redirected to list. Green toast "BOM deleted.". Row no longer present. | | |
| TC-DELETE-02 | Delete confirmation cancellation | Same | 1. Click bin icon<br>2. Click **Cancel** | — | Dialog closes, no nav, row still present, no DB change. | | |
| TC-DELETE-03 | Delete Released BOM blocked | On Released BOM detail | 1. There is **no** Delete button in header (verified TC-DETAIL-06)<br>2. Try POST `/bom/boms/<released-pk>/delete/` directly via DevTools | — | View returns: red toast "Released BOMs cannot be deleted — mark Obsolete first." Redirected to detail. Row still exists. | | |
| TC-DELETE-04 | Delete Approved BOM allowed (per view code) | Approved BOM (SKU-4002 SBOM) | 1. POST to `/bom/boms/<approved-pk>/delete/` | — | Deleted (Approved is not blocked, only Released). NB: there is no Delete button rendered for Approved status — this is a UI gap. **Document as a finding**, not a blocker. | | |
| TC-DELETE-05 | Cascade — BOM lines removed | After TC-DELETE-01, query DB or detail page | 1. Check `BOMLine.objects.filter(bom_id=<deleted-pk>)` | — | Empty (CASCADE on `BOMLine.bom`). | | |
| TC-DELETE-06 | ProtectedError caught (component referenced elsewhere) | Tricky to set up — skip unless desired. | — | — | View has a `ProtectedError` branch ([apps/bom/views.py:221-223](apps/bom/views.py#L221-L223)). | | |

### 4.8 SEARCH — list pages

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-SEARCH-01 | BOM search empty | `/bom/boms/` | 1. Empty `q` field, click Filter | — | All rows shown. URL has `?q=`. | | |
| TC-SEARCH-02 | BOM search by number | `/bom/boms/` | 1. Type `BOM-00001`<br>2. Filter | `BOM-00001` | Only that row shown. | | |
| TC-SEARCH-03 | BOM search by name | `/bom/boms/` | 1. Type `Industrial`<br>2. Filter | `Industrial` | Rows where Name contains "Industrial" (case-insensitive — should include both EBOM and MBOM for SKU-4001). | | |
| TC-SEARCH-04 | BOM search by product SKU | `/bom/boms/` | 1. Type `SKU-4002`<br>2. Filter | `SKU-4002` | Rows for SKU-4002 only (EBOM + SBOM). | | |
| TC-SEARCH-05 | BOM search case-insensitive | `/bom/boms/` | 1. Type `industrial`<br>2. Filter | lowercase | Same result as TC-SEARCH-03. | | |
| TC-SEARCH-06 | BOM search whitespace stripped | `/bom/boms/` | 1. Type `  Industrial  `<br>2. Filter | leading/trailing spaces | Same result as TC-SEARCH-03. (View calls `.strip()` per [apps/bom/views.py:119](apps/bom/views.py#L119).) | | |
| TC-SEARCH-07 | No-match shows empty state | `/bom/boms/` | 1. Type `zzznomatch`<br>2. Filter | — | Empty state row "No BOMs yet.". | | |
| TC-SEARCH-08 | Special chars don't 500 | `/bom/boms/` | 1. Type `%`<br>2. Filter<br>3. Type `'`<br>4. Filter<br>5. Type `_`<br>6. Filter | each special | All return 200 with 0 or matching rows. No 500. | | |
| TC-SEARCH-09 | Search retained across pagination | Need ≥21 BOMs (create extras for this test or skip if <21 exist) | 1. Type a broad term<br>2. Filter, click page 2 | — | URL preserves `?q=…&page=2`. Search field still shows the term. | | |
| TC-SEARCH-10 | Substitution Rule search by name | `/bom/rules/` | 1. Type `M3`<br>2. Filter | — | Row "M3 Bolt — generic source" only. | | |
| TC-SEARCH-11 | Substitution Rule search by SKU | `/bom/rules/` | 1. Type `SKU-2001`<br>2. Filter | — | Rule with original=SKU-2001 shown. | | |
| TC-SEARCH-12 | Cost Element search by SKU | `/bom/costs/` | 1. Type `SKU-4001`<br>2. Filter | — | Rows for SKU-4001 only (3: labor, overhead, tooling). | | |
| TC-SEARCH-13 | Cost Element search by product name | `/bom/costs/` | 1. Type `Controller`<br>2. Filter | — | Rows for any product name containing "Controller". | | |

### 4.9 PAGINATION

> Page size = 20 ([apps/bom/views.py:113](apps/bom/views.py#L113), 552, 624, 708). Seed alone yields 5 BOMs / 2 rules / 15 costs / 2 syncs — to test page 2, add records or note "N/A — under page size".

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-PAGE-01 | BOM list — single page | `/bom/boms/` with seed only (5 BOMs) | 1. Inspect bottom | — | No pagination nav (seed total < 20). | | |
| TC-PAGE-02 | BOM list — multi-page | Create 16+ extra BOMs to reach >20 | 1. Visit `/bom/boms/`<br>2. Inspect bottom | — | Pagination nav shows. Click next → URL `?page=2`. Page label "2 / N". | | |
| TC-PAGE-03 | Filters retained across pagination | Same setup, with q=`Industrial` | 1. Apply filter<br>2. Click page 2 | — | URL is `?q=Industrial&page=2`. Search input retains `Industrial`. | | |
| TC-PAGE-04 | Page beyond last | URL `?page=999` | 1. Visit | — | Django paginator returns 404 (`EmptyPage`) — graceful. NOT 500. | | |
| TC-PAGE-05 | Page=invalid string | URL `?page=abc` | 1. Visit | — | 404 (`PageNotAnInteger`). NOT 500. | | |
| TC-PAGE-06 | Cost Elements multi-page | Seed has 15. Create 6 more → 21. | 1. `/bom/costs/`<br>2. Inspect bottom | — | Pagination nav appears, page 2 has 1 row. | | |

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-FILTER-01 | BOM list — Status dropdown populated | `/bom/boms/` | 1. Inspect Status select | — | Options: Any status / Draft / Under Review / Approved / Released / Obsolete. (Matches `BillOfMaterials.STATUS_CHOICES`.) | | |
| TC-FILTER-02 | BOM list — Status filter applied | `/bom/boms/` | 1. Choose `Released`<br>2. Filter | — | Only Released rows. URL `?status=released`. Dropdown still shows `Released` selected. | | |
| TC-FILTER-03 | BOM list — Bom Type dropdown | `/bom/boms/` | 1. Inspect Type select | — | Options: Any type / Engineering BOM (EBOM) / Manufacturing BOM (MBOM) / Service BOM (SBOM). | | |
| TC-FILTER-04 | BOM list — Bom Type filter | `/bom/boms/` | 1. Choose `Engineering BOM (EBOM)`<br>2. Filter | — | Only EBOM rows. URL `?bom_type=ebom`. | | |
| TC-FILTER-05 | BOM list — Product dropdown | `/bom/boms/` | 1. Inspect Product select | — | All Acme products listed (sorted by SKU). | | |
| TC-FILTER-06 | BOM list — Product filter | `/bom/boms/` | 1. Pick a product<br>2. Filter | — | Rows for that product only. URL has `?product=<pk>`. Dropdown still shows the chosen option (validates `\|stringformat:"d"` use in [templates/bom/boms/list.html:33](templates/bom/boms/list.html#L33)). | | |
| TC-FILTER-07 | BOM list — combined filters AND | `/bom/boms/` | 1. status=`Released` + bom_type=`MBOM`<br>2. Filter | — | Rows where status=released AND bom_type=mbom. URL `?status=released&bom_type=mbom`. | | |
| TC-FILTER-08 | BOM list — filter + search | `/bom/boms/` | 1. q=`Industrial`, status=`Released`, Filter | — | Released BOMs whose name/number/SKU matches "Industrial". | | |
| TC-FILTER-09 | BOM list — Reset filters | After TC-FILTER-07 | 1. Set all selects to "Any…"<br>2. Clear `q`<br>3. Filter | — | Full list returned. | | |
| TC-FILTER-10 | Substitution Rules — Active filter | `/bom/rules/` | 1. Select `Active` → Filter<br>2. Then `Inactive` → Filter | — | First shows is_active=True rows, second shows is_active=False rows (likely empty). URL has `?active=active` / `?active=inactive`. | | |
| TC-FILTER-11 | Cost Elements — cost_type filter | `/bom/costs/` | 1. Choose `Material`<br>2. Filter | — | Only material rows. URL `?cost_type=material`. Dropdown retains selection. | | |
| TC-FILTER-12 | Cost Elements — source filter | `/bom/costs/` | 1. Choose `Manual Entry`<br>2. Filter | — | All seed rows (since seeded as 'manual'). URL `?source=manual`. | | |
| TC-FILTER-13 | Sync Maps — sync_status filter | `/bom/sync/` | 1. Choose `Drift Detected`<br>2. Filter | — | Only drift rows. URL `?sync_status=drift_detected`. Dropdown retains selection. | | |
| TC-FILTER-14 | Filter retains across page nav | Need >20 cost elements | 1. Filter cost_type=material<br>2. Click page 2 | — | URL `?cost_type=material&page=2`. Filter still applied. | | |

### 4.11 Status Transitions / Custom Actions

> Pristine flow: Draft → Under Review → Approved → Released → Obsolete. Reject sends back to Draft.
> Run these in order on a single new BOM you create at TC-CREATE-01.

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-01 | Submit Draft for review | Draft BOM detail | 1. Click **Submit for review**<br>2. Confirm | — | Status badge → Under Review. Toast "BOM BOM-NNNNN submitted for review.". Approve/Reject buttons now visible. Edit still allowed (Under Review is editable). | | |
| TC-ACTION-02 | Approve from Under Review | After TC-ACTION-01 | 1. Click **Approve**<br>2. Confirm | — | Status badge → Approved. `approved_at` and `approved_by` populated (verify on detail card). Release/Obsolete buttons appear. Edit/Delete are gone. | | |
| TC-ACTION-03 | Reject from Under Review | Reproduce: create new BOM, Submit, then Reject | 1. Click **Reject**<br>2. Confirm | — | Status → Draft. Toast "BOM BOM-NNNNN sent back to Draft.". | | |
| TC-ACTION-04 | Release Approved | After TC-ACTION-02 | 1. Click **Release**<br>2. Confirm dialog warns prior released will be obsoleted<br>3. Confirm | — | Status → Released. `released_at` populated. **Major** revision auto-captured (visible in Revisions tab). If a prior released BOM existed for same product+bom_type, it is now Obsolete (verify on list). | | |
| TC-ACTION-05 | Mark Released as Obsolete | On a Released BOM detail | 1. Click **Obsolete**<br>2. Confirm | — | Status → Obsolete. List shows Obsolete badge. No Edit/Delete. | | |
| TC-ACTION-06 | Submit non-draft blocked | On an Approved BOM | 1. POST `/bom/boms/<pk>/submit/` directly | — | Yellow toast "Only Draft BOMs can be submitted.". No status change. | | |
| TC-ACTION-07 | Approve non-review blocked | On a Draft BOM | 1. POST `/bom/boms/<pk>/approve/` directly | — | Yellow toast "BOM is not awaiting review.". | | |
| TC-ACTION-08 | Release non-approved blocked | On a Draft BOM | 1. POST `/bom/boms/<pk>/release/` directly | — | Yellow toast "Only Approved BOMs can be released.". | | |
| TC-ACTION-09 | Obsolete from Draft blocked | On a Draft BOM | 1. POST `/bom/boms/<pk>/obsolete/` | — | Yellow toast "BOM cannot be marked Obsolete from its current state.". | | |
| TC-ACTION-10 | Recompute rollup | On any BOM with cost elements | 1. Click **Recompute** in Cost Roll-Up card | — | Toast "Rollup recomputed: total {amount} USD.". Card values refreshed. `computed_at` updated. | | |
| TC-ACTION-11 | Recompute rollup with no cost elements | Create a BOM with a component that has no `CostElement` | 1. Click Recompute | — | Card shows zeros. No 500. | | |
| TC-ACTION-12 | Add BOM line | Draft BOM detail → Lines tab | 1. Pick component (any non-obsolete product)<br>2. Quantity: `2`<br>3. UoM: `ea`<br>4. Click **Add line** | — | New row appears. Toast "Line {SKU} added.". | | |
| TC-ACTION-13 | Add line on Released blocked | Released BOM detail | 1. POST `/bom/boms/<pk>/lines/new/` directly | — | Yellow toast "Lines can only be added while BOM is Draft or Under Review.". | | |
| TC-ACTION-14 | Add nested (parent_line) | Draft BOM with at least 1 line | 1. On Add Line form, pick a Parent line<br>2. Submit | — | Child line saved. Lines tab shows Parent column = parent SKU. Explode page nests one level deeper. | | |
| TC-ACTION-15 | Edit line | Draft BOM line | 1. Click pencil icon on a line<br>2. Change quantity<br>3. Save | — | Redirect to detail. Toast "Line updated.". | | |
| TC-ACTION-16 | Delete line | Same | 1. Click bin icon on a line, confirm | — | Toast "Line deleted.". Row gone. | | |
| TC-ACTION-17 | Capture revision snapshot | On any BOM detail → Revisions tab | 1. Version `B`, Revision `02`, type `Engineering`, summary `Test snapshot`, Effective today<br>2. Click **Capture revision snapshot** | — | Toast "Revision B.02 captured.". Row appears in revisions table. | | |
| TC-ACTION-18 | Revision detail page | On the new revision row | 1. Click v.r link → opens `/bom/revisions/<pk>/` | — | Revision detail page renders summary, snapshot JSON. | | |
| TC-ACTION-19 | Rollback to revision (Draft BOM) | Draft BOM that has captured revisions | 1. On Revisions tab, click **Rollback** on a revision row, confirm | — | Toast "BOM rolled back to revision B.02.". Lines tab shows lines reconstructed from snapshot. New revision of type **Rollback** auto-captured. | | |
| TC-ACTION-20 | Rollback on Released blocked | Released BOM | 1. The Rollback button is hidden ([templates/bom/boms/detail.html:190](templates/bom/boms/detail.html#L190))<br>2. Try POST directly | — | Yellow toast "Rollback requires BOM to be Draft or Under Review.". | | |
| TC-ACTION-21 | Add alternate to a BOM line | Any BOM line | 1. Click `+` next to alternates count → `/bom/lines/<line_id>/alternates/new/`<br>2. Pick alternate component (different from line component)<br>3. priority `1`, type `Approved Equivalent`<br>4. Submit | — | Redirect to BOM detail. Toast "Alternate {SKU} added.". Line row shows new alternate with `?` (pending) badge. | | |
| TC-ACTION-22 | Approve alternate | On BOM detail with pending alternate | 1. Click ✓ icon next to the pending alternate | — | Badge → ✓ green. Toast "Alternate {SKU} approved.". | | |
| TC-ACTION-23 | Reject alternate | Pending alternate | 1. Click ✗ icon | — | Badge → ✗ red. Toast "Alternate {SKU} rejected.". | | |
| TC-ACTION-24 | Edit alternate | Existing alternate | 1. Click pencil icon | — | Form loads pre-filled. Save changes; toast "Alternate updated.". | | |
| TC-ACTION-25 | Delete alternate | Existing alternate | 1. Click bin icon, confirm | — | Toast "Alternate removed.". Row gone. | | |
| TC-ACTION-26 | Sync Run — drift case | Sync map "EBOM-4001 → MBOM-4001" (seeded as drift) | 1. From sync detail, click **Run sync**, OR list `/bom/sync/` and click refresh icon | — | Yellow flash with drift summary. `sync_status=drift_detected`. New row in Log Entries table with action `drift`. | | |
| TC-ACTION-27 | Sync Run — in-sync case | Make EBOM-4002 == SBOM-4002 (seeded with subset, so will detect drift initially); after equalising lines, click Run | 1. Equalise lines<br>2. Run | — | Green flash "in sync". Status badge → In sync. Log entry action `reconciled`. | | |

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-UI-01 | Browser tab title | On `/bom/boms/` | 1. Read tab title | — | "Bills of Materials" (per `{% block title %}`). | | |
| TC-UI-02 | Browser tab title — detail | On a BOM detail | 1. Read tab title | — | The BOM number (e.g. `BOM-00001`). | | |
| TC-UI-03 | Sidebar BOM link active | On any BOM page | 1. Inspect left nav | — | "Bill of Materials" link highlighted as active. (CANDIDATE — verify your nav template). | | |
| TC-UI-04 | Status badge colors | On BOM list | 1. Compare badges | — | Released = green solid; Approved = green-subtle; Under Review = yellow-subtle; Obsolete = grey; Draft = grey-subtle. Per [templates/bom/boms/list.html:52-56](templates/bom/boms/list.html#L52-L56). | | |
| TC-UI-05 | Action button alignment | List page Actions column | 1. Inspect | — | Actions cell `text-end`, buttons inline with `btn-sm` outline style, consistent gaps. | | |
| TC-UI-06 | Toast auto-dismiss | After any successful create/edit | 1. Observe toast | — | Auto-dismisses within 5s (verify with stopwatch). | | |
| TC-UI-07 | Confirm dialog content | Click delete on BOM-00009 | 1. Read dialog | — | "Delete BOM BOM-00009?" — entity name interpolated correctly. | | |
| TC-UI-08 | Required-field markers | On BOM create form | 1. Inspect labels | — | Name, Product have `*` (or visual cue). | | |
| TC-UI-09 | Form errors under fields | After TC-CREATE-03 | 1. Inspect | — | Red text under Name field. Field has aria-invalid or red border. | | |
| TC-UI-10 | Long text wraps | Create BOM with 200-char description, view detail | 1. Inspect description card | — | Wraps, no horizontal scroll. | | |
| TC-UI-11 | Mobile viewport (375×667) | Chrome DevTools, iPhone SE | 1. Visit `/bom/boms/`<br>2. Inspect | — | Sidebar collapses to hamburger; list table scrolls horizontally; New BOM button visible; no off-screen content. | | |
| TC-UI-12 | Tablet viewport (768×1024) | DevTools | 1. Visit detail page | — | Two-column layout still works (or stacks gracefully). | | |
| TC-UI-13 | Keyboard nav | List page | 1. Tab through interactive elements | — | Logical order: search → status → bom_type → product → Filter button → first row link → Actions → next row… Focus ring visible. | | |
| TC-UI-14 | Form submits on Enter | Create BOM form, focus on Effective From | 1. Press Enter | — | Form submits (or last field's intended behavior). | | |
| TC-UI-15 | No console errors | Visit each page in §3.1 | 1. Open DevTools Console | — | Zero red errors. Yellow warnings allowed but noted. | | |
| TC-UI-16 | Empty list states | Any list with no data | 1. View empty list | — | Single colspan row reading "No … yet." per template. No icon-only or broken layout. | | |
| TC-UI-17 | Tab navigation persists across reload | BOM detail, click Lines tab, F5 | 1. Inspect | — | Bootstrap tab probably resets to Overview on reload. Note observed behavior. | | |
| TC-UI-18 | Cost rollup "Stale" warning | Create new BOM with no rollup | 1. Visit detail | — | Card shows "No rollup yet — click Recompute to calculate." OR after recompute, no stale warning. | | |
| TC-UI-19 | Sync detail drift summary block | On drift sync map detail | 1. Inspect | — | Red `bg-danger-subtle` block shows the drift summary text. | | |
| TC-UI-20 | Sync log entries list ordered desc | After running TC-ACTION-26 | 1. Inspect log entries on detail | — | Latest run at top (timestamp desc). Action labels render (Drift / Reconciled / etc.). | | |

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-NEG-01 | Submit blank create form | `/bom/boms/new/` | 1. Submit with everything blank | — | All required-field errors visible at once (Name + Product). Page still 200. | | |
| TC-NEG-02 | Decimal in quantity rejected | Add line with quantity `abc` | 1. Submit | `abc` | Form error "Enter a number". | | |
| TC-NEG-03 | Negative quantity | Add line with quantity `-1` | 1. Submit | `-1` | **CANDIDATE** — model has no positive-only validator. May accept. Test and document. | | |
| TC-NEG-04 | Scrap_percent > 100 | Add line with scrap=`150` | 1. Submit | `150` | **CANDIDATE** — no upper bound on `scrap_percent`. Effective qty = original × 2.5. Accepted, test for graceful behavior. | | |
| TC-NEG-05 | Substitution rule original==substitute | `/bom/rules/new/` | 1. Pick same SKU for both<br>2. Submit | — | Form error "Substitute must differ from the original component." (Verifies [apps/bom/forms.py:118](apps/bom/forms.py#L118).) No DB write. | | |
| TC-NEG-06 | Sync map source==target | `/bom/sync/new/` | 1. Pick same BOM in both<br>2. Submit | — | Form error "Source and target BOM must be different.". | | |
| TC-NEG-07 | Sync map source.bom_type == target.bom_type | `/bom/sync/new/` | 1. Pick two EBOMs<br>2. Submit | — | Form error "Source and target must have different BOM types (e.g. EBOM → MBOM)." | | |
| TC-NEG-08 | Duplicate sync map | Recreate the existing seeded EBOM→MBOM map | 1. Submit | — | Red toast "A sync map already exists between those two BOMs.". No DB write. | | |
| TC-NEG-09 | Duplicate cost element (same product+cost_type) | Create a 2nd material cost for SKU-1001 (seed already has one) | 1. Submit | — | Red toast "A Material cost already exists for SKU-1001 — edit it instead." (Verifies [apps/bom/views.py:664-667](apps/bom/views.py#L664-L667).) | | |
| TC-NEG-10 | Double-submit (rapid double-click) | On BOM create form | 1. Fill valid data<br>2. Triple-click Submit fast | — | Only ONE BOM created (sequence number lock via `_save_with_unique_number` retry). OR a graceful duplicate error — no 500. | | |
| TC-NEG-11 | Browser back after create | After successful BOM create | 1. Press browser Back twice | — | Returns to form with original data (browser cache). Re-submitting: a NEW BOM is created (idempotency not enforced). Document. | | |
| TC-NEG-12 | Refresh on POST | After successful submit | 1. Press F5 on the detail redirect target | — | Idempotent (we're already on a GET URL after redirect). No double-create. | | |
| TC-NEG-13 | Self-as-parent line | Add line, then Edit it and pick itself as parent | 1. Try to set parent_line=self | — | Form `parent_line` queryset excludes `self.instance.pk` ([apps/bom/forms.py:53](apps/bom/forms.py#L53)) — option not present. | | |
| TC-NEG-14 | Phantom-on-phantom explosion | Build chain: line A is phantom, line B (child of A) is phantom, line C (child of B) is real | 1. View `/bom/boms/<pk>/explode/` | — | Only C appears, both A and B collapse. Quantities multiply through. | | |
| TC-NEG-15 | Snapshot with deleted component | Create a BOM, capture revision, delete the component product (or mark obsolete), rollback | 1. Click Rollback on the captured revision | — | Lines whose component SKU no longer matches an existing product are silently skipped ([apps/bom/views.py:441-443](apps/bom/views.py#L441-L443)). Rollback succeeds with fewer lines. Document. | | |
| TC-NEG-16 | CSRF missing on POST | DevTools, remove `csrfmiddlewaretoken` from a Submit POST | 1. Send | — | 403 Forbidden. | | |
| TC-NEG-17 | Direct URL to alternate of cross-tenant line | Find a Globex BOMLine pk; logged in as Acme, visit `/bom/lines/<globex-line-pk>/alternates/new/` | 1. Visit | — | 404 Not Found. | | |

### 4.14 Cross-Module Integration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-INT-01 | BOM links to PLM product | Any BOM detail card | 1. Click product SKU link in side card | — | Lands on `/plm/products/<pk>/` for that tenant. | | |
| TC-INT-02 | Line component → product detail | Detail Lines tab | 1. Click any component SKU | — | Lands on PLM product detail. | | |
| TC-INT-03 | Cost rollup uses CostElements | Tweak SKU-2001 material cost in `/bom/costs/<pk>/edit/` to `1.00`. Recompute rollup on SKU-4001 EBOM. | 1. Compare rollup before/after | — | Material cost changed proportional to qty (8 × delta), other categories unchanged. | | |
| TC-INT-04 | Cost rollup sub-assembly cascade | SKU-3001 has no direct CostElement of its own ... wait — [seed_bom.py:33](apps/bom/management/commands/seed_bom.py#L33) it does. Set up: create a sub-assembly product Y; build a default released BOM for Y with cost elements on its components; then BOM X uses Y as a line. Recompute X's rollup. | 1. Test cascade | — | Y's costs cascade up into X's material/labor/overhead totals. (Validates [apps/bom/models.py:183-198](apps/bom/models.py#L183-L198).) — **CANDIDATE: needs deliberate setup; may skip in first run.** | | |
| TC-INT-05 | Releasing supersedes prior released | Two seeded released BOMs of same product+type would conflict — seed gives only one. Setup: create second EBOM-A.02 of SKU-4001; submit→approve→release. | 1. Release the new one | — | Original SKU-4001 EBOM A.01 is now Obsolete. (Verifies [apps/bom/views.py:268-271](apps/bom/views.py#L268-L271).) | | |

---

## 5. Bug Log

> Add a row per defect found. Severity guide: **Critical** = blocker (5xx, data loss, IDOR). **High** = wrong data, broken core flow. **Medium** = non-blocking but visible. **Low** = minor polish. **Cosmetic** = pixel-level.

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Screenshot | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | | | | | | | | |
| BUG-02 | | | | | | | | |
| BUG-03 | | | | | | | | |
| BUG-04 | | | | | | | | |
| BUG-05 | | | | | | | | |
| BUG-06 | | | | | | | | |
| BUG-07 | | | | | | | | |
| BUG-08 | | | | | | | | |

---

## 6. Sign-off & Release Recommendation

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---|---|---|---|---|
| 4.1 Authentication & Access | 6 | | | | |
| 4.2 Multi-Tenancy Isolation | 8 | | | | |
| 4.3 CREATE | 12 | | | | |
| 4.4 READ — List Page | 6 | | | | |
| 4.5 READ — Detail Page | 12 | | | | |
| 4.6 UPDATE | 6 | | | | |
| 4.7 DELETE | 6 | | | | |
| 4.8 SEARCH | 13 | | | | |
| 4.9 PAGINATION | 6 | | | | |
| 4.10 FILTERS | 14 | | | | |
| 4.11 Status Transitions / Custom Actions | 27 | | | | |
| 4.12 Frontend UI / UX | 20 | | | | |
| 4.13 Negative & Edge Cases | 17 | | | | |
| 4.14 Cross-Module Integration | 5 | | | | |
| **TOTAL** | **158** | | | | |

**Release Recommendation:** ⬜ GO  ⬜ NO-GO  ⬜ GO-with-fixes

**Rationale (one sentence):**

`__________________________________________________________________________________________`

**Tester signature:** `__________________________`   **Date:** `__________________________`
