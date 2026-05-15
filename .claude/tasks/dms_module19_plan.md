# Module 19 — Document & Knowledge Management — Implementation Plan

**App:** `apps/dms/` · **URL prefix:** `/dms/` · **Reference modules:** `apps/rma/` (most recent, similar 5-sub-module shape), `apps/compliance/` (existing document workflow pattern), `apps/labor/` (existing training pattern — for distinction).

**Scope (confirmed via /AskUserQuestion):**
- Build a **separate** `apps/dms/Document` model — do NOT reuse `compliance.ComplianceDocument`. Compliance keeps its regulatory-only artefacts; DMS owns general SOPs / WIs / policies / manuals.
- Build a **new** `DocumentAssignment` + `ReadAcknowledgment` model pair — independent of `labor.TrainingPlan`. Document acknowledgement ≠ formal training enrolment.
- **All 5 sub-modules** in one ship (matches the existing module-completeness pattern from Modules 13–18).
- **Full pytest suite + idempotent seeder** like Module 18 (≈80–100 tests).

---

## 0. Sub-module → model map

| # | Sub-module | Models |
|---|---|---|
| 19.1 | Controlled Document Repository | `DocumentCategory`, `Document` (auto `DOC-00001`), `DocumentVersion` (with check-in/check-out lock), `DocumentAccessRule` |
| 19.2 | SOP & Work Instruction Authoring | `DocumentTemplate` (auto `TPL-00001`), `TemplateField`, `MediaAttachment` |
| 19.3 | Document Approval Workflows | `ApprovalWorkflow`, `ApprovalStage`, `DocumentApprovalRequest` (auto `AR-00001`), `ApprovalAction`, `DocumentSignature` (FDA 21 CFR Part 11 e-sig) |
| 19.4 | Training Document Assignment | `DocumentAssignment` (auto `DA-00001`), `AssignmentTarget`, `ReadAcknowledgment` (auto `ACK-00001`) |
| 19.5 | Archive & Retention Policy | `RetentionPolicy` (auto `RP-00001`), `DocumentArchive` (auto `ARC-00001`), `LegalHold` (auto `LH-00001`) |

**Total: 17 models.** All inherit `TenantAwareModel, TimeStampedModel`. Auto-numbering via `services/numbering.next_code()` assigned in `save()` before `super().save()`. Decimal/integer fields get `MinValueValidator`/`MaxValueValidator` (L-02). Audit/log child FKs use `on_delete=PROTECT` (L-17); structural children use `CASCADE`.

### Key model fields (condensed)

#### 19.1 Controlled Document Repository

- **DocumentCategory** — `name`, `code` (unique per tenant), `parent` self-FK (hierarchical), `description`, `is_active`. `unique_together(tenant,code)`.
- **Document** — `code` (`DOC-00001`), `title`, `doc_type` (sop / work_instruction / policy / form / manual / specification / report / drawing / training_material / other), `category` FK→DocumentCategory SET_NULL null, `owner` FK→User SET_NULL null, `current_version` FK→DocumentVersion SET_NULL null/blank (nullable to bootstrap), `status` (draft / in_review / approved / effective / superseded / archived), `effective_date` date null, `expiry_date` date null, `retention_policy` FK→RetentionPolicy SET_NULL null/blank, `retention_until` date null (denorm from policy), `is_locked` bool (legal hold flag), `summary` text, `keywords` (comma-separated for search), `is_active` bool. `unique_together(tenant,code)`.
- **DocumentVersion** — `document` FK CASCADE, `version` str (e.g. `A`, `1.0`, `2025-04`), `file` FileField (allowlist `.pdf .docx .xlsx .pptx .txt .md .html .png .jpg .jpeg .svg`, 25 MB cap — L-22), `content_html` text optional (rich body for in-app authored docs), `change_notes` text, `uploaded_by` FK→User SET_NULL, `status` (draft / under_review / released / superseded), `checked_out_by` FK→User SET_NULL null/blank, `checked_out_at` datetime null, `released_at` datetime null. `unique_together(document,version)`.
- **DocumentAccessRule** — `document` FK CASCADE, `role` str (viewer / editor / approver / owner), `user` FK→User SET_NULL null/blank, `department` FK→`labor.Department` SET_NULL null/blank, `position` FK→`labor.Position` SET_NULL null/blank. XOR-validated: exactly one of (user, department, position) must be set. `unique_together(document,role,user,department,position)` enforced via `clean()` (L-01).

