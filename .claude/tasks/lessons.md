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
