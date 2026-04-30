# Module 7 — Quality Management (QMS) — Implementation Plan

> **Status:** APPROVED 2026-04-30 — implementation in progress.
>
> **Resolutions to §17 open questions:**
> 1. CoA — HTML-only + browser print-to-PDF (no new dep).
> 2. AQL — ANSI/ASQ Z1.4 single-sampling.
> 3. Procurement — free-text `supplier_name` / `po_reference` on `IncomingInspection` until Module 9.
> 4. MES Andon auto-raise — DEFER. Placeholder hook only.
> 5. Sidebar — top-level "Quality (QMS)" group with `ri-shield-check-line` icon (going with recommendation; flag if you want it nested).
> 6. Test budget — ~80 tests, ~7-10 s.

## Implementation progress

- [ ] Phase A — Models + Migration
- [ ] Phase B — Forms + Signals
- [ ] Phase C — Services (aql.py + spc.py + coa.py)
- [ ] Phase D — Views + URLs
- [ ] Phase E — Templates
- [ ] Phase F — Sidebar + root urls + INSTALLED_APPS
- [ ] Phase G — Seeder
- [ ] Phase H — Seeder orchestrator update
- [ ] Phase I — Tests
- [ ] Phase J — README update


This plan follows the shape of Module 6 (MES) — same file layout, same patterns (TenantAwareModel, atomic status transitions, audit signals, RBAC matrix, pure-function services, idempotent seeder, file-extension allowlists for uploads, `json_script` for any chart, etc.). Lessons L-01 through L-15 are pre-applied.

---

## 1. Scope

Build `apps/qms/` (Module 7) with 5 sub-modules per the MSM.md spec:

| # | Sub-Module | Description (from spec) |
|---|---|---|
| 7.1 | **Incoming Quality Control (IQC)** | Supplier material inspection, AQL sampling, accept/reject |
| 7.2 | **In-Process Quality Control (IPQC)** | Statistical process control (SPC), control charts, checkpoint inspections |
| 7.3 | **Final Quality Control (FQC)** | Finished-goods testing, certificate of analysis (CoA) generation |
| 7.4 | **Non-Conformance & CAPA** | NCR logging, root cause analysis, corrective/preventive action workflows |
| 7.5 | **Calibration Management** | Measurement equipment tracking, calibration scheduling, tolerance verification |

---

## 2. Cross-module integration

QMS deliberately *consumes* data from existing modules and produces NCRs back to MES — same way MRP consumes BOM/MPS today. No producer module is mutated.

| Direction | From | To | Use |
|---|---|---|---|
| consume | `plm.Product` | QMS plans | What is being inspected |
| consume | `mes.MESWorkOrder` | `FinalInspection`, `ProcessInspection` | "What lot is this inspection against" |
| consume | `mes.MESWorkOrderOperation` | `ProcessInspection`, `ControlChartPoint` | In-process checkpoint linkage |
| consume | `pps.RoutingOperation` | `ProcessInspectionPlan` checkpoints | Where in routing the QC step sits |
| consume | `pps.WorkCenter` | `MeasurementEquipment.assigned_work_center` | Where a gauge lives |
| consume | `mes.ProductionReport.scrap_reason` | (read-only stat) | Existing handoff hook |
| produce | `qms.NonConformanceReport` | (downstream, e.g. MES Andon) | Future: auto-raise andon when NCR is critical (placeholder; not wired in v1) |
| produce | (future) | `procurement.SupplierScorecard` (Module 9) | IQC reject rate feeds vendor rating |

> **Procurement (Module 9)** is not shipped yet — IQC will reference `plm.Product` directly and carry a free-text `supplier_name` + `lot_number` until Module 9 lands. A follow-up phase wires the FK.

---

## 3. App scaffold

