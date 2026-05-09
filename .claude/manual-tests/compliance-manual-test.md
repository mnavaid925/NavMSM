# Compliance & Regulatory (Module 13) — Manual Test Plan

> **Author:** Senior Manual QA — Claude · **Target build:** Module 13 v1 + Phase C (2026-05-10) · **App under test:** [`apps/compliance/`](apps/compliance/) + the PLM compliance subset at [`apps/plm/`](apps/plm/) (signature + audit chain).
>
> A click-through script for a tester. Every step says exactly what to click, what to type, and what to expect on screen. Tester fills **Pass/Fail** + **Notes** columns as they go.
>
> Pre-existing automated coverage at sign-off:
>   - 218 PLM + Compliance tests (compliance: 137, PLM: 134)
>   - 13 SHA-256 hash chain tests (TenantAuditLog + ComplianceAuditLog)
>   - 7 EHS KPI tests · 6 RecallNotice email tests · 6 perf tests · 4 NCR-hook tests · 5 recall-leak tests · 10 e-sig binding tests
>
> **Pre-flight prerequisites:**
>   - `python manage.py migrate`
>   - `python manage.py seed_data` (or at minimum `seed_tenants` + `seed_plm` + `seed_compliance`)
>   - `python manage.py runserver` on `127.0.0.1:8000`
>   - Open in two browser windows: one logged in as `admin_acme / Welcome@123`, one private/incognito logged in as `admin_globex / Welcome@123`. The two windows let you verify cross-tenant isolation visually.

---

## 1. Scope & Objectives

| Item | Value |
|---|---|
| Mode | **Full module test** — every list / create / detail / edit / delete + every workflow transition + every cross-module hook + every Phase C addition |
| Persona | Tenant administrator (`is_tenant_admin=True, role='tenant_admin'`) for write paths; non-admin operator for RBAC checks |
| Tenant | `acme` (with `globex` for cross-tenant 404 verification) |
| Excluded | Anonymous browsing (covered by `TenantRequiredMixin` smoke test), localization, theme switching |
| Sign-off criterion | All sections green, zero High/Critical bugs open |

---

## 2. Smoke — every list page renders 200

| # | URL | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| S-01 | `/compliance/` | Dashboard with KPI cards, EHS panel (TRIR, LTIR, near-miss ratio), recent incidents + recalls tables | | |
| S-02 | `/compliance/incidents/` | Incident list with status / severity filters + Actions column | | |
| S-03 | `/compliance/incident-types/` | IncidentType list (admin-only manage) | | |
| S-04 | `/compliance/risks/` | Risk assessment list with risk-band badges | | |
| S-05 | `/compliance/checklists/` | Safety audit checklist list | | |
| S-06 | `/compliance/audits/` | Safety audit list | | |
| S-07 | `/compliance/documents/` | Regulatory document list | | |
| S-08 | `/compliance/audit-trail/` | Aggregated TenantAuditLog viewer (cross-cutting + ComplianceAuditLog) | | |
| S-09 | `/compliance/audit-trail/archives/` | AuditLogArchive list with hash chain | | |
| S-10 | `/compliance/waste-categories/` | WasteCategory list | | |
| S-11 | `/compliance/waste-manifests/` | WasteManifest list with status filter | | |
| S-12 | `/compliance/recalls/` | ProductRecall list with severity filter | | |

---

## 3. EHS — Incident lifecycle (Sub-module 13.1)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| INC-01 | Click **New Incident** on `/compliance/incidents/` | Form renders with type / title / occurred_at / severity / description fields | | |
| INC-02 | Submit form: type=Injury, title=`Slip on aisle B`, severity=`medium`, occurred_at=today, description=`Wet floor near machine 3` | 302 → detail page; banner `Incident INC-NNNNN created`; status=`reported` badge | | |
| INC-03 | Detail page → click **Investigate** | Status flips to `investigating`; one ComplianceAuditLog row added; TenantAuditLog gets `compliance.incident.investigating` row | | |
| INC-04 | Click **Move to Corrective Action** | Status = `corrective_action`; new audit row | | |
| INC-05 | Click **Close** | Status = `closed`; `closed_at` stamped; new audit row | | |
| INC-06 | Try to click **Edit** on the now-closed incident | Buttons hidden in template (`is_editable()` returns False); manual POST to `/edit/` returns 200 with form-level error | | |
| INC-07 | Refresh `/compliance/` dashboard | Dashboard "Open Incidents" KPI decreases by 1; "EHS Recordable count" includes this incident | | |

