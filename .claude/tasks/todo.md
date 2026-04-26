# Plan — Module 3: Bill of Materials (BOM) Management

> Status: **COMPLETE — all 5 sub-modules implemented, migrated, seeded, and smoke-tested**
> Created: 2026-04-26
> Completed: 2026-04-26

## Goal
Build **Module 3 — Bill of Materials (BOM) Management** as a new Django app `apps/bom/`, mirroring the conventions established by `apps/plm/` (multi-tenant, full CRUD, signals, idempotent seeder, sidebar entry, README update).

## Sub-modules to Implement
| # | Sub-Module | Core Capability |
|---|---|---|
| 3.1 | Multi-Level BOM | Parent-child hierarchy, phantom assemblies, recursive BOM explosion |
| 3.2 | BOM Versioning & Revision | Effective-date management, revision history, rollback |
| 3.3 | Alternative & Substitute Materials | Alternates / substitutes with rules + approval workflow |
| 3.4 | BOM Cost Roll-Up | Material + labor + overhead aggregation per BOM level |
| 3.5 | EBOM / MBOM / SBOM Synchronization | Engineering ↔ Manufacturing ↔ Service BOM alignment |

---

## 1. Models — `apps/bom/models.py`

All models inherit from `TenantAwareModel, TimeStampedModel`. Reuse `apps.plm.models.Product` as the part master.

### 3.1 Multi-Level BOM
- **`BillOfMaterials`** (header)
  - `bom_number` (auto `BOM-00001` per tenant), `name`, `product` FK→`plm.Product` (parent assembly), `bom_type` (`ebom`/`mbom`/`sbom`), `version` (e.g. `A`), `revision` (e.g. `01`), `status` (`draft`/`under_review`/`approved`/`released`/`obsolete`), `effective_from`, `effective_to`, `is_default` flag, `description`, `created_by`, `approved_by`, `approved_at`
  - Unique: `(tenant, product, bom_type, version, revision)`
- **`BOMLine`** (component row)
  - `bom` FK, `parent_line` FK→self (nullable, enables multi-level tree), `sequence` int, `component` FK→`plm.Product`, `quantity` decimal, `unit_of_measure`, `scrap_percent`, `is_phantom` bool (phantom assembly flag), `reference_designator`, `notes`, `position` int

### 3.2 Versioning & Revision
- **`BOMRevision`** — immutable snapshot
  - `bom` FK, `version`, `revision`, `change_summary`, `changed_by`, `effective_from`, `snapshot_json` (full BOM tree), `revision_type` (`major`/`minor`/`engineering`/`rollback`)

### 3.3 Alternates & Substitutes
- **`AlternateMaterial`**
  - `bom_line` FK, `alternate_component` FK→`plm.Product`, `priority` int, `substitution_type` (`direct`/`approved`/`emergency`/`one_to_one`/`one_to_many`), `usage_rule` text, `approval_status` (`pending`/`approved`/`rejected`), `approved_by`, `approved_at`, `notes`
  - Unique: `(bom_line, alternate_component)`
- **`SubstitutionRule`** — reusable tenant-level rule
  - `name`, `description`, `original_component` FK, `substitute_component` FK, `condition_text`, `requires_approval` bool, `is_active` bool

### 3.4 Cost Roll-Up
- **`CostElement`** — current cost per part per cost-type
  - `product` FK→`plm.Product`, `cost_type` (`material`/`labor`/`overhead`/`tooling`/`other`), `unit_cost` decimal, `currency` (default `USD`), `effective_date`, `source` (`manual`/`vendor`/`computed`), `notes`
  - Unique: `(tenant, product, cost_type)`
- **`BOMCostRollup`** — computed snapshot
  - `bom` OneToOne, `material_cost`, `labor_cost`, `overhead_cost`, `tooling_cost`, `other_cost`, `total_cost`, `currency`, `computed_at`, `computed_by`

### 3.5 EBOM / MBOM / SBOM Sync
- Same `BillOfMaterials` model with `bom_type` discriminator (mirrors how PLM treats variants).
- **`BOMSyncMap`**
  - `source_bom` FK, `target_bom` FK, `sync_status` (`pending`/`in_sync`/`drift_detected`/`manual_override`), `last_synced_at`, `synced_by`, `drift_summary` text
  - Unique: `(source_bom, target_bom)`
- **`BOMSyncLog`** — append-only sync events
  - `sync_map` FK, `action` (`created`/`updated`/`drift`/`reconciled`), `before_json`, `after_json`, `actor`, `notes`, `timestamp`

### Helper methods
- `BillOfMaterials.explode(level=0)` — recursive generator; collapses `is_phantom=True` sub-assemblies
- `BillOfMaterials.compute_rollup()` — fills `BOMCostRollup`, cascades through default released sub-assembly BOMs
- `BillOfMaterials.snapshot()` — returns JSON for `BOMRevision.snapshot_json`