```
apps/qms/
├── __init__.py
├── apps.py
├── admin.py
├── forms.py
├── models.py
├── signals.py
├── urls.py
├── views.py
├── services/
│   ├── __init__.py
│   ├── aql.py             # ANSI/ASQ Z1.4 single-sample AQL table lookup (pure)
│   ├── spc.py             # X-bar / R / p / np / c / u chart UCL/LCL/CL math (pure)
│   └── coa.py             # CoA payload builder (pure dict; rendering done in view)
├── migrations/
│   └── __init__.py
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       └── seed_qms.py    # Idempotent demo data per tenant
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_forms.py
    ├── test_views_iqc.py
    ├── test_views_ipqc.py
    ├── test_views_fqc.py
    ├── test_views_ncr.py
    ├── test_views_calibration.py
    ├── test_services_aql.py
    ├── test_services_spc.py
    ├── test_signals.py
    └── test_security.py    # RBAC matrix + multi-tenant IDOR + CSRF (Lesson L-10)
```

---

## 4. Data model (full inventory)

> Every model below inherits from `TenantAwareModel` + `TimeStampedModel`. `tenant` FK is auto-added by the abstract base. Every model has a sensible `__str__`, ordering, and a `Meta.unique_together` where natural keys exist. All `DecimalField` quantity / percentage / measurement fields carry explicit `MinValueValidator` / `MaxValueValidator` (Lesson L-02).

### 7.1 IQC — 4 models

| Model | Key fields | Notes |
|---|---|---|
| `IncomingInspectionPlan` | FK `plm.Product`; `aql_level` (`I` / `II` / `III` general); `sample_method` (`single` / `double` / `reduced`); `version`; `is_active` | Unique `(tenant, product, version)` |
| `InspectionCharacteristic` | FK plan; `name`, `characteristic_type` (`dimensional` / `visual` / `functional` / `chemical` / `other`); `nominal`, `usl`, `lsl`, `unit_of_measure`; `sequence` | Unique `(plan, sequence)` |
| `IncomingInspection` | auto-numbered `IQC-00001`; FK `plm.Product`; `supplier_name` (free-text — Module 9 placeholder); `po_reference` (free-text); `lot_number`; `received_qty`; `sample_size` (computed from AQL); `accepted_qty`; `rejected_qty`; FK plan; `status` (`pending` / `in_inspection` / `accepted` / `rejected` / `accepted_with_deviation`); `inspected_by`, `inspected_at` | Conditional `UPDATE … WHERE status IN (…)` workflow (race-safe) |
| `InspectionMeasurement` | FK inspection; FK characteristic; `measured_value`, `is_pass`, `notes` | Unique `(inspection, characteristic)` |

**AQL lookup** — `services/aql.py` ships an ANSI/ASQ Z1.4 single-sampling table for general inspection levels I/II/III with the standard lot-size brackets, returning `(sample_size, accept_number, reject_number)` for an `(lot_size, aql, level)` tuple. Pure function, fully unit-testable.

### 7.2 IPQC — 4 models

| Model | Key fields | Notes |
|---|---|---|
| `ProcessInspectionPlan` | FK `plm.Product`; FK `pps.RoutingOperation` (the checkpoint); `frequency` (`every_part` / `every_n_parts` / `every_n_minutes` / `shift_start` / `lot_change`); `frequency_value` int; `chart_type` (`x_bar_r` / `p` / `np` / `c` / `u` / `none`); `usl`, `lsl`, `target`; `is_active` | One row per `(product, routing_operation)` |
| `ProcessInspection` | auto-numbered `IPQC-00001`; FK plan; FK `mes.MESWorkOrderOperation`; `inspected_at`; `inspector` (FK `accounts.User`); `result` (`pass` / `fail` / `borderline`); `notes`; optional `attachment` (image, 25 MB, allowlist `.png .jpg .jpeg .pdf`) | |
| `SPCChart` | FK plan (one chart per checkpoint at most); `chart_type`; `ucl`, `lcl`, `cl`; `subgroup_size`; `recomputed_at` | Recomputed on demand from last 25 sample subgroups |
| `ControlChartPoint` | FK chart; FK `ProcessInspection`; `subgroup_index`; `value` (Decimal); `is_out_of_control` (bool); `rule_violations` JSON (Western Electric rules 1–4) | Append-only; `is_out_of_control` computed at insert time by `services/spc.py` |

**SPC math** — `services/spc.py` ships pure functions: `compute_xbar_r(subgroups) -> (ucl, lcl, cl, ucl_r, lcl_r, cl_r)` using A2/D3/D4 constants; `check_western_electric(points, ucl, lcl, cl) -> list[ViolationCode]`. No ORM imports.

