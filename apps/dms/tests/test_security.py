"""Multi-tenant IDOR + RBAC matrix + anonymous redirect."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestAnonymousRedirect:
    @pytest.mark.parametrize('name', [
        'dms:index', 'dms:category_list', 'dms:document_list',
        'dms:template_list', 'dms:workflow_list', 'dms:approval_list',
        'dms:assignment_list', 'dms:my_acknowledgments',
        'dms:policy_list', 'dms:archive_list', 'dms:legal_hold_list',
    ])
    def test_anonymous_redirects_to_login(self, client, name):
        resp = client.get(reverse(name))
        assert resp.status_code == 302
        assert '/accounts/login' in resp.url or 'next=' in resp.url


@pytest.mark.django_db
class TestCrossTenantIdor:
    def test_document_404_cross_tenant(self, client, tenant_admin, tenant_b):
        from apps.dms.models import Document
        other = Document.objects.create(tenant=tenant_b, title='Other')
        client.force_login(tenant_admin)
        resp = client.get(reverse('dms:document_detail', args=[other.pk]))
        assert resp.status_code == 404

    def test_legal_hold_404_cross_tenant(self, client, tenant_admin, tenant_b):
        from apps.dms.models import LegalHold
        h = LegalHold.objects.create(tenant=tenant_b, name='Other Hold')
        client.force_login(tenant_admin)
        resp = client.get(reverse('dms:legal_hold_detail', args=[h.pk]))
        assert resp.status_code == 404

    def test_assignment_404_cross_tenant(self, client, tenant_admin, tenant_b):
        from apps.dms.models import Document, DocumentAssignment
        d = Document.objects.create(tenant=tenant_b, title='X')
        a = DocumentAssignment.objects.create(tenant=tenant_b, document=d)
        client.force_login(tenant_admin)
        resp = client.get(reverse('dms:assignment_detail', args=[a.pk]))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestRbacMatrix:
    """Non-admin staff cannot perform admin-only state mutations."""

    def test_staff_cannot_delete_document(self, client, staff_user, document):
        client.force_login(staff_user)
        # The view decorator bounces back to dashboard with a flash message
        resp = client.post(reverse('dms:document_delete', args=[document.pk]))
        assert resp.status_code == 302
        from apps.dms.models import Document
        assert Document.objects.filter(pk=document.pk).exists()

    def test_staff_cannot_archive_document(self, client, staff_user, document):
        client.force_login(staff_user)
        client.post(reverse('dms:document_archive', args=[document.pk]))
        document.refresh_from_db()
        assert document.status != 'archived'

    def test_staff_cannot_create_legal_hold(self, client, staff_user):
        client.force_login(staff_user)
        resp = client.get(reverse('dms:legal_hold_create'))
        assert resp.status_code == 302
        assert reverse('dms:index') in resp.url

    def test_staff_cannot_release_legal_hold(self, client, staff_user, tenant_a):
        from apps.dms.models import LegalHold
        h = LegalHold.objects.create(tenant=tenant_a, name='H', status='active')
        client.force_login(staff_user)
        resp = client.post(reverse('dms:legal_hold_release', args=[h.pk]), {
            'release_notes': 'Stop',
        })
        h.refresh_from_db()
        assert h.status == 'active'

    def test_staff_cannot_approve_request(self, client, staff_user, tenant_a, document, workflow_with_stages):
        from apps.dms.models import DocumentApprovalRequest
        req = DocumentApprovalRequest.objects.create(
            tenant=tenant_a, document=document, workflow=workflow_with_stages,
            status='in_progress',
        )
        client.force_login(staff_user)
        client.post(reverse('dms:approval_action', args=[req.pk]), {
            'decision': 'approve', 'notes': '', 'typed_name': 'X',
        })
        req.refresh_from_db()
        assert req.status == 'in_progress'  # not approved


@pytest.mark.django_db
class TestSignatureInsertOnlyAdmin:
    """DocumentSignature must not allow in-place edits."""

    def test_admin_change_view_readonly(self, client, tenant_admin, tenant_a, document):
        from apps.dms.models import DocumentSignature
        sig = DocumentSignature.objects.create(
            tenant=tenant_a, document=document, signer=tenant_admin,
            meaning='approver', typed_name='Original',
        )
        # Admin readonly_fields = all fields; the admin POST would not change anything.
        # Verify the model-level immutability:
        sig.typed_name = 'Changed'
        with pytest.raises(PermissionError):
            sig.save()