#### 19.2 SOP & Work Instruction Authoring

- **DocumentTemplate** — `code` (`TPL-00001`), `name`, `applies_to_doc_type` str (matches Document.doc_type values + `any`), `body` text (template skeleton with `{{placeholder}}` markers), `is_active` bool. `unique_together(tenant,name)`.
- **TemplateField** — `template` FK CASCADE, `field_name` slug, `label` str, `field_type` (text / textarea / number / date / select / boolean), `choices` text (one-per-line for select), `is_required` bool, `order` int. `unique_together(template,field_name)`.
- **MediaAttachment** — `document_version` FK→DocumentVersion CASCADE, `media_type` (image / video / pdf / audio / other), `file` FileField (allowlist `.png .jpg .jpeg .gif .svg .pdf .mp4 .webm .mov .mp3 .wav .ogg`, 25 MB cap — L-22), `caption` str, `video_url` URL optional (for externally-hosted YouTube/Vimeo embeds, validated to schemes http/https only), `uploaded_by` FK→User SET_NULL, `order` int.

#### 19.3 Document Approval Workflows

- **ApprovalWorkflow** — `name`, `description`, `applies_to_doc_type` str (matches Document.doc_type + `any`), `is_active` bool. `unique_together(tenant,name)`.
- **ApprovalStage** — `workflow` FK CASCADE, `stage_no` int (1, 2, 3, …), `name` str, `approver_role` (department_head / quality_manager / compliance_officer / plant_manager / cfo / other), `min_approvals` int default 1, `requires_signature` bool default True. `unique_together(workflow,stage_no)`.
- **DocumentApprovalRequest** — `code` (`AR-00001`), `document` FK PROTECT, `workflow` FK PROTECT, `current_stage_no` int default 1, `status` (pending / in_progress / approved / rejected / cancelled), `requested_by` FK→User SET_NULL, `requested_at` datetime auto, `decided_at` datetime null, `effective_date` date null (applied to Document on final approval), `notes` text. `unique_together(document)` partial via `clean()` — only one **open** approval request per document.
- **ApprovalAction** — append-only log: `request` FK→DocumentApprovalRequest PROTECT, `stage_no` int, `decision` (approve / reject / return_for_revision), `decided_by` FK→User SET_NULL, `decided_at` datetime auto, `notes` text, `signature` FK→DocumentSignature SET_NULL null.
- **DocumentSignature** — immutable e-sig (FDA 21 CFR Part 11): `document` FK→Document PROTECT, `signer` FK→User PROTECT, `signed_at` datetime auto, `meaning` (author / reviewer / approver / witness), `typed_name` str (mirrors User.get_full_name at sign time — captured at write time, never recomputed), `ip_address` GenericIP, `user_agent` text. **Admin readonly_fields = all fields** to enforce immutability.

#### 19.4 Training Document Assignment