### 3.1 EHS dashboard KPIs (C.4)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| KPI-01 | Visit `/compliance/` | Panel labelled `EHS Leading & Lagging Indicators (last 90 days)` shows 4 cards: TRIR, LTIR, Near-Miss Ratio, Hours Worked | | |
| KPI-02 | Hover the **TRIR** ⓘ tooltip | Reads `OSHA Total Recordable Incident Rate = (recordable incidents x 200,000) / hours worked. Industry benchmark: < 3.0 (manufacturing avg ~3.3).` | | |
| KPI-03 | If `apps.labor` has no AttendanceRecord rows for the period | A "est. hours" badge appears next to the period label, indicating fallback | | |

---

## 4. EHS — Risk Assessments

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| RA-01 | New risk: title=`Forklift charging area`, hazard=`Battery acid exposure`, likelihood=4, severity=4 | Saves; `risk_score` shows `16`; band badge `critical` (red) | | |
| RA-02 | Edit, set residual_likelihood=2, residual_severity=2 | residual_score shows `4`; band badge changes per residual | | |
| RA-03 | Submit for review (workflow button) | Status `in_review`; audit row added | | |
| RA-04 | Approve | Status `approved`; audit row | | |
| RA-05 | Try to edit an `approved` risk | Edit button hidden; manual POST returns warning toast | | |

---

## 5. EHS — Safety Audits

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| SA-01 | Create checklist: code=`5S-A`, name=`5S walk`, items=`[{"order":1,"question":"Sort done?"},{"order":2,"question":"Set in order?"}]` | Saves; checklist appears in list | | |
| SA-02 | Schedule audit using checklist 5S-A, scheduled_for=tomorrow, auditor=admin_acme | Audit detail page shows status `scheduled` | | |
| SA-03 | Click **Start** | Status `in_progress`; rows for each checklist item rendered | | |
| SA-04 | Record items: pass / pass / fail | Each click writes a SafetyAuditItem with `result`; audit summary updates | | |
| SA-05 | Click **Complete** | Status `completed`; pass-rate computed | | |

---

## 6. Regulatory Documents + e-Signatures (Sub-module 13.2)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| DOC-01 | Create document: type=`sop`, title=`SOP-100 Receiving`, version=`1.0` | Saves; status=`draft` | | |
| DOC-02 | Upload an attachment (PDF) | File saved; download link visible on detail page | | |
| DOC-03 | Click **Submit for review** | Status `in_review`; audit row | | |
| DOC-04 | Click **Approve** | Status `approved`; audit row | | |
| DOC-05 | Click **Sign** → form: typed_name=`Jane Doe`, role=`QA Director`, reason=`approval` | New ElectronicSignature row appears; audit log gets `compliance.signature.created` | | |
| DOC-06 | Try to edit the signature row in Django admin (`/admin/compliance/electronicsignature/<pk>/change/`) | All fields readonly; no Save / Delete buttons (FDA 21 CFR Part 11 immutability) | | |
| DOC-07 | Click **Publish** on document detail | Status `effective`; `effective_date` stamped | | |
| DOC-08 | Create a successor v2.0 of the same SOP, then click **Supersede** on the v1.0 detail | v1.0 status `superseded`; v2.0 stays `draft` | | |

---

## 7. Audit Trail & Data Integrity (Sub-module 13.3 + C.1 SHA chain)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| AUD-01 | Visit `/compliance/audit-trail/` | Table aggregates TenantAuditLog + ComplianceAuditLog rows newest-first | | |
| AUD-02 | Filter by `target_type=IncidentReport` | Only incident-related rows shown | | |
| AUD-03 | Click **Generate Archive** on `/compliance/audit-trail/archives/` | Form prompts for period_start / period_end | | |
| AUD-04 | Generate archive for last 30 days | New AuditLogArchive `ALA-NNNNN` created; record_count populated; hash_chain set; previous_archive FK linked | | |
| AUD-05 | Open Django shell: `from apps.tenants.services.audit_chain import verify_tenant_audit_chain; from apps.core.models import Tenant; t = Tenant.objects.get(slug='acme'); verify_tenant_audit_chain(t)` | Returns `{'ok': True, 'rows_checked': N, 'broken': []}` | | |
| AUD-06 | Same for ComplianceAuditLog: `from apps.plm.services.audit_chain import verify_compliance_audit_chain; verify_compliance_audit_chain(t)` | Returns `{'ok': True, ...}` | | |
| AUD-07 | Tamper test: in shell, run raw SQL `UPDATE tenants_tenantauditlog SET meta='{"tampered":true}' WHERE id=<some pk>` | Re-run `verify_tenant_audit_chain(t)` → returns `ok=False` with broken row pk listed | | |
| AUD-08 | (Cleanup) Restore the tampered row's meta to `'{}'` and re-verify | Chain reports `ok=False` still — once broken, the chain stays broken; this is the FDA-evidence guarantee. Acceptable for the manual test. | | |

