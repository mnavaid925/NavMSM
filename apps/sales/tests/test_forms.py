"""Form-level tests for Module 17 - Sales (17.1)."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.sales.forms import (
    CustomerForm,
    CustomerCategoryForm,
    PriceListForm,
    CustomerDocumentForm,
    CommunicationLogForm,
)
from apps.sales.models import _validate_customer_doc


pytestmark = pytest.mark.django_db


def test_customer_form_minimal_valid(tenant_a):
    form = CustomerForm(
        data={
            'name': 'Foo',
            'customer_class': 'standard',
            'currency': 'USD',
            'payment_terms': 'net30',
            'credit_limit': '0',
            'status': 'active',
        },
        tenant=tenant_a,
    )
    assert form.is_valid(), form.errors


def test_pricelist_form_requires_name():
    form = PriceListForm(data={'currency': 'USD'})
    assert not form.is_valid()
    assert 'name' in form.errors


def test_document_validator_size_cap():
    """L-22: files over 25 MB rejected."""
    big = SimpleUploadedFile('x.pdf', b'a' * (25 * 1024 * 1024 + 1))
    with pytest.raises(ValidationError):
        _validate_customer_doc(big)


def test_document_validator_extension_allowlist():
    """L-22: only PDF/PNG/JPG/JPEG/DOCX accepted."""
    bad = SimpleUploadedFile('x.exe', b'malware')
    with pytest.raises(ValidationError):
        _validate_customer_doc(bad)
    ok = SimpleUploadedFile('x.pdf', b'pdf')
    _validate_customer_doc(ok)  # must not raise


def test_category_form_excludes_self_from_parent(tenant_a, category):
    """Editing a category must not allow itself as parent."""
    form = CustomerCategoryForm(instance=category, tenant=tenant_a)
    assert category not in form.fields['parent'].queryset
