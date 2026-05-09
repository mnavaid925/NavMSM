# Compliance & Regulatory — defect fixes + automation + Module 13 build-out

**Created:** 2026-05-09
**Trigger:** user request after `/sqa-review 13. Compliance & Regulatory Management` — "Fix all defects. Build the automation. Build Module 13 properly".
**Origin report:** previously written to `.claude/Test.md` (overwritten upstream by Module 14 pass — defect findings retained in this plan).

---

## Phased execution

### Phase A — PLM compliance subset: defect fixes + regression automation (THIS SESSION)

Fixes all 6 verified defects in the PLM compliance subset, then ships the §5 automation suite as a regression contract.

| # | Task | Files touched | Status |
|---|---|---|---|
| A.1 | **D-CR-04** — `ProductComplianceForm.clean()` rejects `expiry_date < issued_date` | [apps/plm/forms.py](../../apps/plm/forms.py) | [ ] |
| A.2 | **D-CR-05** — `ProductComplianceForm.clean()` enforces `unique_together (tenant, product, standard)` (lessons.md L-01) | [apps/plm/forms.py](../../apps/plm/forms.py) | [ ] |
| A.3 | **D-CR-07** — `ComplianceListView.get_context_data` adds `status='compliant'` filter to `expiring_soon_count` | [apps/plm/views.py](../../apps/plm/views.py) | [ ] |
| A.4 | **D-CR-08** — template footer "pdf, png, jpg, **jpeg**, zip" | [templates/plm/compliance/form.html](../../templates/plm/compliance/form.html) | [ ] |
| A.5 | **D-CR-01** — `ComplianceAuditLog` custom Manager raises `PermissionDenied` on `delete()`/`update()`; instance `delete()` + `save()` overrides; `ComplianceAuditLogAdmin(has_add=has_change=has_delete=False)` | [apps/plm/models.py](../../apps/plm/models.py), [apps/plm/admin.py](../../apps/plm/admin.py) | [ ] |
| A.6 | **D-CR-02** — `apps/plm/management/commands/expire_compliance.py` (idempotent: `compliant + expiry_date < today` → `expired`; emits `ComplianceAuditLog(event='expired')` via signal) | new file | [ ] |
| A.7 | Test factories — `ComplianceStandardFactory`, `ProductComplianceFactory` | new [apps/plm/tests/factories.py](../../apps/plm/tests/factories.py) | [ ] |
| A.8 | 7 `test_compliance_*.py` regression files | new in [apps/plm/tests/](../../apps/plm/tests/) | [ ] |
| A.9 | Run pytest, fix any failures | n/a | [ ] |
| A.10 | README — add notes for `expire_compliance` cmd + immutability hardening | [README.md](../../README.md) | [ ] |
| A.11 | lessons.md — add L-20 (audit log immutability pattern), L-21 (status auto-expire pattern), L-22 (FDA 21 CFR Part 11 first-step) | [.claude/tasks/lessons.md](lessons.md) | [ ] |
| A.12 | Add Review section here with verified outcome | this file | [ ] |

**Phase A exit criteria** — all 6 defects pass shell reproduction (now-fixed), `pytest apps/plm/tests/test_compliance_*.py` green, README + lessons updated, commit snippets handed to user.

---

### Phase B — Module 13 (`apps/compliance/`) MVP build-out (NEXT SESSION, AFTER USER APPROVAL)

Multi-day epic. Scaffolds the dedicated `apps/compliance/` app and ships the 5 sub-modules per [MSM.md §13](../../MSM.md). Recommend splitting into 5 sub-phases, one per sub-module. **DO NOT START until Phase A is reviewed and accepted.**

| Sub-phase | Sub-module | Models / services | Estimated files |
|---|---|---|---|
| B.1 | EHS — Environmental Health & Safety | `IncidentReport`, `RiskAssessment`, `SafetyAuditChecklist`, `SafetyAuditFinding`, optional `EHS-Asset` link | ~8 models + 12 views + 12 templates + tests = **~40 files** |
| B.2 | Regulatory Document Control + e-Signatures (FDA 21 CFR Part 11) | `RegulatoryDocument`, `RegulatoryDocumentVersion`, `ESignature` (target_content_type + target_id + signer + sha256_payload + password_reauth_at + intent), bind to `CADDocumentVersion.release()` and `ProductCompliance` status transitions | ~5 models + 10 views + 10 templates + signal hooks + tests = **~30 files** |
| B.3 | Audit Trail & Data Integrity — SHA-256 hash chain | Migrate `ComplianceAuditLog` + `tenants.TenantAuditLog` to add `prev_hash`, `this_hash`; verifier service; UI badge "audit chain verified ✓" | ~3 services + 2 migrations + tests = **~15 files** |
| B.4 | Waste & Emission Tracking | `HazardousMaterial` registry, `WasteManifest` (generator/transporter/disposal_facility), `EnvironmentalIncident` (spill / release), `EmissionPermit` | ~5 models + 8 views + 8 templates + tests = **~25 files** |
| B.5 | Recall & Traceability | `RecallNotice` (tenant + scope_type + scope_value + reason + severity + status), `RecallScope` (lot / batch / serial / customer / date_range), recall sweep service over `inventory.StockItem`, customer notification template | ~4 models + 8 views + 8 templates + service + tests = **~25 files** |
| B.6 | Cross-cutting | `apps/compliance/{__init__, apps, urls, admin, signals, tests/conftest, management/commands/seed_compliance}.py`, sidebar nav link, dashboard, README + MSM.md updates | ~15 files |

**Phase B total estimate**: ~150 new files, ~6,000 LoC. Realistically 5-8 focused sessions.

---

## Verification protocol (Phase A)

For each defect fix:
1. Re-run the original shell reproduction → confirm the failure path is now blocked.
2. Run the matching regression test → confirm green.
3. Take a screenshot equivalent (terminal output) of before / after → record in this file's Review section.

---

## Risk register (Phase A)

| Risk | Mitigation |
|---|---|
| Migration required for ComplianceAuditLog Manager — could it lock the table during deploy? | No schema change; pure Manager + admin override. No migration needed. |
| `expire_compliance` running concurrently with manual edits → race | Use `QuerySet.update()` with conditional `status='compliant'` filter (lessons.md L-13 pattern); idempotent. |
| Test for D-CR-04 currently asserts `is_valid()=True` (test_views_basic.py) — would break? | No existing test asserts the inverted-date case. Safe to add the new clean(). Verified by `grep -n 'expiry_date' apps/plm/tests/`. |
| Render of compliance_create form from `test_views_basic.py:test_render_200` will hit the new `clean()` only on POST — no break | Confirmed. |

---

## Review (filled in after Phase A completes)

- [ ] Date completed:
- [ ] Defects fixed: D-CR-01, D-CR-02, D-CR-04, D-CR-05, D-CR-07, D-CR-08
- [ ] Tests added: factories.py + 7 test files
- [ ] Test suite runtime:
- [ ] Defects re-verified blocked in shell:
- [ ] README + lessons.md updated:
- [ ] Commit snippets handed to user:
- [ ] User approval received to start Phase B?