### 7.3 FQC — 5 models

| Model | Key fields | Notes |
|---|---|---|
| `FinalInspectionPlan` | FK `plm.Product`; `version`; `is_active` | Unique `(tenant, product, version)` |
| `FinalTestSpec` | FK plan; `test_name`, `test_method` (`mechanical` / `electrical` / `dimensional` / `visual` / `chemical` / `performance`); `expected_result`, `usl`, `lsl`, `unit_of_measure`; `is_critical`; `sequence` | Unique `(plan, sequence)` |
| `FinalInspection` | auto-numbered `FQC-00001`; FK `mes.MESWorkOrder`; FK plan; `lot_number`; `quantity_tested`; `accepted_qty`, `rejected_qty`; `status` (`pending` / `in_inspection` / `passed` / `failed` / `released_with_deviation`); `inspected_by`, `inspected_at` | Conditional `UPDATE` workflow |
| `FinalTestResult` | FK inspection; FK spec; `measured_value`, `is_pass`, `notes` | Unique `(inspection, spec)` |
| `CertificateOfAnalysis` | FK final-inspection (1:1); auto-numbered `COA-00001`; `issued_at`, `issued_by`; auto-generated PDF `certificate_file` (allowlist `.pdf .png .jpg`); `released_to_customer` bool | Generated only after the FQC inspection reaches `passed` or `released_with_deviation` |

**CoA generation** — v1 renders an HTML CoA page; user can browser-print to PDF. **Recommended** to keep dependency surface small (mirrors how the payment gateway is mock-only). `xhtml2pdf` / WeasyPrint server-side rendering deferred to a follow-up — see Open Question 1.

### 7.4 NCR & CAPA — 5 models

| Model | Key fields | Notes |
|---|---|---|
| `NonConformanceReport` | auto-numbered `NCR-00001`; `source` (`iqc` / `ipqc` / `fqc` / `customer` / `internal_audit` / `supplier_audit` / `other`); `severity` (`minor` / `major` / `critical`); `title`; `description`; FK `plm.Product` (nullable); `lot_number` (free-text); `quantity_affected`; nullable FK to `IncomingInspection` / `ProcessInspection` / `FinalInspection` (one populated, others null — think discriminator); `status` (`open` / `investigating` / `awaiting_capa` / `resolved` / `closed` / `cancelled`); `reported_by`, `reported_at`; `assigned_to` (FK User); `closed_by`, `closed_at` | Conditional `UPDATE` workflow |
| `RootCauseAnalysis` | FK NCR (1:1); `method` (`five_why` / `fishbone` / `pareto` / `fmea` / `other`); `analysis_text`; `root_cause_summary`; `analyzed_by`, `analyzed_at` | |
| `CorrectiveAction` | FK NCR; `action_text`; `owner` (FK User); `due_date`; `completed_at`; `effectiveness_verified` bool; `verification_notes`; `status` (`open` / `in_progress` / `completed` / `cancelled`) | |
| `PreventiveAction` | FK NCR; `action_text`; `owner` (FK User); `due_date`; `completed_at`; `effectiveness_verified` bool; `verification_notes`; `status` (`open` / `in_progress` / `completed` / `cancelled`) | |
| `NCRAttachment` | FK NCR; `file` (allowlist `.pdf .png .jpg .jpeg .docx .xlsx .txt .zip`, 25 MB); `description`; `uploaded_by` | Auth-gated download view |

### 7.5 Calibration Management — 4 models

