# BOM module — defect remediation plan

> Source: [.claude/manual-tests/bom-manual-test.md](../manual-tests/bom-manual-test.md) §4.13 candidate defects (TC-CREATE-05, TC-CREATE-10, TC-DELETE-04, TC-NEG-03, TC-NEG-04, TC-NEG-15, TC-EDIT-06)
> Verified reproducible 2026-04-26 via Django shell against seeded `admin_acme` data.

## Defect register

| ID | Severity | Location | Finding | Reproduction |
|---|---|---|---|---|
| D-01 | High | [apps/bom/forms.py:14-32](../../apps/bom/forms.py#L14-L32) | `BillOfMaterialsForm` excludes `tenant` from fields, so Django's `validate_unique()` cannot enforce `unique_together = ('tenant','product','bom_type','version','revision')`. A second submit with the same combination passes `is_valid()` and 500s on `IntegrityError` from the DB. | Shell: built form with same product/bom_type/version/revision as `BOM-00005`, `is_valid()=True`. Lessons.md #6 trap. |
| D-02 | High | [apps/bom/models.py:215](../../apps/bom/models.py#L215) | `BOMLine.quantity` has no validator — accepts negative, zero, and arbitrarily large values. Negative quantity propagates into rollup and explosion math. | Shell: `BOMLineForm(quantity='-5')` is valid. |
| D-03 | High | [apps/bom/models.py:219-222](../../apps/bom/models.py#L219-L222) | `BOMLine.scrap_percent` has no validator — accepts negative and >100. `effective_quantity()` computes `qty * (1 + scrap/100)` so 500% scrap yields 6× demand. | Shell: `BOMLineForm(scrap_percent='500')` is valid. |
| D-04 | Medium | [apps/bom/forms.py:14-32](../../apps/bom/forms.py#L14-L32) | No date-order validation between `effective_from` and `effective_to`. Tester can save a BOM that "expires" before it begins. | Shell: form with `effective_from=2026-12-31, effective_to=2026-01-01` is valid. |
| D-05 | Medium | [apps/bom/views.py:213-225](../../apps/bom/views.py#L213-L225) vs [templates/bom/boms/list.html:60](../../templates/bom/boms/list.html#L60) | View blocks delete only when `status=='released'`, but the list/detail templates only render the Delete button for Draft/Under Review. **Approved** BOMs can be deleted via crafted POST despite the UI hiding the button — inconsistent and error-prone. | Code inspection. UI gap noted in TC-DELETE-04. |
| D-06 | Medium | [apps/bom/models.py:55-58](../../apps/bom/models.py#L55-L58) | No constraint or save-time check enforces a single `is_default=True` per `(tenant, product, bom_type)`. Cost-rollup cascade ([apps/bom/models.py:185-188](../../apps/bom/models.py#L185-L188)) picks `.first()` non-deterministically when multiple defaults coexist. | Shell: settable on multiple BOMs, no error. |
| D-07 | Low | [apps/bom/views.py:419-432](../../apps/bom/views.py#L419-L432) | `BOMRollbackView` silently skips snapshot lines whose component SKU no longer exists in the tenant's product catalog ([apps/bom/views.py:441-443](../../apps/bom/views.py#L441-L443)). User sees a green success toast even when half the lines were dropped. | Code review. |

## Fix plan

- [ ] **F-01 (D-01, D-04)** — Add `BillOfMaterialsForm.clean()`:
  - Cross-field unique check via `BillOfMaterials.objects.filter(tenant=self.tenant, product=..., bom_type=..., version=..., revision=...).exclude(pk=self.instance.pk if self.instance.pk else None).exists()` → raise on `__all__` or specific field error.
  - Cross-field date check: `effective_to and effective_from and effective_to < effective_from` → `add_error('effective_to', '…')`.
  - Stash `tenant` on the form instance in `__init__` so `clean()` can use it.
- [ ] **F-02 (D-02)** — Add `MinValueValidator(Decimal('0.0001'))` (positive) to `BOMLine.quantity`. Generate migration.
- [ ] **F-03 (D-03)** — Add `MinValueValidator(Decimal('0'))` and `MaxValueValidator(Decimal('100'))` to `BOMLine.scrap_percent`. Generate migration.
- [ ] **F-04 (D-05)** — Tighten `BOMDeleteView`: only allow delete when `bom.is_editable()` (Draft / Under Review). Update messages accordingly.
- [ ] **F-05 (D-06)** — Add a `pre_save` signal on `BillOfMaterials` that, when `is_default=True`, demotes any other `(tenant, product, bom_type)` defaults. Atomic and tenant-scoped.
- [ ] **F-06 (D-07)** — Have `_restore_lines` count skipped components and surface the count back to the view, which appends a yellow warning to the success message when non-zero.
- [ ] **F-07** — Update [README.md](../../README.md) BOM section with a one-line "QA fixes" note (per CLAUDE.md README Maintenance Rule).
- [ ] **F-08** — Re-verify each defect against the patched code via Django shell.

## Migrations

A single migration covering the validator changes on `BOMLine` (quantity + scrap_percent). No DB column changes — validator-only. Name: `0002_bomline_validators.py`.

## Out of scope (future work)

- TC-CREATE-11 obsolete-product exclusion already works ([apps/bom/forms.py:30-32](../../apps/bom/forms.py#L30-L32)).
- TC-NEG-13 self-as-parent line is already prevented in form queryset ([apps/bom/forms.py:53](../../apps/bom/forms.py#L53)).
- Approved-state delete handling could grow into a "supersede on edit" workflow — out of scope.
- Rollback should perhaps fail loudly when *any* line is dropped, but the current "warn but persist" mode is reasonable; flag for future PR.

---

## Review — 2026-04-26

### What changed

| File | Change |
|---|---|
| [apps/bom/forms.py](../../apps/bom/forms.py) | `BillOfMaterialsForm` stashes tenant in `__init__` and adds a `clean()` that enforces tenant-scoped `unique_together(product, bom_type, version, revision)` and `effective_to >= effective_from`. Surfaces friendly errors on `revision` and `effective_to`. |
| [apps/bom/models.py](../../apps/bom/models.py) | Added `MinValueValidator(0.0001)` to `BOMLine.quantity`; added `MinValueValidator(0)` + `MaxValueValidator(100)` to `BOMLine.scrap_percent`. Imports updated. |
| [apps/bom/views.py](../../apps/bom/views.py) | `BOMDeleteView` now refuses any non-`is_editable()` BOM (was: only Released). `BOMRollbackView` collects skipped-component SKUs and surfaces a warning toast + records them on the rollback revision's `change_summary`. `_restore_lines` accepts an optional `skipped` accumulator. |
| [apps/bom/signals.py](../../apps/bom/signals.py) | Added a `post_save` receiver on `BillOfMaterials` that demotes any other `is_default=True` row in the same `(tenant, product, bom_type)` partition. Uses `.all_objects` to bypass the tenant manager. |
| [apps/bom/migrations/0002_alter_bomline_quantity_alter_bomline_scrap_percent.py](../../apps/bom/migrations/0002_alter_bomline_quantity_alter_bomline_scrap_percent.py) | Auto-generated validator-only migration. No DB column changes. Applied cleanly against MySQL/MariaDB. |
| [README.md](../../README.md) | "Audit signals" section adds the new `is_default`-enforcement bullet. New "Validation guards" section documents the four behavioural changes for future developers. |
| [.claude/manual-tests/bom-manual-test.md](../manual-tests/bom-manual-test.md) | TC-CREATE-05, TC-CREATE-10, TC-DELETE-04, TC-NEG-03, TC-NEG-04, TC-NEG-15 updated from CANDIDATE → expected-pass with the new behaviour described. |

### Verification

Each defect was reproduced in a Django shell **before** the fix, then re-run **after** the fix — every check went from "valid? True" to "valid? False" with a friendly form-level error, except F-04 (view-level) and F-05 (signal-level) which were verified by direct view invocation and `pre/post` `is_default` query counts respectively. See conversation log.

### Out of scope going forward

- Convert F-05 to a true DB-level partial unique index for stronger guarantees (`UniqueConstraint(condition=Q(is_default=True))`). Current signal-based approach handles 99% of code paths but not raw SQL bypasses. Track as a future follow-up.
- Rollback could bail entirely (rather than warn) when any line is dropped. Today's "warn but persist" matches user expectation per CLAUDE.md "no temporary fixes" — but flag for product input.

### Lesson captured

See [.claude/tasks/lessons.md](lessons.md) — generalised the unique_together-form trap (lesson #6) with a BOM-specific example.
