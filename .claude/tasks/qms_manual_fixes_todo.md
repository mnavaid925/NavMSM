# QMS — Manual-Test Fix Plan (2026-05-01)

> Smoke pass via [.claude/manual-tests/qms_runner.py](.claude/manual-tests/qms_runner.py) on 2026-05-01 surfaced 2 defects on the seeded Acme tenant. Both are caught BEFORE shipping (Module 7 was built earlier today, this is the first manual walk-through).

## Defect log

| Bug | TC | Severity | Surface | Root cause | Fix |
|---|---|---|---|---|---|
| BUG-01 | TC-LIST-04 | Medium | `/qms/equipment/` row coloring | `_propagate_calibration_to_equipment` signal fires after every seeded `CalibrationRecord` and overwrites the equipment's seeder-hand-picked `last_calibrated_at` / `next_due_at`. Result: every row ends up with `next_due_at` months in the future, so no row ever hits the red (overdue) or yellow (≤7d) tint that the manual test expects. | After `_seed_calibrations`, do an explicit `MeasurementEquipment.all_objects.filter(...).update(last_calibrated_at=..., next_due_at=...)` on equipment 1 (due in 5 days) and equipment 2 (overdue). `update()` bypasses signals — preserves the deliberate test fixture. |
| BUG-02 | TC-DELETE-07 | **High — data integrity** | `MeasurementEquipment` delete | `CalibrationRecord.equipment = ForeignKey(MeasurementEquipment, on_delete=CASCADE)` — deleting an instrument silently destroys its calibration history. The view at [apps/qms/views.py:1639](apps/qms/views.py#L1639) tries `except ProtectedError`, but PROTECT is never set so the catch block is dead code. Calibration audit trail (regulatory evidence) can be wiped by a single click. | Change `CalibrationRecord.equipment` to `on_delete=models.PROTECT`. Generate migration. View's `ProtectedError` handler is now actually reached. |

Two surfaces touched:

1. [apps/qms/management/commands/seed_qms.py](apps/qms/management/commands/seed_qms.py) — pin equipment 1 + 2 to known due dates after calibrations have run.
2. [apps/qms/models.py](apps/qms/models.py) — `CalibrationRecord.equipment` from `CASCADE` to `PROTECT` + new migration.

## Implementation steps

- [ ] Fix model: `CalibrationRecord.equipment` → `on_delete=models.PROTECT`
- [ ] Run `makemigrations qms` → `0002_protect_equipment_on_calibration.py`
- [ ] Apply migration to MySQL
- [ ] Fix seeder: after `_seed_calibrations`, push deterministic due dates onto equipment 1 (due in 5 days) and equipment 2 (overdue 15 days) via `.update()`
- [ ] Re-flush + re-seed: `python manage.py seed_qms --flush`
- [ ] Re-run smoke runner, expect 0 bugs
- [ ] Re-run pytest suite, expect 85 still passing
- [ ] Add a regression test for BUG-02 (equipment with cal history protected from delete)

## What I am NOT changing

- The signal itself remains correct. `_propagate_calibration_to_equipment` is supposed to fire when a real user files a calibration. The seeder is the special case (it's bulk-loading pre-aged equipment), not the signal.
- The `ProtectedError` handler in the view stays as-is — once PROTECT is set, the existing `except ProtectedError` is the right pattern.

## Lessons

L-16 candidate (will write into `.claude/tasks/lessons.md` after the fix lands): "When a `post_save` signal denormalises data onto the parent model, seeders that need to seed deliberate denormalised state on the parent must use `.update()` (which bypasses signals) AFTER the children have been bulk-created. Setting the parent's denorm fields BEFORE creating the children — the obvious order — is undone by the signal."

L-17 candidate: "FK `on_delete` must be considered an audit-trail decision, not just a referential-integrity decision. Workflow / regulated / log-style child models (CalibrationRecord, AuditLog, ApprovalDecision, etc.) should default to PROTECT on the parent FK so cascade-delete cannot silently erase the history. Use CASCADE only when the child is genuinely a structural part of the parent (e.g., MESWorkOrderOperation rows under a MESWorkOrder)."