---

## 8. Waste & Emission Tracking (Sub-module 13.4)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| WST-01 | Create category: code=`HZC`, name=`Hazardous Chemical`, hazard_class=`hazardous_chemical` | Saves | | |
| WST-02 | Create manifest: category=HZC, generator=`Acme Plant`, manifest_date=today | Status `draft` | | |
| WST-03 | Add disposal record line: quantity=100 kg, disposal_facility=`EnviroSafe Inc.` | Line appears in manifest detail | | |
| WST-04 | Click **Dispatch** | Status `in_transit`; `dispatched_at` stamped | | |
| WST-05 | Click **Mark Disposed** | Status `disposed` | | |
| WST-06 | Click **Reconcile** | Status `reconciled` | | |
| WST-07 | Try to edit a reconciled manifest | Edit button hidden; manual POST returns warning | | |

---

## 9. Recall & Traceability (Sub-module 13.5 + C.7 leak detection)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| REC-01 | Create recall: product=`SKU-1001`, title=`Voltage spec deviation`, severity=`class_iii` | `RECALL-NNNNN` allocated; status `draft` | | |
| REC-02 | Add affected lot via the linker form: lot=existing seeded lot, affected_quantity=10 | Lot appears in the table; `affected_quantity` denorm rolls up onto parent recall | | |
| REC-03 | Click **Progress to In-Progress** | Status `in_progress`; cancel still available | | |
| REC-04 | **Leak test (C.7):** in another tab go to `/inventory/movements/` and post an `issue` movement on the same lot, qty=2 | Recall detail page (refresh) shows the affected_lot row in **yellow** with badge `⚠ 1` and warning banner naming the leak | | |
| REC-05 | Post 2 more issue movements on that lot | Badge increments to `⚠ 3`; `last_leak_at` updates to most recent timestamp | | |
| REC-06 | Cancel the recall (workflow button) → enter reason `Test cancellation` | Status `cancelled`; new movements no longer flagged | | |
| REC-07 | Create a new recall, repeat REC-02–03; click **Draft Notice** to add a RecallNotice | Notice form opens with channel, audience, recipient_email (C.5), subject, body | | |
| REC-08 | Submit notice with channel=`email`, recipient_email=`partner@example.com`, subject=`URGENT recall`, body=`Stop distribution` | Notice saved as `draft` | | |
| REC-09 | Click **Send** on the notice | Status `sent`; in DEBUG: server console logs the email body via Django console backend; in PROD: real SMTP delivery | | |
| REC-10 | Click **Send** again | Idempotent — no double-send (button hidden because `is_sendable()=False`); manual POST does nothing | | |
| REC-11 | Try notice with channel=`email` and blank recipient_email | Form returns error `A recipient email address is required when channel = Email.` | | |
| REC-12 | Click **Acknowledge** on a sent notice | Status `acknowledged`; `acknowledged_at` stamped | | |

---

## 10. Cross-module hooks

### 10.1 mes.AndonAlert(safety) → IncidentReport

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| HK1-01 | Open `/mes/work-orders/` → pick any released WO → file an Andon alert: type=`safety`, severity=`high`, message=`Spill near press 3` | Alert filed | | |
| HK1-02 | Visit `/compliance/incidents/` | A new IncidentReport appears titled `Safety Andon: …` with `source_andon` populated and severity=`high` | | |
| HK1-03 | Edit the Andon alert (e.g., bump severity) and save | Incident does NOT duplicate; idempotent on `source_andon` partial unique constraint | | |

