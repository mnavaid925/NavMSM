"""Model invariants — uniqueness, str(), helpers."""
import pytest
from django.db import IntegrityError

from apps.plm.models import Product, ProductRevision, EngineeringChangeOrder


@pytest.mark.django_db
class TestProduct:
    def test_sku_unique_per_tenant(self, acme, category):
        Product.objects.create(tenant=acme, sku='X-1', name='A', category=category)
        with pytest.raises(IntegrityError):
            Product.objects.create(tenant=acme, sku='X-1', name='B', category=category)

    def test_sku_can_repeat_across_tenants(self, acme, globex, category):
        Product.objects.create(tenant=acme, sku='X-1', name='A', category=category)
        Product.objects.create(tenant=globex, sku='X-1', name='B')

    def test_str_contains_sku(self, product):
        assert product.sku in str(product)


@pytest.mark.django_db
class TestProductRevision:
    def test_revision_unique_per_product(self, acme, product):
        ProductRevision.objects.create(tenant=acme, product=product, revision_code='A')
        with pytest.raises(IntegrityError):
            ProductRevision.objects.create(tenant=acme, product=product, revision_code='A')

    def test_str_contains_product_sku(self, revision):
        assert revision.product.sku in str(revision)


@pytest.mark.django_db
class TestECO:
    def test_is_editable_only_in_draft(self, eco):
        assert eco.is_editable() is True
        eco.status = 'submitted'; eco.save()
        assert eco.is_editable() is False