- **DocumentAssignment** — `code` (`DA-00001`), `document` FK PROTECT, `assigned_by` FK→User SET_NULL, `assigned_at` datetime auto, `due_date` date null, `status` (active / completed / cancelled), `instructions` text. `unique_together(tenant,code)`.
- **AssignmentTarget** — `assignment` FK CASCADE, target XOR: `role` str (mirrors User.role) OR `department` FK→`labor.Department` SET_NULL OR `position` FK→`labor.Position` SET_NULL OR `employee` FK→`labor.Employee` SET_NULL OR `user` FK→User SET_NULL. Exactly one set, enforced via `clean()`.
- **ReadAcknowledgment** — `code` (`ACK-00001`), `assignment` FK CASCADE, `document_version` FK→DocumentVersion PROTECT (snapshot at ack time), `acknowledger` FK→User PROTECT, `acknowledged_at` datetime auto, `typed_name` str, `ip_address` GenericIP, `user_agent` text, `notes` text. `unique_together(assignment,acknowledger,document_version)` to block double-ack but allow re-ack on a new released version.

#### 19.5 Archive & Retention Policy

- **RetentionPolicy** — `code` (`RP-00001`), `name`, `applies_to_doc_type` str, `retention_years` int (`MinValueValidator(0)`, `MaxValueValidator(99)`), `archive_action` (archive / soft_delete / hard_delete), `legal_hold_compatible` bool default True (when False, legal hold blocks the auto-archive), `is_active` bool. `unique_together(tenant,name)`.
- **DocumentArchive** — `code` (`ARC-00001`), `document` FK→Document PROTECT, `archived_at` datetime auto, `archived_by` FK→User SET_NULL, `retention_until` date (computed from policy at archive time), `status` (archived / restored / purged), `restored_at` datetime null, `restored_by` FK→User SET_NULL null, `notes` text.
- **LegalHold** — `code` (`LH-00001`), `name`, `reason` text, `status` (active / released), `requested_by` FK→User SET_NULL, `requested_at` datetime auto, `released_at` datetime null, `released_by` FK→User SET_NULL null, `release_notes` text, `documents` M2M→Document `related_name='legal_holds'`. While at least one `LegalHold(status='active')` references a Document, that Document's `is_locked=True` and archive/retention cannot purge it.

**Preflight (L-25):** before writing FKs/signals, run the `_meta.fields` one-liner against `labor.Department`, `labor.Position`, `labor.Employee`, `compliance.ElectronicSignature` (sanity-check the e-sig field shape), and `accounts.User` (for role choices) — write code against the printed field lists, not guesses.

---

## Phase A — Scaffold, models, migration

- [ ] `apps/dms/__init__.py`, `apps.py` (`DmsConfig`, `verbose_name='Document & Knowledge Management'`, `ready()` imports signals), `migrations/__init__.py`
- [ ] `apps/dms/services/__init__.py`, `numbering.py` (copy `next_code` from rma), `checkout.py` (check_in / check_out / is_locked helpers), `approval.py` (advance_stage / finalize), `retention.py` (compute_retention_date / sweep_due_archives), `legal_hold.py` (apply_hold / release_hold), `assignment.py` (fan_out_targets / record_ack)
- [ ] `apps/dms/models.py` — all 17 models above
- [ ] `apps/dms/admin.py` — `@admin.register` per model, `tenant` in `list_display`+`list_filter`, `autocomplete_fields` for FKs, **`DocumentSignatureAdmin.readonly_fields = '__all__'`** to enforce immutability (L-17)
- [ ] Register `'apps.dms'` in `config/settings.py` INSTALLED_APPS (end of Local block)
- [ ] Mount `path('dms/', include('apps.dms.urls'))` in `config/urls.py`
- [ ] `python manage.py makemigrations dms` → `0001_initial.py`; `python manage.py migrate`

## Phase B — Forms, views, URLs