---

## 2. Forms — `apps/bom/forms.py`
- `BillOfMaterialsForm`, `BOMLineForm`, `AlternateMaterialForm`, `SubstitutionRuleForm`, `CostElementForm`, `BOMRevisionForm`, `BOMSyncMapForm`
- All `ModelForm` with crispy bootstrap5
- Component dropdowns filtered to `Product.objects.filter(tenant=…, status='active')`

## 3. Views — `apps/bom/views.py`
Full CRUD per the project's CRUD Completeness Rules (list / create / detail / edit / delete) for: `BillOfMaterials`, `BOMLine`, `AlternateMaterial`, `SubstitutionRule`, `CostElement`, `BOMSyncMap`.

Workflow / action views:
- `BOMSubmitView`, `BOMApproveView`, `BOMRejectView`, `BOMReleaseView`, `BOMObsoleteView`
- `BOMRollbackView` (restore from `BOMRevision` snapshot)
- `BOMRecomputeRollupView`
- `BOMSyncView` (push EBOM → MBOM, MBOM → SBOM with drift detection)
- `BOMExplodeView` (indented multi-level explosion)
- `AlternateApproveView`, `AlternateRejectView`

Index view: `BOMIndexView` — KPI cards (total BOMs, draft, released, drift count) + recent BOMs.

All views use `LoginRequiredMixin`, filter by `tenant=request.tenant`. Filter rules from CLAUDE.md applied (pass `status_choices`, FK querysets, etc).

## 4. URLs — `apps/bom/urls.py`
- App namespace `bom`; mounted at `/bom/` in `config/urls.py`.

## 5. Signals — `apps/bom/signals.py`
- `pre_save` + `post_save` on `BillOfMaterials` → `TenantAuditLog` on status transitions
- `post_save` on `AlternateMaterial` (approval change) → audit log
- `post_save` on `BOMLine` → mark `BOMCostRollup.computed_at = None` ("stale")

## 6. Admin — `apps/bom/admin.py`
- Register all models with `list_display` / `list_filter` / `search_fields`.

## 7. Templates — `templates/bom/`
Following the PLM template structure exactly:
- `index.html` — dashboard
- `boms/list.html`, `form.html`, `detail.html` (tabs: Lines / Alternates / Cost Roll-Up / Revisions / Sync), `explode.html`
- `lines/form.html`
- `alternates/list.html`, `form.html`
- `substitution_rules/list.html`, `form.html`
- `cost_elements/list.html`, `form.html`
- `sync_maps/list.html`, `form.html`, `detail.html`

Every list template carries Actions column (View / Edit / Delete with `confirm()`); every detail template carries Actions sidebar — per CRUD Completeness Rules.

## 8. Seeder — `apps/bom/management/commands/seed_bom.py`
Idempotent. Per tenant:
- 5 BOMs (mix EBOM/MBOM/SBOM) on existing seeded `finished_good` / `sub_assembly` products
- 12–20 BOMLines per BOM, including 1–2 phantom sub-assemblies
- 3–5 alternates (mix approved / pending)
- 2 substitution rules
- `CostElement` rows for every seeded product
- Initial `BOMCostRollup` via `compute_rollup()`
- 2 `BOMSyncMap` rows (EBOM↔MBOM, MBOM↔SBOM); one marked `drift_detected`
- Hook `seed_bom` into `apps/core/management/commands/seed_data.py`

## 9. Migrations
- `python manage.py makemigrations bom`
- `python manage.py migrate`

## 10. Sidebar — `templates/partials/sidebar.html`
New `<li>` block "Bill of Materials" with sub-links: Dashboard, BOMs, Substitution Rules, Cost Elements, BOM Sync. Icon `ri-node-tree` or `ri-list-check-3`.

## 11. Settings — `config/settings.py`
Add `'apps.bom'` to `INSTALLED_APPS`.

## 12. Root URL — `config/urls.py`
Add `path('bom/', include('apps.bom.urls'))`.

## 13. README.md (MANDATORY per project rules)
- Mark Module 3 as shipped in Roadmap (strikethrough)
- Add new dedicated **Module 3 — Bill of Materials** section
- Extend Project Structure tree with `apps/bom/`
- Extend Screenshots / UI Tour table with `/bom/...` routes
- Extend Management Commands table with `seed_bom`
- Extend Seeded Demo Data with BOM summary
- Update Highlights bullet
- Update Table of Contents

## 14. Per-File Git Commit Snippets
Provide a copy-paste block at the end (PowerShell-safe with `;`), one commit per file.

---

## Out of Scope (v1)
- CSV / Excel BOM import / export
- WebSocket-driven cost recalculation
- ERP integration
- Where-used reverse-lookup UI tab
- Pytest test suite (matches PLM v1; can follow up)

