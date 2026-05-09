"""N+1 query budgets for the compliance UI."""
import pytest
from django.urls import reverse

from apps.plm.models import ComplianceAuditLog, Product
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestQueryBudgets:

    def test_list_view_under_budget(self, client_acme, acme, category, django_assert_max_num_queries):
        for i in range(25):
            p = Product.objects.create(
                tenant=acme, sku=f'P-{i:03d}', name=f'P {i}', category=category,
                product_type='component', status='active',
            )
            make_compliance(tenant=acme, product=p, standard=make_standard())
        # Page renders 20 records (page 1) + select_related on product + standard.
        # Generous budget — sessions, auth, tenant, count, page, list = ~8 queries.
        with django_assert_max_num_queries(15):
            r = client_acme.get(reverse('plm:compliance_list'))
            assert r.status_code == 200

    def test_detail_view_under_budget(self, client_acme, acme, product,
                                      django_assert_max_num_queries):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        # Auto-generate 50 audit entries (the create above already added 1)
        for _ in range(50):
            ComplianceAuditLog.objects.create(
                tenant=acme, compliance=rec, event='note_added', meta={'note': 'x'},
            )
        with django_assert_max_num_queries(12):
            r = client_acme.get(reverse('plm:compliance_detail', args=[rec.pk]))
            assert r.status_code == 200
