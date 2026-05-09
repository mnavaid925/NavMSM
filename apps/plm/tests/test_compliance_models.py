"""Unit tests for compliance model invariants."""
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.plm.models import ComplianceStandard, ProductCompliance
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestComplianceStandard:
    def test_code_globally_unique(self):
        ComplianceStandard.objects.create(code='RoHS-T', name='RoHS Test')
        with pytest.raises(IntegrityError):
            ComplianceStandard.objects.create(code='RoHS-T', name='dup')

    def test_str_format(self):
        s = ComplianceStandard.objects.create(code='CE-T', name='CE Marking Test')
        assert 'CE-T' in str(s) and 'CE Marking Test' in str(s)


@pytest.mark.django_db
class TestProductCompliance:
    def test_unique_per_tenant_product_standard(self, acme, product):
        std = make_standard()
        ProductCompliance.objects.create(tenant=acme, product=product, standard=std)
        with pytest.raises(IntegrityError):
            ProductCompliance.objects.create(tenant=acme, product=product, standard=std)

    def test_str_includes_sku_and_code(self, acme, product):
        rec = make_compliance(tenant=acme, product=product)
        assert product.sku in str(rec)
        assert rec.standard.code in str(rec)

    @pytest.mark.parametrize('expiry_offset_days,expected', [
        (-1, False),   # already expired
        (0, False),    # today (boundary)
        (1, True),     # tomorrow
        (30, True),    # max in window
        (31, False),   # just outside window
        (None, False), # no expiry
    ])
    def test_is_expiring_soon_boundary(self, acme, product, expiry_offset_days, expected):
        # `is_expiring_soon` uses `timezone.now().date()` which is the project
        # tz (UTC). Build the expiry against the same clock so the test does
        # not flake when the worker's local date differs from UTC date.
        today = timezone.now().date()
        expiry = (today + timedelta(days=expiry_offset_days)) if expiry_offset_days is not None else None
        rec = make_compliance(tenant=acme, product=product, expiry_date=expiry)
        assert rec.is_expiring_soon() is expected