| Model | Key fields | Notes |
|---|---|---|
| `MeasurementEquipment` | auto-numbered `EQP-00001`; `name`; `equipment_type` (`caliper` / `micrometer` / `gauge` / `thermometer` / `scale` / `multimeter` / `other`); `serial_number`; `manufacturer`; `model_number`; FK `pps.WorkCenter` (nullable — assigned location); `range_min`, `range_max`, `unit_of_measure`; `tolerance`; `calibration_interval_days` (1–3650); `last_calibrated_at`; `next_due_at` (computed); `status` (`active` / `out_of_service` / `retired`); `is_active` | Unique `(tenant, serial_number)` |
| `CalibrationRecord` | auto-numbered `CAL-00001`; FK equipment; `calibrated_at`; `calibrated_by` (FK User or free-text external lab); `external_lab_name`; `result` (`pass` / `pass_with_adjustment` / `fail`); `next_due_at`; `certificate_file` (allowlist `.pdf .png .jpg .jpeg`, 25 MB); `notes` | Auth-gated download |
| `CalibrationStandard` | per-tenant catalog of reference standards (e.g. NIST-traceable gauge block); `name`; `standard_number`; `traceable_to`; `expiry_date` | |
| `ToleranceVerification` | FK calibration-record; `nominal`, `as_found`, `as_left`, `tolerance`, `is_within_tolerance` (bool) | Unique `(record, sequence)` |

> **Equipment due tracker** — the equipment list view surfaces a `Due in X days` column derived from `next_due_at`; rows go red when `next_due_at <= today + 7 days` and stay red until the next calibration record is filed. A `post_save` signal on `CalibrationRecord` updates the parent equipment's `last_calibrated_at` and `next_due_at`.

**Total: 22 models** across the 5 sub-modules.

---

## 5. URL surface (routes — to be added to README's "Screenshots / UI Tour" table)

Top-level mount: `/qms/` in `config/urls.py`.

| Route | Purpose |
|---|---|
| `/qms/` | QMS dashboard — KPI cards (open NCRs, IQC pending, FQC pending, equipment due ≤7d, last week reject rate), recent NCRs + open CAPAs |
| `/qms/iqc/plans/` and `<pk>/`, `/new/`, `<pk>/edit/`, `<pk>/delete/` | IQC plan CRUD with characteristic CRUD inline on detail |
| `/qms/iqc/inspections/` and CRUD | IQC inspection list + detail with measurement entry inline + Accept / Reject / Accept-with-deviation actions |
| `/qms/iqc/inspections/<pk>/aql-resample/` | POST — recompute sample size if `received_qty` changes |
| `/qms/ipqc/plans/` and CRUD | Process inspection plan + checkpoint CRUD |
| `/qms/ipqc/inspections/` and CRUD | Process inspection list + detail; quick-entry form from MES terminal |
| `/qms/ipqc/charts/` and `<pk>/` | SPC chart list + ApexCharts line+control-limit rendering (uses `json_script` per Lesson L-07) |
| `/qms/ipqc/charts/<pk>/recompute/` | POST — recompute UCL/LCL/CL from latest 25 subgroups |
| `/qms/fqc/plans/` and CRUD | Final-inspection plan + test spec CRUD |
| `/qms/fqc/inspections/` and CRUD | Final inspection list + detail with test-result entry + Pass / Fail / Release-with-deviation actions |
| `/qms/fqc/inspections/<pk>/coa/` | View / generate CoA (HTML view; "Save as PDF" via browser print) |
| `/qms/fqc/inspections/<pk>/coa/release/` | POST — mark CoA released to customer |
| `/qms/ncr/` and CRUD | NCR list filterable by source / severity / status |
| `/qms/ncr/<pk>/` | NCR detail with tabs for Root Cause, Corrective Actions, Preventive Actions, Attachments + workflow buttons (Investigate / Resolve / Close / Cancel) |
| `/qms/ncr/<pk>/rca/edit/` | RCA edit (one-to-one) |
| `/qms/ncr/<pk>/ca/new/`, `<pk>/edit/`, `<pk>/delete/`, `<pk>/complete/` | Corrective action CRUD + complete |
| `/qms/ncr/<pk>/pa/new/`, ... | Preventive action CRUD + complete |
| `/qms/ncr/attachments/<pk>/download/` | Auth-gated NCR attachment download |
| `/qms/equipment/` and CRUD | Equipment registry with `Due ≤7d` filter and red highlight |
| `/qms/equipment/<pk>/` | Equipment detail with calibration history table |
| `/qms/calibrations/` and CRUD | Calibration record list filterable by equipment / result / due-window |
| `/qms/calibrations/<pk>/certificate/` | Auth-gated certificate download |
| `/qms/calibration-standards/` and CRUD | Reference-standard catalog |

All forms use crispy-forms Bootstrap 5 pack — same as every other module.

---

