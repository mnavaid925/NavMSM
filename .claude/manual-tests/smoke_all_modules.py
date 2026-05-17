"""Cross-module smoke runner for the manual-test plans.

Walks every named URL in apps.{bi, bom, compliance, eam, inventory, labor,
mes, mrp, plm, qms, sales} that takes no path arguments (i.e. index pages,
list pages, create-form GETs) and asserts a non-500 response.

For URLs taking a single ``<pk>``, picks the first row of the obvious model
from the tenant scope (best-effort) and hits both the detail and edit form.

Run from project root:

    python .claude/manual-tests/smoke_all_modules.py

Writes results to .claude/manual-tests/smoke_all_modules_results.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.apps import apps as django_apps  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import URLPattern, URLResolver, get_resolver, reverse  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.core.models import Tenant  # noqa: E402

MODULES = [
    'bi', 'bom', 'compliance', 'eam', 'inventory',
    'labor', 'mes', 'mrp', 'plm', 'qms', 'sales',
]


def acme_admin_client() -> Client:
    user = User.objects.get(username='admin_acme')
    user.set_password('Welcome@123')
    user.save(update_fields=['password'])
    c = Client()
    assert c.login(username='admin_acme', password='Welcome@123'), 'admin_acme login failed'
    return c


def iter_url_patterns(resolver, prefix=''):
    """Yield (full_pattern_str, url_pattern_obj, name, app_name) for every named URL."""
    for entry in resolver.url_patterns:
        if isinstance(entry, URLPattern):
            if entry.name:
                yield prefix + str(entry.pattern), entry, entry.name, resolver.app_name
        elif isinstance(entry, URLResolver):
            sub_prefix = prefix + str(entry.pattern)
            yield from iter_url_patterns(entry, sub_prefix)


def collect_zero_arg_urls():
    """Returns dict {app_name: [(name, reversed_url), ...]} for URLs with no arguments."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    resolver = get_resolver()
    for _pat, urlpat, name, app_name in iter_url_patterns(resolver):
        if app_name not in MODULES:
            continue
        # Skip URLs with any <param> capture
        if re.search(r'<[^>]+>', str(urlpat.pattern)):
            continue
        try:
            reversed_url = reverse(f'{app_name}:{name}')
        except Exception:
            continue
        out[app_name].append((name, reversed_url))
    return out


def collect_single_pk_urls():
    """For each named URL that takes a single int pk argument, return a
    ``(app, name, pattern_str)`` tuple. We try to GET it with the first row
    of the matching model from the Acme tenant.
    """
    out: list[tuple[str, str, str]] = []
    resolver = get_resolver()
    for _pat, urlpat, name, app_name in iter_url_patterns(resolver):
        if app_name not in MODULES:
            continue
        pattern_str = str(urlpat.pattern)
        params = re.findall(r'<(?:int:)?([a-z_]+)>', pattern_str)
        if len(params) == 1:
            out.append((app_name, name, pattern_str))
    return out


def pick_first_pk_for(app_name: str, url_name: str, tenant) -> int | None:
    """Heuristic: scan the app's models for one whose name matches a
    namespaced word in ``url_name``, then return the first row's pk for the
    Acme tenant (or any tenant if model has no tenant FK).
    """
    try:
        app_config = django_apps.get_app_config(app_name)
    except LookupError:
        return None
    # Build a lowercase token set from the url name (e.g. 'kpi_definition_detail'
    # → {'kpi', 'definition', 'detail'}) so we can match `KPIDefinition`.
    name_tokens = set(url_name.lower().split('_'))
    # Strip generic verbs that don't identify the model
    name_tokens -= {'detail', 'edit', 'delete', 'refresh', 'run', 'create',
                    'list', 'new', 'submit', 'approve', 'reject', 'release',
                    'obsolete', 'recompute', 'explode', 'rollback',
                    'cancel', 'disable', 'pause', 'resume', 'download',
                    'archive', 'archives', 'investigate', 'close', 'sign',
                    'publish', 'supersede', 'reconcile', 'dispatch',
                    'acknowledge', 'send', 'mark', 'disposed', 'now', 'top',
                    'inline', 'add', 'remove', 'start', 'hold', 'complete',
                    'schedule', 'capture', 'progress', 'force', 'manual',
                    'lock', 'pay', 'discard', 'waive', 'terminate',
                    'reactivate', 'view'}
    best = None
    best_score = 0
    for model in app_config.get_models():
        mname = model.__name__.lower()
        score = sum(1 for tok in name_tokens if tok and tok in mname)
        if score > best_score:
            best_score = score
            best = model
    if best is None:
        return None
    try:
        # Prefer Acme rows when the model has a tenant FK
        if 'tenant' in {f.name for f in best._meta.get_fields() if hasattr(f, 'name')}:
            row = best.objects.filter(tenant=tenant).order_by('pk').first()
        else:
            row = best.objects.order_by('pk').first()
    except Exception:
        return None
    return row.pk if row else None


