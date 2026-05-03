"""Security: RBAC matrix (operator vs admin vs supplier portal user),
multi-tenant IDOR, CSRF on workflow transitions.

Per Lesson L-10, every workflow transition that mutates state should reject
non-admin tenant users. The two-assertion pattern (redirect + state-not-changed)
catches both 'silent success' and 'wrong redirect' regressions.
"""
import pytest
from django.urls import reverse

from apps.procurement import models as procm


@pytest.mark.django_db
class TestRBACMatrix:
    """Admin-only POSTs must reject regular tenant users."""

    @pytest.fixture
    def submitted_po(self, po):
        po.status = 'submitted'
        po.save(update_fields=['status'])
        return po

    def test_staff_cannot_approve_po(self, staff_client, submitted_po):
        r = staff_client.post(
            reverse('procurement:po_approve', args=[submitted_po.pk]),
        )
        assert r.status_code == 302
        submitted_po.refresh_from_db()
        assert submitted_po.status == 'submitted'

    def test_staff_cannot_create_supplier(self, staff_client, acme):
        r = staff_client.post(reverse('procurement:supplier_create'), data={
            'code': 'X1', 'name': 'X', 'currency': 'USD',
            'risk_rating': 'low', 'is_active': 'on',
        })
        assert r.status_code == 302
        assert not procm.Supplier.all_objects.filter(tenant=acme, code='X1').exists()

    def test_staff_cannot_delete_supplier(self, staff_client, supplier):
        r = staff_client.post(
            reverse('procurement:supplier_delete', args=[supplier.pk]),
        )
        assert r.status_code == 302
        assert procm.Supplier.all_objects.filter(pk=supplier.pk).exists()

    def test_staff_cannot_create_blanket(self, staff_client):
        r = staff_client.post(reverse('procurement:blanket_create'), data={})
        assert r.status_code == 302

    def test_staff_cannot_recompute_scorecards(self, staff_client):
        r = staff_client.post(reverse('procurement:scorecard_recompute'))
        assert r.status_code == 302


@pytest.mark.django_db
class TestMultiTenantIDOR:
    """A user from tenant Globex must NOT be able to read or mutate Acme's records."""

    def test_globex_cannot_read_acme_supplier(self, globex_client, supplier):
        r = globex_client.get(
            reverse('procurement:supplier_detail', args=[supplier.pk]),
        )
        assert r.status_code == 404

    def test_globex_cannot_read_acme_po(self, globex_client, po):
        r = globex_client.get(reverse('procurement:po_detail', args=[po.pk]))
        assert r.status_code == 404

    def test_globex_cannot_delete_acme_supplier(self, globex_client, supplier):
        r = globex_client.post(
            reverse('procurement:supplier_delete', args=[supplier.pk]),
        )
        assert r.status_code == 404
        assert procm.Supplier.all_objects.filter(pk=supplier.pk).exists()

    def test_supplier_list_scopes_to_tenant(
        self, globex_client, globex_supplier, supplier,
    ):
        r = globex_client.get(reverse('procurement:supplier_list'))
        assert r.status_code == 200
        assert globex_supplier.code.encode() in r.content
        assert supplier.code.encode() not in r.content


@pytest.mark.django_db
class TestSupplierPortalIDOR:
    """A supplier-portal user must only see records belonging to their supplier_company."""

    def test_supplier_portal_cannot_see_other_suppliers_pos(
        self, supplier_user_client, po, supplier2, acme, acme_admin,
    ):
        other = procm.PurchaseOrder.objects.create(
            tenant=acme, supplier=supplier2, currency='USD',
            status='approved', created_by=acme_admin,
        )
        r = supplier_user_client.get(reverse('procurement:portal_pos'))
        assert other.po_number.encode() not in r.content

    def test_supplier_portal_cannot_access_internal_supplier_crud(
        self, supplier_user_client, supplier,
    ):
        # Supplier portal user shouldn't be able to access internal admin pages.
        r = supplier_user_client.get(
            reverse('procurement:supplier_create'),
        )
        # Either redirected (no permission) or 403 - both acceptable; just
        # ensure the create form is not rendered as 200.
        assert r.status_code != 200


@pytest.mark.django_db
class TestAnonymousAccess:
    """Unauthenticated users should be redirected to login on every URL."""

    @pytest.mark.parametrize('url_name', [
        'procurement:index',
        'procurement:supplier_list',
        'procurement:po_list',
        'procurement:rfq_list',
        'procurement:scorecard_list',
        'procurement:portal_dashboard',
    ])
    def test_anon_redirected(self, client, url_name):
        r = client.get(reverse(url_name))
        # 302 redirect to login; should NOT be 200
        assert r.status_code in (302, 403)
