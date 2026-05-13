# Sales & Customer Order Management — Manual Test Plan

> Module 17 (sub-modules 17.1 → 17.5). Sources: [apps/sales/models.py](apps/sales/models.py), [apps/sales/views.py](apps/sales/views.py), [apps/sales/forms.py](apps/sales/forms.py), [apps/sales/urls.py](apps/sales/urls.py), [templates/sales/](templates/sales/).

---

## 1. Scope & Objectives

**Scope:** Full module test (every list / create / detail / edit / delete / custom-action page in [apps/sales/](apps/sales/) plus the customer portal at `/sales/portal/`).

**Sub-modules in scope**

| # | Sub-module | Primary entities |
|---|---|---|
| 17.1 | Customer Master & CRM Lite | Customer, CustomerContact, CommunicationLog, CustomerDocument, CustomerCategory, PriceList, PriceListItem |
| 17.2 | Sales Order Processing | SalesOrder, SalesOrderLine, SalesOrderRevision, SalesOrderApprovalLog |
| 17.3 | ATP / CTP Promising | ATPCalculation, CTPCalculation, OrderPromise |
| 17.4 | Delivery & Dispatch + Invoicing | DeliveryRoute, Shipment, ShipmentLine, ProofOfDelivery, SalesInvoice, SalesInvoiceLine |
| 17.5 | Customer Portal | Self-service views scoped to `request.user.customer_company` |

**Objectives**

- Verify CRUD-complete behavior on every entity (per CLAUDE.md "CRUD Completeness Rules").
- Verify status-gated workflow buttons (draft → submitted → confirmed → fulfilled → invoiced → closed; planned → picked → packed → in_transit → delivered).
- Verify tenant isolation (Tenant A admin cannot reach Tenant B records).
- Verify filter retention across pagination + search.
- Verify file-upload validators on `CustomerDocument` (PDF/PNG/JPG/JPEG/DOCX, 25 MB cap) and POD images.
- Verify customer portal scoping (`/sales/portal/`) — a tenant admin user without `customer_company` is bounced to dashboard.
- Surface any 500s, missing buttons, broken filters, or unescaped output.

**Out of scope:** automated tests (use `/sqa-review`), performance / load testing, GL posting end-to-end, MTO → pps.ProductionOrder hand-off (smoke-only here).

---

## 2. Pre-Test Setup

> Run these once before starting. PowerShell-safe.

### 2.1 Start dev server

```powershell
python manage.py runserver
```

Browser: `http://127.0.0.1:8000/`.

### 2.2 Seed demo data

Seed tenants/users first (idempotent), then the sales module:

```powershell
python manage.py seed_tenants
python manage.py seed_sales
```

If sales rows already exist and you want a clean run:

```powershell
python manage.py seed_sales --flush
```

The `--tenant <slug>` arg restricts seeding to one tenant (`acme`, `globex`, or `stark`).

### 2.3 Tenant admin credentials

| Username | Password | Tenant |
|---|---|---|
| `admin_acme` | `Welcome@123` | Acme Manufacturing |
| `admin_globex` | `Welcome@123` | Globex Industries |
| `admin_stark` | `Welcome@123` | Stark Production Co. |

