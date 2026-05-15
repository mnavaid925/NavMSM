"""Form-level tests for Module 18 - Returns & RMA.

Covers L-01 (tenant unique_together duplicate-check in clean()) and the
per-tenant FK queryset scoping in __init__.
"""
import pytest

pytestmark = pytest.mark.django_db


def test_reason_form_rejects_duplicate_name_within_tenant(tenant_a):
    from apps.rma.forms import RMAReasonForm
    from apps.rma.models import RMAReason
    RMAReason.objects.create(tenant=tenant_a, name='Dup', category='other')
    form = RMAReasonForm(
        data={'name': 'Dup', 'category': 'other', 'description': '', 'is_active': True},
        tenant=tenant_a,
    )
    assert form.is_valid() is False
    assert any('already exists' in str(e).lower() for e in form.errors.get('__all__', []))


def test_reason_form_accepts_duplicate_name_across_tenants(tenant_a, tenant_b):
    """L-01 isolation: duplicate name across tenants is fine."""
    from apps.rma.forms import RMAReasonForm
    from apps.rma.models import RMAReason
    RMAReason.objects.create(tenant=tenant_b, name='Same', category='other')
    form = RMAReasonForm(
        data={'name': 'Same', 'category': 'other', 'description': '', 'is_active': True},
        tenant=tenant_a,
    )
    assert form.is_valid() is True


def test_failure_mode_form_unique_clean(tenant_a):
    from apps.rma.forms import FailureModeForm
    from apps.rma.models import FailureMode
    FailureMode.objects.create(tenant=tenant_a, name='F1', category='mechanical')
    form = FailureModeForm(
        data={'name': 'F1', 'category': 'mechanical', 'description': '', 'is_active': True},
        tenant=tenant_a,
    )
    assert form.is_valid() is False


def test_root_cause_form_unique_clean(tenant_a):
    from apps.rma.forms import RootCauseCategoryForm
    from apps.rma.models import RootCauseCategory
    RootCauseCategory.objects.create(tenant=tenant_a, name='RC1', responsible_area='design')
    form = RootCauseCategoryForm(
        data={'name': 'RC1', 'responsible_area': 'design', 'description': '', 'is_active': True},
        tenant=tenant_a,
    )
    assert form.is_valid() is False


def test_rma_request_form_excludes_blacklisted_customers(tenant_a, customer):
    from apps.rma.forms import RMARequestForm
    from apps.sales.models import Customer
    Customer.objects.create(tenant=tenant_a, name='Blacklisted', status='blacklisted')
    form = RMARequestForm(tenant=tenant_a)
    statuses = list(form.fields['customer'].queryset.values_list('status', flat=True))
    assert 'blacklisted' not in statuses


def test_rma_request_form_customer_queryset_tenant_scoped(tenant_a, tenant_b, customer):
    from apps.rma.forms import RMARequestForm
    from apps.sales.models import Customer
    Customer.all_objects.create(tenant=tenant_b, name='Other Tenant Customer')
    form = RMARequestForm(tenant=tenant_a)
    assert all(c.tenant_id == tenant_a.id for c in form.fields['customer'].queryset)


def test_warranty_registration_form_policy_filtered_active(tenant_a):
    from apps.rma.forms import WarrantyRegistrationForm
    from apps.rma.models import WarrantyPolicy
    WarrantyPolicy.objects.create(
        tenant=tenant_a, name='Active', coverage_type='full',
        duration_months=12, is_active=True,
    )
    WarrantyPolicy.objects.create(
        tenant=tenant_a, name='Inactive', coverage_type='full',
        duration_months=12, is_active=False,
    )
    form = WarrantyRegistrationForm(tenant=tenant_a)
    names = list(form.fields['policy'].queryset.values_list('name', flat=True))
    assert 'Active' in names and 'Inactive' not in names