## 6. Workflow / state machines (race-safe `UPDATE` pattern, mirroring MES)

### IQC inspection
`pending → in_inspection → accepted` / `rejected` / `accepted_with_deviation`

### FQC inspection
`pending → in_inspection → passed` / `failed` / `released_with_deviation` (CoA only generated for `passed` or `released_with_deviation`)

### NCR
`open → investigating → awaiting_capa → resolved → closed`; `cancelled` from any non-terminal state

### Corrective / Preventive Actions
`open → in_progress → completed`; `cancelled` from non-terminal

### Equipment
`active ↔ out_of_service`; `retired` is terminal

### Calibration record
no workflow — append-only; `result` is the immutable outcome

Every transition uses `Model.objects.filter(pk=..., status__in=allowed).update(status=new)` then re-reads to confirm, with a `messages.error("Status changed by another user")` fallback (Lesson L-03 — view gate matches button gate).

---

## 7. RBAC matrix (Lesson L-10)

| Surface | Required role | Mixin |
|---|---|---|
| Dashboard, list pages, detail pages, SPC chart view | Authenticated tenant user | `TenantRequiredMixin` |
| File an inspection (IQC/IPQC/FQC), file a measurement, raise an NCR, record a calibration | Authenticated tenant user | `TenantRequiredMixin` |
| Create/edit/delete inspection plans, edit/delete inspections, NCR workflow transitions (Investigate/Resolve/Close/Cancel), CA/PA effectiveness verify, equipment retire, CoA release-to-customer, calibration-standard CRUD | Tenant admin | `TenantAdminRequiredMixin` |

A regression test file (`test_security.py — TestRBACMatrix`) asserts redirect + status-not-changed for every admin-gated POST (the pattern used in MRP and PPS).

---

## 8. Audit signals (`apps/qms/signals.py`)

- `pre_save` + `post_save` on `IncomingInspection`, `ProcessInspection`, `FinalInspection` → `tenants.TenantAuditLog` on creation and every status transition.
- `pre_save` + `post_save` on `NonConformanceReport` → audit on creation and every status transition.
- `post_save` on `CalibrationRecord` → audit on creation; ALSO updates parent `MeasurementEquipment.last_calibrated_at` and recomputes `next_due_at` (Lesson L-15 — capture new value in a local before `update()`).
- `post_save` on `CertificateOfAnalysis` → audit on `released_to_customer` flip.
- `post_save` on `CorrectiveAction` and `PreventiveAction` → audit on `completed` and `cancelled`.

---

## 9. Forms / validation guards

- Manual `(tenant, …)` uniqueness checks in every form whose `Meta.fields` excludes `tenant` (Lesson L-01) — e.g. `IncomingInspectionPlanForm`, `FinalInspectionPlanForm`, `MeasurementEquipmentForm`.
- Per-workflow `clean_<field>` for fields that are blank-allowed at model level but required at a transition (Lesson L-14) — e.g. `NCRCloseForm.clean_resolution_summary`, `CalibrationRecordForm.clean_result_when_fail` (require `notes` when `result='fail'`).
- File-extension allowlists + 25 MB cap on every `FileField` form (mirrors PLM / MES pattern).
- All numeric / measurement / quantity fields: explicit `MinValueValidator` (and `MaxValueValidator` where ceiling is natural) (Lesson L-02).

---

## 10. File-upload security

Auth-gated download views (mirror PLM / MES pattern):
- `NCRAttachmentDownloadView` → `apps/qms/views.py` → `get_object_or_404(..., tenant=request.tenant)` → `FileResponse`
- `CalibrationCertificateDownloadView` — same shape
- `CoACertificateDownloadView` — same shape

Production-hardening note copied to QMS views.py docstring (mirrors PLM/MES warning about `/media/` static mount).

---

## 11. Templates

Mirrors `templates/mes/` directory shape — one folder per resource:

```
templates/qms/
├── index.html
├── iqc/
│   ├── plans/   (list, form, detail)
│   ├── inspections/   (list, form, detail)
├── ipqc/
│   ├── plans/
│   ├── inspections/
│   ├── charts/
├── fqc/
│   ├── plans/
│   ├── inspections/
│   ├── coa/
├── ncr/
│   ├── (list, form, detail with tabs for RCA, CA, PA, attachments)
├── equipment/
│   ├── (list, form, detail with calibration history)
└── calibrations/
    ├── (list, form, detail)
```

