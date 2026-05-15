"""Seeder idempotency test for Module 18 - Returns & RMA.

Running `seed_rma` twice in a row must NOT duplicate rows. The second
invocation skips silently because data already exists for the tenant.
"""
import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_seed_rma_is_idempotent(tenant_a):
    """First run seeds catalogs; second run is a no-op."""
    from apps.rma.models import RMAReason
    # Without sales.Customer / plm.Product the seeder bails after catalogs,
    # but the catalog rows are still created.
    call_command('seed_rma', '--tenant', tenant_a.slug)
    after_first = RMAReason.all_objects.filter(tenant=tenant_a).count()
    assert after_first >= 5

    # Run again - the "data already exists" guard short-circuits.
    call_command('seed_rma', '--tenant', tenant_a.slug)
    after_second = RMAReason.all_objects.filter(tenant=tenant_a).count()
    assert after_second == after_first


def test_seed_rma_flush_resets(tenant_a):
    from apps.rma.models import FailureMode, RMAReason, RootCauseCategory
    call_command('seed_rma', '--tenant', tenant_a.slug)
    assert RMAReason.all_objects.filter(tenant=tenant_a).exists()

    # --flush then re-seed; counts should be identical.
    before = (
        RMAReason.all_objects.filter(tenant=tenant_a).count(),
        FailureMode.all_objects.filter(tenant=tenant_a).count(),
        RootCauseCategory.all_objects.filter(tenant=tenant_a).count(),
    )
    call_command('seed_rma', '--tenant', tenant_a.slug, '--flush')
    after = (
        RMAReason.all_objects.filter(tenant=tenant_a).count(),
        FailureMode.all_objects.filter(tenant=tenant_a).count(),
        RootCauseCategory.all_objects.filter(tenant=tenant_a).count(),
    )
    assert before == after


def test_expire_warranties_command_dry_run_safe(tenant_a):
    """Dry-run must NOT mutate anything."""
    from apps.rma.models import WarrantyPolicy, WarrantyRegistration
    from datetime import date, timedelta
    pol = WarrantyPolicy.objects.create(
        tenant=tenant_a, name='Test1mo', coverage_type='parts',
        duration_months=1,
    )
    from apps.plm.models import Product
    from apps.sales.models import Customer
    p = Product.objects.create(tenant=tenant_a, sku='X', name='X')
    c = Customer.objects.create(tenant=tenant_a, name='C')
    # Aged purchase -> end_date in the past
    reg = WarrantyRegistration.objects.create(
        tenant=tenant_a, product=p, customer=c, policy=pol,
        purchase_date=date.today() - timedelta(days=60),
        start_date=date.today() - timedelta(days=60),
        status='active',
    )
    assert reg.end_date < date.today()

    call_command('expire_warranties', '--tenant', tenant_a.slug, '--dry-run')
    reg.refresh_from_db()
    assert reg.status == 'active'  # dry-run did not mutate

    call_command('expire_warranties', '--tenant', tenant_a.slug)
    reg.refresh_from_db()
    assert reg.status == 'expired'