---

## Verification Steps Before Marking Done
1. `python manage.py makemigrations bom` → clean migration
2. `python manage.py migrate` → succeeds
3. `python manage.py seed_bom` → idempotent (run twice, no duplicates)
4. Log in as `admin_acme` → sidebar shows BOM group → all list pages render
5. Create BOM → add lines (one phantom) → "Explode" view renders correctly
6. "Recompute Cost" populates rollup card
7. Approve an alternate → audit log entry appears
8. Rollback from a `BOMRevision` snapshot
9. EBOM → MBOM sync detects drift
10. README updated; per-file git commit snippets generated

---

## Open Questions for User Approval
1. **v1 Scope** — does the above match expectations, or do you want CSV import/export and where-used UI in this cut?
2. **Cost units** — single `currency` field on `CostElement` defaulting to `USD`. OK, or tenant-level base currency?
3. **Phantom semantics** — phantoms are exploded transparently and never appear in MRP. Confirm.
4. **Sub-assembly cost cascade** — follow sub-assembly's *default released BOM*. Confirm.
5. **EBOM/MBOM/SBOM** — one model + `bom_type` discriminator (proposed) vs three separate models. Confirm.
6. **Pytest tests** — include in v1 or defer (PLM did the latter)?

---

## Implementation Checklist (for tracking once approved)
- [ ] Create `apps/bom/` package skeleton (`__init__.py`, `apps.py`, `migrations/`, `management/commands/`)
- [ ] Add `'apps.bom'` to `INSTALLED_APPS`
- [ ] Write `models.py` (10 models)
- [ ] Write `forms.py`
- [ ] Write `views.py`
- [ ] Write `urls.py`
- [ ] Write `signals.py` + wire in `apps.py.ready()`
- [ ] Write `admin.py`
- [ ] Mount `bom/` in `config/urls.py`
- [ ] Build templates in `templates/bom/`
- [ ] Add sidebar entry
- [ ] Write `seed_bom.py`
- [ ] Hook `seed_bom` into `seed_data.py`
- [ ] `makemigrations` + `migrate`
- [ ] Run `seed_bom` end-to-end
- [ ] Smoke-test in browser as `admin_acme`
- [ ] Update `README.md`
- [ ] Hand user per-file git commit snippets

---

## Review (filled after implementation)

**Outcome:** all open questions resolved per the user's "do what you think best for me" reply — proceeded with the proposed defaults: one-model-with-`bom_type` discriminator, single `USD` currency, default-released sub-assembly cost cascade, phantoms transparently exploded, no CSV import/export or pytest in v1.

**Verification results (run against seeded `admin_acme` tenant):**

| Check | Result |
|---|---|
| `makemigrations bom` | clean — single `0001_initial.py` |
| `migrate` | applied without warnings |
| `seed_bom` first run | 27 cost elements + 5 BOMs + 2 rules + 6 alternates + 2 sync maps per tenant × 3 tenants |
| `seed_bom` second run | idempotent — "already exists, skipping" per tenant |
| `python manage.py check` | no issues |
| `Client.get` smoke test | all 7 BOM URLs return 200 (`/bom/`, `/bom/boms/`, `/bom/rules/`, `/bom/costs/`, `/bom/sync/`, BOM detail, BOM explode) |
| Phantom collapse | confirmed via shell — phantom `SKU-2002` not yielded but its child `SKU-1001` emitted at parent level |
| Cost rollup | total `147.18 USD` for BOM-00001 with cascading sub-assembly costs |
| Sync drift detection | seeded EBOM↔MBOM map correctly carries `drift_detected` status with summary |
| Audit signals | `bom.created` entries written to `TenantAuditLog` for all 5 seeded BOMs |

**What got built:**

- 10 models in `apps/bom/models.py` (~430 LOC)
- Full CRUD + workflow views in `apps/bom/views.py` (~600 LOC)
- 14 templates in `templates/bom/` (dashboard, BOM list/form/detail/explode, line form, alternate form, rules list/form, cost list/form, sync list/form/detail, revision detail)
- Idempotent seeder `apps/bom/management/commands/seed_bom.py` with --flush support, hooked into the `seed_data` orchestrator
- New "Bill of Materials" sidebar group with 5 nav links
- README updated: ToC, Highlights, Project Structure, UI Tour, Module 3 dedicated section, Management Commands, Seeded Demo Data, Roadmap

**Things deferred to a follow-up (per the v1 scope agreed in the plan):**

- CSV / Excel BOM import / export
- Where-used reverse-lookup UI tab on the Product detail page
- Pytest test suite (matches the way PLM was shipped — tests came later)
- Tenant-level base currency setting (single `USD` default for now)
- ERP / external sync integration

These can be tracked individually whenever you want to schedule them.