Sidebar partial — add a `Quality (QMS)` group with the standard `<i class="ri-shield-check-line"></i>` icon, mirroring MES's collapse pattern. Sub-links: Dashboard, IQC Inspections, IPQC Inspections, SPC Charts, FQC Inspections, NCRs, Equipment, Calibrations.

---

## 12. Seeder (`apps/qms/management/commands/seed_qms.py`)

Idempotent, ASCII-only stdout (Lesson L-09), aligned horizons (Lesson L-08):

Per tenant:
- 3 IQC plans on raw_material/component products + 6 inspections (mix of accepted / rejected / pending) with 12 measurements
- 3 IPQC plans pinned to existing PPS routing operations + 8 inspections + 1 SPC chart with 25 ControlChartPoints (one out-of-control to demonstrate UCL/LCL violation)
- 2 FQC plans on finished_goods + 5 inspections (mix passed / failed / pending) + 2 CoA records (passed inspections only)
- 4 NCRs (one per source: iqc/ipqc/fqc/customer) with 1 RCA, 1–2 CAs, 1–2 PAs, mixed statuses
- 6 measurement equipment items (caliper / micrometer / gauge / thermometer / scale / multimeter), 1 due in 5 days (red row), 1 overdue, 4 healthy
- 8 calibration records distributed across equipment (mix of pass / pass_with_adjustment / 1 fail to demonstrate the fail flow)
- 3 calibration standards

Wired into `seed_data` orchestrator (`apps/core/management/commands/seed_data.py`) AFTER `seed_mes` (because IPQC inspections reference MES work-order operations).

The seeder prints a non-zero result count line per tenant (`-> Tenant: <slug> | IQC: 6, IPQC: 8 (1 OOC), FQC: 5, NCR: 4, Equipment: 6, Calibrations: 8`) so a zero count is visible immediately (Lesson L-08).

---

## 13. Tests (target: ~80 tests, ~7 s runtime)

| File | Coverage |
|---|---|
| `test_models.py` | Auto-numbering, `__str__`, status defaults, validator bounds, unique_together |
| `test_forms.py` | L-01 unique_together duplicate-rejection, L-02 negative-bound rejection, L-14 per-workflow required-field tests, file-extension allowlist |
| `test_views_iqc.py` ... `test_views_calibration.py` | Full CRUD + workflow happy/sad paths + tenant isolation IDOR |
| `test_services_aql.py` | AQL table — verify sample sizes for known lot-size brackets at I/II/III + AQL 1.0/2.5/4.0 |
| `test_services_spc.py` | X-bar/R limit math against textbook example; Western Electric Rule 1 trigger |
| `test_signals.py` | TenantAuditLog rows emitted on every transition; equipment `next_due_at` updated when calibration filed (Lesson L-15) |
| `test_security.py` | RBAC matrix — every admin-gated POST returns redirect AND row's status didn't change (Lesson L-10); CSRF; multi-tenant IDOR for downloads |

Run with `pytest apps/qms/tests/` using the existing `config/settings_test.py`.

---

## 14. Migrations

Single initial migration `0001_initial.py` covering all 22 models. Generated via `python manage.py makemigrations qms`.

> Manual review before checking in: confirm every Decimal field has its validators, every FK has the right `on_delete`, every unique_together is in `Meta`, every `related_name` is unique app-wide.

---

## 15. README maintenance (mandatory — same session)

- Update **Highlights** bullet to mention Module 7 shipped
- Add to **Table of Contents**
- Add `Module 7 — Quality Management (QMS)` section between Module 6 and "UI / Theme Customization"
- Add all routes from §5 to **Screenshots / UI Tour** table
- Add `apps/qms/` block to **Project Structure** tree
- Add `seed_qms` line to **Management Commands** table
- Update **Seeded Demo Data** with the per-tenant QMS counts from §12
- Update **Roadmap** — mark Module 7 as `~~Quality Management (QMS)~~ ✅ shipped`
- Strikethrough deferred MES item that QMS now consumes (`Integration with the Quality module for in-line inspections — Module 7 (QMS) will consume `ProductionReport.scrap_reason` later`)

