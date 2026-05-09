"""OWASP A01 (cross-tenant IDOR) + A05 (file-download gating) for compliance."""
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.plm.models import ProductCompliance
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
@pytest.mark.security
class TestComplianceCrossTenantIDOR:

    @pytest.fixture
    def acme_record(self, acme, product):
        return make_compliance(tenant=acme, product=product, standard=make_standard())

    @pytest.mark.parametrize('method,url_name', [
        ('get', 'plm:compliance_detail'),
        ('get', 'plm:compliance_edit'),
        ('post', 'plm:compliance_delete'),
        ('get', 'plm:compliance_certificate_download'),
    ])
    def test_globex_blocked(self, client_globex, acme_record, method, url_name):
        url = reverse(url_name, args=[acme_record.pk])
        r = getattr(client_globex, method)(url)
        assert r.status_code == 404
        # Row remains intact
        assert ProductCompliance.objects.filter(pk=acme_record.pk).exists()


@pytest.mark.django_db
@pytest.mark.security
class TestCertificateDownloadGating:

    @pytest.fixture
    def record_with_cert(self, acme, product):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        rec.certificate_file.save('cert.pdf', ContentFile(b'%PDF-1.4 stub'))
        return rec

    def test_anonymous_redirects_to_login(self, client, record_with_cert):
        r = client.get(reverse('plm:compliance_certificate_download', args=[record_with_cert.pk]))
        assert r.status_code == 302
        assert '/accounts/login' in r.url

    def test_owner_streams_file(self, client_acme, record_with_cert):
        r = client_acme.get(reverse('plm:compliance_certificate_download', args=[record_with_cert.pk]))
        assert r.status_code == 200
        assert 'attachment' in r['Content-Disposition'].lower()

    def test_owner_no_cert_returns_404(self, client_acme, acme, product):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        r = client_acme.get(reverse('plm:compliance_certificate_download', args=[rec.pk]))
        assert r.status_code == 404