> **Do NOT log in as `admin` (the global superuser)** — it has `tenant=None` and every Sales list will appear empty. This is by design ([apps/sales/views.py:71](apps/sales/views.py#L71)).

### 2.4 Verify seed data exists

After login as `admin_acme`, navigate to `/sales/customers/` — you should see **8 customers** (ACME Industries, Globex Manufacturing, Initech Robotics, Umbrella Aerospace, Soylent Distribution, Hooli Wholesale, Pied Piper Lab, Stark Walk-in). At `/sales/orders/` you should see ~17 sales orders across multiple statuses ([apps/sales/management/commands/seed_sales.py:56](apps/sales/management/commands/seed_sales.py#L56)).

### 2.5 Browser / viewport matrix

| Browser | Viewport | Role |
|---|---|---|
| Chrome (latest) | 1920 × 1080 | Primary |
| Chrome | 375 × 667 | Mobile smoke |
| Chrome | 768 × 1024 | Tablet smoke |
| Edge (latest) | 1920 × 1080 | Secondary |

DevTools open throughout — watch the Console for JS errors and the Network tab for 500s.

### 2.6 Reset between runs

A fresh re-run of `seed_sales --flush` will recreate the 17.1 data and seeded SOs/shipments/invoices. For ad-hoc records you created during testing, delete manually via UI (use the bin icon) or run flush.

### 2.7 Portal user setup

The portal at `/sales/portal/` requires `request.user.customer_company` to be set ([apps/sales/views.py:1454](apps/sales/views.py#L1454)). The default seeder does NOT link any user to a customer. To exercise the portal, in a Django shell:

```powershell
python manage.py shell
```

```python
from apps.accounts.models import User
from apps.sales.models import Customer
u = User.objects.get(username='admin_acme')
u.customer_company = Customer.objects.filter(tenant=u.tenant, name='ACME Industries').first()
u.save()
```

(If `User.customer_company` is absent, mark the portal cases `BLOCKED` and note in §5.)

---

## 3. Test Surface Inventory

### 3.1 URL routes — [apps/sales/urls.py](apps/sales/urls.py)

| Group | URLs |
|---|---|
| Dashboard | `/sales/` |
| Customers | `/sales/customers/`, `/sales/customers/new/`, `/sales/customers/<pk>/`, `/sales/customers/<pk>/edit/`, `/sales/customers/<pk>/delete/`, `/sales/customers/<pk>/toggle-active/` |
| Contacts | `/sales/customers/<cust>/contacts/new/`, `/sales/contacts/<pk>/edit/`, `/sales/contacts/<pk>/delete/` |
| Communications | `/sales/communications/`, `/sales/customers/<cust>/communications/new/`, `/sales/communications/<pk>/edit/`, `/sales/communications/<pk>/delete/` |
| Documents | `/sales/customers/<cust>/documents/upload/`, `/sales/documents/<pk>/delete/`, `/sales/documents/<pk>/download/` |
| Categories | `/sales/categories/`, `/sales/categories/new/`, `/sales/categories/<pk>/edit/`, `/sales/categories/<pk>/delete/` |
| Price Lists | `/sales/pricelists/`, `/sales/pricelists/new/`, `/sales/pricelists/<pk>/`, `/sales/pricelists/<pk>/edit/`, `/sales/pricelists/<pk>/delete/` |
| Price List Items | `/sales/pricelists/<pl>/items/new/`, `/sales/pricelist-items/<pk>/edit/`, `/sales/pricelist-items/<pk>/delete/` |
| Sales Orders | `/sales/orders/`, `/sales/orders/new/`, `/sales/orders/<pk>/`, `/sales/orders/<pk>/edit/`, `/sales/orders/<pk>/delete/` |
| SO Lines | `/sales/orders/<so>/lines/new/`, `/sales/order-lines/<pk>/edit/`, `/sales/order-lines/<pk>/delete/` |
| SO Workflow (POST) | `/sales/orders/<pk>/submit/`, `/sales/orders/<pk>/confirm/`, `/sales/orders/<pk>/release-credit-hold/`, `/sales/orders/<pk>/cancel/`, `/sales/orders/<pk>/hold/`, `/sales/orders/<pk>/resume/`, `/sales/orders/<pk>/revise/`, `/sales/order-revisions/<pk>/` |
| ATP / CTP | `/sales/atp/`, `/sales/atp/new/`, `/sales/atp/<pk>/`, `/sales/ctp/`, `/sales/ctp/new/`, `/sales/ctp/<pk>/`, `/sales/order-lines/<pk>/confirm-promise/` |
| Routes | `/sales/routes/`, `/sales/routes/new/`, `/sales/routes/<pk>/`, `/sales/routes/<pk>/edit/`, `/sales/routes/<pk>/delete/` |
| Shipments | `/sales/shipments/`, `/sales/shipments/new/`, `/sales/shipments/<pk>/`, `/sales/shipments/<pk>/edit/`, `/sales/shipments/<pk>/delete/` |
| Shipment Lines | `/sales/shipments/<sh>/lines/new/`, `/sales/shipment-lines/<pk>/edit/`, `/sales/shipment-lines/<pk>/delete/` |
| Shipment Workflow (POST) | `/sales/shipments/<pk>/pick/`, `/sales/shipments/<pk>/pack/`, `/sales/shipments/<pk>/dispatch/`, `/sales/shipments/<pk>/deliver/`, `/sales/shipments/<pk>/cancel-shipment/`, `/sales/shipments/<sh>/pod/` |
| Invoices | `/sales/invoices/`, `/sales/invoices/new/`, `/sales/invoices/from-shipment/<sh>/`, `/sales/invoices/<pk>/`, `/sales/invoices/<pk>/edit/`, `/sales/invoices/<pk>/delete/`, `/sales/invoices/<pk>/issue/`, `/sales/invoices/<pk>/mark-paid/` |
| Invoice Lines | `/sales/invoices/<inv>/lines/new/`, `/sales/invoice-lines/<pk>/delete/` |
| Portal | `/sales/portal/`, `/sales/portal/orders/`, `/sales/portal/orders/<pk>/`, `/sales/portal/shipments/<pk>/tracking/`, `/sales/portal/invoices/`, `/sales/portal/invoices/<pk>/`, `/sales/portal/documents/<pk>/download/` |

### 3.2 Status enums

| Entity | Statuses |
|---|---|
| `Customer.status` | `active`, `inactive`, `on_hold`, `blacklisted` |
| `SalesOrder.status` | `draft`, `submitted`, `credit_check`, `confirmed`, `in_production`, `fulfilled`, `invoiced`, `closed`, `on_hold`, `cancelled` |
| `Shipment.status` | `planned`, `picked`, `packed`, `in_transit`, `delivered`, `returned`, `cancelled` |
| `DeliveryRoute.status` | `planned`, `dispatched`, `completed`, `cancelled` |
| `SalesInvoice.status` | `draft`, `issued`, `paid`, `overdue`, `cancelled` |
| `CommunicationLog.status` | `open`, `done`, `cancelled` |

### 3.3 Filters available per list (from views.py)

| List | `q` (search fields) | Other filters |
|---|---|---|
| Customers | name, legal_name, code, email, tax_id | status, customer_class, category |
| Communications | subject, body, customer.name, code | type, direction, status |
| Categories | name, code | active=active/inactive |
| Price Lists | name, code | active=active/inactive |
| Sales Orders | code, customer.name, customer_po_number | status, priority, credit_hold (yes/no), customer |
| Shipments | code, sales_order.code, tracking_number, carrier_name | status |
| Routes | code, name, driver_name | status |
| Invoices | code, sales_order.code, customer.name | status |

**Pagination:** `PAGE_SIZE = 25` for every list view ([apps/sales/views.py:58](apps/sales/views.py#L58)).

### 3.4 Status-gated actions

| Entity | Action | Gated By |
|---|---|---|
| SalesOrder | Edit / Add Line / Edit Line / Delete Line | `is_editable()` → `status in ('draft','on_hold')` |
| SalesOrder | Delete | `status == 'draft'` only |
| SalesOrder | Submit | `status == 'draft'` |
| SalesOrder | Confirm | `status in ('submitted','credit_check')` AND `not credit_hold` |
| SalesOrder | Release Credit Hold | `credit_hold AND status=='credit_check'` |
| SalesOrder | Cancel | `status not in ('fulfilled','invoiced','closed','cancelled')` |
| SalesOrder | Revise | `status in ('confirmed','in_production')` |
| Shipment | Edit / Add Line | `is_editable()` → `status in ('planned','picked')` |
| Shipment | Delete | `status in ('planned','cancelled')` only |
| Shipment | Mark Picked | `status == 'planned'` |
| Shipment | Mark Packed | `status == 'picked'` |
| Shipment | Dispatch | `status == 'packed'` |
| Shipment | Mark Delivered | `status == 'in_transit'` |
| Shipment | Record POD | `status == 'delivered' AND no existing pod` |
| Invoice | Edit | `status in ('draft','overdue')` |
| Invoice | Delete | `status == 'draft'` only |
| Invoice | Issue | `status == 'draft'` |
| CommunicationLog | Edit / Delete | row < 24h old (`is_locked()` returns False) |

---

## 4. Test Cases

---

### 4.1 Authentication & Access

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-AUTH-01 | Anonymous redirect — Customers list | Logged out | 1. Open `/sales/customers/` | — | Redirected to `/login/?next=/sales/customers/` | | |
| TC-AUTH-02 | Anonymous redirect — Sales Orders list | Logged out | 1. Open `/sales/orders/` | — | Redirected to `/login/?next=/sales/orders/` | | |
| TC-AUTH-03 | Anonymous redirect — Shipments | Logged out | 1. Open `/sales/shipments/` | — | Redirected to login | | |
| TC-AUTH-04 | Anonymous redirect — Portal | Logged out | 1. Open `/sales/portal/` | — | Redirected to login | | |
| TC-AUTH-05 | Superuser sees empty lists | Logged in as `admin` (superuser) | 1. Open `/sales/customers/`<br>2. Open `/sales/orders/`<br>3. Open `/sales/shipments/` | — | All three lists are empty (BY DESIGN — `request.tenant is None`) | | |
| TC-AUTH-06 | Tenant admin sees full data | Logged in as `admin_acme` | 1. Open `/sales/customers/` | — | At least 8 customers visible | | |
| TC-AUTH-07 | Toggle-active is POST-only | Tenant admin | 1. Browse to `/sales/customers/1/toggle-active/` via GET | — | Redirect to customer detail without status change | | |
| TC-AUTH-08 | CSRF token present on every form | Tenant admin | 1. View page source of `/sales/customers/new/`, `/sales/orders/new/`, `/sales/shipments/new/` | — | Each form contains `<input type="hidden" name="csrfmiddlewaretoken" ...>` | | |
| TC-AUTH-09 | Portal user without customer_company | Tenant admin whose `customer_company` is null | 1. Open `/sales/portal/` | — | Redirect to `dashboard` with warning toast "Your account is not linked to a customer." | | |

---

### 4.2 Multi-Tenancy Isolation

> Pre-step for these cases: log in as `admin_acme`, then open Django Admin (or run a shell) to capture a `pk` of a Globex customer / SO / shipment / invoice to attempt cross-tenant access. Note the `pk` next to each TC ID.

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-TENANT-01 | Cross-tenant Customer detail | Logged in as `admin_acme`; Globex customer pk = `X` | 1. Visit `/sales/customers/X/` | — | HTTP 404 page | | |
| TC-TENANT-02 | Cross-tenant Customer edit | `admin_acme`; pk = `X` | 1. Visit `/sales/customers/X/edit/` | — | HTTP 404 | | |
| TC-TENANT-03 | Cross-tenant SO detail | `admin_acme`; Globex SO pk = `Y` | 1. Visit `/sales/orders/Y/` | — | HTTP 404 | | |
| TC-TENANT-04 | Cross-tenant SO submit (POST) | `admin_acme`; Globex SO pk = `Y` (status=draft) | 1. POST to `/sales/orders/Y/submit/` with CSRF | — | HTTP 404 (record not found via tenant filter) | | |
| TC-TENANT-05 | Cross-tenant Shipment | `admin_acme`; Globex shipment pk = `Z` | 1. Visit `/sales/shipments/Z/` | — | HTTP 404 | | |
| TC-TENANT-06 | Cross-tenant Invoice | `admin_acme`; Globex invoice pk = `W` | 1. Visit `/sales/invoices/W/` | — | HTTP 404 | | |
| TC-TENANT-07 | Cross-tenant Document download | `admin_acme`; Globex CustomerDocument pk = `D` | 1. Visit `/sales/documents/D/download/` | — | HTTP 404 (no file leak) | | |
| TC-TENANT-08 | Cross-tenant Portal order detail | Acme portal user; Globex SO pk = `Y` | 1. Visit `/sales/portal/orders/Y/` | — | HTTP 404 | | |
| TC-TENANT-09 | Cross-tenant Portal shipment tracking | Acme portal user; Globex shipment pk = `Z` | 1. Visit `/sales/portal/shipments/Z/tracking/` | — | HTTP 404 | | |

---

### 4.3 CREATE

#### Customer ([apps/sales/views.py:128](apps/sales/views.py#L128))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| TC-CREATE-01 | Customer — full payload | At `/sales/customers/` | 1. Click **+ Add Customer**<br>2. Fill Name=`Test Co LLC`, Legal name=`Test Co LLC`, Class=`Standard`, Category=`Manufacturing`, Email=`buyer@test.example`, Phone=`+1 415 555 0100`, Tax ID=`TAX-TEST-001`, Billing/Shipping address blocks, City=`San Jose`, State=`CA`, Postal=`95134`, Country=`USA`, Currency=`USD`, Payment terms=`Net 30`, Credit limit=`25000`, Status=`Active`<br>3. Click **Save** | as above | Redirected to customer detail. Auto-code `CUST-NNNNN` assigned. Success toast "Customer 'Test Co LLC' created." | | |
| TC-CREATE-02 | Customer — required only | `/sales/customers/new/` | 1. Fill Name=`Min Co` only<br>2. Save | — | Saved successfully; defaults applied (Currency=USD, Status=active, Payment terms=net30, Class=standard, Credit limit=0) | | |
| TC-CREATE-03 | Customer — missing name | `/sales/customers/new/` | 1. Leave Name blank<br>2. Save | — | Form rejected with red error under Name (`This field is required.`); no record created | | |
| TC-CREATE-04 | Customer — XSS in name | `/sales/customers/new/` | 1. Name=`<script>alert(1)</script>`<br>2. Save | — | Record saved; on list and detail the string renders as escaped text — no JS alert fires | | |
| TC-CREATE-05 | Customer — emoji & unicode | `/sales/customers/new/` | 1. Name=`日本電産 🌐` | — | Saved and displayed correctly | | |
| TC-CREATE-06 | Customer — negative credit limit | `/sales/customers/new/` | 1. Credit limit=`-100`<br>2. Save | — | Validation error under Credit limit (MinValueValidator 0) | | |
| TC-CREATE-07 | Customer — invalid email | `/sales/customers/new/` | 1. Email=`not-an-email` | — | Validation error under Email | | |
| TC-CREATE-08 | Double-submit | `/sales/customers/new/` | 1. Fill required, double-click Save quickly | — | Only one customer record created (browser disables button after first click, OR backend dedupes) | | |

#### CustomerContact ([apps/sales/views.py:200](apps/sales/views.py#L200))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-09 | Contact added under customer | On `/sales/customers/<pk>/`, Contacts tab | 1. Click **+ Add Contact**<br>2. Fill Full name=`Jane Buyer`, Role=`Buyer / Purchasing`, Email=`jane@test.example`, Phone primary=`+1 415 555 0101`, Tick **Is primary**<br>3. Save | — | Redirect to customer detail. Contact appears with "Primary" badge in Contacts tab | | |
| TC-CREATE-10 | Contact — missing full_name | Same | 1. Save without Full name | — | Validation error; no row created | | |

#### CommunicationLog ([apps/sales/views.py:280](apps/sales/views.py#L280))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-11 | Log a call | On customer detail, Communications tab | 1. Click **Log Communication** (or `+` on Communications tab)<br>2. Fill Type=`Phone Call`, Direction=`Inbound`, Subject=`Quote enquiry`, Body=`Asked about pricing`, Occurred at = now<br>3. Save | — | Comm appears with auto-code `COMM-NNNNN`; success toast "Communication logged." | | |
| TC-CREATE-12 | Comm — missing subject | Comm form | 1. Save without Subject | — | Validation error under Subject | | |

#### CustomerDocument ([apps/sales/views.py:342](apps/sales/views.py#L342))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-13 | Upload PDF | Customer detail, Documents tab | 1. Click **Upload Document**<br>2. doc_type=`Contract`, Title=`MSA-2026`, attach a small PDF (< 1 MB) | — | Upload succeeds; row appears in Documents tab; toast "Document uploaded." | | |
| TC-CREATE-14 | Upload — disallowed type | Document form | 1. Title=`Bad`, attach a `.exe` file | — | Validation error: "Allowed file types: PDF, PNG, JPG, JPEG, DOCX." | | |
| TC-CREATE-15 | Upload — oversize | Document form | 1. Title=`Big`, attach a > 25 MB file | — | Validation error: "File exceeds 25 MB limit." | | |

#### CustomerCategory ([apps/sales/views.py:401](apps/sales/views.py#L401))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-16 | Create root category | `/sales/categories/` | 1. **+ New Category**, Name=`Healthcare`, Parent=blank, Active=on, Save | — | Redirect to category list with row present | | |
| TC-CREATE-17 | Create child category | Same | 1. Name=`Hospitals`, Parent=`Healthcare`, Save | — | Saved; parent column shows `Healthcare` | | |
| TC-CREATE-18 | Duplicate name + same parent | unique_together = ('tenant','name','parent') | 1. Create another `Hospitals` under `Healthcare` | — | Form-level error (NOT a 500). If 500 is observed, log as Critical bug — see CLAUDE.md "Unique-together + tenant trap" | | |

#### PriceList ([apps/sales/views.py:466](apps/sales/views.py#L466))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-19 | Create price list | `/sales/pricelists/` | 1. **+ New Price List**, Name=`Promo Q1`, Currency=`USD`, Effective from=today, Active=on, Save | — | Auto-code `PL-NNNNN`; redirected to detail | | |

#### PriceListItem

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-20 | Add item with tier | On price list detail | 1. **+ Add Item**, Product=any, Unit price=`50.00`, Min qty=`1`, Discount=`0`, Save | — | Item row appears | | |
| TC-CREATE-21 | Add second tier at higher min_qty | Same product | 1. Same product, Unit price=`45.00`, Min qty=`10` | — | Both tier rows visible, sorted by min_qty | | |
| TC-CREATE-22 | Duplicate (product, min_qty) | Same | 1. Same product, Min qty=`1` again | — | Form-level error from unique_together, no 500 | | |
| TC-CREATE-23 | Discount > 100 | Same | 1. Discount=`200` | — | Validation error (MaxValueValidator 100) | | |

#### SalesOrder ([apps/sales/views.py:602](apps/sales/views.py#L602))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-24 | Create SO from active customer | `/sales/orders/new/` | 1. Customer=`ACME Industries`, Customer PO=`PO-X-001`, Order date=today, Requested=today+7, Priority=`Normal`, Currency=`USD`, Payment terms=`Net 30`, Save | — | Auto-code `SO-NNNNN`; redirected to detail; addresses snapshotted from customer | | |
| TC-CREATE-25 | Customer dropdown excludes blacklisted | At create form | 1. Open Customer dropdown | — | Only customers with status `active` or `on_hold` listed; no `blacklisted` ([apps/sales/forms.py:162](apps/sales/forms.py#L162)) | | |
| TC-CREATE-26 | Reject blacklisted via clean() | Manually set a customer to blacklisted in admin, then create SO | 1. POST to `/sales/orders/new/` with that customer pk | — | Form-level error "Cannot create an order for a blacklisted customer." | | |

#### SalesOrderLine

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-27 | Add line | Draft SO detail | 1. Click **+ Add Line**<br>2. Product=any, Qty=`10`, UoM=`EA`, Unit price=`100`, Disc=`5`, Tax=`8`, Save | — | Line appears with `line_no=1`, line_total=`950.00`, line_tax=`76.00`; SO totals recomputed in footer | | |
| TC-CREATE-28 | Qty < 0.0001 | Line form | 1. Qty=`0` | — | Validation error (MinValueValidator 0.0001) | | |
| TC-CREATE-29 | Discount > 100 on line | Line form | 1. Disc=`150` | — | Validation error | | |
| TC-CREATE-30 | MTO flag persists | Line form | 1. Tick **Is make-to-order**, Save | — | Line shows blue **MTO** badge in Lines table | | |

#### Shipment ([apps/sales/views.py:1102](apps/sales/views.py#L1102))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-31 | Create shipment from confirmed SO | A confirmed SO exists | 1. `/sales/shipments/new/`, SO dropdown shows only `confirmed`/`in_production`/`fulfilled` SOs<br>2. Pick one, Carrier=`DHL`, Tracking=`DHL12345`, Save | — | Auto-code `SHP-NNNNN`; status=`Planned` | | |
| TC-CREATE-32 | SO dropdown excludes draft | Same | 1. Open SO dropdown | — | No `draft` / `submitted` / `cancelled` SOs visible | | |

#### ShipmentLine

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-33 | Add ship line | Planned shipment detail | 1. **+ Add Line**, Order line=L1, Qty to ship=`5`, Lot=`L-001`, Save | — | Line row appears; Pick status=`Pending` | | |
| TC-CREATE-34 | Add line restricted to SO lines | Same | 1. Open Order line dropdown | — | Only lines from the parent SO are listed ([apps/sales/forms.py:295](apps/sales/forms.py#L295)) | | |

#### SalesInvoice ([apps/sales/views.py:1327](apps/sales/views.py#L1327))

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-35 | Manual invoice | `/sales/invoices/new/` | 1. SO=any, Invoice date=today, Due=today+30, Payment terms=`Net 30`, Save | — | Auto-code `SINV-NNNNN`; status=`Draft` | | |
| TC-CREATE-36 | Generate invoice from shipment | Delivered shipment detail | 1. Click **Generate Invoice** in workflow sidebar | — | Redirects to draft invoice; lines auto-populated from shipment lines; idempotent re-click reuses the same invoice | | |
| TC-CREATE-37 | Add invoice line | Draft invoice | 1. **+ Add Line**, Description=`Service fee`, Qty=`1`, Unit price=`100`, Save | — | Line saved, totals recomputed | | |

#### DeliveryRoute, ATP request, CTP request

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-CREATE-38 | Create delivery route | `/sales/routes/new/` | 1. Name=`North Loop`, Date=today, Driver=`Alice`, Vehicle=`TRK-01`, Save | — | Auto-code `ROUTE-NNNNN`; redirect to detail | | |
| TC-CREATE-39 | Request ATP | `/sales/atp/new/` | 1. Product=any, Qty=`100`, Date=today+3, Method=`Stock + Open PO`, Save | — | Redirect to ATP detail page with auto-code `ATP-NNNNN`; result_status shown | | |
| TC-CREATE-40 | Request CTP | `/sales/ctp/new/` | 1. Product=any, Shortfall=`50`, Target=today+10, Save | — | Redirect to CTP detail `CTP-NNNNN`; earliest completion date displayed | | |

---

### 4.4 READ — List Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-LIST-01 | Customers list renders | Tenant admin | 1. Open `/sales/customers/` | — | Page title "Customers", 25 rows max, columns Code/Name/Class/Category/Currency/Credit Used+Limit/Status/Actions, sidebar Sales group highlighted | | |
| TC-LIST-02 | No `None` literals | Customers list | 1. Open page<br>2. Inspect every cell | — | Empty FKs render as `-` (default filter), never literal `None` | | |
| TC-LIST-03 | Status badges colored | Customers list | 1. Visually inspect Status column | — | active=green, on_hold=yellow, blacklisted=red, inactive=grey | | |
| TC-LIST-04 | Sales Orders list renders | Same | 1. Open `/sales/orders/` | — | Columns Code/Customer/Order Date/Requested/Status/Credit/Grand Total/Actions; Grand Total right-aligned and includes currency | | |
| TC-LIST-05 | SO list shows credit hold badge | Same | 1. Find a credit-hold SO | — | "Hold" yellow badge in Credit column | | |
| TC-LIST-06 | Shipments list renders | Same | 1. Open `/sales/shipments/` | — | Columns Code/SO/Customer/Carrier/Tracking/Status/Planned Ship/Delivered/Actions | | |
| TC-LIST-07 | Invoices list renders | Same | 1. Open `/sales/invoices/` | — | Columns Code/SO/Customer/Date/Due/Status/Grand Total/Paid/Actions | | |
| TC-LIST-08 | Routes list renders | Same | 1. Open `/sales/routes/` | — | Status badges; +New Shipment hidden here | | |
| TC-LIST-09 | Categories list renders | Same | 1. Open `/sales/categories/` | — | Parent column shows tree relationship | | |
| TC-LIST-10 | Price Lists list — default first | Same | 1. Open `/sales/pricelists/` | — | The `is_default=True` price list is sorted to the top (ordering `-is_default, name`) | | |
| TC-LIST-11 | ATP list renders | Same | 1. Open `/sales/atp/` | — | Empty until 4.3 runs TC-CREATE-39; afterwards ATP-codes visible newest-first | | |
| TC-LIST-12 | CTP list renders | Same | 1. Open `/sales/ctp/` | — | Same as above | | |
| TC-LIST-13 | Communications list renders | Same | 1. Open `/sales/communications/` | — | Cross-customer log; date sort newest first | | |
| TC-LIST-14 | Empty state on filtered list | Filter for no-match | 1. `/sales/orders/?status=cancelled&customer=999999` | — | Empty state row "No sales orders yet." (no broken table) | | |
| TC-LIST-15 | Empty Actions column on non-draft SO | SO with status `confirmed` | 1. Find a confirmed SO in list | — | Actions column shows only View (eye) — no Edit / Delete (status-gated) | | |

---

### 4.5 READ — Detail Page

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-DETAIL-01 | Customer detail | `/sales/customers/<pk>/` | 1. Open<br>2. Click each tab: Contacts, Communications, Documents | — | Profile card top; tabs swap content; counts in tab labels match table rows | | |
| TC-DETAIL-02 | Customer detail — Toggle Active | Tenant admin | 1. Click **Toggle Active** | — | Status badge flips active↔inactive; info toast shown | | |
| TC-DETAIL-03 | SO detail — Lines + tabs | A draft SO with ≥ 1 line | 1. Open SO detail | — | Lines table shows line_no, product, qty, unit price, line_total. Footer shows Subtotal/Discount/Tax/Shipping/Grand Total. Right sidebar shows Customer credit summary | | |
| TC-DETAIL-04 | SO detail — Revisions tab | Any SO | 1. Click "Revisions" tab | — | Empty state if no revisions; otherwise version_no, when, by, reason, link | | |
| TC-DETAIL-05 | SO detail — Revise tab gated | Status=draft | 1. Click "Revise" tab | — | Message "Revisions are only available when status is confirmed or in_production." (no form) | | |
| TC-DETAIL-06 | Shipment detail — workflow buttons | Planned shipment | 1. Open detail | — | Only **Mark Picked** + **Cancel** buttons visible; Edit visible top-right | | |
| TC-DETAIL-07 | Invoice detail | A draft invoice | 1. Open `/sales/invoices/<pk>/` | — | Header (code, customer), Lines table, totals; sidebar Issue / Delete buttons | | |
| TC-DETAIL-08 | Route detail | `/sales/routes/<pk>/` | 1. Open | — | Card with header + linked shipments list | | |
| TC-DETAIL-09 | ATP detail JSON snapshot | Created ATP | 1. Open detail | — | `snapshot_json` pretty-printed or rendered as a `<pre>`; available_qty / available_date visible | | |
| TC-DETAIL-10 | Price List detail | Detail of seeded `Standard Price List` | 1. Open | — | Items table grouped by product / min_qty | | |

---

### 4.6 UPDATE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-EDIT-01 | Edit Customer | `admin_acme` on a customer detail | 1. Click **Edit**, change Phone, Save | — | Redirect to detail; new phone shown; toast "Customer updated." | | |
| TC-EDIT-02 | Edit pre-fills every field | Edit Customer | 1. Open Edit page<br>2. Inspect every field | — | All fields pre-populated from current row | | |
| TC-EDIT-03 | Edit invalid → data preserved | Edit Customer | 1. Clear Name<br>2. Save | — | Form re-renders with validation error; other fields you typed are still present | | |
| TC-EDIT-04 | Edit draft SO header | Draft SO detail | 1. Click **Edit**, change Customer PO, Save | — | Updated; detail header reflects new PO | | |
| TC-EDIT-05 | Edit non-editable SO blocked | SO with status=`confirmed` | 1. Manually visit `/sales/orders/<pk>/edit/` | — | Redirect to detail with error toast "Cannot edit a confirmed order." | | |
| TC-EDIT-06 | Edit SO line | Draft SO with line | 1. Click pencil on line<br>2. Change qty from 10 to 20, Save | — | Line updated, SO totals recomputed | | |
| TC-EDIT-07 | Edit confirmed SO line blocked | Confirmed SO | 1. Visit `/sales/order-lines/<pk>/edit/` | — | Redirect to SO detail with error toast | | |
| TC-EDIT-08 | Edit picked shipment blocked | Shipment with status=`picked` | 1. Visit `/sales/shipments/<pk>/edit/` | — | Redirect to detail with error toast | | |
| TC-EDIT-09 | Edit issued invoice blocked | Invoice with status=`issued` | 1. Visit `/sales/invoices/<pk>/edit/` | — | Redirect with toast "Only draft or overdue invoices can be edited." | | |
| TC-EDIT-10 | Edit comm log < 24h | Recent comm (created in TC-CREATE-11) | 1. Click pencil on the comm row | — | Form opens; edit succeeds | | |
| TC-EDIT-11 | Edit locked comm log | A comm log row > 24h old (use shell to set `created_at` back) | 1. Click pencil | — | Redirect to customer detail with error toast "Communication is older than 24h and cannot be edited." | | |

---

### 4.7 DELETE

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-DELETE-01 | Delete customer — confirm dialog | Customer detail, tenant admin | 1. Click **Delete** | — | Native confirm "Delete customer CUST-NNNNN?" appears | | |
| TC-DELETE-02 | Delete customer — cancel | Same | 1. Click cancel on confirm | — | No request fired; customer remains | | |
| TC-DELETE-03 | Delete customer — accept | Same | 1. Confirm | — | Redirect to list; row gone; toast "Customer deleted." | | |
| TC-DELETE-04 | Delete category protected | Category with children OR customers | 1. Try delete | — | Error toast "Cannot delete: ..." (PROTECT FK) — no 500 | | |
| TC-DELETE-05 | Delete draft SO | Draft SO detail | 1. Click **Delete** sidebar button, confirm | — | Redirect to list; toast "Sales order deleted." | | |
| TC-DELETE-06 | Delete non-draft SO blocked | Confirmed SO | 1. POST to `/sales/orders/<pk>/delete/` | — | Error toast "Only draft orders can be deleted. Cancel instead." | | |
| TC-DELETE-07 | Delete planned shipment | Planned shipment | 1. From list, hit delete (if surfaced) OR POST to delete URL | — | Deletion succeeds; back to list | | |
| TC-DELETE-08 | Delete in-transit shipment blocked | In-transit shipment | 1. POST to delete URL | — | Toast "Only planned or cancelled shipments can be deleted." | | |
| TC-DELETE-09 | Delete draft invoice | Draft invoice detail | 1. Click Delete in sidebar | — | Deleted; redirect to list | | |
| TC-DELETE-10 | Delete issued invoice blocked | Issued invoice | 1. POST | — | Toast "Only draft invoices can be deleted." | | |
| TC-DELETE-11 | Delete SO line | Draft SO with ≥ 1 line | 1. Bin icon on line, confirm | — | Line removed, totals recomputed | | |
| TC-DELETE-12 | Delete contact | Customer detail, Contacts tab | 1. Bin icon, confirm | — | Removed | | |
| TC-DELETE-13 | Delete document | Customer detail, Documents tab | 1. Bin icon, confirm | — | Removed; underlying file deleted (best-effort) | | |
| TC-DELETE-14 | GET delete URL is safe | Any | 1. Visit `/sales/customers/<pk>/delete/` via GET (no POST) | — | Redirect to customer list without deletion | | |

---

### 4.8 SEARCH

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-SEARCH-01 | Empty search returns all | `/sales/customers/` | 1. Click Filter without text | — | Full 8-row list | | |
| TC-SEARCH-02 | Search by customer name | Same | 1. Type `acme` in search<br>2. Filter | — | "ACME Industries" row visible; URL has `?q=acme` | | |
| TC-SEARCH-03 | Search by customer code | Same | 1. Type `CUST-00001` | — | Exact row | | |
| TC-SEARCH-04 | Case-insensitive | Same | 1. `ACME` vs `acme` | — | Same results | | |
| TC-SEARCH-05 | Leading/trailing whitespace trimmed | Same | 1. Type `  acme  ` | — | Same as TC-SEARCH-02 (view does `.strip()`) | | |
| TC-SEARCH-06 | No-match empty state | Same | 1. Type `zzz_no_match` | — | Empty row "No customers yet." (with the q param retained in URL) | | |
| TC-SEARCH-07 | SQL meta chars don't 500 | Same | 1. Type `' OR 1=1 --` | — | Empty result OR escaped match; no 500 | | |
| TC-SEARCH-08 | LIKE special chars | Same | 1. Type `100%` then `_test` | — | No 500; rows that literally contain `%` or `_` match | | |
| TC-SEARCH-09 | SO search by customer name | `/sales/orders/?q=ACME` | 1. Submit | — | All ACME SOs returned | | |
| TC-SEARCH-10 | SO search by customer PO | `/sales/orders/?q=PO-X-001` | 1. Submit | — | SO created in TC-CREATE-24 returned | | |
| TC-SEARCH-11 | Shipment search by tracking | `/sales/shipments/?q=DHL12345` | 1. Submit | — | Matching shipment row only | | |
| TC-SEARCH-12 | Invoice search by SO code | `/sales/invoices/?q=SO-00001` | 1. Submit | — | Invoices linked to that SO | | |
| TC-SEARCH-13 | Search retained across pagination | List with > 25 rows; q matches > 25 | 1. Search, click page 2 | — | URL retains `?q=...&page=2`; results still filtered | | |

---

### 4.9 PAGINATION

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-PAGE-01 | Default page size | List with > 25 rows | 1. Open list | — | 25 rows shown; pagination control visible at bottom | | |
| TC-PAGE-02 | "Showing X of Y" text | Same | 1. Inspect pagination footer | — | Correct row range; check the include `templates/sales/_pagination.html` | | |
| TC-PAGE-03 | Click page 2 | Same | 1. Click "2" | — | Next 25 rows shown; URL has `?page=2` | | |
| TC-PAGE-04 | Last partial page | Total = 27 | 1. Navigate to last page | — | 2 rows shown; no broken layout | | |
| TC-PAGE-05 | Out-of-range page | Same | 1. Manually visit `?page=999` | — | Django paginator returns last page (`get_page()` graceful) | | |
| TC-PAGE-06 | Invalid page value | Same | 1. `?page=abc` | — | `get_page()` falls back to page 1; no 500 | | |
| TC-PAGE-07 | Filters retained across pages | Long filtered list | 1. `?status=draft`, click page 2 | — | URL includes both `status=draft&page=2`; results still filtered (the pagination include must propagate request.GET) | | |
| TC-PAGE-08 | Search retained across pages | Same | 1. `?q=ACME&page=2` | — | Both params on every page link | | |

---

### 4.10 FILTERS

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-FILTER-01 | Customer status filter | `/sales/customers/` | 1. Status=`On Hold`, Filter | — | Only `Pied Piper Lab` row | | |
| TC-FILTER-02 | Customer class filter | Same | 1. Class=`Distributor / Reseller` | — | Soylent + Hooli | | |
| TC-FILTER-03 | Customer category filter | Same | 1. Category=`Manufacturing` | — | Customers in that category only | | |
| TC-FILTER-04 | Combined filters AND | Same | 1. Status=`Active` + Class=`Standard` | — | Intersection only | | |
| TC-FILTER-05 | Filter dropdown retains value | Same | 1. Status=`Active`, Filter<br>2. Reload page | — | Dropdown shows "Active" still selected (the `selected` template flag works) | | |
| TC-FILTER-06 | Clear filter | Same | 1. Status=blank, Filter | — | Full list returned | | |
| TC-FILTER-07 | Filter + search combine | Same | 1. q=`Industries` + Status=`Active` | — | Intersection: ACME Industries, Globex Manufacturing — verify rows | | |
| TC-FILTER-08 | SO priority filter | `/sales/orders/` | 1. Priority=`Rush` | — | Only Rush SOs | | |
| TC-FILTER-09 | SO credit_hold filter | Same | 1. Credit hold=`On hold` | — | Only credit_hold=True SOs | | |
| TC-FILTER-10 | SO customer filter | Same | 1. Customer=`ACME Industries` | — | ACME SOs only | | |
| TC-FILTER-11 | Shipment status filter | `/sales/shipments/` | 1. Status=`Planned` | — | Planned shipments only | | |
| TC-FILTER-12 | Invoice status filter | `/sales/invoices/` | 1. Status=`Draft` | — | Draft invoices only | | |
| TC-FILTER-13 | Category active filter | `/sales/categories/?active=inactive` | 1. Submit URL | — | Only is_active=False rows | | |
| TC-FILTER-14 | Comm log type filter | `/sales/communications/?type=call` | 1. Submit | — | Only call rows | | |
| TC-FILTER-15 | Filter for zero matches | `/sales/orders/?status=closed` (if none exist) | 1. Submit | — | Empty state row | | |

---

### 4.11 Status Transitions / Custom Actions

#### Sales Order workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-ACTION-01 | Submit draft SO (passes credit) | Draft SO for a customer well under credit limit, ≥ 1 line | 1. Open SO detail<br>2. Sidebar **Submit** | — | Status → `submitted` OR `credit_check` (depends on grand_total vs credit_available). Approval log row added. Toast | | |
| TC-ACTION-02 | Submit fails credit → credit_check | Draft SO whose grand_total exceeds customer credit_available | 1. Sidebar **Submit** | — | Status → `credit_check`; `credit_hold=True`; warning toast "Submitted - moved to credit_check: ..." | | |
| TC-ACTION-03 | Confirm hidden while credit_hold | SO at credit_check with credit_hold=True | 1. Inspect sidebar | — | No **Confirm** button (`can_confirm()` returns False); **Release Credit Hold** present instead | | |
| TC-ACTION-04 | Release credit hold | SO at credit_check, credit_hold=True | 1. Click **Release Credit Hold** | — | credit_hold cleared; status remains `credit_check`; approval log row | | |
| TC-ACTION-05 | Confirm after credit release | After TC-ACTION-04 | 1. Click **Confirm** | — | Status → `confirmed`; `confirmed_at` + `confirmed_by` set; sidebar Edit / Delete disappear | | |
| TC-ACTION-06 | Confirm with MTO line → drafts ProductionOrder | SO with MTO line | 1. Confirm | — | `pps.ProductionOrder` row created with `source_sales_line=<that line>`. (Open `/pps/orders/` or run a shell query to verify.) | | |
| TC-ACTION-07 | Hold a confirmed SO | Confirmed SO | 1. Sidebar **Hold**, confirm dialog | — | Status → `on_hold`; **Resume** button replaces **Hold** | | |
| TC-ACTION-08 | Resume on-hold SO | After TC-ACTION-07 | 1. Click **Resume** | — | Status → back to confirmed (or previous); approval log | | |
| TC-ACTION-09 | Cancel SO | Confirmed SO | 1. Sidebar **Cancel**, confirm | — | Status → `cancelled`; `cancelled_at` set; Edit/Submit hidden | | |
| TC-ACTION-10 | Cancel forbidden on closed | Closed SO (manually move) | 1. Click Cancel (button should be hidden); attempt POST anyway | — | Service raises ValueError; error toast shown | | |
| TC-ACTION-11 | Revise gated to confirmed/in_production | Draft SO | 1. Open Revise tab | — | "Revisions are only available when status is confirmed or in_production." | | |
| TC-ACTION-12 | Capture revision snapshot | Confirmed SO | 1. Revise tab, optional reason `pricing tweak`, **Snapshot current state** | — | Toast "Snapshot v1 captured."; Revisions tab now lists v1; clicking View opens `/sales/order-revisions/<pk>/` with snapshot JSON | | |
| TC-ACTION-13 | ATP confirm-promise | SO line with at least one ATP record for it | 1. POST to `/sales/order-lines/<line_pk>/confirm-promise/` from a small form / URL hit | — | OrderPromise row created (or updated); SO line `qty_promised` / `promised_date` updated; toast "Promise recorded: stock." (or similar) | | |

#### Shipment workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-ACTION-14 | Mark Picked | Planned shipment with ≥ 1 line | 1. Sidebar **Mark Picked** | — | Status → `picked`; **Mark Packed** appears; Edit still allowed | | |
| TC-ACTION-15 | Mark Packed | Picked shipment | 1. **Mark Packed** | — | Status → `packed`; only Dispatch + Cancel available | | |
| TC-ACTION-16 | Dispatch | Packed shipment | 1. **Dispatch** | — | Status → `in_transit`; `actual_ship_date` set; Cancel still available | | |
| TC-ACTION-17 | Mark Delivered (auto stock movement) | In-transit shipment | 1. **Mark Delivered** | — | Status → `delivered`; toast mentions "Inventory updated"; one `inventory.StockMovement` per line (verify via `/inventory/movements/` or shell) | | |
| TC-ACTION-18 | Record POD | Delivered shipment without existing POD | 1. **Record POD** button → form<br>2. Delivered at = now, Received by=`John Smith`, attach a PNG signature, Save | — | POD section appears on detail with auto-code `POD-NNNNN` | | |
| TC-ACTION-19 | POD oversize signature | POD form | 1. Attach a > 25 MB image | — | Validation error "File exceeds 25 MB limit." | | |
| TC-ACTION-20 | POD disallowed extension | POD form | 1. Attach a `.exe` | — | Validation error "Allowed: PNG, JPG, JPEG, PDF." | | |
| TC-ACTION-21 | Cancel shipment | Planned shipment | 1. Sidebar **Cancel**, confirm | — | Status → `cancelled`; workflow buttons hidden | | |
| TC-ACTION-22 | Out-of-order action rejected | Planned shipment | 1. POST `/sales/shipments/<pk>/pack/` directly (skip pick) | — | Service raises ValueError; error toast; status unchanged | | |

#### Invoice workflow

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-ACTION-23 | Issue invoice | Draft invoice | 1. Sidebar **Issue** | — | Status → `issued`; Edit no longer available; Mark Paid surfaces | | |
| TC-ACTION-24 | Mark Paid | Issued invoice | 1. **Mark Paid** | — | Status → `paid`; `amount_paid` = `grand_total` | | |
| TC-ACTION-25 | Idempotent invoice-from-shipment | Delivered shipment | 1. Click **Generate Invoice** twice | — | Same invoice opened both times; no duplicate created | | |

---

### 4.12 Frontend UI / UX

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-UI-01 | Browser title per page | Any | 1. Open Customers, SOs, Shipments, Invoices | — | Tab titles "Customers", "Sales Orders", "Shipments", "Sales Invoices" respectively | | |
| TC-UI-02 | Sidebar active link | Same | 1. Visit `/sales/orders/` | — | "Sales > Sales Orders" highlighted in sidebar | | |
| TC-UI-03 | Breadcrumb | Detail pages | 1. Open SO detail | — | Title + back-to-list link work | | |
| TC-UI-04 | Empty state on lists | Cleared module (after flush) | 1. Open `/sales/customers/` | — | "No customers yet." centered row | | |
| TC-UI-05 | Status badge colors per choice | SO list | 1. Visually inspect each badge | — | confirmed/in_production=blue; fulfilled/invoiced/closed=green; on_hold/credit_check=yellow; cancelled=red; draft/submitted=grey | | |
| TC-UI-06 | Toast auto-dismiss | Any | 1. Save a change, observe toast | — | Toast appears and dismisses within ~5s | | |
| TC-UI-07 | Confirm dialog names entity | Any | 1. Click bin icon on a customer | — | Confirm reads "Delete customer CUST-NNNNN?" — entity code shown | | |
| TC-UI-08 | Required field markers | Customer create form | 1. Inspect | — | `*` marker (or crispy-forms equivalent) on Name | | |
| TC-UI-09 | Date pickers render | SO create form | 1. Click Order date input | — | Native date picker opens (input `type="date"`) | | |
| TC-UI-10 | Textareas use rows attr | SO form | 1. Inspect notes / billing_address | — | Multi-line input, ~3 rows tall | | |
| TC-UI-11 | Long text wraps | Any list | 1. Create a customer with a 200-char Name | — | Cell wraps; no horizontal overflow | | |
| TC-UI-12 | Mobile viewport — Customers list | DevTools 375x667 | 1. Open `/sales/customers/` | — | Table scrolls horizontally inside `.table-responsive`; no offscreen action buttons | | |
| TC-UI-13 | Tablet viewport | 768x1024 | 1. Open SO detail | — | Two-column layout collapses gracefully | | |
| TC-UI-14 | Keyboard nav | Customer form | 1. Tab through fields | — | Focus ring visible; tab order matches visual order | | |
| TC-UI-15 | Submit on Enter | Customer form | 1. From last text input, press Enter | — | Form submits | | |
| TC-UI-16 | DevTools console clean | Each page | 1. Navigate each list + each detail in 4.4/4.5 | — | No JS errors in console | | |
| TC-UI-17 | Risk flag badge | Customer with risk_flag=True (set via admin) | 1. View list | — | Yellow `!` badge next to name | | |
| TC-UI-18 | MTO badge on line | SO line with `is_make_to_order=True` | 1. Open SO detail | — | Blue "MTO" badge in line's MTO column | | |

---

### 4.13 Negative & Edge Cases

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-NEG-01 | All blank submit | Customer create | 1. Save with no fields filled | — | At least Name shows "This field is required."; no record | | |
| TC-NEG-02 | Letters in decimal field | SO line form | 1. Qty=`abc` | — | Validation error; no 500 | | |
| TC-NEG-03 | Negative shipping_total | SO form | 1. Shipping total=`-50` | — | View accepts but DB-side; observe whether negative renders (no validator on shipping_total). Log as bug if no validation | | |
| TC-NEG-04 | Confirm SO with no lines | Draft SO with 0 lines | 1. Submit | — | Service may allow but is questionable; expect informational warning or empty grand_total. Log behaviour | | |
| TC-NEG-05 | Double-submit on Save | Customer form | 1. Rapid double-click Save | — | One record; or graceful duplicate code error | | |
| TC-NEG-06 | Browser back after create | After TC-CREATE-01 | 1. Press browser Back, then Forward | — | No duplicate submission; form re-renders blank, not resubmitted | | |
| TC-NEG-07 | Refresh on POST | After Save | 1. Press F5 on detail page | — | No browser "resubmit" prompt (PRG pattern enforced) | | |
| TC-NEG-08 | Effective_to before effective_from | PriceList form | 1. effective_from=2026-12-31, effective_to=2026-01-01 | — | View currently allows it (no `clean()`). Log as **Medium bug** — expected: form-level error | | |
| TC-NEG-09 | Due date before invoice_date | Invoice form | 1. invoice_date=today, due_date=today-30 | — | View currently allows. Log behaviour | | |
| TC-NEG-10 | Qty_to_ship > remaining SO qty | ShipmentLine form | 1. SO line has qty_ordered=10, qty_shipped=10; try to ship 5 more | — | Form has no qty cap → ship is accepted. Log as potential bug; expected: warning or hard cap | | |
| TC-NEG-11 | XSS in subject of comm | Comm form | 1. Subject=`"><script>alert(1)</script>` | — | Renders escaped on customer detail; no JS executes | | |
| TC-NEG-12 | Very long text | SO notes | 1. Paste 5000-char string | — | Saved (TextField has no max); renders in tab | | |
| TC-NEG-13 | Unicode in customer code | Auto-coded — N/A | — | — | N/A (code is auto-generated `CUST-NNNNN`) | | |
| TC-NEG-14 | Direct POST to delete with GET-only data | Browser | 1. Visit delete URL via GET | — | Redirect, no deletion | | |
| TC-NEG-15 | Delete locked comm log | Comm > 24h | 1. POST to delete URL | — | Redirect with error toast "Communication is older than 24h and cannot be deleted." | | |
| TC-NEG-16 | Invoice line with qty=0 | Invoice line form | 1. Qty=`0` | — | Validation error (MinValueValidator 0.0001) | | |

---

### 4.14 Cross-Module Integration (smoke only)

| ID | Title | Pre-condition | Steps | Test Data | Expected Result | Pass/Fail |
|---|---|---|---|---|---|---|
| TC-INT-01 | MTO line drafts ProductionOrder | SO with MTO line, confirm it | 1. After TC-ACTION-06, open `/pps/orders/` | — | New ProductionOrder visible with reference back to that SO line | | |
| TC-INT-02 | Shipment delivery emits StockMovement | Shipment with ≥ 1 line, mark delivered | 1. After TC-ACTION-17, open `/inventory/movements/` (or admin)<br>2. Filter for type=outbound or `source_shipment` | — | One `StockMovement` per ShipmentLine | | |
| TC-INT-03 | Idempotent delivery | After TC-ACTION-17 | 1. Re-POST to deliver URL (button is hidden, so curl/postman) | — | Service rejects or no new movements emitted | | |
| TC-INT-04 | Credit_used denorm | Credit-affected customer | 1. After a confirm + invoice + paid cycle, run `python manage.py recompute_credit_used --tenant acme` | — | Command prints affected customer; subsequent credit checks reflect refreshed value | | |
| TC-INT-05 | Portal dashboard KPIs | Portal user linked to a customer with orders + unpaid invoices | 1. Open `/sales/portal/` | — | KPI cards show non-zero Open Orders, In-Transit Shipments, Unpaid Invoices, Outstanding Balance | | |
| TC-INT-06 | Portal order detail visibility | Portal user | 1. Click any order in Recent Orders | — | Order detail shows lines, related shipments, invoices — all scoped to this customer only | | |
| TC-INT-07 | Portal cross-customer block | Portal user A | 1. Manually visit a SO pk that belongs to a DIFFERENT customer in the same tenant | — | HTTP 404 (view filters by `customer=customer`) | | |
| TC-INT-08 | Portal document download scope | Portal user | 1. Try `/sales/portal/documents/<pk>/download/` for a doc whose customer is NOT this user's | — | HTTP 404 | | |

---

## 5. Bug Log

> Fill as you go.

| Bug ID | Test Case ID | Severity | Page URL | Steps to Reproduce | Expected | Actual | Screenshot | Browser |
|---|---|---|---|---|---|---|---|---|
| BUG-01 |  |  |  |  |  |  |  |  |
| BUG-02 |  |  |  |  |  |  |  |  |
| BUG-03 |  |  |  |  |  |  |  |  |

Severity scale: Critical (data loss / security / 500 on common path) · High (workflow blocked, no workaround) · Medium (workaround exists) · Low (rare condition) · Cosmetic (visual only).

---

## 6. Sign-off & Release Recommendation

| Section | Total | Pass | Fail | Blocked | Notes |
|---|---:|---:|---:|---:|---|
| 4.1 Authentication & Access | 9 |  |  |  |  |
| 4.2 Multi-Tenancy Isolation | 9 |  |  |  |  |
| 4.3 CREATE | 40 |  |  |  |  |
| 4.4 READ — List Page | 15 |  |  |  |  |
| 4.5 READ — Detail Page | 10 |  |  |  |  |
| 4.6 UPDATE | 11 |  |  |  |  |
| 4.7 DELETE | 14 |  |  |  |  |
| 4.8 SEARCH | 13 |  |  |  |  |
| 4.9 PAGINATION | 8 |  |  |  |  |
| 4.10 FILTERS | 15 |  |  |  |  |
| 4.11 Status Transitions / Custom Actions | 25 |  |  |  |  |
| 4.12 Frontend UI / UX | 18 |  |  |  |  |
| 4.13 Negative & Edge Cases | 16 |  |  |  |  |
| 4.14 Cross-Module Integration | 8 |  |  |  |  |
| **TOTAL** | **211** |  |  |  |  |

**Tester:** ______________________  **Date:** ______________________

**Release Recommendation:** ☐ GO   ☐ NO-GO   ☐ GO-with-fixes

**Rationale (one sentence):** ______________________________________________________________________

---

### Appendix — Key file:line references

- Pagination size: [apps/sales/views.py:58](apps/sales/views.py#L58)
- SO workflow gates: [apps/sales/models.py:483-496](apps/sales/models.py#L483)
- Shipment workflow gates: [apps/sales/models.py:907-923](apps/sales/models.py#L907)
- Invoice edit/delete gates: [apps/sales/views.py:1361-1389](apps/sales/views.py#L1361)
- Document file validator: [apps/sales/models.py:329-340](apps/sales/models.py#L329)
- POD file validator: [apps/sales/forms.py:303-311](apps/sales/forms.py#L303)
- Customer dropdown excludes blacklisted: [apps/sales/forms.py:162-164](apps/sales/forms.py#L162)
- Customer.clean() rejects blacklisted: [apps/sales/forms.py:170-177](apps/sales/forms.py#L170)
- Portal user scoping: [apps/sales/views.py:1454-1460](apps/sales/views.py#L1454)
- CommunicationLog 24h lock: [apps/sales/models.py:322-326](apps/sales/models.py#L322)
- Seed command + customer fixtures: [apps/sales/management/commands/seed_sales.py:56-65](apps/sales/management/commands/seed_sales.py#L56)
- Tenant fixtures + admin usernames: [apps/tenants/management/commands/seed_tenants.py:23-87](apps/tenants/management/commands/seed_tenants.py#L23)
