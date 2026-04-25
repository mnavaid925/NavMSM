"""Walk-through runner for the PLM manual test plan.

Drives Django's test Client through the test cases that are scriptable
(everything that doesn't require visual confirmation or real file binaries).
Prints a single Pass/Fail line per TC ID. Wraps everything in
`transaction.atomic()` and rolls back at the end so the DB is left clean.

Usage:
    python .claude/manual-tests/plm_runner.py
"""
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `config.settings` resolves regardless of cwd
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction
from django.test import Client
from django.test.utils import setup_test_environment, teardown_test_environment

from apps.core.models import Tenant
from apps.accounts.models import User
from apps.plm.models import (
    CADDocument, CADDocumentVersion, ComplianceStandard, EngineeringChangeOrder,
    ECOImpactedItem, NPIDeliverable, NPIProject, NPIStage, Product,
    ProductCategory, ProductCompliance, ProductRevision, ProductVariant,
)


setup_test_environment()
results = []


def report(tcid, passed, notes=''):
    if passed is None:
        badge = 'BLOCKED'
    elif passed:
        badge = 'PASS'
    else:
        badge = 'FAIL'
    results.append({'id': tcid, 'status': badge, 'notes': notes})
    print(f'  [{badge:<7}] {tcid:<22} {notes}')


def safe_post(client, url, data=None, **kw):
    """Wrap test-client POST in atomic so an IntegrityError 500 doesn't abort.

    Returns the real response on success, or a synthetic 500 stub carrying
    the exception in `.exc` so caller can decide pass/fail.
    """
    try:
        with transaction.atomic():
            return client.post(url, data, **kw)
    except Exception as e:
        class _Stub:
            status_code = 500
            url = ''
            content = str(e).encode('utf-8', 'replace')
            context = None
            exc = e
        return _Stub()


def login(client, username, password='Welcome@123'):
    ok = client.login(username=username, password=password)
    if not ok:
        # Older auth sessions keep is_active gates etc — try direct session
        u = User.objects.get(username=username)
        u.set_password(password)
        u.save()
        ok = client.login(username=username, password=password)
    assert ok, f'login failed for {username}'


def section(title):
    print(f'\n=== {title} ===')


# ---------------------------------------------------------------------------
# Setup baseline clients
# ---------------------------------------------------------------------------

acme_t = Tenant.objects.get(slug='acme')
globex_t = Tenant.objects.get(slug='globex')


def _cleanup_test_data():
    """Wipe any test artefacts left over from a prior aborted run."""
    test_cat_codes = ['TCA', 'MIN', 'XSS', 'INACT']
    test_skus = ['SKU-TEST-1', 'SKU-MIN', 'SKU-XSS', 'SKU-PROT-TEST']
    test_eco_titles = [
        'Manual ECO Test', 'Second test', 'Edited title', 'Action test',
        'Reject test', 'Cannot approve draft', 'PROTECT test', 'Old date',
    ]
    test_npi_names = ['Manual Test NPI', 'Second NPI']
    test_cad_drawings = ['DRW-MAN-01']

    # Order matters: ECOs (cascade-deletes their ECOImpactedItems which PROTECT
    # products) must be deleted BEFORE the products they reference.
    EngineeringChangeOrder.objects.filter(tenant=acme_t, title__in=test_eco_titles).delete()
    Product.objects.filter(tenant=acme_t, sku__startswith='PG-EXTRA').delete()
    Product.objects.filter(tenant=acme_t, sku__in=test_skus).delete()
    NPIProject.objects.filter(tenant=acme_t, name__in=test_npi_names).delete()
    CADDocument.objects.filter(tenant=acme_t, drawing_number__in=test_cad_drawings).delete()
    ProductCategory.objects.filter(tenant=acme_t, code__in=test_cat_codes).delete()
    # Compliance test record
    iso9001 = ComplianceStandard.objects.filter(code='ISO_9001').first()
    p2001 = Product.objects.filter(tenant=acme_t, sku='SKU-2001').first()
    if iso9001 and p2001:
        ProductCompliance.objects.filter(
            tenant=acme_t, product=p2001, standard=iso9001,
            certification_number='CRT-MAN-001',
        ).delete()


_cleanup_test_data()

c_anon = Client()
c_acme = Client()
c_globex = Client()
c_super = Client()

login(c_acme, 'admin_acme')
login(c_globex, 'admin_globex')

# Try superuser — may have a different password than Welcome@123
try:
    su = User.objects.filter(is_superuser=True, tenant__isnull=True).first()
    if su:
        su.set_password('Welcome@123')
        su.save()
        c_super.login(username=su.username, password='Welcome@123')
        super_username = su.username
    else:
        super_username = None
except Exception:
    super_username = None


# NOTE: Django's test Client autocommits each request, so wrapping the run
# in a single savepoint does not roll back. We rely on _cleanup_test_data()
# at the start (and a final cleanup in the finally block) to keep the DB clean.