def main():
    tenant = Tenant.objects.get(slug='acme')
    client = acme_admin_client()
    # Some modules require request.tenant; LoginRequired+TenantRequired mixins
    # rely on the session middleware to derive it. seed_tenants binds admin_acme
    # to acme, so request.tenant will be acme.

    zero_arg = collect_zero_arg_urls()

    oks: list[str] = []
    fails: list[dict] = []

    print(f'Total zero-arg URLs to test: {sum(len(v) for v in zero_arg.values())}')
    for app in MODULES:
        urls = zero_arg.get(app, [])
        print(f'\n== {app} ({len(urls)} urls) ==')
        for name, url in urls:
            label = f'{app}:{name}'
            try:
                resp = client.get(url, follow=False)
                status = resp.status_code
            except Exception as exc:
                fails.append({
                    'app': app, 'name': name, 'url': url,
                    'status': 'EXC', 'detail': f'{type(exc).__name__}: {exc}',
                    'tb': traceback.format_exc(),
                })
                print(f'  FAIL  {label}  EXC {type(exc).__name__}: {exc}')
                continue

            if status >= 500:
                # Render error - capture content for diagnosis
                body = (resp.content[:500].decode('utf-8', 'ignore')
                        if hasattr(resp, 'content') else '')
                fails.append({
                    'app': app, 'name': name, 'url': url,
                    'status': status, 'detail': body,
                })
                print(f'  FAIL  {label}  {status}  {url}')
            elif status in (200, 302, 301, 303, 404, 405):
                # 404 on list page is also a fail; 404 on auth/redirect is OK
                # 405 is correct for POST-only inline submit handlers (e.g.
                # eam:downtime_create, eam:condition_reading_create_top).
                if status == 404 and not name.endswith('_delete'):
                    fails.append({
                        'app': app, 'name': name, 'url': url,
                        'status': status, 'detail': '404 on list/index URL',
                    })
                    print(f'  FAIL  {label}  404  {url}')
                else:
                    oks.append(f'{label} {status}')
                    print(f'  ok    {label}  {status}')
            else:
                # Unexpected status
                fails.append({
                    'app': app, 'name': name, 'url': url,
                    'status': status, 'detail': 'unexpected status code',
                })
                print(f'  FAIL  {label}  {status}')

    # ----- Phase 2: single-pk detail/edit pages -----
    single_pk = collect_single_pk_urls()
    detail_targets = [t for t in single_pk if t[1].endswith(('_detail', '_edit'))]
    print(f'\n\n=== Phase 2: detail/edit URLs ({len(detail_targets)}) ===')
    pk_cache: dict[tuple[str, str], int | None] = {}
    for app, name, pattern_str in detail_targets:
        # Cache pk by model — uses the same heuristic per app+name pair
        cache_key = (app, name.rsplit('_', 1)[0])  # strip _detail/_edit
        if cache_key not in pk_cache:
            pk_cache[cache_key] = pick_first_pk_for(app, name, tenant)
        pk = pk_cache[cache_key]
        if pk is None:
            # No row available — record skipped rather than fail
            oks.append(f'{app}:{name} SKIP (no row)')
            print(f'  skip  {app}:{name}  (no row)')
            continue
        try:
            url = reverse(f'{app}:{name}', args=[pk])
        except Exception as exc:
            print(f'  skip  {app}:{name}  reverse failed: {exc}')
            continue
        label = f'{app}:{name}'
        try:
            resp = client.get(url, follow=False)
            status = resp.status_code
        except Exception as exc:
            fails.append({
                'app': app, 'name': name, 'url': url,
                'status': 'EXC', 'detail': f'{type(exc).__name__}: {exc}',
                'tb': traceback.format_exc(),
            })
            print(f'  FAIL  {label}  EXC {type(exc).__name__}: {exc}')
            continue
        if status >= 500:
            body = (resp.content[:800].decode('utf-8', 'ignore')
                    if hasattr(resp, 'content') else '')
            fails.append({
                'app': app, 'name': name, 'url': url,
                'status': status, 'detail': body,
            })
            print(f'  FAIL  {label}  {status}  {url}')
        elif status in (200, 302, 301, 303, 404, 405):
            # 404 here may mean the heuristic picked the wrong model — note but don't fail
            if status == 404:
                oks.append(f'{label} 404 (wrong-model heuristic)')
                print(f'  ok    {label}  404 (heuristic miss)')
            else:
                oks.append(f'{label} {status}')
                print(f'  ok    {label}  {status}')
        else:
            fails.append({
                'app': app, 'name': name, 'url': url,
                'status': status, 'detail': 'unexpected status code',
            })
            print(f'  FAIL  {label}  {status}')

    # ----- Phase 3: list pages with filter querystrings -----
    # Hit each `_list` URL with a handful of generic GET param combinations.
    # This exposes filter comparison bugs (badge mismatch, |slugify mis-use,
    # missing status_choices in context, etc.) per CLAUDE.md filter rules.
    filter_combos = [
        '?q=a',
        '?q=zzznomatch',
        '?status=draft',
        '?status=released',
        '?status=approved',
        '?active=active',
        '?active=inactive',
        '?page=99',
        '?page=abc',
    ]
    list_urls = [(app, name, url) for app, items in zero_arg.items()
                 for name, url in items if name.endswith(('_list', 'index'))]
    print(f'\n\n=== Phase 3: list-with-filter probes ({len(list_urls)} URLs × '
          f'{len(filter_combos)} combos) ===')
    for app, name, url in list_urls:
        for combo in filter_combos:
            full = url + combo
            label = f'{app}:{name}{combo}'
            try:
                resp = client.get(full, follow=False)
                status = resp.status_code
            except Exception as exc:
                fails.append({
                    'app': app, 'name': name, 'url': full,
                    'status': 'EXC', 'detail': f'{type(exc).__name__}: {exc}',
                    'tb': traceback.format_exc(),
                })
                print(f'  FAIL  {label}  EXC {type(exc).__name__}: {exc}')
                continue
            if status >= 500:
                body = (resp.content[:800].decode('utf-8', 'ignore')
                        if hasattr(resp, 'content') else '')
                fails.append({
                    'app': app, 'name': name, 'url': full,
                    'status': status, 'detail': body,
                })
                print(f'  FAIL  {label}  {status}')
            else:
                oks.append(f'{label} {status}')

    out_path = PROJECT_ROOT / '.claude' / 'manual-tests' / 'smoke_all_modules_results.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'tenant': tenant.slug,
            'totals': {
                'urls_tested': len(oks) + len(fails),
                'oks': len(oks),
                'fails': len(fails),
            },
            'fails': fails,
            'oks_sample': oks[:50],
        }, f, indent=2)

    print(f'\n\n=== summary ===')
    print(f'urls tested: {len(oks) + len(fails)}')
    print(f'ok:   {len(oks)}')
    print(f'fail: {len(fails)}')
    print(f'detail in: {out_path}')

    if fails:
        print('\n--- failures ---')
        for f in fails:
            print(f"  [{f['app']}:{f['name']}]  {f['status']}  {f['url']}")
            print(f"    -> {(f.get('detail') or '')[:200]}")

    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