- [ ] `apps/dms/forms.py` — ModelForm per CRUD model; `tenant=` kwarg in `__init__`; per-tenant FK querysets (categories / templates / workflows / policies); explicit `clean()` for `unique_together` (L-01); XOR validators on `DocumentAccessRule` + `AssignmentTarget`; **`DocumentVersionForm`** validates checked_out_by==request.user before save (refuses overwrites if someone else holds the lock); per-workflow forms where a field is required only at a transition (L-14): `ApprovalRejectForm` requires notes, `LegalHoldReleaseForm` requires release_notes, `DocumentArchiveRestoreForm` requires notes
- [ ] `apps/dms/views.py` — `PAGE_SIZE=25`; `@login_required` everywhere; `request.tenant` filter first; list (search+filters+pagination, passes `*_choices`/FK querysets per **Filter Rules**), create, detail, edit, delete (POST-only, status-gated to match templates — L-03), workflow POST views; dashboard `index` view with KPI cards (Total docs, Docs in review, Active approval requests, Pending ack count, Active legal holds, Docs expiring ≤30d). **Check-in/check-out are POST views** that conditional-UPDATE `checked_out_by` to enforce optimistic locking
- [ ] `apps/dms/urls.py` — `app_name='dms'`; standard `*_list/_create/_detail/_edit/_delete` + workflow actions (check_in, check_out, submit_for_approval, approval_action, ack, archive, restore, hold_release)
- [ ] State-mutating views (approve / reject / archive / legal-hold / e-sig / delete) guarded by tenant-admin check (L-10); read-acknowledgment endpoint is per-user (any logged-in user can ack their own assignments)

## Phase C — Templates

- [ ] `templates/dms/index.html` — dashboard: KPI cards (total docs, in_review, pending approvals, pending acks for current user, active legal holds, docs expiring ≤30d), recent docs, my pending acks, open approval requests
- [ ] `templates/dms/_pagination.html`
- [ ] Per sub-module folders:
  - `templates/dms/categories/` — list / form / detail (hierarchical)
  - `templates/dms/documents/` — list (with search + doc_type + status + category + assigned-to-me filters) / form (with optional template selection) / detail (with version table + check-in/check-out buttons + access rules tab + approval requests tab + acknowledgment tab + media attachments tab + signatures tab) / version_form / access_form
  - `templates/dms/templates/` — list / form (with TemplateField inline CRUD) / detail
  - `templates/dms/workflows/` — list / form (with ApprovalStage inline CRUD) / detail
  - `templates/dms/approvals/` — list / detail (with per-stage action buttons + signature pad form) / cancel_form
  - `templates/dms/assignments/` — list / form (with AssignmentTarget inline) / detail (fan-out preview + ack list); **`my_acknowledgments.html`** = personal landing page for any user to ack pending docs
  - `templates/dms/retention/` — policy_list / policy_form / archive_list / archive_detail (with Restore action — admin only)
  - `templates/dms/legal_holds/` — list / form (with documents M2M selector) / detail (with affected docs + release form)
- [ ] Actions column (view / edit / delete, status-gated) + detail Actions sidebar per **CRUD Completeness Rules**
- [ ] Denorm fields rendered with row-level visual cues (L-26): expiry red ≤7d / yellow ≤30d, legal-hold lock badge, status badges
- [ ] `templates/partials/sidebar.html` — add "Documents & KMS" collapse group (`#sidebarDms`, `ri-file-text-line` icon) inside the `role != 'supplier'/'customer'` block

## Phase D — Signals & cross-module hooks (`apps/dms/signals.py`)

All `@receiver` at module scope, `dispatch_uid='dms.<action>'`, idempotent, `transaction.atomic()` for writes (L-18, L-23):

