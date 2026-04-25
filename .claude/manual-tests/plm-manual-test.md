# PLM Module — Manual Test Plan

> **Author persona:** Senior Manual QA Engineer · **Target:** Module 2 — Product Lifecycle Management ([apps/plm/](../../apps/plm/))
> **Audience:** Tester (developer or non-developer) executing in a browser against a local `runserver`.
> Source files referenced: [apps/plm/urls.py](../../apps/plm/urls.py), [apps/plm/models.py](../../apps/plm/models.py), [apps/plm/views.py](../../apps/plm/views.py), [apps/plm/forms.py](../../apps/plm/forms.py), [templates/plm/](../../templates/plm/), [apps/plm/management/commands/seed_plm.py](../../apps/plm/management/commands/seed_plm.py).

---

## 1. Scope & Objectives

| Item | Detail |
|---|---|
| **Module** | PLM (Module 2) — 5 sub-modules |
| **Sub-modules** | 2.1 Product Master Data · 2.2 Engineering Change Orders (ECO) · 2.3 CAD / Drawing Repository · 2.4 Product Compliance · 2.5 NPI / Stage-Gate |
| **In scope** | Every list, create, detail, edit, delete page; all custom workflow actions (ECO submit/approve/reject/implement, CAD release, NPI stage-gate); search, pagination, filters; UI/UX, multi-tenancy, permissions, negative cases, file uploads. |
| **Out of scope** | Admin (`/admin/`), API, automated tests (see `/sqa-review`), security-only audit. |
| **Browser primary** | Chrome desktop 1920×1080 |
| **Browsers secondary** | Edge desktop, mobile viewport 375×667, tablet 768×1024 |
| **Database** | Local SQLite (default) seeded via `seed_data` |
| **Goal** | Verify CRUD completeness, filter/search retention, status-gating, multi-tenant isolation, and surface any 500/UX defects before release. |

---

## 2. Pre-Test Setup

Run these once before starting the test run.

### 2.1 Start the server (PowerShell-safe)

```powershell
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

> `seed_data` orchestrates `seed_plans` → `seed_tenants` → `seed_plm`. The seeders are idempotent (safe to re-run). To re-seed from scratch, append `--flush`:
> ```powershell
> python manage.py seed_data --flush
> ```

### 2.2 Open the app

Navigate Chrome to `http://127.0.0.1:8000/`.

### 2.3 Login as a TENANT ADMIN (do NOT use `admin` superuser)

> **CRITICAL:** Per [apps/tenants/management/commands/seed_tenants.py:227](../../apps/tenants/management/commands/seed_tenants.py) and CLAUDE.md "Multi-Tenancy Rules", the Django `admin` superuser has `tenant=None` and will see **empty PLM lists**. Always log in with one of the seeded tenant admins below.

| Username | Password | Tenant | Use for |
|---|---|---|---|
| `admin_acme` | `Welcome@123` | Acme Manufacturing | Primary test tenant (Tenant A) |
| `admin_globex` | `Welcome@123` | Globex Industries | Cross-tenant isolation tests (Tenant B) |
| `admin_stark` | `Welcome@123` | Stark Production Co. | Spare |
| `admin` | (your superuser pwd) | NONE | **Negative test only** — must show empty lists |

Login URL: `http://127.0.0.1:8000/login/`. After login, you should land on the dashboard. Click **PLM** in the sidebar (or navigate to `http://127.0.0.1:8000/plm/`).

### 2.4 Verify seed data

After logging in as `admin_acme` and visiting `/plm/`, the dashboard tiles should show non-zero counts:

