# Lessons learned

Running log of corrections and rules. New lessons go to the bottom. Each entry is concise — write the rule, then *why* in one line, then *how to apply*.

---

## L-01 — `unique_together` with `tenant` excluded from a ModelForm escapes to a 500

**Rule:** When a model has `unique_together = ('tenant', <field-a>, <field-b>, …)` and the ModelForm's `Meta.fields` does NOT include `tenant`, Django's default `validate_unique()` cannot enforce the constraint, so a duplicate submit reaches the DB and 500s on `IntegrityError`.

**Why:** Django's `validate_unique()` skips any unique_together set that touches a field not present in `cleaned_data` — `tenant` is set by the view post-`commit=False`, never by the form. The view layer's `_save_with_unique_number` retry only catches collisions on the auto-numbered field, not on the underlying unique_together.

**How to apply:** every tenant-scoped model whose form excludes `tenant` (which is most of them in this codebase) needs an explicit `clean()` that performs the duplicate check itself, scoped to `self._tenant` (stash the tenant in `__init__`). Example: [apps/bom/forms.py — BillOfMaterialsForm.clean()](../../apps/bom/forms.py).

**Concrete examples in repo:**
- `BillOfMaterialsForm` — fixed 2026-04-26 in [.claude/tasks/bom_sqa_fixes_todo.md](bom_sqa_fixes_todo.md) F-01.
- Audit other tenant-scoped forms (`AlternateMaterialForm`, `BOMSyncMapForm` already partially handle, `CostElementForm` relies on view-level `try/except IntegrityError`) — anywhere `Meta.fields` doesn't include `tenant`, check whether the unique_together is enforced.

---

## L-02 — Decimal model fields need explicit validators or they accept any value in range

**Rule:** A bare `DecimalField` with no `validators=[...]` accepts negative, zero, and arbitrarily-large values up to its `max_digits` boundary. The form layer will not synthesize range checks for you.

**Why:** Quantity `-5`, `0`, and scrap `500%` all parsed as valid Decimals and saved without complaint, then propagated into rollups and explosions. The bug surfaces in math output, not in form errors — much harder to detect.