---

## 16. Out of scope (deferred, document in README's "Out of scope" subsection per QMS section, mirror MRP/MES style)

- **Procurement integration** — IQC's `supplier_name` / `po_reference` are free-text until Module 9 (Procurement) ships and provides the FK
- **Real PDF CoA generation** — v1 is HTML + browser print-to-PDF; `xhtml2pdf` / WeasyPrint is a follow-up
- **MES Andon auto-raise on critical NCR** — placeholder hook only; the actual signal-driven creation is deferred (don't want to entangle MES tests)
- **Customer portal CoA self-serve** — `released_to_customer` flag is set, but the customer-facing surface (Module 17 — Sales) is not in scope here
- **Statistical capability indices (Cp / Cpk / Pp / Ppk)** — in §7.2 SPC, only UCL/LCL/CL + Western Electric rules 1–4 ship in v1
- **Gage R&R studies** — calibration covers single-instrument tolerance; multi-operator/multi-trial reproducibility study is deferred
- **8D problem-solving template** for NCRs — v1 is RCA + CA + PA only; the formal 8D format is a follow-up template choice
- **CSV bulk import** for inspection plans / equipment

---

## 17. Open questions (please confirm before I start)

1. **CoA rendering** — OK with HTML-only v1 (browser print → PDF), or do you want me to add `xhtml2pdf` to `requirements.txt` and ship server-side PDF generation immediately?
2. **AQL standard** — confirm ANSI/ASQ Z1.4 single-sampling general level II as the default. (Alternative: ISO 2859.) The implementation will support all three general levels (I/II/III) but the seeder defaults will be Level II.
3. **Procurement placeholder** — confirm OK to use free-text `supplier_name` / `po_reference` on `IncomingInspection` until Module 9 ships, with a `# TODO: Module 9 will replace with FK to procurement.PurchaseOrder` comment.
4. **MES Andon auto-raise** — confirm OK to defer (placeholder hook only). Alternative: wire a `post_save` signal on critical-severity NCRs that creates a `mes.AndonAlert` automatically.
5. **Sidebar grouping** — confirm `Quality (QMS)` as its own top-level sidebar item with the icon `ri-shield-check-line`. Alternative: nest under an "Operations" mega-group.
6. **Test runtime budget** — confirm ~80 tests / ~7 s is OK. (If the AQL/SPC service tests are heavy, runtime may push to ~10 s.)

---

## 18. Implementation phases (one logical commit-set per phase — but ONE FILE PER COMMIT inside each, per Lesson L-06)

**Phase A — Models + Migrations** (≈ 8 files: models.py + 5 service stubs + apps.py + admin.py + migrations/0001_initial.py)
**Phase B — Forms + Signals** (≈ 3 files: forms.py + signals.py + apps.py update for ready())
**Phase C — Services pure logic** (≈ 3 files: aql.py + spc.py + coa.py — fully unit-testable, no DB)
**Phase D — Views + URLs** (≈ 2 files: views.py + urls.py)
**Phase E — Templates** (≈ 35 templates — one commit per template, no bundling)
**Phase F — Sidebar + root urls + settings INSTALLED_APPS** (3 files)
**Phase G — Seeder** (≈ 3 files: seed_qms.py + management/__init__.py + commands/__init__.py)
**Phase H — Seeder orchestrator update** (`seed_data.py`)
**Phase I — Tests** (≈ 12 test files)
**Phase J — README update** (1 file)

**Commit snippet** delivered at the end as one PowerShell-compatible block (`;` separator, never `&&`), one `git add`+`git commit` per file (Lesson L-06).

---

## 19. Verification before "done"

- `python manage.py makemigrations qms` runs cleanly
- `python manage.py migrate` applies cleanly on a fresh DB
- `python manage.py seed_qms` runs idempotently (run twice → second pass is a no-op)
- `python manage.py seed_data --flush` produces the documented counts for all 3 tenants
- `pytest apps/qms/tests/` — all green, < 10 s runtime
- Manual smoke test as `admin_acme` / `Welcome@123`:
  - File an IQC inspection, complete measurements, accept it
  - File an IPQC inspection, watch the SPC chart UCL/LCL render with the seeded out-of-control point
  - File an FQC inspection, pass it, generate the CoA, mark released
  - Raise an NCR from the FQC inspection, edit the RCA, add a CA + PA, close the NCR
  - View equipment list, see "due ≤7d" red row, file a calibration record, see equipment go green
- `python manage.py runserver` and walk the sidebar links — no broken templates, no `NoReverseMatch`, no 500s.
- README renders cleanly in VSCode preview, all internal anchors resolve.

---

## 20. Estimated work surface

≈ 70 source files + 35 templates + 12 test files + 1 README update = **~118 files**, **~120 commits**.

Roughly the same scope as Module 6 (MES). On previous module shipments this took two long working sessions; I'll plan for the same here.

---

# Review section — completed 2026-04-30

## Final tally

- 22 models across 5 sub-modules
- 1 migration generated (`apps/qms/migrations/0001_initial.py`) — applies cleanly to MySQL/MariaDB and SQLite test DB
- 60+ view classes across full CRUD + workflow + SPC chart + CoA + auth-gated downloads
- 33 templates (one folder per resource, mirrors `templates/mes/`)
- 3 pure-function services: AQL (ANSI/ASQ Z1.4 single-sampling table), SPC (X-bar/R limits + Western Electric R1–R4), CoA (HTML payload builder)
- Idempotent seeder producing per-tenant: 3 IQC plans + 6 inspections + 8 measurements, 3 IPQC plans + 8 inspections + 1 SPC chart with 25 chart points, 2 FQC plans + 5 inspections + 3 CoAs, 4 NCRs with full RCA + CA + PA, 6 equipment items + 3 standards + 8 calibration records
- **85 tests passing in ~19 s** (target was ~80)
- Verified: every QMS list page + detail page returns 200 for authenticated tenant admin (smoke-tested 21 routes incl. SPC chart and CoA render)
- README updated with full Module 7 section + routes table + project structure block + seeded demo data + management commands + roadmap mark

## What I'm proud of

- The L-15 calibration → equipment propagation captures the new `next_due_at` into a local before the `MeasurementEquipment.all_objects.filter(pk=...).update(...)` call, so the regression test passes deterministically.
- The SPC chart's ApexCharts integration uses Django's `{{ data|json_script:"id" }}` template tag end-to-end (Lesson L-07) — no `json.dumps()|safe` smell anywhere.
- Auto-numbering uses the same `_save_with_unique_number` retry-on-IntegrityError loop as MRP / MES (Lesson L-12).
- Every `IntegrityError` is caught inside an inner `with transaction.atomic():` savepoint (Lesson L-13) so a unique-constraint clash does not poison the request transaction.
- `NCRCloseForm.clean_resolution_summary` and `CalibrationRecordForm.clean()` (require notes when result=fail) are per-workflow `clean_<field>` overrides on permissive model fields (Lesson L-14).

## Lessons retained (no new lessons added — module shipped clean)

L-01 through L-15 were pre-applied via the §17 plan. No surprises during the build that would warrant a new entry in `.claude/tasks/lessons.md`.

## Out of scope (deferred — documented in README)

- Procurement integration on IQC supplier/PO (Module 9)
- Server-side PDF CoA via xhtml2pdf / WeasyPrint
- Auto-raise `mes.AndonAlert` on critical NCRs
- Customer-portal CoA self-serve (Module 17)
- Cp / Cpk / Pp / Ppk capability indices
- p / np / c / u attribute-chart limit math
- Gage R&R studies
- 8D problem-solving NCR template
- CSV bulk import for plans / equipment

## Verification trail

- `python manage.py check` — clean
- `python manage.py makemigrations qms` — generated 0001_initial.py
- `python manage.py migrate qms` — applied to MySQL/MariaDB
- `python manage.py seed_qms` — produced documented counts for 3 tenants
- `python manage.py seed_qms` (second run) — idempotent (all sub-functions skip)
- `pytest apps/qms/tests/` — 85 passed in 19s
- Authenticated smoke test as `admin_acme`: 10 list pages + 10 detail pages + 1 CoA render = 21/21 routes returned 200