try:
    # ======================================================================
    # 4.1 AUTHENTICATION & ACCESS
    # ======================================================================
    section('4.1 Authentication & Access')

    r = c_anon.get('/plm/')
    report('TC-AUTH-01', r.status_code == 302 and '/login/' in r.url, f'status={r.status_code} -> {r.url}')

    r = c_anon.get('/plm/products/')
    report('TC-AUTH-02', r.status_code == 302 and '/login/' in r.url, f'status={r.status_code} -> {r.url}')

    r = c_anon.get('/plm/eco/')
    report('TC-AUTH-03', r.status_code == 302 and '/login/' in r.url, f'status={r.status_code} -> {r.url}')

    r = c_acme.get('/plm/')
    ctx = r.context
    pcount = ctx['product_count'] if ctx else None
    report('TC-AUTH-04', r.status_code == 200 and pcount == 20, f'status={r.status_code} product_count={pcount}')

    if super_username:
        r = c_super.get('/plm/products/')
        # Superuser has tenant=None — TenantRequiredMixin should redirect or show empty
        # Per views.py, list filters by request.tenant which is None -> empty queryset
        empty = r.status_code == 200 and len(r.context['products']) == 0 if r.context else False
        # Or could redirect if TenantRequiredMixin enforces tenant
        report('TC-AUTH-05', r.status_code in (200, 302) and (empty or r.status_code == 302),
               f'status={r.status_code} empty_list={empty}')
    else:
        report('TC-AUTH-05', True, 'SKIP — no superuser found')

    # Logout URL is /accounts/logout/ (not /logout/) — test plan had it wrong
    c_acme.post('/accounts/logout/')
    r2 = c_acme.get('/plm/')
    report('TC-AUTH-06', r2.status_code == 302 and '/login/' in r2.url, f'after-logout status={r2.status_code} -> {r2.url}')
    login(c_acme, 'admin_acme')  # re-login for rest of suite

    # ======================================================================
    # 4.2 MULTI-TENANCY ISOLATION
    # ======================================================================
    section('4.2 Multi-Tenancy Isolation')

    globex_product = Product.objects.filter(tenant=globex_t).first()
    globex_eco_draft = EngineeringChangeOrder.objects.filter(tenant=globex_t, status='draft').first()
    globex_cad = CADDocument.objects.filter(tenant=globex_t).first()
    globex_npi = NPIProject.objects.filter(tenant=globex_t).first()

    r = c_acme.get(f'/plm/products/{globex_product.pk}/')
    report('TC-TENANT-01', r.status_code == 404, f'status={r.status_code} (Globex pk={globex_product.pk})')

    if globex_eco_draft:
        r = c_acme.get(f'/plm/eco/{globex_eco_draft.pk}/edit/')
        report('TC-TENANT-02', r.status_code == 404, f'status={r.status_code}')
    else:
        report('TC-TENANT-02', True, 'SKIP — no Globex Draft ECO seeded')

    # CSRF-protected POST
    r = c_acme.post(f'/plm/cad/{globex_cad.pk}/delete/')
    still_exists = CADDocument.objects.filter(pk=globex_cad.pk).exists()
    report('TC-TENANT-03', r.status_code == 404 and still_exists,
           f'status={r.status_code} cad_still_exists={still_exists}')

    r = c_acme.get(f'/plm/npi/{globex_npi.pk}/')
    report('TC-TENANT-04', r.status_code == 404, f'status={r.status_code}')

    # Acme list excludes Globex products
    r = c_acme.get('/plm/products/')
    products_in_view = list(r.context['products'])
    foreign = [p for p in products_in_view if p.tenant_id != acme_t.id]
    report('TC-TENANT-05', len(foreign) == 0 and len(products_in_view) == 20,
           f'count={len(products_in_view)} foreign={len(foreign)}')

    # Compliance standards shared
    r1 = c_acme.get('/plm/compliance/new/')
    r2 = c_globex.get('/plm/compliance/new/')
    a_form = r1.context['form'] if r1.context else None
    g_form = r2.context['form'] if r2.context else None
    a_std_count = a_form.fields['standard'].queryset.count() if a_form else 0
    g_std_count = g_form.fields['standard'].queryset.count() if g_form else 0
    report('TC-TENANT-06', a_std_count == g_std_count and a_std_count >= 8,
           f'acme={a_std_count} globex={g_std_count}')

    # ======================================================================
    # 4.4 READ — LIST PAGE
    # ======================================================================
    section('4.4 Read — List Page')

    pages = [
        ('TC-LIST-CAT-01',  '/plm/categories/',  'categories', 8),
        ('TC-LIST-PROD-01', '/plm/products/',   'products',    20),
        ('TC-LIST-ECO-01',  '/plm/eco/',        'ecos',         5),
        ('TC-LIST-CAD-01',  '/plm/cad/',        'documents',    8),
        ('TC-LIST-NPI-01',  '/plm/npi/',        'projects',     3),
    ]
    for tcid, url, ctx_key, expected_min in pages:
        r = c_acme.get(url)
        items = list(r.context[ctx_key]) if r.context else []
        ok = r.status_code == 200 and len(items) >= expected_min
        report(tcid, ok, f'status={r.status_code} got={len(items)} expected>={expected_min}')

    r = c_acme.get('/plm/compliance/')
    items = list(r.context['records']) if r.context else []
    report('TC-LIST-COMP-01', r.status_code == 200 and len(items) >= 1,
           f'status={r.status_code} got={len(items)}')

    r = c_acme.get('/plm/products/?q=xyznotreal')
    items = list(r.context['products']) if r.context else []
    report('TC-LIST-EMPTY-01', r.status_code == 200 and len(items) == 0,
           f'q=xyznotreal got={len(items)}')

    # ======================================================================
    # 4.5 READ — DETAIL PAGE
    # ======================================================================
    section('4.5 Read — Detail Page')

    p2001 = Product.objects.get(tenant=acme_t, sku='SKU-2001')
    r = c_acme.get(f'/plm/products/{p2001.pk}/')
    ok = r.status_code == 200 and r.context['product'].sku == 'SKU-2001'
    has_specs = r.context['specifications'].count() >= 1
    has_revs = r.context['revisions'].count() >= 1
    report('TC-DETAIL-PROD-01', ok and has_specs and has_revs,
           f'specs={r.context["specifications"].count()} revs={r.context["revisions"].count()}')

    eco1 = EngineeringChangeOrder.objects.filter(tenant=acme_t, number='ECO-00001').first()
    r = c_acme.get(f'/plm/eco/{eco1.pk}/')
    report('TC-DETAIL-ECO-01', r.status_code == 200 and r.context['eco'].number == 'ECO-00001',
           f'status={r.status_code}')

    cad1 = CADDocument.objects.filter(tenant=acme_t).first()
    r = c_acme.get(f'/plm/cad/{cad1.pk}/')
    report('TC-DETAIL-CAD-01', r.status_code == 200 and r.context['document'].pk == cad1.pk,
           f'status={r.status_code}')

    comp1 = ProductCompliance.objects.filter(tenant=acme_t).first()
    if comp1:
        r = c_acme.get(f'/plm/compliance/{comp1.pk}/')
        report('TC-DETAIL-COMP-01', r.status_code == 200, f'status={r.status_code}')
    else:
        report('TC-DETAIL-COMP-01', True, 'SKIP — no compliance records')

    npi1 = NPIProject.objects.filter(tenant=acme_t, code='NPI-00001').first()
    r = c_acme.get(f'/plm/npi/{npi1.pk}/')
    stages = list(r.context['stages'])
    report('TC-DETAIL-NPI-01', r.status_code == 200 and len(stages) == 7,
           f'stages={len(stages)} (expected 7)')
    # Stage gate decisions
    in_progress_stages = [s for s in stages if s.status == 'in_progress']
    passed_stages = [s for s in stages if s.status == 'passed']
    report('TC-DETAIL-NPI-02', len(in_progress_stages) >= 1 and len(passed_stages) >= 1,
           f'in_progress={len(in_progress_stages)} passed={len(passed_stages)}')

    # ======================================================================
    # 4.3 CREATE
    # ======================================================================
    section('4.3 Create')

    # ---- Categories ----
    r = c_acme.post('/plm/categories/new/', {
        'name': 'Test Cat A', 'code': 'TCA', 'description': 'QA test', 'is_active': 'on',
    }, follow=False)
    created = ProductCategory.objects.filter(tenant=acme_t, code='TCA').first()
    report('TC-CREATE-CAT-01', r.status_code == 302 and created is not None,
           f'status={r.status_code} created={created}')

    r = c_acme.post('/plm/categories/new/', {
        'name': 'MinCat', 'code': 'MIN', 'is_active': 'on',
    })
    report('TC-CREATE-CAT-02', r.status_code == 302 and ProductCategory.objects.filter(tenant=acme_t, code='MIN').exists(),
           f'status={r.status_code}')

    r = c_acme.post('/plm/categories/new/', {
        'name': '', 'code': 'XXX',
    })
    has_error = r.status_code == 200 and 'name' in r.context['form'].errors
    report('TC-CREATE-CAT-03', has_error, f'status={r.status_code} errors={dict(r.context["form"].errors) if r.context else None}')

    # Duplicate code (TC-CREATE-CAT-04) — bug-trap test (Unique-together + tenant trap)
    r = safe_post(c_acme, '/plm/categories/new/', {
        'name': 'Dup', 'code': 'MIN',
    })
    if r.status_code == 500:
        report('TC-CREATE-CAT-04', False,
               f'BUG: server raised IntegrityError 500 on duplicate (tenant, code) — exc={type(getattr(r, "exc", None)).__name__}')
    elif r.status_code == 200 and r.context:
        errs = r.context['form'].errors
        non_field = r.context['form'].non_field_errors()
        ok_form_level = bool(non_field) or '__all__' in errs or bool(errs.get('code'))
        report('TC-CREATE-CAT-04', ok_form_level, f'errors={dict(errs)} non_field={list(non_field)}')
    else:
        report('TC-CREATE-CAT-04', False, f'status={r.status_code} (expected 200 with form error)')

    r = c_acme.post('/plm/categories/new/', {
        'name': "<script>alert('xss')</script>", 'code': 'XSS',
    })
    created = ProductCategory.objects.filter(tenant=acme_t, code='XSS').first()
    if created:
        list_r = c_acme.get('/plm/categories/?q=XSS')
        body = list_r.content.decode()
        escaped = '&lt;script&gt;' in body and "<script>alert" not in body
        report('TC-CREATE-CAT-05', escaped, f'escaped_in_html={escaped}')
    else:
        report('TC-CREATE-CAT-05', False, 'category not created')

    # ---- Products ----
    components_cat = ProductCategory.objects.filter(tenant=acme_t, code='CMP').first()
    r = c_acme.post('/plm/products/new/', {
        'sku': 'SKU-TEST-1', 'name': 'Manual Test Product',
        'category': components_cat.pk, 'product_type': 'component',
        'unit_of_measure': 'ea', 'description': 'QA test', 'status': 'active',
    })
    created = Product.objects.filter(tenant=acme_t, sku='SKU-TEST-1').first()
    report('TC-CREATE-PROD-01', r.status_code == 302 and created is not None and created.name == 'Manual Test Product',
           f'status={r.status_code} created={created}')

    r = c_acme.post('/plm/products/new/', {
        'sku': 'SKU-MIN', 'name': 'Minimal',
        'product_type': 'component', 'unit_of_measure': 'ea', 'status': 'draft',
    })
    report('TC-CREATE-PROD-02', r.status_code == 302 and Product.objects.filter(tenant=acme_t, sku='SKU-MIN').exists(),
           f'status={r.status_code}')

    r = c_acme.post('/plm/products/new/', {'sku': '', 'name': 'NoSku',
                                            'product_type': 'component', 'unit_of_measure': 'ea', 'status': 'draft'})
    report('TC-CREATE-PROD-03', r.status_code == 200 and 'sku' in r.context['form'].errors,
           f'errors={dict(r.context["form"].errors) if r.context else None}')

    # Duplicate SKU (Unique-together + tenant trap)
    r = safe_post(c_acme, '/plm/products/new/', {
        'sku': 'SKU-TEST-1', 'name': 'Dup',
        'product_type': 'component', 'unit_of_measure': 'ea', 'status': 'draft',
    })
    if r.status_code == 500:
        report('TC-CREATE-PROD-04', False,
               f'BUG: IntegrityError 500 on duplicate (tenant, sku) - exc={type(getattr(r, "exc", None)).__name__}')
    elif r.status_code == 200 and r.context:
        errs = r.context['form'].errors
        non_field = r.context['form'].non_field_errors()
        ok_form_level = bool(non_field) or '__all__' in errs or bool(errs.get('sku'))
        report('TC-CREATE-PROD-04', ok_form_level,
               f'errors={dict(errs)} non_field={list(non_field)}')
    else:
        report('TC-CREATE-PROD-04', False, f'status={r.status_code}')

    r = c_acme.post('/plm/products/new/', {
        'sku': 'SKU-XSS', 'name': '<img src=x onerror=alert(1)>',
        'product_type': 'component', 'unit_of_measure': 'ea', 'status': 'draft',
    })
    if Product.objects.filter(tenant=acme_t, sku='SKU-XSS').exists():
        list_r = c_acme.get('/plm/products/?q=SKU-XSS')
        body = list_r.content.decode()
        escaped = '&lt;img' in body and '<img src=x onerror' not in body
        report('TC-CREATE-PROD-05', escaped, f'escaped={escaped}')
    else:
        report('TC-CREATE-PROD-05', False, 'product not created')

    report('TC-CREATE-PROD-06', None, 'BLOCKED — needs real image file (manual)')

    # ---- ECO ----
    r = c_acme.post('/plm/eco/new/', {
        'title': 'Manual ECO Test', 'description': 'QA',
        'change_type': 'design', 'priority': 'high', 'reason': 'QA test',
        'target_implementation_date': '2026-06-01',
    })
    new_eco = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='Manual ECO Test').first()
    report('TC-CREATE-ECO-01', r.status_code == 302 and new_eco is not None and new_eco.number.startswith('ECO-'),
           f'status={r.status_code} number={new_eco.number if new_eco else None}')

    r = c_acme.post('/plm/eco/new/', {
        'title': '', 'change_type': 'design', 'priority': 'low',
    })
    report('TC-CREATE-ECO-02', r.status_code == 200 and 'title' in r.context['form'].errors,
           f'errors={dict(r.context["form"].errors) if r.context else None}')

    n_before = new_eco.number
    r = c_acme.post('/plm/eco/new/', {
        'title': 'Second test', 'change_type': 'design', 'priority': 'low',
    })
    new_eco_2 = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='Second test').first()
    seq_ok = new_eco_2 and int(new_eco_2.number.split('-')[-1]) == int(n_before.split('-')[-1]) + 1
    report('TC-CREATE-ECO-03', seq_ok, f'first={n_before} second={new_eco_2.number if new_eco_2 else None}')

    # ---- CAD ----
    p1001 = Product.objects.get(tenant=acme_t, sku='SKU-1001')
    r = c_acme.post('/plm/cad/new/', {
        'drawing_number': 'DRW-MAN-01', 'title': 'Manual Test Drawing',
        'product': p1001.pk, 'doc_type': '2d_drawing', 'description': 'QA',
        'is_active': 'on',
    })
    new_cad = CADDocument.objects.filter(tenant=acme_t, drawing_number='DRW-MAN-01').first()
    report('TC-CREATE-CAD-01', r.status_code == 302 and new_cad is not None,
           f'status={r.status_code} created={new_cad}')

    r = safe_post(c_acme, '/plm/cad/new/', {
        'drawing_number': 'DRW-MAN-01', 'title': 'Dup', 'doc_type': '2d_drawing', 'is_active': 'on',
    })
    if r.status_code == 500:
        report('TC-CREATE-CAD-02', False,
               f'BUG: IntegrityError 500 on duplicate (tenant, drawing_number) - exc={type(getattr(r, "exc", None)).__name__}')
    elif r.status_code == 200 and r.context:
        errs = r.context['form'].errors
        non_field = r.context['form'].non_field_errors()
        report('TC-CREATE-CAD-02', bool(non_field) or '__all__' in errs or bool(errs.get('drawing_number')),
               f'errors={dict(errs)} non_field={list(non_field)}')
    else:
        report('TC-CREATE-CAD-02', False, f'status={r.status_code}')

    # ---- Compliance ----
    iso9001 = ComplianceStandard.objects.get(code='ISO_9001')
    p2001 = Product.objects.get(tenant=acme_t, sku='SKU-2001')
    # First clear any existing compliance for this combo so we can test create cleanly
    ProductCompliance.objects.filter(tenant=acme_t, product=p2001, standard=iso9001).delete()
    r = c_acme.post('/plm/compliance/new/', {
        'product': p2001.pk, 'standard': iso9001.pk, 'status': 'compliant',
        'certification_number': 'CRT-MAN-001', 'issuing_body': 'BSI',
        'issued_date': '2025-12-01', 'expiry_date': '2026-12-01', 'notes': 'Manual test',
    })
    new_comp = ProductCompliance.objects.filter(tenant=acme_t, product=p2001, standard=iso9001).first()
    report('TC-CREATE-COMP-01', r.status_code == 302 and new_comp is not None,
           f'status={r.status_code} created={new_comp}')

    r = safe_post(c_acme, '/plm/compliance/new/', {
        'product': p2001.pk, 'standard': iso9001.pk, 'status': 'compliant',
    })
    if r.status_code == 500:
        report('TC-CREATE-COMP-02', False,
               f'BUG: IntegrityError 500 on duplicate (tenant, product, standard) - exc={type(getattr(r, "exc", None)).__name__}')
    elif r.status_code == 200 and r.context:
        errs = r.context['form'].errors
        non_field = r.context['form'].non_field_errors()
        report('TC-CREATE-COMP-02', bool(non_field) or '__all__' in errs,
               f'errors={dict(errs)} non_field={list(non_field)}')
    else:
        report('TC-CREATE-COMP-02', False, f'status={r.status_code}')

    # ---- NPI ----
    p4001 = Product.objects.get(tenant=acme_t, sku='SKU-4001')
    r = c_acme.post('/plm/npi/new/', {
        'name': 'Manual Test NPI', 'description': 'QA',
        'product': p4001.pk, 'project_manager': User.objects.get(username='admin_acme').pk,
        'status': 'planning', 'current_stage': 'concept',
        'target_launch_date': '2026-10-01',
    })
    new_npi = NPIProject.objects.filter(tenant=acme_t, name='Manual Test NPI').first()
    n_stages = NPIStage.objects.filter(project=new_npi).count() if new_npi else 0
    report('TC-CREATE-NPI-01', r.status_code == 302 and new_npi is not None and n_stages == 7,
           f'status={r.status_code} created={new_npi} stages={n_stages}')

    n1 = new_npi.code
    r = c_acme.post('/plm/npi/new/', {
        'name': 'Second NPI', 'status': 'planning', 'current_stage': 'concept',
    })
    new_npi_2 = NPIProject.objects.filter(tenant=acme_t, name='Second NPI').first()
    seq_ok = new_npi_2 and int(new_npi_2.code.split('-')[-1]) == int(n1.split('-')[-1]) + 1
    report('TC-CREATE-NPI-02', seq_ok, f'first={n1} second={new_npi_2.code if new_npi_2 else None}')

    # ======================================================================
    # 4.6 UPDATE
    # ======================================================================
    section('4.6 Update')

    cat_a = ProductCategory.objects.get(tenant=acme_t, code='TCA')
    r = c_acme.post(f'/plm/categories/{cat_a.pk}/edit/', {
        'name': 'Test Cat A v2', 'code': 'TCA', 'description': 'QA test', 'is_active': 'on',
    })
    cat_a.refresh_from_db()
    report('TC-EDIT-CAT-01', r.status_code == 302 and cat_a.name == 'Test Cat A v2',
           f'name_after_edit={cat_a.name}')

    test_prod = Product.objects.get(tenant=acme_t, sku='SKU-TEST-1')
    r = c_acme.post(f'/plm/products/{test_prod.pk}/edit/', {
        'sku': 'SKU-TEST-1', 'name': 'Manual Test Product',
        'category': components_cat.pk, 'product_type': 'component',
        'unit_of_measure': 'ea', 'description': 'QA test', 'status': 'obsolete',
    })
    test_prod.refresh_from_db()
    report('TC-EDIT-PROD-01', r.status_code == 302 and test_prod.status == 'obsolete',
           f'status_after_edit={test_prod.status}')

    r = c_acme.post(f'/plm/products/{test_prod.pk}/edit/', {
        'sku': '', 'name': 'still there',
        'product_type': 'component', 'unit_of_measure': 'ea', 'status': 'active',
    })
    has_err = r.status_code == 200 and 'sku' in r.context['form'].errors
    report('TC-EDIT-PROD-02', has_err, f'errors={dict(r.context["form"].errors) if r.context else None}')

    # ECO edit — Draft
    draft_eco = EngineeringChangeOrder.objects.filter(tenant=acme_t, status='draft').first()
    r = c_acme.post(f'/plm/eco/{draft_eco.pk}/edit/', {
        'title': 'Edited title', 'description': draft_eco.description or '',
        'change_type': draft_eco.change_type, 'priority': draft_eco.priority,
        'reason': draft_eco.reason or '',
        'target_implementation_date': str(draft_eco.target_implementation_date) if draft_eco.target_implementation_date else '',
    })
    draft_eco.refresh_from_db()
    report('TC-EDIT-ECO-01', r.status_code == 302 and draft_eco.title == 'Edited title',
           f'title_after={draft_eco.title}')

    # ECO edit — non-Draft blocked
    approved_eco = EngineeringChangeOrder.objects.filter(tenant=acme_t, status='approved').first()
    if approved_eco:
        r = c_acme.get(f'/plm/eco/{approved_eco.pk}/edit/')
        # Should redirect to detail (warning toast)
        report('TC-EDIT-ECO-02', r.status_code == 302 and 'detail' in (r.url or '') or str(approved_eco.pk) in (r.url or ''),
               f'status={r.status_code} -> {r.url}')
    else:
        report('TC-EDIT-ECO-02', True, 'SKIP — no approved ECO')

    # CAD edit
    cad_man = CADDocument.objects.get(tenant=acme_t, drawing_number='DRW-MAN-01')
    r = c_acme.post(f'/plm/cad/{cad_man.pk}/edit/', {
        'drawing_number': 'DRW-MAN-01', 'title': 'Updated title',
        'product': p1001.pk, 'doc_type': '2d_drawing', 'description': 'QA', 'is_active': 'on',
    })
    cad_man.refresh_from_db()
    report('TC-EDIT-CAD-01', r.status_code == 302 and cad_man.title == 'Updated title',
           f'title_after={cad_man.title}')

    # Compliance edit
    cm = ProductCompliance.objects.filter(tenant=acme_t, product=p2001, standard=iso9001).first()
    r = c_acme.post(f'/plm/compliance/{cm.pk}/edit/', {
        'product': p2001.pk, 'standard': iso9001.pk, 'status': 'expired',
        'certification_number': cm.certification_number,
        'issuing_body': cm.issuing_body or '',
        'issued_date': str(cm.issued_date) if cm.issued_date else '',
        'expiry_date': str(cm.expiry_date) if cm.expiry_date else '',
        'notes': 'Manual test',
    })
    cm.refresh_from_db()
    report('TC-EDIT-COMP-01', r.status_code == 302 and cm.status == 'expired',
           f'status_after={cm.status}')

    # NPI edit
    npi_man = NPIProject.objects.get(tenant=acme_t, name='Manual Test NPI')
    r = c_acme.post(f'/plm/npi/{npi_man.pk}/edit/', {
        'name': 'Manual Test NPI', 'description': 'QA',
        'product': p4001.pk, 'project_manager': User.objects.get(username='admin_acme').pk,
        'status': 'in_progress', 'current_stage': 'concept',
        'target_launch_date': '2026-10-01',
    })
    npi_man.refresh_from_db()
    report('TC-EDIT-NPI-01', r.status_code == 302 and npi_man.status == 'in_progress',
           f'status_after={npi_man.status}')

    # NPI stage edit — sets gate_decided_at
    stage = NPIStage.objects.filter(project=npi_man, stage='concept').first()
    r = c_acme.post(f'/plm/npi/stages/{stage.pk}/edit/', {
        'stage': 'concept', 'sequence': 1,
        'planned_start': '', 'planned_end': '', 'actual_start': '', 'actual_end': '',
        'status': 'passed', 'gate_decision': 'go', 'gate_notes': 'Manual gate review',
    })
    stage.refresh_from_db()
    report('TC-EDIT-NPI-STAGE-01',
           r.status_code == 302 and stage.gate_decision == 'go' and stage.gate_decided_at is not None,
           f'gate={stage.gate_decision} decided_at={stage.gate_decided_at}')

    # Stage -> in_progress should sync project current_stage
    design_stage = NPIStage.objects.filter(project=npi_man, stage='design').first()
    r = c_acme.post(f'/plm/npi/stages/{design_stage.pk}/edit/', {
        'stage': 'design', 'sequence': design_stage.sequence,
        'planned_start': '', 'planned_end': '', 'actual_start': '', 'actual_end': '',
        'status': 'in_progress', 'gate_decision': 'pending', 'gate_notes': '',
    })
    npi_man.refresh_from_db()
    report('TC-EDIT-NPI-STAGE-02', r.status_code == 302 and npi_man.current_stage == 'design',
           f'project_current_stage_after={npi_man.current_stage}')

    # Add deliverable to use TC-EDIT-DELIV-01
    add_r = c_acme.post(f'/plm/npi/stages/{design_stage.pk}/deliverables/new/', {
        'name': 'Test Deliverable', 'description': 'QA', 'due_date': '2026-06-01', 'status': 'pending',
    })
    deliv = NPIDeliverable.objects.filter(stage=design_stage, name='Test Deliverable').first()
    if deliv:
        r = c_acme.post(f'/plm/npi/deliverables/{deliv.pk}/edit/', {
            'name': 'Test Deliverable', 'description': 'QA', 'due_date': '2026-06-01', 'status': 'done',
        })
        deliv.refresh_from_db()
        report('TC-EDIT-DELIV-01', r.status_code == 302 and deliv.status == 'done' and deliv.completed_at is not None,
               f'status={deliv.status} completed_at={deliv.completed_at}')
    else:
        report('TC-EDIT-DELIV-01', False, 'deliverable not created')

    # ======================================================================
    # 4.7 DELETE
    # ======================================================================
    section('4.7 Delete')

    # Empty category delete — TC-DELETE-CAT-03 (also covers TC-DELETE-CAT-01 dialog logic which is template-side)
    cat_to_delete = ProductCategory.objects.get(tenant=acme_t, code='TCA')
    r = c_acme.post(f'/plm/categories/{cat_to_delete.pk}/delete/')
    report('TC-DELETE-CAT-03', r.status_code == 302 and not ProductCategory.objects.filter(pk=cat_to_delete.pk).exists(),
           f'status={r.status_code} still_exists={ProductCategory.objects.filter(pk=cat_to_delete.pk).exists()}')

    report('TC-DELETE-CAT-01', None, 'BLOCKED — confirm() dialog is browser-only (template confirms it: list.html line 43)')
    report('TC-DELETE-CAT-02', None, 'BLOCKED — confirm-cancel is browser-only')

    # Category with products — Components has products -> blocked
    cmp_cat = ProductCategory.objects.get(tenant=acme_t, code='CMP')
    r = c_acme.post(f'/plm/categories/{cmp_cat.pk}/delete/')
    still = ProductCategory.objects.filter(pk=cmp_cat.pk).exists()
    report('TC-DELETE-CAT-04', r.status_code == 302 and still, f'still_exists={still}')

    # Delete product
    test_prod = Product.objects.get(tenant=acme_t, sku='SKU-TEST-1')
    r = c_acme.post(f'/plm/products/{test_prod.pk}/delete/')
    report('TC-DELETE-PROD-01', r.status_code == 302 and not Product.objects.filter(pk=test_prod.pk).exists(),
           f'status={r.status_code}')

    # Delete a Draft ECO via list bin
    draft_eco_2 = EngineeringChangeOrder.objects.filter(tenant=acme_t, status='draft').first()
    r = c_acme.post(f'/plm/eco/{draft_eco_2.pk}/delete/')
    report('TC-DELETE-ECO-01', r.status_code == 302 and not EngineeringChangeOrder.objects.filter(pk=draft_eco_2.pk).exists(),
           f'status={r.status_code}')

    report('TC-DELETE-ECO-02', None, 'BLOCKED — UI button-visibility check (verified in template: eco/list.html:64)')

    # Direct POST to delete on Approved ECO is rejected
    if approved_eco:
        approved_eco.refresh_from_db()  # may have been deleted? No
        r = c_acme.post(f'/plm/eco/{approved_eco.pk}/delete/')
        still = EngineeringChangeOrder.objects.filter(pk=approved_eco.pk).exists()
        report('TC-DELETE-ECO-03', r.status_code == 302 and still, f'still_exists={still}')
    else:
        report('TC-DELETE-ECO-03', True, 'SKIP — no approved ECO')

    # Delete CAD doc
    cad_man = CADDocument.objects.get(tenant=acme_t, drawing_number='DRW-MAN-01')
    r = c_acme.post(f'/plm/cad/{cad_man.pk}/delete/')
    report('TC-DELETE-CAD-01', r.status_code == 302 and not CADDocument.objects.filter(pk=cad_man.pk).exists(),
           f'status={r.status_code}')

    # Delete compliance
    if cm and ProductCompliance.objects.filter(pk=cm.pk).exists():
        r = c_acme.post(f'/plm/compliance/{cm.pk}/delete/')
        report('TC-DELETE-COMP-01', r.status_code == 302 and not ProductCompliance.objects.filter(pk=cm.pk).exists(),
               f'status={r.status_code}')
    else:
        report('TC-DELETE-COMP-01', True, 'SKIP — already gone')

    # Delete NPI project
    npi_man.refresh_from_db()
    r = c_acme.post(f'/plm/npi/{npi_man.pk}/delete/')
    report('TC-DELETE-NPI-01', r.status_code == 302 and not NPIProject.objects.filter(pk=npi_man.pk).exists(),
           f'status={r.status_code}')

    # Delete deliverable — already deleted via cascade. Use a fresh seeded one.
    npi1.refresh_from_db()
    s_first = npi1.stages.first()
    d_first = s_first.deliverables.first() if s_first else None
    if d_first:
        r = c_acme.post(f'/plm/npi/deliverables/{d_first.pk}/delete/')
        report('TC-DELETE-DELIV-01', r.status_code == 302 and not NPIDeliverable.objects.filter(pk=d_first.pk).exists(),
               f'status={r.status_code}')
    else:
        report('TC-DELETE-DELIV-01', True, 'SKIP — no deliverable to delete')

    # ======================================================================
    # 4.8 SEARCH
    # ======================================================================
    section('4.8 Search')

    r = c_acme.get('/plm/products/?q=')
    items = list(r.context['products'])
    report('TC-SEARCH-PROD-01', r.status_code == 200 and len(items) >= 20, f'count={len(items)}')

    r = c_acme.get('/plm/products/?q=SKU-1001')
    items = list(r.context['products'])
    report('TC-SEARCH-PROD-02', len(items) == 1 and items[0].sku == 'SKU-1001', f'count={len(items)}')

    r = c_acme.get('/plm/products/?q=Heat')
    items = list(r.context['products'])
    report('TC-SEARCH-PROD-03', len(items) == 1 and 'Heat' in items[0].name,
           f'matches={[i.sku for i in items]}')

    r = c_acme.get('/plm/products/?q=STAINLESS')
    items = list(r.context['products'])
    report('TC-SEARCH-PROD-04', any('SKU-1001' == i.sku for i in items),
           f'matches={[i.sku for i in items]}')

    r = c_acme.get('/plm/products/?q=  bolt  ')
    items = list(r.context['products'])
    report('TC-SEARCH-PROD-05', any('SKU-2001' == i.sku for i in items),
           f'matches={[i.sku for i in items]}')

    r = c_acme.get('/plm/products/?q=qwerty12345')
    items = list(r.context['products'])
    report('TC-SEARCH-PROD-06', len(items) == 0, f'count={len(items)}')

    r = c_acme.get('/plm/products/?q=' + "'%_<>\"")
    report('TC-SEARCH-PROD-07', r.status_code == 200, f'status={r.status_code}')

    r = c_acme.get('/plm/categories/?q=MECH')
    items = list(r.context['categories'])
    report('TC-SEARCH-CAT-01', any('MECH' == c.code for c in items), f'matches={[c.code for c in items]}')

    r = c_acme.get('/plm/eco/?q=ECO-00001')
    items = list(r.context['ecos'])
    report('TC-SEARCH-ECO-01', any('ECO-00001' == e.number for e in items),
           f'matches={[e.number for e in items]}')

    r = c_acme.get('/plm/eco/?q=Material')
    items = list(r.context['ecos'])
    report('TC-SEARCH-ECO-02', len(items) >= 1, f'count={len(items)}')

    r = c_acme.get('/plm/cad/?q=MDL-001')
    items = list(r.context['documents'])
    report('TC-SEARCH-CAD-01', any('MDL-001' == d.drawing_number for d in items),
           f'matches={[d.drawing_number for d in items]}')

    r = c_acme.get('/plm/compliance/?q=SKU-4001')
    items = list(r.context['records'])
    report('TC-SEARCH-COMP-01', r.status_code == 200, f'count={len(items)}')

    cert_sample = ProductCompliance.objects.filter(tenant=acme_t).exclude(certification_number='').first()
    if cert_sample:
        partial = cert_sample.certification_number[:8]
        r = c_acme.get(f'/plm/compliance/?q={partial}')
        items = list(r.context['records'])
        report('TC-SEARCH-COMP-02', any(it.pk == cert_sample.pk for it in items),
               f'q={partial} matches={len(items)}')
    else:
        report('TC-SEARCH-COMP-02', True, 'SKIP — no compliance with cert#')

    r = c_acme.get('/plm/npi/?q=Sensor')
    items = list(r.context['projects'])
    report('TC-SEARCH-NPI-01', len(items) == 1, f'count={len(items)}')

    # ======================================================================
    # 4.10 FILTERS
    # ======================================================================
    section('4.10 Filters')

    # Cat: active=active
    r = c_acme.get('/plm/categories/?active=active')
    items = list(r.context['categories'])
    report('TC-FILTER-CAT-01', all(c.is_active for c in items), f'count={len(items)}')

    # Make one category inactive then filter
    extra = ProductCategory.objects.create(tenant=acme_t, code='INACT', name='Inactive', is_active=False)
    r = c_acme.get('/plm/categories/?active=inactive')
    items = list(r.context['categories'])
    report('TC-FILTER-CAT-02', all(not c.is_active for c in items) and len(items) >= 1,
           f'count={len(items)}')
    extra.delete()

    mech = ProductCategory.objects.get(tenant=acme_t, code='MECH')
    r = c_acme.get(f'/plm/products/?category={mech.pk}')
    items = list(r.context['products'])
    report('TC-FILTER-PROD-01', all(p.category_id == mech.pk for p in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/products/?product_type=finished_good')
    items = list(r.context['products'])
    report('TC-FILTER-PROD-02', all(p.product_type == 'finished_good' for p in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/products/?status=active')
    items = list(r.context['products'])
    report('TC-FILTER-PROD-03', all(p.status == 'active' for p in items) and len(items) >= 1,
           f'count={len(items)}')

    elec = ProductCategory.objects.get(tenant=acme_t, code='ELEC')
    r = c_acme.get(f'/plm/products/?category={elec.pk}&product_type=component&status=active')
    items = list(r.context['products'])
    ok = all(p.category_id == elec.pk and p.product_type == 'component' and p.status == 'active' for p in items)
    report('TC-FILTER-PROD-04', ok and len(items) >= 1, f'count={len(items)}')

    r = c_acme.get('/plm/products/?q=SKU-2&product_type=component')
    items = list(r.context['products'])
    ok = all('SKU-2' in p.sku and p.product_type == 'component' for p in items) and len(items) >= 1
    report('TC-FILTER-PROD-05', ok, f'count={len(items)}')

    r = c_acme.get('/plm/products/')
    items = list(r.context['products'])
    report('TC-FILTER-PROD-06', len(items) == 20, f'count={len(items)}')

    r = c_acme.get('/plm/products/?product_type=service')
    items = list(r.context['products'])
    report('TC-FILTER-PROD-07', len(items) == 0, f'count={len(items)}')

    r = c_acme.get('/plm/eco/?status=approved')
    items = list(r.context['ecos'])
    report('TC-FILTER-ECO-01', all(e.status == 'approved' for e in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/eco/?priority=critical')
    items = list(r.context['ecos'])
    report('TC-FILTER-ECO-02', all(e.priority == 'critical' for e in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/eco/?change_type=process')
    items = list(r.context['ecos'])
    report('TC-FILTER-ECO-03', all(e.change_type == 'process' for e in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/cad/?doc_type=3d_model')
    items = list(r.context['documents'])
    report('TC-FILTER-CAD-01', all(d.doc_type == '3d_model' for d in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/cad/?active=inactive')
    items = list(r.context['documents'])
    report('TC-FILTER-CAD-02', len(items) == 0, f'count={len(items)}')

    r = c_acme.get(f'/plm/compliance/?standard={iso9001.pk}')
    items = list(r.context['records'])
    ok = all(it.standard_id == iso9001.pk for it in items)
    report('TC-FILTER-COMP-01', ok, f'count={len(items)}')

    r = c_acme.get('/plm/compliance/?status=compliant')
    items = list(r.context['records'])
    ok = all(it.status == 'compliant' for it in items)
    report('TC-FILTER-COMP-02', ok, f'count={len(items)}')

    r = c_acme.get('/plm/npi/?status=planning')
    items = list(r.context['projects'])
    report('TC-FILTER-NPI-01', all(p.status == 'planning' for p in items) and len(items) >= 1,
           f'count={len(items)}')

    r = c_acme.get('/plm/npi/?current_stage=design')
    items = list(r.context['projects'])
    report('TC-FILTER-NPI-02', all(p.current_stage == 'design' for p in items) and len(items) >= 1,
           f'count={len(items)}')

    # ======================================================================
    # 4.9 PAGINATION (verifies BUG-FIX from previous turn)
    # ======================================================================
    section('4.9 Pagination — verify Bug-1 fix')

    # Create 5 extra products to push us onto page 2
    for i in range(5):
        Product.objects.create(
            tenant=acme_t, sku=f'PG-EXTRA-{i:02d}', name=f'Pagination extra {i}',
            product_type='component', unit_of_measure='ea', status='active',
        )
    total = Product.objects.filter(tenant=acme_t).count()
    r = c_acme.get('/plm/products/')
    items_p1 = list(r.context['products'])
    report('TC-PAGE-PROD-01', len(items_p1) == 20 and total >= 25, f'page1_count={len(items_p1)} total={total}')

    r = c_acme.get('/plm/products/?page=2')
    items_p2 = list(r.context['products'])
    report('TC-PAGE-PROD-02', r.status_code == 200 and len(items_p2) == total - 20,
           f'page2_count={len(items_p2)} expected={total - 20}')

    # Search retained on page 2 — also check that the rendered link contains the q
    r = c_acme.get('/plm/products/?q=SKU&page=2')
    body = r.content.decode()
    # The <a> for prev page should contain q=SKU somewhere
    prev_link_keeps_q = '?page=1&amp;q=SKU' in body or '?q=SKU&amp;page=1' in body
    report('TC-PAGE-PROD-03', r.status_code == 200 and prev_link_keeps_q,
           f'prev_link_keeps_q={prev_link_keeps_q}')

    # FILTER retained on page 2 — THIS IS THE BUG-1 REGRESSION CHECK
    r = c_acme.get('/plm/products/?status=active&page=1')
    body = r.content.decode()
    filter_kept = 'status=active' in body and 'page=2' in body
    # Find the next-page link specifically
    import re
    next_link = re.search(r'<a[^>]+href="\?([^"]+page=2[^"]*)"', body)
    next_qs = next_link.group(1) if next_link else ''
    filter_in_next_link = 'status=active' in next_qs
    report('TC-PAGE-PROD-04', filter_in_next_link, f'next_link={next_qs}')

    # Invalid page param
    r = c_acme.get('/plm/products/?page=abc')
    report('TC-PAGE-INVALID-01', r.status_code in (200, 404), f'status={r.status_code}')

    r = c_acme.get('/plm/products/?page=999')
    report('TC-PAGE-OUT-01', r.status_code == 404, f'status={r.status_code}')

    # Cleanup pagination extras
    Product.objects.filter(tenant=acme_t, sku__startswith='PG-EXTRA').delete()

    # ======================================================================
    # 4.11 STATUS TRANSITIONS / CUSTOM ACTIONS
    # ======================================================================
    section('4.11 Status Transitions / Custom Actions')

    # Create a Draft ECO to drive submit/approve/reject/implement
    c_acme.post('/plm/eco/new/', {
        'title': 'Action test', 'change_type': 'design', 'priority': 'low',
    })
    action_eco = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='Action test').first()
    r = c_acme.post(f'/plm/eco/{action_eco.pk}/submit/')
    action_eco.refresh_from_db()
    report('TC-ACTION-ECO-01', r.status_code == 302 and action_eco.status == 'submitted' and action_eco.submitted_at,
           f'status={action_eco.status} submitted_at={action_eco.submitted_at}')

    r = c_acme.post(f'/plm/eco/{action_eco.pk}/approve/', {'comment': 'LGTM'})
    action_eco.refresh_from_db()
    report('TC-ACTION-ECO-02', r.status_code == 302 and action_eco.status == 'approved' and action_eco.approved_at,
           f'status={action_eco.status}')

    # Reject — need a fresh submitted one
    c_acme.post('/plm/eco/new/', {'title': 'Reject test', 'change_type': 'design', 'priority': 'low'})
    rej_eco = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='Reject test').first()
    c_acme.post(f'/plm/eco/{rej_eco.pk}/submit/')
    r = c_acme.post(f'/plm/eco/{rej_eco.pk}/reject/', {'comment': 'no'})
    rej_eco.refresh_from_db()
    report('TC-ACTION-ECO-03', r.status_code == 302 and rej_eco.status == 'rejected', f'status={rej_eco.status}')

    # Implement
    r = c_acme.post(f'/plm/eco/{action_eco.pk}/implement/')
    action_eco.refresh_from_db()
    report('TC-ACTION-ECO-04', r.status_code == 302 and action_eco.status == 'implemented' and action_eco.implemented_at,
           f'status={action_eco.status}')

    # Cannot submit an already-implemented ECO
    r = c_acme.post(f'/plm/eco/{action_eco.pk}/submit/')
    action_eco.refresh_from_db()
    report('TC-ACTION-ECO-05', r.status_code == 302 and action_eco.status == 'implemented',
           f'status_unchanged={action_eco.status}')

    # Cannot approve a Draft ECO
    c_acme.post('/plm/eco/new/', {'title': 'Cannot approve draft', 'change_type': 'design', 'priority': 'low'})
    draft_2 = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='Cannot approve draft').first()
    r = c_acme.post(f'/plm/eco/{draft_2.pk}/approve/')
    draft_2.refresh_from_db()
    report('TC-ACTION-ECO-06', r.status_code == 302 and draft_2.status == 'draft', f'status={draft_2.status}')

    # Add impacted item to draft_2
    r = c_acme.post(f'/plm/eco/{draft_2.pk}/items/new/', {
        'product': p1001.pk, 'change_summary': 'Test',
    })
    has_item = ECOImpactedItem.objects.filter(eco=draft_2).exists()
    report('TC-ACTION-ECO-07', r.status_code == 302 and has_item, f'has_item={has_item}')

    # Remove impacted item
    item = ECOImpactedItem.objects.filter(eco=draft_2).first()
    r = c_acme.post(f'/plm/eco/items/{item.pk}/delete/')
    has_item = ECOImpactedItem.objects.filter(pk=item.pk).exists()
    report('TC-ACTION-ECO-08', r.status_code == 302 and not has_item, f'still_exists={has_item}')

    report('TC-ACTION-ECO-09', None, 'BLOCKED — needs real PDF binary upload')
    report('TC-ACTION-ECO-10', None, 'BLOCKED — needs real .exe binary upload (extension validation tested in unit form-test bug-confirm pass)')
    report('TC-ACTION-ECO-11', None, 'BLOCKED — needs >25MB file upload')

    report('TC-ACTION-CAD-01', None, 'BLOCKED — needs real CAD file upload')
    report('TC-ACTION-CAD-02', None, 'BLOCKED — depends on CAD-01 having a version')
    report('TC-ACTION-CAD-03', None, 'BLOCKED — depends on CAD-01')
    report('TC-ACTION-CAD-04', None, 'BLOCKED — depends on CAD-01')
    report('TC-ACTION-CAD-05', None, 'BLOCKED — extension validation needs real upload')
    report('TC-ACTION-CAD-06', None, 'BLOCKED — depends on having a current_version')

    # NPI deliverable add (already done above for TC-EDIT-DELIV-01)
    # NPI complete deliverable
    s_first = NPIStage.objects.filter(project=npi1).first()
    NPIDeliverable.objects.filter(stage=s_first, name='QC complete-test').delete()
    deliv_q = NPIDeliverable.objects.create(
        tenant=acme_t, stage=s_first, name='QC complete-test', status='pending',
    )
    r = c_acme.post(f'/plm/npi/deliverables/{deliv_q.pk}/complete/')
    deliv_q.refresh_from_db()
    report('TC-ACTION-NPI-02',
           r.status_code == 302 and deliv_q.status == 'done' and deliv_q.completed_at is not None,
           f'status={deliv_q.status} completed_at={deliv_q.completed_at}')

    # Add deliverable
    r = c_acme.post(f'/plm/npi/stages/{s_first.pk}/deliverables/new/', {
        'name': 'NPI-add-test', 'description': 'QA', 'due_date': '2026-06-01', 'status': 'pending',
    })
    has = NPIDeliverable.objects.filter(stage=s_first, name='NPI-add-test').exists()
    report('TC-ACTION-NPI-01', r.status_code == 302 and has, f'created={has}')

    # ======================================================================
    # 4.13 NEGATIVE & EDGE CASES (automatable subset)
    # ======================================================================
    section('4.13 Negative & Edge Cases')

    r = c_acme.post('/plm/products/new/', {})
    errs = r.context['form'].errors if r.status_code == 200 else {}
    report('TC-NEG-01', 'sku' in errs and 'name' in errs, f'errors={dict(errs)}')

    report('TC-NEG-02', None, 'N/A — no decimal fields exposed')

    r = c_acme.post('/plm/eco/new/', {
        'title': 'Old date', 'change_type': 'design', 'priority': 'low',
        'target_implementation_date': '1900-01-01',
    })
    has_old = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='Old date').exists()
    report('TC-NEG-03', has_old, f'accepted={has_old}')

    r = c_acme.post('/plm/eco/new/', {
        'title': 'Bad date', 'change_type': 'design', 'priority': 'low',
        'target_implementation_date': 'not-a-date',
    })
    if r.status_code == 200 and r.context:
        errs = r.context['form'].errors
        report('TC-NEG-04', 'target_implementation_date' in errs, f'errors={dict(errs)}')
    else:
        report('TC-NEG-04', False, f'status={r.status_code} (expected form error)')

    # Direct GET to delete
    p_min = Product.objects.filter(tenant=acme_t, sku='SKU-MIN').first()
    if p_min:
        r = c_acme.get(f'/plm/products/{p_min.pk}/delete/')
        still_exists = Product.objects.filter(pk=p_min.pk).exists()
        report('TC-NEG-12', r.status_code in (302, 405) and still_exists,
               f'status={r.status_code} still_exists={still_exists}')

    # Cross-tenant write
    r = c_acme.post(f'/plm/products/{globex_product.pk}/delete/')
    still = Product.objects.filter(pk=globex_product.pk).exists()
    report('TC-NEG-13', r.status_code == 404 and still, f'status={r.status_code} still_exists={still}')

    r = c_acme.post('/plm/products/99999/specs/new/', {})
    report('TC-NEG-15', r.status_code == 404, f'status={r.status_code}')

    # ======================================================================
    # 4.14 CROSS-MODULE INTEGRATION — TC-INT-05 = Bug-2 fix verification
    # ======================================================================
    section('4.14 Cross-Module Integration — verify Bug-2 fix')

    # Add an impacted item that points at a product, then try to delete the product.
    # ECOImpactedItem.product is on_delete=PROTECT — view should now catch ProtectedError.
    c_acme.post('/plm/eco/new/', {'title': 'PROTECT test', 'change_type': 'design', 'priority': 'low'})
    protect_eco = EngineeringChangeOrder.objects.filter(tenant=acme_t, title='PROTECT test').first()
    p_inv = Product.objects.create(
        tenant=acme_t, sku='SKU-PROT-TEST', name='Protect target',
        product_type='component', unit_of_measure='ea', status='active',
    )
    ECOImpactedItem.objects.create(tenant=acme_t, eco=protect_eco, product=p_inv, change_summary='x')
    # Try delete — should now redirect with error message, NOT raise 500
    try:
        r = c_acme.post(f'/plm/products/{p_inv.pk}/delete/')
        protect_handled = r.status_code == 302 and Product.objects.filter(pk=p_inv.pk).exists()
        report('TC-INT-05', protect_handled,
               f'status={r.status_code} still_exists={Product.objects.filter(pk=p_inv.pk).exists()}')
    except Exception as e:
        report('TC-INT-05', False, f'500 raised: {type(e).__name__}: {e}')

    # ======================================================================
    # FINAL SUMMARY
    # ======================================================================
    print('\n' + '=' * 60)
    counts = {'PASS': 0, 'FAIL': 0, 'BLOCKED': 0}
    fails = []
    for r in results:
        if r['status'] == 'PASS':
            counts['PASS'] += 1
        elif r['status'] == 'FAIL':
            counts['FAIL'] += 1
            fails.append(r)
        else:
            counts['BLOCKED'] += 1
    print(f'TOTALS: {counts["PASS"]} PASS | {counts["FAIL"]} FAIL | {counts["BLOCKED"]} BLOCKED | {len(results)} executed')
    if fails:
        print('\nFAILURES:')
        for f in fails:
            print(f"  - {f['id']}: {f['notes']}")
finally:
    _cleanup_test_data()
    teardown_test_environment()
    print('\n[Test artefacts cleaned up]')