**How to apply:** every `DecimalField` representing a physical quantity, percentage, money amount, or count gets explicit `MinValueValidator` (and `MaxValueValidator` where there's a natural ceiling like 100% for percentages). Add the migration the same turn — don't ship the model change without the migration.

**Concrete example in repo:** [apps/bom/models.py — BOMLine](../../apps/bom/models.py) — fixed 2026-04-26 in [.claude/tasks/bom_sqa_fixes_todo.md](bom_sqa_fixes_todo.md) F-02 / F-03.

---

## L-03 — View-side status gates must match the buttons rendered by the template

**Rule:** If the list/detail template only renders a button under `{% if obj.status in (...) %}`, the corresponding view MUST also reject any other status. Otherwise a hand-crafted POST bypasses the UI and ends up in a state the rest of the system never expects.

**Why:** The original `BOMDeleteView` only blocked `released` — but the templates only rendered the Delete button for `draft` / `under_review`. An attacker (or a clever tester with DevTools) could delete an `approved` BOM, leaving sync maps and revisions referencing it dangling.

**How to apply:** when adding a status-gated UI button, use the same `is_editable()` / `is_actionable()` helper on the model in BOTH the template and the view. Don't repeat the literal status-list in two places.

**Concrete example in repo:** [apps/bom/views.py — BOMDeleteView](../../apps/bom/views.py) — fixed 2026-04-26 in [.claude/tasks/bom_sqa_fixes_todo.md](bom_sqa_fixes_todo.md) F-04.

---

## L-04 — Operations that silently drop data should warn loudly

**Rule:** When a write path can drop or skip records (orphans, missing FKs, schema drift), the user MUST see a warning that names the count and ideally a sample of what was dropped. A green success toast on a partial operation is worse than an outright failure.

**Why:** `BOMRollbackView` was returning "rolled back to revision X" even when half the lines were skipped because their components no longer existed in the catalog. The user thought the rollback worked.

**How to apply:** any view that loops over external data (snapshots, JSON imports, CSV uploads) should accumulate a `skipped: list[str]` and surface it as a `messages.warning(...)` AND record it on whatever revision/audit row the operation creates.

**Concrete example in repo:** [apps/bom/views.py — BOMRollbackView](../../apps/bom/views.py) — fixed 2026-04-26 in [.claude/tasks/bom_sqa_fixes_todo.md](bom_sqa_fixes_todo.md) F-06.

---

## L-05 — Naive vs aware datetimes silently work in unit tests, then crash on the first call from a view

**Rule:** When a service computes against `datetime.combine(date, time)` (which is naive) and the public entry point may receive `timezone.now()` (which is aware under `USE_TZ=True`), the comparison `cursor < shift_end` raises `TypeError: can't compare offset-naive and offset-aware datetimes`. Either normalize at the boundary or reject one of the two shapes loudly.

**Why:** The PPS scheduler service is a pure-function module that does its calendar walk in naive local time (because shift definitions are naive `time` values). I caught this only on the first real seeder run, not in the model layer. Django's `USE_TZ=True` is the project default, so any service that wraps `datetime.combine()` arithmetic is at risk.

**How to apply:** at the public entry point of any datetime-walking service, strip tz with `dt.replace(tzinfo=None)` and stash the original `tzinfo`; do the math; re-attach the tzinfo on every output datetime. Encapsulate with `_strip_tz(dt) -> (naive, tz)` + `_attach_tz(dt, tz)` helpers — never sprinkle `replace(tzinfo=...)` calls through the algorithm body.

**Concrete example in repo:** [apps/pps/services/scheduler.py](../../apps/pps/services/scheduler.py) — fixed 2026-04-27 during initial PPS seeding.

---

## L-06 — One file per commit means ONE file per commit, never "logical groups"

**Rule:** When the user asks for per-file git commit snippets, every single file gets its own `git add` + `git commit` pair. Never bundle "the three templates of a sub-module" or "the four files of a feature folder" into one commit, regardless of how tightly they're related.

**Why:** The user reviews and squashes commits by hand and explicitly wants each file's history isolated. I bundled the 4 routing templates into one commit ("feat(pps): routing templates with operation CRUD inline") — they had to ask me to redo every batched group across the entire Module 4 snippet block. Folder-grouping looks economical to me; it costs the user time when they want to revert / cherry-pick / review one file.

**How to apply:** when generating commit snippets, output one block per file. **Never** put two file paths after a single `git add`. Even shared `__init__.py` files, even three near-identical sibling templates. The signal that I should bundle is **always wrong** — resist it. Re-read [.claude/CLAUDE.md → GIT Commit Rule → "STRICT — ONE FILE PER COMMIT (no exceptions)"](../../.claude/CLAUDE.md) before producing the final block.

**Concrete example in repo:** the Module 4 (PPS) commit snippet bundle was rejected on 2026-04-27 because of this; the corrected snippet block in [.claude/tasks/todo.md](todo.md) review section is the new reference shape.

---

## L-07 — When embedding server data in inline JS, use `{{ data|json_script:"id" }}`, never `{{ json_dumps_string|safe }}`

**Rule:** To pass server-side Python data into an inline `<script>` block, ALWAYS use Django's `{{ data|json_script:"some-id" }}` template tag and read it via `JSON.parse(document.getElementById('some-id').textContent)`. Never call `json.dumps()` in the view and emit it as `{{ chart_series_json|safe }}`.

**Why:** `json.dumps` does not escape `</script>`, `<`, `>`, `&`, or `'` — these aren't required for valid JSON-as-data, but they ARE required for safe embedding inside an HTML `<script>` tag. A user-controlled string like a Product SKU containing `</script><img src=x onerror=alert(1)>` will close the script tag and execute the injected `<img>` payload. The `json_script` template tag wraps the data in `<script type="application/json">` and HTML-escapes the dangerous characters automatically.

**How to apply:** in views, return the raw Python list/dict (NOT a json.dumps string). In templates, `{{ obj|json_script:"chart-id" }}` BEFORE the `<script>` block that consumes it. In JS, read with `JSON.parse(document.getElementById('chart-id').textContent)`. Add a grep guard in code review: `chart_series_json|safe` is a smell.

**Concrete example in repo:** [templates/pps/orders/gantt.html](../../templates/pps/orders/gantt.html), [templates/pps/capacity/dashboard.html](../../templates/pps/capacity/dashboard.html) — fixed 2026-04-28 in [.claude/tasks/pps_sqa_fixes_todo.md](pps_sqa_fixes_todo.md) F-01 (defect D-01).

---

## L-08 — When seeding cross-module data, align horizons or the consuming engine looks broken

**Rule:** When a seeder for module B reads date-bounded data produced by module A's seeder (e.g. MRP reading MPS lines), the consumer's horizon MUST overlap the producer's data window. Otherwise the engine runs cleanly with zero output and looks broken. Either align horizons explicitly in the seeder, or extend the producer's data window so any reasonable consumer horizon hits it.

**Why:** The MRP seeder's first run produced **0 planned orders, 0 PRs, 0 exceptions** for all 3 tenants. The engine ran fine — but the seeded `MasterProductionSchedule` only carries 2 weeks of lines starting from the first day of the current month, and my MRP horizon was `today → today + 28 days`. When today is past day 14 of the month, those windows never overlap, so the engine collected zero demand. A green "completed" status with empty results is much harder to debug than an outright failure.

**How to apply:** when wiring a seeder that consumes another module's data, either pull the source module's actual horizon and use it (`mrp.MRPCalculation.horizon_start = mps.horizon_start` if `mps` is linked) or extend the producer's data to span ±60 days from today so any reasonable consumer horizon hits it. ALWAYS print a non-zero result count in the seeder output (e.g. `19 planned orders, 10 PRs, 35 exceptions`) so a zero count is visible immediately, not buried in a "completed" status.

**Concrete example in repo:** [apps/mrp/management/commands/seed_mrp.py — `_seed_mrp_run`](../../apps/mrp/management/commands/seed_mrp.py) — fixed 2026-04-28 during initial Module 5 seeding. The fix sets `horizon_start = mps.horizon_start` and `horizon_end = mps.horizon_end` whenever a source MPS exists.

---

## L-09 — Console output: keep seeder strings ASCII-safe; Windows cp1252 chokes on Unicode arrows

**Rule:** Management command stdout must be ASCII-only (or explicitly utf-8-safe) on Windows. The default Windows console (cp1252) cannot encode `→`, `·`, `✓`, `←`, `★`, etc. and crashes the entire seeder with `UnicodeEncodeError: 'charmap' codec can't encode character`.

**Why:** I copied the dashboard's `→` arrow into the MRP seeder output. The seeder ran fine until the first `self.stdout.write(...)` call, then crashed mid-tenant. The existing PPS seeder uses `->` for exactly this reason; I should have noticed and matched.

**How to apply:** in any `BaseCommand.handle()` that writes to `self.stdout`, restrict to ASCII characters. Use `->` not `→`, prefer ` - ` or `*` over `·`, and avoid emoji entirely. Templates and other text rendered via Django's HTTP response are utf-8 by default and safe — this rule applies *only* to direct `stdout.write()` paths.

**Concrete example in repo:** [apps/mrp/management/commands/seed_mrp.py:326](../../apps/mrp/management/commands/seed_mrp.py) — fixed 2026-04-28 by changing `→ Tenant:` to `-> Tenant:`. Pattern reference: [apps/pps/management/commands/seed_pps.py:487](../../apps/pps/management/commands/seed_pps.py).

---

## L-10 — Workflow modules need an explicit RBAC layer; `TenantRequiredMixin` is not enough

**Rule:** Any view that mutates a status (approve, apply, commit, resolve, ignore, discard, cancel, delete-of-workflow-row) must be guarded by `TenantAdminRequiredMixin` (or a more granular role mixin). `TenantRequiredMixin` only enforces "logged in + has tenant" — every staff user in the tenant inherits full mutation power, which is a material A01 violation for any ERP-shaped workflow.

**Why:** The MRP module shipped with `PRApproveView`, `RunApplyView`, `ExceptionResolveView`, `ExceptionIgnoreView`, `CalculationDeleteView`, `RunDiscardView` etc. all on `TenantRequiredMixin`. A non-admin tenant user could approve PRs, apply MRP runs (committing the calc), ignore critical exceptions, and delete calculations. The PPS module already does this correctly — it was a regression of pattern, not a new design problem.

**How to apply:** when adding a state-changing view to a tenant-scoped workflow, default to `TenantAdminRequiredMixin`. Keep `TenantRequiredMixin` for read-only / list / detail / non-privileged CRUD only. Always pair the change with a `test_*_d01` test that confirms `staff_client.post(<url>)` is a redirect AND that the underlying row's status did not change. The two-assertion pattern catches both the redirect AND silent-success regressions.

**Concrete example in repo:** [apps/mrp/views.py](../../apps/mrp/views.py) — fixed 2026-04-29 in [.claude/tasks/mrp_sqa_fixes_todo.md](mrp_sqa_fixes_todo.md) F-01 (defect D-01). RBAC matrix test in [apps/mrp/tests/test_security.py — TestRBACMatrix](../../apps/mrp/tests/test_security.py).

---

## L-11 — When a docstring promises three modes but the code implements one, delete the dead branch — don't tip-toe around it

**Rule:** If an engine accepts a `mode=` parameter and only one branch is real (the others are placeholders for "future optimisation"), the placeholders MUST either be removed OR collapse cleanly to the real branch. Leaving a half-implemented mode that "skips deletion but still bulk-creates" is worse than no mode at all — the unique constraint will surface as a 500 the moment someone exercises it.

**Why:** The MRP engine's docstring claimed three modes (`regenerative`, `net_change`, `simulation`) but the code only handled two. `net_change` skipped the wipe step but still ran the full bulk_create, so the second call against the same calc raised `IntegrityError` on `unique_together(mrp_calculation, product, period_start)`. The form exposed `net_change` to operators, so this was selectable from the UI — i.e. one click away from a 500. The fix was to delete the conditional and have all three modes wipe-and-recompute, with the docstring updated to say so honestly.

**How to apply:** when reviewing or writing dispatch logic with multiple branches, audit each branch end-to-end: does it produce a coherent, persistable result? If not, either (a) collapse the branch to the working one with a comment explaining the v1 limitation, or (b) raise `NotImplementedError` so the caller knows immediately. NEVER leave a branch that runs to completion but produces an invalid persistence state.

**Concrete example in repo:** [apps/mrp/services/mrp_engine.py — `run_mrp` step 4](../../apps/mrp/services/mrp_engine.py) — fixed 2026-04-29 in [.claude/tasks/mrp_sqa_fixes_todo.md](mrp_sqa_fixes_todo.md) F-02 (defect D-02). Regression test in [apps/mrp/tests/test_engine.py — TestEngineNetChangeModeD02](../../apps/mrp/tests/test_engine.py).

---

## L-12 — Sequence-numbered FKs need retry-on-IntegrityError, not just `count + 1`

**Rule:** Any auto-generated identifier built from `MAX(prefix-NNNNN) + 1` (or `count + 1`) MUST be wrapped in a transaction-per-row retry loop that catches `IntegrityError` and re-reads the max. Two engine runs (or two HTTP workers) can both observe the same starting value and collide on the unique constraint.

**Why:** The MRP engine's PR auto-generation computed `existing_count + 1` once and incremented in a Python loop. Two concurrent engine runs against the same tenant would both pick the same starting sequence and the second run's first INSERT would 500 on `unique_together(tenant, pr_number)`. The pattern reference `_save_with_unique_number` already exists in [apps/mrp/views.py](../../apps/mrp/views.py) for exactly this — engines should reuse it.

**How to apply:** every engine / service that creates rows with prefixed sequence identifiers should wrap each `.create()` in a 5-attempt try/except IntegrityError + recompute-next-number loop. Then assert in tests that pre-allocating the engine's "starting slot" does NOT crash subsequent calls — see [apps/mrp/tests/test_engine.py — TestEnginePRSequenceD04](../../apps/mrp/tests/test_engine.py).

**Concrete example in repo:** [apps/mrp/services/mrp_engine.py — `_next_mpr_sequence`](../../apps/mrp/services/mrp_engine.py) — fixed 2026-04-29 in [.claude/tasks/mrp_sqa_fixes_todo.md](mrp_sqa_fixes_todo.md) F-04 (defect D-04).

---

## L-13 — Catching `IntegrityError` without an inner savepoint poisons the parent transaction

**Rule:** When a view does `try: Model.objects.create(...) except IntegrityError:`, wrap the `create()` (or any single statement that may raise) inside an inner `with transaction.atomic():` block. Otherwise the failed statement leaves the parent transaction in a broken state, and any subsequent ORM call raises `TransactionManagementError: An error occurred in the current transaction. You can't execute queries until the end of the 'atomic' block.`

**Why:** Django's transaction model says: an exception inside an atomic block aborts THAT atomic. With a NESTED atomic, only the inner savepoint is rolled back — the outer keeps going. Without the inner atomic, the failure aborts whichever atomic is active. Production usage with `ATOMIC_REQUESTS=True` and pytest-django's per-test transaction wrap both expose the bug; plain autocommit usage hides it. The toast still renders because flash messages don't hit the DB, so the bug looks fine in isolated manual testing.

**How to apply:** any view that `try: ... except IntegrityError: ...` MUST wrap the protected call:
```python
try:
    with transaction.atomic():
        Model.objects.create(...)
    messages.success(...)
except IntegrityError:
    messages.info(...)
```
Same rule applies to `ProtectedError` on delete paths and any other DB-error path where downstream queries follow.

**Concrete example in repo:** [apps/mes/views.py — InstructionAcknowledgeView](../../apps/mes/views.py) — fixed 2026-04-29 (Module 6 manual-test walkthrough, BUG-06). Regression test in [apps/mes/tests/test_seeder.py — TestBug06AckSavepoint](../../apps/mes/tests/test_seeder.py).

---

## L-14 — `blank=True` on a model field doesn't mean every workflow ModelForm should accept blank

**Rule:** A model field with `blank=True` allows empty values at the DB layer. A ModelForm built from that field inherits the same permissiveness. If you have a workflow where the field is REQUIRED at one transition (e.g. resolving an alert) but optional elsewhere (drafting an alert), add a `clean_<field>()` on the workflow-specific form — don't change `blank=True` on the model.

**Why:** `AndonAlert.resolution_notes` is `TextField(blank=True)` because alerts in `open / acknowledged / cancelled` states have no resolution notes. But `AndonResolveForm` is the *resolve transition* — at that point a note is mandatory for traceability. The original ModelForm inherited `blank=True` and accepted whitespace input, which silently flipped the andon to `resolved` with empty `resolution_notes` — TC-ACTION-12 in the MES manual-test plan caught it. The success toast appeared even though no note was filed.

**How to apply:** when a single field has different required-ness across workflows, define a per-workflow form (`SubmitForm`, `ResolveForm`, `ApproveForm`, etc.) with a `clean_<field>` that enforces the per-workflow rule. Keep the model permissive — it represents the union of all valid states. Tag the per-form override with a one-line comment explaining the workflow constraint.

**Concrete example in repo:** [apps/mes/forms.py — AndonResolveForm.clean_resolution_notes](../../apps/mes/forms.py) — fixed 2026-04-29 (Module 6 manual-test walkthrough, BUG-05). Regression test in [apps/mes/tests/test_seeder.py — TestBug05AndonResolveRequiresNotes](../../apps/mes/tests/test_seeder.py).

---

## L-15 — Reading a denormalised field from a stale Python variable after `.update()`

**Rule:** Django's `QuerySet.update(field=value)` writes directly to the DB and does NOT refresh in-memory model instances. If you read an updated field from the same Python variable later in the same function, you get the pre-update value. Either re-fetch from DB, call `instance.refresh_from_db(fields=['field'])`, or — preferably — keep the value you wrote in a local variable and reuse it.

**Why:** The MES seeder's `_seed_time_logs_and_reports` did `MESWorkOrderOperation.all_objects.filter(...).update(total_good_qty=wo.quantity_to_build)` then later read `first_op.total_good_qty` to roll up the parent work order. The Python variable still held the value from the earlier `select_related` fetch (`Decimal('0')`), so the work order's `quantity_completed` was set to `0` even though the op's DB row said `10`. The seeded data became internally inconsistent — TC-DETAIL-01 in the MES manual test plan would catch the rollup mismatch.

**How to apply:** anywhere you do `Model.objects.filter(...).update(...)` and use the same instance variable later, prefer:
1. Capture the value in a local first: `new_value = some_calc(); Model.objects.filter(...).update(field=new_value); use(new_value)`.
2. Or `instance.refresh_from_db(fields=['field'])` immediately after the `.update()`.

Avoid `Model.save()` here only when there are signals you specifically want to skip; otherwise `instance.field = new_value; instance.save()` is the cleanest path because the instance stays in sync with the DB.

**Concrete example in repo:** [apps/mes/management/commands/seed_mes.py — _seed_time_logs_and_reports](../../apps/mes/management/commands/seed_mes.py) — fixed 2026-04-29 (Module 6 manual-test walkthrough, BUG-02 / BUG-03). Regression test in [apps/mes/tests/test_seeder.py — TestBug02SeededRollupConsistency](../../apps/mes/tests/test_seeder.py).

---

## L-16 — When a `post_save` signal denormalises onto the parent, seed the parent's denorm fields AFTER the children, via `.update()` (which bypasses signals)

**Rule:** If a child model has a `post_save` signal that writes denormalised fields onto the parent (e.g. `CalibrationRecord` writes `last_calibrated_at` / `next_due_at` onto `MeasurementEquipment`), a seeder that needs the parent in a specific denormalised state MUST set those fields via `Parent.all_objects.filter(...).update(...)` AFTER the children have been bulk-created. Setting them on the parent row first — the obvious order — gets silently overwritten the moment a single child is saved through `.create()`.

**Why:** The QMS seeder set `MeasurementEquipment.next_due_at = now + 5 days` to demo a "due-soon yellow row" on the dashboard. Then it seeded 8 calibration records via `CalibrationRecord.all_objects.create()`. The `_propagate_calibration_to_equipment` `post_save` signal fired on every record and pushed the equipment's `next_due_at` to `cal_at + interval_days` — months in the future. The dashboard never showed a single yellow or red row even though the seeder claimed to produce two. The manual test (TC-LIST-04 in `qms-manual-test.md`) caught it on the first pass.

**How to apply:** for any seeder that wants the parent row in a specific denorm state, run `Parent.all_objects.filter(pk=...).update(field=value)` AS THE LAST STEP for that fixture. `.update()` bypasses Django signals (per `QuerySet.update()` docs). Bonus: the same trick lets seeders age data deliberately ("this calibration was filed 380 days ago, equipment is overdue") without the signal undoing the test fixture.

**Concrete example in repo:** [apps/qms/management/commands/seed_qms.py — `_pin_equipment_due_dates`](../../apps/qms/management/commands/seed_qms.py) — added 2026-05-01 (Module 7 manual-test walkthrough, BUG-01).

---

## L-17 — `on_delete` on regulated/audit-trail child FKs is an audit decision, not just a referential decision — default to PROTECT

**Rule:** When a child model represents a regulated or audit-trail record (CalibrationRecord, AuditLog, ApprovalDecision, NCR closure, certificate, payment, etc.), the FK to the parent MUST use `on_delete=models.PROTECT`. Otherwise a single click on the parent's Delete button silently destroys the entire history. CASCADE is appropriate ONLY when the child is structurally part of the parent (e.g., `MESWorkOrderOperation` rows under a `MESWorkOrder` — operations make no sense without their work order) AND there is no external regulatory reason to keep it.

**Why:** `CalibrationRecord.equipment` was originally `on_delete=CASCADE`. The `EquipmentDeleteView` had a `try / except ProtectedError` block (copy-pasted from a model that did use PROTECT) — but PROTECT was never set, so the `ProtectedError` never raised, the catch block was dead code, and equipment with a full calibration history was silently deleted. Calibration records vanished with it. ISO/regulatory auditors would not have a calibration audit trail to review for any retired instrument. Manual test TC-DELETE-07 caught it: the test EXPECTED the delete to be blocked with the toast `Cannot delete - equipment has calibration history.` but the equipment was deleted instead.

**How to apply:** when adding a new model with an FK, ask: "if the parent is deleted, is the child's history still useful or required?" If yes (audit, regulation, certification, payment, approval log, calibration log), use `PROTECT`. Add a `try / except ProtectedError` in the parent's delete view with a friendly toast naming the blocking child type. If the answer is no (purely structural composition), use CASCADE deliberately.

When auditing existing models, a quick grep:
```
grep -rn "on_delete=models.CASCADE" apps/
```
followed by reading each child model name aloud — if the name has "Record", "Log", "Approval", "Certificate", "Audit", "Payment", "Acknowledgement", or similar, double-check that CASCADE is intentional.

**Concrete example in repo:** [apps/qms/models.py — `CalibrationRecord.equipment`](../../apps/qms/models.py) — fixed 2026-05-01 in [apps/qms/migrations/0002_alter_calibrationrecord_equipment.py](../../apps/qms/migrations/0002_alter_calibrationrecord_equipment.py) (Module 7 manual-test walkthrough, BUG-02). Regression test in [apps/qms/tests/test_views_workflow.py — `test_equipment_with_calibration_history_protected_from_delete`](../../apps/qms/tests/test_views_workflow.py).

---

## L-18 — Signal handlers defined inside a factory function need `weak=False` or they get garbage-collected

**Rule:** When you connect signal handlers inside a factory / loop / closure, the inner functions live only in the factory's local scope. By default `signal.connect()` (and `@receiver`) hold the receiver as a **weak reference**, so once the factory returns the inner functions are garbage-collected and the signal **silently never fires**. Pass `weak=False` (or hoist the function to module scope and reference it explicitly) to keep the receiver alive.

**Why:** I built a `_mk_status_signals(model, action_prefix)` factory in `apps/procurement/signals.py` to register `pre_save` + `post_save` audit handlers for 7 status-tracked models in one DRY pattern. The handlers were defined inside the factory and decorated with `@receiver(...)`. The decorator connected them with the default `weak=True`. After each call the inner closures went out of scope, the weak-refs dropped, and **none** of the audit signals fired. Detection cost: 1 failed test (`test_creation_audited`) that asserted the audit row existed; debugging trail was straightforward once I dumped `post_save.receivers` and saw only the explicit module-level handlers were live (`procurement_grn_metric`, `procurement_iqc_metric`) — the 14 factory-registered handlers were missing. Module-level `@receiver(...)` works because the function name itself is a strong reference held by the module's `__dict__`.

**How to apply:** any `signal.connect(handler, sender=..., dispatch_uid=...)` call where `handler` is NOT a module-level name (factory-defined, closure-captured, decorator-stacked) MUST pass `weak=False`. Equivalent rule for `@receiver`: only safe at module scope. If you must register inside a function, either:
1. Connect with `weak=False`: `pre_save.connect(_pre, sender=model, weak=False, dispatch_uid='...')`.
2. Or hoist the handler to module scope and connect explicitly.

A drop-in unit-test guard: assert `dispatch_uid` is present in `post_save.receivers` after `apps.ready()`. Catches both this regression and any future "I deleted the handler but forgot to remove the connect call" drift.

**Concrete example in repo:** [apps/procurement/signals.py — `_mk_status_signals`](../../apps/procurement/signals.py) — fixed 2026-05-04 during initial Module 9 test-suite run. The fix replaced `@receiver(...)` decorators inside the factory with explicit `pre_save.connect(_pre, ..., weak=False, dispatch_uid=...)` + `post_save.connect(_post, ..., weak=False, dispatch_uid=...)` calls. Regression evidence: 70 procurement tests passed once `weak=False` was applied; before the fix, every test that asserted an audit row existed was failing.

---

## L-19 — Chained `|default:` filter on a nullable FK raises `VariableDoesNotExist` at render time

**Rule:** The template idiom `{{ obj.fk.get_full_name|default:obj.fk.username|default:"-" }}` looks ergonomic but is **broken when `obj.fk` is None**. Django's template engine evaluates *every* operand of `|default:` before deciding which one to use, and the second operand `obj.fk.username` triggers `getattr(None, 'username')` which raises and is not always silenced. Use `{% if obj.fk %}{{ obj.fk.get_full_name|default:obj.fk.username }}{% else %}-{% endif %}` (or just `{{ obj.fk|default:"-" }}` if `__str__` is acceptable).

**Why:** I shipped 9 occurrences of `{{ obj.user_fk.get_full_name|default:obj.user_fk.username|default:"-" }}` across 7 EAM templates. The first list page that hit the seeded MySQL DB with a row whose FK was `None` crashed with `VariableDoesNotExist: Failed lookup for key [username] in None` — which the test client surfaces as a 500. The *unit* tests didn't catch it because every fixture I wrote set the FK to a real user (e.g. `recorded_by=acme_admin`); the real production data path (auto-generated `PMSchedule` rows from `generate_pm_schedules` have `assignee=None` until someone assigns) hits the bug instantly. Pure unit tests are weak against this class of bug — only a manual walkthrough or a fixture that explicitly leaves FKs null catches it.

**How to apply:** every nullable FK render in a template gets the `{% if %}` wrap, not chained `|default:`. The two safe forms are:
1. **With name fallback (preferred for User FKs)**:
   ```django
   {% if obj.user_fk %}{{ obj.user_fk.get_full_name|default:obj.user_fk.username }}{% else %}-{% endif %}
   ```
2. **String fallback (when `__str__` is fine)**:
   ```django
   {{ obj.fk|default:"-" }}
   ```

When auditing existing templates, grep:
```
grep -rn "\.get_full_name|default:.*\.username" templates/
```
Every match needs to be wrapped. Also add a regression test that creates the parent row with the FK explicitly set to `None` and asserts the relevant page renders 200 — see [apps/eam/tests/test_views.py — TestNullableFKRendersGracefully](../../apps/eam/tests/test_views.py).

**Concrete example in repo:** Fixed 2026-05-06 in [.claude/manual-tests/eam-manual-test.md — BUG-01](../manual-tests/eam-manual-test.md) walkthrough. 9 EAM templates updated (`pm_schedules/list.html`, `pm_schedules/detail.html`, `mwo/detail.html`, `assets/detail.html`, `condition_points/detail.html`, `tools/detail.html`, `failure_predictions/detail.html`). Regression coverage in `TestNullableFKRendersGracefully` (4 tests). The same anti-pattern exists in `templates/mes/operators/detail.html:7` and `templates/mes/terminal/index.html:8` but is safe there because `operator.user` is a non-nullable FK — the Operator profile cannot exist without a user. Anywhere the FK is *nullable*, the chained-default pattern is unsafe.

---

## L-20 — A model that calls itself "immutable" in its docstring is NOT immutable until you write a manager + admin guard

**Rule:** If a model represents an audit trail or a regulated record (`ComplianceAuditLog`, `tenants.TenantAuditLog`, any `*Record` / `*Log` / `*History` table) and the docstring says "immutable" or "append-only", that's a wish, not a constraint. To enforce it, FOUR things must all happen:
1. **QuerySet override** — both `update()` and `delete()` raise `PermissionDenied` (so `.objects.filter(...).update()` and `.objects.all().delete()` both fail).
2. **Instance `delete()`** — raise `PermissionDenied` so `entry.delete()` fails.
3. **Instance `save()`** — raise `PermissionDenied` if `self.pk is not None` (allow the first insert, block every subsequent edit).
4. **Custom `ModelAdmin`** — override `has_add_permission = has_change_permission = has_delete_permission = lambda *a, **k: False`. Without this a Django superuser bypasses the model layer entirely from the admin UI.

If you forget step 4, the audit log is fully editable from `/admin/<app>/<model>/`. If you forget step 1, `QuerySet.update()` succeeds because Django bypasses `save()`. If you forget step 2, the parent CASCADE works but a stray `instance.delete()` in a view still wipes the row. If you forget step 3, anyone can mutate `meta`, `event`, or `performed_by` to rewrite history.

**Why:** `ComplianceAuditLog` shipped with the docstring "Immutable audit trail for compliance changes — no UI edit/delete." That comment was true *for the UI* (no edit/delete URL was wired) but false at every other layer: instance delete worked, queryset delete worked, queryset update worked, instance save with mutated fields worked, and the model was registered in admin with `admin.site.register(ComplianceAuditLog)` (default `ModelAdmin`, full edit + delete). Verified in shell: `entry.delete()` succeeded silently. For any tenant in a regulated industry (FDA 21 CFR Part 11, ISO 9001, GMP, GDP), this is a finding the auditor flags as non-compliant — the audit trail must be tamper-evident.

**How to apply:** for any new model whose role is to be a permanent record:
1. Subclass the parent's `Manager` and override `get_queryset()` to return a custom `QuerySet` whose `update()` and `delete()` raise `PermissionDenied`.
2. Add an `_ImmutableQuerySet` so `.objects` AND `.all_objects` (if you have one — `TenantAwareModel` does) both inherit the immutability.
3. Override the model's `save(*args, **kwargs)` to `raise PermissionDenied` if `self.pk is not None`; override `delete(*args, **kwargs)` to always raise.
4. Register in admin with a custom `ModelAdmin` that sets all three `has_*_permission` methods to return `False` and lists every field in `readonly_fields` for good measure.
5. Pin the contract with regression tests: instance.delete(), queryset.delete(), queryset.update(), instance.save() after pk — all four must raise `PermissionDenied`. Plus a positive test that the parent CASCADE still cleans up cleanly.

The CASCADE-from-parent path stays open by design: when the parent record is legitimately deleted (record-lifecycle, not tampering), the children go too. Django's cascade machinery bypasses the QuerySet you customised, so this Just Works without extra care.

**Concrete example in repo:** [apps/plm/models.py — `ComplianceAuditLog` + `_ImmutableTenantAuditManager` + `_ImmutableAllAuditManager` + `_ImmutableAuditQuerySet`](../../apps/plm/models.py), admin override at [apps/plm/admin.py — `ComplianceAuditLogAdmin`](../../apps/plm/admin.py), regression tests in [apps/plm/tests/test_compliance_audit_immutable.py](../../apps/plm/tests/test_compliance_audit_immutable.py) (6 tests including the parent-CASCADE positive case). Fixed 2026-05-09 (defect D-CR-01 from the SQA review of Module 13 / PLM compliance subset).

---

## L-21 — Status enums with a "stale" terminal state need an automatic transition, or they silently rot

**Rule:** When a model has a `status` enum that includes a terminal state representing the *passage of time* (e.g. `'expired'`, `'overdue'`, `'lapsed'`, `'late'`), there MUST be either a `post_save` signal or a periodic management command that flips affected rows when the trigger date passes. The choice is just "expired" / "compliant" — leaving it as a manual edit means the state never updates and the dashboard lies indefinitely. Worse: the regulator looking at the screen sees `Compliant ✓` for a record whose certificate expired 18 months ago.

The pattern that works:
1. Write a `manage.py <verb>_<noun>` command (`expire_compliance`, `mark_overdue_pms`, `lapse_certifications`).
2. Use `QuerySet.update()` with a conditional filter (`status='compliant', expiry_date__lt=today`) for race-safe atomic transitions; `update()` bypasses `pre_save`/`post_save`, so manually emit any audit-log row from inside the same `transaction.atomic()` block.
3. Idempotent — second run is a no-op because the conditional filter excludes already-flipped rows. Add an explicit "audit row already exists" check before creating the audit row to handle the case where someone manually re-set `status='compliant'` after the first run.
4. Support `--dry-run` so an operator can see what would change before committing.
5. Support `--tenant <slug>` for surgical re-runs after a partial failure.
6. Schedule daily via cron (Linux) / Task Scheduler (Windows) — and document the cadence in the README's Management Commands table.

**Why:** `ProductCompliance` shipped with `STATUS_CHOICES` including `'expired'`, but nothing wrote it. The shell-verifying call `ProductCompliance.objects.filter(status='compliant', expiry_date__lt=today).count()` returned 1 against the `acme` seed — and would return more for any tenant that's been in production a few months. The compliance dashboard's "Compliant" count and the per-record `Compliant ✓` badge both lied. The fix is the `expire_compliance` management command described above, not a UI button (which only fires on demand and gets forgotten).

A subtle related rule: any KPI or banner that shows "X expiring within N days" MUST also filter on `status='compliant'`. A record with `status='non_compliant'` whose expiry_date is in the next 30 days is not "expiring" — it's already broken; counting it inflates the banner and trains the user to ignore it. Defect D-CR-07 in the same review caught this on `expiring_soon_count`.

**How to apply:** when you add a `status` enum:
1. Identify which states are time-driven (`expired`, `overdue`, `lapsed`).
2. For each, write the matching scheduled command + tests at the same time as the model — not as "we'll add a cron later".
3. Add it to the README's Management Commands table with the recommended cadence.
4. Audit any KPI count that sums by date window — make sure it's status-scoped.

**Concrete example in repo:** [apps/plm/management/commands/expire_compliance.py](../../apps/plm/management/commands/expire_compliance.py) + [apps/plm/views.py — ComplianceListView (D-CR-07 fix)](../../apps/plm/views.py) + 7 regression tests in [apps/plm/tests/test_compliance_workflow.py](../../apps/plm/tests/test_compliance_workflow.py). Fixed 2026-05-09 (defects D-CR-02 + D-CR-07 from the SQA review of Module 13 / PLM compliance subset). Same pattern already exists in `apps/eam/management/commands/generate_pm_schedules.py` for the `'overdue'` state on `PMSchedule` — that one was right from the start.

---

## L-22 — File uploads need extension + content-type + size + magic-byte validation, not just FileField

**Rule:** A bare `forms.FileField()` (or `models.FileField()`) accepts ANY uploaded bytes up to Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` default. Renaming `evil.exe` to `evil.csv`, uploading a 50 MiB ZIP, or a polyglot CSV/PE binary all sail through silently. Any FileField wired to a user-facing form needs FOUR layers of validation:

1. **Extension allow-list** via `validators=[FileExtensionValidator(['csv', 'pdf', ...])]` declared on the field — Django checks before the form's `clean()` runs.
2. **Size cap** in a `clean_<field>()` method (don't rely on `DATA_UPLOAD_MAX_MEMORY_SIZE` alone — it's project-wide, not per-field, and chunked uploads can bypass it).
3. **Content-type allow-list** in the same `clean_<field>()` checking `f.content_type` against a small whitelist.
4. **Magic-byte sniff** for the first ~8 bytes — reject `MZ` (PE), `\x7fELF`, `PK\x03\x04` (ZIP), `\x89PNG`, `%PDF`, `\xff\xd8\xff` (JPEG) when the file claims to be CSV / text.

**Why:** D-03 in the Module 14 SQA review found `UtilityConsumptionImportForm.csv_file` had ZERO of these. A determined attacker could upload a 5 MB executable, store it on disk via the import code path, and probably hit it later via `/media/`. Even when the file is consumed and discarded, polyglot attacks can exfiltrate data to a downstream pipeline.

**How to apply:** every time you add a `FileField` (model OR form), implement all four layers in the same change. Capture the size cap as a module-level constant so it's easy to adjust per surface. Have a regression test that uploads a binary masquerading as the allowed extension and asserts the form is invalid.

**Concrete example in repo:** [apps/utility/forms.py — `UtilityConsumptionImportForm.clean_csv_file`](../../apps/utility/forms.py) and [apps/compliance/forms.py — `ComplianceDocumentForm.clean_attachment`](../../apps/compliance/forms.py) — both follow the same shape. Regression tests in [apps/utility/tests/test_security_extended.py](../../apps/utility/tests/test_security_extended.py) and [apps/compliance/tests/test_forms.py](../../apps/compliance/tests/test_forms.py). Introduced 2026-05-09 (defect D-03 from the Module 14 SQA review).

---

## L-23 — `except Exception: pass` in a write-path side-effect (audit, telemetry) is a silent regression generator

**Rule:** Any `try/except Exception: pass` block whose role is "best-effort side-effect that must never crash the parent write path" — audit emission, metric publish, cache invalidation — MUST log the exception at WARNING with `exc_info=True`. Otherwise the side-effect can silently rot for months and only surface during an audit / disaster.

**Why:** `apps/utility/signals.py::_audit` was wrapping `TenantAuditLog.objects.create(...)` in `except: pass`. The keyword argument was `payload=` but the model field is `meta=`. Every audit row write had been failing with `TypeError` since module ship — and nobody knew, because `pass` swallowed it. The Module 14 D-09 fix added `logger.warning(..., exc_info=True)`, which immediately surfaced the latent bug as a stacktrace in the test output. Once you can SEE the exception, you can fix it; while it's swallowed, it's structurally invisible.

**How to apply:** when writing best-effort side-effects:

```python
try:
    do_the_side_effect(...)
except Exception as exc:
    logger.warning(
        '<module> <action> failed: <key context> err=%s',
        exc, exc_info=True,
    )
```

The bare `pass` form is acceptable ONLY when the exception class is narrow and the failure mode is well-understood (e.g. `except ImportError: pass` for an optional dependency). For `except Exception:` the answer is always: log it. Add a regression test that monkey-patches the side-effect to raise and asserts the warning was logged via `caplog`.

**Concrete example in repo:** [apps/utility/signals.py — `_audit`](../../apps/utility/signals.py) and [apps/compliance/signals.py — `_audit`](../../apps/compliance/signals.py). Regression test [apps/utility/tests/test_audit_log.py — `test_audit_emit_failure_logs_warning`](../../apps/utility/tests/test_audit_log.py). Surfaced 2026-05-09 while implementing defect D-09 from the Module 14 SQA review — patching `pass` → `logger.warning` immediately exposed a latent `payload=` vs `meta=` kwarg mismatch that had been silent since module ship.

---

## L-24 — A SHA-256 hash chain across audit rows is half a feature without a backfill data migration

**Rule:** When you add `prev_hash` + `this_hash` columns to an existing audit-log table for FDA 21 CFR Part 11 / ISO 9001 tamper-evidence, you MUST also ship a `RunPython` data migration that walks the existing rows in chronological order and computes the chain. Otherwise the verifier reports every pre-migration row as broken — the chain only "starts" at the moment the column is added.

**Why:** Adding the columns alone gives you tamper-evidence for new rows ONLY. Pre-existing audit data is left with empty `prev_hash` + `this_hash`, which (a) means the verifier flags every legacy row as `prev_hash_mismatch` (false positive flood), and (b) leaves the historical record unverifiable — defeating the regulatory purpose. An auditor reviewing 12 months of pre-existing audit data needs the chain to begin at row 0, not at the migration date.

**Mechanics matter for an immutable model:** `apps.get_model('plm', 'ComplianceAuditLog')` returns the historical model class WITHOUT the immutable manager / `save()` override. The data migration can therefore use `objects.update(...)` to write `prev_hash` + `this_hash` directly — at runtime the same write would raise `PermissionDenied`, but inside the migration's historical-model context, the override is bypassed cleanly. Hash both the canonical payload AND the previous row's `this_hash` (same algorithm as the runtime helper) — duplicate the helper logic inside the migration so the migration stays runnable even if the production helper changes shape later.

**How to apply:** every immutable-audit-log schema change that adds chain columns ships TWO migrations:
  1. `XXXX_add_prev_this_hash.py` — `AddField` for both columns, `default=''`, `blank=True`.
  2. `XXXX_backfill_audit_chain.py` — `RunPython(forwards, backwards)` where `forwards` walks `Tenant.objects.all()`, then for each tenant walks the audit rows in chronological order computing prev/this and persisting via `objects.update()`. `backwards` blanks both columns.

The second migration MUST list `('core', '0001_initial')` in `dependencies` so the historical Tenant model is available even when running migrations from scratch. Verify by running `verify_*_audit_chain(tenant)` against seeded data after both migrations apply — `ok=True, broken=[]` confirms the chain.

**Concrete example in repo:** [apps/tenants/migrations/0002_…_prev_hash_…_this_hash.py](../../apps/tenants/migrations) + [apps/tenants/migrations/0003_backfill_audit_chain.py](../../apps/tenants/migrations/0003_backfill_audit_chain.py); analogous pair for [apps/plm/migrations/0005_…](../../apps/plm/migrations) + [0006_backfill_compliance_audit_chain.py](../../apps/plm/migrations/0006_backfill_compliance_audit_chain.py). Verifier services at [apps/tenants/services/audit_chain.py](../../apps/tenants/services/audit_chain.py) + [apps/plm/services/audit_chain.py](../../apps/plm/services/audit_chain.py). Shipped 2026-05-10 (Phase C closeout of Module 13 SQA review). Confirmed across all 3 seeded tenants: 823 + 49 = 872 rows backfilled, 0 broken.

---

## L-25 — When wiring a cross-module signal hook, the hard part is field names — read the actual model first

**Rule:** Before writing a `post_save` receiver that fires on a model in another app, READ the target app's `models.py` and confirm the field names you reference. Apps that look interchangeable from their domain (NCR, IncidentReport, Lot, Movement) often have surprising field-name drift across modules — `severity` vs `risk_level`, `detected_at` vs `reported_at`, `lot_number` vs `code`, `quantity` vs `qty` vs `planned_qty` vs `quantity_to_build`. Guessing costs an hour of failing tests + traceback decoding; reading costs 60 seconds of `grep -n class`.

**Why:** While shipping Phase C the QMS NCR hook used `instance.detected_at` (matched no field), the MES context builder used `BillOfMaterials(kind=...)` (real field is `bom_type`), `Routing(name='R')` (real field requires `routing_number`), `ProductionOrder(planned_qty=10)` (real field is `quantity`), and `MESWorkOrder(planned_qty=10)` (real field is `quantity_to_build` and the model also requires `product` + `wo_number`). The signals were correct in spirit but had to be re-tested 4 times because each hidden field-name mismatch re-surfaced as a `TypeError: Foo() got unexpected keyword arguments: 'X'` only when the signal fired. **Each retry costs ~90 seconds of pytest run + 60 seconds of inspection — five field-name mistakes added 12 min of cycle time before any real bug showed up.**

**How to apply:** when the signal handler or test fixture references another app's model, paste this one-liner FIRST:
```bash
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.qms.models import NonConformanceReport
print([f.name for f in NonConformanceReport._meta.fields if not f.is_relation or f.many_to_one])
"
```
Then write code against the printed field list, not the docstring or the dashboard label or your memory. For test fixtures, ALSO mirror the canonical fixture pattern from the target app's `tests/conftest.py` (e.g., `apps/mes/tests/conftest.py` for MES models) — those are battle-tested and pre-include all the required-but-default fields you'd otherwise miss.

**Concrete example in repo:** Phase C of [.claude/tasks/compliance_module13_plan.md](compliance_module13_plan.md) — five field-name retries logged in commit history for `apps/compliance/tests/test_signals.py`. The fix pattern is now codified in the test file's `_build_mes_context()` helper docstring, which names every "did NOT match my guess" field for future reference.

---

## L-26 — When extending an existing model's denorm fields, render the new state in the template at the same time

**Rule:** Adding a denormalized count column (`post_recall_movement_count`, `last_leak_at`, `recovery_pct`, etc.) is half the feature. The other half is making it visible — the operator who sees a stale "Affected: 5 / Recovered: 0" today won't notice the new "Movements after recall: ⚠ 3" warning unless you put it on the page in the same change. Otherwise the field exists but the bug it surfaces stays invisible.

**Why:** Phase C added `RecallAffectedLot.post_recall_movement_count` + `last_leak_at` plus the `inventory.StockMovement.post_save` hook that increments them. Without also extending the recall detail template's affected-lots table, the entire signal would be silent — leak counts would be incrementing in the database but no operator would ever see them. The signal becomes invisible infrastructure rather than a UX feature, and the regression test that asserts the count incremented passes while the actual workflow regression (operator missing a leak) goes uncaught.

**How to apply:** every denorm field added to a model gets:
  1. A column or badge in the relevant list / detail template the SAME turn.
  2. A row-level visual cue (yellow row tint, badge, alert banner) when the value crosses a threshold (`> 0`, `expiring_soon`, `overdue`).
  3. A regression test that hits the page (HTTP GET) and asserts the visual cue is present in the response body — not just that the denorm field has the right value.

The order of work is: model field → migration → signal → service → template → view test that asserts the rendered cue. If you stop at "service writes the denorm correctly", you've shipped half a feature.

**Concrete example in repo:** [apps/compliance/models.py — `RecallAffectedLot.has_leaks` property](../../apps/compliance/models.py) + [templates/compliance/recalls/detail.html — yellow row + warning banner](../../templates/compliance/recalls/detail.html) + [apps/compliance/tests/test_signals.py — `test_outbound_movement_on_recalled_lot_increments_leak_count`](../../apps/compliance/tests/test_signals.py). Shipped 2026-05-10 as Phase C C.7.
