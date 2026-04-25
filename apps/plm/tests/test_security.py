"""Security tests — OWASP A01 (cross-tenant IDOR) + A04 (workflow bypass) +
A05 (auth-gated media)."""
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.plm.models import (
    CADDocument, CADDocumentVersion, ECOAttachment, EngineeringChangeOrder,
    Product, ProductCompliance,
)


@pytest.mark.django_db
@pytest.mark.security
class TestCrossTenantIDOR:
    """Foreign-tenant access must 404 on every PLM detail/edit/delete URL."""

    def test_product_detail(self, client_globex, product):
        r = client_globex.get(reverse('plm:product_detail', args=[product.pk]))
        assert r.status_code == 404

    def test_product_edit(self, client_globex, product):
        r = client_globex.get(reverse('plm:product_edit', args=[product.pk]))
        assert r.status_code == 404

    def test_product_delete(self, client_globex, product):
        r = client_globex.post(reverse('plm:product_delete', args=[product.pk]))
        assert r.status_code == 404
        assert Product.objects.filter(pk=product.pk).exists()

    @pytest.mark.parametrize('method,url_name', [
        ('get', 'plm:eco_detail'),
        ('get', 'plm:eco_edit'),
        ('post', 'plm:eco_submit'),
        ('post', 'plm:eco_approve'),
        ('post', 'plm:eco_reject'),
        ('post', 'plm:eco_implement'),
        ('post', 'plm:eco_delete'),
    ])
    def test_eco_actions_blocked(self, client_globex, submitted_eco, method, url_name):
        url = reverse(url_name, args=[submitted_eco.pk])
        r = getattr(client_globex, method)(url)
        assert r.status_code == 404
        submitted_eco.refresh_from_db()
        assert submitted_eco.status == 'submitted'


@pytest.mark.django_db
@pytest.mark.security
class TestWorkflowBypass:
    """D-05 regression: ECO status guards on direct POST."""

    def test_implement_non_approved_blocked(self, client_acme, submitted_eco):
        # Status is 'submitted', not 'approved'
        r = client_acme.post(reverse('plm:eco_implement', args=[submitted_eco.pk]))
        submitted_eco.refresh_from_db()
        assert submitted_eco.status == 'submitted'
        assert submitted_eco.implemented_at is None

    def test_double_approve_idempotent(self, client_acme, submitted_eco):
        # First approve succeeds
        r1 = client_acme.post(reverse('plm:eco_approve', args=[submitted_eco.pk]),
                              data={'comment': 'first'})
        submitted_eco.refresh_from_db()
        assert submitted_eco.status == 'approved'
        first_approval_count = submitted_eco.approvals.count()

        # Second approve must NOT create a duplicate ECOApproval row
        r2 = client_acme.post(reverse('plm:eco_approve', args=[submitted_eco.pk]),
                              data={'comment': 'second'})
        submitted_eco.refresh_from_db()
        assert submitted_eco.approvals.count() == first_approval_count


@pytest.mark.django_db
@pytest.mark.security
class TestAuthGatedDownloadsD03:
    """D-03 regression: file downloads must require auth + tenant ownership."""

    @pytest.fixture
    def cad_version_with_file(self, acme):
        doc = CADDocument.objects.create(
            tenant=acme, drawing_number='DL-T1', title='Test',
        )
        v = CADDocumentVersion.objects.create(
            tenant=acme, document=doc, version='1.0', status='draft',
        )
        v.file.save('test.pdf', ContentFile(b'%PDF-1.4 stub'))
        return v

    def test_owner_can_download(self, client_acme, cad_version_with_file):
        url = reverse('plm:cad_version_download', args=[cad_version_with_file.pk])
        r = client_acme.get(url)
        assert r.status_code == 200

    def test_other_tenant_blocked(self, client_globex, cad_version_with_file):
        url = reverse('plm:cad_version_download', args=[cad_version_with_file.pk])
        r = client_globex.get(url)
        assert r.status_code == 404

    def test_anonymous_redirected_to_login(self, client, cad_version_with_file):
        url = reverse('plm:cad_version_download', args=[cad_version_with_file.pk])
        r = client.get(url)
        assert r.status_code == 302
        assert '/accounts/login' in r.url