| Tile | Expected (approx.) | Source view |
|---|---|---|
| Products | **20** | [views.py:60](../../apps/plm/views.py#L60) |
| Open ECOs | ≥ **3** (drafts + submitted, excluding implemented/cancelled/rejected) | [views.py:61-63](../../apps/plm/views.py#L61-L63) |
| CAD documents | **8** | [views.py:64](../../apps/plm/views.py#L64) |
| NPI active | **2** (planning + in_progress) | [views.py:71-73](../../apps/plm/views.py#L71-L73) |
| Compliance compliant | varies (random) | [views.py:65-67](../../apps/plm/views.py#L65-L67) |

Sub-module list pages should show:

| List page | URL | Expected rows (Acme) |
|---|---|---|
| Products | `/plm/products/` | 20 |
| Categories | `/plm/categories/` | 8 |
| ECOs | `/plm/eco/` | 5 |
| CAD documents | `/plm/cad/` | 8 |
| Compliance | `/plm/compliance/` | up to 16 (random per product) |
| NPI projects | `/plm/npi/` | 3 |

### 2.5 Browser / viewport matrix

| Viewport | Browser | When to test |
|---|---|---|
| 1920×1080 (desktop) | Chrome | Every test case (primary) |
| 1366×768 (laptop) | Chrome / Edge | Spot-check key list pages |
| 768×1024 (tablet) | Chrome DevTools | UI checks only (TC-UI-08) |
| 375×667 (mobile) | Chrome DevTools | UI checks only (TC-UI-07) |

### 2.6 Reset between runs

Delete created records in the UI as you go, OR re-run `python manage.py seed_data --flush` to wipe & re-seed PLM data (will also flush tenants/plans — backup before doing this in shared envs).

> **CAD upload note:** Per [seed_plm.py:332-335](../../apps/plm/management/commands/seed_plm.py#L332-L335), seeded CAD documents have **no file binaries**. To test version upload (TC-ACTION-CAD-01) you must upload a real `.pdf`/`.dwg`/`.step` file (max 25 MB). Keep a small `test.pdf` (~1 MB) and an oversized `>25MB` file ready in your downloads folder.

---

## 3. Test Surface Inventory

### 3.1 Routes (every URL — from [apps/plm/urls.py](../../apps/plm/urls.py))

| Sub-module | Action | URL pattern | View | Method |
|---|---|---|---|---|
| Index | Dashboard | `/plm/` | `PLMIndexView` | GET |
| **Categories** | List | `/plm/categories/` | `CategoryListView` | GET |
|  | Create | `/plm/categories/new/` | `CategoryCreateView` | GET/POST |
|  | Edit | `/plm/categories/<pk>/edit/` | `CategoryEditView` | GET/POST |
|  | Delete | `/plm/categories/<pk>/delete/` | `CategoryDeleteView` | POST |
| **Products** | List | `/plm/products/` | `ProductListView` | GET |
|  | Create | `/plm/products/new/` | `ProductCreateView` | GET/POST |
|  | Detail | `/plm/products/<pk>/` | `ProductDetailView` | GET |
|  | Edit | `/plm/products/<pk>/edit/` | `ProductEditView` | GET/POST |
|  | Delete | `/plm/products/<pk>/delete/` | `ProductDeleteView` | POST |
|  | Add revision | `/plm/products/<id>/revisions/new/` | `RevisionCreateView` | POST |
|  | Delete revision | `/plm/revisions/<pk>/delete/` | `RevisionDeleteView` | POST |
|  | Add spec | `/plm/products/<id>/specs/new/` | `SpecificationCreateView` | POST |
|  | Delete spec | `/plm/specs/<pk>/delete/` | `SpecificationDeleteView` | POST |
|  | Add variant | `/plm/products/<id>/variants/new/` | `VariantCreateView` | POST |
|  | Edit variant | `/plm/variants/<pk>/edit/` | `VariantEditView` | GET/POST |
|  | Delete variant | `/plm/variants/<pk>/delete/` | `VariantDeleteView` | POST |
| **ECO** | List | `/plm/eco/` | `ECOListView` | GET |
|  | Create | `/plm/eco/new/` | `ECOCreateView` | GET/POST |
|  | Detail | `/plm/eco/<pk>/` | `ECODetailView` | GET |
|  | Edit (draft only) | `/plm/eco/<pk>/edit/` | `ECOEditView` | GET/POST |
|  | Delete (draft only) | `/plm/eco/<pk>/delete/` | `ECODeleteView` | POST |
|  | Submit | `/plm/eco/<pk>/submit/` | `ECOSubmitView` | POST |
|  | Approve | `/plm/eco/<pk>/approve/` | `ECOApproveView` | POST |
|  | Reject | `/plm/eco/<pk>/reject/` | `ECORejectView` | POST |
|  | Implement | `/plm/eco/<pk>/implement/` | `ECOImplementView` | POST |
|  | Add impacted item | `/plm/eco/<pk>/items/new/` | `ECOImpactedItemAddView` | POST |
|  | Delete impacted item | `/plm/eco/items/<pk>/delete/` | `ECOImpactedItemDeleteView` | POST |
|  | Add attachment | `/plm/eco/<pk>/attachments/new/` | `ECOAttachmentAddView` | POST |
|  | Delete attachment | `/plm/eco/attachments/<pk>/delete/` | `ECOAttachmentDeleteView` | POST |
| **CAD** | List | `/plm/cad/` | `CADListView` | GET |
|  | Create | `/plm/cad/new/` | `CADCreateView` | GET/POST |
|  | Detail | `/plm/cad/<pk>/` | `CADDetailView` | GET |
|  | Edit | `/plm/cad/<pk>/edit/` | `CADEditView` | GET/POST |
|  | Delete | `/plm/cad/<pk>/delete/` | `CADDeleteView` | POST |
|  | Upload version | `/plm/cad/<pk>/versions/new/` | `CADVersionUploadView` | POST |
|  | Release version | `/plm/cad/versions/<pk>/release/` | `CADVersionReleaseView` | POST |
|  | Delete version | `/plm/cad/versions/<pk>/delete/` | `CADVersionDeleteView` | POST |
| **Compliance** | List | `/plm/compliance/` | `ComplianceListView` | GET |
|  | Create | `/plm/compliance/new/` | `ComplianceCreateView` | GET/POST |
|  | Detail | `/plm/compliance/<pk>/` | `ComplianceDetailView` | GET |
|  | Edit | `/plm/compliance/<pk>/edit/` | `ComplianceEditView` | GET/POST |
|  | Delete | `/plm/compliance/<pk>/delete/` | `ComplianceDeleteView` | POST |
| **NPI** | List | `/plm/npi/` | `NPIListView` | GET |
|  | Create | `/plm/npi/new/` | `NPICreateView` | GET/POST |
|  | Detail | `/plm/npi/<pk>/` | `NPIDetailView` | GET |
|  | Edit | `/plm/npi/<pk>/edit/` | `NPIEditView` | GET/POST |
|  | Delete | `/plm/npi/<pk>/delete/` | `NPIDeleteView` | POST |
|  | Edit stage | `/plm/npi/stages/<pk>/edit/` | `NPIStageEditView` | GET/POST |
|  | Add deliverable | `/plm/npi/stages/<id>/deliverables/new/` | `NPIDeliverableAddView` | POST |
|  | Edit deliverable | `/plm/npi/deliverables/<pk>/edit/` | `NPIDeliverableEditView` | GET/POST |
|  | Complete deliverable | `/plm/npi/deliverables/<pk>/complete/` | `NPIDeliverableCompleteView` | POST |
|  | Delete deliverable | `/plm/npi/deliverables/<pk>/delete/` | `NPIDeliverableDeleteView` | POST |

### 3.2 Search inputs (per list page)

| Page | `q=` searches | Source |
|---|---|---|
| Categories | `name`, `code` | [views.py:96](../../apps/plm/views.py#L96) |
| Products | `sku`, `name` | [views.py:165](../../apps/plm/views.py#L165) |
| ECOs | `number`, `title` | [views.py:362](../../apps/plm/views.py#L362) |
| CAD | `drawing_number`, `title` | [views.py:574](../../apps/plm/views.py#L574) |
| Compliance | `product__sku`, `product__name`, `certification_number` | [views.py:714-718](../../apps/plm/views.py#L714-L718) |
| NPI | `code`, `name` | [views.py:811](../../apps/plm/views.py#L811) |

### 3.3 Filter parameters (per list page)

| Page | Filter param | Source |
|---|---|---|
| Categories | `active` (active/inactive) | [views.py:97-101](../../apps/plm/views.py#L97-L101) |
| Products | `category` (pk), `product_type`, `status` | [views.py:166-174](../../apps/plm/views.py#L166-L174) |
| ECOs | `status`, `priority`, `change_type` | [views.py:363-366](../../apps/plm/views.py#L363-L366) |
| CAD | `doc_type`, `active` | [views.py:575-582](../../apps/plm/views.py#L575-L582) |
| Compliance | `status`, `standard` (pk) | [views.py:719-724](../../apps/plm/views.py#L719-L724) |
| NPI | `status`, `current_stage` | [views.py:812-817](../../apps/plm/views.py#L812-L817) |

### 3.4 Pagination

All list views use `paginate_by = 20` ([views.py:90](../../apps/plm/views.py#L90), [159](../../apps/plm/views.py#L159), [356](../../apps/plm/views.py#L356), [568](../../apps/plm/views.py#L568), [706](../../apps/plm/views.py#L706), [805](../../apps/plm/views.py#L805)).

> **Known concern (verify in TC-PAGE):** The pagination links in templates only forward the `q` param (Products / Categories) or none at all (ECO / CAD / Compliance / NPI). Filters may be **dropped** when clicking page 2. See [products/list.html:76-78](../../templates/plm/products/list.html#L76-L78), [eco/list.html:81-83](../../templates/plm/eco/list.html#L81-L83), etc.

### 3.5 File upload constraints (from [forms.py](../../apps/plm/forms.py))

| Form | Allowed extensions | Max size |
|---|---|---|
| ECO attachment | `.pdf .dwg .dxf .step .stp .iges .igs .png .jpg .jpeg .svg .zip .docx .xlsx .txt .csv` | 25 MB |
| CAD version | `.pdf .dwg .dxf .step .stp .iges .igs .png .jpg .jpeg .svg .zip` | 25 MB |
| Compliance certificate | `.pdf .png .jpg .jpeg .zip` | 25 MB |
| Product image | (Django ImageField — no extra extension allowlist) | (none enforced) |

### 3.6 Status-gating

| Entity | Edit/Delete allowed when | Source |
|---|---|---|
| ECO | `status == 'draft'` | [models.py:212](../../apps/plm/models.py#L212), [eco/list.html:64](../../templates/plm/eco/list.html#L64), [eco/detail.html:16](../../templates/plm/eco/detail.html#L16) |
| Product | always (no status gate) | [views.py:238-243](../../apps/plm/views.py#L238-L243) |
| Category | always — but DELETE blocked if `products.exists()` | [views.py:143-147](../../apps/plm/views.py#L143-L147) |
| CAD doc | always | [views.py:639-644](../../apps/plm/views.py#L639-L644) |
| Compliance | always | [views.py:789-794](../../apps/plm/views.py#L789-L794) |
| NPI project | always | [views.py:885-890](../../apps/plm/views.py#L885-L890) |

---

## 4. Test Cases

> **How to use:** Each row is one runnable test case. Execute steps in order, mark **Pass / Fail** in the column. If anything diverges from Expected Result, log a row in §5 Bug Log.

---

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous redirect — PLM index | Logged out (clear cookies) | 1. Open `http://127.0.0.1:8000/plm/` in a private window. | — | Browser is redirected to `/login/?next=/plm/`. Login form is visible. | | |
| TC-AUTH-02 | Anonymous redirect — Product list | Logged out | 1. Open `http://127.0.0.1:8000/plm/products/`. | — | Redirect to `/login/?next=/plm/products/`. | | |
| TC-AUTH-03 | Anonymous redirect — ECO list | Logged out | 1. Open `http://127.0.0.1:8000/plm/eco/`. | — | Redirect to `/login/?next=/plm/eco/`. | | |
| TC-AUTH-04 | Tenant admin login → can see PLM data | None | 1. Go to `/login/`. 2. Username `admin_acme`, password `Welcome@123`. 3. After redirect, click **PLM** in left sidebar. | — | Lands on `/plm/`. Dashboard shows Products = 20, CAD = 8, NPI active = 2 (or seeded values). | | |
| TC-AUTH-05 | Superuser sees empty PLM lists (BY DESIGN) | Django superuser `admin` exists and has `tenant=None` | 1. Logout. 2. Login as `admin` (your superuser). 3. Visit `/plm/products/`. | — | Empty list with message "No products yet." Dashboard tiles = 0. **This is correct.** Per [CLAUDE.md Multi-Tenancy Rules](../../.claude/CLAUDE.md). | | |
| TC-AUTH-06 | Logout from PLM | Logged in as `admin_acme` | 1. Click user avatar top-right → **Logout** (or visit `/logout/`). 2. Try to revisit `/plm/`. | — | Redirected to login. Session cleared. | | |

---

### 4.2 Multi-Tenancy Isolation

> **CLAUDE.md mandate:** every test plan must include an IDOR check. Use a `python manage.py shell` window to fetch a Tenant B (Globex) record's pk, then visit it as Tenant A (Acme).

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Cross-tenant Product view → 404 | Logged in as `admin_acme`. Open a 2nd terminal: `python manage.py shell` → `from apps.plm.models import Product; from apps.core.models import Tenant; t=Tenant.objects.get(slug='globex'); Product.objects.filter(tenant=t).first().pk` | 1. Note the Globex product pk (e.g. 27). 2. In browser address bar visit `/plm/products/27/`. | Globex product pk | Page returns **404 Not Found** (NOT the product detail). | | |
| TC-TENANT-02 | Cross-tenant ECO edit → 404 | Same as above; pick a Globex draft ECO pk via `EngineeringChangeOrder.objects.filter(tenant=t, status='draft').first().pk` | 1. Visit `/plm/eco/<globex-eco-pk>/edit/`. | Globex ECO pk | 404. | | |
| TC-TENANT-03 | Cross-tenant CAD delete POST → 404 | Pick Globex CAD pk: `CADDocument.objects.filter(tenant=t).first().pk` | 1. Open DevTools console. 2. Run: `fetch('/plm/cad/<pk>/delete/', {method:'POST', headers:{'X-CSRFToken': document.cookie.match(/csrftoken=([^;]+)/)[1]}, credentials:'same-origin'})` | Globex CAD pk | Response status `404`. Globex's CAD document is **not** deleted (verify by logging in as `admin_globex`). | | |
| TC-TENANT-04 | Cross-tenant NPI detail → 404 | Pick Globex NPI pk | 1. Visit `/plm/npi/<globex-npi-pk>/`. | — | 404. | | |
| TC-TENANT-05 | Acme product list excludes Globex products | Logged in as `admin_acme` | 1. Visit `/plm/products/`. 2. Logout, login as `admin_globex`. 3. Visit `/plm/products/`. | — | Each tenant sees only its own 20 seeded products. SKUs are duplicated (both tenants have `SKU-1001`) but they are DIFFERENT records. | | |
| TC-TENANT-06 | Compliance standards (shared catalog) visible to both tenants | Login as `admin_acme`, then `admin_globex` | 1. Each visits `/plm/compliance/new/`. 2. Open the **Standard** dropdown. | — | Both tenants see the same 8 standards (`ISO_9001`, `ISO_14001`, `RoHS`, `REACH`, `CE`, `UL`, `FCC`, `IPC`) — these are global per [models.py:349](../../apps/plm/models.py#L349). | | |

---

### 4.3 CREATE

#### 4.3.1 Categories

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-CAT-01 | Create category — all fields | Logged in as `admin_acme`. On `/plm/categories/`. | 1. Click **+ New Category** (top-right). 2. Type Name = `Test Cat A`. 3. Type Code = `TCA`. 4. Pick Parent = `Components`. 5. Type Description = `Manual test category`. 6. Leave **Is active** checked. 7. Click **Save**. | Name=`Test Cat A`, Code=`TCA`, Parent=`Components` | Redirected to `/plm/categories/`. Green toast `Category "Test Cat A" created.`. New row visible with Parent = Components, Status badge = Active. | | |
| TC-CREATE-CAT-02 | Create category — required only (Name + Code) | On `/plm/categories/new/` | 1. Name = `MinCat`, Code = `MIN`. 2. Save. | — | Created successfully. Parent = `—` in list. | | |
| TC-CREATE-CAT-03 | Create — missing Name | On `/plm/categories/new/` | 1. Leave Name blank. 2. Code = `XXX`. 3. Save. | — | Form re-renders. Red `This field is required.` under **Name**. No DB write. | | |
| TC-CREATE-CAT-04 | Create — duplicate code (unique_together with tenant) | An existing category with code `MIN` from TC-CREATE-CAT-02 | 1. New Category. 2. Name = `Dup`, Code = `MIN`. 3. Save. | — | Form-level error `Product category with this Tenant and Code already exists.` (NOT a 500). Per [CLAUDE.md "Unique-together + tenant trap"](../../.claude/CLAUDE.md). | | |
| TC-CREATE-CAT-05 | Create — XSS in name | New Category | 1. Name = `<script>alert('xss')</script>`. 2. Code = `XSS`. 3. Save. | `<script>alert('xss')</script>` | Created. List page shows the literal text **escaped** (`&lt;script&gt;...`); NO alert popup fires; no JS console error. | | |

#### 4.3.2 Products

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-PROD-01 | Create product — all fields | Logged in as `admin_acme`. On `/plm/products/`. | 1. Click **+ New Product**. 2. SKU = `SKU-TEST-1`. 3. Name = `Manual Test Product`. 4. Category = `Components`. 5. Type = `Component`. 6. UoM = `Each`. 7. Description = `QA test product`. 8. Status = `Active`. 9. Skip image. 10. Save. | SKU=`SKU-TEST-1` | Redirected to `/plm/products/<pk>/`. Toast `Product "SKU-TEST-1" created.`. Detail page shows all entered values. Product appears in `/plm/products/` list. | | |
| TC-CREATE-PROD-02 | Create product — required only (SKU + Name) | On `/plm/products/new/` | 1. SKU = `SKU-MIN`. 2. Name = `Minimal`. 3. Save. | — | Created. Detail shows Category = `—`, Type defaults to `Component`, UoM defaults to `Each`, Status defaults to `Draft`. | | |
| TC-CREATE-PROD-03 | Create — missing SKU | On `/plm/products/new/` | 1. Name = `NoSku`. 2. Save. | — | Form re-renders with red `This field is required.` under **SKU**. | | |
| TC-CREATE-PROD-04 | Create — duplicate SKU (unique per tenant) | TC-CREATE-PROD-01 created `SKU-TEST-1` | 1. New Product. 2. SKU = `SKU-TEST-1`, Name = `Dup`. 3. Save. | — | Form-level error containing `Tenant` and `Sku` (NOT a 500). Per [models.py:90](../../apps/plm/models.py#L90). | | |
| TC-CREATE-PROD-05 | Create — XSS in name | New Product | 1. SKU = `SKU-XSS`, Name = `<img src=x onerror=alert(1)>`. 2. Save. | `<img src=x onerror=alert(1)>` | Created. List/detail show the text escaped, no JS executes. | | |
| TC-CREATE-PROD-06 | Create — upload image | New Product | 1. Fill SKU `SKU-IMG`, Name `WithImage`. 2. Click **Choose file** in Image. 3. Pick a `<5MB` PNG/JPG. 4. Save. | small.png | Created. Detail page shows the uploaded image preview. File saved under `media/plm/products/`. | | |

#### 4.3.3 ECO

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-ECO-01 | Create ECO — all fields | On `/plm/eco/` | 1. Click **+ New ECO**. 2. Title = `Manual ECO Test`. 3. Description = `Testing ECO creation`. 4. Change type = `Design`. 5. Priority = `High`. 6. Reason = `QA verification`. 7. Target implementation date = (today + 30 days). 8. Save. | Title=`Manual ECO Test` | Redirected to `/plm/eco/<pk>/`. Toast `ECO ECO-00006 created.` (number = next sequence — see [views.py:388](../../apps/plm/views.py#L388)). Status badge = `Draft`. Requested by = `admin_acme`. | | |
| TC-CREATE-ECO-02 | Create — missing title | On `/plm/eco/new/` | 1. Leave Title blank. 2. Save. | — | Form error under Title. | | |
| TC-CREATE-ECO-03 | ECO number auto-generated & sequential | TC-CREATE-ECO-01 created ECO-00006 | 1. Create another ECO with title `Second test`. | — | Number = `ECO-00007`. | | |

#### 4.3.4 CAD

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-CAD-01 | Create CAD doc — all fields | On `/plm/cad/` | 1. Click **+ New Drawing**. 2. Drawing # = `DRW-MAN-01`. 3. Title = `Manual Test Drawing`. 4. Linked Product = pick `SKU-1001 — Stainless Steel...`. 5. Type = `2D Drawing`. 6. Description = `QA`. 7. **Is active** checked. 8. Save. | DRW-MAN-01 | Redirect to `/plm/cad/<pk>/`. Toast `Drawing DRW-MAN-01 created.`. Detail page shows no versions yet (current version `—`). | | |
| TC-CREATE-CAD-02 | Create — duplicate drawing # | TC-CREATE-CAD-01 created `DRW-MAN-01` | 1. New Drawing. 2. Drawing # = `DRW-MAN-01`. 3. Title = `Dup`. 4. Save. | — | Form-level error (not 500) per [models.py:310](../../apps/plm/models.py#L310). | | |

#### 4.3.5 Compliance

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-COMP-01 | Create compliance — all fields | On `/plm/compliance/` | 1. Click **+ New Record**. 2. Product = `SKU-2001 — M3 Hex Bolt 8mm`. 3. Standard = `ISO_9001 — ISO 9001 — Quality Management`. 4. Status = `Compliant`. 5. Cert # = `CRT-MAN-001`. 6. Issuing body = `BSI`. 7. Issued date = (today − 90). 8. Expiry date = (today + 365). 9. Skip certificate file. 10. Notes = `Manual test`. 11. Save. | — | Redirected to `/plm/compliance/<pk>/`. Toast `Compliance record created.`. Detail shows entered values. | | |
| TC-CREATE-COMP-02 | Create — duplicate (product + standard) | TC-CREATE-COMP-01 saved `SKU-2001 + ISO_9001` | 1. New Record. 2. Same product + same standard. 3. Save. | — | Form-level error per `unique_together = ('tenant', 'product', 'standard')` ([models.py:398](../../apps/plm/models.py#L398)) — NOT a 500. | | |

#### 4.3.6 NPI

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-NPI-01 | Create NPI project — all fields | On `/plm/npi/` | 1. Click **+ New Project**. 2. Name = `Manual Test NPI`. 3. Description = `QA`. 4. Product = `SKU-4001 — Industrial Controller Mk-3`. 5. Project manager = `admin_acme`. 6. Status = `Planning`. 7. Current stage = `Concept`. 8. Target launch date = (today + 180). 9. Save. | — | Redirect to `/plm/npi/<pk>/`. Toast `NPI project NPI-00004 created.`. Detail page shows **7 stages** auto-created (Concept → Launch) per [views.py:843-848](../../apps/plm/views.py#L843-L848). | | |
| TC-CREATE-NPI-02 | NPI code auto-generated & sequential | TC-CREATE-NPI-01 created `NPI-00004` | 1. Create another NPI with name `Second NPI`. | — | Code = `NPI-00005`. | | |

---

### 4.4 READ — List Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-LIST-CAT-01 | Categories list renders | Seeded data, logged in as `admin_acme` | 1. Visit `/plm/categories/`. | — | 8 rows. Columns: Code, Name, Parent, Products (count), Status, Actions. Parent shows `—` for top-level. Products column shows non-zero counts for `Components`, `Metals`, etc. No `None` literals. | | |
| TC-LIST-PROD-01 | Products list renders | Same | 1. Visit `/plm/products/`. | — | 20 rows. Columns: SKU, Name, Category, Type, UoM, Rev, Status, Actions. Each row shows badge for Type (info), badge for Status (color-coded). Rev column shows revision code (`B` for seeded products). | | |
| TC-LIST-ECO-01 | ECOs list renders | Same | 1. Visit `/plm/eco/`. | — | 5 rows ordered newest-first. Status badges colored: Draft = gray, Submitted = warning, Approved = success, Implemented = success solid, Rejected = danger. Priority badges: Critical = danger, High = warning. | | |
| TC-LIST-CAD-01 | CAD list renders | Same | 1. Visit `/plm/cad/`. | — | 8 rows. Columns: Drawing #, Title, Type, Linked Product, Current Version, Status, Actions. Current Version shows `—` (seed creates docs without versions). Drawing # is a clickable link. | | |
| TC-LIST-COMP-01 | Compliance list renders | Same | 1. Visit `/plm/compliance/`. | — | Up to 16 rows. Columns: Product, Standard, Cert #, Status, Issued, Expires, Actions. Status badges colored. If any record expires within 30 days, the warning icon appears next to the expiry date AND the page subtitle shows `N expiring within 30 days` badge. | | |
| TC-LIST-NPI-01 | NPI list renders | Same | 1. Visit `/plm/npi/`. | — | 3 rows. Columns: Code, Name, Product, Manager, Stage, Status, Target Launch, Actions. Stage badge shows current stage label (e.g. `Design`, `Validation`). | | |
| TC-LIST-EMPTY-01 | Empty state — no matching search | On `/plm/products/` | 1. Type `xyznotreal` in the Search box. 2. Click **Filter**. | — | Table shows `No products yet. Create the first one.` link. | | |

---

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DETAIL-PROD-01 | Product detail — all sections | On `/plm/products/`, click any seeded SKU (e.g. `SKU-2001`) | 1. Click `SKU-2001` link. | — | Detail page renders. Shows SKU, Name, Category, Type, UoM, Status, Description, current revision badge. Tabs/sections: **Specifications** (3 entries), **Revisions** (A superseded, B active), **Variants** (only for finished_goods), **CAD Documents** (linked drawings if any), **Compliance** (linked records if any). No `None` literals. | | |
| TC-DETAIL-ECO-01 | ECO detail — overview & tabs | On `/plm/eco/`, click `ECO-00001` | 1. Click `ECO-00001` link. | — | Shows status badge, sidebar with Number/Type/Priority/dates. Tabs: **Overview** (description + reason), **Impacted Items**, **Approvals**, **Attachments**. For Draft ECO, top-right shows **Edit**, **Submit for review**, **Delete** buttons. | | |
| TC-DETAIL-CAD-01 | CAD detail — versions table | On `/plm/cad/`, click any drawing | 1. Click `DRW-001` link. | — | Detail page shows drawing metadata + versions table (empty for seeded docs). Upload form available. | | |
| TC-DETAIL-COMP-01 | Compliance detail — audit log | On `/plm/compliance/`, click any record | 1. Click any **eye icon**. | — | Shows product, standard, status, cert #, issuing body, dates, notes. Audit Entries section may be empty (only created via signal — verify [signals.py](../../apps/plm/signals.py)). | | |
| TC-DETAIL-NPI-01 | NPI detail — stages + deliverables | On `/plm/npi/`, click `NPI-00001` | 1. Click `NPI-00001` link. | — | Shows project header + 7 stages (Concept → Launch). Each stage row shows status badge + gate decision + deliverables (1–3 each from seed). Each stage has an Edit button. Each deliverable has Edit / Complete / Delete actions. | | |
| TC-DETAIL-NPI-02 | NPI stage shows seeded gate decisions | NPI-00001 detail | 1. Scroll through stages. | — | For `in_progress` projects, earlier stages show `passed` + `Go` gate; current stage shows `in_progress`; later stages show `pending`. | | |

---

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-EDIT-CAT-01 | Edit category — pre-fill + save | TC-CREATE-CAT-01 created `Test Cat A` | 1. On `/plm/categories/`, click pencil icon for `Test Cat A`. 2. Verify form pre-filled with current values. 3. Change Name to `Test Cat A v2`. 4. Save. | — | Redirect to list. Toast `Category updated.`. Row shows new name. | | |
| TC-EDIT-PROD-01 | Edit product — pre-fill + save | TC-CREATE-PROD-01 created `SKU-TEST-1` | 1. On `/plm/products/`, click pencil for `SKU-TEST-1`. 2. Form pre-filled. 3. Change Status from Active → Obsolete. 4. Save. | — | Redirect to detail page. Toast `Product updated.`. Status badge = `Obsolete` (warning color). | | |
| TC-EDIT-PROD-02 | Edit product — invalid (blank SKU) | On product edit form | 1. Clear SKU. 2. Save. | — | Form re-renders with error. Original data NOT lost (other fields still filled). | | |
| TC-EDIT-ECO-01 | Edit Draft ECO succeeds | Pick a Draft ECO (`ECO-00001` or `ECO-00005`) | 1. From list click pencil. 2. Change Title to `Edited title`. 3. Save. | — | Redirect to ECO detail. Toast `ECO updated.`. New title visible. | | |
| TC-EDIT-ECO-02 | Edit non-Draft ECO blocked | Pick a Submitted/Approved/Implemented ECO (e.g. `ECO-00003` Approved) | 1. Manually visit `/plm/eco/<pk>/edit/`. | — | Redirect to detail page. Yellow warning toast `ECO can only be edited in Draft status.`. No edit form rendered. | | |
| TC-EDIT-CAD-01 | Edit CAD doc | Any CAD doc | 1. Pencil → change Title to `Updated title`. 2. Save. | — | Redirect to detail. Toast `Drawing updated.`. | | |
| TC-EDIT-COMP-01 | Edit compliance — change status | TC-CREATE-COMP-01 record | 1. Pencil → change Status to `Expired`. 2. Save. | — | Redirect. Status badge = warning `Expired`. | | |
| TC-EDIT-NPI-01 | Edit NPI project | TC-CREATE-NPI-01 record | 1. Pencil → change Status to `In Progress`. 2. Save. | — | Toast `NPI project updated.`. Status badge = primary `In Progress`. | | |
| TC-EDIT-NPI-STAGE-01 | Edit NPI stage — sets gate decided_at | NPI detail page | 1. Click Edit on `Concept` stage. 2. Status = `Passed`. 3. Gate decision = `Go`. 4. Gate notes = `Manual gate review`. 5. Save. | — | Redirect to NPI detail. Toast contains stage name. Stage shows `Passed`/`Go`. Per [views.py:905-908](../../apps/plm/views.py#L905-L908), `gate_decided_at` is auto-set. | | |
| TC-EDIT-NPI-STAGE-02 | Editing stage to in_progress syncs project current_stage | NPI detail | 1. Edit `Design` stage to `In Progress`. 2. Save. | — | Project's **Current Stage** badge updates to `Design` per [views.py:910-912](../../apps/plm/views.py#L910-L912). | | |
| TC-EDIT-DELIV-01 | Edit deliverable — completing sets completed_at | NPI detail | 1. Click Edit on any pending deliverable. 2. Status = `Done`. 3. Save. | — | Redirect. Status = Done. `completed_at` is auto-set per [views.py:946-948](../../apps/plm/views.py#L946-L948). | | |

---

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-DELETE-CAT-01 | Delete confirm dialog appears | TC-EDIT-CAT-01 record | 1. On `/plm/categories/`, click bin icon for `Test Cat A v2`. | — | Browser `confirm()` dialog reads `Delete category "Test Cat A v2"?`. | | |
| TC-DELETE-CAT-02 | Cancel confirm — record not deleted | TC-DELETE-CAT-01 dialog open | 1. Click **Cancel**. | — | Dialog closes. Row still in list. No DB change. | | |
| TC-DELETE-CAT-03 | Confirm delete — empty category | TC-DELETE-CAT-01 dialog | 1. Click **OK**. | — | Page reloads. Toast `Category deleted.`. Row gone from list. | | |
| TC-DELETE-CAT-04 | Cannot delete category with products | Pick `Components` category (has products) | 1. Click bin → confirm. | — | Page reloads. Red toast `Cannot delete "Components" — it has assigned products.`. Row still present. Per [views.py:143-147](../../apps/plm/views.py#L143-L147). | | |
| TC-DELETE-PROD-01 | Delete product | TC-CREATE-PROD-01 record | 1. Bin icon → confirm `Delete product "SKU-TEST-1"? This cannot be undone.`. | — | Toast `Product deleted.`. Row gone. | | |
| TC-DELETE-ECO-01 | Delete Draft ECO via list bin | Draft ECO (`ECO-00001` or new test ECO) | 1. From list, bin icon → confirm. | — | Toast `ECO deleted.`. Row gone. | | |
| TC-DELETE-ECO-02 | Delete button hidden for non-Draft ECO | Approved ECO (`ECO-00003`) on list | 1. Look at the Actions column for `ECO-00003`. | — | Only the View (eye) button is present. NO Edit, NO Delete. Per [eco/list.html:64-69](../../templates/plm/eco/list.html#L64-L69). | | |
| TC-DELETE-ECO-03 | Direct POST to delete on Approved ECO is rejected | Approved ECO | 1. Open DevTools console. 2. Run `fetch('/plm/eco/<approved-pk>/delete/', {method:'POST', headers:{'X-CSRFToken': document.cookie.match(/csrftoken=([^;]+)/)[1]}, credentials:'same-origin'})` | — | Response `302` redirecting to detail; record NOT deleted. Detail shows red toast `Only Draft ECOs can be deleted.`. | | |
| TC-DELETE-CAD-01 | Delete CAD doc | Any CAD doc | 1. Bin → confirm. | — | Toast `Drawing deleted.`. Row gone. Versions cascade. | | |
| TC-DELETE-COMP-01 | Delete compliance | Any compliance record | 1. Bin → confirm. | — | Toast `Compliance record deleted.`. | | |
| TC-DELETE-NPI-01 | Delete NPI project | TC-CREATE-NPI-01 record | 1. Bin → confirm `Delete project NPI-00004?`. | — | Toast `NPI project deleted.`. Stages + deliverables cascade. | | |
| TC-DELETE-DELIV-01 | Delete deliverable from detail | NPI detail | 1. Click bin on any deliverable → confirm. | — | Reload. Toast `Deliverable deleted.`. Row gone from stage. | | |

---

### 4.8 SEARCH

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-SEARCH-PROD-01 | Empty search returns all | `/plm/products/` | 1. Clear search box. 2. Click Filter. | empty | All 20 products listed. URL has `?q=`. | | |
| TC-SEARCH-PROD-02 | Search by SKU | `/plm/products/` | 1. q = `SKU-1001`. 2. Filter. | `SKU-1001` | One row: `SKU-1001 — Stainless Steel...`. | | |
| TC-SEARCH-PROD-03 | Search by name fragment | `/plm/products/` | 1. q = `Heat`. 2. Filter. | `Heat` | One row: `SKU-2002 — Heat-Sink 40x40mm`. | | |
| TC-SEARCH-PROD-04 | Case-insensitive | `/plm/products/` | 1. q = `STAINLESS`. | `STAINLESS` | Returns `SKU-1001`. (icontains per [views.py:165](../../apps/plm/views.py#L165)) | | |
| TC-SEARCH-PROD-05 | Whitespace trimmed | `/plm/products/` | 1. q = `  bolt  ` (with spaces). | `  bolt  ` | Returns `SKU-2001` (M3 Hex Bolt). Per `.strip()` in view. | | |
| TC-SEARCH-PROD-06 | No-match empty state | `/plm/products/` | 1. q = `qwerty12345`. | nonsense | Empty table with `No products yet.` message. | | |
| TC-SEARCH-PROD-07 | Special chars do not 500 | `/plm/products/` | 1. q = `'%_<>"`. | `'%_<>"` | Page renders OK (likely empty list). No 500. | | |
| TC-SEARCH-CAT-01 | Search categories by code | `/plm/categories/` | 1. q = `MECH`. | `MECH` | One row: `MECH — Mechanical`. | | |
| TC-SEARCH-ECO-01 | Search ECO by number | `/plm/eco/` | 1. q = `ECO-00001`. | `ECO-00001` | One row. | | |
| TC-SEARCH-ECO-02 | Search ECO by title fragment | `/plm/eco/` | 1. q = `Material`. | `Material` | At least 1 row (seeded ECO `Material upgrade for SKU-1001`). | | |
| TC-SEARCH-CAD-01 | Search CAD by drawing # | `/plm/cad/` | 1. q = `MDL-001`. | `MDL-001` | One row: `MDL-001 — Robotic Arm 3D Model`. | | |
| TC-SEARCH-COMP-01 | Search compliance by SKU | `/plm/compliance/` | 1. q = `SKU-4001`. | `SKU-4001` | Records for that product (varies by random seed). | | |
| TC-SEARCH-COMP-02 | Search compliance by cert # | `/plm/compliance/` | 1. Note any seeded cert # (e.g. `CRT-SKU-4001-ISO_9001-1234`). 2. q = first half. | partial cert # | At least the matching record returned. | | |
| TC-SEARCH-NPI-01 | Search NPI by name | `/plm/npi/` | 1. q = `Sensor`. | `Sensor` | One row: `NPI-00002 Smart Sensor Pack`. | | |

---

### 4.9 PAGINATION

> **Pre-step:** Pagination only triggers when records exceed 20. The seeded data hits this only for **Compliance** (up to 16 — usually no page 2). To force page 2 on Products, create 5+ extra products via TC-CREATE-PROD steps OR temporarily edit `paginate_by` to `5` (developer task — NOT for testers).

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-PAGE-PROD-01 | Default page size = 20 | Products list with > 20 records (seed all tenants then it's still 20 per tenant — create 5 dummy products) | 1. Visit `/plm/products/`. 2. Count rows. | — | Page 1 shows 20. Pagination shows `1 / 2`. | | |
| TC-PAGE-PROD-02 | Click page 2 | Same | 1. Click `»` next-page link. | — | URL becomes `?page=2`. Remaining 5 records shown. Pagination shows `2 / 2`. | | |
| TC-PAGE-PROD-03 | Search retained on page 2 | > 20 products with name containing `SKU` | 1. Search `SKU` (matches all). 2. Click page 2. | — | URL has `?page=2&q=SKU`. Search box still shows `SKU`. Per [products/list.html:76-78](../../templates/plm/products/list.html#L76-L78). | | |
| TC-PAGE-PROD-04 | **FILTER NOT retained on page 2 (BUG candidate)** | > 20 products | 1. Set Status filter = `Active`. 2. Click page 2. | — | EXPECTED: URL preserves `&status=active`. Likely actual: URL only has `?page=2&q=`. **Log as BUG if filter resets.** Reference [CLAUDE.md "Filter Implementation Rules"](../../.claude/CLAUDE.md). | | |
| TC-PAGE-INVALID-01 | `?page=abc` | Any list | 1. Visit `/plm/products/?page=abc`. | — | Django returns 404 (`PageNotAnInteger`) or graceful first page. NOT a 500. | | |
| TC-PAGE-OUT-01 | `?page=999` | Any list | 1. Visit `/plm/products/?page=999`. | — | 404 (`EmptyPage`). NOT a 500. | | |
| TC-PAGE-CAT-01 | Categories pagination | Need > 20 categories — create extras manually | 1. Same flow as TC-PAGE-PROD-01 → 02. | — | Same retention behavior as Products. | | |
| TC-PAGE-ECO-01 | ECO pagination | Need > 20 ECOs | 1. Same. | — | EXPECTED filter retention. Likely actual: ECO template's pagination forwards NEITHER `q` NOR filters per [eco/list.html:81-83](../../templates/plm/eco/list.html#L81-L83). **Log BUG if so.** | | |

---

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-FILTER-CAT-01 | Filter by Active | `/plm/categories/` | 1. Active dropdown = `Active`. 2. Filter. | — | URL has `?active=active`. Only active categories shown. Dropdown retains `Active`. | | |
| TC-FILTER-CAT-02 | Filter by Inactive | First, edit a category → uncheck `Is active` → save. Then `/plm/categories/` | 1. Active dropdown = `Inactive`. | — | Only the inactive category visible. | | |
| TC-FILTER-PROD-01 | Filter by Category | `/plm/products/` | 1. Category dropdown = `Mechanical`. 2. Filter. | — | URL has `?category=<pk>`. Only Mechanical-category products shown (e.g. `SKU-2001`, `SKU-2002`). Dropdown retains `Mechanical`. | | |
| TC-FILTER-PROD-02 | Filter by Type | `/plm/products/` | 1. Type = `Finished Good`. | — | URL `?product_type=finished_good`. Only finished_good rows. | | |
| TC-FILTER-PROD-03 | Filter by Status | `/plm/products/` | 1. Status = `Active`. | — | All seeded products visible (all are `active`). | | |
| TC-FILTER-PROD-04 | Combined filters AND | `/plm/products/` | 1. Category=`Electronics`, Type=`Component`, Status=`Active`. 2. Filter. | — | URL `?category=...&product_type=component&status=active`. Only ELEC components shown. | | |
| TC-FILTER-PROD-05 | Filter + search | `/plm/products/` | 1. q = `SKU-2`, Type = `Component`. 2. Filter. | — | URL `?q=SKU-2&product_type=component`. Only `SKU-2xxx` components. | | |
| TC-FILTER-PROD-06 | Reset by clearing | After TC-FILTER-PROD-04 | 1. Reset all dropdowns to `Any...`. 2. Clear q. 3. Filter. | — | All 20 products listed. | | |
| TC-FILTER-PROD-07 | Filter for zero results | `/plm/products/` | 1. Type = `Service`. (none seeded) | — | Empty state shown. | | |
| TC-FILTER-ECO-01 | Filter by Status = Approved | `/plm/eco/` | 1. Status = `Approved`. | — | One row: `ECO-00003`. | | |
| TC-FILTER-ECO-02 | Filter by Priority = Critical | `/plm/eco/` | 1. Priority = `Critical`. | — | One row: `ECO-00003`. | | |
| TC-FILTER-ECO-03 | Filter by Change Type = Process | `/plm/eco/` | 1. Change type = `Process`. | — | One row: `ECO-00004`. | | |
| TC-FILTER-CAD-01 | Filter by Type = 3D Model | `/plm/cad/` | 1. Type = `3D Model`. | — | Two rows: `MDL-001`, `MDL-002`. | | |
| TC-FILTER-CAD-02 | Filter by Active=Inactive | `/plm/cad/` | 1. Active = `Inactive`. | — | Empty (all seeded docs are active). | | |
| TC-FILTER-COMP-01 | Filter by Standard | `/plm/compliance/` | 1. Standard dropdown = `ISO_9001 — ...`. | — | URL `?standard=<pk>`. Only ISO_9001 records. Dropdown retains selection. | | |
| TC-FILTER-COMP-02 | Filter by Status = Compliant | `/plm/compliance/` | 1. Status = `Compliant`. | — | Only compliant records. | | |
| TC-FILTER-NPI-01 | Filter by Status = Planning | `/plm/npi/` | 1. Status = `Planning`. | — | One row: `NPI-00002 Smart Sensor Pack`. | | |
| TC-FILTER-NPI-02 | Filter by Stage = Design | `/plm/npi/` | 1. Current stage = `Design`. | — | One row: `NPI-00001 Next-gen Controller`. | | |

---

### 4.11 Status Transitions / Custom Actions

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-ACTION-ECO-01 | Submit Draft ECO | A Draft ECO (e.g. created in TC-CREATE-ECO-01) | 1. Open detail. 2. Click **Submit for review** → confirm. | — | Status badge changes from Draft → `Submitted`. Toast `ECO ECO-XXXXX submitted for review.`. Sidebar shows Submitted timestamp. Edit/Delete buttons disappear; Approve/Reject buttons appear. | | |
| TC-ACTION-ECO-02 | Approve Submitted ECO | Submitted ECO (TC-ACTION-ECO-01 result, or `ECO-00002`) | 1. Click **Approve** → confirm. | — | Status → `Approved`. Toast `ECO ECO-XXXXX approved.`. Sidebar shows Approved timestamp. Approvals tab shows new row with approver = `admin_acme`, decision = Approved. | | |
| TC-ACTION-ECO-03 | Reject Submitted ECO | Another Submitted ECO | 1. Click **Reject** → confirm. | — | Status → `Rejected`. Toast `ECO ... rejected.` (info color). Approvals tab shows rejection row. | | |
| TC-ACTION-ECO-04 | Implement Approved ECO | Approved ECO from TC-ACTION-ECO-02 | 1. Click **Mark Implemented** → confirm. | — | Status → `Implemented`. Toast `... marked Implemented.`. Sidebar shows Implemented timestamp. | | |
| TC-ACTION-ECO-05 | Cannot Submit non-Draft ECO | An Implemented ECO | 1. DevTools fetch POST to `/plm/eco/<pk>/submit/` (action button is hidden in UI). | — | 302 to detail. Yellow toast `Only Draft ECOs can be submitted.`. Status unchanged. | | |
| TC-ACTION-ECO-06 | Cannot Approve Draft ECO | Draft ECO | 1. DevTools POST to `/plm/eco/<pk>/approve/`. | — | 302 with toast `ECO must be Submitted or Under Review to approve.`. | | |
| TC-ACTION-ECO-07 | Add impacted item | Draft ECO detail page | 1. Open Impacted Items tab. 2. Pick a Product. 3. Pick before/after revision. 4. Type Change summary. 5. Click **Add impacted item**. | — | Toast `Impacted item added.`. Row appears in table. | | |
| TC-ACTION-ECO-08 | Remove impacted item | Has at least one impacted item | 1. Click bin in row → confirm. | — | Toast `Impacted item removed.`. Row gone. | | |
| TC-ACTION-ECO-09 | Upload attachment (valid PDF) | Draft ECO detail | 1. Attachments tab. 2. Title = `Test Spec`. 3. Choose `<25MB` test.pdf. 4. Upload. | test.pdf | Toast `Attachment uploaded.`. Row visible. Title link opens the file in new tab. | | |
| TC-ACTION-ECO-10 | Upload — disallowed extension | Draft ECO detail | 1. Title = `bad`. 2. Choose `test.exe` (or any disallowed type). 3. Upload. | test.exe | Red toast contains `Unsupported attachment type ".exe"...`. No row added. | | |
| TC-ACTION-ECO-11 | Upload — file too large | Draft ECO detail | 1. Choose a file > 25 MB. 2. Upload. | bigfile.pdf (>25MB) | Red toast contains `attachment too large (max 25 MB)`. | | |
| TC-ACTION-CAD-01 | Upload first version → becomes current | TC-CREATE-CAD-01 created `DRW-MAN-01` (no versions yet) | 1. Open `/plm/cad/<pk>/`. 2. Version = `1.0`. 3. Choose `test.pdf`. 4. Change notes = `initial`. 5. Status = `Draft`. 6. Upload. | test.pdf | Toast `Version 1.0 uploaded.`. Version row visible. List page now shows `v1.0` in Current Version column (auto-promoted per [views.py:658-660](../../apps/plm/views.py#L658-L660)). | | |
| TC-ACTION-CAD-02 | Release version | Version uploaded as Draft from TC-ACTION-CAD-01 | 1. On CAD detail, click **Release** for version 1.0. | — | Toast `Version 1.0 released.`. Status badge → Released. `released_at` timestamp set. Previous released versions become Obsolete. | | |
| TC-ACTION-CAD-03 | Upload second version | Same drawing | 1. Version = `2.0`. Upload `test2.pdf`. | — | Toast. Two versions in table. Current version still v1.0 (not auto-bumped — only auto on first). | | |
| TC-ACTION-CAD-04 | Release v2.0 supersedes v1.0 | After TC-ACTION-CAD-03 | 1. Click Release on v2.0. | — | v2.0 = Released. v1.0 status flips to Obsolete. Current version on list = v2.0. | | |
| TC-ACTION-CAD-05 | Disallowed file ext | CAD detail | 1. Upload `test.exe`. | test.exe | Red toast `CAD file type ".exe"...`. | | |
| TC-ACTION-CAD-06 | Delete current version detaches | Drawing with current_version set | 1. Click bin on the current version → confirm. | — | Version deleted. Drawing's current_version cleared (`—`) per [views.py:690-692](../../apps/plm/views.py#L690-L692). | | |
| TC-ACTION-NPI-01 | Add deliverable to stage | NPI detail | 1. On any stage row, click `+ Deliverable`. 2. Name = `QA review`. 3. Owner = self. 4. Due date = (today + 14). 5. Status = `Pending`. 6. Save. | — | Toast `Deliverable "QA review" added.`. Row appears under stage. | | |
| TC-ACTION-NPI-02 | Mark deliverable Done via quick button | NPI detail with a pending deliverable | 1. Click **Complete** check on a pending deliverable. | — | Toast `Deliverable "..." marked done.`. Status badge → Done. `completed_at` set per [views.py:957-959](../../apps/plm/views.py#L957-L959). | | |

---

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-UI-01 | Page titles correct | All PLM pages | 1. Visit each list. 2. Check browser tab title. | — | `Products`, `Engineering Change Orders`, `CAD / Drawing Repository`, `Product Compliance`, `NPI / Stage-Gate`, `Product Categories` (per `{% block title %}`). | | |
| TC-UI-02 | Sidebar **PLM** group active when on a PLM page | Logged in | 1. Visit `/plm/products/`. 2. Check sidebar. | — | The PLM nav item is highlighted. The Products sub-item (if any) is highlighted. | | |
| TC-UI-03 | Action buttons aligned right | Each list page | 1. Visit `/plm/products/`, `/plm/eco/`, etc. 2. Inspect Actions column. | — | View / Edit / Delete buttons sit on a single row, right-aligned, with consistent spacing (no overlap, no wrap on 1920×1080). | | |
| TC-UI-04 | Status badge colors match CHOICES | Multi-status data exists (after TC-ACTION-ECO-* runs) | 1. Visit `/plm/eco/`. 2. Inspect badges. | — | Draft = secondary gray, Submitted/Under Review = warning yellow, Approved = success green, Implemented = solid green, Rejected = danger red, Cancelled = gray. Per [eco/list.html:53-58](../../templates/plm/eco/list.html#L53-L58). | | |
| TC-UI-05 | Empty state has CTA link | Wipe products and visit `/plm/products/` | 1. Use `--flush` then login as a fresh tenant or filter for nonsense. | — | Empty state row reads `No products yet. Create the first one.` with the link active. | | |
| TC-UI-06 | Toasts auto-dismiss | After any successful save | 1. Save anything. | — | Toast appears at top. Dismisses or fades after a few seconds (depends on base template config). | | |
| TC-UI-07 | Mobile viewport (375×667) | DevTools device toolbar set to iPhone SE | 1. Visit `/plm/products/`. 2. Scroll. | — | Layout usable. Table scrolls horizontally (table-responsive class). No content offscreen. Filter form stacks vertically. Buttons remain tappable. | | |
| TC-UI-08 | Tablet viewport (768×1024) | DevTools | 1. Visit `/plm/eco/`. 2. Open ECO detail. | — | Tabs render. Sidebar collapses or remains usable. | | |
| TC-UI-09 | Confirm dialog names entity | Click Delete on `SKU-2001` | 1. Click bin → read dialog. | — | Dialog text contains `SKU-2001`. Per [products/list.html:61](../../templates/plm/products/list.html#L61). | | |
| TC-UI-10 | Form errors render under fields | Submit invalid product (blank SKU) | 1. Save. | — | Red error message below the SKU input. | | |
| TC-UI-11 | Required markers on form | Visit `/plm/products/new/` | 1. Inspect labels. | — | Required fields display `*` indicator (depends on crispy-forms defaults). Verify SKU + Name show as required. | | |
| TC-UI-12 | Long text wraps cleanly | Create product with 250-char description | 1. Visit detail page. | 250-char text | No horizontal overflow. Description wraps within the card. | | |
| TC-UI-13 | Keyboard nav — Tab order logical on Product create form | `/plm/products/new/` | 1. Click SKU. 2. Press Tab repeatedly. | — | Focus advances SKU → Name → Category → Type → UoM → Description → Status → Image → Save. Visible focus ring. | | |
| TC-UI-14 | Form submits on Enter | `/plm/products/new/` | 1. Fill SKU + Name. 2. From Name field press Enter. | — | Form submits. (Bootstrap default behavior for single-button forms.) | | |
| TC-UI-15 | No console errors browsing PLM | `admin_acme` | 1. Open DevTools console. 2. Visit each PLM list + 1 detail of each type. | — | Zero red errors. (Warnings allowed.) | | |
| TC-UI-16 | Breadcrumb / back nav present on detail | ECO detail | 1. Visit `/plm/eco/<pk>/`. | — | Top-right shows `← Back` button linking to `/plm/eco/`. Click it returns to list. Per [eco/detail.html:15](../../templates/plm/eco/detail.html#L15). | | |
| TC-UI-17 | Compliance "expiring soon" banner shows count | Login as `admin_acme` (after seed creates compliant records that expire within 30 days; if none, edit one to expiry = today+15) | 1. Visit `/plm/compliance/`. | — | Page subtitle includes `N expiring within 30 days` warning badge. Per [compliance/list.html:10](../../templates/plm/compliance/list.html#L10). | | |
| TC-UI-18 | Cross-link from CAD list to product detail works | `/plm/cad/` | 1. Click any product SKU under "Linked Product". | — | Navigates to `/plm/products/<pk>/`. | | |

---

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-NEG-01 | All required blank → all errors at once | `/plm/products/new/` | 1. Click Save with everything blank. | — | Form re-renders. SKU and Name show errors simultaneously (not just one). | | |
| TC-NEG-02 | Decimal where text not allowed | n/a — PLM has no decimal user inputs | — | — | **N/A** — PLM forms do not expose numeric/decimal fields to the user. | | N/A |
| TC-NEG-03 | Date — far past / far future | `/plm/eco/new/` | 1. Target implementation date = `1900-01-01`. 2. Save. | 1900-01-01 | Accepted (no validator). Verify it round-trips on detail. (Document if business wants future-only.) | | |
| TC-NEG-04 | Date — invalid format via direct GET | `/plm/eco/new/` | 1. Type `not-a-date`. | not-a-date | Browser HTML5 date input rejects invalid input OR Django form returns `Enter a valid date.` Not a 500. | | |
| TC-NEG-05 | Negative variant attributes via JSON | `/plm/products/<pk>/` (Variants tab) | 1. Add variant. 2. Attributes textarea = `weight=-5\ncolor=red`. 3. Save. | `weight=-5` | Saved. Detail shows attribute. (No validator — accepts any string.) | | |
| TC-NEG-06 | Non-allowed CAD file type | `/plm/cad/<pk>/` upload | 1. Pick `test.exe`. | test.exe | Red toast `Unsupported CAD file type ".exe"...`. No DB write. Per [forms.py:30-33](../../apps/plm/forms.py#L30-L33). | | |
| TC-NEG-07 | Oversized CAD file (>25 MB) | CAD detail | 1. Pick a 30 MB file. | bigfile.pdf | Red toast `CAD file too large (max 25 MB).`. Per [forms.py:34-35](../../apps/plm/forms.py#L34-L35). | | |
| TC-NEG-08 | Non-allowed compliance certificate | `/plm/compliance/new/` | 1. Pick `test.docx` (not in `{.pdf, .png, .jpg, .jpeg, .zip}`). | test.docx | Form error `Unsupported certificate type ".docx"...`. | | |
| TC-NEG-09 | Double-submit form (rapid double-click) | `/plm/products/new/` | 1. Fill SKU+Name. 2. Double-click Save fast. | SKU=`SKU-DBL` | Either: (a) one product created + redirect; or (b) on 2nd request, duplicate error. Should NOT 500 or create two records. | | |
| TC-NEG-10 | Browser back after create | After TC-CREATE-PROD-01 | 1. Click browser ← back. 2. Browser may prompt "resubmit?". | — | Browser shows resubmit warning. Cancel → no duplicate. If user confirms → duplicate error (handled per TC-CREATE-PROD-04). | | |
| TC-NEG-11 | Refresh on POST | After successful save (PRG pattern) | 1. After redirect, press F5. | — | Refreshes the GET (list/detail) page. NO form resubmission. | | |
| TC-NEG-12 | Direct GET to delete URL | Logged in | 1. Visit `/plm/products/<pk>/delete/` in address bar (GET, not POST). | — | View only accepts POST. Django returns 405 Method Not Allowed OR a redirect — verify NO data is deleted via GET. | | |
| TC-NEG-13 | Cross-tenant write attempt via POST | Logged in as `admin_acme`. Pick a Globex product pk. | 1. DevTools fetch POST to `/plm/products/<globex-pk>/delete/`. | — | 404. Globex product remains. | | |
| TC-NEG-14 | Stale CSRF token | Logged in, leave a form open 24h then submit | (Document only) | — | Submit returns 403 CSRF failure page. | | Skip if no time. |
| TC-NEG-15 | Spec/variant nested form on missing product | n/a | 1. Visit `/plm/products/99999/specs/new/` (POST). | — | 404 — `get_object_or_404`. | | |
| TC-NEG-16 | Image upload for product — large image | `/plm/products/new/` | 1. Choose 50 MB image. | huge.jpg | Either: rejected by Django default upload size (`DATA_UPLOAD_MAX_MEMORY_SIZE`), or uploaded. **Document what happens — there's no extra ImageField validator.** | | |

---

### 4.14 Cross-Module Integration

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-INT-01 | ECO impacted item references real Product | TC-ACTION-ECO-07 added a product to a Draft ECO | 1. Open ECO detail. 2. Click the SKU link in Impacted Items. | — | Navigates to `/plm/products/<pk>/`. | | |
| TC-INT-02 | CAD doc cross-links to Product | A CAD doc with `product` set | 1. On `/plm/cad/`, click the product SKU. | — | Navigates to product detail. | | |
| TC-INT-03 | Compliance record cross-links to Product | Any compliance record | 1. On `/plm/compliance/`, click product SKU. | — | Navigates to product detail. | | |
| TC-INT-04 | Product detail aggregates cross-module data | `SKU-4001` (used in NPI + has compliance) | 1. Open `/plm/products/<pk>/` for `SKU-4001`. | — | Sections show: Specifications, Revisions A+B, Variants (2), Compliance records (if any), CAD docs (if any linked). | | |
| TC-INT-05 | Delete Product blocked when referenced by ECO impacted item (PROTECT FK) | `ECOImpactedItem.product` is `on_delete=PROTECT` per [models.py:220](../../apps/plm/models.py#L220) | 1. Add a product to an ECO impacted item. 2. Try to delete that product from `/plm/products/`. | — | Should raise `ProtectedError`. **CURRENT VIEW does not catch it** ([views.py:238-243](../../apps/plm/views.py#L238-L243)) — likely renders a 500. **Log as BUG.** | | |
| TC-INT-06 | Delete Category blocked when products attached | TC-DELETE-CAT-04 | (already covered) | — | (See TC-DELETE-CAT-04.) | | |
| TC-INT-07 | NPI project links to Product detail | `NPI-00001` has product set | 1. From NPI list, click the product SKU. | — | Navigates to product detail. | | |

---

## 5. Bug Log

> Fill as you go. Use IDs `BUG-01`, `BUG-02`, …. Severity scale: **Critical** (data loss, 500, security), **High** (broken core flow), **Medium** (degraded flow with workaround), **Low** (cosmetic-but-noticeable), **Cosmetic** (minor visual).

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Screenshot | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | | | | | | | | |
| BUG-02 | | | | | | | | |
| BUG-03 | | | | | | | | |
| BUG-04 | | | | | | | | |
| BUG-05 | | | | | | | | |

---

## 6. Sign-off & Release Recommendation

### 6.1 Tally

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---:|---:|---:|---:|---|
| 4.1 Authentication & Access | 6 | | | | |
| 4.2 Multi-Tenancy Isolation | 6 | | | | |
| 4.3 CREATE | 19 | | | | |
| 4.4 READ — List Page | 7 | | | | |
| 4.5 READ — Detail Page | 6 | | | | |
| 4.6 UPDATE | 11 | | | | |
| 4.7 DELETE | 12 | | | | |
| 4.8 SEARCH | 14 | | | | |
| 4.9 PAGINATION | 7 | | | | |
| 4.10 FILTERS | 18 | | | | |
| 4.11 Status Transitions / Custom Actions | 19 | | | | |
| 4.12 Frontend UI / UX | 18 | | | | |
| 4.13 Negative & Edge Cases | 16 | | | | |
| 4.14 Cross-Module Integration | 7 | | | | |
| **TOTAL** | **166** | | | | |

### 6.2 Release Recommendation

| Field | Value |
|---|---|
| Recommendation | ☐ GO  ☐ NO-GO  ☐ GO-with-fixes |
| Rationale (one sentence) | _______________________________________________ |
| Tester | _________________________  Date: __________ |
| Reviewer | _________________________  Date: __________ |

---

> **Companion automation skill:** [.claude/skills/sqa-review/SKILL.md](../../.claude/skills/sqa-review/SKILL.md). Once this manual pass is green, run `/sqa-review apps/plm` to convert the high-value scenarios into a pytest+Playwright suite.
