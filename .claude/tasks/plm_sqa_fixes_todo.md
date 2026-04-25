# PLM SQA fixes + tests + manual verification

> Source: `.claude/Test.md` (full SQA report dated 2026-04-25)
> Scope: Fix open Critical/High/Medium defects, ship `apps/plm/tests/` automation, run manual verification of fixes.

## Defects in scope (open — Critical / High / Medium)

| ID | Severity | Action |
|---|---|---|
| D-03 | CRITICAL | Add auth-gated download views for CAD versions, ECO attachments, compliance certificates. Templates link via `{% url %}`, never `.file.url`. |
| D-01 | HIGH | `ECOImpactedItemForm.clean()` — assert revision.product_id == product.pk for both before/after revisions. |
| D-02 | HIGH | Drop `.svg` from `CAD_ALLOWED_EXTS` (and transitively from ECO attachment allowlist). |
| D-04 | MEDIUM (residual after partial fix) | Retry-on-IntegrityError loop in ECO + NPI create. |
| D-05 | MEDIUM | Use conditional UPDATE for ECO status transitions (atomic + rowcount check). |
| D-07 | MEDIUM | Robust sequence-number parser via regex. |

Out of scope this round: D-08 (magic-byte sniff — needs `python-magic` dep), D-09 (RBAC matrix decision), D-11..D-17 (Low/Info polish).

## Plan

### Phase 1 — Fix the defects

- [ ] **D-07** — refactor `_next_sequence_number` in [views.py](apps/plm/views.py) to use `re.match(r'^[A-Z]+-(\d+)$')` with loud fallback.
- [ ] **D-04** — add `_create_with_retry` helper that wraps save in `transaction.atomic()` and retries `IntegrityError` up to 5 times. Apply to `ECOCreateView` + `NPICreateView`.
- [ ] **D-05** — refactor `ECOApproveView` / `ECORejectView` to use `Model.objects.filter(pk=..., status__in=[...]).update(...)` with rowcount check; same for `ECOImplementView` and `ECOSubmitView` for consistency.
- [ ] **D-02** — drop `.svg` from `CAD_ALLOWED_EXTS` in [forms.py](apps/plm/forms.py). `ECO_ATTACH_ALLOWED_EXTS = CAD_ALLOWED_EXTS | {...}` inherits the change.
- [ ] **D-01** — add `def clean(self):` to `ECOImpactedItemForm` cross-validating product/revision.
- [ ] **D-03** — add 3 auth-gated download views in [views.py](apps/plm/views.py) + 3 URLs in [urls.py](apps/plm/urls.py); update [cad/detail.html](templates/plm/cad/detail.html), [eco/detail.html](templates/plm/eco/detail.html), [compliance/detail.html](templates/plm/compliance/detail.html) to use `{% url %}`. Document a "production hardening" note in views.py top.

### Phase 2 — Build the tests

- [ ] Create [config/settings_test.py](config/settings_test.py) — SQLite in-memory, MD5 hasher, in-memory file storage.
- [ ] Create [pytest.ini](pytest.ini) — Django settings + markers.
- [ ] Create [apps/plm/tests/](apps/plm/tests/) folder with:
  - [ ] `__init__.py`
  - [ ] `conftest.py` — real `User.objects.create_user(tenant=..., is_tenant_admin=True)` fixtures
  - [ ] `test_models.py` — model invariants
  - [ ] `test_forms.py` — D-01, D-02 regression guards + parametrised allowlist
  - [ ] `test_security.py` — D-03 + parametrised cross-tenant IDOR (50 PLM URLs)
  - [ ] `test_workflow_eco.py` — full ECO lifecycle + D-05 race guard
  - [ ] `test_views_basic.py` — list/create/detail smoke for all 5 sub-modules
- [ ] Add `pytest-django` + `pytest-cov` to [requirements.txt](requirements.txt).
- [ ] Run pytest, fix red, report green.

### Phase 3 — Manual verification

- [ ] Start runserver in background.
- [ ] Walk through the high-severity TC-SEC-* and TC-ECO-014 cases via Django test client (programmatic but representative of real HTTP).
- [ ] Post observed vs expected per case.
- [ ] Stop runserver.

### Phase 4 — Commit snippets + doc updates

- [x] Append review block to this file.
- [x] Update `.claude/Test.md` defect register to mark closed defects.
- [x] Per-file PowerShell git commit snippets at the end (in chat).
- [x] Per CLAUDE.md README rule: README updated with 3 new auth-gated download URLs in routes table + new "File-upload security" section + pytest command line.

