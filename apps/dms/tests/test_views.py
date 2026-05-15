"""HTTP CRUD smoke + workflow happy paths."""
import pytest
from django.urls import reverse


def _login(client, user):
    """Set both the session login + the tenant binding the middleware reads."""
    client.force_login(user)


@pytest.mark.django_db
class TestListPages:
    @pytest.mark.parametrize('name', [
        'dms:index', 'dms:category_list', 'dms:document_list',
        'dms:template_list', 'dms:workflow_list', 'dms:approval_list',
        'dms:assignment_list', 'dms:my_acknowledgments',
        'dms:policy_list', 'dms:archive_list', 'dms:legal_hold_list',
    ])
    def test_list_200(self, client, tenant_admin, name):
        _login(client, tenant_admin)
        resp = client.get(reverse(name))
        assert resp.status_code == 200, name


@pytest.mark.django_db
class TestDocumentCrud:
    def test_create_document(self, client, tenant_admin, category):
        _login(client, tenant_admin)
        resp = client.post(reverse('dms:document_create'), {
            'title': 'New SOP',
            'doc_type': 'sop',
            'category': category.pk,
            'is_active': 'on',
            'summary': '',
            'keywords': '',
        })
        assert resp.status_code == 302
        from apps.dms.models import Document
        assert Document.objects.filter(tenant=tenant_admin.tenant, title='New SOP').exists()

    def test_detail_page(self, client, tenant_admin, document):
        _login(client, tenant_admin)
        resp = client.get(reverse('dms:document_detail', args=[document.pk]))
        assert resp.status_code == 200

    def test_submit_for_review_flips_status(self, client, tenant_admin, tenant_a, document):
        from apps.dms.models import DocumentVersion
        DocumentVersion.objects.create(tenant=tenant_a, document=document, version='1')
        _login(client, tenant_admin)
        resp = client.post(reverse('dms:document_submit', args=[document.pk]))
        assert resp.status_code == 302
        document.refresh_from_db()
        assert document.status == 'in_review'

    def test_archive_action(self, client, tenant_admin, document):
        _login(client, tenant_admin)
        resp = client.post(reverse('dms:document_archive', args=[document.pk]))
        assert resp.status_code == 302
        document.refresh_from_db()
        assert document.status == 'archived'

    def test_delete_blocks_locked(self, client, tenant_admin, document):
        from apps.dms.models import Document
        Document.all_objects.filter(pk=document.pk).update(is_locked=True)
        _login(client, tenant_admin)
        resp = client.post(reverse('dms:document_delete', args=[document.pk]))
        # 302 back to detail; document still exists.
        assert Document.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
class TestVersionCheckout:
    def test_check_out_round_trip(self, client, tenant_admin, version):
        _login(client, tenant_admin)
        r1 = client.post(reverse('dms:version_check_out', args=[version.pk]))
        assert r1.status_code == 302
        version.refresh_from_db()
        assert version.checked_out_by_id == tenant_admin.id
        r2 = client.post(reverse('dms:version_check_in', args=[version.pk]))
        assert r2.status_code == 302
        version.refresh_from_db()
        assert version.checked_out_by_id is None

    def test_release_action(self, client, tenant_admin, version):
        _login(client, tenant_admin)
        resp = client.post(reverse('dms:version_release', args=[version.pk]))
        assert resp.status_code == 302
        version.refresh_from_db()
        assert version.status == 'released'
        assert version.released_at is not None


