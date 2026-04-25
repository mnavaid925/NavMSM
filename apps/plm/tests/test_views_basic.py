"""Basic list / create smoke tests for all 5 PLM sub-modules."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestPLMListPagesRender:

    @pytest.mark.parametrize('url_name', [
        'plm:index',
        'plm:product_list', 'plm:product_create',
        'plm:category_list', 'plm:category_create',
        'plm:eco_list', 'plm:eco_create',
        'plm:cad_list', 'plm:cad_create',
        'plm:compliance_list', 'plm:compliance_create',
        'plm:npi_list', 'plm:npi_create',
    ])
    def test_render_200(self, client_acme, url_name, standard):
        # `standard` fixture ensures at least one ComplianceStandard exists
        # for the compliance form's queryset.
        r = client_acme.get(reverse(url_name))
        assert r.status_code == 200

    def test_paginate_preserves_filters_d06(self, client_acme, acme, category):
        """D-06 regression: filters survive pagination. Seed > 20 products
        with status='obsolete' so we get a real page-2 link."""
        from apps.plm.models import Product
        for i in range(25):
            Product.objects.create(
                tenant=acme, sku=f'OBSOLETE-{i:03d}', name=f'Old #{i}',
                category=category, product_type='component', status='obsolete',
            )
        r = client_acme.get('/plm/products/?status=obsolete')
        assert r.status_code == 200
        body = r.content.decode()
        # Pagination links must carry status=obsolete forward
        assert 'status=obsolete' in body