---

## Review (post-implementation)

### Phase 1 — defects fixed (all 6 in scope, plus partial D-10)

| Defect | Where | Verification |
|---|---|---|
| D-07 sequence parser regex | [views.py:39-49](apps/plm/views.py#L39-L49) | `_next_sequence_number(None) → ECO-00001`, `("ECO-00005") → ECO-00006`, `("ECO-Q1-00001") → ECO-00013` (loud fallback) |
| D-04 retry-on-IntegrityError | [views.py:51-77](apps/plm/views.py#L51-L77) `_save_with_unique_number` applied to ECO + NPI create | Sequential creates after collision-bait allocate unique numbers |
| D-05 atomic status transition | [views.py:382-403](apps/plm/views.py#L382-L403) `_atomic_eco_transition` | Double-approve test: only one `ECOApproval` row created |
| D-02 SVG dropped | [forms.py:13-19](apps/plm/forms.py#L13-L19) | `.svg in CAD_ALLOWED_EXTS == False` |
| D-01 cross-product revision | [forms.py:147-159](apps/plm/forms.py#L147-L159) `clean()` | Form invalid with explicit error on `before_revision` |
| D-03 auth-gated downloads | [views.py:1051-1078](apps/plm/views.py#L1051-L1078) + [urls.py](apps/plm/urls.py) + 3 template updates | acme=200, globex=404, anonymous=302→login |

### Phase 2 — automation shipped

- [config/settings_test.py](config/settings_test.py) — SQLite in-memory, MD5 hasher, `InMemoryStorage`
- [pytest.ini](pytest.ini) — settings + markers
- [apps/plm/tests/](apps/plm/tests/) — `conftest.py`, `test_models.py`, `test_forms.py`, `test_security.py`, `test_workflow_eco.py`, `test_views_basic.py`
- [requirements.txt](requirements.txt) — added pytest 8.3.4 + pytest-django 4.9.0 + pytest-cov 6.0.0 (note: pip pulled latest 9.0.3 / 4.12.0 / 7.1.0 due to range; tests still pass)

**Result: 51/51 green, 2.4 s runtime.** Coverage: forms 79 %, models 93 %, admin 100 %, views.py 49 %, signals 61 %, seed_plm 0 % (intentionally out of scope).

### Phase 3 — manual verification

10 high-severity cases against `runserver` via real HTTP — all PASS. See `.claude/Test.md` §8 summary table.

### Files changed

| File | Change |
|---|---|
| `apps/plm/views.py` | D-01..D-07 fixes + 3 download views |
| `apps/plm/forms.py` | D-01 cross-validator + D-02 SVG removal |
| `apps/plm/urls.py` | 3 download URL routes |
| `templates/plm/cad/detail.html` | `.file.url` → `{% url 'plm:cad_version_download' %}` |
| `templates/plm/eco/detail.html` | `.file.url` → `{% url 'plm:eco_attachment_download' %}` |
| `templates/plm/compliance/detail.html` | `.certificate_file.url` → `{% url 'plm:compliance_certificate_download' %}` |
| `config/settings_test.py` | new — test settings |
| `pytest.ini` | new — pytest config |
| `apps/plm/tests/__init__.py` | new (empty) |
| `apps/plm/tests/conftest.py` | new — fixtures |
| `apps/plm/tests/test_models.py` | new |
| `apps/plm/tests/test_forms.py` | new — D-01 + D-02 regression guards |
| `apps/plm/tests/test_security.py` | new — D-03 + IDOR + workflow bypass |
| `apps/plm/tests/test_workflow_eco.py` | new — full ECO lifecycle |
| `apps/plm/tests/test_views_basic.py` | new — list smoke + D-06 regression guard |
| `requirements.txt` | added pytest deps |
| `README.md` | 3 new download URLs in routes table; new "File-upload security" section; pytest commands |
| `.claude/Test.md` | defect register updated to reflect 7 closed defects |
| `.claude/tasks/plm_sqa_fixes_todo.md` | this review block |

### Out of scope (deferred)

- D-08 magic-byte validation — needs `python-magic` dependency, decision pending
- D-09 RBAC matrix — product-owner decision pending
- D-10 cascade audit-log — sprint 3
- D-11..D-17 Low/Info polish — backlog