### 10.2 qms.NCR(severity=critical) → IncidentReport (C.6)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| HK2-01 | Open `/qms/ncr/new/` → create NCR with severity=`critical`, source=`internal`, title=`Lot contamination` | NCR saved | | |
| HK2-02 | Visit `/compliance/incidents/` | A new IncidentReport titled `Critical NCR: NCR-NNNNN` appears with `source_ncr` populated, severity=`critical` | | |
| HK2-03 | Re-save the NCR (e.g., update description) | No duplicate IncidentReport (idempotent) | | |
| HK2-04 | Create a `major`-severity NCR | NO incident created (only critical fires the hook) | | |

### 10.3 inventory.StockMovement → recall leak (C.7)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| HK3-01 | Covered by REC-04 / REC-05 above | | | |

---

## 11. PLM Compliance Subset + e-Signature binding (C.8)

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| ESIG-01 | Visit `/admin/core/tenant/<acme-pk>/change/` as superuser; tick `require_compliance_e_signature` | Save successful | | |
| ESIG-02 | Log back in as admin_acme; visit `/plm/compliance/new/`; submit form transitioning to `compliant` WITHOUT typing the e-sig name | Form re-renders with error `Electronic signature is required when transitioning to "Compliant"` | | |
| ESIG-03 | Re-submit with esig_typed_name=`Jane Doe`, esig_role=`QA Director`, esig_reason=`initial_certification` | Saves; detail page shows new "Electronic Signatures (FDA 21 CFR Part 11)" panel with the row | | |
| ESIG-04 | Edit the same record (no status change), update notes only | NO new signature row created (only fires on actual transition INTO compliant) | | |
| ESIG-05 | Try to edit the existing signature in Django admin (`/admin/plm/productcompliancesignature/<pk>/change/`) | All fields readonly; immutable per FDA 21 CFR Part 11 | | |
| ESIG-06 | Untick `require_compliance_e_signature` on the tenant; create a new compliance record into compliant without filling esig fields | Saves successfully (opt-in behaviour preserved) | | |

---

## 12. RBAC + cross-tenant isolation

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| SEC-01 | In private window logged in as `admin_globex`, try to GET `/compliance/incidents/<acme-incident-pk>/` | 404 | | |
| SEC-02 | Same window, try POST `/compliance/incidents/<acme-incident-pk>/delete/` | 404; row preserved | | |
| SEC-03 | Same window, try POST `/compliance/recalls/<acme-recall-pk>/cancel/` with `reason=test` | 404 | | |
| SEC-04 | As admin_acme, log out; visit `/compliance/incidents/<pk>/` anonymously | 302 → `/accounts/login/?next=/compliance/...` | | |
| SEC-05 | As `staff_acme` (operator role, not admin), try GET `/compliance/incident-types/new/` | 403 or redirect (TenantAdminRequiredMixin) | | |
| SEC-06 | As `staff_acme`, GET `/compliance/incidents/` | List renders 200 (read-only is allowed) | | |

---

## 13. Negative / edge cases

| # | Action | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| NEG-01 | Submit incident form with `occurred_at` 100 years in the future | Form accepts (no future-date guard by design — treat as Future-of-Plan note); saves | | |
| NEG-02 | Submit risk with likelihood=10, severity=10 | Validators bound at 5; form rejects | | |
| NEG-03 | Submit document upload with `.exe` extension | Form rejects with extension allowlist error | | |
| NEG-04 | Submit document upload >25 MB | Form rejects with size error | | |
| NEG-05 | Search with `?q=' OR 1=1 --` | 200; ORM parameterized — no SQL leak; 0 matches | | |
| NEG-06 | Search with `?q=<script>alert(1)</script>` | Results render with HTML escaped; no script tag in DOM | | |
| NEG-07 | Pagination with `?page=99` (beyond range) | Falls back to last page or empty result; no 500 | | |
| NEG-08 | Try to delete a `closed` incident | Delete button hidden; manual POST returns warning toast | | |
| NEG-09 | Submit waste manifest line with quantity=0 | Form rejects (MinValueValidator) | | |
| NEG-10 | Submit recall with severity=`class_xyz` (invalid choice) | Form rejects with choice error | | |

---

## 14. Sign-off

| Role | Name | Date | Decision (GO / NO-GO) | Notes |
|---|---|---|---|---|
| QA tester | | | | |
| Module owner | | | | |
| Compliance officer | | | | |

**GO criteria:** zero High/Critical bugs open; all sections green; the `verify_*_audit_chain()` calls in §7 return `ok=True` on the seeded data.

**Decision:** ___________________________________________