1. `DocumentVersion.post_save(status='released')` → mark prior released versions on the same document as `superseded`; update `Document.current_version` to this row; recompute `Document.status` to `effective` if there is an approved active `DocumentApprovalRequest`. Idempotent on re-save.
2. `DocumentApprovalRequest.post_save(status='approved')` → flip `Document.status='effective'`, set `Document.effective_date=request.effective_date or today`, set `Document.current_version` to the latest released version. Invalidate older `ReadAcknowledgment` rows by NOT changing them (audit-only trail) — fresh assignments must be issued for the new version.
3. `DocumentAssignment.post_save(created)` → expand `AssignmentTarget` rows into a set of `User`s to notify (compute in memory; do NOT create `ReadAcknowledgment` rows up-front — those are only created when each user actually clicks "Acknowledge"). Idempotent.
4. `LegalHold.post_save(status='active')` → set `documents.is_locked=True`; `LegalHold.post_save(status='released')` → set `is_locked=False` ONLY if no other active hold references the doc. Idempotent.
5. `RetentionPolicy.post_save` / `Document.post_save(retention_policy_id changed)` → recompute `Document.retention_until = effective_date + policy.retention_years` via `services/retention.compute_retention_date()`.
6. Audit-log receivers (`_audit` helper, L-23): status changes on `Document` / `DocumentApprovalRequest` / `LegalHold` / `DocumentArchive` → tenant audit log; check-in/check-out actions on `DocumentVersion`.
7. `DocumentSignature.pre_save` blocks `update` (raise on pk-set + changed) — signatures are immutable; only `post_save` for the first INSERT is allowed.

### Management commands

- [ ] `apps/dms/management/__init__.py`, `management/commands/__init__.py`
- [ ] `archive_due_documents.py` — daily job (L-21): scans `Document` rows where `retention_until < today AND status != 'archived' AND retention_policy.archive_action != 'noop'` AND no active legal hold; flips to `archived` via conditional `update()` and creates a `DocumentArchive` row. `--dry-run`, `--tenant`.
- [ ] `expire_assignments.py` — daily job: flags `DocumentAssignment` rows where `due_date < today AND status='active'` with no ack from all targets; surfaces in dashboard via a denorm/property. `--dry-run`, `--tenant`.

## Phase E — Seeder

- [ ] `apps/dms/management/commands/seed_dms.py`
- [ ] Idempotent (skip-if-exists + `--flush` + `--tenant`), iterates active tenants, `get_or_create` for catalogs (categories / templates / workflows / policies), existence-check for auto-numbered rows
- [ ] Seeds **per tenant**: 5 categories (SOP / WI / Policy / Form / Manual), 2 retention policies (5-year + 7-year), 1 approval workflow with 2 stages (Department Head → Quality Manager), 2 templates (SOP template + WI template), 5 Documents across all `doc_type`s with 1–2 versions each (one released, one draft for the SOP), 1 effective Document with full approval chain (`DocumentApprovalRequest(approved)` + 2 `ApprovalAction`s + 2 `DocumentSignature`s), 2 active `DocumentAssignment` rows (one role-based, one department-based) with 2–3 `ReadAcknowledgment` rows seeded for some users, 1 archived Document (with `DocumentArchive` row), 1 active `LegalHold` covering 1 Document (proving the `is_locked` cascade)
- [ ] No actual file uploads in seeder — `FileField` is left blank with a placeholder filename; readme note in seed output instructs users to upload real files via UI
- [ ] ASCII-only stdout (L-09); print non-zero counts (L-08); print tenant-admin login hint
- [ ] **Update `apps/core/management/commands/seed_data.py`** orchestrator to call `seed_dms` after `seed_rma`

## Phase F — Tests (`apps/dms/tests/`)

