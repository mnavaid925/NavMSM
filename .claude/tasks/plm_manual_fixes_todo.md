# PLM manual-test follow-up fixes

Source: `.claude/manual-tests/plm-manual-test.md` Bug-candidate flags TC-PAGE-PROD-04, TC-PAGE-ECO-01, TC-INT-05.

## Plan

- [x] **1. Pagination filter retention (Bug 1)**
  - Create `apps/core/templatetags/__init__.py`
  - Create `apps/core/templatetags/url_tags.py` with `querystring_replace` tag (mirrors Django 5.1's built-in `{% querystring %}`; we are on Django 4.2 so we add our own)
  - Add `'apps.core'` to INSTALLED_APPS check — already installed (templatetags auto-discovered)
  - Update pagination block in each of the 6 PLM list templates to use the tag:
    - `templates/plm/categories/list.html`
    - `templates/plm/products/list.html`
    - `templates/plm/eco/list.html`
    - `templates/plm/cad/list.html`
    - `templates/plm/compliance/list.html`
    - `templates/plm/npi/list.html`

- [x] **2. ProductDeleteView ProtectedError (Bug 2)**
  - In `apps/plm/views.py` `ProductDeleteView.post()`, wrap `product.delete()` in `try/except ProtectedError` and emit `messages.error(...)` then redirect to detail (consistent with how `CategoryDeleteView` handles its own protection check at `views.py:143-147`).
  - Import `ProtectedError` from `django.db.models.deletion`.

- [x] **3. Verify**
  - Re-read each edited file (Edit tool errors if changes don't apply, so reading is only for sanity-check on the new template tag wiring).
  - Per CLAUDE.md: do NOT update README — these are bug fixes, not new modules/routes/commands/env vars/seed fixtures. (README rule is for additive changes.)

## Out of scope (deliberate)

- TC-NEG-16 (product image size limit) — flagged as "worth documenting" not a confirmed bug. Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` already provides a default cap. Skipping per "No Laziness" / "Minimal Impact" rule — don't fix what isn't broken.
- Other PLM modules' pagination is fixed by Bug 1 (it's a project-wide problem, but the user's request scope is PLM).

## Files changed

| File | Change | Reason |
|---|---|---|
| `apps/core/templatetags/__init__.py` | new (empty) | Django requires this for tag discovery |
| `apps/core/templatetags/url_tags.py` | new | Adds `querystring_replace` |
| `templates/plm/categories/list.html` | edit pagination block | Bug 1 |
| `templates/plm/products/list.html` | edit pagination block | Bug 1 |
| `templates/plm/eco/list.html` | edit pagination block | Bug 1 |
| `templates/plm/cad/list.html` | edit pagination block | Bug 1 |
| `templates/plm/compliance/list.html` | edit pagination block | Bug 1 |
| `templates/plm/npi/list.html` | edit pagination block | Bug 1 |
| `apps/plm/views.py` | catch `ProtectedError` in `ProductDeleteView` | Bug 2 |