@pytest.mark.django_db
class TestApprovalWorkflow:
    def test_full_walk_to_approved(self, client, tenant_admin, tenant_a, document, workflow_with_stages):
        _login(client, tenant_admin)
        # Create the request via the form view.
        resp = client.post(reverse('dms:approval_create'), {
            'document': document.pk,
            'workflow': workflow_with_stages.pk,
            'effective_date': '',
            'notes': 'Test',
        })
        assert resp.status_code == 302
        from apps.dms.models import DocumentApprovalRequest
        req = DocumentApprovalRequest.objects.get(tenant=tenant_a, document=document)

        # Stage 1 approve.
        client.post(reverse('dms:approval_action', args=[req.pk]), {
            'decision': 'approve',
            'typed_name': 'Test Admin',
            'notes': '',
        })
        req.refresh_from_db()
        assert req.current_stage_no == 2
        assert req.status == 'in_progress'

        # Stage 2 approve.
        client.post(reverse('dms:approval_action', args=[req.pk]), {
            'decision': 'approve',
            'typed_name': 'Test Admin',
            'notes': '',
        })
        req.refresh_from_db()
        assert req.status == 'approved'
        document.refresh_from_db()
        assert document.status == 'effective'

    def test_reject_terminates(self, client, tenant_admin, document, workflow_with_stages, tenant_a):
        _login(client, tenant_admin)
        from apps.dms.models import DocumentApprovalRequest
        req = DocumentApprovalRequest.objects.create(
            tenant=tenant_a, document=document, workflow=workflow_with_stages,
            status='in_progress',
        )
        client.post(reverse('dms:approval_action', args=[req.pk]), {
            'decision': 'reject',
            'typed_name': 'Test',
            'notes': 'No good',
        })
        req.refresh_from_db()
        assert req.status == 'rejected'

    def test_reject_without_notes_blocked(self, client, tenant_admin, document, workflow_with_stages, tenant_a):
        _login(client, tenant_admin)
        from apps.dms.models import DocumentApprovalRequest
        req = DocumentApprovalRequest.objects.create(
            tenant=tenant_a, document=document, workflow=workflow_with_stages,
            status='in_progress',
        )
        client.post(reverse('dms:approval_action', args=[req.pk]), {
            'decision': 'reject',
            'typed_name': 'Test',
            'notes': '',
        })
        req.refresh_from_db()
        # Notes required - status stays unchanged.
        assert req.status == 'in_progress'


@pytest.mark.django_db
class TestAssignmentAck:
    def test_ack_records_row(self, client, staff_user, tenant_a, document):
        from apps.dms.models import (
            DocumentAssignment, DocumentVersion, ReadAcknowledgment,
        )
        v = DocumentVersion.objects.create(
            tenant=tenant_a, document=document, version='1', status='released',
        )
        # Re-bind current_version after signal.
        document.refresh_from_db()
        asn = DocumentAssignment.objects.create(
            tenant=tenant_a, document=document, status='active',
        )
        _login(client, staff_user)
        resp = client.post(reverse('dms:assignment_ack', args=[asn.pk]), {
            'typed_name': 'Staff A', 'notes': '',
        })
        assert resp.status_code == 302
        assert ReadAcknowledgment.objects.filter(assignment=asn, acknowledger=staff_user).exists()

    def test_double_ack_idempotent(self, client, staff_user, tenant_a, document):
        from apps.dms.models import (
            DocumentAssignment, DocumentVersion, ReadAcknowledgment,
        )
        DocumentVersion.objects.create(
            tenant=tenant_a, document=document, version='1', status='released',
        )
        document.refresh_from_db()
        asn = DocumentAssignment.objects.create(
            tenant=tenant_a, document=document, status='active',
        )
        _login(client, staff_user)
        for _ in range(2):
            client.post(reverse('dms:assignment_ack', args=[asn.pk]), {
                'typed_name': 'Staff A', 'notes': '',
            })
        assert ReadAcknowledgment.objects.filter(assignment=asn, acknowledger=staff_user).count() == 1


@pytest.mark.django_db
class TestListFilters:
    def test_document_filter_by_status(self, client, tenant_admin, tenant_a, category):
        from apps.dms.models import Document
        d1 = Document.objects.create(tenant=tenant_a, title='Draft', status='draft', category=category)
        d2 = Document.objects.create(tenant=tenant_a, title='Effective', status='effective', category=category)
        _login(client, tenant_admin)
        resp = client.get(reverse('dms:document_list'), {'status': 'effective'})
        assert resp.status_code == 200
        body = resp.content.decode()
        assert d2.code in body
        assert d1.code not in body