- [ ] `__init__.py`, `conftest.py` (fixtures: `tenant_a`, `tenant_b`, `tenant_admin`, `staff_user`, `dept`, `position`, `employee`, base Document objects — mirror `apps/rma/tests/conftest.py`)
- [ ] `test_models.py` — auto-numbering for every coded model, computed fields (`Document.retention_until` from policy, `ReadAcknowledgment.typed_name` capture), `__str__`, validators (`retention_years` bounds, file allowlist via form), L-22 file size cap, XOR validation on `DocumentAccessRule` + `AssignmentTarget`
- [ ] `test_forms.py` — `unique_together` `clean()` (L-01) on every catalog form, workflow-form required-field (L-14: ApprovalRejectForm needs notes, LegalHoldReleaseForm needs release_notes), FK querysets tenant-scoped, **check-out lock honored** (refuse save when checked_out_by ≠ request.user)
- [ ] `test_views.py` — HTTP CRUD smoke (list 200, create/edit/delete) on every CRUD endpoint, filters apply (status / doc_type / category), pagination, dashboard 200, check-in / check-out / submit-for-approval / record-action / ack / archive / legal-hold / release workflows happy path
- [ ] `test_services.py` — `next_code` retry loop, `check_in` / `check_out` optimistic-locking, `compute_retention_date` (with leap-year edge), `advance_stage` (multi-stage with `min_approvals`), `sweep_due_archives` honors active legal holds, `apply_hold` cascades `is_locked`, signatures immutable
- [ ] `test_signals.py` — each cross-module hook fires + is idempotent: version-released supersedes prior, approval-approved flips Document, legal-hold-active locks/unlocks, retention recompute, audit log emitted on status change. Second save = no dup row.
- [ ] `test_security.py` — multi-tenant IDOR (cross-tenant 404 on every detail URL: document / version / approval / workflow / template / assignment / archive / legal_hold / signature), RBAC matrix (staff blocked from approve / archive / legal-hold / signature endpoints — L-10), anonymous redirect on every list URL, **DocumentSignature insert-only** (PATCH returns 405; admin form has no fields)
- [ ] `test_seeder.py` — seeder idempotency (run twice, counts stable), `--flush` consistency, `archive_due_documents --dry-run` safety, `expire_assignments --dry-run` safety
- [ ] Run `pytest apps/dms/tests/` green before done (target ≈80–100 passing tests)

## Phase G — README + sidebar + final wiring

- [ ] `templates/partials/sidebar.html` — new "Documents & KMS" group
- [ ] **`README.md` mandatory update** (per CLAUDE.md README Maintenance Rule):
  - Highlights bullet describing Module 19
  - Table of Contents entry "Module 19 — Document & Knowledge Management"
  - Project Structure tree entry for `apps/dms/`
  - Screenshots/UI Tour table rows for every `/dms/...` route (~25 rows)
  - Dedicated **Module 19** section with sub-module spec + routes + test suite + out-of-scope deferrals
  - Management Commands table rows for `seed_dms`, `archive_due_documents`, `expire_assignments`, `pytest apps/dms/tests/`
  - Seeded Demo Data bullet describing per-tenant DMS seed counts
  - Roadmap — strike through "Document & Knowledge Management" + mark ✅ shipped; update intro line from "Modules 1-18" to "Modules 1-19"
- [ ] Run the full test suite scan one more time (`pytest apps/dms/tests/`) and verify no regressions in adjacent modules

## Phase H — Per-file git commit snippets

- [ ] Hand the user **one `git add` + `git commit` per file** (no bundling) per CLAUDE.md GIT Commit Rule. PowerShell-safe (`;` separator, single-quoted paths).

---

## Lessons applied (cross-checked against `.claude/tasks/lessons.md`)

- **L-01** `unique_together` with tenant excluded → form-level `clean()` (every catalog form: DocumentCategory, DocumentTemplate, ApprovalWorkflow, RetentionPolicy)
- **L-02** every Decimal/IntegerField carries explicit `MinValueValidator`/`MaxValueValidator` (`retention_years`, `min_approvals`, `stage_no`, `order`)
- **L-03** view + template status-gate parity via `is_*()` helpers on Document / DocumentApprovalRequest / LegalHold / DocumentArchive
- **L-09** ASCII-only stdout in seeder
- **L-10** state-mutating views guarded with `@tenant_admin_required` (approve / archive / legal-hold / e-sig)
- **L-12** auto-numbering retry loop via `save()` (mirrors rma / cost / utility)
- **L-13** `transaction.atomic()` around denorm bumps (Document.current_version + status flip on approval-approved signal)
- **L-14** per-workflow forms enforce required fields (rejection / archive restore / legal-hold release notes)
- **L-17** `on_delete=PROTECT` on every audit-trail child (DocumentSignature.document, DocumentArchive.document, ApprovalAction.request, ReadAcknowledgment.document_version)
- **L-18** `weak=False` + `dispatch_uid` on every closure receiver
- **L-21** time-driven status flip (`archive_due_documents` cron + race-safe conditional `update()`)
- **L-22** file uploads validate extension + content_type + size cap + magic-byte sniff (DocumentVersion.file, MediaAttachment.file)
- **L-23** audit-emit failures logged at WARNING (never raise, never block workflow)
- **L-25** preflight `_meta.fields` printout before writing FKs/signals
- **L-26** row-level visual cues for denorm fields (expiry tint, legal-hold badge, status badges)

