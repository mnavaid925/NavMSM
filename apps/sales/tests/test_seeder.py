"""Seeder idempotency test for Module 17 - Sales (17.1)."""
import pytest
from django.core.management import call_command

from apps.sales.models import Customer


pytestmark = pytest.mark.django_db


def test_seed_sales_is_idempotent(tenant_a):
    """Running the seeder twice must not double-create rows."""
    call_command('seed_sales', '--tenant', tenant_a.slug)
    n1 = Customer.all_objects.filter(tenant=tenant_a).count()
    call_command('seed_sales', '--tenant', tenant_a.slug)
    n2 = Customer.all_objects.filter(tenant=tenant_a).count()
    assert n1 == n2
    assert n1 > 0


def test_seed_sales_flush(tenant_a):
    call_command('seed_sales', '--tenant', tenant_a.slug)
    n1 = Customer.all_objects.filter(tenant=tenant_a).count()
    call_command('seed_sales', '--tenant', tenant_a.slug, '--flush')
    n2 = Customer.all_objects.filter(tenant=tenant_a).count()
    assert n2 == n1  # same final state - same seed data
