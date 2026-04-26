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