---

## Out of scope (deferred — document explicitly in README)

- **Full-text search** over `Document.content_html` + uploaded file contents — keyword field only in v1; OpenSearch/Elasticsearch integration deferred
- **WebSocket live-collaboration** on `content_html` — single-author check-out/check-in only
- **External DMS integration** (SharePoint / Google Drive / Confluence) — not in v1
- **DocuSign / Adobe Sign** integration — typed-name e-sig only (FDA 21 CFR Part 11 compliant for internal use)
- **WORM (write-once-read-many) storage** for archived docs — application-level read-only enforcement only
- **Per-paragraph version diff** rendering — version list + change_notes only
- **Public-link sharing** for external reviewers — internal users only
- **Customer/supplier-portal document distribution** — internal staff only in v1

---

## Risks & open questions surfaced during planning

1. **Check-out lock is application-level**, not DB-level. Concurrent saves are mitigated by conditional `UPDATE ... WHERE checked_out_by IS NULL` in the `check_out` service. Multi-process race window is microseconds.
2. **`DocumentSignature` immutability** relies on the `pre_save` raise + admin `readonly_fields = '__all__'`. Direct DB writes via `Model.objects.filter().update()` would bypass this — but that's true for every FDA 21 CFR Part 11 model in the codebase (`compliance.ElectronicSignature` has the same constraint). Acceptable.
3. **`Document.retention_until` denorm** can drift if a `RetentionPolicy` changes after a Document is bound to it. Mitigated by signal #5 — but a `recompute_retention_dates` admin action is also planned for the seeder/maintenance use case (optional, deferred).
4. **Loose link to `compliance.ComplianceDocument`** — per user decision, *no* FK is added. README will document the relationship as "Module 13 owns regulatory-only artefacts; Module 19 owns operational documents. Cross-link manually via the `keywords` field if needed."
5. **`labor.Department` and `labor.Position` FKs** in `DocumentAccessRule` and `AssignmentTarget` are SET_NULL — a tenant deleting a department won't break access rules, but will leave them in an inconsistent state. UI surfaces this with a "Stale rule" badge.

---

## Estimated file count for commit snippets

| Group | Files |
|---|---|
| `apps/dms/` Python files (`__init__`, `apps`, `models`, `forms`, `views`, `urls`, `admin`, `signals`, `services/*`, `management/*`, `tests/*`) | ≈30 |
| `apps/dms/migrations/0001_initial.py` | 1 |
| `templates/dms/` html files (index + per-sub-module list/form/detail + partials) | ≈35 |
| `templates/partials/sidebar.html` (modified) | 1 |
| `config/settings.py` (INSTALLED_APPS), `config/urls.py` (include) | 2 |
| `apps/core/management/commands/seed_data.py` (orchestrator) | 1 |
| `README.md` (mandatory README maintenance) | 1 |
| **Total** | **≈71 files / 71 separate commits** |

---

## Review section (to be filled in after implementation)

_TBD — will document what shipped, what got deferred, and any lessons captured into [`lessons.md`](./lessons.md)._
